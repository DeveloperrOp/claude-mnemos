from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.core.auto_dump import auto_dump_stale
from claude_mnemos.daemon.lockfile import cleanup_pid_file, write_pid_file
from claude_mnemos.daemon.scheduler import build_empty_scheduler
from claude_mnemos.daemon.schemas import SchedulerJobInfo
from claude_mnemos.state.alerts_store import AlertsStore
from claude_mnemos.state.install_state import load_install_state
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
from claude_mnemos.state.settings import GlobalSettings, ProjectSettings, SettingsStore

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime

logger = logging.getLogger(__name__)


def _attempt_autostart_install() -> bool:
    """Best-effort tray autostart registration. Returns True on success."""
    try:
        from claude_mnemos.tray.__main__ import _cmd_install as tray_install
        rc = tray_install()
        return rc == 0
    except Exception:  # noqa: BLE001
        logger.exception("autostart-default-on attempt failed")
        return False


def maybe_install_autostart_default() -> None:
    """If user has not made a decision yet, register tray autostart and remember.

    Idempotent. Designed to be called on daemon startup from MnemosDaemon.run().
    """
    state = load_install_state()
    if state.autostart_decision is not None:
        return
    if _attempt_autostart_install():
        state.autostart_decision = "accepted"
        state.save()


@dataclass(frozen=True)
class CronTask:
    """Declarative description of a cron-scheduled async task.

    ``id``: APScheduler job-id (must remain stable — live tests poll these
    via /scheduler/jobs).
    ``schedule_kwargs``: keyword args forwarded to ``scheduler.add_job(...,
    "cron", **schedule_kwargs)`` (e.g. ``{"minute": 0}`` for hourly).
    ``fn``: zero-argument coroutine factory invoked at every cron tick.
    """

    id: str
    schedule_kwargs: dict[str, Any]
    fn: Callable[[], Awaitable[None]]


