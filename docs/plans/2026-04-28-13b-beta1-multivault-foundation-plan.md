# Multi-vault daemon foundation Implementation Plan (Plan #13b-β1)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Convert `MnemosDaemon` into a multi-vault service that hosts every registered project simultaneously — per-vault watchdog observers, JobStore + JobWorker + lost-sessions cache + settings, all isolated via a new `VaultRuntime` class. Hot mount/unmount via `/projects` CRUD. `IngestHandler` routing by `project_name`. CLI `mnemos daemon start` defaults to mounting every project. Existing single-vault routes keep working against an auto-selected "primary" vault (β2 will rewrite them).

**Architecture:** New module `claude_mnemos/daemon/vault_runtime.py` owns everything per-vault (`VaultRuntime` + `VaultMountError` + `VaultBusyError`). `MnemosDaemon` becomes an orchestrator with `runtimes: dict[str, VaultRuntime]` + shared `AsyncIOScheduler` (cron jobs ID'd `<task>:<name>`) + shared `Alerts` + `_runtimes_lock: asyncio.Lock`. `mnemos daemon start [--all | --project N1,N2]` (default `--all`) bootstraps. POST/DELETE/PATCH on `/projects` calls daemon.mount_vault/unmount_vault/remount_vault under the lock. `/jobs` POST routes by `payload["project_name"]` to the right vault's JobStore. New `daemon_url.py` helper closes the hardcoded-URL tech debt. `DaemonConfig` drops `vault_root`; `DaemonRuntimeState` switches to `extra="ignore"` to silently absorb α-written files.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, APScheduler, sqlite, pytest, pytest-asyncio. No new third-party deps.

**Design doc:** `docs/plans/2026-04-28-13b-beta1-multivault-foundation-design.md` — read before starting each task.

---

## Files map

**Create:**
- `claude_mnemos/daemon/vault_runtime.py` — `VaultRuntime`, `VaultMountError`, `VaultBusyError`
- `claude_mnemos/daemon_url.py` — `daemon_base_url()` helper
- `tests/daemon/test_vault_runtime.py`
- `tests/daemon/test_process_multivault.py`
- `tests/daemon/test_scheduler_ids.py`
- `tests/daemon/test_routes_jobs_routing.py`
- `tests/daemon/test_routes_projects_hotmount.py`
- `tests/daemon/test_routes_settings_reload.py`
- `tests/test_daemon_url.py`
- `tests/test_cli_daemon_multivault.py`
- `tests/state/test_jobs_cancel_all_queued.py`
- `tests/daemon/test_jobs_worker_cancel_on_timeout.py`
- `tests/daemon/integration/__init__.py`
- `tests/daemon/integration/test_multivault_lifecycle.py`
- `tests/daemon/integration/test_hot_mount_unmount.py`
- `tests/daemon/integration/test_empty_project_map.py`
- `tests/daemon/integration/test_hook_routing.py`
- `tests/daemon/test_runtime_state_legacy.py`

**Modify:**
- `claude_mnemos/state/settings.py` — add `GlobalSettings.primary_project`
- `claude_mnemos/state/jobs.py` — add `JobStore.cancel_all_queued()`
- `claude_mnemos/daemon/jobs/worker.py` — `JobWorker.stop()` cancels task on timeout
- `claude_mnemos/daemon/scheduler.py` — replace `build_scheduler()` with `build_empty_scheduler()`
- `claude_mnemos/daemon/config.py` — add `BootFilter`, drop `vault_root`/`retention_days` from `DaemonConfig`
- `claude_mnemos/daemon/runtime_state.py` — `DaemonRuntimeState`: drop `vault_root`, `extra="ignore"`
- `claude_mnemos/daemon/process.py` — major rewrite: multi-vault orchestrator
- `claude_mnemos/daemon/app.py` — `create_app(vault_root: Path | None = None, daemon)`
- `claude_mnemos/daemon/__main__.py` — `--all`/`--project` flags, no `--vault`
- `claude_mnemos/daemon/routes/projects.py` — hot mount/unmount/remount
- `claude_mnemos/daemon/routes/settings.py` — daemon-aware reload
- `claude_mnemos/daemon/routes/jobs.py` — POST routes by `project_name`
- All other route modules with `_vault(request)` — handle None primary
- `claude_mnemos/cli.py` — daemon subgroup uses `BootFilter`; `--vault` hard error
- `claude_mnemos/cli_project.py` — `_handle_update` no pre-read (TOCTOU fix)
- All CLI/MCP code that hits daemon URL — use `daemon_base_url()`
- `tests/conftest.py` — extend `register_project` (no breaking change expected)
- Existing `tests/daemon/test_*` that asserts old single-vault `MnemosDaemon` shape — adapt

**Delete:**
- (none; all changes are in-place)

---

## Task 1: Add `GlobalSettings.primary_project` field

**Files:**
- Modify: `claude_mnemos/state/settings.py:112-120`
- Modify: `tests/state/test_settings.py` (add cases)

- [ ] **Step 1: Write the failing tests**

```python
# tests/state/test_settings.py — append
def test_global_settings_primary_project_default_none(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from claude_mnemos.state.settings import SettingsStore
    g = SettingsStore().get_global()
    assert g.primary_project is None


def test_global_settings_primary_project_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from claude_mnemos.state.settings import GlobalSettings, SettingsStore
    store = SettingsStore()
    store.set_global(GlobalSettings(primary_project="claude-mnemos"))
    g = store.get_global()
    assert g.primary_project == "claude-mnemos"


def test_global_settings_primary_project_pattern():
    from claude_mnemos.state.settings import GlobalSettings
    # Empty allowed (None == unset). Names must follow the project_name
    # regex; pydantic does NOT validate by content here — caller is
    # responsible for matching against project-map. So just round-trip.
    g = GlobalSettings(primary_project="a-b-c")
    assert g.primary_project == "a-b-c"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/state/test_settings.py -k primary_project -v
```

Expected: FAIL — `GlobalSettings` has no `primary_project` field.

- [ ] **Step 3: Add the field**

```python
# claude_mnemos/state/settings.py — class GlobalSettings
class GlobalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    locale: Literal["uk", "ru", "en"] = "uk"
    daemon_port: int = Field(default=5757, ge=1, le=65535)
    default_model: str = "claude-sonnet-4-6"
    default_language_hint: Literal["auto", "uk", "ru", "en"] = "auto"
    default_max_input_tokens: int = Field(default=150_000, ge=1024)
    default_retention_days: int = Field(default=180, ge=1)
    primary_project: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/state/test_settings.py -k primary_project -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/state/settings.py tests/state/test_settings.py
git commit -m "feat(state): GlobalSettings.primary_project for β1 primary-vault selection"
```

---

## Task 2: New `daemon_url` helper module

**Files:**
- Create: `claude_mnemos/daemon_url.py`
- Create: `tests/test_daemon_url.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_daemon_url.py
from __future__ import annotations
from pathlib import Path

import pytest


def _set_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_daemon_base_url_default(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url() == "http://127.0.0.1:5757"


def test_daemon_base_url_reads_from_settings(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.state.settings import GlobalSettings, SettingsStore
    SettingsStore().set_global(GlobalSettings(daemon_port=5800))
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url() == "http://127.0.0.1:5800"


def test_daemon_base_url_custom_host(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url(host="0.0.0.0") == "http://0.0.0.0:5757"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_daemon_url.py -v
```

Expected: FAIL — `claude_mnemos.daemon_url` does not exist.

- [ ] **Step 3: Create the module**

```python
# claude_mnemos/daemon_url.py
"""Compute the daemon HTTP base URL from GlobalSettings.

CLI/MCP processes are short-lived; SettingsStore reads the JSON file once
per call (cheap — file is small and OS-cached). Daemon itself caches in memory.
"""

from __future__ import annotations

from claude_mnemos.daemon.config import DEFAULT_HOST
from claude_mnemos.state.settings import SettingsStore


def daemon_base_url(host: str = DEFAULT_HOST) -> str:
    settings = SettingsStore().get_global()
    return f"http://{host}:{settings.daemon_port}"
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_daemon_url.py -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon_url.py tests/test_daemon_url.py
git commit -m "feat(util): daemon_base_url helper reads GlobalSettings.daemon_port"
```

---

## Task 3: `JobStore.cancel_all_queued()` helper

**Files:**
- Modify: `claude_mnemos/state/jobs.py` (add method near `cancel_queued` at line 384)
- Create: `tests/state/test_jobs_cancel_all_queued.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/state/test_jobs_cancel_all_queued.py
from __future__ import annotations
from pathlib import Path

from claude_mnemos.state.jobs import JobStore


def _open(path: Path) -> JobStore:
    return JobStore(path / ".jobs.db")


def test_cancel_all_queued_zero_when_empty(tmp_path: Path):
    s = _open(tmp_path)
    try:
        assert s.cancel_all_queued() == 0
    finally:
        s.close()


def test_cancel_all_queued_marks_only_queued(tmp_path: Path):
    s = _open(tmp_path)
    try:
        s.create(kind="ingest", payload={"transcript_path": "a"})
        s.create(kind="ingest", payload={"transcript_path": "b"})
        s.create(kind="ingest", payload={"transcript_path": "c"})
        # Mark one as running so it's not affected.
        rows = s._conn.execute("SELECT id FROM jobs ORDER BY created_at").fetchall()
        s._conn.execute(
            "UPDATE jobs SET status='running' WHERE id=?", (rows[0]["id"],)
        )
        s._conn.commit()

        n = s.cancel_all_queued()
        assert n == 2

        statuses = {
            r["id"]: r["status"]
            for r in s._conn.execute("SELECT id, status FROM jobs").fetchall()
        }
        assert statuses[rows[0]["id"]] == "running"
        assert statuses[rows[1]["id"]] == "cancelled"
        assert statuses[rows[2]["id"]] == "cancelled"
    finally:
        s.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/state/test_jobs_cancel_all_queued.py -v
```

Expected: FAIL — `cancel_all_queued` does not exist.

- [ ] **Step 3: Add the method**

Find `cancel_queued(self, job_id: str)` around line 384 of `claude_mnemos/state/jobs.py` and add the new method right above or below it:

```python
def cancel_all_queued(self) -> int:
    """Mark every 'queued' job as 'cancelled'. Returns count cancelled.
    Used by VaultRuntime.unmount(force=True) to drain pending work."""
    from datetime import UTC, datetime  # local import to avoid header changes
    with self._lock:
        cur = self._conn.execute(
            "UPDATE jobs SET status='cancelled', finished_at=? "
            "WHERE status='queued'",
            (datetime.now(UTC).isoformat(),),
        )
        self._conn.commit()
        return cur.rowcount
```

If `from datetime import UTC, datetime` is already at module top, drop the local import.

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/state/test_jobs_cancel_all_queued.py -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/state/jobs.py tests/state/test_jobs_cancel_all_queued.py
git commit -m "feat(state): JobStore.cancel_all_queued for force-unmount drain"
```

---

## Task 4: `JobWorker.stop()` cancels task on timeout

**Files:**
- Modify: `claude_mnemos/daemon/jobs/worker.py:47-54`
- Create: `tests/daemon/test_jobs_worker_cancel_on_timeout.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/daemon/test_jobs_worker_cancel_on_timeout.py
from __future__ import annotations
import asyncio

import pytest

from claude_mnemos.daemon.jobs.handlers import JobHandler
from claude_mnemos.daemon.jobs.worker import JobWorker
from claude_mnemos.state.jobs import Job, JobStore


class _SlowHandler:
    """Sleeps forever — emulates a wedged ingest."""

    async def run(self, job: Job) -> None:  # pragma: no cover — never returns
        await asyncio.sleep(60.0)


@pytest.mark.asyncio
async def test_stop_cancels_task_on_timeout(tmp_path):
    store = JobStore(tmp_path / ".jobs.db")
    try:
        store.create(kind="ingest", payload={"transcript_path": "x"})
        worker = JobWorker(
            store=store,
            handlers={"ingest": _SlowHandler()},
            scheduler=None,
            poll_interval_s=0.05,
        )
        await worker.start()
        # Let the worker pick up the job and enter the slow handler.
        await asyncio.sleep(0.3)
        await worker.stop(timeout=0.2)
        assert worker._task is not None
        assert worker._task.cancelled() or worker._task.done()
    finally:
        store.close()
```

`pytest-asyncio` is already in dev deps; verify with `grep pytest-asyncio pyproject.toml` if uncertain.

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/daemon/test_jobs_worker_cancel_on_timeout.py -v
```

Expected: FAIL or hang — current `stop()` only logs warning on TimeoutError without cancelling.

- [ ] **Step 3: Update `JobWorker.stop()`**

`claude_mnemos/daemon/jobs/worker.py`:

```python
async def stop(self, *, timeout: float = 10.0) -> None:
    self._stop.set()
    self._wakeup.set()  # break out of any wait_for
    if self._task is not None:
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except TimeoutError:
            # Task is wedged inside a handler — cancel it so we don't
            # leak the asyncio task across daemon shutdown / unmount.
            # Underlying threads (asyncio.to_thread) may finish later,
            # but their results are discarded.
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            logger.warning("JobWorker stop timed out, task cancelled")
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/daemon/test_jobs_worker_cancel_on_timeout.py -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/jobs/worker.py tests/daemon/test_jobs_worker_cancel_on_timeout.py
git commit -m "fix(jobs): JobWorker.stop cancels wedged task on timeout"
```

---

## Task 5: Replace `build_scheduler` with `build_empty_scheduler`

**Files:**
- Modify: `claude_mnemos/daemon/scheduler.py` (full rewrite of file)
- Create: `tests/daemon/test_scheduler_ids.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/daemon/test_scheduler_ids.py
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_mnemos.daemon.scheduler import build_empty_scheduler


def test_build_empty_scheduler_returns_scheduler():
    sch = build_empty_scheduler()
    assert isinstance(sch, AsyncIOScheduler)
    assert sch.get_jobs() == []


def test_build_empty_scheduler_timezone():
    sch = build_empty_scheduler(timezone="Europe/Kyiv")
    assert str(sch.timezone) == "Europe/Kyiv"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/daemon/test_scheduler_ids.py -v
```

Expected: FAIL — `build_empty_scheduler` does not exist.

- [ ] **Step 3: Rewrite `scheduler.py`**

```python
# claude_mnemos/daemon/scheduler.py
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_empty_scheduler(*, timezone: str = "UTC") -> AsyncIOScheduler:
    """Return an empty AsyncIOScheduler. Per-vault cron jobs are added by
    VaultRuntime.mount() so that we can register/remove them with a stable
    `<task>:<project_name>` ID convention as vaults are mounted/unmounted.
    """
    return AsyncIOScheduler(timezone=timezone)
```

The old `build_scheduler(vault, retention_days, snapshots_enabled)` is removed entirely. Callers in `MnemosDaemon` will be updated in Task 12.

- [ ] **Step 4: Run tests**

```
pytest tests/daemon/test_scheduler_ids.py -v
```

The old `tests/daemon/test_scheduler.py` (if present) likely references `build_scheduler` and will fail. Open it and either delete the file (the function is gone) or update its tests to use `build_empty_scheduler` + manual `add_job` for any retained behaviour. Verify decisions:

```
pytest tests/daemon/ -k scheduler -v
```

Should be green.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/scheduler.py tests/daemon/test_scheduler_ids.py tests/daemon/test_scheduler.py
git commit -m "refactor(scheduler): build_empty_scheduler — per-vault jobs added at mount time"
```

(Drop `tests/daemon/test_scheduler.py` from the staged set if it didn't exist.)

---

## Task 6: `VaultRuntime` skeleton + custom errors

**Files:**
- Create: `claude_mnemos/daemon/vault_runtime.py`
- Create: `tests/daemon/test_vault_runtime.py`

- [ ] **Step 1: Write failing tests for skeleton**

```python
# tests/daemon/test_vault_runtime.py
from __future__ import annotations
from pathlib import Path

import pytest

from claude_mnemos.daemon.vault_runtime import (
    VaultBusyError,
    VaultMountError,
    VaultRuntime,
)
from claude_mnemos.state.projects import ProjectMapEntry
from claude_mnemos.state.settings import ProjectSettings


def _entry(tmp_path: Path, name: str = "demo") -> ProjectMapEntry:
    vault = tmp_path / name
    vault.mkdir()
    return ProjectMapEntry(name=name, vault_root=vault, cwd_patterns=[])


def test_construction_does_not_mount(tmp_path: Path):
    rt = VaultRuntime(project=_entry(tmp_path), settings=ProjectSettings())
    assert rt.is_mounted is False
    assert rt.observer is None
    assert rt.job_worker is None
    assert rt.name == "demo"
    assert rt.vault_root == tmp_path / "demo"
    rt.job_store.close()


def test_busy_error_carries_counts():
    err = VaultBusyError(name="demo", queued=2, running=1)
    assert err.queued == 2
    assert err.running == 1
    assert err.name == "demo"
    assert "2 queued" in str(err)
    assert "1 running" in str(err)


def test_mount_error_inherits_runtime_error():
    err = VaultMountError("boom")
    assert isinstance(err, Exception)
```

- [ ] **Step 2: Run tests**

```
pytest tests/daemon/test_vault_runtime.py -v
```

Expected: FAIL — module/class do not exist.

- [ ] **Step 3: Create the skeleton**

```python
# claude_mnemos/daemon/vault_runtime.py
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

        self.job_worker: JobWorker | None = None  # type: ignore[no-any-unimported]
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
```

- [ ] **Step 4: Run tests**

```
pytest tests/daemon/test_vault_runtime.py -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/vault_runtime.py tests/daemon/test_vault_runtime.py
git commit -m "feat(daemon): VaultRuntime skeleton + VaultMountError/VaultBusyError"
```

---

## Task 7: `VaultRuntime.mount()` + rollback on failure

**Files:**
- Modify: `claude_mnemos/daemon/vault_runtime.py`
- Modify: `tests/daemon/test_vault_runtime.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/daemon/test_vault_runtime.py`:

```python
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_mnemos.daemon.alerts import Alerts


@pytest.fixture
def scheduler():
    sch = AsyncIOScheduler(timezone="UTC")
    yield sch
    try:
        sch.shutdown(wait=False)
    except Exception:
        pass


@pytest.fixture
def alerts():
    return Alerts()


@pytest.mark.asyncio
async def test_mount_starts_observer_and_registers_cron_jobs(
    tmp_path: Path, scheduler, alerts
):
    rt = VaultRuntime(
        project=_entry(tmp_path, "alpha"),
        settings=ProjectSettings(),  # snapshots.daily_enabled defaults True
    )
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        assert rt.is_mounted is True
        assert rt.observer is not None
        assert rt.job_worker is not None

        ids = {j.id for j in scheduler.get_jobs()}
        assert "daily_snapshot:alpha" in ids
        assert "backups_cleanup:alpha" in ids
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_mount_skips_daily_snapshot_when_disabled(
    tmp_path: Path, scheduler, alerts
):
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "noscan"),
        settings=ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False)),
    )
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        ids = {j.id for j in scheduler.get_jobs()}
        assert "daily_snapshot:noscan" not in ids
        assert "backups_cleanup:noscan" in ids
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_mount_twice_raises(tmp_path: Path, scheduler, alerts):
    rt = VaultRuntime(project=_entry(tmp_path, "x"), settings=ProjectSettings())
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        with pytest.raises(VaultMountError, match="already mounted"):
            await rt.mount(scheduler=scheduler, alerts=alerts)
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_mount_rollback_on_observer_failure(
    tmp_path: Path, scheduler, alerts, monkeypatch
):
    """If observer.start() raises, no scheduler jobs nor JobWorker leak."""

    class _Boom:
        def start(self):
            raise RuntimeError("disk full")

        def stop(self):  # not called, but defensive
            pass

    def _bad_observer(_root, _handler):
        return _Boom()

    monkeypatch.setattr(
        "claude_mnemos.daemon.vault_runtime.VaultObserver", _bad_observer
    )

    rt = VaultRuntime(project=_entry(tmp_path, "rb"), settings=ProjectSettings())
    with pytest.raises(VaultMountError, match="disk full"):
        await rt.mount(scheduler=scheduler, alerts=alerts)
    assert rt.is_mounted is False
    assert rt.observer is None
    assert rt.job_worker is None
    ids = {j.id for j in scheduler.get_jobs()}
    assert "daily_snapshot:rb" not in ids
    assert "backups_cleanup:rb" not in ids
    # Alert should be recorded.
    rt.job_store.close()
    snap = alerts.list()
    assert any("rb" in str(a.message) and "mount failed" in str(a.message) for a in snap)
