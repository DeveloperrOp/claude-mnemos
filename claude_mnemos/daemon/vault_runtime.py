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

import contextlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from claude_mnemos.config import Config
from claude_mnemos.core.lost_sessions import LostSessionsCache
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.jobs.handlers import IngestHandler
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.tasks import backups_cleanup_task, daily_snapshot_task
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler
from claude_mnemos.daemon.watchdog_observer import VaultObserver
from claude_mnemos.ingest.llm import LLMClient, MissingApiKeyError, make_llm_client
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.projects import ProjectMapEntry
from claude_mnemos.state.settings import ProjectSettings

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
        self._scheduler: AsyncIOScheduler | None = None
        self._alerts: Alerts | None = None

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def is_mounted(self) -> bool:
        return self._mounted

    async def mount(
        self,
        *,
        scheduler: AsyncIOScheduler,
        alerts: Alerts,
    ) -> None:
        """Start observer, register cron jobs, start JobWorker.

        On any sub-step failure: best-effort rollback + raise VaultMountError.
        """
        if self._mounted:
            raise VaultMountError(f"vault {self.name!r} already mounted")

        self._scheduler = scheduler
        self._alerts = alerts
        try:
            # 1. Recover zombies left by previous crash.
            self.job_store.recover_zombie_running()

            # 2. Watchdog observer.
            handler = VaultChangeHandler(self.vault_root, self.tracker, alerts)
            observer = VaultObserver(self.vault_root, handler)
            observer.start()
            self.observer = observer

            # 3. Cron jobs in shared scheduler.
            if self.settings.snapshots.daily_enabled:
                scheduler.add_job(
                    daily_snapshot_task,
                    "cron",
                    hour=4,
                    minute=0,
                    args=[self.vault_root],
                    id=f"daily_snapshot:{self.name}",
                    replace_existing=True,
                )
                # Catch-up: if the user's machine was off at 04:00 today,
                # the daily snapshot didn't run. `daily_snapshot_task` is
                # idempotent (no-op if today's snapshot already exists),
                # so it's safe to fire-and-forget on mount. Runs in a
                # thread because tar.gz creation is blocking.
                import asyncio as _asyncio
                _asyncio.create_task(
                    _asyncio.to_thread(daily_snapshot_task, self.vault_root),
                )
            scheduler.add_job(
                backups_cleanup_task,
                "cron",
                hour=5,
                minute=0,
                args=[self.vault_root, self.settings.snapshots.retention_days],
                id=f"backups_cleanup:{self.name}",
                replace_existing=True,
            )

            # 4. Jobs subsystem.
            from claude_mnemos.daemon.jobs.worker import JobWorker

            def cfg_factory() -> Config:
                return Config.from_env()

            def llm_factory(cfg: Config) -> LLMClient | None:
                """Resolve LLMClient via factory. Return None only if both
                provider paths are unavailable (API key missing AND CLI
                unavailable) — IngestHandler then falls back to --no-llm
                behaviour (manual extraction skipped)."""
                try:
                    return make_llm_client(cfg)
                except MissingApiKeyError:
                    return None

            from claude_mnemos.daemon.jobs.handlers import JobHandler
            from claude_mnemos.state.jobs import JobKind

            handlers: dict[JobKind, JobHandler] = {
                "ingest": IngestHandler(
                    vault=self.vault_root,
                    cfg_factory=cfg_factory,
                    llm_factory=llm_factory,
                    job_store=self.job_store,
                )
            }
            worker = JobWorker(
                store=self.job_store,
                handlers=handlers,
                scheduler=scheduler,
            )
            await worker.start()
            self.job_worker = worker

            self._mounted = True
        except Exception as exc:
            await self._rollback_mount(error=str(exc))
            raise VaultMountError(
                f"failed to mount vault {self.name!r}: {exc}"
            ) from exc

    async def _rollback_mount(self, *, error: str) -> None:
        if self.job_worker is not None:
            try:
                await self.job_worker.stop(timeout=5.0)
            except Exception:
                logger.exception("rollback: worker stop failed")
            self.job_worker = None

        if self._scheduler is not None:
            for jid in (
                f"daily_snapshot:{self.name}",
                f"backups_cleanup:{self.name}",
            ):
                with contextlib.suppress(Exception):
                    self._scheduler.remove_job(jid)

        if self.observer is not None:
            try:
                self.observer.stop()
            except Exception:
                logger.exception("rollback: observer stop failed")
            self.observer = None

        if self._alerts is not None:
            try:
                self._alerts.add(
                    kind="handler_error",
                    path=str(self.vault_root),
                    message=f"vault {self.name!r} mount failed: {error}",
                    detected_at=datetime.now(UTC),
                )
            except Exception:
                logger.exception("rollback: alerts.add failed")

    async def unmount(self, *, timeout: float = 10.0, force: bool = False) -> None:
        """Stop everything; close JobStore.

        force=False: VaultBusyError if any queued/running jobs.
        force=True: cancel queued, wait running with timeout, then stop.
        """
        if not self._mounted:
            return

        counts = self.job_store.count_by_status()
        queued = int(counts.get("queued", 0))
        running = int(counts.get("running", 0))

        if (queued or running) and not force:
            raise VaultBusyError(name=self.name, queued=queued, running=running)

        if force and queued:
            self.job_store.cancel_all_queued()

        if self.job_worker is not None:
            try:
                await self.job_worker.stop(timeout=timeout)
            except Exception:
                logger.exception("worker stop failed")
            self.job_worker = None

        if self._scheduler is not None:
            for jid in (
                f"daily_snapshot:{self.name}",
                f"backups_cleanup:{self.name}",
            ):
                with contextlib.suppress(Exception):
                    self._scheduler.remove_job(jid)

        if self.observer is not None:
            try:
                self.observer.stop()
            except Exception:
                logger.exception("observer stop failed")
            self.observer = None

        try:
            self.job_store.close()
        except Exception:
            logger.exception("job_store close failed")

        self._mounted = False

    def reload_settings(self, new: ProjectSettings) -> None:
        """Apply new settings; reschedule cron jobs as needed.

        Caller MUST hold MnemosDaemon._runtimes_lock when applicable. Synchronous
        (only APScheduler in-memory mutations + dict assignment).
        """
        if not self._mounted or self._scheduler is None:
            self.settings = new
            return

        old = self.settings
        self.settings = new

        if old.snapshots.daily_enabled != new.snapshots.daily_enabled:
            jid = f"daily_snapshot:{self.name}"
            existing = self._scheduler.get_job(jid)
            if new.snapshots.daily_enabled and existing is None:
                self._scheduler.add_job(
                    daily_snapshot_task,
                    "cron",
                    hour=4,
                    minute=0,
                    args=[self.vault_root],
                    id=jid,
                    replace_existing=True,
                )
            elif not new.snapshots.daily_enabled and existing is not None:
                self._scheduler.remove_job(jid)

        if old.snapshots.retention_days != new.snapshots.retention_days:
            self._scheduler.modify_job(
                f"backups_cleanup:{self.name}",
                args=[self.vault_root, new.snapshots.retention_days],
            )
