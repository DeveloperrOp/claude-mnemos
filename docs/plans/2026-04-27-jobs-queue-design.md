# Design: Jobs + Dead-letter Queue (Plan #11 — NEW)

**Status:** drafted, scope C approved (full spec §8.9), storage = SQLite approved.
**Date:** 2026-04-27
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-27-lint-design.md` (Plan #10, merged in `9f923b2` + post-merge fixes `3d1c2f6`/`311e427`).
**Successor planned:** Plan #12 (Page edit + Trash) → Plan #13 (Sessions+Settings+Metrics+Multi-vault+adaptive context) → Plan #14 (Dashboard).

---

## 1. Goal

Дать daemon'у **persistent job queue** для асинхронных операций с retry/dead-letter политикой. Закрывает три смежные задачи:

1. **Daemon-as-orchestrator для ingest**: SessionEnd hook больше не spawn'ит детач'нутый CLI subprocess — он `POST`'ит job в queue, daemon worker его подхватывает и запускает ingest in-process. Закрывается known limitation Plan #9 (concurrent CLI ingest false positive `human_edit_detected`).

2. **Retry policy для transient failures**: API timeout, network blip, lock contention — все превращаются в exponential backoff retry без потери work'а. 3 attempts × backoff 30s/2min/20min per spec §8.9.

3. **Dead-letter quarantine**: finally-failed jobs копятся в отдельной таблице **навсегда** (no auto-cleanup) до ручного review через `mnemos jobs retry-dead <id>` или `mnemos jobs dismiss <id>`. Health alert при > 10 dead items.

После Plan #11:

```bash
# Workflow A: SessionEnd hook → daemon queue (auto)
# (происходит автоматически после каждой Claude Code сессии)
# Hook делает POST /jobs {kind="ingest", payload={"transcript_path": "..."}}.
# Daemon worker pulls, выполняет ingest in-process под pipeline_lock'ом.
# Если падает с retry'able exception — schedule retry через APScheduler.

# Workflow B: ручная инспекция
mnemos jobs list --vault <path> [--status queued|running|succeeded|failed|dead_letter]
mnemos jobs show <job_id> --vault <path>
mnemos jobs retry-dead <job_id> --vault <path>     # вернуть в очередь с attempt=0
mnemos jobs dismiss <job_id> --vault <path>        # удалить навсегда
mnemos jobs cancel <job_id> --vault <path>         # для status=queued

