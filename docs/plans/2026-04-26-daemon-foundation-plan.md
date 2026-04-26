# Daemon Foundation Implementation Plan (Plan #5)

> **For agentic workers:** Use TDD at every step. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** First working `mnemos-daemon` — FastAPI on `127.0.0.1:5757` + APScheduler with daily snapshot + 180-day backups cleanup + REST API for activity/snapshots/undo. CLI `mnemos daemon {start,stop,status,foreground}`.

**Architecture:** See design doc `docs/plans/2026-04-26-daemon-foundation-design.md`.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, APScheduler, psutil, httpx (test+CLI client), pytest-asyncio.

---

## Что НЕ делаем в этом плане

См. §2.2 design doc'а — MCP server (Plan #6), Claude Code hooks (Plan #7), Frontend dashboard (Plan #8), Watchdog real-time (Plan #9+), multi-vault routing, ingest endpoints, jobs/dead-letter/alerts/metrics, auth.

---

## Files map

**Создаём:**

| Файл | Ответственность |
|---|---|
| `claude_mnemos/daemon/__init__.py` | re-export `create_app`, `MnemosDaemon` |
| `claude_mnemos/daemon/__main__.py` | `python -m claude_mnemos.daemon` entry |
| `claude_mnemos/daemon/config.py` | `DaemonConfig` Pydantic |
| `claude_mnemos/daemon/lockfile.py` | `is_daemon_running`, `write_pid_file`, `cleanup_pid_file` |
| `claude_mnemos/daemon/schemas.py` | `HealthResponse`, `VaultInfo`, `SnapshotInfo`, `UndoApiResult`, `SchedulerJobInfo` |
| `claude_mnemos/daemon/app.py` | `create_app(vault_root, daemon=None)` |
| `claude_mnemos/daemon/process.py` | `MnemosDaemon` lifecycle |
| `claude_mnemos/daemon/scheduler.py` | `attach_scheduler(daemon)` |
| `claude_mnemos/daemon/tasks/__init__.py` | re-export tasks |
| `claude_mnemos/daemon/tasks/daily_snapshot.py` | `daily_snapshot_task` |
| `claude_mnemos/daemon/tasks/backups_cleanup.py` | `backups_cleanup_task` |
| `claude_mnemos/daemon/routes/__init__.py` | router exports |
| `claude_mnemos/daemon/routes/health.py` | `/health`, `/version` |
| `claude_mnemos/daemon/routes/vault.py` | `/vault/info` |
| `claude_mnemos/daemon/routes/activity.py` | `/activity*` |
| `claude_mnemos/daemon/routes/snapshots.py` | `/snapshots*` |
| `tests/daemon/__init__.py` | |
| `tests/daemon/test_lockfile.py` | |
| `tests/daemon/test_config.py` | |
| `tests/daemon/test_schemas.py` | |
| `tests/daemon/test_app_health.py` | health/version routes |
| `tests/daemon/test_app_vault.py` | vault info route |
| `tests/daemon/test_app_activity.py` | activity routes |
| `tests/daemon/test_app_snapshots.py` | snapshots routes |
| `tests/daemon/test_tasks.py` | daily_snapshot + backups_cleanup |
| `tests/daemon/test_scheduler.py` | scheduler wiring |
| `tests/daemon/test_process_subprocess.py` | E2E start/stop subprocess (slow marker) |
| `tests/daemon/test_cli_daemon.py` | CLI `mnemos daemon` subcommands |

**Изменяем:**

| Файл | Что |
|---|---|
| `pyproject.toml` | deps: `fastapi`, `uvicorn[standard]`, `apscheduler`, `psutil`, `httpx`, `pytest-asyncio` (dev). pytest-asyncio mode auto. |
| `claude_mnemos/__init__.py` | Добавить `__version__ = "0.0.1"` если нет |
| `claude_mnemos/core/snapshots.py` | Добавить `compute_daily_snapshot_path`, `compute_manual_snapshot_path`, `create_daily_snapshot`, `create_manual_snapshot`, `list_snapshots`, `delete_snapshot`, `prune_old_backups` + dataclass `PruneResult`, helper `parse_snapshot_name` |
| `tests/test_snapshots.py` | Тесты под новые функции |
| `claude_mnemos/cli.py` | Subcommands `daemon {start,stop,status,foreground}` + exit codes 78/79/80 |
| `tests/test_cli.py` | (тесты daemon CLI идут в отдельный файл `tests/daemon/test_cli_daemon.py`) |

---

## Зависимости между задачами

