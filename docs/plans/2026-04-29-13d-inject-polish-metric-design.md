# Plan #13d — SessionStart inject polish + §15 compression_ratio metric (design)

**Date:** 2026-04-29
**Status:** Design
**Goal:** Close the 4 small tech debts from Plan #13c (log timestamps, SKIP_SOURCES comment, slug helper dedup, double `read_page` perf) and land spec §15 compression_ratio metric — the only remaining piece of spec v0.2 that wasn't shipped (deferred at the end of #13c).

---

## 1. Background

After Plan #13c the SessionStart hook works end-to-end (cwd → project → graph → score → markdown bundle → `additionalContext`). Five tech debts remain:

1. **Inject log timestamps** — `~/.claude-mnemos/inject.log` lines have no timestamp prefix; debugging stale logs is annoying.
2. **`SKIP_SOURCES` comment** — `frozenset({"resume", "compact", "edit"})` skips four payload sources; `"edit"` reason isn't obvious to future readers.
3. **Slug helper dedup** — `page_slug_from_path` in `core/session_start.py` and `_slug_for` in `core/graph.py` are byte-identical. Consolidate.
4. **Double `read_page`** — graph builder reads each `wiki/**/*.md` once; `build_adaptive_context` reads candidates again. On a 500-page vault that's 600 disk reads where 500 would suffice. Also load-bearing for the §15 metric (need parsed bodies in scope to compute `tokens_full` cheaply).
5. **§15 compression_ratio metric** — spec v0.2 §15 mandates a `state/inject-metrics.json` (we go per-vault `.inject-metrics.json` per mnemos convention), event records `{timestamp, session_id, project, operation, mode, tokens_full, tokens_actual}`, aggregator `avg_compression_ratio = mean(tokens_full / tokens_actual for e if tokens_actual > 0)`, surfaced via `/metrics/usage` extension and dashboard widget.

### Why one plan, not two

Recon recommended split. I'm going monolith because:
- Items 1-3 are 1-line each, doesn't justify a separate merge.
- Item 4 is required by item 5 (parsed pages must be in scope for stats computation), so they land together.
- Total scope ≈ 12-14 tasks — same shape as #14b-2 / #14c.

### Out of scope (deferred)

- **Activity entry on inject** — needs new daemon POST route + httpx call from hook + daemon-down graceful degradation. Recon flagged it non-trivial. The literal `"session_start_inject"` op_type is reserved; daemon path lands in a future plan if needed.
- **`state/graph.json` cache + watchdog invalidate** — premature optim until we see real-vault performance issues.
- **Pricing / $ savings** — spec §15 explicitly says "no $ pricing, only counts". We honor that.
- **MCP `get_session_context` tool** — out of scope; hook channel is sufficient.

---

## 2. Architecture

### 2.1 State file: `.inject-metrics.json` (per-vault)

Schema mirrors `state/activity.py` patterns (Pydantic `BaseModel`, `extra="forbid"`, `load`/`save`/`append`):

```python
# claude_mnemos/state/inject_metrics.py
INJECT_METRICS_FILENAME = ".inject-metrics.json"

InjectMode = Literal["full", "trimmed", "empty"]
InjectOperation = Literal["session_start"]

class InjectMetricEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str                       # ULID
    timestamp: datetime
    session_id: str | None        # nullable — payload may not carry it
    operation: InjectOperation
    mode: InjectMode
    tokens_full: int              # ceil(chars_full / 4)
    tokens_actual: int            # ceil(chars_actual / 4)
    candidates_total: int         # graph BFS pool size
    candidates_packed: int        # how many actually emitted

class InjectMetricsLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    events: list[InjectMetricEvent] = Field(default_factory=list)

    @classmethod
    def load(cls, vault_root: Path) -> "InjectMetricsLog": ...
    def save(self, vault_root: Path) -> None: ...
    def append(self, event: InjectMetricEvent, vault_root: Path) -> None: ...
```

**Per-vault, not global**, despite spec literal `state/inject-metrics.json`. Mnemos went per-vault for everything in #13b-α/β1 — `.activity.json`, `.manifest.json`, `.jobs.db` all live at vault root. This is internally consistent and matches the multi-vault aggregator pattern.

