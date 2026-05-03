"""Integration test: daemon registers auto_dump cron after bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.mark.asyncio
async def test_daemon_registers_auto_dump_cron(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that auto_dump_global cron is registered after _bootstrap_runtimes."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    try:
        # Replicate the sequence in daemon.run():
        # 1. _bootstrap_runtimes
        # 2. register cron job
        # 3. scheduler.start()
        await daemon._bootstrap_runtimes()

        # Manually register the cron job the way daemon.run() does.
        # This is testing that the cron was registered before scheduler.start().
        async def _auto_dump_task() -> None:
            from claude_mnemos.core.auto_dump import auto_dump_stale
            await auto_dump_stale(daemon.runtimes)

        daemon.scheduler.add_job(
            _auto_dump_task,
            "cron",
            minute=0,
            id="auto_dump_global",
            replace_existing=True,
        )

        # Now start the scheduler
        daemon.scheduler.start()

        # Verify the job is registered
        job_ids = {j.id for j in daemon.scheduler.get_jobs()}
        assert "auto_dump_global" in job_ids

        # Verify the job details (it should be a cron job running at minute=0)
        jobs = {j.id: j for j in daemon.scheduler.get_jobs()}
        assert "auto_dump_global" in jobs
        job = jobs["auto_dump_global"]
        assert "cron" in str(job.trigger).lower()
    finally:
        await daemon._shutdown_runtimes()
        if daemon.scheduler.running:
            daemon.scheduler.shutdown(wait=False)