# REST для будущего dashboard
GET    /jobs?status=...&limit=N&offset=M
GET    /jobs/{id}
DELETE /jobs/{id}                       # cancel queued job
GET    /dead-letter                     # alias for status=dead_letter
POST   /dead-letter/{id}/retry          # back to queue с attempt=0
DELETE /dead-letter/{id}                # dismiss permanently
```

### Что НЕ даёт (явно отложено)

- **MCP tools для jobs** — Plan #14 (Dashboard) добавит, в Plan #11 только REST + CLI.
- **`mnemos jobs backup`** для ручного backup'а .jobs.db — отложено в Plan #12+.
- **Generic job kinds** (`lint_run`, `ontology_apply` в очереди) — schema позволяет, но в Plan #11 единственный handler — `ingest`. Plans #12+ добавят остальные.
- **Per-job priority** — все jobs обрабатываются FIFO внутри `(status, next_attempt_at)` order.
- **Multi-worker concurrency** — один daemon-side worker, sequential execution. `pipeline_lock` всё равно сериализует, plurality бесполезна.
- **Job history retention pruning** — succeeded jobs копятся; pruning старше 180 дней — отдельная scheduled task, отложено в Plan #12+.
- **Quarantine merger** в spec §8.6 (reject staging) — это отдельная подсистема, не jobs queue. Не пересекаются.
- **Job log streaming через stdout/stderr** — spec §10.3 упоминает `GET /jobs/{id}` возвращает stdout/stderr. В Plan #11 нет — только `error: str | None` и `error_traceback: str | None`. UI tail-streaming — Plan #14+.

---

## 2. Scope

### 2.1 In scope

| Компонент | Где |
|---|---|
| SQLite schema + connection management (WAL mode, isolation_level=None для explicit transactions) | `claude_mnemos/state/jobs.py` |
| `JobStatus` Literal enum: `queued/running/succeeded/failed/dead_letter` | `state/jobs.py` |
| `JobKind` Literal: `"ingest"` (extensible) | `state/jobs.py` |
| `Job` Pydantic model + DB row mapper | `state/jobs.py` |
| `JobStore` — CRUD: `create()`, `claim_next_ready()`, `mark_running()`, `mark_succeeded()`, `mark_failed_with_retry()`, `mark_dead_letter()`, `list_by_status()`, `get_by_id()`, `cancel_queued()`, `restore_from_dead_letter()`, `dismiss_dead_letter()` | `state/jobs.py` |
| `JobsCorruptError(ValueError)` для unreadable/incompatible DB | `state/jobs.py` |
| Retry policy: `RETRY_DELAYS_S = [30, 120, 1200]`, `MAX_ATTEMPTS = 3` | `state/jobs.py` |
| `daemon/jobs/worker.py` — async coroutine pulling next ready job, dispatching to handler, handling result | новый |
| `daemon/jobs/handlers.py` — `IngestHandler` + dispatcher pattern | новый |
| `daemon/jobs/recovery.py` — startup scan: `running → queued (attempt+=1)` или `dead_letter` если attempt>=MAX | новый |
| `daemon/jobs/scheduler.py` — APScheduler hook для retry timestamps | новый |
| `daemon/routes/jobs.py` — REST endpoints | новый |
| `daemon/routes/dead_letter.py` — REST endpoints | новый |
| `MnemosDaemon` wiring: запуск worker'а + recovery on startup | edit `daemon/process.py` |
| Health endpoint расширение: `jobs_queued`, `jobs_running`, `jobs_dead_letter`, `jobs_alert` (>10) | edit `daemon/routes/health.py`, `daemon/schemas.py` |
| `core/snapshots.py` — `_EXCLUDED_FILES` += `.jobs.db` (WAL files: `.jobs.db-wal`, `.jobs.db-shm` тоже) | edit |
| `hooks/session_end.py` — POST к daemon `/jobs`, fallback на subprocess если daemon offline | edit |
| `cli.py` — `mnemos jobs {list, show, retry-dead, dismiss, cancel}` subgroup | edit |
| `ActivityOperationType += "ingest_via_queue"` ?  **НЕТ** — ingest pipeline уже пишет `ingest_extracted`/`ingest_raw_only`. Queue — это transport, не operation. Никакие новые activity literals. | (no change) |
| Tests: state + worker + handlers + recovery + scheduler + REST + hook update + CLI | новые в `tests/state/`, `tests/daemon/jobs/`, `tests/daemon/test_app_jobs.py`, `tests/daemon/test_app_dead_letter.py`, `tests/test_cli_jobs.py`, `tests/test_session_end_hook.py` (extend) |

### 2.2 Out of scope

| Component | План | Reason |
|---|---|---|
| MCP tools для jobs/dead-letter | Plan #14 | LLM не оркестрирует queue — это user concern |
| Generic job handlers (lint, ontology) | Plans #12+ | пока только ingest нужен в queue |
| Per-job priority / SLA | Plan #14+ | YAGNI |
| Multi-worker concurrency | не делаем | pipeline_lock анyway сериализует |
| Job history pruning (succeeded > 180d) | Plan #12+ | в Plan #11 keep all succeeded jobs |
| stdout/stderr streaming для running jobs | Plan #14+ | dashboard concern |
| `.jobs.db` backup command | Plan #12+ | manual backup отдельная подсистема |
| Quarantine staging (spec §8.6) | не пересекается | другая подсистема (rejected ingests в .trash) |
| Persistent alerts (Plan #9 known limitation) | Plan #12+ | отдельный refactor; Plan #11 не трогает alerts |

---

## 3. Architecture

### 3.1 SQLite schema

```sql
-- Schema version 1
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', '1');

CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,             -- uuid4 hex
    kind            TEXT NOT NULL,                -- "ingest" (extensible)
    payload_json    TEXT NOT NULL,                -- JSON-encoded handler args
    status          TEXT NOT NULL,                -- queued | running | succeeded | failed | dead_letter
    attempt         INTEGER NOT NULL DEFAULT 0,   -- 0 on first try, 1/2/3 on retries
    next_attempt_at REAL NOT NULL,                -- unix ts; 0 means "ready now"
    created_at      REAL NOT NULL,
    started_at      REAL,
    finished_at     REAL,
    error           TEXT,                         -- short message
    error_traceback TEXT,                         -- full traceback if available
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter')),
    CHECK (attempt >= 0)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_next_at
    ON jobs (status, next_attempt_at);

CREATE INDEX IF NOT EXISTS idx_jobs_kind
    ON jobs (kind);

CREATE INDEX IF NOT EXISTS idx_jobs_created
    ON jobs (created_at);
```

**Connection policy:** `sqlite3.connect(path, isolation_level=None, check_same_thread=False)` + explicit `BEGIN IMMEDIATE`/`COMMIT`. WAL mode (`PRAGMA journal_mode=WAL`) для concurrent reads. `synchronous=NORMAL` (acceptable durability на single-vault scenario; spec не требует full FSYNC).

**JobStore lifecycle:** один экземпляр на vault, держит open connection в daemon. CLI commands (read-only `list`/`show`) открывают свою connection, читают, закрывают. Write CLI (cancel, retry-dead, dismiss) идут через REST к daemon — единственный writer = daemon.

**Schema migration:** `schema_meta.version` отслеживает schema. На startup: если version mismatch — `JobsCorruptError`. v1 → v2 миграции — Plan #12+.

### 3.2 `Job` model

```python
JobStatus = Literal["queued", "running", "succeeded", "failed", "dead_letter"]
JobKind = Literal["ingest"]   # extensible — Plans #12+ add lint_run, ontology_apply

class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: JobKind
    payload: dict[str, Any]            # decoded from payload_json
    status: JobStatus
    attempt: int = Field(ge=0)
    next_attempt_at: datetime          # UTC
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    error_traceback: str | None
```

`payload` для `kind="ingest"`:
```python
{
    "transcript_path": "/abs/path/to/session.jsonl",
    "extract": True,                    # default True
    "dry_run": False,                   # default False
    # model/language_hint/max_input_tokens идут из daemon Config, не из payload
}
```

### 3.3 `JobStore` API

```python
class JobStore:
    def __init__(self, db_path: Path) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> "JobStore": ...

    # — write operations (single writer = daemon) —
    def create(self, kind: JobKind, payload: dict[str, Any]) -> Job: ...
    def claim_next_ready(self, *, now: datetime) -> Job | None:
        """Pull oldest queued job with next_attempt_at <= now and mark running.
        Atomic via BEGIN IMMEDIATE + UPDATE WHERE.
        Returns None if no ready job."""

    def mark_succeeded(self, job_id: str, *, finished_at: datetime) -> None: ...
    def mark_failed_with_retry(
        self, job_id: str, *, error: str, traceback: str, finished_at: datetime
    ) -> Job:
        """Increment attempt. If attempt >= MAX_ATTEMPTS — mark dead_letter.
        Else: status=queued, next_attempt_at = finished_at + RETRY_DELAYS_S[attempt-1].
        Returns updated job."""

    def cancel_queued(self, job_id: str) -> bool:
        """Only works on status=queued; returns True if cancelled."""

    def restore_from_dead_letter(self, job_id: str) -> Job:
        """status=queued, attempt=0, next_attempt_at=now, error=None."""

    def dismiss_dead_letter(self, job_id: str) -> bool:
        """Permanent delete. Only works on status=dead_letter."""

    # — read operations —
    def get_by_id(self, job_id: str) -> Job | None: ...
    def list_by_status(
        self, status: JobStatus | None, *, limit: int = 50, offset: int = 0
    ) -> list[Job]: ...
    def count_by_status(self) -> dict[JobStatus, int]: ...

    # — recovery —
    def recover_zombie_running(self) -> RecoveryResult:
        """Called once on daemon startup. For each status=running:
        - if attempt + 1 < MAX_ATTEMPTS: status=queued, attempt+=1, next_attempt_at=now
        - else: status=dead_letter, error='daemon crashed during execution'.
        Returns counts."""