**Retention.** Spec §15.6 says 365d retention. `append()` calls a `_cleanup_old_events(retention_days=365)` filter on save. Cap secondarily at `MAX_EVENTS = 10_000` to avoid unbounded growth on a server with 100+ daily sessions for years.

### 2.2 `build_adaptive_context_with_stats` — instrumented variant

Refactor `core/session_start.py::build_adaptive_context` to internally compute both numbers via a single pass. Public API:

```python
@dataclass(frozen=True)
class InjectStats:
    tokens_full: int       # ceil(chars_full / 4)
    tokens_actual: int     # ceil(chars_actual / 4)
    candidates_total: int
    candidates_packed: int
    mode: Literal["full", "trimmed", "empty"]

def build_adaptive_context_with_stats(
    vault: Path, *, cwd: Path, max_chars: int = 40_000, ...,
) -> tuple[str, InjectStats]: ...

def build_adaptive_context(...) -> str:
    """Backward-compatible wrapper that drops the stats."""
    context, _ = build_adaptive_context_with_stats(...)
    return context
```

**Computation:** loop through `scored` and build all blocks first (ignoring budget), summing into `chars_full`. Then greedy-pack with budget for `chars_actual`. Both passes share already-loaded `parsed` pages — no re-IO. **Mode** = `"empty"` if no scored pages, `"full"` if all packed (`chars_full ≤ max_chars`), `"trimmed"` otherwise.

The hook calls `_with_stats`; library callers (none currently) use the wrapper.

### 2.3 Graph builder — thread parsed pages through

`build_page_graph` already calls `read_page` on every file. Cheapest refactor:

```python
def build_page_graph(vault: Path) -> dict[str, set[str]]: ...  # unchanged

def build_page_graph_with_pages(
    vault: Path,
) -> tuple[dict[str, set[str]], dict[str, ParsedPage]]:
    """Same graph plus a slug → ParsedPage map for already-loaded files.
    Bad pages still skipped silently — only valid pages appear in the map.
    """
    ...
```

**Two functions, not one** — keeps the simple `build_page_graph` cheap for callers that don't need the page bodies (e.g. lint module if it ever uses graph). Adds 8 lines.