class MnemosDaemon:
    """Multi-vault daemon: hosts every project in ``project-map.json``
    (filtered by ``config.boot_filter``) inside one process. Each vault has
    a self-contained ``VaultRuntime``; the scheduler and alerts are shared.

    This class is the orchestrator only — vault-specific state (watchdog,
    job queue, tracker, lost-sessions cache, project settings) lives inside
    each ``VaultRuntime`` and is keyed by project name in ``self.runtimes``.
    """

    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.alerts = Alerts()
        # Persistent health-alerts store (singleton owned by the daemon).
        # Cron tasks and route handlers reuse this instance instead of
        # re-loading from disk on every call.
        self.alerts_store: AlertsStore = AlertsStore.load_from_disk()
        self.project_store = ProjectStore()
        self.settings_store = SettingsStore()
        self.global_settings: GlobalSettings = self.settings_store.get_global()

        self.scheduler: AsyncIOScheduler = build_empty_scheduler(timezone="UTC")
        self.runtimes: dict[str, VaultRuntime] = {}
        self._runtimes_lock = asyncio.Lock()

        self.app: FastAPI = create_app(daemon=self)
        self.started_at_monotonic: float = 0.0
        self._server: uvicorn.Server | None = None
        # Pause-flag flipped by /api/daemon/{pause,resume}. Read by callers
        # who choose to honour it (scheduler/watchdog integration is out of
        # scope for the route; the flag is the single source of truth).
        self.paused: bool = False

    # ─── Scheduler info (used by /scheduler/jobs) ─────────────────

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

    # ─── Lifecycle ────────────────────────────────────────────────

    async def run(self) -> None:
        """Run the daemon: write PID, bootstrap runtimes, start FastAPI/uvicorn,
        install signal handlers, then on shutdown unmount all runtimes and clean up.
        """
        write_pid_file(self.config.pid_file, os.getpid())
        self.started_at_monotonic = time.monotonic()
        try:
            await self._bootstrap_runtimes()

            self._register_cron_tasks(self._build_cron_tasks())

            self.scheduler.start()

            # Catch-up immediately after bootstrap — addresses any stale sessions
            # that accumulated while the daemon was down.
            asyncio.create_task(self._auto_dump_task_fn())
            asyncio.create_task(self._health_checks_task_fn())

            # Best-effort: register tray autostart on first run if user hasn't
            # explicitly opted out. Idempotent — runs at most once across
            # daemon lifetimes (decision is persisted in install-state.json).
            asyncio.create_task(asyncio.to_thread(maybe_install_autostart_default))

            await self._serve_uvicorn()
        finally:
            await self._shutdown_runtimes()
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("scheduler shutdown failed")
            cleanup_pid_file(self.config.pid_file)

    async def _serve_uvicorn(self) -> None:
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

    async def _shutdown_runtimes(self) -> None:
        async with self._runtimes_lock:
            tasks = [
                rt.unmount(timeout=5.0, force=True)
                for rt in list(self.runtimes.values())
            ]
            self.runtimes.clear()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _install_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except (NotImplementedError, ValueError):
                if sys.platform != "win32":
                    signal.signal(sig, lambda *_: self._request_shutdown())

    # ─── Boot selection + runtime bootstrap ───────────────────────

    def _select_boot_entries(self) -> list[ProjectMapEntry]:
        """Return entries to mount at startup, filtered by ``config.boot_filter``.

        - ``boot_filter is None`` or ``boot_filter.all`` → all registered projects,
          sorted alphabetically by name.
        - ``boot_filter.names`` → only those names (sorted); names absent from the
          project-map generate a ``handler_error`` alert and are silently skipped.
        """
        all_entries = sorted(
            self.project_store.list_all(), key=lambda e: e.name
        )
        flt = self.config.boot_filter
        if flt is None or flt.all:
            return all_entries
        wanted = set(flt.names or [])
        present = {e.name for e in all_entries}
        missing = wanted - present
        for m in sorted(missing):
            self.alerts.add(
                kind="handler_error",
                path="",
                message=f"--project asked for {m!r}, not in project-map; skipped",
                detected_at=datetime.now(UTC),
            )
        return [e for e in all_entries if e.name in wanted]

    async def _bootstrap_runtimes(self) -> None:
        """Mount every selected project. Failures degrade to alerts."""
        from claude_mnemos.daemon.vault_runtime import VaultMountError, VaultRuntime

        entries = self._select_boot_entries()
        for entry in entries:
            settings = self.settings_store.get_project(entry.name)
            runtime = VaultRuntime(project=entry, settings=settings)
            try:
                await runtime.mount(scheduler=self.scheduler, alerts=self.alerts)
            except VaultMountError as exc:
                logger.warning("vault %s mount failed: %s", entry.name, exc)
                continue
            self.runtimes[entry.name] = runtime

    def _build_cron_tasks(self) -> list[CronTask]:
        """Declarative list of cron tasks owned by the daemon.

        - ``auto_dump_global`` (hourly, minute=0): P0+P1 safety net that
          calls ``auto_dump_stale`` on every runtime.
        - ``health_checks_global`` (every 5 min): runs the 7 semantic
          detectors and persists results to ``alerts.json``.

        Each closure is also stashed on ``self`` so ``run()`` can fire a
        catch-up invocation after scheduler.start().
        """
        async def _auto_dump_task() -> None:
            try:
                await auto_dump_stale(self.runtimes)
            except Exception:
                logger.exception("auto_dump_task failed")

        async def _health_checks_task() -> None:
            try:
                from claude_mnemos.core.health_checks import run_all_checks

                new_alerts = await run_all_checks(
                    daemon=self, scheduler=self.scheduler, runtimes=self.runtimes
                )
                for alert in new_alerts:
                    self.alerts_store.upsert(alert)
                self.alerts_store.save()
            except Exception:
                logger.exception("health_checks_task failed")

        async def _update_check_task() -> None:
            # Runs once daily — hits GitHub Releases API on the worker thread
            # so the network/file IO doesn't block the scheduler loop.
            try:
                from claude_mnemos.core.update_check import check_for_update

                await asyncio.to_thread(check_for_update, force=True)
            except Exception:
                logger.exception("update_check_task failed")

        self._auto_dump_task_fn = _auto_dump_task
        self._health_checks_task_fn = _health_checks_task

        return [
            CronTask(
                id="auto_dump_global",
                schedule_kwargs={"minute": 0},
                fn=_auto_dump_task,
            ),
            CronTask(
                id="health_checks_global",
                schedule_kwargs={"minute": "*/5"},
                fn=_health_checks_task,
            ),
            CronTask(
                id="update_check_global",
                schedule_kwargs={"hour": 3, "minute": 17},
                fn=_update_check_task,
            ),
        ]

    def _register_cron_tasks(self, tasks: list[CronTask]) -> None:
        """Register every ``CronTask`` against ``self.scheduler``.

        Job ids must remain stable — they're observed by /scheduler/jobs and
        by the auto_dump_overdue health detector. ``replace_existing=True``
        keeps re-mounting safe in tests.
        """
        for task in tasks:
            self.scheduler.add_job(
                task.fn,
                "cron",
                **task.schedule_kwargs,
                id=task.id,
                replace_existing=True,
            )

    # ─── Dynamic vault management (Task 14) ───────────────────────

    async def mount_vault(self, entry: ProjectMapEntry) -> VaultRuntime:
        """Mount a new vault and add it to ``self.runtimes``.

        Raises ``VaultMountError`` if a runtime with the same name is already
        mounted. Holds ``_runtimes_lock`` for the entire lifecycle so no
        concurrent CRUD-mid-mount race is possible.
        """
        async with self._runtimes_lock:
            if entry.name in self.runtimes:
                from claude_mnemos.daemon.vault_runtime import VaultMountError

                raise VaultMountError(f"{entry.name!r} already mounted")
            from claude_mnemos.daemon.vault_runtime import VaultRuntime

            settings = self.settings_store.get_project(entry.name)
            runtime = VaultRuntime(project=entry, settings=settings)
            await runtime.mount(scheduler=self.scheduler, alerts=self.alerts)
            self.runtimes[entry.name] = runtime
            return runtime

    async def unmount_vault(
        self,
        name: str,
        *,
        force: bool = False,
        drain_timeout: float = 10.0,
    ) -> None:
        """Unmount and remove ``name`` from ``self.runtimes``.

        Raises ``KeyError`` if no such runtime is mounted.
        Raises ``VaultBusyError`` when ``force=False`` and jobs are in-flight.
        """
        async with self._runtimes_lock:
            runtime = self.runtimes.get(name)
            if runtime is None:
                raise KeyError(name)
            await runtime.unmount(timeout=drain_timeout, force=force)
            del self.runtimes[name]

    async def remount_vault(self, entry: ProjectMapEntry) -> VaultRuntime:
        """Unmount the existing runtime for ``entry.name`` (if any) and mount a
        fresh one with the new ``entry`` (e.g. after vault_root changes).

        If the old vault is busy (active jobs) ``VaultBusyError`` is raised and
        ``self.runtimes`` is left unchanged — the caller should convert to 409.
        """
        async with self._runtimes_lock:
            old = self.runtimes.get(entry.name)
            if old is not None:
                await old.unmount(timeout=10.0, force=False)
                del self.runtimes[entry.name]
            from claude_mnemos.daemon.vault_runtime import VaultRuntime

            settings = self.settings_store.get_project(entry.name)
            runtime = VaultRuntime(project=entry, settings=settings)
            await runtime.mount(scheduler=self.scheduler, alerts=self.alerts)
            self.runtimes[entry.name] = runtime
            return runtime

    # ─── Settings hot-reload (Task 15) ────────────────────────────

    async def reload_project_settings(
        self, name: str, new: ProjectSettings,
    ) -> None:
        """Apply *new* settings to the named runtime, if it is mounted.

        If the runtime is not mounted the call is a no-op (the settings file
        remains the source of truth for the next mount).
        """
        async with self._runtimes_lock:
            runtime = self.runtimes.get(name)
            if runtime is None:
                return  # not mounted; settings file is the source of truth
            runtime.reload_settings(new)

    async def reload_global_settings(self, new: GlobalSettings) -> None:
        """Replace the in-memory global settings."""
        async with self._runtimes_lock:
            self.global_settings = new

    def _request_shutdown(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