```

`RETRY_DELAYS_S = [30.0, 120.0, 1200.0]` — индексируется по `attempt` (0 для первой попытки до retry, 1 после первой неудачи и т.д.). `MAX_ATTEMPTS = 3` означает: первая попытка + до 2 retry'ев = 3 total runs. Spec §8.9 says "3 retries × backoff 30s/2min/20min" — формулировка amиguous; принимаем как 3 total = 1 initial + 2 retries (30s, 2min waits). Третья неудача → dead_letter без waiting на 20min retry. Это экономит 20min wasted и проще.

**Альтернативное чтение:** "3 retries" = 4 total (initial + 3 retries по 30s/2min/20min). Делаю по альтернативе чтобы быть ближе к буквальному spec'у. **Финал:** `MAX_ATTEMPTS = 4` (initial + 3 retries), `RETRY_DELAYS_S = [30, 120, 1200]` (используется когда attempt 1, 2, 3 фейлятся → задержка перед attempts 2, 3, 4).

Wait, перечитываю spec: "3 retries × exponential backoff 30s/2min/20min". 3 retries = после 3 неудач job становится dead_letter. Каждая retry имеет свой backoff. То есть:
- attempt 0 (first try) → fail → wait 30s → attempt 1
- attempt 1 → fail → wait 2min → attempt 2
- attempt 2 → fail → wait 20min → attempt 3
- attempt 3 → fail → dead_letter

Total 4 runs. `MAX_ATTEMPTS = 4` (4 attempts total before dead_letter). `RETRY_DELAYS_S = [30, 120, 1200]` (3 entries — задержки между 1→2, 2→3, 3→4 attempts).

OK, фиксирую: `MAX_ATTEMPTS = 4`, `RETRY_DELAYS_S = [30.0, 120.0, 1200.0]`.

### 3.4 Worker model

```python
# daemon/jobs/worker.py

class JobWorker:
    POLL_INTERVAL_S = 5.0       # back-pressure при empty queue

    def __init__(
        self,
        store: JobStore,
        scheduler: AsyncIOScheduler,
        handlers: dict[JobKind, JobHandler],
    ) -> None:
        self._store = store
        self._scheduler = scheduler
        self._handlers = handlers
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self, *, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._task is not None:
            await asyncio.wait_for(self._task, timeout=timeout)

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._store.claim_next_ready(now=datetime.now(UTC))
            except Exception:
                logger.exception("job claim failed")
                await asyncio.sleep(self.POLL_INTERVAL_S)
                continue

            if job is None:
                # No ready job — wait for either timeout or wakeup signal
                try:
                    await asyncio.wait_for(self._wakeup_event.wait(), timeout=self.POLL_INTERVAL_S)
                    self._wakeup_event.clear()
                except asyncio.TimeoutError:
                    pass
                continue

            await self._run_job(job)

    async def _run_job(self, job: Job) -> None:
        handler = self._handlers.get(job.kind)
        if handler is None:
            err = f"no handler for kind={job.kind}"
            self._store.mark_failed_with_retry(
                job.id, error=err, traceback="", finished_at=datetime.now(UTC),
            )
            return
        try:
            await handler.run(job)
            self._store.mark_succeeded(job.id, finished_at=datetime.now(UTC))
        except Exception as exc:
            tb = traceback.format_exc()
            updated = self._store.mark_failed_with_retry(
                job.id, error=str(exc), traceback=tb, finished_at=datetime.now(UTC),
            )
            if updated.status == "queued":
                # Schedule wakeup at next_attempt_at via APScheduler DateTrigger
                self._scheduler.add_job(
                    self._wakeup,
                    trigger=DateTrigger(run_date=updated.next_attempt_at),
                    id=f"jobs-wakeup-{job.id}-{updated.attempt}",
                    replace_existing=True,
                )

    def _wakeup(self) -> None:
        """Called by APScheduler when a retry's next_attempt_at lands."""
        self._wakeup_event.set()
