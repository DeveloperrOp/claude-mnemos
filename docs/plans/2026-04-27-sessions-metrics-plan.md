# Sessions + Lost-sessions + Token metrics Implementation Plan (Plan #13a)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` for tracking.

**Goal:** Backend views on session lifecycle (succeeded ingests + queued/running/dead-letter jobs) + lost-sessions scanner + token metrics, all reusing existing manifest+jobs state.

**Architecture:** Enrich `manifest.IngestRecord` with `transcript_path` + `raw_transcript_bytes`. Three new core modules (`sessions.py`, `lost_sessions.py`, `metrics.py`) compute views from manifest+jobs. Three new REST routers. Three new CLI subgroups. One new state file: `<vault>/.lost-sessions-ignore.json`.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest. No new third-party deps.

**Design doc:** `docs/plans/2026-04-27-sessions-metrics-design.md` — read before starting.

---

## Files map

**Create:**
- `claude_mnemos/core/sessions.py` — `SessionStatus`, `SessionView`, `list_sessions`, `get_session`, `SessionNotFoundError`
- `claude_mnemos/core/lost_sessions.py` — `LostSession`, `LostSessionsIgnore`, `LostSessionsCache`, `scan_lost_sessions`, `add_to_ignore`, `LostSessionNotFoundError`
- `claude_mnemos/core/metrics.py` — `UsageSummary`, `SessionMetric`, `TimelinePoint`, `usage_summary`, `top_sessions`, `timeline`
- `claude_mnemos/daemon/routes/sessions.py`
- `claude_mnemos/daemon/routes/lost_sessions.py`
- `claude_mnemos/daemon/routes/metrics.py`
- `tests/core/test_sessions.py`
- `tests/core/test_lost_sessions.py`
- `tests/core/test_metrics.py`
- `tests/daemon/test_app_sessions.py`
- `tests/daemon/test_app_lost_sessions.py`
- `tests/daemon/test_app_metrics.py`
- `tests/test_cli_sessions.py`
- `tests/test_cli_lost_sessions.py`
- `tests/test_cli_metrics.py`

**Modify:**
- `claude_mnemos/state/manifest.py` — add 2 fields to `IngestRecord`
- `claude_mnemos/ingest/pipeline.py` — populate `transcript_path` + `raw_transcript_bytes`
- `claude_mnemos/daemon/process.py` — `lost_sessions_cache: LostSessionsCache` attribute
- `claude_mnemos/daemon/app.py` — include 3 new routers
- `claude_mnemos/cli.py` — 3 new subgroups (`sessions`, `lost-sessions`, `metrics`)
- `tests/test_manifest.py` — extend with new field tests
- `README.md` — Plans #1-#13a status + new section

---

## Task 1: extend `IngestRecord` with transcript_path + raw_transcript_bytes

**Files:** `claude_mnemos/state/manifest.py`, `tests/test_manifest.py`

- [ ] Append failing test:

```python
def test_ingest_record_accepts_new_fields():
    rec = IngestRecord(
        session_id="abc",
        ingested_at=datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC),
        raw_path="raw/chats/abc.md",
        source_path=None,
        created_pages=[],
        skipped_collisions=[],
        model=None,
        input_tokens=None,
        output_tokens=None,
        transcript_path="/abs/path/to/abc.jsonl",
        raw_transcript_bytes=12345,
    )
    assert rec.transcript_path == "/abs/path/to/abc.jsonl"
    assert rec.raw_transcript_bytes == 12345


def test_ingest_record_new_fields_optional():
    rec = IngestRecord(
        session_id="abc",
        ingested_at=datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC),
        raw_path="raw/chats/abc.md",
        source_path=None,
        created_pages=[],
        skipped_collisions=[],
        model=None,
        input_tokens=None,
        output_tokens=None,
    )
    assert rec.transcript_path is None
    assert rec.raw_transcript_bytes is None


def test_manifest_round_trip_with_new_fields(tmp_path: Path):
    m = Manifest()
    m.add(
        "sha-abc",
        IngestRecord(
            session_id="abc", ingested_at=datetime.now(UTC),
            raw_path="raw/chats/abc.md", source_path=None,
            created_pages=[], skipped_collisions=[],
            model=None, input_tokens=None, output_tokens=None,
            transcript_path="/x.jsonl", raw_transcript_bytes=1024,
        ),
    )
    m.save(tmp_path)
    loaded = Manifest.load(tmp_path)
    rec = loaded.ingested["sha-abc"]
    assert rec.transcript_path == "/x.jsonl"
    assert rec.raw_transcript_bytes == 1024
```