```
Task 1: pyproject deps + branch
    ↓
Task 2: snapshots extensions + helper parse_snapshot_name
    ↓
Task 3: daemon/config + schemas (data layer, no app)
    ↓
Task 4: daemon/lockfile (PID file, psutil)
    ↓
Task 5: routes/health + create_app skeleton
    ↓
Task 6: routes/vault
    ↓
Task 7: routes/activity (list, get, undo)
    ↓
Task 8: routes/snapshots (list, create, restore, delete)
    ↓
Task 9: tasks/daily_snapshot + tasks/backups_cleanup
    ↓
Task 10: scheduler.attach_scheduler
    ↓
Task 11: process.MnemosDaemon (lifecycle + signal handlers)
    ↓
Task 12: __main__.py + CLI daemon subcommands (start/stop/status/foreground)
    ↓
Task 13: E2E subprocess test + manual smoke + final verification + merge
```

---

## Task 1: Setup — branch + dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/daemon-foundation
```

- [ ] **Step 2: Edit `pyproject.toml`**

Add to `dependencies`: `"fastapi>=0.115"`, `"uvicorn[standard]>=0.30"`, `"apscheduler>=3.10"`, `"psutil>=5.9"`, `"httpx>=0.27"`.

Add to `dev`: `"pytest-asyncio>=0.24"`.

Add to `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`.

Add `[[tool.mypy.overrides]]` for `apscheduler.*` (`ignore_missing_imports = true`) and `psutil` (same).

- [ ] **Step 3: Install + sanity check**

```bash
pip install -e .[dev]
python -c "import fastapi, uvicorn, apscheduler, psutil, httpx; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Run baseline tests**

```bash
pytest -q
```

Expected: 193 passed + 1 skipped (no regressions).

- [ ] **Step 5: Commit**

```
chore: add daemon dependencies (fastapi, uvicorn, apscheduler, psutil, httpx, pytest-asyncio)
```

---

## Task 2: Snapshot module extensions

**Files:**
- Modify: `claude_mnemos/core/snapshots.py`
- Modify: `tests/test_snapshots.py`

**Why:** Daemon scheduler tasks нужны `create_daily_snapshot`, `prune_old_backups`. REST snapshots router нужны `list_snapshots`, `delete_snapshot`, `create_manual_snapshot`. Все share helper `parse_snapshot_name(name) -> ParsedSnapshot | None`.

- [ ] **Step 1: Failing tests for `parse_snapshot_name`**

Test cases:
- `pre-op-2026-04-26-14-30-00-ingest_extracted-abc123` → kind=pre-op, ts, op_type=ingest_extracted, op_id=abc123
- `daily-2026-04-26` → kind=daily, ts at midnight UTC
- `manual-2026-04-26-14-30-00` → kind=manual, ts, label=None
- `manual-2026-04-26-14-30-00-pre-release` → kind=manual, label="pre-release"
- `random-junk` → None
- `pre-op-malformed` → None

- [ ] **Step 2: Failing tests for `compute_daily_snapshot_path` + `compute_manual_snapshot_path`**

- daily: `<vault>/.backups/daily-2026-04-26`
- manual без label: `<vault>/.backups/manual-2026-04-26-14-30-00`
- manual с label "release-1": `<vault>/.backups/manual-2026-04-26-14-30-00-release-1`
- manual label sanitization (slashes/spaces → dashes; reject empty after sanitize)

- [ ] **Step 3: Failing tests for `create_daily_snapshot` + `create_manual_snapshot`**

- `create_daily_snapshot(vault, date(2026,4,26))` создаёт `<vault>/.backups/daily-2026-04-26/` с meta.json
- Повторный вызов того же дня — no-op, возвращает существующий path (idempotent)
- `create_manual_snapshot(vault, label="x")` — путь содержит "manual-" prefix и label, op_type="manual"

- [ ] **Step 4: Failing tests for `list_snapshots`**

- Empty `.backups/` → `[]`
- 3 snapshots (pre-op, daily, manual) → 3 SnapshotInfo с правильными kind/timestamp
- Junk dir `random-stuff` → пропущен (warning logged)
- Sort: newest first

- [ ] **Step 5: Failing tests for `delete_snapshot`**

- Existing snapshot → удалён
- Name with `..` → ValueError
- Absolute path → ValueError
- Name without known prefix → ValueError ("not a snapshot")
- Missing snapshot → FileNotFoundError

- [ ] **Step 6: Failing tests for `prune_old_backups`**

- `today=2026-04-26`, retention=180:
  - `pre-op-2025-09-01-...` (>180 days) → pruned
  - `pre-op-2026-04-25-...` (1 day) → kept
  - `daily-2025-09-01` → pruned
  - `daily-2026-04-26` → kept
  - `manual-...` старый → pruned
  - junk dir → kept (skipped, не удаляем что не наше)
- Returns `PruneResult(pruned=[names], kept=N, errors=[])`
- Mocked rmtree failure → попадает в `errors`

- [ ] **Step 7: Implementation**