```

- [ ] **Step 2: Run tests**

```
pytest tests/daemon/test_vault_runtime.py -v
```

Expected: FAIL — `mount` not implemented.

- [ ] **Step 3: Implement `mount()` + `_rollback_mount()`**

Add to `claude_mnemos/daemon/vault_runtime.py`:

```python
import asyncio
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_mnemos.config import Config
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.jobs.handlers import IngestHandler
from claude_mnemos.daemon.tasks import backups_cleanup_task, daily_snapshot_task
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler
from claude_mnemos.ingest.llm import LLMClient

# Within class VaultRuntime:

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
            try:
                self._scheduler.remove_job(jid)
            except Exception:
                pass

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
                message=f"mount failed: {error}",
                detected_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception("rollback: alerts.add failed")
```

(Place these methods inside the existing `class VaultRuntime`. The top-of-file imports may already be set; consolidate as needed.)

- [ ] **Step 4: Run tests**

```
pytest tests/daemon/test_vault_runtime.py -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/vault_runtime.py tests/daemon/test_vault_runtime.py
git commit -m "feat(daemon): VaultRuntime.mount + rollback on partial failure"
```

---

## Task 8: `VaultRuntime.unmount()` busy + force semantics

**Files:**
- Modify: `claude_mnemos/daemon/vault_runtime.py`
- Modify: `tests/daemon/test_vault_runtime.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/daemon/test_vault_runtime.py`:

```python
@pytest.mark.asyncio
async def test_unmount_clean_path(tmp_path, scheduler, alerts):
    rt = VaultRuntime(project=_entry(tmp_path, "u1"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    await rt.unmount(timeout=2.0, force=False)
    assert rt.is_mounted is False
    assert rt.observer is None
    assert rt.job_worker is None
    ids = {j.id for j in scheduler.get_jobs()}
    assert "daily_snapshot:u1" not in ids
    assert "backups_cleanup:u1" not in ids


@pytest.mark.asyncio
async def test_unmount_busy_raises_when_queued(tmp_path, scheduler, alerts):
    rt = VaultRuntime(project=_entry(tmp_path, "u2"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        rt.job_store.create(kind="ingest", payload={"transcript_path": "x"})
        with pytest.raises(VaultBusyError) as exc_info:
            await rt.unmount(timeout=2.0, force=False)
        assert exc_info.value.queued >= 1
        assert rt.is_mounted is True  # still mounted
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_unmount_force_drains_queued(tmp_path, scheduler, alerts):
    rt = VaultRuntime(project=_entry(tmp_path, "u3"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    rt.job_store.create(kind="ingest", payload={"transcript_path": "x"})
    rt.job_store.create(kind="ingest", payload={"transcript_path": "y"})
    await rt.unmount(timeout=2.0, force=True)
    assert rt.is_mounted is False
    # Underlying file is closed; can't query rt.job_store. Re-open to verify.
    from claude_mnemos.state.jobs import JobStore
    fresh = JobStore(rt.vault_root / ".jobs.db")
    try:
        statuses = [r["status"] for r in fresh._conn.execute("SELECT status FROM jobs").fetchall()]
        assert all(s in ("cancelled", "succeeded", "failed") for s in statuses)
    finally:
        fresh.close()


@pytest.mark.asyncio
async def test_unmount_idempotent_when_not_mounted(tmp_path, scheduler, alerts):
    rt = VaultRuntime(project=_entry(tmp_path, "u4"), settings=ProjectSettings())
    # No mount() call. unmount should be a silent no-op.
    await rt.unmount(timeout=1.0, force=False)
    assert rt.is_mounted is False
```

- [ ] **Step 2: Run tests**

```
pytest tests/daemon/test_vault_runtime.py -v
```

Expected: FAIL — `unmount` not implemented.

- [ ] **Step 3: Implement `unmount()`**

Add inside `VaultRuntime`:

```python
async def unmount(
    self,
    *,
    timeout: float = 10.0,
    force: bool = False,
) -> None:
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
            try:
                self._scheduler.remove_job(jid)
            except Exception:
                pass

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
```

- [ ] **Step 4: Run tests**

```
pytest tests/daemon/test_vault_runtime.py -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/vault_runtime.py tests/daemon/test_vault_runtime.py
git commit -m "feat(daemon): VaultRuntime.unmount with busy/force semantics"
```

---

## Task 9: `VaultRuntime.reload_settings()`

**Files:**
- Modify: `claude_mnemos/daemon/vault_runtime.py`
- Modify: `tests/daemon/test_vault_runtime.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
@pytest.mark.asyncio
async def test_reload_settings_disable_daily_snapshot(tmp_path, scheduler, alerts):
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(project=_entry(tmp_path, "rs1"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        assert scheduler.get_job("daily_snapshot:rs1") is not None
        rt.reload_settings(
            ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False))
        )
        assert scheduler.get_job("daily_snapshot:rs1") is None
        assert scheduler.get_job("backups_cleanup:rs1") is not None
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_reload_settings_re_enable_daily_snapshot(tmp_path, scheduler, alerts):
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "rs2"),
        settings=ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False)),
    )
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        assert scheduler.get_job("daily_snapshot:rs2") is None
        rt.reload_settings(
            ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=True))
        )
        assert scheduler.get_job("daily_snapshot:rs2") is not None
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_reload_settings_updates_retention_days(tmp_path, scheduler, alerts):
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "rs3"),
        settings=ProjectSettings(snapshots=SnapshotsSettings(retention_days=180)),
    )
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        rt.reload_settings(
            ProjectSettings(snapshots=SnapshotsSettings(retention_days=30))
        )
        job = scheduler.get_job("backups_cleanup:rs3")
        assert job is not None
        # args = [vault_root, retention_days]
        assert job.args[1] == 30
    finally:
        await rt.unmount(timeout=2.0, force=True)