- [ ] Run, confirm fail.
- [ ] Add fields to `IngestRecord`:

```python
class IngestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    ingested_at: datetime
    raw_path: str
    source_path: str | None
    created_pages: list[str] = Field(default_factory=list)
    skipped_collisions: list[str] = Field(default_factory=list)
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    transcript_path: str | None = None
    raw_transcript_bytes: int | None = None
```

- [ ] Run pytest + ruff + mypy.
- [ ] Commit:

```
feat(state): extend IngestRecord with transcript_path + raw_transcript_bytes

Plan #13a Task 1. Adds two nullable fields to manifest.IngestRecord:
transcript_path stores the absolute transcript path before ingest, used
by sessions view + lost-sessions cross-ref. raw_transcript_bytes stores
the original file size, used by metrics.compression_ratio. Both nullable
for backward compat with existing manifests.
```

---

## Task 2: pipeline populates new fields

**Files:** `claude_mnemos/ingest/pipeline.py`, `tests/test_pipeline.py`

- [ ] Locate `IngestRecord(...)` construction(s) in `pipeline.py:96-113` and `pipeline.py:193-206`. Both call sites should populate:
  - `transcript_path=str(jsonl_path.resolve())`
  - `raw_transcript_bytes=len(raw_bytes)`  (raw_bytes already exists on line 64)

- [ ] Append a test that asserts manifest entries after ingest have non-None new fields:

```python
def test_ingest_populates_transcript_path_and_bytes(tmp_path: Path, monkeypatch):
    """After raw_only ingest the manifest entry has new fields populated."""
    # Use existing test fixture infrastructure (tests/test_pipeline.py has helpers)
    ...
    result = ingest(jsonl_path, vault, cfg=cfg, llm_client=None, extract=False, today=date.today())
    manifest = Manifest.load(vault)
    rec = next(iter(manifest.ingested.values()))
    assert rec.transcript_path == str(jsonl_path.resolve())
    assert rec.raw_transcript_bytes == jsonl_path.stat().st_size
```

(Look at existing pipeline tests for fixture patterns; mirror them.)

- [ ] Run, commit `feat(ingest): populate transcript_path + raw_transcript_bytes in IngestRecord`.

---

## Task 3: `core/sessions.py` — merged manifest + jobs view

**Files:** `claude_mnemos/core/sessions.py`, `tests/core/test_sessions.py`

Read design §3.2 for full schema.

- [ ] Define:

```python
from enum import Enum

class SessionStatus(str, Enum):
    SUCCEEDED   = "succeeded"
    QUEUED      = "queued"
    RUNNING     = "running"
    FAILED      = "failed"
    DEAD_LETTER = "dead_letter"


class SessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    status: SessionStatus
    transcript_path: str | None
    ingested_at: datetime | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    raw_transcript_bytes: int | None
    created_pages: list[str] = Field(default_factory=list)
    error: str | None = None


class SessionNotFoundError(LookupError):
    pass


def list_sessions(vault: Path) -> list[SessionView]:
    """Merge succeeded entries from manifest with in-flight jobs (kind=ingest).
    Sort by ingested_at desc (None ingested_at = use job created_at).
    """

def get_session(vault: Path, session_id: str) -> SessionView:
    """Returns SessionView or raises SessionNotFoundError."""
```

Implementation flow для `list_sessions`:
1. Load manifest. For each `IngestRecord` → `SessionView(status=SUCCEEDED, ingested_at=..., model=..., tokens=..., transcript_path=..., raw_transcript_bytes=..., created_pages=...)`.
2. Open `JobStore`. List jobs `kind="ingest"` not in successful manifest set. Each job → `SessionView(session_id=derived_from_payload_path_stem, status=...job.status, transcript_path=job.payload.transcript_path, error=job.error)`.
3. Conflict resolution: if same session_id appears in both — succeeded wins (drop the job entry).
4. Sort: succeeded by `ingested_at` desc, others by `now` (newest jobs first).

`session_id` for jobs:
```python
def _sid_from_job_payload(payload: dict) -> str:
    p = payload.get("transcript_path", "")
    return Path(p).stem if p else f"job-{payload.get('id', 'unknown')}"
```

Tests (~6):
- empty vault → []
- 2 succeeded manifest entries → 2 SessionViews with status=SUCCEEDED
- 1 succeeded + 1 queued job (different sids) → 2 entries
- 1 succeeded + 1 dead-letter same sid → 1 entry (succeeded wins)
- get_session raises SessionNotFoundError on missing
- new IngestRecord fields surface (transcript_path + raw_transcript_bytes in view)

