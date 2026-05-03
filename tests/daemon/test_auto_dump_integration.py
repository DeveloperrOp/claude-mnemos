"""Integration test: daemon registers auto_dump cron after bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.mark.asyncio
async def test_register_cron_tasks_adds_auto_dump_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling _register_cron_tasks(_build_cron_tasks()) must add the
    ``auto_dump_global`` job (and the ``health_checks_global`` job) to
    the scheduler. This validates that the production helper (called
    from run()) does its job.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    try:
        await daemon._bootstrap_runtimes()
        daemon._register_cron_tasks(daemon._build_cron_tasks())

        job_ids = {j.id for j in daemon.scheduler.get_jobs()}
        assert "auto_dump_global" in job_ids
        assert "health_checks_global" in job_ids

        assert callable(daemon._auto_dump_task_fn)
    finally:
        await daemon._shutdown_runtimes()
        if daemon.scheduler.running:
            daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_build_cron_tasks_exposes_task_fns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After _build_cron_tasks(), daemon._auto_dump_task_fn /
    _health_checks_task_fn are coroutine functions used by the catch-up
    create_task() calls in run().
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    try:
        await daemon._bootstrap_runtimes()
        daemon._build_cron_tasks()

        import inspect
        assert inspect.iscoroutinefunction(daemon._auto_dump_task_fn)
        assert inspect.iscoroutinefunction(daemon._health_checks_task_fn)
    finally:
        await daemon._shutdown_runtimes()
        if daemon.scheduler.running:
            daemon.scheduler.shutdown(wait=False)
