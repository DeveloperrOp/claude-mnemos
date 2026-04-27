from __future__ import annotations

from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_mnemos.daemon.tasks import backups_cleanup_task, daily_snapshot_task


def build_scheduler(
    vault: Path,
    retention_days: int,
    *,
    timezone: str = "UTC",
    snapshots_enabled: bool = True,
) -> AsyncIOScheduler:
    """Construct (but do not start) AsyncIOScheduler with cron jobs.

    - daily_snapshot at 04:00 (only if ``snapshots_enabled``)
    - backups_cleanup at 05:00 (always — old backups must be cleaned even
      if no new snapshots are being created)
    """
    sch = AsyncIOScheduler(timezone=timezone)
    if snapshots_enabled:
        sch.add_job(
            daily_snapshot_task,
            "cron",
            hour=4,
            minute=0,
            args=[vault],
            id="daily_snapshot",
            replace_existing=True,
        )
    sch.add_job(
        backups_cleanup_task,
        "cron",
        hour=5,
        minute=0,
        args=[vault, retention_days],
        id="backups_cleanup",
        replace_existing=True,
    )
    return sch