Commit `feat(core): sessions view (merged manifest + jobs queue)`.

---

## Task 4: `core/lost_sessions.py`

**Files:** `claude_mnemos/core/lost_sessions.py`, `tests/core/test_lost_sessions.py`

Read design §3.3.

- [ ] Define:

```python
LOST_SESSIONS_IGNORE_FILENAME = ".lost-sessions-ignore.json"


class LostSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    transcript_path: str
    sha: str
    size_bytes: int
    mtime: datetime


class LostSessionNotFoundError(LookupError):
    pass


class LostSessionsIgnore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    ignored_shas: set[str] = Field(default_factory=set)

    @classmethod
    def load(cls, vault: Path) -> "LostSessionsIgnore":
        path = vault / LOST_SESSIONS_IGNORE_FILENAME
        if not path.is_file():
            return cls()
        ...

    def save(self, vault: Path, *, tracker=None) -> None:
        ...


def scan_lost_sessions(
    vault: Path,
    *,
    transcripts_root: Path | None = None,
) -> list[LostSession]:
    """Scan transcripts_root (default ~/.claude/projects/), SHA each .jsonl,
    cross-ref manifest + ignore list. Returns sessions NOT in either.
    Tolerates missing transcripts_root (returns []).
    """


class LostSessionsCache:
    """In-memory cache for daemon — lazily rescans with TTL=60s."""
    DEFAULT_TTL_S = 60.0
    def __init__(self, ttl_s: float = DEFAULT_TTL_S) -> None: ...
    def get_or_scan(self, vault: Path, *, transcripts_root: Path | None = None) -> list[LostSession]: ...
    def invalidate(self) -> None: ...


def add_to_ignore(vault: Path, sha: str, *, tracker=None) -> LostSessionsIgnore: ...
```

Implementation для `scan_lost_sessions`:
1. Resolve `transcripts_root`: `transcripts_root or os.environ.get("MNEMOS_TRANSCRIPTS_ROOT") or Path.home() / ".claude" / "projects"`.
2. If not exists → return [].
3. Walk via `rglob("*.jsonl")`. For each: open in chunks, SHA-256, file size, mtime.
4. Load `Manifest.load(vault).ingested.keys()` (= set of SHAs) AND `LostSessionsIgnore.load(vault).ignored_shas`.
5. Yield only entries NOT in either set.

`session_id` for LostSession: filename stem (without `.jsonl`).

Tests (~7):
- empty transcripts_root → []
- non-existent transcripts_root → []
- transcripts_root with 3 jsonl files, all in manifest → []
- transcripts_root with 3 jsonl, 2 in manifest, 1 lost → 1 entry
- ignore list filters → entry skipped
- LostSessionsIgnore.save/load round-trip
- LostSessionsCache TTL behavior

Commit `feat(core): lost-sessions scanner + ignore list`.

---

## Task 5: `core/metrics.py`

**Files:** `claude_mnemos/core/metrics.py`, `tests/core/test_metrics.py`

Read design §3.4.

- [ ] Define types:

```python
from datetime import date as date_class

class UsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_days: int
    sessions_covered: int
    tokens_input: int
    tokens_output: int
    tokens_injected: int
    raw_bytes_total: int
    compression_ratio: float | None


class SessionMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    ingested_at: datetime
    tokens_input: int | None
    tokens_output: int | None
    tokens_total: int | None
    raw_bytes: int | None


class TimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date_class
    sessions: int
    tokens_input: int
    tokens_output: int


def usage_summary(vault: Path, *, period_days: int = 30, today: date_class | None = None) -> UsageSummary: ...
def top_sessions(vault: Path, *, limit: int = 10) -> list[SessionMetric]: ...
def timeline(vault: Path, *, period_days: int = 30, today: date_class | None = None) -> list[TimelinePoint]: ...
```

Implementation:
- `usage_summary`: load manifest, filter records by `ingested_at.date() >= today - period_days`. Sum tokens. `tokens_injected = tokens_input + tokens_output`. `compression_ratio = tokens_output / raw_bytes_total` if `raw_bytes_total > 0` else None.
- `top_sessions`: sort all records by (input+output) tokens desc, return first `limit`.
- `timeline`: bucket by `ingested_at.date()`, count sessions + sum tokens per day. Fill missing days with zeros for clean charting (last `period_days` days).

