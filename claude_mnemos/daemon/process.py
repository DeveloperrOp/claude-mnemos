from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from claude_mnemos.core.lost_sessions import LostSessionsCache
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.jobs.worker import JobWorker
from claude_mnemos.daemon.lockfile import cleanup_pid_file, write_pid_file
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.scheduler import build_empty_scheduler
from claude_mnemos.daemon.schemas import SchedulerJobInfo
from claude_mnemos.daemon.tasks import daily_snapshot_task
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler
from claude_mnemos.daemon.watchdog_observer import VaultObserver
from claude_mnemos.mapping.resolver import ProjectResolver
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
from claude_mnemos.state.settings import GlobalSettings, ProjectSettings, SettingsStore

logger = logging.getLogger(__name__)


class MnemosDaemon:
    """Long-running daemon: FastAPI server + APScheduler housekeeping +
    real-time vault watchdog (Plan #9) + jobs queue worker (Plan #11).
    """

    def __init__(
        self,
        config: DaemonConfig,
        vault_root: Path,  # TODO(Task 12): fold into multi-vault VaultRuntime
    ) -> None:
        self.config = config
        # TODO(Task 12): vault_root moves to VaultRuntime; DaemonConfig no longer
        # carries a single vault.  Until then keep it as an explicit arg so that
        # DaemonConfig no longer needs the field but process.py stays importable.
        self.vault_root: Path = vault_root
        self.tracker = OurWritesTracker()
        self.alerts = Alerts()
        self.project_store = ProjectStore()
        self.settings_store = SettingsStore()
        self.global_settings: GlobalSettings = self.settings_store.get_global()
        self.project_entry: ProjectMapEntry | None = None
        try:
            self.project_entry = ProjectResolver(self.project_store).resolve_by_vault(
                vault_root
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("project resolver failed at startup")
            self.alerts.add(
                kind="handler_error",
                path=str(vault_root),
                message=f"project resolver failed: {exc}",
                detected_at=datetime.now(UTC),
            )
        if self.project_entry is None:
            self.project_settings: ProjectSettings = ProjectSettings()
            self.alerts.add(
                kind="handler_error",
                path=str(vault_root),
                message=(
                    f"daemon vault {vault_root} not registered in "
                    "project-map; using built-in defaults"
                ),
                detected_at=datetime.now(UTC),
            )
        else:
            self.project_settings = self.settings_store.get_project(
                self.project_entry.name
            )
        self.scheduler: AsyncIOScheduler = build_empty_scheduler()
        self.job_store: JobStore = JobStore(vault_root / JOBS_DB_FILENAME)
        self.job_worker: JobWorker | None = None
        # Plan #13a: TTL-cached lost-sessions list owned by the daemon, so the
        # GET /lost-sessions endpoint doesn't re-hash every transcript on each
        # request. Invalidated by /lost-sessions/scan and /lost-sessions/*/ignore.
        self.lost_sessions_cache: LostSessionsCache = LostSessionsCache()
        self.app: FastAPI = create_app(vault_root, daemon=self)
        self.started_at_monotonic: float = 0.0
        self._server: uvicorn.Server | None = None
        self.observer: VaultObserver | None = None

    def scheduler_jobs_info(self) -> list[SchedulerJobInfo]:
        # `next_run_time` attribute exists only after scheduler.start() resolves
        # the trigger; before that the job is "pending" and access raises.
        return [
            SchedulerJobInfo(
                id=j.id,
                next_run_time=getattr(j, "next_run_time", None),
                trigger=str(j.trigger),
            )
            for j in self.scheduler.get_jobs()
        ]

    async def run(self) -> None:
        write_pid_file(self.config.pid_file, os.getpid())
        self.started_at_monotonic = time.monotonic()
        try:
            self._start_observer()
            await self._start_jobs_subsystem()
            self.scheduler.start()
            uconfig = uvicorn.Config(
                app=self.app,
                host=self.config.host,
                port=self.config.port,
                log_level=self.config.log_level,
                lifespan="on",
            )
            self._server = uvicorn.Server(uconfig)
            self._install_signal_handlers()
            await self._server.serve()
        finally:
            await self._stop_jobs_subsystem()
            self._stop_observer()
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("scheduler shutdown failed")
            cleanup_pid_file(self.config.pid_file)

    def _start_observer(self) -> None:
        """Start the watchdog observer. On failure, log an alert and continue —
        the daemon is still useful as REST + scheduler even without watchdog.
        """
        try:
            handler = VaultChangeHandler(
                self.vault_root, self.tracker, self.alerts
            )
            observer = VaultObserver(self.vault_root, handler)
            observer.start()
            self.observer = observer
        except Exception as exc:
            logger.exception("failed to start watchdog observer")
            self.alerts.add(
                kind="handler_error",
                path=str(self.vault_root),
                message=f"failed to start watchdog observer: {exc}",
                detected_at=datetime.now(UTC),
            )
            self.observer = None

    def _stop_observer(self) -> None:
        if self.observer is None:
            return
        try:
            self.observer.stop()
        except Exception:
            logger.exception("observer stop failed")
        finally:
            self.observer = None

    async def _start_jobs_subsystem(self) -> None:
        """Recover zombies, then spawn JobWorker. Failure surfaces as alert —
        the daemon keeps running without the worker.
        """
        try:
            from claude_mnemos.config import Config
            from claude_mnemos.daemon.jobs.handlers import IngestHandler, JobHandler
            from claude_mnemos.ingest.llm import LLMClient
            from claude_mnemos.state.jobs import JobKind

            self.job_store.recover_zombie_running()

            def cfg_factory() -> Config:
                return Config.from_env()

            def llm_factory(cfg: Config) -> LLMClient | None:
                if not cfg.api_key:
                    return None
                return LLMClient(cfg)

            handlers: dict[JobKind, JobHandler] = {
                "ingest": IngestHandler(
                    vault=self.vault_root,
                    cfg_factory=cfg_factory,
                    llm_factory=llm_factory,
                )
            }
            worker = JobWorker(
                store=self.job_store,
                handlers=handlers,
                scheduler=self.scheduler,
            )
            await worker.start()
            self.job_worker = worker
        except Exception as exc:
            logger.exception("failed to start jobs subsystem")
            self.alerts.add(
                kind="handler_error",
                path=str(self.vault_root),
                message=f"jobs subsystem failed to start: {exc}",
                detected_at=datetime.now(UTC),
            )
            self.job_worker = None

    async def _stop_jobs_subsystem(self) -> None:
        if self.job_worker is not None:
            try:
                await self.job_worker.stop(timeout=10.0)
            except Exception:
                logger.exception("job worker stop failed")
            finally:
                self.job_worker = None
        try:
            self.job_store.close()
        except Exception:
            logger.exception("job store close failed")

    def reload_settings(self, new_settings: ProjectSettings) -> None:
        """Apply new settings; reschedule snapshot jobs as needed.

        Called by PATCH /settings/{project} when the patched project's
        vault matches our own. Lint-schedule reload is deferred to
        Plan #11+ when the scheduled lint runner exists.

        Thread-safety: this method assumes the daemon runs uvicorn
        with a single worker (default), so concurrent PATCH requests
        are serialised on the event loop. Multi-worker deployment is
        out of scope for Plan #13b-α; #13b-β multi-vault refactor
        will revisit synchronisation when needed.
        """
        old = self.project_settings
        self.project_settings = new_settings

        if old.snapshots.daily_enabled != new_settings.snapshots.daily_enabled:
            existing = self.scheduler.get_job("daily_snapshot")
            if new_settings.snapshots.daily_enabled and existing is None:
                self.scheduler.add_job(
                    daily_snapshot_task,
                    "cron",
                    hour=4,
                    minute=0,
                    args=[self.vault_root],
                    id="daily_snapshot",
                    replace_existing=True,
                )
            elif not new_settings.snapshots.daily_enabled and existing is not None:
                self.scheduler.remove_job("daily_snapshot")

        if old.snapshots.retention_days != new_settings.snapshots.retention_days:
            # APScheduler's add_job(replace_existing=True) is a no-op for jobs
            # in the pending list (scheduler not started yet) — modify_job
            # works for both pending and live jobs.
            self.scheduler.modify_job(
                "backups_cleanup",
                args=[
                    self.vault_root,
                    new_settings.snapshots.retention_days,
                ],
            )

    def _install_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except (NotImplementedError, ValueError):
                # Windows ProactorEventLoop / non-main thread: fallback
                if sys.platform != "win32":
                    signal.signal(sig, lambda *_: self._request_shutdown())

    def _request_shutdown(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
