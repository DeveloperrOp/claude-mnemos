"""Per-vault runtime state container for the multi-vault daemon (Plan #13b-β1).

A VaultRuntime owns everything that is vault-specific:
- watchdog observer
- our-writes tracker
- lost-sessions cache
- JobStore (sqlite at <vault>/.jobs.db)
- JobWorker (async task)
- effective ProjectSettings

Lifecycle:
    rt = VaultRuntime(project=..., settings=...)
    await rt.mount(scheduler=shared_scheduler, alerts=shared_alerts)
    ...
    await rt.unmount(timeout=10.0, force=False)

The shared scheduler hosts cron jobs registered with `<task>:<project_name>`
IDs (e.g. `daily_snapshot:foo`, `backups_cleanup:foo`) so unmount can remove
them precisely without touching other vaults' jobs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from claude_mnemos.core.lost_sessions import LostSessionsCache
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.watchdog_observer import VaultObserver
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.projects import ProjectMapEntry
from claude_mnemos.state.settings import ProjectSettings

logger = logging.getLogger(__name__)


class VaultRuntimeError(Exception):
    """Base error for VaultRuntime lifecycle issues."""


class VaultMountError(VaultRuntimeError):
    """mount() failed; partial rollback already attempted."""


class VaultBusyError(VaultRuntimeError):
    """unmount() rejected because there are active jobs and force=False."""

    def __init__(self, *, name: str, queued: int, running: int) -> None:
        super().__init__(
            f"vault {name!r} has {queued} queued and {running} running jobs"
        )
        self.name = name
        self.queued = queued
        self.running = running


class VaultRuntime:
    """Per-vault runtime: observer + tracker + lost-sessions + jobs + settings."""

    def __init__(
        self,
        *,
        project: ProjectMapEntry,
        settings: ProjectSettings,
    ) -> None:
        self.project = project
        self.settings = settings
        self.vault_root: Path = project.vault_root

        self.tracker = OurWritesTracker()
        self.lost_sessions_cache = LostSessionsCache()
        self.job_store = JobStore(self.vault_root / JOBS_DB_FILENAME)

        self.observer: VaultObserver | None = None
        # Forward-ref import to break circular dep with daemon.jobs
        from claude_mnemos.daemon.jobs.worker import JobWorker

        self.job_worker: JobWorker | None = None
        self._mounted: bool = False

        # Set on mount(); needed for reload_settings.
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self._scheduler: AsyncIOScheduler | None = None
        self._alerts: object | None = None  # claude_mnemos.daemon.alerts.Alerts

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def is_mounted(self) -> bool:
        return self._mounted