```

`_wakeup_event: asyncio.Event` ускоряет worker pickup для retry'ов — не ждём 5s polling после attainment of next_attempt_at.

**Why poll AND event?** Pure polling медленный (до 5s задержка для свежих jobs). Pure event — миссит jobs с `next_attempt_at` в прошлом (e.g. recovery). Hybrid = best of both.

### 3.5 IngestHandler

```python
# daemon/jobs/handlers.py

class IngestHandler:
    def __init__(self, vault: Path, daemon: "MnemosDaemon") -> None:
        self._vault = vault
        self._daemon = daemon

    async def run(self, job: Job) -> None:
        transcript_path = Path(job.payload["transcript_path"])
        extract = bool(job.payload.get("extract", True))
        dry_run = bool(job.payload.get("dry_run", False))

        # Run sync ingest in thread executor — keeps event loop responsive
        await asyncio.to_thread(
            ingest,
            transcript_path,
            self._vault,
            cfg=self._daemon.config_runtime_or_env(),
            llm_client=self._daemon.llm_client(),  # may be None for no-LLM
            extract=extract,
            dry_run=dry_run,
            today=date.today(),
        )
```

`MnemosDaemon` теперь должен уметь дать `Config` instance + опциональный `LLMClient`. В Plan #5 daemon не имел LLM client — его создавал CLI ingest. В Plan #11 daemon должен уметь сам ingest'ить. Минимально:

```python
class MnemosDaemon:
    def config_runtime_or_env(self) -> Config:
        return Config.from_env()  # reads ANTHROPIC_API_KEY etc.

    def llm_client(self) -> LLMClient | None:
        cfg = self.config_runtime_or_env()
        if not cfg.api_key:
            return None
        return AnthropicLLMClient(cfg)
```

Если no API key — `extract=False` принудительно (raw_only ingest). Hook должен передавать `extract=True` только если уверен что daemon имеет API key — пока проще: hook всегда передаёт `extract=True`, daemon downgrade'ит если key отсутствует.

**Retry'able vs final errors:** все exceptions считаются retry'able до `MAX_ATTEMPTS`. `FileNotFoundError` (transcript исчез) — теоретически не retryable, но пусть пробует — может race с ingest worker hookups. Plan #12+ может добавить granular `RetryableError`/`PermanentError`.

### 3.6 Recovery on startup

```python
# daemon/jobs/recovery.py

@dataclass(frozen=True)
class RecoveryResult:
    requeued: int
    moved_to_dead_letter: int

def recover_zombie_running(store: JobStore) -> RecoveryResult:
    """Implementation in JobStore — this is just the public adapter."""
    return store.recover_zombie_running()
```

Called once в `MnemosDaemon._start_jobs_subsystem` перед стартом worker'а.

### 3.7 SessionEnd hook update

```python
# hooks/session_end.py — обновлено

def main():
    payload = json.loads(sys.stdin.read())
    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        sys.exit(0)

    vault = os.environ.get("MNEMOS_VAULT_ROOT")
    if not vault:
        print("MNEMOS_VAULT_ROOT not set", file=sys.stderr)
        sys.exit(0)

    daemon_url = os.environ.get("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757")

    # Try queue mode first
    if _try_post_to_daemon(daemon_url, transcript_path):
        sys.exit(0)

    # Fallback: detached subprocess (Plan #7 behavior)
    _spawn_detached_ingest(transcript_path, vault)
    sys.exit(0)

