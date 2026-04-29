# Plan #13e — Final polish (design)

**Date:** 2026-04-29
**Status:** Design
**Goal:** Close 6 carry-over polish items from #13d code review + memory: dedup `build_page_graph`, defensive cap-sort, unified period cutoff, file lock for concurrent hook writes, `/metrics/inject/timeline` endpoint + chart, per-project compression visibility. After #13e the inject metric stack is complete and the dashboard fully exposes it.

---

## 1. Background

After Plan #13d the §15 compression_ratio metric is in place — events are recorded per-vault, aggregator works, `/metrics/usage` exposes the cross-vault summary, `<UsageWidget>` renders it. Six known follow-ups remain:

1. **`build_page_graph` near-dead code** — production now uses only `build_page_graph_with_pages`. Old function is exercised only by tests. Make it a thin wrapper around `_with_pages` to eliminate duplication.
2. **`_apply_cap` drops by insertion order, not timestamp** — for monotonic ingest order this is fine, but defensive sort before slice closes a latent bug.
3. **Period boundary inconsistency** — `usage_summary` filters by `rec.ingested_at.date() >= cutoff` (date-level), `compression_summary` by `e.timestamp >= cutoff_dt` (datetime midnight UTC). On the boundary day the two functions count slightly different sets.
4. **Concurrent hook writes** — two SessionStart hooks firing simultaneously can both load → modify → save the same `.inject-metrics.json`, losing one event. Acceptable but fixable with a simple file lock.
5. **No timeline view of inject events** — dashboard shows only the 30-day summary number. A daily timeline (events_count + avg_ratio per day) belongs on the Metrics page next to `<UsageTimelineChart>`.
6. **Per-project compression invisibility** — `/metrics/usage/by-project` endpoint and `<UsageByProjectTable>` widget don't expose compression. Cross-vault summary is good, but per-project debugging needs the breakdown.

After #13e + a follow-up UI smoke test (separate from this plan), the entire stack is verified end-to-end.

### Out of scope

- New endpoints beyond `/metrics/inject/timeline` and `/metrics/usage/by-project` extension.
- New chart libraries (recharts already in).
- Activity entry on inject (still deferred).
- Frontend tests for new chart beyond render smoke (chart rendering tested via existing UsageTimelineChart pattern).
- New 3rd-party Python deps (use stdlib `os.O_EXCL` for file lock).

---

## 2. Architecture

### 2.1 `build_page_graph` thin-wrapper refactor

Currently `build_page_graph` and `build_page_graph_with_pages` duplicate the file walk + parse. After:

```python
def build_page_graph(vault: Path) -> dict[str, set[str]]:
    """Undirected page adjacency. See :func:`build_page_graph_with_pages`
    for the variant that also returns parsed pages."""
    graph, _ = build_page_graph_with_pages(vault)
    return graph
```

Public API preserved. Tests both keep meaning. -30 lines net.

### 2.2 `_apply_cap` defensive sort

Currently `self.events = self.events[-MAX_EVENTS:]` keeps last N by insertion order. Hooks always append in time order, but a backfill, a manual edit, or a future feature could violate that invariant. Fix:

```python
def _apply_cap(self) -> None:
    if len(self.events) > MAX_EVENTS:
        self.events.sort(key=lambda e: e.timestamp)
        self.events = self.events[-MAX_EVENTS:]
```

Additional 1-line cost on the rare cap path. New test: append events in non-monotonic order, assert oldest dropped.

### 2.3 Unified period cutoff helper

Add to `core/metrics.py`:

```python
def _period_cutoff_dt(today: date_class, period_days: int) -> datetime:
    """UTC midnight at start of the period window. Used by both usage_summary
    and compression_summary so they count the same boundary day."""
    return datetime.combine(today - timedelta(days=period_days), datetime.min.time(), UTC)
```

