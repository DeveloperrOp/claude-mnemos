# Design: Daemon Foundation (Plan #5)

**Status:** drafted, awaiting Yarik approval before implementation-plan generation.
**Date:** 2026-04-26
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-activity-undo-design.md` (Plan #4, merged in `6596207`).
**Successor planned:** Plan #6 (MCP server) → Plan #7 (Claude Code hooks) → Plan #8 (dashboard frontend) → Plan #9 (ontology).

---

## 1. Goal

Поднять долгоживущий процесс — `mnemos-daemon` — который выполняет две вещи:

1. **Housekeeping:** APScheduler с тасками `daily_snapshot` и `backups_cleanup` (180-day retention) — то, что spec §7.4 + §8.10 требуют, но в Plans #1-#4 не реализовано (память: «Snapshots никогда не удаляются автоматически»).
2. **REST API:** минимальный набор HTTP endpoints на `127.0.0.1:5757`, через которые внешние клиенты (будущий MCP, dashboard, hooks, CLI) читают состояние vault'а и запускают `undo` / `restore` без прямого доступа к файлам.

Это **первая итерация daemon'а как наблюдателя над уже работающим CLI**. Existing `mnemos ingest` остаётся synchronous и держит `pipeline_lock` сам — daemon не владеет ingest queue, не плодит workers, не имеет watchdog'а. Spec §10 описывает «полный» daemon (ingest workers, dead-letter, watchdog, jobs); мы режем до фундамента.

Что Plan #5 даёт пользователю:

- `mnemos daemon start` — поднял в background.
- `mnemos daemon status` — увидеть, бежит ли, какой PID, какой vault слушает.
- `mnemos daemon stop` — остановить.
- `mnemos daemon foreground` — для отладки + dev-режима.
- Автоматическая daily snapshot vault'а в 04:00 + автоматическая чистка `.backups/` старше 180 дней в 05:00.
- HTTP API `GET /health`, `GET /version`, `GET /vault/info`, `GET /activity`, `GET /activity/{id}`, `POST /activity/{id}/undo`, `GET /snapshots`, `POST /snapshots`, `POST /snapshots/{name}/restore`, `DELETE /snapshots/{name}`.

Что **НЕ** даёт (явно отложено в Plan #6+):

- Не делает ingest в background (CLI остаётся authority).
- Не имеет watchdog real-time для external file changes.
- Не имеет dead-letter queue, jobs.json, alerts.json.
- Не подключён к Claude Code hooks.
- Не отдаёт никакого UI/HTML — только JSON.
- Не имеет multi-vault routing (один daemon = один vault, заданный в конфиге).
- Не имеет auth — слушает только `127.0.0.1`, доверяет всем локальным клиентам.

---

## 2. Scope

### 2.1 In scope

| Компонент | Где |
|---|---|
| `MnemosDaemon` class — start/stop, single-instance lock, scheduler+server lifecycle | `daemon/process.py` |
| Daemon PID file lock с stale PID recovery (psutil + cmdline check) | `daemon/lockfile.py` |
| FastAPI app factory с health/version/vault/activity/snapshots routers | `daemon/app.py` |
| Routers (тонкие — вся логика в `core/*` и `state/*`) | `daemon/routes/{health,vault,activity,snapshots}.py` |
| Pydantic response models (re-export `ActivityEntry`, новые `VaultInfo`, `SnapshotInfo`, `HealthResponse`) | `daemon/schemas.py` |
| Daemon config (vault path, port, host, pid path, log level) — env + CLI overrides | `daemon/config.py` |
| APScheduler wiring + daily_snapshot + backups_cleanup tasks | `daemon/scheduler.py`, `daemon/tasks/{daily_snapshot,backups_cleanup}.py` |
| `core/snapshots.py` extension: `list_snapshots()`, `delete_snapshot()`, `prune_old_backups(retention_days, today)` | `core/snapshots.py` |
| `core/snapshots.py` extension: `create_daily_snapshot(vault, today)` — отдельная категория `daily-<YYYY-MM-DD>` | `core/snapshots.py` |
| CLI `mnemos daemon {start,stop,status,foreground}` | `cli.py` + `daemon/cli.py` (helpers) |
| Daemon test suite — pytest + httpx.AsyncClient + pytest-asyncio + ASGITransport | `tests/daemon/...` |
| Updated `pyproject.toml` deps: `fastapi`, `uvicorn[standard]`, `apscheduler`, `psutil`, `pytest-asyncio` | `pyproject.toml` |

### 2.2 Out of scope (явно отложено)

| Компонент | План |
|---|---|
| Ingest endpoints (`POST /api/ingest/...`) | Plan #7 (hooks) — там понадобится |
| Lint, ontology, jobs, dead-letter, alerts, metrics endpoints | Plan #8+ |
| Watchdog real-time (FSEvents) + `_our_writes` set + human_edit detection | Plan #9+ |
| Multi-vault routing (`/api/projects/{name}/...`) — single-vault daemon | Plan #7 |
| Frontend (React + shadcn) | Plan #8 |
| MCP server (отдельный процесс с REST к daemon) | Plan #6 |
| Claude Code hooks (SessionStart/SessionEnd/PreCompact) | Plan #7 |
| Auth/tokens (REST открытый на `127.0.0.1` без проверки) | v1.x |
| `auto_stale_task`, `trash_cleanup_task`, `scheduled_lint` (нет lifecycle/lint в кодовой базе ещё) | планы по мере появления операций |
| Daemon-as-orchestrator (ingest queue под daemon) | Plan #7+ |
| ingest_metrics writes from daemon | Plan #8+ |
| Логирование в файл (структурированное `daemon.log`) | v1.x — пока stderr через stdlib `logging` |
| systemd / launchd / Windows service unit-файлы | v1.x distribution |

---

## 3. Architecture

### 3.1 Где живёт daemon

```
~/.mnemos/                     # NEW: daemon state directory (пользовательский home)
├── daemon.pid                 # PID file для single-instance lock
└── daemon.config.json         # last-known config (vault path, port) — для status / stop
```

Vault при этом **не модифицируется** daemon'ом структурно — остаются `.activity.json`, `.manifest.json`, `.backups/`, `.staging/`, `.trash/` как в Plan #4. Daemon только пишет в `.backups/` (новые daily snapshots) и удаляет из `.backups/` (retention cleanup) — обе операции уже есть в `core/snapshots.py`, мы их расширяем.

### 3.2 Single-instance lock

Spec §5.5 — глобальный для daemon'а, не per-vault:

```python
# daemon/lockfile.py
PID_FILE = Path.home() / ".mnemos" / "daemon.pid"

def is_daemon_running() -> int | None:
    """Return live daemon PID, или None если не бежит / stale.

    Логика по spec §5.5:
    1. PID file отсутствует → None.
    2. PID file есть, но не int → удалить, None.
    3. PID жив, но cmdline не содержит "mnemos-daemon" → PID переиспользован, удалить, None.
    4. PID жив, cmdline валиден → return pid.
    5. Иначе → удалить stale, None.
    """
```

`cmdline` маркер: `mnemos-daemon` (substring) — daemon'ы запускаем через `python -m claude_mnemos.daemon` или CLI subprocess в которое прокинем `--marker mnemos-daemon` в argv хотя бы как cosmetic argument чтоб psutil cmdline проверка работала.

### 3.3 Process lifecycle

```
mnemos daemon start
  ├─ is_daemon_running() → если жив, exit 1 с user-friendly сообщением
  ├─ spawn detached child через subprocess.Popen([python, "-m", "claude_mnemos.daemon", "run", ...])
  │      (Windows: CREATE_NEW_PROCESS_GROUP; POSIX: start_new_session=True)
  ├─ child writes PID file, начинает MnemosDaemon.run()
  ├─ parent ждёт до 5s появления PID file + успешного GET /health
  └─ exit 0 (или 1 если daemon не поднялся)

mnemos daemon foreground
  └─ MnemosDaemon.run() прямо в текущем процессе (Ctrl+C завершает)

mnemos daemon stop
  ├─ pid = is_daemon_running()
  ├─ if pid is None → exit 0 ("daemon not running")
  ├─ os.kill(pid, SIGTERM) (Windows: psutil.Process(pid).terminate())
  ├─ wait до 10s, потом SIGKILL
  └─ удалить PID file (если daemon сам не убрал)

mnemos daemon status
  ├─ pid = is_daemon_running()
  ├─ if None → "stopped" (exit 1)
  └─ else → GET /health → печатает {pid, port, vault, uptime, scheduler_jobs} (exit 0)
```

Внутри `MnemosDaemon.run()`:

```python
async def run(self) -> None:
    self._write_pid_file()
    try:
        # 1. APScheduler
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.scheduler.add_job(
            daily_snapshot_task, "cron", hour=4, minute=0,
            args=[self.vault_root], id="daily_snapshot", replace_existing=True,
        )
        self.scheduler.add_job(
            backups_cleanup_task, "cron", hour=5, minute=0,
            args=[self.vault_root, self.retention_days], id="backups_cleanup",
            replace_existing=True,
        )
        self.scheduler.start()

        # 2. FastAPI via uvicorn
        config = uvicorn.Config(
            app=create_app(self.vault_root, self),
            host=self.host, port=self.port, log_level=self.log_level,
            lifespan="on",
        )
        self.server = uvicorn.Server(config)

        # 3. graceful shutdown — обработать SIGTERM/SIGINT
        self._install_signal_handlers()

        await self.server.serve()
    finally:
        self.scheduler.shutdown(wait=False)
        self._cleanup_pid_file()
```

### 3.4 Scheduler tasks

**`daily_snapshot_task(vault: Path)`:**

1. Acquire `pipeline_lock` (выкидывает наружу `LockTimeoutError` → APScheduler логирует, не падает) с timeout=30s.
2. Compute snapshot path `<vault>/.backups/daily-<utc-date>/` через `compute_daily_snapshot_path(vault, today)`.
3. Если уже существует (т.е. сегодня уже снимали) → no-op, return.
4. Иначе `create_snapshot_at(vault, snapshot_path, op_id="daily", op_type="daily")` — переиспользуем существующий код с явным путём (Plan #4 ввёл `compute_snapshot_path`; добавим `compute_daily_snapshot_path` рядом).
5. Лог в stderr через stdlib logging.

**`backups_cleanup_task(vault: Path, retention_days: int)`:**

1. Acquire `pipeline_lock` с timeout=30s (защита от удаления snapshot'а во время undo).
2. Iterate `<vault>/.backups/`, для каждой директории парсим timestamp из имени:
   - `pre-op-<utc-ts>-<type>-<id>/`
   - `daily-<utc-date>/`
3. Сравниваем `now - parsed_ts > retention_days`. Если да → `shutil.rmtree(snapshot_dir)`.
4. Возвращает counts: `pruned, kept, errors`. Логируем в stderr.

**Важно:** retention применяется ко всем snapshot'ам, включая pre-op (память: «Snapshots никогда не удаляются автоматически»). Spec §7.4 говорит «180-day retention»; default = 180, override через `--retention-days` или env `MNEMOS_RETENTION_DAYS`.

### 3.5 FastAPI app structure

```python
# daemon/app.py
def create_app(vault_root: Path, daemon: "MnemosDaemon | None" = None) -> FastAPI:
    app = FastAPI(title="claude-mnemos daemon", version=__version__)
    app.state.vault_root = vault_root
    app.state.daemon = daemon  # для health uptime / scheduler info; None в test mode

    app.include_router(health_router)
    app.include_router(vault_router)
    app.include_router(activity_router)
    app.include_router(snapshots_router)

    @app.exception_handler(ActivityCorruptError)
    async def _activity_corrupt(request, exc):
        return JSONResponse(
            status_code=503,
            content={"error": "activity_corrupt", "detail": str(exc)},
        )
    @app.exception_handler(UndoError)
    async def _undo_error(request, exc):
        return JSONResponse(
            status_code=409,
            content={"error": "undo_failed", "detail": str(exc)},
        )
    @app.exception_handler(LockTimeoutError)
    async def _lock_timeout(request, exc):
        return JSONResponse(
            status_code=423,
            content={"error": "vault_locked", "detail": str(exc)},
        )
    return app
```

Routers — тонкие переходники в существующие модули:

| Endpoint | Зовёт | Returns |
|---|---|---|
| `GET /health` | — | `HealthResponse{status, vault, uptime_s, scheduler_jobs[]}` |
| `GET /version` | — | `{version, python_version, platform}` |
| `GET /vault/info` | `Manifest.load`, `ActivityLog.load`, count `wiki/**/*.md`, count `raw/chats/*.md` | `VaultInfo` |
| `GET /activity?limit=N&offset=M` | `ActivityLog.load`, slice | `{entries: list[ActivityEntry], total: int}` |
| `GET /activity/{id}` | `ActivityLog.load.find_by_id` | `ActivityEntry` или 404 |
| `POST /activity/{id}/undo` | `core.undo.undo(vault, id)` | `UndoResult` (новые поля как в core/undo) |
| `GET /snapshots` | `core.snapshots.list_snapshots(vault)` | `{snapshots: list[SnapshotInfo]}` |
| `POST /snapshots` body=`{name?: str}` | `create_manual_snapshot(vault, name)` | `SnapshotInfo` |
| `POST /snapshots/{name}/restore` | `restore_from_snapshot(vault, snap)` + write `manual_restore` activity entry | `{success: True, snapshot, activity_id}` |
| `DELETE /snapshots/{name}` | `core.snapshots.delete_snapshot(vault, name)` | `{deleted: name}` |

Note: per-project routing по spec §10.3 (`/api/projects/{name}/activity`) — НЕ в Plan #5. Daemon знает один vault. Если позже multi-vault → переедем под `/api/projects/{name}/...` без breaking change для Plan #6/7 (они ещё не написаны).

### 3.6 Module map

**Новые:**

| Файл | Ответственность |
|---|---|
| `claude_mnemos/daemon/__init__.py` | re-export `create_app`, `MnemosDaemon` |
| `claude_mnemos/daemon/__main__.py` | `python -m claude_mnemos.daemon run|stop|status|foreground` (entry для CLI subprocess) |
| `claude_mnemos/daemon/process.py` | `MnemosDaemon` class — start/stop/run, signal handlers, PID file write |
| `claude_mnemos/daemon/lockfile.py` | `is_daemon_running()`, `write_pid_file()`, `cleanup_pid_file()` |
| `claude_mnemos/daemon/config.py` | `DaemonConfig` Pydantic model (vault_root, host, port, retention_days, log_level) |
| `claude_mnemos/daemon/app.py` | `create_app(vault_root, daemon=None) -> FastAPI` |
| `claude_mnemos/daemon/schemas.py` | `HealthResponse`, `VaultInfo`, `SnapshotInfo`, `UndoApiResult` Pydantic |
| `claude_mnemos/daemon/scheduler.py` | `attach_scheduler(daemon)` — jobs registration |
| `claude_mnemos/daemon/tasks/__init__.py` | re-export task fns |
| `claude_mnemos/daemon/tasks/daily_snapshot.py` | `daily_snapshot_task(vault)` |
| `claude_mnemos/daemon/tasks/backups_cleanup.py` | `backups_cleanup_task(vault, retention_days)` |
| `claude_mnemos/daemon/routes/__init__.py` | router exports |
| `claude_mnemos/daemon/routes/health.py` | health/version |
| `claude_mnemos/daemon/routes/vault.py` | vault info |
| `claude_mnemos/daemon/routes/activity.py` | activity list/get/undo |
| `claude_mnemos/daemon/routes/snapshots.py` | snapshots CRUD + restore |

**Изменяемые:**

| Файл | Что |
|---|---|
| `claude_mnemos/core/snapshots.py` | `list_snapshots(vault)`, `delete_snapshot(vault, name)`, `prune_old_backups(vault, retention_days, today)`, `compute_daily_snapshot_path(vault, today)`, `create_manual_snapshot(vault, label=None)` |
| `claude_mnemos/core/undo.py` | (no changes — REST переиспользует `undo()` как есть) |
| `claude_mnemos/cli.py` | Subcommand group `daemon {start,stop,status,foreground}` |
| `pyproject.toml` | Добавить deps + console_scripts entry `mnemos-daemon = claude_mnemos.daemon.__main__:main` |
| `tests/conftest.py` | Опциональный — добавить `pytest-asyncio` mode='auto' |

---

## 4. Pydantic schemas

### 4.1 HealthResponse

```python
class SchedulerJobInfo(BaseModel):
    id: str
    next_run_time: datetime | None
    trigger: str  # human-readable

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    vault: str  # absolute path
    uptime_s: float
    scheduler_jobs: list[SchedulerJobInfo]
```

### 4.2 VaultInfo

```python
class VaultInfo(BaseModel):
    vault: str
    raw_chats: int
    wiki_pages: int
    manifest_processed: int
    activity_entries: int
    snapshots: int
    total_size_bytes: int  # sum file sizes (best-effort, errors=0)
```

### 4.3 SnapshotInfo

```python
SnapshotKind = Literal["pre-op", "daily", "manual"]

class SnapshotInfo(BaseModel):
    name: str            # directory name e.g. "pre-op-2026-04-26-14-30-ingest-abc"
    kind: SnapshotKind
    timestamp: datetime  # parsed from name
    op_id: str | None    # для pre-op
    op_type: str | None  # для pre-op
    label: str | None    # для manual
    size_bytes: int
    path: str            # relative to vault root, e.g. ".backups/<name>"
```

### 4.4 UndoApiResult

```python
class UndoApiResult(BaseModel):
    success: bool
    op_id: str
    restored_pages: list[str]
    new_entry_id: str | None
```

### 4.5 DaemonConfig

```python
class DaemonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vault_root: Path
    host: str = "127.0.0.1"
    port: int = 5757
    retention_days: int = 180
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    pid_file: Path = Field(default_factory=lambda: Path.home() / ".mnemos" / "daemon.pid")

    @classmethod
    def from_env(cls, vault_root: Path) -> "DaemonConfig":
        # MNEMOS_DAEMON_PORT, MNEMOS_DAEMON_HOST, MNEMOS_RETENTION_DAYS, MNEMOS_DAEMON_LOG
        ...
```

---

## 5. Snapshot module extensions

`core/snapshots.py` сейчас экспортирует `compute_snapshot_path(vault, op_id, op_type)`, `create_snapshot(vault, op_id, op_type)`, `restore_from_snapshot(vault, snapshot_path)` (Plan #3+#4). Добавляем:

```python
def compute_daily_snapshot_path(vault: Path, today: date) -> Path:
    """Return <vault>/.backups/daily-<YYYY-MM-DD>/ — deterministic per-day path."""

def compute_manual_snapshot_path(vault: Path, label: str | None, now: datetime) -> Path:
    """Return <vault>/.backups/manual-<utc-ts>[-<slug>]/."""

def create_daily_snapshot(vault: Path, today: date) -> Path:
    """Atomically create daily snapshot if not exists; return path. Idempotent: existing path → return as-is."""

def create_manual_snapshot(vault: Path, label: str | None = None) -> Path:
    """Create snapshot with op_id='manual', op_type='manual' под уникальным timestamp."""

def list_snapshots(vault: Path) -> list[SnapshotInfo]:
    """Iterate <vault>/.backups/, parse names, return SnapshotInfo[].

    Skip directories that don't match known prefixes (pre-op-, daily-, manual-) — log warning.
    Best-effort size computation; errors → size_bytes=0.
    """

def delete_snapshot(vault: Path, name: str) -> None:
    """Reject names с traversal (../) и absolute paths.
    Reject names that don't match known prefixes.
    shutil.rmtree(<vault>/.backups/<name>).
    """

def prune_old_backups(vault: Path, retention_days: int, today: date) -> PruneResult:
    """Iterate snapshots, delete those с timestamp older than today-retention_days.
    Returns (pruned: list[str], kept: int, errors: list[(name, str)]).
    """
```

**Path safety.** `delete_snapshot` обязательно проверяет:

```python
target = (vault / ".backups" / name).resolve()
backups_root = (vault / ".backups").resolve()
if not target.is_relative_to(backups_root):
    raise ValueError(f"snapshot name escapes .backups/: {name}")
if target == backups_root:
    raise ValueError("cannot delete .backups/ itself")
```

То же для `restore_from_snapshot` входа из REST (`POST /snapshots/{name}/restore`) — мы уже резолвим path внутри роутера, потом передаём в `restore_from_snapshot`. Защита от path traversal — обязательна.

---

## 6. CLI commands

### 6.1 `mnemos daemon start [--vault <path>] [--port N] [--host H] [--retention-days N] [--log-level L]`

1. Resolve config (CLI → env → defaults).
2. `is_daemon_running()` → если да, print `daemon already running on :{port}, pid={pid}` и exit 1.
3. Иначе spawn detached subprocess `python -m claude_mnemos.daemon run --vault ... --port ... ...`.
4. Wait до 5s полла `is_daemon_running()` AND `httpx.get(http://host:port/health, timeout=1.0)`.
5. Success: print `daemon started: pid=N, vault=..., http://host:port`, exit 0.
6. Timeout: print error в stderr, попытка убить дитя, exit 1.

### 6.2 `mnemos daemon foreground [--vault <path>] [--port N] ...`

То же что `start`, но без detach. Прямо в текущем процессе зовёт `MnemosDaemon(...).run()`. Ctrl+C / SIGTERM → graceful shutdown через signal handlers.

### 6.3 `mnemos daemon stop [--timeout N]`

1. `pid = is_daemon_running()`.
2. None → print `daemon not running`, exit 0.
3. SIGTERM, wait до timeout=10s.
4. Не умер → SIGKILL.
5. Удалить PID file (защита от child который не успел cleanup).
6. Print `daemon stopped: pid=N`.

### 6.4 `mnemos daemon status`

1. `pid = is_daemon_running()`.
2. None → print `stopped`, exit 1.
3. Else → `httpx.get(http://127.0.0.1:port/health)` где port читаем из `~/.mnemos/daemon.config.json` (write при start).
4. Печатаем JSON-pretty: `{status, pid, vault, uptime_s, scheduler_jobs}`.

### 6.5 Exit codes

| Code | Cause |
|---|---|
| 78 | Daemon already running (start) |
| 79 | Daemon failed to start (timeout / spawn error) |
| 80 | Daemon stop failed (process не отвечает на SIGKILL) |
| 1 | Daemon not running (status) |

Ранее зарегистрированные exit codes (2/65/66/70/71/73/74/75/76/77) — без изменений.

---

## 7. HTTP error handling matrix

| Сценарий | Status | Body |
|---|---|---|
| `/activity/{id}` not found | 404 | `{error: "not_found", id: ...}` |
| `/activity/{id}/undo`: already undone | 409 | `{error: "undo_failed", detail: "...already undone..."}` |
| `/activity/{id}/undo`: snapshot missing | 409 | `{error: "undo_failed", detail: "...snapshot at ... not found"}` |
| Vault locked во время undo / snapshot create | 423 | `{error: "vault_locked", detail: ...}` |
| `.activity.json` corrupt при load | 503 | `{error: "activity_corrupt", detail: ...}` |
| `.manifest.json` corrupt при vault info | 503 | `{error: "manifest_corrupt", detail: ...}` |
| `/snapshots/{name}` traversal попытка | 400 | `{error: "invalid_name", detail: ...}` |
| `/snapshots/{name}` не существует (delete/restore) | 404 | `{error: "not_found", name: ...}` |
| `POST /snapshots/{name}/restore` фейлится частично | 500 | `{error: "restore_failed", detail: ..., recovery_hint: ...}` |
| Любая uncaught exception | 500 | `{error: "internal", detail: <str(exc)>}` (без stack trace в body) |

---

## 8. Concurrency и locking

| Operation | Holds | Why |
|---|---|---|
| `daily_snapshot_task` | `pipeline_lock` | snapshot во время промежуточного состояния `.staging/` пишет inconsistent vault |
| `backups_cleanup_task` | `pipeline_lock` | ничего из `.staging/` он не трогает, но защищает от удаления `.backups/<X>` пока undo делает `restore_from_snapshot(X)` |
| `POST /activity/{id}/undo` | внутри `core.undo.undo()` уже берёт `pipeline_lock` | без изменений |
| `POST /snapshots/{name}/restore` | `pipeline_lock` через `restore_from_snapshot` (Plan #3 уже это делает? — проверить, иначе обернуть в роутере) | block ingest во время restore |
| `POST /snapshots` (manual) | `pipeline_lock` | snapshot во время ingest = inconsistent |
| `DELETE /snapshots/{name}` | `pipeline_lock` | защита от удаления того который кто-то restore'ит |
| `GET /activity`, `GET /vault/info`, `GET /snapshots` | без lock | read-only; могут увидеть стейл `.activity.json` если параллельно идёт promote — приемлемо (eventual consistency для read API) |

**`pipeline_lock` blocking в FastAPI request thread.** Lock берётся в sync коде, а FastAPI handlers — async. Решение: write/destructive endpoints запускаем через `await asyncio.to_thread(blocking_op)` — пуляем в default executor pool. Или явно делаем sync def handler — Starlette сам вызовет в threadpool. Выбираем явный pattern: handler — `def`, не `async def`, для блокирующих операций. Read-only handlers — `async def` (file IO быстрое, не страшно). Это решение зафиксировано в коде.

---

## 9. Testing strategy

### 9.1 Уровни

1. **Unit (`daemon/lockfile.py`):**
   - `is_daemon_running()`: PID file отсутствует → None
   - PID file содержит мусор → None + удаление
   - PID жив, cmdline без marker → None + удаление (mock psutil)
   - PID жив с marker → возвращает pid
   - psutil.NoSuchProcess → None + удаление

2. **Unit (`core/snapshots.py` extensions):**
   - `compute_daily_snapshot_path` deterministic
   - `create_daily_snapshot` idempotent (повторный вызов в тот же день — no-op)
   - `list_snapshots` парсит pre-op / daily / manual; пропускает мусор с warning
   - `delete_snapshot` отвергает `..`, abs path, имя не из whitelist
   - `prune_old_backups`: старые удалены, новые сохранены, ошибки агрегируются

3. **Unit (`daemon/config.py`):**
   - DaemonConfig.from_env с дефолтами
   - Override через env vars
   - Валидация port (1-65535)
   - Валидация retention_days (>= 1)

4. **Unit (`daemon/tasks/*`):**
   - `daily_snapshot_task` создаёт snapshot, повторно — no-op
   - `daily_snapshot_task` с залоченным vault → LockTimeoutError logged, no crash
   - `backups_cleanup_task` удаляет старые, оставляет новые

5. **Integration HTTP (`daemon/app.py`):**
   - `httpx.AsyncClient(transport=ASGITransport(app), base_url="http://test")` без реального сокета
   - GET /health → 200, version из package
   - GET /vault/info → counts корректные на known fixture vault
   - GET /activity → пустой / с entries
   - GET /activity/{id} → 200 / 404
   - POST /activity/{id}/undo → success path (mock undo or real ingested fixture)
   - POST /activity/{id}/undo → 409 для already undone
   - GET /snapshots → list
   - POST /snapshots → создаёт manual
   - POST /snapshots/{name}/restore → vault rolled back, activity manual_restore написан
   - DELETE /snapshots/{name} → удаляет
   - DELETE /snapshots/`../etc/passwd` → 400

6. **Integration scheduler:**
   - `attach_scheduler(daemon)` регистрирует 2 jobs
   - APScheduler `next_run_time` корректный (в 04:00 UTC и 05:00 UTC)

7. **End-to-end CLI subprocess:**
   - `mnemos daemon foreground &` → poll /health → kill → проверка PID file удалён
   - `mnemos daemon start` → status → stop полный round-trip
   - `mnemos daemon start` дважды → второй exit 78
   - `mnemos daemon status` без бегущего → exit 1, "stopped"

### 9.2 Coverage targets

- 193 текущих + ~50-70 новых.
- ruff + mypy strict чистые.
- Manual smoke в Task последний:
  - `python -m claude_mnemos.daemon run --vault <fixture>` в одном терминале.
  - `curl http://127.0.0.1:5757/health` → JSON.
  - `curl http://127.0.0.1:5757/activity` → ingested entries из fixture.
  - `curl -XPOST http://127.0.0.1:5757/snapshots` → создал manual.
  - `mnemos daemon stop`.

### 9.3 Test infrastructure

- `pytest-asyncio` с `asyncio_mode = "auto"` (через `pyproject.toml`).
- `httpx.AsyncClient(transport=ASGITransport(app=create_app(vault, None)))` — без реальной сети.
- E2E daemon тесты — через `subprocess.Popen([sys.executable, "-m", "claude_mnemos.daemon", "run", ...])` + `httpx.get` polling. Limited (1-2 теста), потому что subprocess медленный. Скипаются через `@pytest.mark.slow` если не указан `--run-slow` (новый marker).

---

## 10. Known limitations

1. **Daemon = single-vault.** Один daemon знает один vault. Multi-vault routing (как в spec §10.3) — Plan #6/7. На практике пользователь сейчас работает с одним проектом — приемлемо.
2. **Auth отсутствует.** REST на `127.0.0.1` без токена. Любой локальный процесс может вызвать `POST /snapshots/{name}/restore`. Acceptable для localhost dev, не для multi-user системы. v1.x добавим bearer token из `~/.mnemos/auth.token`.
3. **Нет `_our_writes` set / watchdog.** Daemon не следит за external file changes; если пользователь руками правит `wiki/*.md` — никаких сигналов. Plan #9.
4. **APScheduler без persistence.** Если daemon упал, missed daily snapshot не будет дозапущен (он stateless — следующий день в 04:00 нормально сработает). Acceptable.
5. **Нет dead-letter queue.** Если `daily_snapshot_task` падает — error в stderr, retry в следующее окно (24h). Если шёл бы dead-letter — мы бы знали через `.dead-letter/`. Plan #8.
6. **Нет логирования в файл.** stdlib logging → stderr. Если daemon detached, stderr идёт в `os.devnull` (Windows) / TTY если в foreground. v1.x добавим `daemon.log` в `~/.mnemos/`.
7. **Daemon-as-orchestrator не реализован.** ingest всё ещё CLI-only. SessionEnd hook (Plan #7) попросит daemon `POST /api/ingest/...` → нужен новый endpoint и worker. Сейчас spec'овский §10 про `workers/ingest_worker.py` не сделан.
8. **`uvicorn[standard]` тащит `httptools` + `uvloop` (на Linux/Mac).** На Windows uvloop отсутствует — нормально, fallback на asyncio. Зависимость тяжёлая, но spec её требует.
9. **`pipeline_lock` для read-only endpoints не берётся.** Если активный ingest пишет `.activity.json` через staging promote — read endpoint может вернуть pre-promote (старую) версию или post-promote (новую). Eventual consistency. Не race condition (atomic_write гарантирует либо старое либо новое, не битое). Acceptable.
10. **Нет per-project routing yet.** Если v1.x добавим `/api/projects/{name}/...` — текущие endpoints `/activity` и `/snapshots` сломают URL'ы. Решение: с самого начала жить под `/api/v1/...` префиксом, или принять breaking change. **Решение:** жить без `/api/` префикса в Plan #5 (так короче и проще), но при добавлении multi-vault — переедем под `/api/v1/projects/{name}/...` с deprecation periodом.

---

## 11. What this enables (#6+ onwards)

- **Plan #6 (MCP):** MCP сервер дёргает `GET /vault/info`, `GET /activity`, `GET /pages` (которые добавим тогда). Read-only часть MCP (`query_wiki`, `read_page`) может работать без daemon, но write (`add_entity`, `apply_ontology_suggestion`) — только через daemon REST по принципу single-owner (spec §9.5).
- **Plan #7 (hooks):** SessionEnd hook вызовет `POST /api/ingest/sessions/{sid}` — мы добавим тогда ingest endpoint и worker. Sync ingest CLI остаётся как fallback.
- **Plan #8 (dashboard):** React frontend будет ходить в `/health`, `/activity`, `/snapshots`, `/vault/info` — все они уже есть. Добавятся `/pages/*` и `/lint/*` тогда.
- **Plan #9 (ontology):** ontology suggestions — новые endpoints, существующая инфраструктура работает.
- **Plan #10 (watchdog):** добавим `daemon.our_writes` set + Observer + handler. `atomic_write` обернём в `with daemon.tracking_write(path):`.

---

## 12. Решения, которые я принял сам (для протокола)

| Решение | Альтернатива | Почему выбрал |
|---|---|---|
| Plan #5 = только daemon, без MCP/hooks/dashboard | Один большой план «всё разом» | Прецедент Plans #1-#4: фокусные узкие планы. Меньше риска, чище review, ranchable. |
| Single-vault, daemon в `~/.mnemos/daemon.pid` | Multi-vault per-vault PID file | Простота. Multi-vault routing требует per-project state (`projects.json`) — пока такого нет. |
| Detached subprocess для `daemon start` | systemd unit / Windows Service | Cross-platform, без зависимости от service manager. v1.x distribution может добавить service files. |
| Endpoints без `/api/v1/` префикса в Plan #5 | С `/api/v1/` чтоб не сломать при multi-vault | Короче, проще. Breaking change при multi-vault приемлем — v1 ещё не релизнут. |
| `pipeline_lock` берётся для всех destructive endpoints | Только для сжатого окна около `restore_from_snapshot` | Защита от race с `mnemos ingest` CLI который сейчас единственный writer. Иначе race по `.activity.json`. |
| Sync def handlers для destructive ops, async для read | Везде async (нужно `asyncio.to_thread` обёртки) | Starlette автоматически кидает `def` в threadpool. Меньше кода и явная семантика «эта ручка блокирующая». |
| FastAPI вместо Flask | Flask + sync | Spec §10 требует FastAPI. У нас уже Pydantic — bonus интеграция. async daily snapshot job через AsyncIOScheduler. |
| APScheduler вместо cron / systemd timer | OS-level scheduler | Spec §10.4 требует APScheduler. Cross-platform. Daemon owns его. |
| Daemon не владеет ingest queue в Plan #5 | Daemon-as-orchestrator с самого начала | Огромный refactor существующего pipeline + worker model + jobs.json. Не нужен для пользы первой итерации. |
| Daily snapshot путь — отдельный prefix `daily-<date>` | Использовать `pre-op-<ts>-daily-<id>` (как pre-op) | Семантически разное: pre-op привязан к operation_id, daily — к дате. Отдельный prefix упрощает retention rules и UI. |
| Retention применяется ко ВСЕМ snapshots (pre-op + daily + manual) | Только daily | Память: «Snapshots никогда не удаляются автоматически» — это и про pre-op. Без чистки `.backups/` пухнет vault. Pin (`POST /snapshots/{id}/pin` из spec) пока не делаем — v1.x. |
| Path traversal защита внутри `core/snapshots.py`, не в роутере | Только в роутере | Defence in depth. Если будущий MCP вызовет `delete_snapshot(...)` напрямую — тоже защищены. |
| `mnemos daemon` subcommand group, не отдельная команда `mnemos-daemon` | Отдельная команда | Один entry point, проще help. `console_scripts` все равно `mnemos`. |
| Без auth | Bearer token из `~/.mnemos/auth.token` | YAGNI для localhost-only v1. Добавим когда понадобится remote access (которого spec не предусматривает). |
| `python -m claude_mnemos.daemon` через `__main__.py` | Прямо `claude-mnemos-daemon` console_script | Оба добавим. `python -m` для тестирования; console_script для UX. |

---

## 13. Open questions для имплементации (не блокеры)

- **APScheduler timezone.** Cron `hour=4` в UTC → в Киеве это 06:00/07:00. Нормально? Локализованный default = `Europe/Kyiv` (Ярик в Украине)? Решу при коде; пока UTC, легко override через env.
- **uvicorn `lifespan="on"` startup/shutdown hooks.** Пробрасывать ли scheduler через `app.state.scheduler` чтоб health endpoint видел? Решу при коде.
- **Daemon detach на Windows.** `subprocess.Popen` с `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` — стандартный паттерн. Если родитель закрывается, дитя живёт. Проверить руками. Если не сработает — fallback к `pythonw.exe`.
- **`mnemos daemon foreground` SIGTERM signal handler на Windows.** Windows console не получает SIGTERM от Ctrl+C — только SIGINT. Установим оба handler'а.
- **`pyproject.toml` console_scripts entry для `mnemos-daemon`.** Stub-обёртка, или через `python -m claude_mnemos.daemon`? Решу при коде.
- **`SnapshotInfo.size_bytes`.** Best-effort `sum(p.stat().st_size for p in dir.rglob("*") if p.is_file())` — на больших vault'ах медленно. Кешировать в `<snapshot>/.size`? Решу при коде; пока без кеша.
- **`/version` endpoint:** где брать версию? `claude_mnemos.__version__` — если такого нет, добавить в `__init__.py`. Проверить при коде.
- **Daemon graceful shutdown timeout** при остановке uvicorn — сколько ждать активные requests? 5s default ok.
- **`MNEMOS_DAEMON_VAULT` env var.** Чтобы `mnemos daemon start` без `--vault` мог взять из env. Решу при коде; вероятно да.

---

## 14. Why this scope

Через эту узкую дверь (housekeeping + read API + минимальный write через REST) мы:

1. Получаем **первый working daemon** — пользователь увидит, что mnemos может бежать в background и автоматически чистить snapshots. До сих пор демон был **только** концепцией в spec'е.
2. Закрываем дыру из памяти — **«Snapshots никогда не удаляются автоматически (нужен scheduler/daemon, Plan #5+)»**. После Plan #5 — закрыто.
3. Подкладываем фундамент под Plan #6 (MCP) и Plan #7 (hooks) без необходимости тащить frontend и watchdog.
4. Не блокируем существующий sync-CLI ingest. Если daemon упал — `mnemos ingest` работает как до Plan #5. Низкий риск регрессий в основном flow.
5. По cycle time остаёмся в той же продолжительности что Plans #2/#3/#4 (по 1-2 недели каждый). Plans #6-#10 пойдут дальше тем же ритмом.