Tests (~6):
- empty manifest → zeros, compression_ratio=None
- 3 records summed correctly
- period_days filter excludes old entries
- top_sessions sort correct, respects limit
- timeline buckets correct
- compression_ratio=None when raw_bytes_total=0

Commit `feat(core): token usage metrics aggregations`.

---

## Task 6-8: REST routes (sessions, lost_sessions, metrics)

**Files:** 3 routers + 3 test files. Wire in `app.py` (Task 8 separately).

For each router, follow existing `daemon/routes/lint.py` style: pull `vault_root` from `app.state.vault_root`, call core module, return `model_dump(mode="json")`. 503 if `daemon.job_store` missing on sessions route (sessions view needs jobs queue).

### Task 6: sessions routes

```python
# routes/sessions.py
@router.get("/sessions")
async def list_sessions_route(request: Request, status: str | None = None, limit: int = 50) -> dict:
    vault = request.app.state.vault_root
    sessions = core_sessions.list_sessions(vault)
    if status:
        sessions = [s for s in sessions if s.status.value == status]
    return {"sessions": [s.model_dump(mode="json") for s in sessions[:limit]], "total": len(sessions)}

@router.get("/sessions/{session_id}")
async def get_session_route(session_id: str, request: Request) -> dict:
    try:
        session = core_sessions.get_session(request.app.state.vault_root, session_id)
    except SessionNotFoundError:
        raise HTTPException(404, {"error": "not_found", "session_id": session_id})
    return session.model_dump(mode="json")

@router.post("/sessions/{session_id}/ingest", status_code=201)
async def ingest_session_route(session_id: str, request: Request, body: dict) -> dict:
    """Body: {"transcript_path": "..."}. Creates a job in the daemon queue."""
    daemon = request.app.state.daemon
    if daemon is None or daemon.job_store is None:
        raise HTTPException(503, {"error": "jobs_subsystem_unavailable"})
    transcript_path = body.get("transcript_path")
    if not isinstance(transcript_path, str) or not Path(transcript_path).is_file():
        raise HTTPException(400, {"error": "missing_or_invalid_transcript_path"})
    job = daemon.job_store.create(kind="ingest", payload={"transcript_path": transcript_path})
    if daemon.job_worker is not None:
        daemon.job_worker.signal_wakeup()
    return job.model_dump(mode="json")
```

Tests: list, list with status filter, get, get 404, ingest creates job, ingest 400 missing path.

Commit `feat(daemon): /sessions routes for list/get/ingest`.

### Task 7: lost-sessions routes

```python
@router.get("/lost-sessions")
async def list_lost_route(request: Request) -> dict:
    daemon = request.app.state.daemon
    cache = getattr(daemon, "lost_sessions_cache", None) if daemon else None
    if cache is None:
        # daemon not present (e.g. tests with FakeDaemon without cache attr) — scan synchronously
        items = core_lost_sessions.scan_lost_sessions(request.app.state.vault_root)
    else:
        items = cache.get_or_scan(request.app.state.vault_root)
    return {"sessions": [s.model_dump(mode="json") for s in items], "total": len(items)}

@router.post("/lost-sessions/scan")
async def rescan_route(request: Request) -> dict:
    daemon = request.app.state.daemon
    if daemon and getattr(daemon, "lost_sessions_cache", None):
        daemon.lost_sessions_cache.invalidate()
    items = core_lost_sessions.scan_lost_sessions(request.app.state.vault_root)
    if daemon and getattr(daemon, "lost_sessions_cache", None):
        daemon.lost_sessions_cache._cached = items   # primitive cache update; refactor as needed
    return {"sessions": [s.model_dump(mode="json") for s in items], "total": len(items)}

@router.post("/lost-sessions/{session_id}/import", status_code=201)
async def import_route(session_id: str, request: Request, body: dict) -> dict:
    """Body optionally {"transcript_path": "..."}. If omitted, looks up via scan."""
    transcript_path = body.get("transcript_path")
    if not transcript_path:
        items = core_lost_sessions.scan_lost_sessions(request.app.state.vault_root)
        match = next((i for i in items if i.session_id == session_id), None)
        if match is None:
            raise HTTPException(404, {"error": "lost_session_not_found", "session_id": session_id})
        transcript_path = match.transcript_path
    daemon = request.app.state.daemon
    if daemon is None or daemon.job_store is None:
        raise HTTPException(503, {"error": "jobs_subsystem_unavailable"})
    job = daemon.job_store.create(kind="ingest", payload={"transcript_path": transcript_path})
    if daemon.job_worker is not None:
        daemon.job_worker.signal_wakeup()
    return job.model_dump(mode="json")

@router.post("/lost-sessions/{session_id}/ignore", status_code=200)
async def ignore_route(session_id: str, request: Request, body: dict) -> dict:
    sha = body.get("sha")
    if not sha:
        # Resolve from scan
        items = core_lost_sessions.scan_lost_sessions(request.app.state.vault_root)
        match = next((i for i in items if i.session_id == session_id), None)
        if match is None:
            raise HTTPException(404, {"error": "lost_session_not_found"})
        sha = match.sha
    ig = core_lost_sessions.add_to_ignore(request.app.state.vault_root, sha)
    return {"ignored_count": len(ig.ignored_shas)}
```