def test_reload_settings_when_not_mounted_just_replaces(tmp_path):
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(project=_entry(tmp_path, "rs4"), settings=ProjectSettings())
    new = ProjectSettings(snapshots=SnapshotsSettings(retention_days=7))
    rt.reload_settings(new)
    assert rt.settings.snapshots.retention_days == 7
    rt.job_store.close()
```

- [ ] **Step 2: Run tests** → FAIL.

- [ ] **Step 3: Implement `reload_settings()`**

```python
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
```

- [ ] **Step 4: Run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/vault_runtime.py tests/daemon/test_vault_runtime.py
git commit -m "feat(daemon): VaultRuntime.reload_settings reschedules cron jobs"
```

---

## Task 10: `DaemonConfig` adds `BootFilter`, drops `vault_root`/`retention_days`

**Files:**
- Modify: `claude_mnemos/daemon/config.py`
- Modify: any test that instantiates `DaemonConfig(vault_root=...)` (search the tree)

- [ ] **Step 1: Identify call sites**

```
grep -rn "DaemonConfig(" claude_mnemos tests
grep -rn "DaemonConfig\b" claude_mnemos tests
```

Note every line. They will need updating in this task or downstream tasks (Task 12 + 21 + 22).

- [ ] **Step 2: Write the failing test**

Create or extend `tests/daemon/test_config.py`:

```python
from __future__ import annotations
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.daemon.config import BootFilter, DaemonConfig


def test_daemon_config_defaults():
    c = DaemonConfig(pid_file=Path("/tmp/p.pid"))
    assert c.host == "127.0.0.1"
    assert c.port == 5757
    assert c.boot_filter is None  # None == "all"


def test_daemon_config_rejects_legacy_vault_root():
    with pytest.raises(ValidationError):
        DaemonConfig(pid_file=Path("/tmp/p.pid"), vault_root=Path("/v"))


def test_daemon_config_rejects_legacy_retention_days():
    with pytest.raises(ValidationError):
        DaemonConfig(pid_file=Path("/tmp/p.pid"), retention_days=180)


def test_boot_filter_all_default_false():
    f = BootFilter()
    assert f.all is False
    assert f.names == []


def test_boot_filter_round_trip():
    f = BootFilter(all=False, names=["a", "b"])
    assert f.model_dump() == {"all": False, "names": ["a", "b"]}
```

- [ ] **Step 3: Run** → FAIL (BootFilter missing; vault_root still accepted).

- [ ] **Step 4: Update `config.py`**

```python
# claude_mnemos/daemon/config.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["debug", "info", "warning", "error"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5757
DEFAULT_LOG_LEVEL: LogLevel = "info"

LEGACY_HOME_DIRNAME = ".mnemos"
HOME_DIRNAME = ".claude-mnemos"


def default_pid_file() -> Path:
    return Path.home() / HOME_DIRNAME / "daemon.pid"


def default_runtime_config_file() -> Path:
    return Path.home() / HOME_DIRNAME / "daemon.config.json"


def migrate_legacy_dotmnemos() -> bool:
    """One-shot move from ~/.mnemos to ~/.claude-mnemos. Unchanged from α."""
    legacy_dir = Path.home() / LEGACY_HOME_DIRNAME
    if not legacy_dir.is_dir():
        return False
    new_dir = Path.home() / HOME_DIRNAME
    new_dir.mkdir(parents=True, exist_ok=True)
    moved = False
    for name in ("daemon.pid", "daemon.config.json"):
        src = legacy_dir / name
        dst = new_dir / name
        if src.is_file() and not dst.exists():
            try:
                dst.write_bytes(src.read_bytes())
                src.unlink()
                moved = True
            except OSError:
                continue
    return moved


class BootFilter(BaseModel):
    """Selects which projects daemon mounts at startup.

    None / all=True == every registered project.
    names=[...] == subset by project name; missing names alerted.
    """
    model_config = ConfigDict(extra="forbid")
    all: bool = False
    names: list[str] = Field(default_factory=list)


class DaemonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    log_level: LogLevel = DEFAULT_LOG_LEVEL
    pid_file: Path = Field(default_factory=default_pid_file)
    boot_filter: BootFilter | None = None

    @classmethod
    def from_env(cls) -> DaemonConfig:
        host = os.environ.get("MNEMOS_DAEMON_HOST", DEFAULT_HOST)
        port_str = os.environ.get("MNEMOS_DAEMON_PORT")
        port = int(port_str) if port_str else DEFAULT_PORT
        log_level_raw = os.environ.get("MNEMOS_DAEMON_LOG", DEFAULT_LOG_LEVEL).lower()
        if log_level_raw not in ("debug", "info", "warning", "error"):
            raise ValueError(
                f"MNEMOS_DAEMON_LOG must be one of debug/info/warning/error, "
                f"got {log_level_raw!r}"
            )
        log_level: LogLevel = log_level_raw  # type: ignore[assignment]
        pid_file_str = os.environ.get("MNEMOS_DAEMON_PID")
        pid_file = Path(pid_file_str) if pid_file_str else default_pid_file()
        return cls(host=host, port=port, log_level=log_level, pid_file=pid_file)
```

- [ ] **Step 5: Run** the new test:

```
pytest tests/daemon/test_config.py -v
```

- [ ] **Step 6: Update existing call sites that pass `vault_root=`/`retention_days=`**

Use the grep output. Most are in `claude_mnemos/cli.py` and tests. Replace with the appropriate signature. Leave a `# TODO(Task 22)` if a CLI call site is best fixed in the dedicated CLI task.

- [ ] **Step 7: Run the full daemon-config test slice**

```
pytest tests/daemon/test_config.py tests/daemon/test_lockfile.py -v
```

- [ ] **Step 8: Commit**

```bash
git add claude_mnemos/daemon/config.py tests/daemon/test_config.py
git commit -m "feat(daemon): DaemonConfig drops vault_root/retention_days, adds BootFilter"
```

If you had to update CLI call sites, include them in the same commit.

---

## Task 11: `DaemonRuntimeState` — drop `vault_root`, ignore unknown fields

**Files:**
- Modify: `claude_mnemos/daemon/runtime_state.py`
- Create: `tests/daemon/test_runtime_state_legacy.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/daemon/test_runtime_state_legacy.py
from __future__ import annotations
import json
from pathlib import Path

from claude_mnemos.daemon.runtime_state import DaemonRuntimeState


def test_load_legacy_alpha_file_with_vault_root(tmp_path: Path):
    """α users have ~/.claude-mnemos/daemon.config.json with vault_root.
    β1 ignores the field silently (extra='ignore')."""
    p = tmp_path / "daemon.config.json"
    p.write_text(json.dumps({
        "vault_root": "/some/old/path",
        "host": "127.0.0.1",
        "port": 5757,
        "pid_file": "/x/daemon.pid",
    }))
    state = DaemonRuntimeState.load(p)
    assert state is not None
    assert state.host == "127.0.0.1"
    assert state.port == 5757
    assert state.pid_file == Path("/x/daemon.pid")
    assert not hasattr(state, "vault_root")


def test_save_does_not_emit_vault_root(tmp_path: Path):
    p = tmp_path / "daemon.config.json"
    DaemonRuntimeState(host="127.0.0.1", port=5757, pid_file=Path("/x/p")).save(p)
    data = json.loads(p.read_text())
    assert "vault_root" not in data
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Update the model**

```python
# claude_mnemos/daemon/runtime_state.py
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.daemon.config import default_runtime_config_file