Реализуй по design §5. Ключи:
- `parse_snapshot_name` через regex для трёх prefix.
- `compute_daily_snapshot_path(vault, today: date)` — `daily-{today.isoformat()}`.
- `create_daily_snapshot` — idempotent через `.exists()` check.
- `create_manual_snapshot` — `_timestamp()` из существующего helper'а.
- `list_snapshots` — `iterdir()`, filter по `is_dir()`, parse name, sort.
- `delete_snapshot` — path safety + rmtree.
- `prune_old_backups` — iterate, parse, compare с `today - timedelta(days=retention)`.

`SnapshotInfo` — Pydantic модель, **не** в `daemon/schemas.py`, а здесь — потому что core ownership. Daemon её re-export.

- [ ] **Step 8: Run tests**

```bash
pytest tests/test_snapshots.py -v
```

Expected: all green.

- [ ] **Step 9: Lint + mypy**

```bash
ruff check claude_mnemos/core/snapshots.py tests/test_snapshots.py
mypy claude_mnemos/core/snapshots.py
```

- [ ] **Step 10: Commit**

```
feat(core): snapshot listing, manual/daily kinds, retention pruning
```

---

## Task 3: Daemon config + schemas

**Files:**
- Create: `claude_mnemos/daemon/__init__.py` (empty stub)
- Create: `claude_mnemos/daemon/config.py`
- Create: `claude_mnemos/daemon/schemas.py`
- Create: `tests/daemon/__init__.py`
- Create: `tests/daemon/test_config.py`
- Create: `tests/daemon/test_schemas.py`

**Why:** Pydantic модели на которые опираются routes и process. Никаких runtime зависимостей на FastAPI пока — pure data.

- [ ] **Step 1: Failing tests `DaemonConfig`**

- Default port 5757, host "127.0.0.1", retention_days 180
- `from_env(vault_root)` подбирает MNEMOS_DAEMON_PORT, MNEMOS_DAEMON_HOST, MNEMOS_RETENTION_DAYS, MNEMOS_DAEMON_LOG, MNEMOS_DAEMON_PID
- Invalid port (0, 70000) → ValidationError
- retention_days < 1 → ValidationError

- [ ] **Step 2: Failing tests `schemas.py`**

- `HealthResponse(status="ok", version="0.0.1", vault="...", uptime_s=1.5, scheduler_jobs=[])` валиден
- `SchedulerJobInfo(id="x", next_run_time=None, trigger="cron")` валиден
- `VaultInfo(...)` валиден с counts
- `UndoApiResult(success=True, op_id="x", restored_pages=[], new_entry_id=None)` валиден

- [ ] **Step 3: Implementation**

```python
# config.py
class DaemonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vault_root: Path
    host: str = "127.0.0.1"
    port: int = Field(default=5757, ge=1, le=65535)
    retention_days: int = Field(default=180, ge=1)
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    pid_file: Path = Field(
        default_factory=lambda: Path.home() / ".mnemos" / "daemon.pid"
    )

    @classmethod
    def from_env(cls, vault_root: Path) -> "DaemonConfig":
        return cls(
            vault_root=vault_root,
            host=os.environ.get("MNEMOS_DAEMON_HOST", "127.0.0.1"),
            port=int(os.environ.get("MNEMOS_DAEMON_PORT", "5757")),
            retention_days=int(os.environ.get("MNEMOS_RETENTION_DAYS", "180")),
            log_level=os.environ.get("MNEMOS_DAEMON_LOG", "info"),  # type: ignore[arg-type]
            pid_file=Path(
                os.environ.get(
                    "MNEMOS_DAEMON_PID",
                    str(Path.home() / ".mnemos" / "daemon.pid"),
                )
            ),
        )
```

```python
# schemas.py — see design §4
```

`SnapshotInfo` re-export из `core.snapshots`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/daemon/test_config.py tests/daemon/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```
feat(daemon): config + response schemas
```

---

## Task 4: Daemon lockfile

**Files:**
- Create: `claude_mnemos/daemon/lockfile.py`
- Create: `tests/daemon/test_lockfile.py`

- [ ] **Step 1: Failing tests**

Use `monkeypatch` для psutil:
- PID file отсутствует → `is_daemon_running()` returns None
- PID file invalid content → returns None + file deleted
- psutil.pid_exists returns False → returns None + file deleted
- psutil.pid_exists True но Process(pid).cmdline() без "mnemos-daemon" → returns None + file deleted
- All checks pass → returns pid (int)
- psutil.NoSuchProcess raised → returns None + file deleted

- `write_pid_file(pid_path, pid)` создаёт файл с pid (parent dir auto-create)
- `cleanup_pid_file(pid_path)` удаляет файл (idempotent — missing OK)

- [ ] **Step 2: Implementation**

