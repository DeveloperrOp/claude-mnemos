"""Integration test: daemon registers auto_dump cron after bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.mark.asyncio
async def test_register_auto_dump_cron_adds_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling _register_auto_dump_cron must add 'auto_dump_global' to scheduler.

    This validates that the production method (called from run()) does its job.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    try:
        # Bootstrap minimal vault state (zero projects is fine).
        await daemon._bootstrap_runtimes()

        # Call the production helper directly — this is what run() does.
        daemon._register_auto_dump_cron()

        # Now scheduler must have the cron job registered (state is on the scheduler,
        # which doesn't need .start() to inspect get_jobs()).
        job_ids = {j.id for j in daemon.scheduler.get_jobs()}
        assert "auto_dump_global" in job_ids

        # And the closure attribute is exposed for the catch-up create_task() call.
        assert callable(daemon._auto_dump_task_fn)
    finally:
        await daemon._shutdown_runtimes()
        if daemon.scheduler.running:
            daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_register_auto_dump_cron_exposes_task_fn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After _register_auto_dump_cron, daemon._auto_dump_task_fn is callable."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    try:
        await daemon._bootstrap_runtimes()
        daemon._register_auto_dump_cron()

        # The task function must be set and callable (for the catch-up asyncio.create_task call).
        assert hasattr(daemon, "_auto_dump_task_fn")
        assert callable(daemon._auto_dump_task_fn)

        # Verify it can be awaited (it's an async function).
        import inspect
        assert inspect.iscoroutinefunction(daemon._auto_dump_task_fn)
    finally:
        await daemon._shutdown_runtimes()
        if daemon.scheduler.running:
            daemon.scheduler.shutdown(wait=False)