Both summaries call it. Then they use `e.timestamp >= cutoff_dt` (datetime-level) for filtering — `usage_summary` switches from `rec.ingested_at.date() >= cutoff` to the datetime form. The behaviour change: events on the boundary day at, say, 23:00 UTC are now included in both (they were previously excluded by `usage_summary`).

Existing `usage_summary` tests likely don't pin boundary-day behaviour at hour-precision — should pass unchanged. New test: event at 22:00 UTC on boundary day is included by both summaries.

### 2.4 File lock for concurrent hook writes

`InjectMetricsLog.append_to_vault` becomes:

```python
@classmethod
def append_to_vault(cls, vault_root: Path, event: InjectMetricEvent) -> None:
    """Convenience: load → append → save, with a file lock to serialize
    concurrent writers. If the lock can't be acquired in 5 seconds, falls
    back to last-writer-wins (logs to ~/.claude-mnemos/inject.log)."""
    lock_path = vault_root / ".inject-metrics.lock"
    acquired = False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.05)
    try:
        log = cls.load(vault_root)
        log.append(event)
        log.save(vault_root)
    finally:
        if acquired:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
```

Stdlib only. The lock file is at vault root next to `.inject-metrics.json`. Stale locks (process crashed mid-write) are unlikely but addressable: if `lock_path` exists and is older than e.g. 10 s, a future concurrent writer treats it as stale. **Defer that** — first-version best-effort lock is enough.

If the lock can't be acquired in 5 s, we proceed without it (degraded last-writer-wins) so the hook never blocks the session. The hook also wraps the whole metric-write block in try/except (existing #13d behaviour) so even total failure here is silent.

### 2.5 `compression_timeline` aggregator

`core/metrics.py`:

```python
class CompressionTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date_class
    events_count: int
    valid_events_count: int
    avg_compression_ratio: float | None  # None for empty days

def compression_timeline(
    vault: Path, *, period_days: int = 30, today: date_class | None = None,
) -> list[CompressionTimelinePoint]:
    """Per-day buckets of inject events. Zero-fills empty days."""
    today = today or datetime.now(UTC).date()
    cutoff_dt = _period_cutoff_dt(today, period_days)
    # ...bucket events by .date(), compute per-day stats, zero-fill
```

Returns sorted ascending by date. Mirrors `timeline()` shape so frontend can re-use a similar chart.

### 2.6 `/metrics/inject/timeline` daemon endpoint

Routes file. Aggregates across vaults (sum events per day, weighted-avg of ratios per day). Returns `{points: [{date, events_count, valid_events_count, avg_compression_ratio}]}`.

```python
@router.get("/metrics/inject/timeline")
async def inject_timeline_route(request, period: str = "30d"):
    days = _parse_period(period)
    today = datetime.now(UTC).date()
    # collect per-vault timelines, aggregate by date across vaults
    aggregated: dict[date_class, dict] = {}
    for runtime in await all_runtimes(request):
        for p in compression_timeline(runtime.vault_root, period_days=days, today=today):
            agg = aggregated.setdefault(p.date, {"events": 0, "valid": 0, "ratio_sum": 0.0})
            agg["events"] += p.events_count
            agg["valid"] += p.valid_events_count
            if p.avg_compression_ratio is not None:
                agg["ratio_sum"] += p.avg_compression_ratio * p.valid_events_count
    points = []
    for d in sorted(aggregated):
        a = aggregated[d]
        avg = a["ratio_sum"] / a["valid"] if a["valid"] > 0 else None
        points.append({"date": d.isoformat(), "events_count": a["events"],
                       "valid_events_count": a["valid"], "avg_compression_ratio": avg})
    return {"points": points}
```

### 2.7 Frontend `<CompressionTimelineChart>` widget

New widget on Metrics page. Same recharts pattern as `<UsageTimelineChart>`:
- X-axis: date.
- Left Y-axis: events_count (bars).
- Right Y-axis: avg_compression_ratio (line, gold-ish).
- Empty-state callout when all zero.