```python
DAEMON_CMDLINE_MARKER = "claude_mnemos.daemon"

def is_daemon_running(pid_file: Path) -> int | None:
    if not pid_file.is_file():
        return None
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        cleanup_pid_file(pid_file)
        return None
    if not psutil.pid_exists(pid):
        cleanup_pid_file(pid_file)
        return None
    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline())
        if DAEMON_CMDLINE_MARKER not in cmdline:
            cleanup_pid_file(pid_file)
            return None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        cleanup_pid_file(pid_file)
        return None
    return pid

def write_pid_file(pid_file: Path, pid: int) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid), encoding="utf-8")

def cleanup_pid_file(pid_file: Path) -> None:
    pid_file.unlink(missing_ok=True)
```

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```
feat(daemon): PID lockfile with stale recovery via psutil cmdline check
```

---

## Task 5: routes/health + create_app skeleton

**Files:**
- Create: `claude_mnemos/daemon/routes/__init__.py`
- Create: `claude_mnemos/daemon/routes/health.py`
- Create: `claude_mnemos/daemon/app.py`
- Create: `tests/daemon/test_app_health.py`
- Modify: `claude_mnemos/__init__.py` (add `__version__`)

- [ ] **Step 1: Failing tests**

```python
import httpx
from httpx import ASGITransport
from claude_mnemos.daemon.app import create_app

@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, daemon=None)

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

async def test_health_returns_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

async def test_health_includes_version_and_vault(client, tmp_path):
    r = await client.get("/health")
    body = r.json()
    assert body["version"]  # non-empty
    assert body["vault"] == str(tmp_path)
    assert "uptime_s" in body
    assert body["scheduler_jobs"] == []  # daemon=None

async def test_version_endpoint(client):
    r = await client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert "python_version" in body
```

- [ ] **Step 2: Implementation**

`__init__.py`: `__version__ = "0.0.1"`.

`routes/health.py`:
```python
import platform
import sys
import time
from fastapi import APIRouter, Request
from claude_mnemos import __version__
from claude_mnemos.daemon.schemas import HealthResponse, SchedulerJobInfo

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    daemon = request.app.state.daemon
    uptime_s = 0.0
    jobs: list[SchedulerJobInfo] = []
    if daemon is not None:
        uptime_s = time.monotonic() - daemon.started_at_monotonic
        jobs = daemon.scheduler_jobs_info()
    return HealthResponse(
        status="ok",
        version=__version__,
        vault=str(request.app.state.vault_root),
        uptime_s=uptime_s,
        scheduler_jobs=jobs,
    )

@router.get("/version")
async def version() -> dict[str, str]:
    return {
        "version": __version__,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }
```

`app.py`:
```python
from fastapi import FastAPI
from pathlib import Path
from claude_mnemos.daemon.routes.health import router as health_router

def create_app(vault_root: Path, daemon: object | None = None) -> FastAPI:
    app = FastAPI(title="claude-mnemos daemon")
    app.state.vault_root = vault_root
    app.state.daemon = daemon
    app.include_router(health_router)
    return app
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/daemon/test_app_health.py -v
```

- [ ] **Step 4: Commit**

```
feat(daemon): FastAPI app skeleton with /health and /version
```

---

## Task 6: routes/vault

**Files:**
- Create: `claude_mnemos/daemon/routes/vault.py`
- Create: `tests/daemon/test_app_vault.py`
- Modify: `claude_mnemos/daemon/app.py` (include router)

- [ ] **Step 1: Failing tests**

- Empty vault → counts всё нули
- Vault с известными fixture (1 manifest entry, 2 wiki, 1 raw) → корректные counts
- Corrupt `.activity.json` → 503 `{error: "activity_corrupt"}`
- Corrupt `.manifest.json` → 503 `{error: "manifest_corrupt"}`

- [ ] **Step 2: Implementation**

```python
@router.get("/vault/info", response_model=VaultInfo)
def vault_info(request: Request) -> VaultInfo:
    vault: Path = request.app.state.vault_root
    activity = ActivityLog.load(vault)
    manifest = Manifest.load(vault)
    raw_chats = sum(1 for _ in (vault / "raw" / "chats").glob("*.md")) if (vault / "raw" / "chats").exists() else 0
    wiki_pages = sum(1 for _ in (vault / "wiki").rglob("*.md")) if (vault / "wiki").exists() else 0
    snapshots = len(list_snapshots(vault))
    return VaultInfo(
        vault=str(vault),
        raw_chats=raw_chats,
        wiki_pages=wiki_pages,
        manifest_processed=len(manifest.entries),  # adjust to actual field name
        activity_entries=len(activity.entries),
        snapshots=snapshots,
        total_size_bytes=_compute_size(vault),
    )
```

`def` (sync) — Manifest.load и list_snapshots блокирующие. Starlette уйдёт в threadpool.

