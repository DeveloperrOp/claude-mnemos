# Design: Sessions + Lost-sessions + Token metrics (Plan #13a — NEW)

**Status:** drafted, autonomous per Yarik's "стартуем" directive.
**Date:** 2026-04-27
**Author:** Claude.
**Predecessor:** `2026-04-27-page-edit-trash-design.md` (Plan #12, merged in `b25b09f` + 3 hotfixes).
**Successor planned:** Plan #13b (Settings + Multi-vault project_map) → Plan #13c (SessionStart adaptive context) → Plan #14 (Dashboard).

---

## 1. Goal

Дать дашборду готовые backend-views на три раздела (`💬 Sessions`, `🔍 Lost`, Token usage widget) и метрики usage без введения новых state-файлов где это не нужно.

После Plan #13a:

```bash
mnemos sessions list --vault <path>                    # all ingested + queued + dead_letter
mnemos sessions show <session_id> --vault <path>       # full details with tokens
mnemos sessions ingest <transcript_path> --vault <path>  # enqueue via /jobs

mnemos lost-sessions list --vault <path>               # transcripts not in manifest
mnemos lost-sessions scan --vault <path>               # rescan Claude Code transcripts dir
mnemos lost-sessions import <session_id> --vault <path>   # enqueue via /jobs
mnemos lost-sessions ignore <session_id> --vault <path>   # mark as ignored

mnemos metrics usage --vault <path> [--period 30d]
mnemos metrics top-sessions --vault <path> [--limit 10]
mnemos metrics timeline --vault <path> [--period 30d]
```

REST для будущего dashboard:

```
GET    /sessions                            — merged manifest + jobs view
GET    /sessions/{sid}                      — single entry
POST   /sessions/{sid}/ingest               — alias for POST /jobs

GET    /lost-sessions                       — scan result (cached)
POST   /lost-sessions/scan                  — force rescan
POST   /lost-sessions/{sid}/import          — alias for POST /jobs
POST   /lost-sessions/{sid}/ignore          — add to ignore list

GET    /metrics/usage[?period=30d]
GET    /metrics/usage/by-project            — single-entry in single-vault mode (Plan #13b multi-vault)
GET    /metrics/usage/top-sessions[?limit=10]
GET    /metrics/usage/timeline[?period=30d]
```

### Что НЕ даёт (явно отложено)

- **Settings, Multi-vault, project_map.json** → Plan #13b.
- **SessionStart adaptive context (`tiered_query`, `hot.md`)** → Plan #13c.
- **MCP tools** для sessions/metrics → Plan #14.
- **Frontend разделы** → Plan #14.
- **Per-project metrics aggregation** в Plan #13a — single-vault только. `/metrics/usage/by-project` возвращает один entry с именем "default". Multi-vault expansion — Plan #13b.

---

## 2. Architectural choice: enriched manifest, no new state file for sessions

`Manifest.IngestRecord` (Plan #2) уже хранит большую часть session metadata: `session_id`, `ingested_at`, `raw_path`, `source_path`, `created_pages`, `skipped_collisions`, `model`, `input_tokens`, `output_tokens`. Plan #13a **не добавляет** новый `<vault>/.sessions.json` файл. Вместо этого:

- **Расширяем `IngestRecord`** двумя nullable fields:
  - `transcript_path: str | None` — original transcript path before ingest (для возможности re-import/lookup).
  - `raw_transcript_bytes: int | None` — original transcript file size (для `compression_ratio` metric).

- **Sessions view** комбинирует:
  - Succeeded ingests из `manifest.ingested.values()`.
  - In-progress / failed / dead-letter из `JobStore.list_by_status` (Plan #11) с `kind="ingest"`.

- **Failed ingest** = job в queue со статусом `dead_letter` (Plan #11 already does this).

- **Lost sessions** = transcripts в Claude Code dir НЕ в manifest по SHA AND НЕ в ignore list.

- **Ignore list** — единственный новый state file: `<vault>/.lost-sessions-ignore.json` (Pydantic-validated, simple `{"version": 1, "ignored_shas": [...]}`).

Преимущество: **минимум новых файлов** (1 state file vs 4 в alt design); single-source-of-truth для каждого aspect (manifest для succeeded, jobs queue для in-flight/failed, ignore-list для user dismissals).

---

## 3. Data shapes

### 3.1 Extended `IngestRecord`

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
    # NEW:
    transcript_path: str | None = None
    raw_transcript_bytes: int | None = None
```

Старые manifest файлы parseят OK — оба новых поля имеют default `None`. Pipeline populates их при новых ingest'ах.

### 3.2 `core/sessions.py:SessionView` — merged view

```python
class SessionStatus(str, Enum):
    SUCCEEDED = "succeeded"      # in manifest
    QUEUED    = "queued"         # in jobs (status=queued)
    RUNNING   = "running"        # in jobs (status=running)
    FAILED    = "failed"         # in jobs (status=failed; mid-retry)
    DEAD_LETTER = "dead_letter"  # in jobs (status=dead_letter)


class SessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: SessionStatus
    transcript_path: str | None
    ingested_at: datetime | None         # only succeeded
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    raw_transcript_bytes: int | None
    created_pages: list[str] = Field(default_factory=list)
    error: str | None = None             # only for failed/dead_letter


def list_sessions(vault: Path) -> list[SessionView]: ...
def get_session(vault: Path, session_id: str) -> SessionView | None: ...
```

`session_id` derivation для jobs: extract from `job.payload["transcript_path"]` filename без extension. Manifest uses session_id stored at ingest time. Conflict resolution: succeeded entries take precedence over queued/running entries with same sid (e.g. re-ingest scenario).

### 3.3 `core/lost_sessions.py`

```python
LOST_SESSIONS_IGNORE_FILENAME = ".lost-sessions-ignore.json"


class LostSessionsIgnore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    ignored_shas: set[str] = Field(default_factory=set)

    @classmethod
    def load(cls, vault: Path) -> "LostSessionsIgnore": ...
    def save(self, vault: Path, *, tracker=None) -> None: ...


class LostSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str             # derived from filename stem
    transcript_path: str
    sha: str                    # sha256 hex of file content
    size_bytes: int
    mtime: datetime


def scan_lost_sessions(
    vault: Path,
    *,
    transcripts_root: Path | None = None,  # default ~/.claude/projects/
) -> list[LostSession]: ...
```

`scan_lost_sessions`:
1. Resolve `transcripts_root` (default `Path.home() / ".claude" / "projects"`).
2. Walk all `*.jsonl` files (deep traversal).
3. For each: SHA-256 of bytes, file mtime.
4. Cross-ref manifest.ingested keys (which ARE SHAs) and `LostSessionsIgnore.ignored_shas`.
5. Return entries NOT in either set.

### 3.4 `core/metrics.py`

```python
class UsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_days: int
    sessions_covered: int                # count of succeeded ingests in window
    tokens_input: int                    # sum input_tokens (None entries → 0)
    tokens_output: int                   # sum output_tokens
    tokens_injected: int                 # tokens_input + tokens_output (per spec §15 main metric)
    raw_bytes_total: int                 # sum raw_transcript_bytes
    compression_ratio: float | None      # tokens_output / raw_bytes_total (chars→tokens approx)


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

`compression_ratio` interpretation: for now `tokens_output / raw_bytes_total` (rough proxy). Spec §15 talks about "compression ratio" as "tokens injected vs. raw transcript size" — мы используем output as proxy для injected tokens. Plan #13c может пересмотреть when adaptive context lands.

### 3.5 REST schemas (request/response)

Plain dicts via `model_dump(mode="json")`. No new Pydantic schemas in `daemon/schemas.py` — endpoints return dicts directly (consistent с lint/jobs routes).

`POST /sessions/{sid}/ingest` body: `{"transcript_path": "..."}` — same shape as POST /jobs payload. Convenience: route translates to POST /jobs internally (or directly creates Job).

`POST /lost-sessions/{sid}/import` body: optional `{"transcript_path": "..."}` — if omitted, server resolves path from latest scan cache. **Cache:** `core/lost_sessions.py` caches last `scan_lost_sessions` result in-memory on the daemon (TTL 60s). `POST /lost-sessions/scan` invalidates cache + rescans synchronously (blocking).

`POST /lost-sessions/{sid}/ignore` body: `{"sha": "...", "reason": "optional"}`. Adds SHA to `LostSessionsIgnore`.

### 3.6 CLI surface

```bash
mnemos sessions list [--vault] [--status STATUS] [--limit N]
mnemos sessions show <session_id> [--vault]
mnemos sessions ingest <transcript_path> [--vault]              # → POST /sessions/{sid}/ingest

mnemos lost-sessions list [--vault]
mnemos lost-sessions scan [--vault]                              # rescan + cache
mnemos lost-sessions import <session_id> [--vault]
mnemos lost-sessions ignore <session_id> [--vault] [--reason TEXT]

mnemos metrics usage [--vault] [--period 30d]
mnemos metrics top-sessions [--vault] [--limit 10]
mnemos metrics timeline [--vault] [--period 30d]
```

Read commands (`list`, `show`, `usage`, `top-sessions`, `timeline`) — direct read через `core/sessions.py` / `core/lost_sessions.py` / `core/metrics.py`. Write commands (`ingest`, `import`, `scan`, `ignore`) — POST к daemon (need running daemon).

Exit codes: 0 success, 1 missing vault, 87 daemon offline, 91 SessionNotFoundError, 92 LostSessionNotFoundError, 93 ManifestCorruptError.

### 3.7 Daemon route wiring

3 new routers in `daemon/routes/{sessions,lost_sessions,metrics}.py`. Wire in `app.py`. No new exception handlers beyond existing `ManifestCorruptError → 503`.

### 3.8 Lost-sessions cache

`MnemosDaemon` gets a new attribute `lost_sessions_cache: LostSessionsCache` (in-memory dict keyed by transcripts_root path, TTL'd). GET /lost-sessions uses cache (rescan if expired). POST /lost-sessions/scan force-invalidates.

---

## 4. Test strategy

### Unit (per module)
- `tests/state/test_manifest.py` extended: round-trip new fields with both populated and None.
- `tests/core/test_sessions.py`: list_sessions merged manifest + jobs (succeeded + queued + dead-letter), get_session by sid, conflict resolution (succeeded > queued).
- `tests/core/test_lost_sessions.py`: scan with synthetic transcripts dir, ignore list filters, cross-ref manifest works.
- `tests/core/test_metrics.py`: usage_summary edge cases (empty manifest → zeros; all None tokens → zeros), top_sessions sort + limit, timeline buckets per-day.

### Integration / REST
- `tests/daemon/test_app_sessions.py`: GET list/by-id, POST ingest creates job.
- `tests/daemon/test_app_lost_sessions.py`: GET list/scan, POST import/ignore.
- `tests/daemon/test_app_metrics.py`: GET each metrics endpoint.

### CLI
- `tests/test_cli_sessions.py`, `test_cli_lost_sessions.py`, `test_cli_metrics.py`.

### Slow E2E
- `tests/daemon/test_sessions_metrics_e2e.py` (1 test): subprocess daemon, seed manifest entry, GET /metrics/usage returns non-zero counts. (Optional — depends on time budget.)

---

## 5. Open questions

| # | Q | Решение |
|---|---|---|
| Q1 | Где хранить session metadata: new `.sessions.json` или enriched manifest? | enriched manifest. Avoid duplication. |
| Q2 | Lost-sessions transcripts root — hardcoded `~/.claude/projects/` или env var? | env var `MNEMOS_TRANSCRIPTS_ROOT`, default `~/.claude/projects/`. |
| Q3 | `compression_ratio` formula? | `tokens_output / raw_bytes_total`. Approximation; revisit Plan #13c. |
| Q4 | Sessions cache invalidation? | Lost-sessions cache: 60s TTL + manual invalidate via POST /scan. Sessions list: no cache (manifest read each time, cheap). |
| Q5 | What about ingest jobs from non-vault transcripts (e.g. user manually invoked `mnemos jobs` for test)? | Listed under Sessions view (jobs queue is source-of-truth for in-flight). User can dismiss via /jobs/{id}/cancel. |
| Q6 | Multi-vault `/metrics/usage/by-project` in Plan #13a? | Returns one entry with `project="default"` (vault name). Plan #13b adds real per-project routing. |
| Q7 | `last_human_edit` aggregation in metrics? | Out of scope for #13a. |
| Q8 | Session "ingest" CLI command requires daemon? | Yes (uses /jobs queue per Plan #11). Without daemon → exit 87 + suggest `mnemos ingest <path> <vault>` direct CLI. |

---

## 6. Migration / compatibility

- Manifest extension: 2 new nullable fields. Backward compat — existing manifest files parse with `None`.
- `.lost-sessions-ignore.json` — new file, created on first POST /ignore.
- No new pyproject deps.
- Watchdog: `.lost-sessions-ignore.json` is dotfile → skipped.
- Snapshot: same dotfile rule via `_EXCLUDED_DIRS`/`_EXCLUDED_FILES`. NOT EXCLUDED — лost-sessions ignore IS legitimate vault state to preserve through restore. Decision: include в snapshot (don't add to excluded). Treated like manifest.
- Future Plan #13b multi-vault adds `project_map.json` global state at `~/.mnemos/`.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| `~/.claude/projects/` doesn't exist (user не run'ил Claude Code yet) | `scan_lost_sessions` returns empty list, не raises |
| Permission denied on transcripts dir | Skip + log warning, return what we got |
| Huge transcripts (100MB+) — SHA computation slow | Read in 64KB chunks (existing pattern in ingest.transcript) |
| Manifest very large (1000+ ingests over months) | Read full file each call, ~MB-ish JSON. Acceptable on local SSD; Plan #14+ may add caching layer |
| `transcript_path` in manifest may point to non-existent file (user moved Claude Code dir) | Sessions view returns the path as-is; restore/re-import will 404 if transcript missing |
| Compression ratio with raw_bytes=0 (empty transcript ingested raw_only without LLM tokens) | Return `compression_ratio=None` in summary |
| Periodic timeline boundary issues (timezone) | Use UTC date everywhere; document in CLI help |

---

## 8. Estimated diff

- New files: 3 prod (`core/sessions.py`, `core/lost_sessions.py`, `core/metrics.py`) + 3 daemon routes + ~9 test files
- Modified: `state/manifest.py` (add fields), `ingest/pipeline.py` (populate fields), `daemon/app.py` (wire 3 routers), `cli.py` (3 subgroups)
- LOC: ~2800 prod + ~2400 tests = ~5200 total
- Branch: `feat/sessions-metrics` (created)
- Expected commits: ~12

---

## 9. Spec self-review

1. **Placeholder scan:** all sections concrete. ✓
2. **Internal consistency:** session_id derivation rules consistent (manifest.session_id used as-is; jobs payload transcript filename stem for jobs-only entries). ✓
3. **Scope check:** single subsystem (session lifecycle + metrics). #13b/#13c clearly outside. ✓
4. **Ambiguity check:** compression_ratio formula explicit (Q3). Lost-sessions cache TTL explicit (Q4). ✓