Tests: list, scan, import 404 + 201 + 503 (no daemon), ignore.

Commit `feat(daemon): /lost-sessions routes for scan/import/ignore`.

### Task 8: metrics routes

```python
@router.get("/metrics/usage")
async def usage_route(request: Request, period: str = "30d") -> dict:
    days = _parse_period(period)  # "30d" → 30; "7d" → 7
    summary = core_metrics.usage_summary(request.app.state.vault_root, period_days=days)
    return summary.model_dump(mode="json")

@router.get("/metrics/usage/by-project")
async def by_project_route(request: Request) -> dict:
    """Single-vault now: returns one entry. Plan #13b adds real per-project."""
    summary = core_metrics.usage_summary(request.app.state.vault_root)
    return {"projects": [{"project": "default", **summary.model_dump(mode="json")}]}

@router.get("/metrics/usage/top-sessions")
async def top_sessions_route(request: Request, limit: int = 10) -> dict:
    items = core_metrics.top_sessions(request.app.state.vault_root, limit=limit)
    return {"sessions": [m.model_dump(mode="json") for m in items]}

@router.get("/metrics/usage/timeline")
async def timeline_route(request: Request, period: str = "30d") -> dict:
    days = _parse_period(period)
    points = core_metrics.timeline(request.app.state.vault_root, period_days=days)
    return {"points": [p.model_dump(mode="json") for p in points]}


def _parse_period(period: str) -> int:
    if period.endswith("d"):
        try:
            return int(period[:-1])
        except ValueError:
            pass
    raise HTTPException(400, {"error": "invalid_period_format", "expected": "Nd"})
```

Tests: 4 endpoints, default and explicit period, 400 on bad period.

Commit `feat(daemon): /metrics/usage routes`.

### Wire all 3 routers in `app.py`

After Tasks 6-8 (or as final step in Task 8):

```python
from claude_mnemos.daemon.routes.sessions import router as sessions_router
from claude_mnemos.daemon.routes.lost_sessions import router as lost_sessions_router
from claude_mnemos.daemon.routes.metrics import router as metrics_router

app.include_router(sessions_router)
app.include_router(lost_sessions_router)
app.include_router(metrics_router)
```

Also add `lost_sessions_cache` attribute to `MnemosDaemon.__init__`:

```python
from claude_mnemos.core.lost_sessions import LostSessionsCache
self.lost_sessions_cache = LostSessionsCache()
```

---

## Tasks 9-11: CLI subgroups

Mirror existing `mnemos jobs` / `mnemos lint` / `mnemos page` patterns. Read commands direct (no daemon needed for `sessions list/show`, `lost-sessions list`, `metrics *`). Write commands (`sessions ingest`, `lost-sessions scan/import/ignore`) hit daemon REST.

Exit codes: 0/1/87/91/92/93 per design §3.6.

Each subgroup ~5-7 tests (parser + main dispatch + at least one direct + one daemon path mocked).

Commits:
- `feat(cli): mnemos sessions subgroup`
- `feat(cli): mnemos lost-sessions subgroup`
- `feat(cli): mnemos metrics subgroup`

---

## Task 12: README + memory + merge

- README: bump status to Plans #1-#13a. Add new "Sessions + Metrics" section listing CLI commands + REST endpoints. Update test counts.
- Memory file: add "Что нового после Plan #13a" section. Add to "История main".
- Merge non-FF to main. Branch cleanup after.

Commit and merge per usual.

---

## Definition of Done

- [ ] All 12 tasks committed on `feat/sessions-metrics`
- [ ] `pytest -q` green
- [ ] `pytest -q -m slow` green
- [ ] `ruff check .` clean
- [ ] `mypy claude_mnemos` clean
- [ ] README + memory updated
- [ ] Merged to `main` via non-FF
- [ ] feat/sessions-metrics branch deleted after merge