Исключения `ActivityCorruptError` / `ManifestCorruptError` ловятся exception handlers в `create_app`. Добавить их в Task 5/6 boundary — обновить `app.py`.

- [ ] **Step 3: Tests pass + lint**

- [ ] **Step 4: Commit**

```
feat(daemon): /vault/info endpoint with corrupt-state error handlers
```

---

## Task 7: routes/activity

**Files:**
- Create: `claude_mnemos/daemon/routes/activity.py`
- Create: `tests/daemon/test_app_activity.py`
- Modify: `app.py` (include + exception handlers `UndoError`, `LockTimeoutError`)

- [ ] **Step 1: Failing tests**

- `GET /activity` empty vault → `{entries:[], total:0}`
- `GET /activity?limit=5&offset=10` slicing
- `GET /activity/{id}` known id → 200 + entry
- `GET /activity/{id}` unknown id → 404
- `POST /activity/{id}/undo` known undoable → 200 + UndoApiResult, vault rolled back, manual_restore appended
- `POST /activity/{id}/undo` already undone → 409
- `POST /activity/{id}/undo` snapshot missing → 409
- `POST /activity/{id}/undo` ambiguous behavior NOT applicable (REST принимает full id, не prefix — упрощение)

- [ ] **Step 2: Implementation**

```python
@router.get("/activity")
async def list_activity(request: Request, limit: int = 20, offset: int = 0) -> dict:
    vault = request.app.state.vault_root
    log = ActivityLog.load(vault)
    entries = list(reversed(log.entries))  # newest first
    sliced = entries[offset : offset + limit] if limit > 0 else entries[offset:]
    return {"entries": [e.model_dump(mode="json") for e in sliced], "total": len(entries)}

@router.get("/activity/{op_id}", response_model=ActivityEntry)
async def get_activity(op_id: str, request: Request) -> ActivityEntry:
    vault = request.app.state.vault_root
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    if entry is None:
        raise HTTPException(404, detail={"error": "not_found", "id": op_id})
    return entry

@router.post("/activity/{op_id}/undo", response_model=UndoApiResult)
def undo_activity(op_id: str, request: Request) -> UndoApiResult:
    vault = request.app.state.vault_root
    result = undo(vault, op_id)  # raises UndoError / LockTimeoutError → handled globally
    return UndoApiResult(
        success=result.success,
        op_id=op_id,
        restored_pages=list(result.restored_pages),
        new_entry_id=result.new_entry_id,
    )
```

- [ ] **Step 3: Tests + commit**

```
feat(daemon): /activity REST endpoints with undo through core.undo
```

---

## Task 8: routes/snapshots

**Files:**
- Create: `claude_mnemos/daemon/routes/snapshots.py`
- Create: `tests/daemon/test_app_snapshots.py`
- Modify: `app.py` (include)

- [ ] **Step 1: Failing tests**

- `GET /snapshots` пустой → `{snapshots:[]}`
- `GET /snapshots` 3 snapshots → newest first
- `POST /snapshots` body `{}` → создаёт manual без label, returns SnapshotInfo
- `POST /snapshots` body `{"label":"release"}` → label в имени
- `POST /snapshots` body `{"label":"../etc"}` → 400 invalid_name
- `POST /snapshots/{name}/restore` known → vault rolled back + activity manual_restore appended + 200
- `POST /snapshots/{name}/restore` missing → 404
- `POST /snapshots/{name}/restore` traversal → 400
- `DELETE /snapshots/{name}` known → 200 + dir gone
- `DELETE /snapshots/{name}` missing → 404
- `DELETE /snapshots/{name}` traversal → 400

- [ ] **Step 2: Implementation**

`POST /snapshots/{name}/restore` берёт `pipeline_lock`, зовёт `restore_from_snapshot`, потом отдельно append'ит manual_restore entry в activity (через `atomic_write` напрямую, по аналогии с undo). Использовать существующий код — выделить helper в `core/undo.py` или inline здесь? **Решение:** добавить `core.snapshots.restore_with_activity_log(vault, snapshot_path) -> RestoreResult` — это новый helper над restore_from_snapshot который пишет manual_restore activity entry. Используется и здесь, и в Task 12 (если CLI добавит manual restore — пока не делаем).

Альтернатива: дублировать логику. Не хочу. Пишу helper.

Wait — undo() в plan #4 уже делает это. Может вызывать undo()? Нет — undo принимает op_id, а тут snapshot_name. Нужен новый helper. Поднимаем общую часть.

**Решение упрощённое:** helper в `core/undo.py` — `_append_manual_restore_entry(vault, restored_op_id_or_none, restored_pages, snapshot_path) -> str (new entry id)`. Использует обоими.

- [ ] **Step 3: Tests + commit**

```
feat(daemon): /snapshots REST endpoints with path-traversal protection
```

