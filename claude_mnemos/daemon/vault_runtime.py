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
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from apscheduler.triggers.cron import CronTrigger

from claude_mnemos.config import Config
from claude_mnemos.core.lost_sessions import LostSessionsCache
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.jobs.handlers import IngestHandler
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.tasks import (
    backups_cleanup_task,
    daily_snapshot_task,
    lint_check_task,
)
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler
from claude_mnemos.daemon.watchdog_observer import VaultObserver
from claude_mnemos.ingest.llm import LLMClient, MissingApiKeyError, make_llm_client
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.projects import ProjectMapEntry
from claude_mnemos.state.settings import ProjectSettings, SettingsStore

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from claude_mnemos.core.snapshots import RestoreResult
    from claude_mnemos.daemon.jobs.worker import JobWorker

logger = logging.getLogger(__name__)


def _snapshot_cron_kwargs(schedule: str) -> dict[str, int | str] | None:
    """Map a snapshot `schedule` preset to APScheduler cron keyword args.

    Returns None for "off" (no automatic snapshot job). All presets fire at
    04:00 local time; the snapshot itself is always named ``daily-<date>``
    (idempotent per day) — the preset only changes the cadence.
    """
    if schedule == "daily":
        return {"hour": 4, "minute": 0}
    if schedule == "weekly":
        return {"day_of_week": "sun", "hour": 4, "minute": 0}
    if schedule == "monthly":
        return {"day": 1, "hour": 4, "minute": 0}
    return None


def _lint_cron_trigger(schedule: str | None) -> CronTrigger | None:
    """Parse a lint `schedule` crontab string into a CronTrigger.

    Unlike snapshots (which use a fixed preset), lint stores a raw 5-field
    crontab expression ("m h dom mon dow"). Returns None for a blank schedule
    (no automatic lint) or an unparseable expression (logged, lint not
    scheduled rather than crashing the mount).
    """
    if not schedule or not schedule.strip():
        return None
    try:
        return CronTrigger.from_crontab(schedule.strip(), timezone="UTC")
    except (ValueError, TypeError):
        logger.warning(
            "invalid lint cron schedule %r — lint will not run automatically",
            schedule,
        )
        return None


class VaultRuntimeError(Exception):
    """Base error for VaultRuntime lifecycle issues."""


class VaultMountError(VaultRuntimeError):
    """mount() failed; partial rollback already attempted."""


