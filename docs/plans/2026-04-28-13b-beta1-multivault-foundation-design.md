# Plan #13b-β1: Multi-vault daemon foundation — design

**Status:** DRAFT
**Date:** 2026-04-28
**Branch:** `feat/13b-beta1-multivault-foundation`
**Predecessor:** Plan #13b-α (`82bd1d0`, 2026-04-27)
**Successor:** Plan #13b-β2 (per-project route params + cross-vault metrics)

---

## 1. Background and goals

### 1.1 Where we are

After Plan #13b-α `MnemosDaemon` knows about project-map and per-project settings but is still **bound to one vault** for its lifetime: `--vault PATH` is required at startup, `app.state.vault_root` is a single `Path`, observer/scheduler/jobs all serve that one vault. SessionEnd hook (#13b-α) already includes `project_name` in `/jobs` payload but the IngestHandler ignores it (forward-compat stub).

Spec §1.1 frames the product as "every project gets its own brain" and §10.4 sketches the daemon as a **service for all of the user's vaults simultaneously** with a `watchdogs = {project_name → observer}` dict and `start_watchdog(project)` method called in a loop over `load_projects()`. β1 brings the implementation in line with that model.

### 1.2 Goal of β1

Convert `MnemosDaemon` into a multi-vault service while keeping the existing single-vault HTTP contract intact. After β1:

- One daemon process owns N vaults concurrently. Each vault has its own watchdog observer, JobStore + JobWorker, lost-sessions cache, settings — all fully isolated.
- The shared scheduler hosts cron jobs for every mounted vault, IDs suffixed by project name.
- `mnemos daemon start` (no args) mounts every project in `project-map.json`. `--project N1,N2` is a subset filter. `--vault PATH` legacy is dropped.
- `POST /projects` hot-mounts a new vault; `DELETE /projects/{name}` hot-unmounts it (with active-jobs protection); `PATCH /projects/{name}` with vault_root change does unmount+mount.
- SessionEnd hook's `project_name` finally drives ingest routing — `/jobs` POST stores jobs in the right vault's JobStore.
- Existing single-vault routes (`/jobs` GET, `/sessions`, `/lost-sessions`, `/metrics`, `/snapshots`, etc.) keep working against a "primary" vault selected automatically; β2 will rewrite them to take explicit project params.

### 1.3 Non-goals (deferred to β2)

