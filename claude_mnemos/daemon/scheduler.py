from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_empty_scheduler(*, timezone: str = "UTC") -> AsyncIOScheduler:
    """Return an empty AsyncIOScheduler. Per-vault cron jobs are added by
    VaultRuntime.mount() so that we can register/remove them with a stable
    `<task>:<project_name>` ID convention as vaults are mounted/unmounted.
    """
    return AsyncIOScheduler(timezone=timezone)