New zod type `CompressionTimelinePoint` (mirrors backend), new `getCompressionTimeline` API fn, new `useCompressionTimeline(period)` hook (60s refetch like the rest), new chart widget, slot under `<UsageTimelineChart>` on Metrics page.

Locale keys `metrics.compression_timeline_title`, `metrics.compression_legend_events`, `metrics.compression_legend_ratio`, `metrics.compression_timeline_empty`.

### 2.8 Per-project compression breakdown

Two backend touches:
- `core/metrics.py::usage_by_project` already returns per-project `UsageSummary`. Extend with `avg_compression_ratio` + `inject_events_count` + `valid_events_count` per project. Implementation: each per-project row also calls `compression_summary(vault, period_days)` for that vault and merges fields.
- `/metrics/usage/by-project` route returns the extended shape automatically once the type extends.

Frontend:
- `UsageByProjectEntrySchema` adds 3 fields with defaults (`null`, `0`, `0`).
- `<UsageByProjectTable>` adds 1 column: "Compression" showing `{ratio}× ({events} events)` or `—` when null.
- Locale `metrics.col_compression`.

---

## 3. Data flow

Two new flows:

**Inject timeline (read):**
```
Metrics page mount
  → useCompressionTimeline(period=30d)
  → GET /metrics/inject/timeline?period=30d
  → daemon iterates runtimes, calls compression_timeline per vault
  → aggregates per-day across vaults (events sum, weighted-avg ratio)
  → response {points: [...]}
  → CompressionTimelineChart renders bars + line
```

**Per-project compression (read):**
```
Metrics page mount
  → useUsageByProject(period=30d) (existing)
  → GET /metrics/usage/by-project?period=30d
  → response: each project row now also has compression fields
  → UsageByProjectTable renders extra column
```

**Concurrent hook writes:**
```
hook A starts → tries O_EXCL create lock → success
  ↓
hook B starts → tries O_EXCL create lock → fails → polls every 50ms
  ↓
hook A: load → append → save → unlink lock
  ↓
hook B: O_EXCL succeeds → load (sees A's event) → append → save → unlink lock
```

If hook B exhausts 5s budget (unusual on local SSD), proceeds without lock. Last-writer-wins fallback is the existing #13d behaviour — strictly no worse.

---

## 4. New / changed files

**New (backend):**
- `tests/test_compression_timeline.py`
- `tests/test_period_cutoff.py` (or extend `test_compression_summary.py`)

**Modified (backend):**
- `claude_mnemos/core/graph.py` — `build_page_graph` becomes thin wrapper.
- `claude_mnemos/core/metrics.py` — `_period_cutoff_dt` helper, `usage_summary` switches to datetime cutoff, `compression_timeline` + `CompressionTimelinePoint` model, per-project shape extended.
- `claude_mnemos/state/inject_metrics.py` — `_apply_cap` defensive sort, `append_to_vault` file-lock wrap.
- `claude_mnemos/daemon/routes/metrics.py` — new `/metrics/inject/timeline` route, `/metrics/usage/by-project` extended response.
- `tests/test_inject_metrics.py` — new lock test.

**New (frontend):**
- `frontend/src/types/CompressionTimeline.ts`
- `frontend/src/api/compression.api.ts` (or extend metrics.api.ts)
- `frontend/src/hooks/useCompressionTimeline.ts`
- `frontend/src/components/widgets/CompressionTimelineChart.tsx`
- `frontend/src/__tests__/CompressionTimelineChart.test.tsx`

**Modified (frontend):**
- `frontend/src/types/UsageSummary.ts` — `UsageByProjectEntrySchema` extended.
- `frontend/src/components/widgets/UsageByProjectTable.tsx` — new column.
- `frontend/src/pages/Metrics.tsx` — slot in `<CompressionTimelineChart>`.
- `frontend/src/__tests__/UsageByProjectTable.test.tsx` — extended for new column.
- `frontend/public/locales/{en,uk,ru}.json` — new keys.

---