---

## Task 9: scheduler tasks

**Files:**
- Create: `claude_mnemos/daemon/tasks/__init__.py`
- Create: `claude_mnemos/daemon/tasks/daily_snapshot.py`
- Create: `claude_mnemos/daemon/tasks/backups_cleanup.py`
- Create: `tests/daemon/test_tasks.py`

- [ ] **Step 1: Failing tests `daily_snapshot_task`**

- Создаёт `<vault>/.backups/daily-<today>` через `create_daily_snapshot`
- Идемпотентно (повторный вызов в тот же день — no-op)
- Под `pipeline_lock` — если lock занят (mock), task возвращает без crash, логирует warning

- [ ] **Step 2: Failing tests `backups_cleanup_task`**

- Удаляет старые snapshots (mock today)
- Возвращает PruneResult counts
- Под pipeline_lock — graceful skip on timeout

- [ ] **Step 3: Implementation**

```python
# daily_snapshot.py
import logging
from datetime import date
from pathlib import Path
from claude_mnemos.core.locks import pipeline_lock, LockTimeoutError
from claude_mnemos.core.snapshots import create_daily_snapshot

logger = logging.getLogger(__name__)

def daily_snapshot_task(vault: Path, today: date | None = None) -> Path | None:
    today = today or date.today()
    try:
        with pipeline_lock(vault, timeout=30.0):
            return create_daily_snapshot(vault, today)
    except LockTimeoutError:
        logger.warning("daily_snapshot: pipeline busy, skipping")
        return None
    except Exception:
        logger.exception("daily_snapshot failed")
        return None
```

```python
# backups_cleanup.py
def backups_cleanup_task(vault: Path, retention_days: int, today: date | None = None) -> PruneResult | None:
    today = today or date.today()
    try:
        with pipeline_lock(vault, timeout=30.0):
            return prune_old_backups(vault, retention_days, today)
    except LockTimeoutError:
        logger.warning("backups_cleanup: pipeline busy, skipping")
        return None
    except Exception:
        logger.exception("backups_cleanup failed")
        return None
```

- [ ] **Step 4: Tests + commit**

```
feat(daemon): scheduler tasks (daily_snapshot, backups_cleanup) under pipeline_lock
```

---

## Task 10: scheduler wiring

**Files:**
- Create: `claude_mnemos/daemon/scheduler.py`
- Create: `tests/daemon/test_scheduler.py`

- [ ] **Step 1: Failing test**

- `attach_scheduler(vault, retention_days)` returns AsyncIOScheduler с двумя jobs (`daily_snapshot`, `backups_cleanup`)
- Job `daily_snapshot` next_run_time hour=4 minute=0
- Job `backups_cleanup` next_run_time hour=5 minute=0
- Replace existing jobs allowed

- [ ] **Step 2: Implementation**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from claude_mnemos.daemon.tasks import daily_snapshot_task, backups_cleanup_task

def build_scheduler(vault: Path, retention_days: int, *, timezone: str = "UTC") -> AsyncIOScheduler:
    sch = AsyncIOScheduler(timezone=timezone)
    sch.add_job(
        daily_snapshot_task, "cron", hour=4, minute=0,
        args=[vault], id="daily_snapshot", replace_existing=True,
    )
    sch.add_job(
        backups_cleanup_task, "cron", hour=5, minute=0,
        args=[vault, retention_days], id="backups_cleanup", replace_existing=True,
    )
    return sch
```

- [ ] **Step 3: Tests + commit**

```
feat(daemon): APScheduler wiring with daily_snapshot 04:00 + backups_cleanup 05:00 UTC
```

---

## Task 11: process.MnemosDaemon

**Files:**
- Create: `claude_mnemos/daemon/process.py`
- Test: directly tested via subprocess in Task 13 (start/stop fully integration); unit-test scheduler_jobs_info() and started_at_monotonic via mock

- [ ] **Step 1: Failing tests (limited unit coverage)**

- `MnemosDaemon(config).scheduler_jobs_info()` returns SchedulerJobInfo list when scheduler attached
- `started_at_monotonic` set when `run()` called (mock уvicorn server)

- [ ] **Step 2: Implementation skeleton**

```python
import asyncio
import signal
import time
import uvicorn
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.lockfile import write_pid_file, cleanup_pid_file
from claude_mnemos.daemon.scheduler import build_scheduler
from claude_mnemos.daemon.schemas import SchedulerJobInfo