class DaemonRuntimeState(BaseModel):
    """Snapshot of the running daemon's effective config — used by
    `mnemos daemon status` / `stop`. After β1 the daemon is multi-vault,
    so vault_root is no longer part of the state.

    `extra='ignore'` lets us silently absorb α-written files that contain
    a now-defunct `vault_root` field.
    """

    model_config = ConfigDict(extra="ignore")

    host: str
    port: int = Field(ge=1, le=65535)
    pid_file: Path

    @classmethod
    def load(cls, path: Path | None = None) -> DaemonRuntimeState | None:
        path = path or default_runtime_config_file()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return cls.model_validate(data)
        except Exception:
            return None

    def save(self, path: Path | None = None) -> None:
        path = path or default_runtime_config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    @classmethod
    def cleanup(cls, path: Path | None = None) -> None:
        path = path or default_runtime_config_file()
        path.unlink(missing_ok=True)
```

- [ ] **Step 4: Run**

```
pytest tests/daemon/test_runtime_state_legacy.py -v
```

- [ ] **Step 5: Find and update call sites that build `DaemonRuntimeState(vault_root=...)`**

```
grep -rn "DaemonRuntimeState(" claude_mnemos tests
```

Remove the `vault_root=` keyword everywhere. Update affected tests.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/runtime_state.py tests/daemon/test_runtime_state_legacy.py
git commit -m "refactor(daemon): DaemonRuntimeState drops vault_root, ignores legacy field"
```

If you updated other tests/CLI call sites, include them.

---

## Task 12: `MnemosDaemon` — multi-vault `__init__` + `_recompute_primary`

**Files:**
- Modify: `claude_mnemos/daemon/process.py` (large rewrite)
- Modify: `claude_mnemos/daemon/app.py` (signature change)
- Create: `tests/daemon/test_process_multivault.py`

This task lays the spine of the multi-vault daemon. Mount/unmount methods come in Tasks 14-16; here we cover construction, primary selection, and the FastAPI app wiring.

- [ ] **Step 1: Write the failing tests**

```python
# tests/daemon/test_process_multivault.py
from __future__ import annotations
from pathlib import Path

import pytest

from claude_mnemos.daemon.config import BootFilter, DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
from claude_mnemos.state.settings import GlobalSettings, SettingsStore


def _setup_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def _config(tmp_path: Path, **kwargs) -> DaemonConfig:
    return DaemonConfig(pid_file=tmp_path / "d.pid", **kwargs)


def test_init_empty_runtimes(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))
    assert daemon.runtimes == {}
    assert daemon.primary_runtime is None
    assert daemon.app.state.vault_root is None


def test_recompute_primary_alphabetical_first(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))

    from claude_mnemos.daemon.vault_runtime import VaultRuntime
    from claude_mnemos.state.settings import ProjectSettings

    for name in ("zeta", "alpha", "mike"):
        v = tmp_path / name
        v.mkdir()
        rt = VaultRuntime(
            project=ProjectMapEntry(name=name, vault_root=v, cwd_patterns=[]),
            settings=ProjectSettings(),
        )
        daemon.runtimes[name] = rt
        rt.job_store.close()  # we won't mount here — just test selection

    daemon._recompute_primary()
    assert daemon.primary_runtime is not None
    assert daemon.primary_runtime.name == "alpha"
    assert daemon.app.state.vault_root == tmp_path / "alpha"


def test_recompute_primary_pinned(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)

    SettingsStore().set_global(GlobalSettings(primary_project="mike"))

    daemon = MnemosDaemon(_config(tmp_path))

    from claude_mnemos.daemon.vault_runtime import VaultRuntime
    from claude_mnemos.state.settings import ProjectSettings

    for name in ("zeta", "alpha", "mike"):
        v = tmp_path / name
        v.mkdir()
        rt = VaultRuntime(
            project=ProjectMapEntry(name=name, vault_root=v, cwd_patterns=[]),
            settings=ProjectSettings(),
        )
        daemon.runtimes[name] = rt
        rt.job_store.close()

    daemon._recompute_primary()
    assert daemon.primary_runtime.name == "mike"


def test_recompute_primary_pinned_missing_falls_back(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    SettingsStore().set_global(GlobalSettings(primary_project="absent"))

    daemon = MnemosDaemon(_config(tmp_path))

    from claude_mnemos.daemon.vault_runtime import VaultRuntime
    from claude_mnemos.state.settings import ProjectSettings

    for name in ("alpha", "beta"):
        v = tmp_path / name
        v.mkdir()
        rt = VaultRuntime(
            project=ProjectMapEntry(name=name, vault_root=v, cwd_patterns=[]),
            settings=ProjectSettings(),
        )
        daemon.runtimes[name] = rt
        rt.job_store.close()

    daemon._recompute_primary()
    assert daemon.primary_runtime.name == "alpha"  # alphabetical first


def test_recompute_primary_empty_runtimes(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))
    daemon._recompute_primary()
    assert daemon.primary_runtime is None
    assert daemon.app.state.vault_root is None
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Update `app.py` signature**

```python
# claude_mnemos/daemon/app.py — change create_app signature
def create_app(vault_root: Path | None = None, daemon: Any | None = None) -> FastAPI:
    app = FastAPI(title="claude-mnemos daemon", version=__version__)
    app.state.vault_root = vault_root  # may be None when no primary yet
    app.state.daemon = daemon
    # … rest unchanged …
```

- [ ] **Step 4: Rewrite `MnemosDaemon` core**

```python
# claude_mnemos/daemon/process.py
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.lockfile import cleanup_pid_file, write_pid_file
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
    a self-contained VaultRuntime; the scheduler and alerts are shared.
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
        return self._primary_runtime

    def _recompute_primary(self) -> None:
        primary: VaultRuntime | None = None
        pinned = self.global_settings.primary_project
        if pinned and pinned in self.runtimes:
            primary = self.runtimes[pinned]
        elif self.runtimes:
            primary = self.runtimes[min(self.runtimes.keys())]
        self._primary_runtime = primary
        self.app.state.vault_root = primary.vault_root if primary else None
```

(The mount/unmount methods + `run()` are added in Tasks 14-16. For now, this file may not be runnable end-to-end. The unit tests for primary/_init_ pass.)

- [ ] **Step 5: Update old `MnemosDaemon` tests**

`tests/daemon/test_process_*.py` likely instantiates `MnemosDaemon(DaemonConfig(vault_root=..., retention_days=...))`. Skip-mark or update those tests minimally so the suite stays mostly green; full overhaul comes when `mount_vault` lands in Task 14.

- [ ] **Step 6: Run new tests**

```
pytest tests/daemon/test_process_multivault.py -v
```

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/daemon/process.py claude_mnemos/daemon/app.py tests/daemon/test_process_multivault.py
git commit -m "refactor(daemon): MnemosDaemon multi-vault __init__ + _recompute_primary"
```

---

## Task 13: `_select_boot_entries` + `_bootstrap_runtimes`

**Files:**
- Modify: `claude_mnemos/daemon/process.py`
- Modify: `tests/daemon/test_process_multivault.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/daemon/test_process_multivault.py`:

```python
def _add_project(name: str, vault: Path) -> ProjectMapEntry:
    vault.mkdir(parents=True, exist_ok=True)
    e = ProjectMapEntry(name=name, vault_root=vault, cwd_patterns=[])
    ProjectStore().add(e)
    return e


def test_select_boot_entries_all_default(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")
    _add_project("beta", tmp_path / "b")

    daemon = MnemosDaemon(_config(tmp_path))
    selected = daemon._select_boot_entries()
    assert [e.name for e in selected] == ["alpha", "beta"]


def test_select_boot_entries_filter_subset(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")
    _add_project("beta", tmp_path / "b")
    _add_project("gamma", tmp_path / "g")

    daemon = MnemosDaemon(
        _config(tmp_path, boot_filter=BootFilter(names=["alpha", "gamma"]))
    )
    selected = daemon._select_boot_entries()
    assert [e.name for e in selected] == ["alpha", "gamma"]


def test_select_boot_entries_missing_name_alerts(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")

    daemon = MnemosDaemon(
        _config(tmp_path, boot_filter=BootFilter(names=["alpha", "ghost"]))
    )
    selected = daemon._select_boot_entries()
    assert [e.name for e in selected] == ["alpha"]
    msgs = [a.message for a in daemon.alerts.list()]
    assert any("'ghost'" in m for m in msgs)


def test_select_boot_entries_empty_map(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))
    assert daemon._select_boot_entries() == []


@pytest.mark.asyncio
async def test_bootstrap_runtimes_mounts_all(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")
    _add_project("beta", tmp_path / "b")

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon._bootstrap_runtimes()
        assert set(daemon.runtimes.keys()) == {"alpha", "beta"}
        for rt in daemon.runtimes.values():
            assert rt.is_mounted is True
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_bootstrap_runtimes_partial_failure_continues(
    tmp_path: Path, monkeypatch
):
    _setup_home(tmp_path, monkeypatch)
    _add_project("good", tmp_path / "good")
    # Bad project: vault_root points at a path that does not exist —
    # JobStore will create the parent or raise depending on impl. Force
    # via monkeypatch on VaultObserver to raise on the bad name.
    bad = tmp_path / "bad"
    bad.mkdir()
    _add_project("bad", bad)

    from claude_mnemos.daemon import vault_runtime as vr

    real_observer = vr.VaultObserver

    class _MaybeBoom:
        def __init__(self, root, handler):
            self._root = root
            self._real = real_observer(root, handler)

        def start(self):
            if "bad" in str(self._root):
                raise RuntimeError("simulated mount failure")
            return self._real.start()

        def stop(self):
            try:
                self._real.stop()
            except Exception:
                pass

    monkeypatch.setattr(vr, "VaultObserver", _MaybeBoom)

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon._bootstrap_runtimes()
        assert "good" in daemon.runtimes
        assert "bad" not in daemon.runtimes
        msgs = [a.message for a in daemon.alerts.list()]
        assert any("simulated mount failure" in m for m in msgs)
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement methods**

Append to `claude_mnemos/daemon/process.py` inside `MnemosDaemon`:

```python
from claude_mnemos.daemon.vault_runtime import VaultMountError, VaultRuntime

# (keep TYPE_CHECKING import for class annotation; runtime import here.)

def _select_boot_entries(self) -> list[ProjectMapEntry]:
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
            message=(
                f"--project asked for {m!r}, not in project-map; skipped"
            ),
            detected_at=datetime.now(UTC),
        )
    return [e for e in all_entries if e.name in wanted]