`build_adaptive_context_with_stats` calls `build_page_graph_with_pages`, looks up `pages[slug]` instead of re-`read_page(page_path)`. Drops the inner `try/except PageParseError` (page is either in the map or it's not). **Eliminates the double-read.**

Signature changes:
- `build_page_graph` keeps backward-compat (just returns adjacency).
- `build_page_graph_with_pages` is new.
- `build_adaptive_context` and `_with_stats` use `_with_pages`.

### 2.4 Hook writes the event directly

Hook flow (modified):

```python
context, stats = build_adaptive_context_with_stats(
    vault, cwd=cwd, max_chars=DEFAULT_MAX_CHARS,
)
if not context:
    return 0  # silent skip

event = InjectMetricEvent(
    id=str(ulid.ulid()),
    timestamp=datetime.now(UTC),
    session_id=payload.get("session_id"),
    operation="session_start",
    mode=stats.mode,
    tokens_full=stats.tokens_full,
    tokens_actual=stats.tokens_actual,
    candidates_total=stats.candidates_total,
    candidates_packed=stats.candidates_packed,
)
try:
    InjectMetricsLog.append_to_vault(vault, event)
except Exception as exc:
    _log(f"metric write failed: {exc}")
# Always emit context regardless of metric write outcome.

print(json.dumps({
    "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}
}))
```

**Hook owns the write** — no daemon dep. `atomic_write` handles concurrency. If two sessions start simultaneously and both append, last-writer-wins on file replace is OK because event IDs are unique ULIDs and the load-modify-save window is tiny.

**ULID dependency** — `python-ulid` likely already used (check `pyproject.toml`). If not, fallback to `uuid.uuid4().hex` — unique enough for this purpose.

### 2.5 `compression_summary` aggregator

Add to `core/metrics.py`:

```python
class CompressionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_days: int
    events_count: int
    sessions_covered: int       # unique session_ids
    avg_compression_ratio: float | None  # None if no events with tokens_actual > 0
    total_tokens_full: int
    total_tokens_actual: int

def compression_summary(
    vault: Path, *, period_days: int = 30, today: date | None = None,
) -> CompressionSummary:
    today = today or datetime.now(UTC).date()
    cutoff = today - timedelta(days=period_days)
    log = InjectMetricsLog.load(vault)
    events = [e for e in log.events if e.timestamp.date() >= cutoff]
    valid = [e for e in events if e.tokens_actual > 0]
    avg = (
        sum(e.tokens_full / e.tokens_actual for e in valid) / len(valid)
        if valid else None
    )
    return CompressionSummary(
        period_days=period_days,
        events_count=len(events),
        sessions_covered=len({e.session_id for e in events if e.session_id}),
        avg_compression_ratio=avg,
        total_tokens_full=sum(e.tokens_full for e in events),
        total_tokens_actual=sum(e.tokens_actual for e in events),
    )
```

UTC-anchored (matches #14e parity fix). Pure function, deterministic.

### 2.6 Daemon endpoint extension

Two surfaces, both small:

**A.** Extend `/metrics/usage` response with two new fields:

```python
{
    "period": "30d",
    ...existing fields...,
    "avg_compression_ratio": 6.3,          # NEW (nullable)
    "inject_events_count": 47,             # NEW
}
```

These come from `compression_summary` aggregated across vaults via `all_runtimes`.

**B.** Optionally add `/metrics/inject/timeline?period=30d` for chart. Returns daily event counts + avg ratio. **Defer if scope tight** — `/metrics/usage` extension already enables a single-card display.

**Scope decision:** Ship only (A) in #13d. Timeline can come later if user wants a graph. Reduces frontend scope to a small extension of `<UsageWidget>` instead of a new chart.

### 2.7 Frontend — extend UsageWidget

Single change. `frontend/src/types/UsageSummary.ts` adds two fields:

```ts
avg_compression_ratio: z.number().nullable(),
inject_events_count: z.number().int().nonnegative().default(0),
```

`<UsageWidget>` component (`frontend/src/components/widgets/UsageWidget.tsx`) displays:

```
Sessions: 12 · Tokens in: 100k · Tokens out: 200k
Inject: 47 events · 6.3x avg compression
```

When `avg_compression_ratio === null` (no events yet), display "Inject: 0 events" only. Translation keys: `metrics.inject_events`, `metrics.avg_compression`.

**No new chart, no new widget file.** The metric is informational, not chart-worthy yet (chart needs a timeline endpoint that we deferred).

### 2.8 Polish items in detail

**(1) Inject log timestamps.** `_log(msg)` in `hooks/session_start.py` becomes:

```python
def _log(msg: str) -> None:
    try:
        log_path = Path.home() / ".claude-mnemos" / "inject.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(UTC).isoformat()} {msg}\n")
    except Exception:
        pass
```

**(2) SKIP_SOURCES comment.**

```python
# resume: claude is restoring an existing session; it already has prior context
#         (no need to re-inject).
# compact: claude just ran context compaction; injecting more content would
#          undo what the user asked for.
# edit: PostToolUse-triggered partial source — not a fresh session, the model
#        is mid-flight and any inject would land in an unpredictable position.
SKIP_SOURCES = frozenset({"resume", "compact", "edit"})
```

**(3) Slug helper dedup.** Both `core/session_start.py::page_slug_from_path` and `core/graph.py::_slug_for` compute identically (`relative_to(vault/wiki).with_suffix("").replace("\\", "/")`). Move the canonical impl to a single location. Recon found `core/slug.py` may exist — verify; if not, put it in `core/page_io.py` (already imports paths). **Recommendation:** add `slug_from_page_path(vault, page_path)` to `core/page_io.py`, drop both duplicates, import from there.

**(4) Double read_page perf.** Covered in §2.3 — `build_page_graph_with_pages` returns the parsed-pages map.

---

## 3. Data flow

```
SessionStart hook stdin
  ↓ payload {cwd, session_id, source, ...}
hooks/session_start.py
  ├─ source filter, recursion guard, project resolve (existing)
  └─ build_adaptive_context_with_stats(vault, cwd=cwd, max_chars=...)
      ├─ build_page_graph_with_pages(vault) → graph + pages dict
      ├─ pages_within_k_hops → candidates
      ├─ score each (using already-loaded parsed pages)
      ├─ build all blocks (no budget) → chars_full
      ├─ greedy pack with budget → chars_actual + final markdown
      └─ return (markdown, InjectStats)
          ↓
  ├─ InjectMetricsLog.append_to_vault(vault, event)
  │     (atomic_write to <vault>/.inject-metrics.json, retention cleanup)
  └─ stdout JSON {hookSpecificOutput: {additionalContext, ...}}

Daemon /metrics/usage
  ├─ for each runtime: compression_summary(vault, period_days)
  ├─ aggregate avg_compression_ratio (weighted-by-events) and total events_count
  └─ extend response with avg_compression_ratio + inject_events_count

Frontend UsageWidget
  └─ render "Inject: N events · X.Yx avg compression"
```

---

## 4. New / changed files

**New:**
- `claude_mnemos/state/inject_metrics.py` — `InjectMetricEvent`, `InjectMetricsLog`, `INJECT_METRICS_FILENAME`.
- `tests/test_inject_metrics.py` — load/save/append/cleanup unit tests.

**Modified:**
- `claude_mnemos/core/page_io.py` — add `slug_from_page_path` helper.
- `claude_mnemos/core/graph.py` — add `build_page_graph_with_pages`; replace `_slug_for` with import from `page_io`.
- `claude_mnemos/core/session_start.py` — refactor to `_with_stats` variant; remove `page_slug_from_path` duplicate; thread parsed pages.
- `claude_mnemos/core/metrics.py` — add `CompressionSummary` + `compression_summary()`.
- `claude_mnemos/daemon/routes/metrics.py` — extend `/metrics/usage` response with two new fields, aggregating across vaults.
- `claude_mnemos/daemon/schemas.py` (or wherever `UsageSummary` Pydantic for routes lives) — extend response model.
- `hooks/session_start.py` — add timestamp to `_log`, add `SKIP_SOURCES` comment, call `_with_stats`, write event.
- `frontend/src/types/UsageSummary.ts` — extend zod schema.
- `frontend/src/components/widgets/UsageWidget.tsx` — render the two new fields.
- `frontend/public/locales/{en,uk,ru}.json` — add `metrics.inject_events`, `metrics.avg_compression`.
- `tests/test_session_start.py`, `tests/test_graph.py` — update for new return shapes.

---

## 5. Testing strategy

**Backend (~25 new tests):**
- `test_inject_metrics.py`:
  - empty vault → load returns empty log
  - append single event → load returns it
  - append > MAX_EVENTS → oldest dropped
  - retention 365d cleanup on save
  - JSON malformed → raises `InjectMetricsCorruptError`
- `test_session_start.py` (extends):
  - `_with_stats` returns InjectStats with both counts
  - `mode == "empty"` when no scored pages
  - `mode == "full"` when all candidates fit
  - `mode == "trimmed"` when at least one candidate dropped
  - parsed-pages dict consumed (no second `read_page`)
- `test_graph.py` (extends):
  - `build_page_graph_with_pages` returns same graph + pages dict
  - bad pages skipped from both graph and pages dict
- `test_metrics.py`:
  - `compression_summary` empty → events_count=0, avg=None
  - one event with tokens_full=1000 tokens_actual=200 → avg=5.0
  - multiple events → mean of ratios
  - period filter excludes old events
- `test_session_start_hook.py` (extend existing):
  - hook writes event to `.inject-metrics.json` after emit
  - hook silent when metric-write fails (filesystem error)
  - log line has ISO8601 prefix

**Frontend (~3 new Vitest tests):**
- `api-usage-summary.test.ts`: schema accepts `avg_compression_ratio: null` and `avg_compression_ratio: 6.3`.
- `UsageWidget.test.tsx`: renders "Inject: 47 events · 6.3x avg compression" when fields present.
- `UsageWidget.test.tsx`: renders "Inject: 0 events" when `avg_compression_ratio === null`.

---

## 6. Acceptance criteria

1. ✅ `~/.claude-mnemos/inject.log` lines have ISO8601 timestamp prefix.
2. ✅ `SKIP_SOURCES` has a 3-line explanatory comment.
3. ✅ Single canonical slug helper used everywhere (no duplicates).
4. ✅ `build_adaptive_context_with_stats` returns `(str, InjectStats)`; backward-compat wrapper preserves old API.
5. ✅ `build_page_graph_with_pages` returns parsed-pages dict; double `read_page` eliminated.
6. ✅ `.inject-metrics.json` per-vault state file with `InjectMetricEvent` schema.
7. ✅ Hook writes event after every successful inject. Failure to write metric does NOT block the inject.
8. ✅ `compression_summary(vault, period_days)` returns correct ratio; UTC-anchored.
9. ✅ `/metrics/usage` response includes `avg_compression_ratio` (nullable) + `inject_events_count`.
10. ✅ `<UsageWidget>` displays both fields; null ratio → "0 events" only.
11. ✅ ~28 new tests (25 backend + 3 frontend); all pass.
12. ✅ Backend baseline holds (1269 → ~1295).
13. ✅ Frontend Vitest baseline holds (174 → 177).
14. ✅ ruff + tsc + ESLint clean.
15. ⚠️ Manual smoke: open a session, verify event appears in `.inject-metrics.json` and shows in dashboard.

---

## 7. Risks

- **ULID dep absence.** If `python-ulid` not in `pyproject.toml`, fallback to `uuid.uuid4().hex` is fine — only need uniqueness.
- **Concurrent hook writes.** Two sessions start simultaneously, both append. `atomic_write` (load → modify → temp-write → rename) is not concurrency-safe — last writer wins. Loss is one event; acceptable. Real fix needs a lock file; defer.
- **Retention cleanup cost.** Filtering 10 000 events per write is O(n). Negligible — once per session. No issue.
- **Per-vault file conflicts spec literal.** Spec says `state/inject-metrics.json` (global). Mnemos says per-vault. Document the deviation in module docstring; not a contract break — spec is internal.
- **Frontend zod default.** `inject_events_count: z.number().int().nonnegative().default(0)` lets us add the field without breaking older daemon responses. `avg_compression_ratio: z.number().nullable()` fails on missing key. Set `.default(null)` to be safe.
- **`UsageSummary` is consumed by other widgets** (UsageByProjectTable, etc.). Verify the schema extension doesn't break by-project response which doesn't include compression fields. **Mitigation:** by-project schema is separate (`UsageByProjectEntrySchema`); only top-level `UsageSummary` gets the new fields.

---

## 8. Out of scope / deferred

- Activity entry on inject.
- `/metrics/inject/timeline` endpoint + chart.
- `state/graph.json` cache.
- MCP `get_session_context` tool.
- Pricing in $.
- Per-session top-N compression (spec mentioned `compression_ratio` per-row in `/usage/top-sessions` — defer; row-level data isn't materialized in `top_sessions` aggregator).

---

## 9. Spec coverage map (for plan-writing)

| Design § | Plan task |
|---|---|
| 2.8(1) timestamp | Task 1 |
| 2.8(2) skip-sources comment | Task 2 |
| 2.8(3) slug dedup | Task 3 |
| 2.3 graph_with_pages | Task 4 |
| 2.2 with_stats variant | Task 5 |
| 2.1 inject_metrics state | Task 6 |
| 2.4 hook writes event | Task 7 |
| 2.5 compression_summary | Task 8 |
| 2.6 /metrics/usage extension | Task 9 |
| 2.7 frontend UsageWidget | Task 10 |
| §6 ACs | Task 11 (final verification) |

11 tasks. Mostly backend + 1 small frontend diff.

---

(end of design)