class MnemosDaemon:
    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.scheduler = build_scheduler(config.vault_root, config.retention_days)
        self.app = create_app(config.vault_root, daemon=self)
        self.started_at_monotonic = 0.0
        self._server: uvicorn.Server | None = None

    def scheduler_jobs_info(self) -> list[SchedulerJobInfo]:
        return [
            SchedulerJobInfo(
                id=j.id,
                next_run_time=j.next_run_time,
                trigger=str(j.trigger),
            )
            for j in self.scheduler.get_jobs()
        ]

    async def run(self) -> None:
        write_pid_file(self.config.pid_file, os.getpid())
        self.started_at_monotonic = time.monotonic()
        try:
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
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                pass
            cleanup_pid_file(self.config.pid_file)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except NotImplementedError:
                # Windows: add_signal_handler not supported on ProactorEventLoop
                signal.signal(sig, lambda *_: self._request_shutdown())

    def _request_shutdown(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
```

- [ ] **Step 3: Commit**

```
feat(daemon): MnemosDaemon process lifecycle with PID file + signal handlers
```

---

## Task 12: __main__ + CLI subcommands

**Files:**
- Create: `claude_mnemos/daemon/__main__.py`
- Modify: `claude_mnemos/cli.py`
- Create: `tests/daemon/test_cli_daemon.py`

**CLI subcommands:**

```
mnemos daemon start [--vault PATH] [--port N] [--host H] [--retention-days N] [--log-level L]
mnemos daemon foreground [--vault PATH] [--port N] ...
mnemos daemon stop [--timeout N]
mnemos daemon status
```

`python -m claude_mnemos.daemon` — alias for `mnemos daemon foreground` semantics; used internally by `start` to spawn detached child.

`__main__.py` invocation chain (used by `daemon start` subprocess spawn):

```bash
python -m claude_mnemos.daemon run --vault PATH --port N --host H --retention-days N --log-level L --pid-file P
```

- [ ] **Step 1: Failing tests for CLI**

Используем subprocess + httpx polling (slow marker):
- `mnemos daemon status` без бегущего → exit 1, stderr "stopped"
- `mnemos daemon start --vault tmp` → success, поднимается, status показывает pid+port+vault
- `mnemos daemon start` второй раз → exit 78
- `mnemos daemon stop` → terminates, status → stopped
- `mnemos daemon stop` без бегущего → exit 0

В CI эти тесты будут медленные (subprocess + polling). Помечаем `@pytest.mark.slow`.

Не-slow юнит тесты:
- argparse правильно парсит flags
- `_cmd_daemon_status` без daemon — печатает "stopped" exit 1
- `_cmd_daemon_status` с daemon — печатает JSON

- [ ] **Step 2: Implementation `__main__.py`**

```python
import argparse
import asyncio
import sys
from pathlib import Path
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claude_mnemos.daemon")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--vault", type=Path, required=True)
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=5757)
    run.add_argument("--retention-days", type=int, default=180)
    run.add_argument("--log-level", default="info")
    run.add_argument("--pid-file", type=Path, default=Path.home() / ".mnemos" / "daemon.pid")
    args = parser.parse_args(argv)

    if args.cmd == "run":
        config = DaemonConfig(
            vault_root=args.vault,
            host=args.host,
            port=args.port,
            retention_days=args.retention_days,
            log_level=args.log_level,
            pid_file=args.pid_file,
        )
        daemon = MnemosDaemon(config)
        try:
            asyncio.run(daemon.run())
        except KeyboardInterrupt:
            pass
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Implementation CLI subcommands в `cli.py`**

Add subparser group `daemon` with start/stop/status/foreground.

