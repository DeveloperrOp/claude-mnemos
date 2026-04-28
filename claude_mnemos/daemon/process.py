from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.scheduler import build_empty_scheduler
from claude_mnemos.daemon.schemas import SchedulerJobInfo
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
from claude_mnemos.state.settings import GlobalSettings, ProjectSettings, SettingsStore

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime

logger = logging.getLogger(__name__)


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
        self.project_store = ProjectStore()
        self.settings_store = SettingsStore()
        self.global_settings: GlobalSettings = self.settings_store.get_global()

        self.scheduler: AsyncIOScheduler = build_empty_scheduler(timezone="UTC")
        self.runtimes: dict[str, VaultRuntime] = {}
        self._runtimes_lock = asyncio.Lock()
        self._primary_runtime: VaultRuntime | None = None

        self.app: FastAPI = create_app(vault_root=None, daemon=self)
        self.started_at_monotonic: float = 0.0
        self._server: uvicorn.Server | None = None

    # ─── Scheduler info (used by /scheduler/jobs) ──────────────────

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

    # ─── Primary selection ─────────────────────────────────────────

    @property
    def primary_runtime(self) -> VaultRuntime | None:
        """Currently-selected primary runtime, or None if no runtimes mounted.

        Recomputed by ``_recompute_primary`` whenever ``self.runtimes`` changes
        (mount/unmount in Task 14) or whenever the pinned primary changes in
        global settings.
        """
        return self._primary_runtime

    def _recompute_primary(self) -> None:
        """Pick the primary VaultRuntime and propagate it to ``app.state``.

        Selection rule:
          1. ``global_settings.primary_project`` if it names a mounted runtime.
          2. Otherwise alphabetically-first runtime by project name.
          3. None when no runtimes are mounted.

        Synchronous; only mutates in-memory state.
        """
        primary: VaultRuntime | None = None
        pinned = self.global_settings.primary_project
        if pinned and pinned in self.runtimes:
            primary = self.runtimes[pinned]
        elif self.runtimes:
            primary = self.runtimes[min(self.runtimes.keys())]
        self._primary_runtime = primary
        self.app.state.vault_root = primary.vault_root if primary else None

    # ─── Lifecycle (added in later tasks) ──────────────────────────

    async def run(self) -> None:  # pragma: no cover - implemented in Task 16
        """Run the daemon: bootstrap runtimes, start FastAPI server, install
        signal handlers, await shutdown.

        Implemented in Task 16 alongside ``_bootstrap_runtimes`` (Task 13) and
        ``mount_vault``/``unmount_vault`` (Task 14).
        """
        raise NotImplementedError("MnemosDaemon.run() lands in Task 16")

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
            self._recompute_primary()
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
            self._recompute_primary()

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
            self._recompute_primary()
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
        """Replace the in-memory global settings and recompute the primary runtime."""
        async with self._runtimes_lock:
            self.global_settings = new
            self._recompute_primary()

    def _request_shutdown(self) -> None:  # pragma: no cover - implemented in Task 16
        if self._server is not None:
            self._server.should_exit = True