class VaultBusyError(VaultRuntimeError):
    """unmount() rejected because there are active jobs and force=False."""

    def __init__(self, *, name: str, queued: int, running: int) -> None:
        super().__init__(f"vault {name!r} has {queued} queued and {running} running jobs")
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
        settings_store: SettingsStore | None = None,
    ) -> None:
        self.project = project
        self.settings = settings
        self.vault_root: Path = project.vault_root
        # Used by _make_cfg() to read GlobalSettings.default_max_input_tokens
        # (the UI value) into ingest Config. Defaults to the standard store
        # (~/.claude-mnemos/global-settings.json); injectable for tests.
        self._settings_store = settings_store or SettingsStore()

        self.tracker = OurWritesTracker()
        self.lost_sessions_cache = LostSessionsCache()
        self.job_store = JobStore(self.vault_root / JOBS_DB_FILENAME)

        self.observer: VaultObserver | None = None
        # Forward-ref import to break circular dep with daemon.jobs

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
            cron_kwargs = _snapshot_cron_kwargs(self.settings.snapshots.schedule)
            if cron_kwargs is not None:
                scheduler.add_job(
                    daily_snapshot_task,
                    "cron",
                    args=[self.vault_root],
                    id=f"daily_snapshot:{self.name}",
                    replace_existing=True,
                    **cron_kwargs,
                )
                # Catch-up: if the user's machine was off at 04:00 today,
                # the daily snapshot didn't run. `daily_snapshot_task` is
                # idempotent (no-op if today's snapshot already exists),
                # so it's safe to fire-and-forget on mount. Runs in a
                # thread because tar.gz creation is blocking.
                #
                # Only for the "daily" preset: weekly/monthly snapshots are
                # named `daily-<date>` too, so firing catch-up on every mount
                # would create off-cadence snapshots and defeat the chosen
                # frequency. Missing one weekly/monthly run is acceptable.
                if self.settings.snapshots.schedule == "daily":
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

            # Lint auto-run: only when the project configured a schedule.
            lint_trigger = _lint_cron_trigger(self.settings.lint.schedule)
            if lint_trigger is not None:
                scheduler.add_job(
                    lint_check_task,
                    lint_trigger,
                    args=[self.vault_root, self.settings.lint.enabled_rules],
                    id=f"lint_check:{self.name}",
                    replace_existing=True,
                )

            # 4. Jobs subsystem.
            worker = self._build_job_worker()
            await worker.start()
            self.job_worker = worker

            self._mounted = True
        except Exception as exc:
            await self._rollback_mount(error=str(exc))
            raise VaultMountError(f"failed to mount vault {self.name!r}: {exc}") from exc

    def _make_cfg(self) -> Config:
        """Build the ingest Config for this vault.

        Env stays the highest-priority developer escape hatch:
        ``Config.from_env()`` already reads ``MNEMOS_MAX_INPUT_TOKENS`` when
        set. When it's *unset*, ``max_input_tokens`` would silently fall back
        to ``DEFAULT_MAX_INPUT_TOKENS`` and ignore the UI value — that was the
        placebo. So in the no-env case we layer
        ``GlobalSettings.default_max_input_tokens`` (the value the user edits
        in the dashboard) on top via ``with_overrides``.
        """
        cfg = Config.from_env()
        # Falsy/whitespace-aware (not ``is None``): an empty or blank env var is
        # treated as unset here too, matching ``Config.from_env()``, so the UI
        # override still applies instead of being silently skipped.
        if not (os.environ.get("MNEMOS_MAX_INPUT_TOKENS") or "").strip():
            global_settings = self._settings_store.get_global()
            cfg = cfg.with_overrides(
                max_input_tokens=global_settings.default_max_input_tokens
            )
        return cfg

    def _build_job_worker(self) -> JobWorker:
        """Construct (not start) the JobWorker for this vault.

        Shared by mount() and restore_with_quiesce() so the post-restore worker
        can never drift from the mounted-worker config. Requires self.job_store
        and self._scheduler to be set.
        """
        from claude_mnemos.daemon.jobs.handlers import JobHandler
        from claude_mnemos.daemon.jobs.worker import JobWorker
        from claude_mnemos.state.jobs import JobKind

        def cfg_factory() -> Config:
            return self._make_cfg()

        def llm_factory(cfg: Config) -> LLMClient | None:
            """Resolve LLMClient via factory. Return None only if both provider
            paths are unavailable (API key missing AND CLI unavailable) —
            IngestHandler then falls back to --no-llm (manual extraction
            skipped)."""
            try:
                return make_llm_client(cfg)
            except MissingApiKeyError:
                return None

        handlers: dict[JobKind, JobHandler] = {
            "ingest": IngestHandler(
                vault=self.vault_root,
                cfg_factory=cfg_factory,
                llm_factory=llm_factory,
                job_store=self.job_store,
                tracker=self.tracker,
            )
        }
        assert self._scheduler is not None
        return JobWorker(
            store=self.job_store,
            handlers=handlers,
            scheduler=self._scheduler,
        )

    async def restore_with_quiesce(self, snapshot: Path) -> RestoreResult:
        """Restore the vault from ``snapshot``, releasing the sqlite jobs.db
        handle around the swap so the vault-directory rename succeeds on Windows.

        The blocker for the Windows rename is the open ``.jobs.db`` handle, not
        the watchdog observer (the existing code already runs the swap with the
        observer alive and only fails on Windows). So we stop the worker, close
        the JobStore, stop the observer (it would otherwise keep watching the
        renamed-away directory and go blind), run the UNCHANGED atomic swap,
        then reopen the store, start a fresh observer on the restored dir and
        restart the worker. If a corrupted final-rename left the vault directory
        missing we do NOT reopen/restart — recreating an empty .jobs.db over the
        loss would mask it.
        """
        import asyncio

        from claude_mnemos.core.snapshots import restore_from_snapshot

        # 1. Drain + stop the worker, release the jobs.db handle (the blocker).
        if self.job_worker is not None:
            try:
                await self.job_worker.stop(timeout=10.0)
            except Exception:
                logger.exception("restore: worker stop failed")
            self.job_worker = None
        self.job_store.close()

        # 1b. Stop the observer: its ReadDirectoryChangesW handle survives the
        # rename but follows the OLD directory, so after the swap it would
        # silently watch a deleted path and never see vault events again.
        if self.observer is not None:
            try:
                self.observer.stop()
            except Exception:
                logger.exception("restore: observer stop failed")
            self.observer = None

        # 2. Run the unchanged atomic swap off the event loop, paused.
        result = await asyncio.to_thread(
            restore_from_snapshot, self.vault_root, snapshot, tracker=self.tracker
        )

        # 3. Reopen the store, restart observer + worker — never recreate a
        #    vault that a corrupted final-rename left missing.
        if self.vault_root.exists():
            self.job_store = JobStore(self.vault_root / JOBS_DB_FILENAME)
            self.job_store.recover_zombie_running()
            if self._alerts is not None:
                handler = VaultChangeHandler(self.vault_root, self.tracker, self._alerts)
                observer = VaultObserver(self.vault_root, handler)
                observer.start()
                self.observer = observer
            worker = self._build_job_worker()
            await worker.start()
            self.job_worker = worker
        elif self._alerts is not None:
            with contextlib.suppress(Exception):
                self._alerts.add(
                    kind="handler_error",
                    path=str(self.vault_root),
                    message=(f"restore left vault {self.name!r} missing; manual recovery needed"),
                    detected_at=datetime.now(UTC),
                )
        return result

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
                f"lint_check:{self.name}",
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
                f"lint_check:{self.name}",
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

        if old.snapshots.schedule != new.snapshots.schedule:
            jid = f"daily_snapshot:{self.name}"
            new_kwargs = _snapshot_cron_kwargs(new.snapshots.schedule)
            existing = self._scheduler.get_job(jid)
            if new_kwargs is not None:
                if existing is not None:
                    # Cadence changed on a live job — reschedule_job is the
                    # canonical way to swap the trigger (add_job replace
                    # leaves the old trigger in place on a running scheduler).
                    self._scheduler.reschedule_job(jid, trigger="cron", **new_kwargs)
                else:
                    # off → on: register a fresh job.
                    self._scheduler.add_job(
                        daily_snapshot_task,
                        "cron",
                        args=[self.vault_root],
                        id=jid,
                        replace_existing=True,
                        **new_kwargs,
                    )
            elif existing is not None:
                self._scheduler.remove_job(jid)

        if old.snapshots.retention_days != new.snapshots.retention_days:
            self._scheduler.modify_job(
                f"backups_cleanup:{self.name}",
                args=[self.vault_root, new.snapshots.retention_days],
            )

        # Lint schedule or enabled_rules changed: rebuild the lint job. We
        # remove + re-add (rather than reschedule_job) because the args
        # (enabled_rules) may also have changed, not just the trigger.
        if (
            old.lint.schedule != new.lint.schedule
            or old.lint.enabled_rules != new.lint.enabled_rules
        ):
            jid = f"lint_check:{self.name}"
            trigger = _lint_cron_trigger(new.lint.schedule)
            if self._scheduler.get_job(jid) is not None:
                self._scheduler.remove_job(jid)
            if trigger is not None:
                self._scheduler.add_job(
                    lint_check_task,
                    trigger,
                    args=[self.vault_root, new.lint.enabled_rules],
                    id=jid,
                    replace_existing=True,
                )
