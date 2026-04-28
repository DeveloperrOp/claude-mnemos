from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.scheduler import build_empty_scheduler
from claude_mnemos.daemon.schemas import SchedulerJobInfo
from claude_mnemos.state.projects import ProjectStore
from claude_mnemos.state.settings import GlobalSettings, SettingsStore

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

    def _request_shutdown(self) -> None:  # pragma: no cover - implemented in Task 16
        if self._server is not None:
            self._server.should_exit = True