- Per-project query/path params on existing routes (`/jobs?project=` etc.).
- Real cross-vault aggregation in `/metrics/usage/by-project`.
- Removal of `app.state.vault_root` and the "primary" concept.
- Dashboard wiring (Plan #14).

### 1.4 Spec alignment

| Spec section | β1 alignment |
|---|---|
| §1.1 vision: "every project gets its own brain" | One daemon hosts all projects; each runs in isolation. |
| §1.4 Принцип 5 ("always a UI path to fix") | Empty project-map at boot ≠ fatal — daemon stays up serving `/projects/*` so user can register their first vault via REST/CLI without restart. |
| §10.1 single-owner state | Each vault's state-files (`.jobs.db`, `.lost-sessions.json`, `.our-writes`) owned by exactly one VaultRuntime. Shared state (`alerts.json`, project-map, settings) owned by daemon. |
| §10.4 daemon code sketch | Direct implementation: `runtimes: dict[str, VaultRuntime]` mirrors spec's `watchdogs` dict but generalised over the full per-vault state set. |
| §13.2 onboarding wizard step 3 ("add project") | Wizard's CRUD calls hit running daemon → hot mount → ready to ingest within seconds, no restart. |

---

## 2. Architecture overview

### 2.1 Component map

```
MnemosDaemon (single process)
├── runtimes: dict[str, VaultRuntime]      ← multi-vault state
│     ├── "project-a" → VaultRuntime
│     │     ├── observer (watchdog.Observer thread)
│     │     ├── tracker (OurWritesTracker)
│     │     ├── lost_sessions_cache (LostSessionsCache)
│     │     ├── job_store (JobStore at <vault>/.jobs.db)
│     │     ├── job_worker (JobWorker async task)
│     │     ├── settings (ProjectSettings)
│     │     └── project (ProjectMapEntry)
│     ├── "project-b" → VaultRuntime
│     └── …
│
├── scheduler: AsyncIOScheduler            ← shared, jobs ID'd "<task>:<name>"
├── alerts: Alerts                         ← shared, alerts tagged with vault path
├── project_store: ProjectStore            ← shared, owns project-map.json
├── settings_store: SettingsStore          ← shared, owns settings/*.json + global
├── global_settings: GlobalSettings        ← cached from store
│
├── _runtimes_lock: asyncio.Lock           ← serialises mount/unmount/reload
├── _primary_runtime: VaultRuntime | None  ← cached for app.state.vault_root
│
├── app: FastAPI                           ← single uvicorn instance on :daemon_port
└── pid_file, _server (uvicorn)            ← single per daemon
```

### 2.2 What is per-vault vs. shared

| Concern | Scope | Why |
|---|---|---|
| Watchdog observer | per-vault | One observer per vault path; spec §10.4. |
| OurWritesTracker | per-vault | Tracker is consulted by the same vault's observer; cross-vault would create false negatives. |
| LostSessionsCache | per-vault | Cache contents are vault-relative file paths. |
| JobStore (`.jobs.db`) | per-vault | Existing layout (#13b-α uses `<vault>/.jobs.db`); spec §10.1 single-owner; deletion of vault → jobs vanish naturally. |
| JobWorker | per-vault | Worker is tightly coupled to one JobStore + one IngestHandler bound to one vault. Parallel ingest across vaults is a feature, not a bug. |
| IngestHandler | per-vault | Already constructed with `vault: Path`. |
| ProjectSettings | per-vault | Spec §12.8 — per-project. |
| AsyncIOScheduler | shared | One scheduler instance can host N×M cron jobs cheaply; spec §10.4 implies one. |
| Alerts | shared | UI shows one alert pane; alerts already carry `path` for vault attribution. |
| ProjectStore + SettingsStore + GlobalSettings | shared | Single global config, nothing vault-relative. |
| FastAPI app + uvicorn | shared | One HTTP listener; β2 will route to vaults via per-route params. |
| pid_file | shared | One daemon = one PID file. |

### 2.3 Cron job ID convention

Each vault registers its own cron jobs in the shared scheduler with the suffix `:<project_name>`:

- `daily_snapshot:<name>` (cron 04:00) — gated on `settings.snapshots.daily_enabled`.
- `backups_cleanup:<name>` (cron 05:00) — always, because old snapshots must rotate.
- Future (out of scope here): `auto_stale:<name>`, `trash_cleanup:<name>`, `scheduled_lint:<name>`.

The colon separator is safe because `project_name` regex is `^[a-z0-9][a-z0-9_-]{0,63}$` — colons are excluded. Unmount removes jobs by suffix match.

The current single-vault scheduler builder (`build_scheduler(vault, retention_days, snapshots_enabled)`) becomes **`build_empty_scheduler(timezone)`** — returns a bare `AsyncIOScheduler`. Vault-specific jobs are registered inside `VaultRuntime.mount()`.

### 2.4 Primary vault concept (β1-only)

Existing routes (`/jobs` GET, `/sessions`, `/lost-sessions`, `/metrics/*`, `/snapshots`, `/pages`, etc.) read `request.app.state.vault_root: Path`. β2 will change every such route to accept an explicit `?project=NAME` (or path-prefix) param. β1 must keep them working with **one** vault selected as "primary."

**Selection rule:**

1. If `GlobalSettings.primary_project` is set and that project name exists in `runtimes` → primary = that runtime.
2. Else first runtime by alphabetically-sorted `name` in `runtimes`.
3. Else (`runtimes` empty) → no primary. `app.state.vault_root` becomes `None`.

**`primary_project` setting** is a new field on `GlobalSettings`:

```python
class GlobalSettings(BaseModel):
    ...
    primary_project: str | None = None  # routes' default vault before β2
```

Defaults to `None` so existing α users get auto-pick (alphabetical first). User can pin via `mnemos settings set --global primary_project NAME` if they want.

**Empty primary semantics:** when `app.state.vault_root is None`, helpers like `_vault(request)` raise `HTTPException(503, "no_vault_registered", "Run: mnemos project add NAME --vault PATH")`. Routes that don't need a vault (`/health`, `/version`, `/projects/*`, `/settings/*`, `/alerts`) keep working. This honours spec §1.4 Принцип 5.

---

## 3. `VaultRuntime` — class spec

**File:** `claude_mnemos/daemon/vault_runtime.py` (new).

```python
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_mnemos.config import Config
from claude_mnemos.core.lost_sessions import LostSessionsCache
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.jobs.handlers import IngestHandler
from claude_mnemos.daemon.jobs.worker import JobWorker
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.tasks import backups_cleanup_task, daily_snapshot_task
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler
from claude_mnemos.daemon.watchdog_observer import VaultObserver
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.projects import ProjectMapEntry
from claude_mnemos.state.settings import ProjectSettings


class VaultRuntimeError(Exception):
    """Base error for VaultRuntime lifecycle issues."""


class VaultMountError(VaultRuntimeError):
    """mount() failed; partial rollback already attempted."""


class VaultBusyError(VaultRuntimeError):
    """unmount() rejected because there are active jobs and force=False."""

    def __init__(self, name: str, queued: int, running: int) -> None:
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
        self.job_worker: JobWorker | None = None
        self._mounted: bool = False
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
        """Start observer + jobs subsystem + register cron jobs.

        On any sub-step failure: best-effort rollback (stop what was started),
        re-raise as VaultMountError. Caller decides whether to surface as alert
        and continue without this vault, or abort.
        """
        if self._mounted:
            raise VaultMountError(f"vault {self.name!r} already mounted")

        self._scheduler = scheduler
        self._alerts = alerts
        try:
            # 1. Recover zombie running jobs left behind by previous crash.
            self.job_store.recover_zombie_running()

            # 2. Watchdog observer.
            handler = VaultChangeHandler(self.vault_root, self.tracker, alerts)
            observer = VaultObserver(self.vault_root, handler)
            observer.start()
            self.observer = observer

            # 3. Cron jobs: daily_snapshot:<name> + backups_cleanup:<name>.
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
            def cfg_factory() -> Config:
                return Config.from_env()

            def llm_factory(cfg: Config) -> LLMClient | None:
                if not cfg.api_key:
                    return None
                return LLMClient(cfg)

            handlers = {
                "ingest": IngestHandler(
                    vault=self.vault_root,
                    cfg_factory=cfg_factory,
                    llm_factory=llm_factory,
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
        """Best-effort cleanup of any partial mount state."""
        # Stop worker if started (no-op if None).
        if self.job_worker is not None:
            try:
                await self.job_worker.stop(timeout=5.0)
            except Exception:
                logging.getLogger(__name__).exception(
                    "rollback: worker stop failed"
                )
            self.job_worker = None

        # Remove cron jobs if scheduler was set.
        if self._scheduler is not None:
            for job_id in (
                f"daily_snapshot:{self.name}",
                f"backups_cleanup:{self.name}",
            ):
                try:
                    self._scheduler.remove_job(job_id)
                except Exception:
                    pass

        # Stop observer.
        if self.observer is not None:
            try:
                self.observer.stop()
            except Exception:
                logging.getLogger(__name__).exception(
                    "rollback: observer stop failed"
                )
            self.observer = None

        if self._alerts is not None:
            self._alerts.add(
                kind="handler_error",
                path=str(self.vault_root),
                message=f"mount failed: {error}",
                detected_at=datetime.now(UTC),
            )

    async def unmount(
        self,
        *,
        timeout: float = 10.0,
        force: bool = False,
    ) -> None:
        """Stop everything; close JobStore.

        If force=False and there are queued/running jobs → raise VaultBusyError.
        If force=True → cancel queued, wait running with timeout, then stop.
        """
        if not self._mounted:
            return

        counts = self.job_store.count_by_status()
        queued = int(counts.get("queued", 0))
        running = int(counts.get("running", 0))

        if (queued or running) and not force:
            raise VaultBusyError(self.name, queued=queued, running=running)

        if force and queued:
            # Cancel all queued jobs (they won't be picked up).
            self.job_store.cancel_all_queued()  # new helper, see §6.2

        # Stop worker (waits running with timeout). On timeout, JobWorker
        # is expected to cancel its own task; we trust it to leave no
        # awaitable handles.
        if self.job_worker is not None:
            try:
                await self.job_worker.stop(timeout=timeout)
            except Exception:
                logging.getLogger(__name__).exception("worker stop failed")
            self.job_worker = None

        # Remove cron jobs.
        if self._scheduler is not None:
            for job_id in (
                f"daily_snapshot:{self.name}",
                f"backups_cleanup:{self.name}",
            ):
                try:
                    self._scheduler.remove_job(job_id)
                except Exception:
                    pass

        # Stop observer.
        if self.observer is not None:
            try:
                self.observer.stop()
            except Exception:
                logging.getLogger(__name__).exception("observer stop failed")
            self.observer = None

        # Close JobStore.
        try:
            self.job_store.close()
        except Exception:
            logging.getLogger(__name__).exception("job_store close failed")

        self._mounted = False

    def reload_settings(self, new: ProjectSettings) -> None:
        """Apply new settings; reschedule cron jobs as needed.

        Caller MUST hold MnemosDaemon._runtimes_lock. Synchronous (only
        APScheduler in-memory mutations + dict assignment).
        """
        if not self._mounted or self._scheduler is None:
            self.settings = new
            return

        old = self.settings
        self.settings = new

        if old.snapshots.daily_enabled != new.snapshots.daily_enabled:
            job_id = f"daily_snapshot:{self.name}"
            existing = self._scheduler.get_job(job_id)
            if new.snapshots.daily_enabled and existing is None:
                self._scheduler.add_job(
                    daily_snapshot_task,
                    "cron",
                    hour=4,
                    minute=0,
                    args=[self.vault_root],
                    id=job_id,
                    replace_existing=True,
                )
            elif not new.snapshots.daily_enabled and existing is not None:
                self._scheduler.remove_job(job_id)

        if old.snapshots.retention_days != new.snapshots.retention_days:
            self._scheduler.modify_job(
                f"backups_cleanup:{self.name}",
                args=[self.vault_root, new.snapshots.retention_days],
            )
```

**Notes:**

- `mount()` is **idempotent at the boot loop**: caller catches `VaultMountError`, logs alert, continues with the next vault. One unmountable vault doesn't kill the daemon.
- `unmount()` is **graceful by default**, **forceful on demand**. Mid-sized active jobs (a 5-minute LLM ingest) won't be silently killed; user explicitly opts into the disruption via `?force=true` on `DELETE /projects/{name}`.
- `reload_settings()` is sync because all its work is in-memory. The async lock is held by the **caller** (settings PATCH endpoint) for the duration.

---

## 4. `MnemosDaemon` — orchestration spec

**File:** `claude_mnemos/daemon/process.py` (rewritten — most of the existing logic moves into `VaultRuntime`).

```python
class MnemosDaemon:
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

        # FastAPI app gets daemon ref; vault_root populated after primary picked.
        self.app: FastAPI = create_app(vault_root=None, daemon=self)

        self.started_at_monotonic: float = 0.0
        self._server: uvicorn.Server | None = None

    async def run(self) -> None:
        write_pid_file(self.config.pid_file, os.getpid())
        self.started_at_monotonic = time.monotonic()
        try:
            await self._bootstrap_runtimes()
            self._recompute_primary()
            self.scheduler.start()
            await self._serve_uvicorn()
        finally:
            await self._shutdown_runtimes()
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("scheduler shutdown failed")
            cleanup_pid_file(self.config.pid_file)

    # ─── Bootstrap ─────────────────────────────────────────────────

    async def _bootstrap_runtimes(self) -> None:
        """Mount every project the user asked for. Failures degrade to alerts."""
        entries = self._select_boot_entries()
        for entry in entries:
            settings = self.settings_store.get_project(entry.name)
            runtime = VaultRuntime(project=entry, settings=settings)
            try:
                await runtime.mount(scheduler=self.scheduler, alerts=self.alerts)
            except VaultMountError as exc:
                logger.warning("vault %s mount failed: %s", entry.name, exc)
                # Alert was already added by VaultRuntime._rollback_mount.
                continue
            self.runtimes[entry.name] = runtime

    def _select_boot_entries(self) -> list[ProjectMapEntry]:
        """Use config.boot_filter to decide which projects to mount.

        - None / empty filter → all registered projects.
        - {"all": True} → all.
        - {"names": [...]}  → those names; missing names alerted but skipped.
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
        for m in missing:
            self.alerts.add(
                kind="handler_error",
                path="",
                message=(
                    f"--project asked for {m!r}, not in project-map; skipped"
                ),
                detected_at=datetime.now(UTC),
            )
        return [e for e in all_entries if e.name in wanted]

    # ─── Hot mount/unmount ─────────────────────────────────────────

    async def mount_vault(self, entry: ProjectMapEntry) -> VaultRuntime:
        """Add and mount a runtime for an already-persisted project entry.

        Caller (POST /projects route) has already written the entry to
        project-map. If mount fails, caller MUST roll back project-map by
        calling project_store.remove(entry.name).
        """
        async with self._runtimes_lock:
            if entry.name in self.runtimes:
                raise VaultMountError(f"{entry.name!r} already mounted")
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
        """Stop and remove a runtime. Raises VaultBusyError if active jobs
        and force=False. KeyError if name not mounted."""
        async with self._runtimes_lock:
            runtime = self.runtimes.get(name)
            if runtime is None:
                raise KeyError(name)
            await runtime.unmount(timeout=drain_timeout, force=force)
            del self.runtimes[name]
            self._recompute_primary()

    async def remount_vault(self, entry: ProjectMapEntry) -> VaultRuntime:
        """PATCH /projects/{name} with vault_root change → unmount old + mount new."""
        async with self._runtimes_lock:
            old = self.runtimes.get(entry.name)
            if old is not None:
                # If old vault has active jobs, this is a hard error — caller
                # must drain or force first. We do NOT auto-force on remount.
                await old.unmount(timeout=10.0, force=False)
                del self.runtimes[entry.name]
            settings = self.settings_store.get_project(entry.name)
            runtime = VaultRuntime(project=entry, settings=settings)
            await runtime.mount(scheduler=self.scheduler, alerts=self.alerts)
            self.runtimes[entry.name] = runtime
            self._recompute_primary()
            return runtime

    # ─── Settings reload ───────────────────────────────────────────

    async def reload_project_settings(
        self,
        name: str,
        new: ProjectSettings,
    ) -> None:
        async with self._runtimes_lock:
            runtime = self.runtimes.get(name)
            if runtime is None:
                return  # settings-only project, no daemon-side state to reload
            runtime.reload_settings(new)

    async def reload_global_settings(self, new: GlobalSettings) -> None:
        """Re-pick primary if primary_project changed."""
        async with self._runtimes_lock:
            self.global_settings = new
            self._recompute_primary()

    # ─── Primary selection ─────────────────────────────────────────

    def _recompute_primary(self) -> None:
        """Pick primary by global_settings.primary_project; else alphabetical
        first; else None. Updates app.state.vault_root."""
        primary: VaultRuntime | None = None
        pinned = self.global_settings.primary_project
        if pinned and pinned in self.runtimes:
            primary = self.runtimes[pinned]
        elif self.runtimes:
            primary = self.runtimes[min(self.runtimes.keys())]
        self._primary_runtime = primary
        self.app.state.vault_root = primary.vault_root if primary else None
        # Daemon-aware routes can also reach runtimes via app.state.daemon.

    @property
    def primary_runtime(self) -> VaultRuntime | None:
        return self._primary_runtime

    # ─── Shutdown ──────────────────────────────────────────────────

    async def _shutdown_runtimes(self) -> None:
        """Stop every mounted runtime in parallel; force=True so jobs don't
        block daemon termination indefinitely."""
        async with self._runtimes_lock:
            tasks = [
                rt.unmount(timeout=5.0, force=True)
                for rt in list(self.runtimes.values())
            ]
            self.runtimes.clear()
            self._primary_runtime = None
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
```

**Concurrency model:**

- `self._runtimes_lock` (an `asyncio.Lock`) covers **every mutation of `self.runtimes`** and every multi-step read-modify-write done by daemon orchestration methods (`mount_vault`, `unmount_vault`, `remount_vault`, `reload_project_settings`, `reload_global_settings`, `_recompute_primary` after dict mutation).
- Single-step lookups in REST handlers (`runtime = daemon.runtimes.get(name)`) do **not** acquire the lock. Concurrent unmount mid-request is acceptable: handlers wrap downstream calls in try/except and return 503 with `vault_unavailable` if the runtime/JobStore was closed mid-flight (see §6.1).
- Read paths in routes that don't touch runtime internals (e.g. `GET /projects/` reading project_store, `GET /alerts`) don't need the lock at all.
- The lock is **always async-acquired**; never held across ingest worker boundaries or LLM calls.
- Uvicorn single-worker is the supported deployment. Multi-worker would require migrating shared state (alerts, runtimes dict) to an external store; out of scope here.

---

## 5. Bootstrap — CLI and DaemonConfig changes

### 5.1 `DaemonConfig` extended

```python
class BootFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all: bool = False
    names: list[str] = Field(default_factory=list)


class DaemonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = DEFAULT_HOST
    port: int = ...
    log_level: LogLevel = ...
    pid_file: Path = ...
    boot_filter: BootFilter | None = None  # None == "all"
    # NOTE: vault_root REMOVED.
    # NOTE: retention_days REMOVED — now per-project setting.
```

`vault_root` is no longer a daemon-level config — daemon binds to whatever's in project-map. `retention_days` per-project moved to `ProjectSettings.snapshots.retention_days` already in α.

### 5.2 `claude_mnemos.daemon.__main__` (run subcommand)

```text
python -m claude_mnemos.daemon run
    [--host HOST] [--port PORT] [--log-level LEVEL] [--pid-file PATH]
    [--all | --project NAME[,NAME...]]
```

- No `--vault` flag.
- `--all` and `--project` mutually exclusive. If both omitted → `BootFilter(all=True)` (mount everything).
- Empty project-map at boot: `runtimes` stays empty; daemon serves `/projects/*` `/settings/*` `/health` `/version` `/alerts`. Other routes return 503 via primary-vault helper (§7.3).

### 5.3 `mnemos daemon start|foreground` CLI

`_cmd_daemon_start` and `_cmd_daemon_foreground` mirror the daemon `__main__` flags:

```text
mnemos daemon start
    [--port PORT] [--retention-days N] [--log-level LEVEL] [--pid-file PATH]
    [--all | --project NAME[,NAME...]]
```

`_resolve_daemon_config(args)`:

- Reads `~/.claude-mnemos/daemon.config.json` runtime state for defaults (host, port).
- Drops the old `vault_root` resolution code path.
- Builds `BootFilter` from `args.all`/`args.project`.
- If `--vault` is found in argv → exit 2 with: `--vault is no longer supported. Register the vault with: mnemos project add NAME --vault PATH`.

`DaemonRuntimeState` (the `~/.claude-mnemos/daemon.config.json`) loses `vault_root` from its schema. To stay forward-compatible with α-written files that contain `vault_root`, switch the model from `extra="forbid"` to `extra="ignore"` so legacy files still load. Saved files no longer include the field. Migration is silent (no user-facing message).

### 5.4 Backward compat for α users

α users who ran `mnemos daemon start --vault PATH` had to first do `mnemos project add NAME --vault PATH` (the single-project bootstrap). After β1 they just do `mnemos daemon start` — the existing project-map entry gets mounted automatically. Their `daemon.config.json` is regenerated without `vault_root` on next start.

If a user still types `--vault PATH`, CLI exits with the migration hint. No silent fallback.

---

## 6. Routing — `/jobs` POST + JobStore changes

### 6.1 `/jobs` POST resolves `project_name`

```python
@router.post("/jobs", status_code=201)
async def create_job(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, detail={"error": "daemon_unavailable"})

    kind = body.get("kind")
    payload = body.get("payload", {})
    if kind != "ingest":
        raise HTTPException(400, detail={"error": "unknown_kind", "kind": kind})
    if not isinstance(payload, dict):
        raise HTTPException(400, detail={"error": "payload_must_be_object"})

    project_name = payload.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            400, detail={"error": "missing_project_name"}
        )

    runtime = daemon.runtimes.get(project_name)
    if runtime is None:
        raise HTTPException(
            400,
            detail={"error": "unknown_project", "project_name": project_name},
        )

    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        raise HTTPException(400, detail={"error": "missing_transcript_path"})
    if not Path(transcript_path).is_file():
        raise HTTPException(
            400,
            detail={"error": "transcript_not_found", "transcript_path": transcript_path},
        )

    try:
        job = runtime.job_store.create(kind=kind, payload=payload)
    except sqlite3.ProgrammingError as exc:
        # Connection closed by concurrent unmount.
        raise HTTPException(
            503,
            detail={
                "error": "vault_unavailable",
                "project_name": project_name,
                "detail": str(exc),
            },
        )
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    return job.model_dump(mode="json")
```

The `_runtimes_lock` is **not** acquired in this handler: dict membership is checked lock-free, and the rare race with concurrent unmount is handled by catching `sqlite3.ProgrammingError` (the closed-connection signal) and returning 503. For β1 + uvicorn-single-worker this is sufficient and avoids holding an async lock through synchronous SQLite work.

### 6.2 `JobStore.cancel_all_queued()`

New helper for force-unmount:

```python
def cancel_all_queued(self) -> int:
    """Mark every 'queued' job as 'cancelled'. Returns count cancelled.
    Used by VaultRuntime.unmount(force=True)."""
    with self._lock:
        cur = self._conn.execute(
            "UPDATE jobs SET status='cancelled', finished_at=? "
            "WHERE status='queued'",
            (datetime.now(UTC).isoformat(),),
        )
        self._conn.commit()
        return cur.rowcount
```

### 6.3 `/jobs` GET, `/jobs/{id}`, `/jobs/{id}` DELETE

These remain **single-vault (primary)** in β1. They use `daemon.primary_runtime.job_store`. β2 adds `?project=NAME` query parameter and aggregates across vaults. The α stub returning empty primary handles primary=None gracefully (503).

### 6.4 Other routes that touch vault_root

`activity`, `snapshots`, `pages`, `trash`, `lint`, `ontology`, `dead_letter`, `lost_sessions`, `sessions`, `metrics`, `alerts`, `vault`, `health` — all keep their existing `_vault(request)` pattern. The helper is updated to gracefully fail when primary is None (§7.3).

---

## 7. REST endpoints affected

### 7.1 `POST /projects` — hot mount

```python
@router.post("/projects", status_code=201)
async def create_project(...):
    entry = ProjectMapEntry(...)  # validated input
    # 1. Persist to project-map first.
    try:
        store.add(entry)
    except ProjectNameConflictError:
        raise HTTPException(409, ...)

    # 2. Mount via daemon.
    daemon = request.app.state.daemon
    if daemon is not None:
        try:
            await daemon.mount_vault(entry)
        except VaultMountError as exc:
            # Roll back project-map.
            try:
                store.remove(entry.name)
            except Exception:
                pass  # alert already in `daemon.alerts`
            raise HTTPException(
                500,
                detail={"error": "mount_failed", "detail": str(exc)},
            )
    return entry.model_dump(mode="json")
```

### 7.2 `DELETE /projects/{name}` — hot unmount

```python
@router.delete("/projects/{name}", status_code=204)
async def delete_project(name: str, force: bool = False, ...):
    daemon = request.app.state.daemon

    if daemon is not None and name in daemon.runtimes:
        try:
            await daemon.unmount_vault(name, force=force)
        except VaultBusyError as exc:
            raise HTTPException(
                409,
                detail={
                    "error": "vault_busy",
                    "queued": exc.queued,
                    "running": exc.running,
                    "hint": "delete with ?force=true to drain",
                },
            )

    # Remove from project-map after unmount.
    try:
        store.remove(name)
    except ProjectNotFoundError:
        raise HTTPException(404, ...)
    return Response(status_code=204)
```

### 7.3 `PATCH /projects/{name}` — possibly remount

PATCH that changes `vault_root` while the project is mounted does unmount+mount. To keep the project-map and the runtime in sync, **busy is checked before persisting** the map change:

```python
async def patch_project(name: str, body: PatchBody, request: Request):
    daemon = request.app.state.daemon
    new_vault = body.vault_root  # may be None == unchanged
    new_patterns = body.cwd_patterns

    if daemon is not None and name in daemon.runtimes and new_vault is not None:
        current = daemon.runtimes[name].vault_root
        if current != new_vault:
            # Pre-flight busy check — fail fast before touching the map.
            counts = daemon.runtimes[name].job_store.count_by_status()
            if counts.get("queued", 0) or counts.get("running", 0):
                raise HTTPException(
                    409,
                    detail={
                        "error": "vault_busy",
                        "queued": counts.get("queued", 0),
                        "running": counts.get("running", 0),
                        "hint": "drain or cancel jobs before changing vault_root",
                    },
                )

    new_entry = store.update(name, vault_root=new_vault, cwd_patterns=new_patterns)

    if daemon is not None and name in daemon.runtimes and new_vault is not None:
        if daemon.runtimes[name].vault_root != new_entry.vault_root:
            try:
                await daemon.remount_vault(new_entry)
            except VaultMountError as exc:
                # Map already updated — surface as 500 with a clear hint.
                raise HTTPException(
                    500,
                    detail={
                        "error": "remount_failed",
                        "detail": str(exc),
                        "hint": "project-map is updated; restart daemon if "
                                "auto-remount keeps failing",
                    },
                )

    return new_entry.model_dump(mode="json")
```

The pre-flight check has a small race (jobs could be enqueued between the check and `remount_vault`'s second check), but it covers the common case where the user is trying to update a quiet vault. The race window is bounded — `remount_vault`'s own busy check inside `unmount` is the authoritative gate.

### 7.4 `PATCH /settings/{name}` — settings reload

Already exists in α. Becomes:

```python
await daemon.reload_project_settings(name, new_settings)
```

(daemon's method holds the lock, looks up runtime by name, calls `runtime.reload_settings`).

`PATCH /settings/global` — for `primary_project` change, we re-run `_recompute_primary()`:

```python
await daemon.reload_global_settings(new_global)
```

### 7.5 Helper `_vault(request)` update

All routes that `_vault(request)` now branch on None:

```python
def _vault(request: Request) -> Path:
    vault = request.app.state.vault_root
    if vault is None:
        raise HTTPException(
            503,
            detail={
                "error": "no_vault_registered",
                "hint": "Register: mnemos project add NAME --vault PATH",
            },
        )
    assert isinstance(vault, Path)
    return vault
```

This single change makes ~12 existing route modules (activity, snapshots, etc.) safe under empty project-map at boot.

---

## 8. Tech debt fixes (closing α-leftovers)

### 8.1 #1 TOCTOU in `cli_project._handle_update`

Current code reads entry via direct `ProjectStore.get`, then issues PATCH. Multi-vault concurrent CLI usage makes the race wider.

**Fix:** delete the pre-read entirely. Build the PATCH body purely from CLI args (`--vault PATH` and/or `--cwd-pattern P`); the daemon's PATCH endpoint already supports None=unchanged via `ProjectStore.update`. CLI no longer reads-before-write.

If user wants to "see before state" they call `mnemos project show NAME` separately; that's a clear two-step flow with no race expectations.

### 8.2 #2 `reload_settings` thread-safety

Already documented in α but with informal "uvicorn single-worker" assumption. β1 adds an actual `asyncio.Lock` (`_runtimes_lock`) covering the mutation. Multi-worker uvicorn becomes safer (still uvicorn-single-worker recommended; the lock is a defence in depth).

### 8.3 #3 CLI/MCP daemon URL hardcoded

New module `claude_mnemos/daemon_url.py`:

```python
"""Helpers to compute the daemon HTTP base URL.

Reads ~/.claude-mnemos/global-settings.json once per call (cheap — file is
small and cached by OS). CLI/MCP processes are short-lived enough that
re-reading on each call is fine; daemon itself caches in memory.
"""

from __future__ import annotations

from claude_mnemos.daemon.config import DEFAULT_HOST
from claude_mnemos.state.settings import SettingsStore


def daemon_base_url(host: str = DEFAULT_HOST) -> str:
    settings = SettingsStore().get_global()
    return f"http://{host}:{settings.daemon_port}"
```

Replace every hardcoded `"http://127.0.0.1:5757"` in CLI and MCP code with `daemon_base_url()`.

After β1 a user can `mnemos settings set --global daemon_port 5800` and the next CLI/MCP invocation hits 5800 automatically. Daemon itself reads the port from `DaemonConfig` at boot — port change requires daemon restart (acceptable, daemon is a server).

---

## 9. Migration and backward compatibility

### 9.1 α user with one project

α: `mnemos project add foo --vault /path/foo` then `mnemos daemon start --vault /path/foo`.

β1: `mnemos daemon start`. Daemon mounts every entry in project-map (just `foo`) — same end state as before. No data migration needed.

### 9.2 α user who never ran `project add`

α: `mnemos daemon start --vault /path/foo` (unregistered vault — daemon ran with built-in defaults + alert).

β1: same command exits with `--vault no longer supported. Run: mnemos project add NAME --vault PATH`.

This is the documented hard-cut from α; β1 makes it absolute. Migration path is one CLI command.

### 9.3 α `daemon.config.json` field cleanup

Old `~/.claude-mnemos/daemon.config.json` may contain `vault_root`. β1 silently ignores the field on read. Next daemon start regenerates the file without it.

### 9.4 SessionEnd hook (#13b-α)

Hook already sends `payload["project_name"]` to `/jobs`. After β1 this is finally consumed. No hook changes needed; the endpoint contract is what tightens (missing/unknown name → 400 instead of silent ingest into hardcoded vault).

### 9.5 MCP server

MCP config `--auto-resolve` flow in α already ends up with `vault_root: Path | None`. β1 is unchanged for MCP — it still resolves cwd to one project at startup. β2 may revisit MCP for cross-project tools.

---

## 10. Testing strategy

### 10.1 Unit tests

- `tests/daemon/test_vault_runtime.py` — VaultRuntime construction, mount, unmount, force-unmount, mount-rollback on failure, reload_settings flips daily_snapshot job, reload_settings updates retention_days args.
- `tests/daemon/test_process_multivault.py` — daemon bootstrap with N runtimes, mount_vault, unmount_vault (busy → raises, force → drains), remount_vault, primary selection (pinned vs alphabetical vs None), reload_global_settings re-picks primary.
- `tests/daemon/test_scheduler_ids.py` — cron job IDs with `:<name>` suffix, no collisions across vaults, removal on unmount.

### 10.2 Integration tests (subprocess daemon)

- `tests/daemon/integration/test_multivault_lifecycle.py` — start daemon with `--all` over 2 projects, verify both have observers, both have `<vault>/.jobs.db`, both schedule cron jobs.
- `tests/daemon/integration/test_hot_mount.py` — start daemon empty, POST /projects, verify mount succeeds, POST /jobs with project_name routes correctly, ingest produces output in correct vault.
- `tests/daemon/integration/test_hot_unmount.py` — DELETE /projects/{name} with active jobs → 409; with `?force=true` → drains; queued jobs marked cancelled.
- `tests/daemon/integration/test_remount.py` — PATCH /projects/{name} with new vault_root → old observer stops, new observer starts on new vault.
- `tests/daemon/integration/test_empty_project_map.py` — start daemon with empty map, /projects/* and /health work, /jobs and /sessions return 503 with hint.

### 10.3 CLI tests

- `tests/cli/test_daemon_start_flags.py` — `--all`, `--project N`, `--project A,B,C`, both flags conflict, missing names alerted.
- `tests/cli/test_daemon_start_no_vault_flag.py` — old `--vault` exits 2 with hint.
- `tests/cli/test_cli_project_no_pre_read.py` — `mnemos project update` no longer reads-before-PATCHing (TOCTOU fix).

### 10.4 Hook test

- `tests/hooks/test_session_end_jobs_routing.py` — daemon up with two projects, hook fires from project A's cwd, /jobs gets project_name=A, ingest lands in vault A only.

### 10.5 Migration test

- `tests/state/test_daemon_config_legacy_vault_root.py` — daemon.config.json with stale `vault_root` field is silently ignored; next save omits it.

### 10.6 Coverage targets

Same as α: 100% on new modules (`vault_runtime.py`, `daemon_url.py`), all changed paths in process.py, all REST routes touched. ~80–120 new tests expected.

### 10.7 Pre-existing flaky reminder

`tests/daemon/test_app_metrics.py::test_usage_timeline` is a known flaky from α, not part of β1. Skip-marked or quarantined as needed during the run.

---

## 11. File-level change summary

**New files:**

- `claude_mnemos/daemon/vault_runtime.py` — `VaultRuntime`, `VaultMountError`, `VaultBusyError`.
- `claude_mnemos/daemon_url.py` — `daemon_base_url()` helper.

**Modified files (high-impact):**

- `claude_mnemos/daemon/process.py` — major rewrite (most logic moves to VaultRuntime; daemon becomes orchestrator).
- `claude_mnemos/daemon/config.py` — `DaemonConfig.vault_root` removed, `BootFilter` added.
- `claude_mnemos/daemon/__main__.py` — `--all`/`--project` flags, no `--vault`.
- `claude_mnemos/daemon/scheduler.py` — `build_scheduler` becomes `build_empty_scheduler`; per-vault jobs registered by VaultRuntime.
- `claude_mnemos/daemon/app.py` — `create_app` accepts `vault_root: Path | None`.
- `claude_mnemos/daemon/routes/projects.py` — POST/PATCH/DELETE wired to mount/remount/unmount.
- `claude_mnemos/daemon/routes/settings.py` — PATCH project + global routed through daemon's reload methods.
- `claude_mnemos/daemon/routes/jobs.py` — POST resolves project_name; GET/DELETE use primary runtime.
- All other route files — `_vault(request)` helper updated to handle None.
- `claude_mnemos/cli.py` — daemon start/foreground rewritten; `_cmd_daemon_*` use BootFilter; `--vault` exits 2.
- `claude_mnemos/state/jobs.py` — `cancel_all_queued()` helper added.
- `claude_mnemos/state/settings.py` — `GlobalSettings.primary_project: str | None = None`.
- `claude_mnemos/daemon/runtime_state.py` — `DaemonRuntimeState.vault_root` removed; `model_config` switched to `extra="ignore"` to load α-written files silently.
- `claude_mnemos/daemon/jobs/worker.py` — `JobWorker.stop()` cancels `self._task` on timeout (so dangling tasks don't hold scheduler/store references).
- All MCP/CLI code paths that hit daemon URL — switch to `daemon_base_url()`.

**Removed:**

- `MNEMOS_VAULT_ROOT` legacy traces (already gone in α; verify zero matches).
- `daemon.config.json` `vault_root` write path.

---

## 12. Risks and rollback

### 12.1 Top risks

| Risk | Mitigation |
|---|---|
| Watchdog observer threads leak across mount/unmount cycles. | unmount stops `observer.stop()` + tests assert no thread leak via `threading.enumerate()` snapshots. |
| Hot remount under load loses queued jobs. | Documented behaviour: remount of busy vault → 409; user must drain or `?force=true` first. |
| Force-unmount kills running ingest mid-LLM-call. | JobWorker.stop has graceful timeout; if it times out, the worker task is explicitly cancelled (`task.cancel()`). The underlying `asyncio.to_thread` thread may keep running but its result is discarded; layer-3 atomic writes guarantee no partial vault state. Quarantine catches partial ingest output on next start. |
| Two CLI invocations of `mnemos project add` simultaneously → race in mount_vault. | Daemon lock serialises. ProjectStore.add is also locked. Worst case: second add gets ProjectNameConflictError 409. |
| primary_project race when user pins a project then deletes it. | unmount_vault calls `_recompute_primary` after dict mutation; result drops the pinned name back to alphabetical-first or None. |
| Empty project-map at boot leaves `app.state.vault_root = None` and breaks routes that didn't expect None. | Centralised `_vault(request)` helper raises 503 with consistent error shape; tests cover every route under empty-runtimes. |
| Settings PATCH for primary_project takes effect mid-request. | reload_global_settings holds lock; route reads result on next request. |

### 12.2 Rollback

β1 ships as one branch + one merge to main. If integration breaks in production:

1. `git revert -m 1 <merge-sha>` on main → restore α state.
2. Existing α users' `~/.claude-mnemos/` layout is unchanged (project-map.json + settings/* are α artifacts; β1 doesn't migrate them in-place).
3. The only forward-incompatible change on disk is `daemon.config.json` losing `vault_root` field — α reads it but tolerates absent field (Pydantic optional? — verify in α tests).

### 12.3 Pre-existing flaky test

`tests/daemon/test_app_metrics.py::test_usage_timeline` (timezone bucket bug) is unrelated. β1 does not touch metrics route or core/metrics.py — flaky stays as-is. Optionally quarantined with `@pytest.mark.flaky`.

---

## 13. Open questions resolved by this design

| Question | Decision | Rationale |
|---|---|---|
| Single big plan or decompose? | Decomposed into β1 + β2. β1 does foundation, β2 does route surface. | User-confirmed; matches α-sized scope. |
| Per-vault or shared JobStore? | Per-vault `<vault>/.jobs.db`. | Matches existing α layout, spec §10.1, vault-deletion symmetry, parallel-ingest. |
| Hot reload of project-map? | Yes — POST/DELETE/PATCH on /projects hot-mount. | Spec §13.2 onboarding wizard depends on it; spec §10.4 implies dynamic. |
| `mnemos daemon start` default? | `--all` (no args = mount everything). | Daemon is a service for all of user's projects (spec §10.4 sketch: `for project in load_projects(): start_watchdog(project)`). |
| `--vault PATH` legacy support? | Dropped, exit 2 with hint. | α already hard-cut env var; β1 finishes the migration. |
| What is the "primary" vault in β1 routes? | `GlobalSettings.primary_project` if set, else alphabetical first, else None → 503. | β1-only concept; β2 removes it. |
| Routes' migration to per-project? | Deferred to β2. | Keeps β1 reviewable; β2 is its own focused refactor. |
| Force-unmount semantics? | `?force=true` → cancel queued, wait running with timeout. | Layer-3 atomic writes guarantee no partial state on cancellation. |

---

## 14. Out of scope (β2 will handle)

- All routes that take vault_root: add `?project=NAME` (or path-prefix) param. Drop `app.state.vault_root` and `_vault(request)`.
- `/metrics/usage/by-project`: real cross-vault aggregation iterating manifest of every mounted vault.
- `/lost-sessions`: cross-vault scan with project attribution per result.
- `/jobs` GET cross-vault aggregation.
- Dashboard wiring (Plan #14).

---

## 15. Acceptance criteria

β1 is done when:

1. ✅ `MnemosDaemon` no longer takes `vault_root` in DaemonConfig.
2. ✅ `mnemos daemon start` (no args) mounts every project from project-map.
3. ✅ `mnemos daemon start --project A,B` mounts only A and B.
4. ✅ POST /projects + POST /jobs with payload.project_name=newproj works without daemon restart.
5. ✅ DELETE /projects/{name} with active jobs returns 409; with `?force=true` drains them.
6. ✅ PATCH /projects/{name} with new vault_root remounts.
7. ✅ Empty project-map at boot: daemon stays up, /projects works, /jobs returns 503.
8. ✅ Two SessionEnd hooks from two different vaults route to two different `<vault>/.jobs.db`.
9. ✅ Cron jobs visible via /scheduler/jobs are suffixed with `:<name>`.
10. ✅ `cli_project._handle_update` no longer reads-before-PATCH.
11. ✅ CLI/MCP read `daemon_port` via `daemon_base_url()` (no hardcoded 5757).
12. ✅ `_runtimes_lock: asyncio.Lock` covers every dict mutation.
13. ✅ Test suite green: ~1100+ fast pytest, ~80–120 new tests, ruff + mypy --strict clean.
14. ✅ No regression in α-merged functionality (project-map CRUD, settings CRUD, hook routing, MCP --auto-resolve).