## 5. Testing strategy

Backend (~10 new tests):
- `build_page_graph` thin-wrapper still returns same graph.
- `_apply_cap` with non-monotonic insert order keeps recent-by-timestamp.
- `_period_cutoff_dt` helper UTC midnight invariant.
- `usage_summary` boundary day inclusion (event at 22:00 UTC on cutoff day included).
- `compression_summary` boundary day same as `usage_summary`.
- `compression_timeline` empty vault → all-zero points.
- `compression_timeline` events on different days → correct buckets.
- `compression_timeline` zero-fills missing days.
- `compression_timeline` ratio is None for days with no valid events.
- File lock: two concurrent appends both persist (use threading + small sleep).

Frontend (~3 new):
- `useCompressionTimeline` hook returns parsed points.
- `<CompressionTimelineChart>` renders legend labels (sr-only fallback like `UsageTimelineChart`).
- `<CompressionTimelineChart>` empty state.
- `<UsageByProjectTable>` renders compression column.

Total: ~13 new tests.

---

## 6. Acceptance criteria

1. ✅ `build_page_graph` is a thin wrapper; net code reduction.
2. ✅ `_apply_cap` sorts by timestamp before slice.
3. ✅ Both summaries use `_period_cutoff_dt` — boundary-day events counted consistently.
4. ✅ `InjectMetricsLog.append_to_vault` acquires a file lock; concurrent appends both persist.
5. ✅ `/metrics/inject/timeline?period=Nd` returns `{points: [...]}` with daily aggregates.
6. ✅ `<CompressionTimelineChart>` on Metrics page renders bars + line + legend.
7. ✅ `/metrics/usage/by-project` per-row response includes `avg_compression_ratio`, `inject_events_count`, `valid_events_count`.
8. ✅ `<UsageByProjectTable>` shows the new compression column.
9. ✅ Backend baseline holds: 1296 → 1306+.
10. ✅ Frontend baseline holds: 176 → 179+.
11. ✅ ruff + tsc + ESLint clean.
12. ⚠️ Manual smoke (after merge): open Metrics page, see two timelines and updated table.

---

## 7. Risks

- **`usage_summary` boundary change** — events at 22:00 UTC on the cutoff day were previously excluded. Now included. Strictly more inclusive, no data loss. But could cause tiny shifts in dashboard numbers — acceptable.
- **File lock retry budget** — 5 seconds on slow filesystems (NFS) might be tight. Mitigation: degraded fallback (no lock, proceed) so hook never blocks. Document explicitly.
- **Stale lock file** if a writer crashes — never auto-cleaned in v1. Manual `rm .inject-metrics.lock` recovers. Document; defer auto-cleanup.
- **Concurrent test flakiness** — testing real OS-level locking with threads can be flaky on Windows CI. Mitigation: small fixed sleep + retry assertions.
- **`/metrics/inject/timeline` performance on large vaults** — same `read_page` + scan as `compression_summary`. 10k events × 10 vaults = 100k events to filter per request. With 60s refetch, 1.7 req/min — fine. If it ever becomes hot, cache aggregated results per period.

---

## 8. Out of scope / deferred

- Stale lock-file auto-recovery.
- portalocker / external lock library.
- `/metrics/inject/{event_id}` detail endpoint.
- Per-session compression view (top-sessions-style).
- Compression chart export (CSV / image).

---

## 9. Spec coverage map

| Design § | Plan task |
|---|---|
| 2.1 build_page_graph wrapper | 1 |
| 2.2 _apply_cap sort | 2 |
| 2.3 unified cutoff helper | 3 |
| 2.4 file lock | 4 |
| 2.5 compression_timeline aggregator | 5 |
| 2.6 timeline daemon route | 6 |
| 2.7 frontend chart | 7 |
| 2.8 per-project breakdown | 8 (backend) + 9 (frontend) |
| §6 ACs | 10 (final verification) |

10 tasks. Mostly small individually.

---

(end of design)