```python
def _cmd_daemon_start(args) -> int:
    config = DaemonConfig.from_env(args.vault).model_copy(
        update={k: v for k, v in {
            "host": args.host, "port": args.port,
            "retention_days": args.retention_days, "log_level": args.log_level,
        }.items() if v is not None}
    )
    pid = is_daemon_running(config.pid_file)
    if pid is not None:
        print(f"daemon already running on :{config.port}, pid={pid}", file=sys.stderr)
        return 78
    cmd = [
        sys.executable, "-m", "claude_mnemos.daemon", "run",
        "--vault", str(config.vault_root),
        "--host", config.host,
        "--port", str(config.port),
        "--retention-days", str(config.retention_days),
        "--log-level", config.log_level,
        "--pid-file", str(config.pid_file),
    ]
    kwargs: dict = {"stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    # Save config for status
    _save_daemon_runtime_config(config)
    # Poll up to 5s
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"http://{config.host}:{config.port}/health", timeout=0.5)
            if r.status_code == 200:
                print(f"daemon started: pid={proc.pid}, vault={config.vault_root}, http://{config.host}:{config.port}")
                return 0
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    print("daemon failed to start within 5s", file=sys.stderr)
    return 79

def _cmd_daemon_stop(args) -> int:
    config_runtime = _load_daemon_runtime_config()
    pid_file = config_runtime.pid_file if config_runtime else (Path.home() / ".mnemos" / "daemon.pid")
    pid = is_daemon_running(pid_file)
    if pid is None:
        print("daemon not running")
        return 0
    proc = psutil.Process(pid)
    proc.terminate()
    try:
        proc.wait(timeout=args.timeout)
    except psutil.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5.0)
        except psutil.TimeoutExpired:
            print("daemon process did not die after SIGKILL", file=sys.stderr)
            return 80
    cleanup_pid_file(pid_file)
    print(f"daemon stopped: pid={pid}")
    return 0

def _cmd_daemon_status(args) -> int:
    config_runtime = _load_daemon_runtime_config()
    pid_file = config_runtime.pid_file if config_runtime else (Path.home() / ".mnemos" / "daemon.pid")
    pid = is_daemon_running(pid_file)
    if pid is None:
        print("stopped")
        return 1
    if config_runtime is None:
        print(json.dumps({"pid": pid, "status": "running", "info": "no runtime config — call /health manually"}))
        return 0
    try:
        r = httpx.get(f"http://{config_runtime.host}:{config_runtime.port}/health", timeout=2.0)
        print(json.dumps({"pid": pid, **r.json()}, indent=2))
        return 0
    except httpx.HTTPError as exc:
        print(f"daemon process alive but HTTP unreachable: {exc}", file=sys.stderr)
        return 1

def _cmd_daemon_foreground(args) -> int:
    config = DaemonConfig.from_env(args.vault).model_copy(
        update={k: v for k, v in {
            "host": args.host, "port": args.port,
            "retention_days": args.retention_days, "log_level": args.log_level,
        }.items() if v is not None}
    )
    pid = is_daemon_running(config.pid_file)
    if pid is not None:
        print(f"daemon already running on :{config.port}, pid={pid}", file=sys.stderr)
        return 78
    daemon = MnemosDaemon(config)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        pass
    return 0
```

`_save_daemon_runtime_config` / `_load_daemon_runtime_config` — пишут/читают `~/.mnemos/daemon.config.json` с `{vault_root, host, port, pid_file}`.

- [ ] **Step 4: Tests pass + commit**

```
feat(cli): mnemos daemon {start,stop,status,foreground} subcommands
```

---

## Task 13: E2E + manual smoke + final verification + merge

- [ ] **Step 1: Run full test suite**

```bash
pytest -q
```

Expected: 193 + ~50-70 new = ~250 passed; slow tests separate marker.

- [ ] **Step 2: Run slow tests**

```bash
pytest -q -m slow
```

E2E daemon start/stop через subprocess.

- [ ] **Step 3: Lint + mypy**

```bash
ruff check .
mypy claude_mnemos
```

- [ ] **Step 4: Manual smoke**

```bash
# В одном терминале
mnemos daemon foreground --vault /tmp/test-vault --port 5757

# В другом
curl http://127.0.0.1:5757/health | jq
curl http://127.0.0.1:5757/version | jq
curl http://127.0.0.1:5757/vault/info | jq
curl http://127.0.0.1:5757/activity | jq
curl -X POST http://127.0.0.1:5757/snapshots -H "Content-Type: application/json" -d '{"label":"smoke"}' | jq
curl http://127.0.0.1:5757/snapshots | jq
# Убить foreground через Ctrl+C
```

```bash
# Background lifecycle
mnemos daemon start --vault /tmp/test-vault
mnemos daemon status
mnemos daemon stop
mnemos daemon status   # → stopped
```

- [ ] **Step 5: Update CLAUDE.md / README** — пропуск, у нас этого нет в проекте.

- [ ] **Step 6: Merge non-FF**

```bash
git checkout main
git merge --no-ff feat/daemon-foundation -m "Merge branch 'feat/daemon-foundation' — Plan #5: daemon foundation (FastAPI + scheduler + REST)"
```

- [ ] **Step 7: Update memory file**

Update `claude_mnemos_project.md` с новым статусом (Plans #1-#5 в main, кол-во тестов, что нового).

---

## Risks / things to watch

1. **Windows subprocess detach.** `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` иногда не выживает закрытие parent shell. Проверить руками. Fallback: использовать `pythonw.exe`.
2. **APScheduler cron timezone.** Default UTC. Если Ярик хочет local time — добавим env override `MNEMOS_DAEMON_TZ`.
3. **uvicorn signal handling on Windows.** `add_signal_handler` не работает на ProactorEventLoop. Fallback к `signal.signal()` сделан в `_install_signal_handlers`.
4. **`pipeline_lock` в FastAPI sync handler.** Уйдёт в Starlette threadpool — limited to 40 threads default. Долгие undo/restore могут забить pool. Acceptable для localhost single-user.
5. **`uvicorn[standard]` тащит много.** httptools, uvloop, websockets, watchfiles. Размер увеличится, но нам нужно minimum только httptools. Если станет проблемой — переедем на `uvicorn` (no extras) с явным `--http=h11`.