def _try_post_to_daemon(daemon_url: str, transcript_path: str) -> bool:
    """POST /jobs. Returns True on 201/200, False otherwise."""
    try:
        r = httpx.post(
            f"{daemon_url}/jobs",
            json={"kind": "ingest", "payload": {"transcript_path": transcript_path}},
            timeout=2.0,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False
```

Hook **никогда не блокирует session end**, как в Plan #7. Soft-skip на любую ошибку.

### 3.8 REST API

```
POST   /jobs                           — create job (kind, payload)
                                         body: {"kind": "ingest", "payload": {...}}
                                         → 201 with Job model
GET    /jobs                           — list jobs
                                         query: ?status=&kind=&limit=&offset=
GET    /jobs/{id}                      — get job by id
DELETE /jobs/{id}                      — cancel queued job (404 if not queued)
GET    /dead-letter                    — alias for GET /jobs?status=dead_letter
POST   /dead-letter/{id}/retry         — restore_from_dead_letter
DELETE /dead-letter/{id}               — dismiss_dead_letter
```

Exception handlers:
- `JobsCorruptError` → 503 "jobs database corrupt"
- `JobNotFoundError` → 404 (or just `HTTPException` from inside handler — keep simple)
- `JobInvalidStateError` (e.g. cancel on running job) → 409

### 3.9 Health endpoint

```python
class HealthResponse(BaseModel):
    ...
    jobs_queued: int = 0
    jobs_running: int = 0
    jobs_dead_letter: int = 0
    jobs_alert: bool = False             # True if jobs_dead_letter > 10
```

Frontend (Plan #14) опросом /health показывает badge.

### 3.10 CLI

```bash
mnemos jobs list [--vault] [--status STATUS] [--limit N]
mnemos jobs show <job_id> [--vault]
mnemos jobs retry-dead <job_id> [--vault]    # alias: retry
mnemos jobs dismiss <job_id> [--vault]
mnemos jobs cancel <job_id> [--vault]        # for queued
```

Read commands (`list`, `show`) — direct DB read через JobStore. Write commands (`retry-dead`, `dismiss`, `cancel`) — POST/DELETE к daemon REST. Если daemon offline — print informative message + exit 84.

Exit codes:
- 84 — daemon required but offline
- 85 — JobsCorruptError
- 86 — JobNotFoundError / JobInvalidStateError

### 3.11 Snapshot interaction

`core/snapshots.py:_EXCLUDED_FILES` уже содержит `{".pipeline.lock"}`. Расширим:

```python
_EXCLUDED_FILES = {
    ".pipeline.lock",
    ".jobs.db",
    ".jobs.db-wal",
    ".jobs.db-shm",
    ".jobs.db-journal",
}
```

`restore_from_snapshot` после swap'а оставит `.jobs.db` нетронутым (preserved across swap, аналогично `.backups`/`.staging`/`.trash`). Это значит что daemon на restart после restore увидит существующий queue.

### 3.12 Wiring в `MnemosDaemon`

```python
class MnemosDaemon:
    def __init__(self, config: DaemonConfig) -> None:
        ...
        self.job_store = JobStore(config.vault_root / ".jobs.db")
        self.job_worker: JobWorker | None = None

    async def run(self) -> None:
        write_pid_file(...)
        try:
            self._start_observer()
            self._start_jobs_subsystem()
            self.scheduler.start()
            ...
        finally:
            self._stop_jobs_subsystem()
            self._stop_observer()
            ...

    def _start_jobs_subsystem(self) -> None:
        try:
            self.job_store.recover_zombie_running()
            handlers = {"ingest": IngestHandler(self.config.vault_root, self)}
            self.job_worker = JobWorker(self.job_store, self.scheduler, handlers)
            asyncio.create_task(self.job_worker.start())
        except Exception as exc:
            logger.exception("failed to start jobs subsystem")
            self.alerts.add(
                kind="handler_error",
                path=str(self.config.vault_root),
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
        self.job_store.close()
```

---

## 4. Test strategy

### 4.1 Unit

- `tests/state/test_jobs.py`: full CRUD lifecycle (create → claim → succeed/fail → retry → dead_letter); concurrent claims (two `claim_next_ready` from same DB only return one to one caller); recovery; corrupt DB raises; schema version mismatch raises; cancel rules; dismiss rules.

- `tests/daemon/jobs/test_worker.py`: worker picks up job, dispatches handler, marks succeeded; on handler exception marks failed_with_retry + schedules APScheduler wakeup; handler crash propagates traceback to job.error_traceback; worker stop is graceful.

- `tests/daemon/jobs/test_handlers.py`: IngestHandler invokes core ingest function via to_thread with right payload; raises propagate.

- `tests/daemon/jobs/test_recovery.py`: 3 zombie jobs → 2 requeued + 1 dead_letter (last attempt before crash).

### 4.2 Integration / REST

- `tests/daemon/test_app_jobs.py`: POST /jobs create + GET list/by-id + DELETE cancel; status filter; 404 on missing.
- `tests/daemon/test_app_dead_letter.py`: POST retry restores to queue; DELETE dismisses permanently.
- `tests/daemon/test_app_health.py` (extend): jobs counts in HealthResponse.

### 4.3 Slow E2E

- `tests/daemon/test_jobs_e2e.py` (`@pytest.mark.slow`):
  Spin up subprocess daemon. POST /jobs with synthetic ingest payload (small fixture transcript). Poll /jobs/{id} until status=succeeded or until activity log получает entry. Verify .jobs.db persisted across restart (kill daemon, restart, check job is succeeded в DB).

- `tests/test_session_end_hook.py` (extend): hook with running daemon → POST sees the job in /jobs; hook with offline daemon → fallback subprocess path still works.

---

## 5. Open questions

| # | Q | Решение |
|---|---|---|
| Q1 | `MAX_ATTEMPTS = 3` (3 retries) или `MAX_ATTEMPTS = 4` (initial + 3 retries)? | 4 — буквально 3 retries по spec'у. RETRY_DELAYS_S = [30, 120, 1200]. |
| Q2 | Retry'able vs permanent errors? | Все exceptions retry'able в Plan #11. Granular классификация — Plan #12+. |
| Q3 | `IngestHandler` запускает `ingest` через `asyncio.to_thread` — risk блокировки event loop'а если ingest очень long? | `to_thread` отпускает loop, OK. Worker не запускает следующий job до завершения текущего (sequential). |
| Q4 | Persist payload как JSON-text или TEXT в SQLite? | TEXT (JSON-encoded). Schema validation на boundary при чтении. |
| Q5 | Можно ли cancel'ить running job? | Нет в Plan #11. Только queued. Cancel running = риск partial state. Plan #14+ может реализовать через cooperative cancel flag. |
| Q6 | Что если daemon рестартует пока handler в-flight для job? | recover_zombie_running на startup делает requeue или dead_letter (если последняя попытка). Idempotent ingest защищён SHA-dedup в manifest. |
| Q7 | Подсистема jobs нужно ли её включать в backup стратегию? | Нет — `.jobs.db` runtime state, исключаем из snapshot. После restore .jobs.db нетронут (preserved across swap). |
| Q8 | Concurrent `claim_next_ready` race в daemon (only one writer на самом деле)? | One writer = daemon. Но `BEGIN IMMEDIATE` + `UPDATE WHERE status='queued'` атомарно — concurrency safety даже если pluraly. |
| Q9 | `payload_json` versioning — что если schema payload'а меняется в Plan #12+ (например, добавляем `language_hint` field)? | Pydantic `extra="allow"` для payload + handler сам валидирует свои поля. Old jobs в queue с old payload не ломаются. |
| Q10 | sqlite WAL: stale `.jobs.db-wal` файл на disk если daemon crash? | OK — sqlite restart corrects. WAL replay автоматический. |

---

## 6. Migration / compatibility

- **Plan #7 SessionEnd hook updated:** добавляет POST /jobs path с fallback на existing subprocess. Old behavior preserved if daemon offline.
- **CLI `mnemos ingest` без изменений** — sync, прямой. Manual users никак не затронуты.
- **`.jobs.db` появляется в каждом vault'е** при первом запуске daemon после Plan #11. Old vaults без файла — JobStore создаёт схему при первом connect.
- **No new pyproject deps.** sqlite3 — stdlib. APScheduler уже есть. httpx уже есть.
- **Watchdog handler** — `.jobs.db` начинается с точки → already skipped.
- **MCP server** — без изменений в Plan #11.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Daemon crash mid-ingest leaves zombie running job | recover_zombie_running на startup |
| Zombie job restored as queued, ingest pipeline уже частично применил writes | StagingTransaction промоут atomic — либо успех, либо rollback. SHA-dedup manifest. Idempotent. |
| `claim_next_ready` race у нескольких writers | BEGIN IMMEDIATE + UPDATE WHERE — атомарно даже без race. Daemon — единственный writer в Plan #11. |
| Hook падает с timeout если daemon медленный | timeout=2s + try/except → fallback subprocess. |
| `next_attempt_at` далёкое будущее блокирует worker от текущих ready jobs | claim_next_ready filter `next_attempt_at <= now`, не trips на future jobs. |
| APScheduler retry trigger в прошлом не fires | DateTrigger с past run_date — APScheduler logs misfire, doesn't run. Решение: при scheduling `if next_attempt_at < now: next_attempt_at = now + 1s`. |
| `.jobs.db` corrupt после disk full | sqlite.OperationalError → JobsCorruptError → 503. Manual recovery: delete .jobs.db, daemon recreate (jobs lost). Документировать. |
| Generic Exception catch в worker — может скрыть baddoc'и (KeyboardInterrupt, SystemExit) | Filter explicitly: `except Exception` (not BaseException). KeyboardInterrupt → propagates → graceful shutdown via stop event. |
| Long handler выполнения блокирует graceful shutdown | `worker.stop(timeout=10)` ждёт. После timeout — forced. Real fix — cooperative cancellation handler-side в Plan #12+. |
| Hook env loss (daemon URL not set) | default `http://127.0.0.1:5757` baked in. |

---

## 8. Estimated diff

- New files: 6 prod (`state/jobs.py`, `daemon/jobs/__init__.py`, `worker.py`, `handlers.py`, `recovery.py`, `routes/jobs.py`, `routes/dead_letter.py` = 7) + 7 test files
- Modified: `daemon/process.py`, `daemon/app.py`, `daemon/schemas.py`, `daemon/routes/health.py`, `core/snapshots.py`, `hooks/session_end.py`, `cli.py`
- LOC estimate: ~2400 prod + ~2000 tests = ~4400 total
- Branch: `feat/jobs-queue` (already created)
- Expected commits: ~13

---

## 9. Spec self-review

1. **Placeholder scan:** все sections content'ные, нет TBD. Pseudocode имеет concrete schemas. ✓

2. **Internal consistency:** retry policy — Q1 говорит MAX_ATTEMPTS=4, §3.3 same; RETRY_DELAYS_S=[30,120,1200], 3 entries — соответствует 3 retry waiting periods между 4 attempts. ✓

3. **Scope check:** один subsystem (jobs queue) с интегрированными точками (hook, snapshots, daemon). Plan может быть выполнен как single implementation plan. ✓

4. **Ambiguity check:** "3 retries" в spec amybiguous — пofiксирован Q1 как "3 retries после initial = 4 attempts total". Документировано. ✓

Spec ready for writing-plans skill.