async def _bootstrap_runtimes(self) -> None:
    """Mount every selected project. Failures degrade to alerts."""
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
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/process.py tests/daemon/test_process_multivault.py
git commit -m "feat(daemon): bootstrap_runtimes + select_boot_entries with filter + alerts"
```

---

## Task 14: `mount_vault` / `unmount_vault` / `remount_vault`

**Files:**
- Modify: `claude_mnemos/daemon/process.py`
- Modify: `tests/daemon/test_process_multivault.py`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_mount_vault_appends_to_runtimes(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        new_entry = _add_project("beta", tmp_path / "b")
        await daemon.mount_vault(new_entry)
        assert "beta" in daemon.runtimes
        assert daemon.runtimes["beta"].is_mounted
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_mount_vault_duplicate_raises(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    e = _add_project("alpha", tmp_path / "a")
    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon.mount_vault(e)
        from claude_mnemos.daemon.vault_runtime import VaultMountError
        with pytest.raises(VaultMountError):
            await daemon.mount_vault(e)
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_unmount_vault_removes_from_dict(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    e = _add_project("alpha", tmp_path / "a")
    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon.mount_vault(e)
        await daemon.unmount_vault("alpha")
        assert "alpha" not in daemon.runtimes
    finally:
        daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_unmount_vault_unknown_raises_keyerror(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        with pytest.raises(KeyError):
            await daemon.unmount_vault("ghost")
    finally:
        daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_remount_vault_swaps_root(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    e = _add_project("alpha", tmp_path / "a-old")

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon.mount_vault(e)
        old_observer = daemon.runtimes["alpha"].observer

        new_root = tmp_path / "a-new"
        new_root.mkdir()
        new_entry = ProjectMapEntry(name="alpha", vault_root=new_root, cwd_patterns=[])
        await daemon.remount_vault(new_entry)
        assert daemon.runtimes["alpha"].vault_root == new_root
        assert daemon.runtimes["alpha"].observer is not old_observer
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement the three methods**

Append inside `MnemosDaemon`:

```python
async def mount_vault(self, entry: ProjectMapEntry) -> VaultRuntime:
    async with self._runtimes_lock:
        if entry.name in self.runtimes:
            from claude_mnemos.daemon.vault_runtime import VaultMountError
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
    async with self._runtimes_lock:
        runtime = self.runtimes.get(name)
        if runtime is None:
            raise KeyError(name)
        await runtime.unmount(timeout=drain_timeout, force=force)
        del self.runtimes[name]
        self._recompute_primary()


async def remount_vault(self, entry: ProjectMapEntry) -> VaultRuntime:
    async with self._runtimes_lock:
        old = self.runtimes.get(entry.name)
        if old is not None:
            await old.unmount(timeout=10.0, force=False)
            del self.runtimes[entry.name]
        settings = self.settings_store.get_project(entry.name)
        runtime = VaultRuntime(project=entry, settings=settings)
        await runtime.mount(scheduler=self.scheduler, alerts=self.alerts)
        self.runtimes[entry.name] = runtime
        self._recompute_primary()
        return runtime
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/process.py tests/daemon/test_process_multivault.py
git commit -m "feat(daemon): mount_vault/unmount_vault/remount_vault under runtimes_lock"
```

---

## Task 15: `reload_project_settings` / `reload_global_settings`

**Files:**
- Modify: `claude_mnemos/daemon/process.py`
- Modify: `tests/daemon/test_process_multivault.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_reload_project_settings_applies_to_runtime(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    e = _add_project("alpha", tmp_path / "a")

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon.mount_vault(e)
        from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

        new = ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False))
        await daemon.reload_project_settings("alpha", new)
        assert daemon.runtimes["alpha"].settings.snapshots.daily_enabled is False
        assert daemon.scheduler.get_job("daily_snapshot:alpha") is None
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_reload_project_settings_for_unmounted_no_op(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        from claude_mnemos.state.settings import ProjectSettings
        # Should not raise even if "ghost" is unmounted (no runtime in dict).
        await daemon.reload_project_settings("ghost", ProjectSettings())
    finally:
        daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_reload_global_settings_repicks_primary(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")
    _add_project("beta", tmp_path / "b")

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon._bootstrap_runtimes()
        daemon._recompute_primary()
        assert daemon.primary_runtime.name == "alpha"

        new_global = GlobalSettings(primary_project="beta")
        await daemon.reload_global_settings(new_global)
        assert daemon.primary_runtime.name == "beta"
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```python
async def reload_project_settings(
    self, name: str, new: ProjectSettings,
) -> None:
    async with self._runtimes_lock:
        runtime = self.runtimes.get(name)
        if runtime is None:
            return  # not mounted; settings file is the source of truth
        runtime.reload_settings(new)


async def reload_global_settings(self, new: GlobalSettings) -> None:
    async with self._runtimes_lock:
        self.global_settings = new
        self._recompute_primary()
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/process.py tests/daemon/test_process_multivault.py
git commit -m "feat(daemon): reload_project_settings + reload_global_settings"
```

---

## Task 16: `MnemosDaemon.run()` + `_shutdown_runtimes()`

**Files:**
- Modify: `claude_mnemos/daemon/process.py`
- Modify: `tests/daemon/test_process_multivault.py` (or add a small subprocess smoke)

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_shutdown_unmounts_all_with_force(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")
    _add_project("beta", tmp_path / "b")

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    await daemon._bootstrap_runtimes()
    # Enqueue a job in alpha so force=True path is exercised.
    daemon.runtimes["alpha"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )

    await daemon._shutdown_runtimes()

    assert daemon.runtimes == {}
    assert daemon.primary_runtime is None
    daemon.scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement `run()` + `_shutdown_runtimes` + signal handlers**

```python
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
        self._primary_runtime = None
        self.app.state.vault_root = None
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


def _request_shutdown(self) -> None:
    if self._server is not None:
        self._server.should_exit = True
```

- [ ] **Step 4: Run**

```
pytest tests/daemon/test_process_multivault.py -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/process.py tests/daemon/test_process_multivault.py
git commit -m "feat(daemon): MnemosDaemon.run + _shutdown_runtimes (force-unmount-all)"
```

---

## Task 17: `_vault(request)` helpers handle None primary

**Files:**
- Modify: every route file under `claude_mnemos/daemon/routes/` that has a `_vault(request)` helper. Confirm the list:

```
grep -rln "request.app.state.vault_root" claude_mnemos/daemon/routes
```

Expect: `activity.py`, `snapshots.py`, `pages.py`, `trash.py`, `lint.py`, `ontology.py`, `dead_letter.py`, `lost_sessions.py`, `sessions.py`, `metrics.py`, `vault.py`, `alerts.py` (if present).

- Modify: `tests/daemon/test_routes_*.py` (add at least one None-primary test per affected route)
- Create: `tests/daemon/test_routes_no_primary.py` (consolidated coverage)

- [ ] **Step 1: Write the failing test**

```python
# tests/daemon/test_routes_no_primary.py
from __future__ import annotations
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(vault_root=None, daemon=None)
    return TestClient(app)


@pytest.mark.parametrize("path", [
    "/snapshots",
    "/activity",
    "/pages",
    "/trash",
    "/lint",
    "/ontology",
    "/dead-letter",
    "/lost-sessions",
    "/sessions",
    "/metrics/usage",
])
def test_routes_return_503_when_no_primary(client, path):
    r = client.get(path)
    assert r.status_code == 503, (path, r.text)
    body = r.json()
    assert body.get("detail", {}).get("error") == "no_vault_registered"


def test_health_works_without_primary(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_projects_works_without_primary(client):
    r = client.get("/projects")
    assert r.status_code == 200
```

- [ ] **Step 2: Run** → FAIL (some routes 500 because `_vault` blindly asserts).

- [ ] **Step 3: Update every `_vault` helper**

Pattern (apply identically across files):

```python
def _vault(request: Request) -> Path:
    vault = request.app.state.vault_root
    if vault is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_vault_registered",
                "hint": "Register: mnemos project add NAME --vault PATH",
            },
        )
    assert isinstance(vault, Path)
    return vault
```

If a route reads `request.app.state.vault_root` directly without going through a helper, add the same None guard inline.

- [ ] **Step 4: Run**

```
pytest tests/daemon/test_routes_no_primary.py -v
```

If a parametrized path 404's because the actual URL is different (e.g. `/sessions` requires path params), drop it from the param list — the goal is *every route group* gets None coverage, not literally every URL.

- [ ] **Step 5: Run the full route test suite**

```
pytest tests/daemon/ -v
```

Adjust any test that assumed `vault_root` was always set.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/ tests/daemon/test_routes_no_primary.py
git commit -m "feat(daemon): _vault helper returns 503 when no primary registered"
```

---

## Task 18: `/projects` routes — hot mount/unmount/remount

**Files:**
- Modify: `claude_mnemos/daemon/routes/projects.py`
- Create: `tests/daemon/test_routes_projects_hotmount.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/daemon/test_routes_projects_hotmount.py
from __future__ import annotations
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon_with_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    daemon.scheduler.start()
    yield daemon
    asyncio.run(daemon._shutdown_runtimes())
    daemon.scheduler.shutdown(wait=False)


def test_post_projects_hot_mounts(daemon_with_app, tmp_path):
    daemon = daemon_with_app
    vault = tmp_path / "alpha"
    vault.mkdir()
    client = TestClient(daemon.app)
    r = client.post("/projects", json={
        "name": "alpha",
        "vault_root": str(vault),
        "cwd_patterns": [],
    })
    assert r.status_code == 201, r.text
    assert "alpha" in daemon.runtimes
    assert daemon.runtimes["alpha"].is_mounted


def test_post_projects_mount_failure_rolls_back_map(
    daemon_with_app, tmp_path, monkeypatch
):
    daemon = daemon_with_app
    vault = tmp_path / "rb"
    vault.mkdir()

    from claude_mnemos.daemon import vault_runtime as vr

    class _Boom:
        def __init__(self, *a, **k): pass
        def start(self): raise RuntimeError("simulated")
        def stop(self): pass

    monkeypatch.setattr(vr, "VaultObserver", _Boom)

    client = TestClient(daemon.app)
    r = client.post("/projects", json={
        "name": "rb",
        "vault_root": str(vault),
        "cwd_patterns": [],
    })
    assert r.status_code == 500
    # Project map should be rolled back.
    list_r = client.get("/projects")
    assert all(e["name"] != "rb" for e in list_r.json()["projects"])


def test_delete_projects_busy_returns_409(daemon_with_app, tmp_path):
    daemon = daemon_with_app
    vault = tmp_path / "busy"
    vault.mkdir()
    client = TestClient(daemon.app)
    client.post("/projects", json={"name": "busy", "vault_root": str(vault), "cwd_patterns": []})

    daemon.runtimes["busy"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )
    r = client.delete("/projects/busy")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "vault_busy"


def test_delete_projects_force_drains(daemon_with_app, tmp_path):
    daemon = daemon_with_app
    vault = tmp_path / "drain"
    vault.mkdir()
    client = TestClient(daemon.app)
    client.post("/projects", json={"name": "drain", "vault_root": str(vault), "cwd_patterns": []})
    daemon.runtimes["drain"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )
    r = client.delete("/projects/drain?force=true")
    assert r.status_code == 204
    assert "drain" not in daemon.runtimes


def test_patch_vault_root_remounts(daemon_with_app, tmp_path):
    daemon = daemon_with_app
    old_vault = tmp_path / "old"
    old_vault.mkdir()
    new_vault = tmp_path / "new"
    new_vault.mkdir()
    client = TestClient(daemon.app)
    client.post("/projects", json={"name": "rm", "vault_root": str(old_vault), "cwd_patterns": []})
    r = client.patch("/projects/rm", json={"vault_root": str(new_vault)})
    assert r.status_code == 200
    assert daemon.runtimes["rm"].vault_root == new_vault


def test_patch_vault_root_busy_returns_409_without_changing_map(
    daemon_with_app, tmp_path
):
    daemon = daemon_with_app
    old_vault = tmp_path / "old2"
    old_vault.mkdir()
    new_vault = tmp_path / "new2"
    new_vault.mkdir()
    client = TestClient(daemon.app)
    client.post("/projects", json={"name": "rm2", "vault_root": str(old_vault), "cwd_patterns": []})
    daemon.runtimes["rm2"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )
    r = client.patch("/projects/rm2", json={"vault_root": str(new_vault)})
    assert r.status_code == 409
    show = client.get("/projects/rm2").json()
    assert show["vault_root"] == str(old_vault)  # map untouched
```

- [ ] **Step 2: Run** → FAIL (existing routes don't call daemon mount/unmount/remount).

- [ ] **Step 3: Update `claude_mnemos/daemon/routes/projects.py`**

Replace the existing POST/DELETE/PATCH handlers. Keep GET handlers as-is.

```python
# Inside POST /projects
@router.post("/projects", status_code=201)
async def create_project(request: Request, body: ProjectCreate) -> dict[str, Any]:
    store = ProjectStore()
    entry = ProjectMapEntry(
        name=body.name,
        vault_root=body.vault_root,
        cwd_patterns=body.cwd_patterns or [],
    )
    try:
        store.add(entry)
    except ProjectNameConflictError as exc:
        raise HTTPException(409, detail={"error": "name_conflict", "detail": str(exc)})

    daemon = request.app.state.daemon
    if daemon is not None:
        from claude_mnemos.daemon.vault_runtime import VaultMountError

        try:
            await daemon.mount_vault(entry)
        except VaultMountError as exc:
            try:
                store.remove(entry.name)
            except Exception:
                pass
            raise HTTPException(500, detail={"error": "mount_failed", "detail": str(exc)})

    return entry.model_dump(mode="json")


# Inside DELETE /projects/{name}
@router.delete("/projects/{name}", status_code=204)
async def delete_project(name: str, request: Request, force: bool = False) -> Response:
    daemon = request.app.state.daemon
    if daemon is not None and name in daemon.runtimes:
        from claude_mnemos.daemon.vault_runtime import VaultBusyError

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

    try:
        ProjectStore().remove(name)
    except ProjectNotFoundError:
        if daemon is None or name not in (e.name for e in ProjectStore().list_all()):
            raise HTTPException(404, detail={"error": "not_found", "name": name})
    return Response(status_code=204)


# Inside PATCH /projects/{name}
@router.patch("/projects/{name}")
async def patch_project(
    name: str, request: Request, body: ProjectPatch
) -> dict[str, Any]:
    daemon = request.app.state.daemon
    new_vault = body.vault_root
    new_patterns = body.cwd_patterns

    # Pre-flight busy check before touching the map (vault_root change only).
    if daemon is not None and name in daemon.runtimes and new_vault is not None:
        current = daemon.runtimes[name].vault_root
        if current != new_vault:
            counts = daemon.runtimes[name].job_store.count_by_status()
            queued = int(counts.get("queued", 0))
            running = int(counts.get("running", 0))
            if queued or running:
                raise HTTPException(
                    409,
                    detail={
                        "error": "vault_busy",
                        "queued": queued,
                        "running": running,
                        "hint": "drain or cancel jobs before changing vault_root",
                    },
                )

    try:
        new_entry = ProjectStore().update(
            name, vault_root=new_vault, cwd_patterns=new_patterns
        )
    except ProjectNotFoundError:
        raise HTTPException(404, detail={"error": "not_found", "name": name})

    if daemon is not None and name in daemon.runtimes and new_vault is not None:
        if daemon.runtimes[name].vault_root != new_entry.vault_root:
            from claude_mnemos.daemon.vault_runtime import VaultMountError
            try:
                await daemon.remount_vault(new_entry)
            except VaultMountError as exc:
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

(`ProjectCreate` / `ProjectPatch` request models are already defined in α route file; reuse them.)

- [ ] **Step 4: Run**

```
pytest tests/daemon/test_routes_projects_hotmount.py -v
```

- [ ] **Step 5: Re-run the full daemon test suite**

```
pytest tests/daemon/ -v
```

Fix any α-tests on routes that asserted old behaviour (e.g. POST without daemon ref returning 200 — now still 201, but if a test relies on `request.app.state.daemon is None` working, set `daemon=None` explicitly via `create_app`).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/projects.py tests/daemon/test_routes_projects_hotmount.py
git commit -m "feat(daemon): /projects POST/DELETE/PATCH hot-mount/unmount/remount"
```

---

## Task 19: `/settings` routes — daemon-aware reload

**Files:**
- Modify: `claude_mnemos/daemon/routes/settings.py`
- Create: `tests/daemon/test_routes_settings_reload.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/daemon/test_routes_settings_reload.py
from __future__ import annotations
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon_with_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    daemon.scheduler.start()
    yield daemon
    asyncio.run(daemon._shutdown_runtimes())
    daemon.scheduler.shutdown(wait=False)


def test_patch_project_settings_reloads_runtime(daemon_with_app, tmp_path):
    daemon = daemon_with_app
    vault = tmp_path / "alpha"
    vault.mkdir()
    client = TestClient(daemon.app)
    client.post("/projects", json={"name": "alpha", "vault_root": str(vault), "cwd_patterns": []})

    assert daemon.scheduler.get_job("daily_snapshot:alpha") is not None
    r = client.patch("/settings/alpha", json={"snapshots": {"daily_enabled": False}})
    assert r.status_code == 200, r.text
    assert daemon.scheduler.get_job("daily_snapshot:alpha") is None


def test_patch_global_settings_repicks_primary(daemon_with_app, tmp_path):
    daemon = daemon_with_app
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    client = TestClient(daemon.app)
    client.post("/projects", json={"name": "alpha", "vault_root": str(a), "cwd_patterns": []})
    client.post("/projects", json={"name": "beta", "vault_root": str(b), "cwd_patterns": []})
    assert daemon.primary_runtime.name == "alpha"

    r = client.patch("/settings/global", json={"primary_project": "beta"})
    assert r.status_code == 200, r.text
    assert daemon.primary_runtime.name == "beta"
    assert daemon.app.state.vault_root == b
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Update `claude_mnemos/daemon/routes/settings.py`**

Locate the existing PATCH handlers. Wrap their reload step:

```python
# PATCH /settings/{name}
@router.patch("/settings/{name}")
async def patch_project_settings(
    name: str, request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    store = SettingsStore()
    try:
        new = store.patch_project(name, body)
    except ValidationError as exc:
        raise HTTPException(422, detail={"error": "validation_error", "detail": exc.errors()})

    daemon = request.app.state.daemon
    if daemon is not None:
        await daemon.reload_project_settings(name, new)
    return new.model_dump(mode="json")


# PATCH /settings/global
@router.patch("/settings/global")
async def patch_global_settings(
    request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    store = SettingsStore()
    try:
        new = store.patch_global(body)
    except ValidationError as exc:
        raise HTTPException(422, detail={"error": "validation_error", "detail": exc.errors()})
    daemon = request.app.state.daemon
    if daemon is not None:
        await daemon.reload_global_settings(new)
    return new.model_dump(mode="json")
```

- [ ] **Step 4: Run**

```
pytest tests/daemon/test_routes_settings_reload.py -v
```

- [ ] **Step 5: Run the full settings test suite**

```
pytest tests/daemon/test_routes_settings*.py tests/daemon/test_settings_consumption.py -v
```

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/settings.py tests/daemon/test_routes_settings_reload.py
git commit -m "feat(daemon): /settings PATCH triggers daemon.reload_*_settings"
```

---

## Task 20: `/jobs` POST routes by `payload.project_name`

**Files:**
- Modify: `claude_mnemos/daemon/routes/jobs.py`
- Create: `tests/daemon/test_routes_jobs_routing.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/daemon/test_routes_jobs_routing.py
from __future__ import annotations
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon_with_two(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    daemon.scheduler.start()
    client = TestClient(daemon.app)
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    client.post("/projects", json={"name": "alpha", "vault_root": str(a), "cwd_patterns": []})
    client.post("/projects", json={"name": "beta", "vault_root": str(b), "cwd_patterns": []})
    yield daemon, client, tmp_path
    asyncio.run(daemon._shutdown_runtimes())
    daemon.scheduler.shutdown(wait=False)


def test_jobs_post_routes_by_project_name(daemon_with_two):
    daemon, client, tmp_path = daemon_with_two
    transcript_a = tmp_path / "a" / "t.jsonl"
    transcript_a.write_text("{}\n")
    transcript_b = tmp_path / "b" / "t.jsonl"
    transcript_b.write_text("{}\n")

    r = client.post("/jobs", json={
        "kind": "ingest",
        "payload": {"project_name": "alpha", "transcript_path": str(transcript_a)},
    })
    assert r.status_code == 201, r.text

    r = client.post("/jobs", json={
        "kind": "ingest",
        "payload": {"project_name": "beta", "transcript_path": str(transcript_b)},
    })
    assert r.status_code == 201, r.text

    a_count = daemon.runtimes["alpha"].job_store.count_by_status()
    b_count = daemon.runtimes["beta"].job_store.count_by_status()
    assert sum(a_count.values()) == 1
    assert sum(b_count.values()) == 1


def test_jobs_post_missing_project_name_returns_400(daemon_with_two):
    daemon, client, tmp_path = daemon_with_two
    t = tmp_path / "a" / "t.jsonl"
    t.write_text("{}\n")
    r = client.post("/jobs", json={
        "kind": "ingest",
        "payload": {"transcript_path": str(t)},
    })
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_project_name"


def test_jobs_post_unknown_project_returns_400(daemon_with_two):
    daemon, client, tmp_path = daemon_with_two
    t = tmp_path / "a" / "t.jsonl"
    t.write_text("{}\n")
    r = client.post("/jobs", json={
        "kind": "ingest",
        "payload": {"project_name": "ghost", "transcript_path": str(t)},
    })
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unknown_project"
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite `/jobs` POST**

```python
# claude_mnemos/daemon/routes/jobs.py
import sqlite3
# … existing imports …


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
        raise HTTPException(400, detail={"error": "missing_project_name"})

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

GET / DELETE handlers in the same file: route through `daemon.primary_runtime.job_store` (replacing the existing `_store(request)` helper). Quick patch:

```python
def _store(request: Request) -> JobStore:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, detail={"error": "jobs_subsystem_unavailable"})
    primary = getattr(daemon, "primary_runtime", None)
    if primary is None or primary.job_store is None:
        raise HTTPException(503, detail={"error": "no_vault_registered"})
    return primary.job_store
```

- [ ] **Step 4: Run**

```
pytest tests/daemon/test_routes_jobs_routing.py tests/daemon/ -k jobs -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/jobs.py tests/daemon/test_routes_jobs_routing.py
git commit -m "feat(daemon): /jobs POST routes by project_name; GET/DELETE use primary"
```

---

## Task 21: `python -m claude_mnemos.daemon` argparse — `--all`/`--project`

**Files:**
- Modify: `claude_mnemos/daemon/__main__.py`
- Create: extend `tests/daemon/test_main.py` (or create if missing)

- [ ] **Step 1: Write the failing test**

```python
# tests/daemon/test_main.py — add
import pytest
from claude_mnemos.daemon.__main__ import build_parser


def test_parser_default_no_filter():
    args = build_parser().parse_args(["run"])
    assert args.cmd == "run"
    assert getattr(args, "all", False) is False
    assert getattr(args, "project", "") == ""


def test_parser_all_flag():
    args = build_parser().parse_args(["run", "--all"])
    assert args.all is True
    assert args.project == ""


def test_parser_project_subset():
    args = build_parser().parse_args(["run", "--project", "alpha,beta"])
    assert args.project == "alpha,beta"


def test_parser_all_and_project_conflict():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--all", "--project", "alpha"])


def test_parser_drops_vault_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--vault", "/x"])
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite `__main__.py`**

```python
# claude_mnemos/daemon/__main__.py
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from claude_mnemos.daemon.config import (
    DEFAULT_LOG_LEVEL,
    BootFilter,
    DaemonConfig,
    default_pid_file,
)
from claude_mnemos.daemon.process import MnemosDaemon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude_mnemos.daemon")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="Run the daemon in foreground")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=5757)
    run.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["debug", "info", "warning", "error"],
    )
    run.add_argument("--pid-file", type=Path, default=default_pid_file())
    grp = run.add_mutually_exclusive_group()
    grp.add_argument(
        "--all", action="store_true",
        help="Mount every project in project-map (default).",
    )
    grp.add_argument(
        "--project", default="",
        help="Comma-separated subset of project names to mount.",
    )
    return parser


def _build_config(args: argparse.Namespace) -> DaemonConfig:
    boot_filter: BootFilter | None
    if args.project:
        names = [n.strip() for n in args.project.split(",") if n.strip()]
        boot_filter = BootFilter(all=False, names=names)
    elif args.all:
        boot_filter = BootFilter(all=True)
    else:
        boot_filter = None  # None == all by convention
    return DaemonConfig(
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        pid_file=args.pid_file,
        boot_filter=boot_filter,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd != "run":
        return 1
    config = _build_config(args)
    daemon = MnemosDaemon(config)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run**

```
pytest tests/daemon/test_main.py -v
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/__main__.py tests/daemon/test_main.py
git commit -m "feat(daemon): __main__ replaces --vault with --all/--project (mutually exclusive)"
```

---

## Task 22: `mnemos daemon start|foreground` CLI — flags + `--vault` hard error

**Files:**
- Modify: `claude_mnemos/cli.py` (search for `_cmd_daemon_start`, `_cmd_daemon_foreground`, `_resolve_daemon_config`)
- Create: `tests/test_cli_daemon_multivault.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_daemon_multivault.py
from __future__ import annotations
from pathlib import Path

import pytest

from claude_mnemos.cli import build_parser, _resolve_daemon_config
from claude_mnemos.daemon.config import BootFilter


def test_daemon_start_default_no_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter is None  # None == "all"


def test_daemon_start_all_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start", "--all"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter == BootFilter(all=True)


def test_daemon_start_project_subset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start", "--project", "alpha,beta"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter == BootFilter(names=["alpha", "beta"])


def test_daemon_start_vault_flag_rejected():
    """--vault PATH legacy flag must exit with code 2 + migration hint."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["daemon", "start", "--vault", "/v"])
    assert exc.value.code == 2
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Update `claude_mnemos/cli.py`**

Find `daemon` subparser construction. Replace `--vault` argument with `--all`/`--project` (mutually exclusive). Anywhere a custom error message is needed for the rejected `--vault`, intercept before argparse via a custom action:

```python
class _VaultDeprecated(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        parser.exit(2, (
            "--vault is no longer supported. Register the vault first:\n"
            "    mnemos project add NAME --vault PATH\n"
            "Then start daemon with `mnemos daemon start` (mounts all projects)\n"
            "or `mnemos daemon start --project NAME`.\n"
        ))


def _add_daemon_start_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--port", type=int)
    p.add_argument("--log-level")
    p.add_argument("--pid-file", type=Path)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--all", action="store_true")
    grp.add_argument("--project", default="")
    # Hard-cut for legacy.
    p.add_argument("--vault", action=_VaultDeprecated, nargs="?", help=argparse.SUPPRESS)
```

`_resolve_daemon_config(args)` now builds `boot_filter`:

```python
def _resolve_daemon_config(args: argparse.Namespace) -> DaemonConfig:
    base = DaemonConfig.from_env()
    overrides: dict[str, Any] = {}
    if getattr(args, "port", None):
        overrides["port"] = args.port
    if getattr(args, "log_level", None):
        overrides["log_level"] = args.log_level
    if getattr(args, "pid_file", None):
        overrides["pid_file"] = args.pid_file

    boot_filter: BootFilter | None
    project = getattr(args, "project", "")
    if project:
        names = [n.strip() for n in project.split(",") if n.strip()]
        boot_filter = BootFilter(all=False, names=names)
    elif getattr(args, "all", False):
        boot_filter = BootFilter(all=True)
    else:
        boot_filter = None
    overrides["boot_filter"] = boot_filter

    return base.model_copy(update=overrides)
```

In `_cmd_daemon_start`, drop every `vault_root`-related branch. The subprocess command line passed to `claude_mnemos.daemon` becomes:

```python
cmd = [
    sys.executable, "-m", "claude_mnemos.daemon", "run",
    "--host", config.host,
    "--port", str(config.port),
    "--log-level", config.log_level,
    "--pid-file", str(config.pid_file),
]
if config.boot_filter is not None:
    if config.boot_filter.all:
        cmd.append("--all")
    elif config.boot_filter.names:
        cmd.extend(["--project", ",".join(config.boot_filter.names)])
```

`_cmd_daemon_foreground` mirrors but invokes `MnemosDaemon` in-process:

```python
def _cmd_daemon_foreground(args: argparse.Namespace) -> int:
    config = _resolve_daemon_config(args)
    pid = is_daemon_running(config.pid_file)
    if pid is not None:
        print(f"daemon already running on :{config.port}, pid={pid}", file=sys.stderr)
        return 78
    DaemonRuntimeState(host=config.host, port=config.port, pid_file=config.pid_file).save()
    daemon = MnemosDaemon(config)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        return 0
    finally:
        DaemonRuntimeState.cleanup()
    return 0
```

- [ ] **Step 4: Run**

```
pytest tests/test_cli_daemon_multivault.py tests/test_cli.py -v
```

Update any CLI test that assumed `--vault PATH` worked.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/cli.py tests/test_cli_daemon_multivault.py
git commit -m "feat(cli): mnemos daemon start --all/--project; --vault hard error"
```

---

## Task 23: `cli_project._handle_update` — TOCTOU fix (drop pre-read)

**Files:**
- Modify: `claude_mnemos/cli_project.py` (around `_handle_update`)
- Modify: `tests/test_cli_project.py`

- [ ] **Step 1: Read current `_handle_update`**

```
grep -n "_handle_update" claude_mnemos/cli_project.py
```

Find where it does `entry = store.get(name)` followed by HTTP PATCH. The pre-read is the TOCTOU; remove it.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_cli_project.py — append
def test_update_does_not_pre_read(monkeypatch, tmp_path):
    """_handle_update must build PATCH body purely from CLI args (no pre-GET)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))

    calls = []
    real_get = ProjectStore.get

    def spy_get(self, name):
        calls.append(name)
        return real_get(self, name)

    monkeypatch.setattr(ProjectStore, "get", spy_get)

    import httpx
    captured = {}
    def fake_patch(url, json, **kw):
        captured["json"] = json
        return httpx.Response(200, json={"name": "x", "vault_root": str(vault), "cwd_patterns": ["p"]})

    monkeypatch.setattr(httpx, "patch", fake_patch)

    from claude_mnemos.cli_project import _handle_update
    import argparse
    ns = argparse.Namespace(name="x", vault=None, cwd_pattern=["p"])
    _handle_update(ns)

    assert "x" not in calls  # no pre-read of the entry
    assert captured["json"] == {"cwd_patterns": ["p"]}
```

The exact command-builder code may differ; adapt the assertion to what the CLI sends. Goal: prove no `ProjectStore.get` is invoked before the HTTP call.

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Strip the pre-read**

In `_handle_update`, remove the `store.get(name)` (and any "before" print). Build the PATCH body purely from `args.vault` and `args.cwd_pattern` (None means unchanged). Emit the result to the user from the PATCH response.

- [ ] **Step 5: Run**

```
pytest tests/test_cli_project.py -v
```

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/cli_project.py tests/test_cli_project.py
git commit -m "fix(cli): cli_project._handle_update no pre-read (TOCTOU)"
```

---

## Task 24: CLI / MCP — replace hardcoded URLs with `daemon_base_url()`

**Files:**
- Find every occurrence:

```
grep -rn "127.0.0.1:5757" claude_mnemos
grep -rn "http://127.0.0.1" claude_mnemos
```

- Modify each call site
- Modify or add tests in `tests/test_cli*.py` and `tests/mcp/*.py` covering the indirection

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daemon_url.py — append
def test_cli_uses_daemon_base_url(monkeypatch, tmp_path):
    """When user pins daemon_port via global settings, CLI hits the new port."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from claude_mnemos.state.settings import GlobalSettings, SettingsStore
    SettingsStore().set_global(GlobalSettings(daemon_port=5800))

    captured = {}

    def fake_get(url, **kw):
        captured["url"] = url
        import httpx
        return httpx.Response(200, json={"projects": []})

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    from claude_mnemos.cli_project import _handle_list
    import argparse
    _handle_list(argparse.Namespace())
    assert captured["url"].startswith("http://127.0.0.1:5800")
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Update call sites**

Every CLI / MCP file that builds a daemon URL replaces:

```python
url = f"http://127.0.0.1:{port}/projects"
```

with:

```python
from claude_mnemos.daemon_url import daemon_base_url
url = f"{daemon_base_url()}/projects"
```

- [ ] **Step 4: Run**

```
pytest tests/test_daemon_url.py tests/test_cli*.py tests/mcp -v
```

- [ ] **Step 5: Verify no hardcodes remain**

```
grep -rn "127.0.0.1:5757" claude_mnemos
```

Should return zero matches outside of `daemon/config.py` (where `DEFAULT_HOST`/`DEFAULT_PORT` constants are defined).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos tests
git commit -m "refactor(cli,mcp): use daemon_base_url() instead of hardcoded :5757"
```

---

## Task 25: Subprocess integration tests — multivault lifecycle

**Files:**
- Create: `tests/daemon/integration/__init__.py`
- Create: `tests/daemon/integration/test_multivault_lifecycle.py`
- Create: `tests/daemon/integration/test_hot_mount_unmount.py`
- Create: `tests/daemon/integration/test_empty_project_map.py`
- Create: `tests/daemon/integration/test_hook_routing.py`

These tests boot a real `python -m claude_mnemos.daemon run` subprocess (mirrors α `tests/e2e/test_project_settings_e2e.py`). They are slow tests; mark with `@pytest.mark.slow`.

- [ ] **Step 1: Confirm an existing integration helper**

```
grep -rn "subprocess.Popen.*claude_mnemos.daemon" tests
```

If α has a fixture (e.g. `tests/e2e/conftest.py`) that spawns the daemon, reuse it. Otherwise lift its boot/health-check loop into `tests/daemon/integration/conftest.py`.

- [ ] **Step 2: Write integration test — multivault lifecycle**

```python
# tests/daemon/integration/test_multivault_lifecycle.py
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


@pytest.mark.slow
def test_two_vault_bootstrap(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    a = tmp_path / "alpha"; a.mkdir()
    b = tmp_path / "beta"; b.mkdir()
    ProjectStore().add(ProjectMapEntry(name="alpha", vault_root=a, cwd_patterns=[]))
    ProjectStore().add(ProjectMapEntry(name="beta", vault_root=b, cwd_patterns=[]))

    pid_file = tmp_path / "d.pid"
    proc = subprocess.Popen(
        [sys.executable, "-m", "claude_mnemos.daemon", "run",
         "--port", "5760", "--pid-file", str(pid_file), "--all"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                r = httpx.get("http://127.0.0.1:5760/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("daemon failed to start in time")

        # Both vaults' .jobs.db should exist.
        assert (a / ".jobs.db").is_file()
        assert (b / ".jobs.db").is_file()

        # /projects should list both.
        r = httpx.get("http://127.0.0.1:5760/projects")
        names = [p["name"] for p in r.json()["projects"]]
        assert set(names) == {"alpha", "beta"}
    finally:
        proc.terminate()
        proc.wait(timeout=5.0)
```

- [ ] **Step 3: Write integration test — hot mount/unmount**

```python
# tests/daemon/integration/test_hot_mount_unmount.py
@pytest.mark.slow
def test_hot_mount_then_post_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    pid_file = tmp_path / "d.pid"
    proc = subprocess.Popen(
        [sys.executable, "-m", "claude_mnemos.daemon", "run",
         "--port", "5761", "--pid-file", str(pid_file)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for /health.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                if httpx.get("http://127.0.0.1:5761/health", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)

        vault = tmp_path / "live"; vault.mkdir()
        r = httpx.post(
            "http://127.0.0.1:5761/projects",
            json={"name": "live", "vault_root": str(vault), "cwd_patterns": []},
            timeout=5.0,
        )
        assert r.status_code == 201

        transcript = vault / "t.jsonl"
        transcript.write_text("{}\n")
        r = httpx.post(
            "http://127.0.0.1:5761/jobs",
            json={
                "kind": "ingest",
                "payload": {"project_name": "live", "transcript_path": str(transcript)},
            },
            timeout=5.0,
        )
        assert r.status_code == 201
    finally:
        proc.terminate()
        proc.wait(timeout=5.0)
```

- [ ] **Step 4: Write integration test — empty project map**

```python
# tests/daemon/integration/test_empty_project_map.py
@pytest.mark.slow
def test_empty_bootstrap_serves_projects_returns_503_for_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    pid_file = tmp_path / "d.pid"
    proc = subprocess.Popen(
        [sys.executable, "-m", "claude_mnemos.daemon", "run",
         "--port", "5762", "--pid-file", str(pid_file)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                if httpx.get("http://127.0.0.1:5762/health", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)

        # Empty project map → /projects returns 200 with no entries
        r = httpx.get("http://127.0.0.1:5762/projects")
        assert r.status_code == 200
        assert r.json()["projects"] == []

        # /sessions should 503 because no primary vault.
        r = httpx.get("http://127.0.0.1:5762/snapshots")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "no_vault_registered"
    finally:
        proc.terminate()
        proc.wait(timeout=5.0)
```

- [ ] **Step 5: Write integration test — hook routing**

```python
# tests/daemon/integration/test_hook_routing.py
@pytest.mark.slow
def test_session_end_hook_routes_to_correct_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MNEMOS_INGEST_RUNNING", "")  # not in recursion

    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    a = tmp_path / "alpha"; a.mkdir()
    b = tmp_path / "beta"; b.mkdir()
    a_cwd = tmp_path / "src" / "alpha"; a_cwd.mkdir(parents=True)
    b_cwd = tmp_path / "src" / "beta"; b_cwd.mkdir(parents=True)
    ProjectStore().add(ProjectMapEntry(
        name="alpha", vault_root=a, cwd_patterns=[str(a_cwd) + "/**"],
    ))
    ProjectStore().add(ProjectMapEntry(
        name="beta", vault_root=b, cwd_patterns=[str(b_cwd) + "/**"],
    ))

    pid_file = tmp_path / "d.pid"
    proc = subprocess.Popen(
        [sys.executable, "-m", "claude_mnemos.daemon", "run",
         "--port", "5763", "--pid-file", str(pid_file), "--all"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                if httpx.get("http://127.0.0.1:5763/health", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)

        # Simulate hook from beta's cwd.
        from hooks.session_end import on_session_end
        transcript = b / "t.jsonl"; transcript.write_text("{}\n")
        on_session_end(
            cwd=b_cwd,
            transcript_path=transcript,
            daemon_url="http://127.0.0.1:5763",
        )

        # Wait briefly for the job to appear in beta's store, NOT alpha's.
        time.sleep(0.5)
        from claude_mnemos.state.jobs import JobStore
        a_store = JobStore(a / ".jobs.db")
        b_store = JobStore(b / ".jobs.db")
        try:
            assert sum(b_store.count_by_status().values()) >= 1
            assert sum(a_store.count_by_status().values()) == 0
        finally:
            a_store.close()
            b_store.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5.0)
```

(If `on_session_end` doesn't take a `daemon_url=` argument today, expose one or have the test set `MNEMOS_DAEMON_PORT=5763` env var and call the hook entrypoint via `subprocess.run`.)

- [ ] **Step 6: Run all integration tests**

```
pytest tests/daemon/integration -v -m slow
```

- [ ] **Step 7: Commit**

```bash
git add tests/daemon/integration/
git commit -m "test(integration): multi-vault bootstrap, hot mount/unmount, empty map, hook routing"
```

---

## Task 26: Final verification — full test suite + ruff + mypy + grep clean-up

**Files:**
- All

- [ ] **Step 1: Run the fast suite**

```
pytest -q -x --ignore=tests/daemon/integration -k "not slow"
```

Target: ~1100+ passed, 1 skipped (`test_real_extraction` without API key), 1 deselected (the pre-existing flaky `test_usage_timeline`).

- [ ] **Step 2: Run the slow suite**

```
pytest -q -x -m slow
```

Target: ~14+ passed (including the new 4 integration tests).

- [ ] **Step 3: Run ruff + mypy**

```
ruff check claude_mnemos tests
mypy --strict claude_mnemos
```

Both must report zero issues.

- [ ] **Step 4: Verify hard-cuts**

```
grep -rn "MNEMOS_VAULT_ROOT" claude_mnemos
grep -rn "127.0.0.1:5757" claude_mnemos
grep -rn "build_scheduler\b" claude_mnemos
grep -rn "vault_root: Path$" claude_mnemos/daemon/config.py claude_mnemos/daemon/runtime_state.py
```

Expected:
- First: 0 matches.
- Second: 0 matches outside of `daemon/config.py` (constant).
- Third: 0 matches outside of legacy comment / removed file.
- Fourth: 0 matches.

- [ ] **Step 5: Verify acceptance criteria**

Walk through §15 of the design doc; check each box manually:

1. `MnemosDaemon` no longer takes `vault_root`. ✓ via `tests/daemon/test_config.py`.
2. `mnemos daemon start` mounts everything. ✓ via `tests/daemon/integration/test_multivault_lifecycle.py`.
3. `--project A,B`. ✓ via `tests/test_cli_daemon_multivault.py`.
4. POST /projects + POST /jobs without restart. ✓ via `tests/daemon/integration/test_hot_mount_unmount.py`.
5. DELETE busy → 409, force → drain. ✓ via `tests/daemon/test_routes_projects_hotmount.py`.
6. PATCH new vault_root remounts. ✓ via same.
7. Empty bootstrap. ✓ via `tests/daemon/integration/test_empty_project_map.py`.
8. Two hooks → two stores. ✓ via `tests/daemon/integration/test_hook_routing.py`.
9. Cron jobs `:<name>` suffixed. ✓ via `tests/daemon/test_vault_runtime.py`.
10. cli_project no pre-read. ✓ via `tests/test_cli_project.py`.
11. CLI/MCP `daemon_base_url()`. ✓ via `tests/test_daemon_url.py`.
12. `_runtimes_lock` covers mutations. ✓ visible in `process.py`.
13. Test suite green. ✓ via Step 1+2.
14. No regression of α functionality. ✓ via the existing α test suite still green.

- [ ] **Step 6: Final commit if anything dangling, otherwise just verify clean**

```
git status
```

Should be clean.

- [ ] **Step 7: Branch summary**

```
git log --oneline main..HEAD
```

Should show ~26 focused commits. No merges to main yet — that happens in `finishing-a-development-branch`.

---

## Spec coverage map

| Design §   | Plan task(s) |
|------------|--------------|
| 1.1 (background) | n/a (intro) |
| 1.2 (goal) | All tasks contribute |
| 1.3 (non-goals β2) | Documented out-of-scope; no tasks here |
| 1.4 (spec alignment) | Tasks 6-9 (VaultRuntime), 12-16 (Daemon), 18 (POST /projects), 25 (integration) |
| 2.1 (component map) | Tasks 6-16 |
| 2.2 (per-vault vs shared) | Task 6 (VaultRuntime owns per-vault), Task 12 (daemon owns shared) |
| 2.3 (cron job IDs) | Tasks 7, 9, 14 |
| 2.4 (primary vault) | Tasks 1 (`primary_project`), 12 (`_recompute_primary`), 17 (`_vault` 503), 19 (PATCH /settings/global re-pick) |
| 3 (`VaultRuntime`) | Tasks 6-9 |
| 4 (`MnemosDaemon` orchestration) | Tasks 12-16 |
| 5 (Bootstrap CLI) | Tasks 10, 21, 22 |
| 6.1 (`/jobs` POST routing) | Task 20 |
| 6.2 (`cancel_all_queued`) | Task 3 |
| 6.3 (`/jobs` GET/DELETE primary) | Task 20 |
| 6.4 (other routes touching vault) | Task 17 |
| 7.1 (POST /projects) | Task 18 |
| 7.2 (DELETE /projects) | Task 18 |
| 7.3 (PATCH /projects) | Task 18 |
| 7.4 (PATCH /settings) | Task 19 |
| 7.5 (`_vault` helper update) | Task 17 |
| 8.1 (TOCTOU fix) | Task 23 |
| 8.2 (reload_settings thread-safety) | Tasks 12, 15 (`_runtimes_lock` documented) |
| 8.3 (CLI/MCP daemon URL) | Tasks 2, 24 |
| 9 (Migration & backcompat) | Tasks 11, 22 (legacy `--vault` hard error), 25 (E2E) |
| 10 (Testing strategy) | Tasks 6-25 (per-task TDD) + Task 25 (integration) |
| 11 (File-level summary) | All — covered by Files map at top of plan |
| 12 (Risks/rollback) | n/a (operational concern) |
| 13 (Open questions resolved) | n/a (decisions baked in) |
| 14 (Out of scope) | n/a (β2) |
| 15 (Acceptance criteria) | Task 26 step 5 |

No uncovered spec requirements.
