# Final polish Implementation Plan (Plan #13e)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Close 6 carry-over polish items from #13d: dedup `build_page_graph`, defensive cap-sort, unified period cutoff, file lock for concurrent hook writes, `/metrics/inject/timeline` endpoint + chart, per-project compression visibility.

**Architecture:** `build_page_graph` becomes a thin wrapper around `_with_pages`. `_period_cutoff_dt(today, days)` helper unifies datetime cutoffs in `usage_summary` + `compression_summary`. `_apply_cap` sorts by timestamp before slice. `InjectMetricsLog.append_to_vault` acquires an `O_EXCL` file lock with 5s budget, falls back to last-writer-wins. New `compression_timeline` aggregator + `/metrics/inject/timeline` endpoint + frontend chart. `/metrics/usage/by-project` extended with per-row compression fields, `<UsageByProjectTable>` adds a column.

**Tech Stack:** Python 3.12, Pydantic v2, pytest. React 19, zod, recharts. **No new deps** — stdlib `os.O_EXCL` for file lock.

**Design doc:** `docs/plans/2026-04-29-13e-final-polish-design.md` — read before each task.

---

## Files map

**Modified (backend):**
- `claude_mnemos/core/graph.py` — `build_page_graph` thin wrapper
- `claude_mnemos/core/metrics.py` — `_period_cutoff_dt` helper, `usage_summary` switches to datetime cutoff, `compression_timeline` aggregator + `CompressionTimelinePoint` model, `compression_summary_by_project` for per-project rows
- `claude_mnemos/state/inject_metrics.py` — `_apply_cap` defensive sort, `append_to_vault` file-lock wrap
- `claude_mnemos/daemon/routes/metrics.py` — `/metrics/inject/timeline` route, `/metrics/usage/by-project` extended response
- `tests/test_inject_metrics.py` — extend with cap-sort + lock tests
- `tests/test_compression_summary.py` — boundary day test
- `tests/daemon/test_app_metrics.py` — extend with timeline + by-project compression tests

**New (backend):**
- `tests/test_compression_timeline.py`

**Modified (frontend):**
- `frontend/src/types/UsageSummary.ts` — `UsageByProjectEntrySchema` extended with compression fields
- `frontend/src/types/CompressionTimeline.ts` (new)
- `frontend/src/api/metrics.api.ts` — `getCompressionTimeline`
- `frontend/src/hooks/useCompressionTimeline.ts` (new)
- `frontend/src/components/widgets/CompressionTimelineChart.tsx` (new)
- `frontend/src/components/widgets/UsageByProjectTable.tsx` — new column
- `frontend/src/pages/Metrics.tsx` — slot in new chart
- `frontend/public/locales/{en,uk,ru}.json` — new keys
- `frontend/src/__tests__/CompressionTimelineChart.test.tsx` (new)
- `frontend/src/__tests__/UsageByProjectTable.test.tsx` — extend

---

## Task 1: `build_page_graph` thin-wrapper refactor

**Files:**
- Modify: `claude_mnemos/core/graph.py`

- [ ] **Step 1: Read current implementation**

```bash
cd /d/code/claude-mnemos
sed -n '40,90p' claude_mnemos/core/graph.py
```

Confirm `build_page_graph` and `build_page_graph_with_pages` duplicate the file walk + parse.

- [ ] **Step 2: Replace `build_page_graph` body with wrapper call**

Edit `claude_mnemos/core/graph.py`. Find the existing `build_page_graph` function. Replace its body with:

```python
def build_page_graph(vault: Path) -> dict[str, set[str]]:
    """Walk ``vault/wiki/**/*.md`` and return slug → set of neighbor slugs.

    Bidirectional. Bad pages are skipped. Targets not present as their own
    pages still appear as keys (empty neighbor set).

    Thin wrapper around :func:`build_page_graph_with_pages` — see that
    function for the variant that also returns parsed page bodies.
    """
    graph, _ = build_page_graph_with_pages(vault)
    return graph
```

Keep all other code in the file unchanged (the original imports + `build_page_graph_with_pages` + `pages_within_k_hops`).

- [ ] **Step 3: Run all graph tests**

```bash
python -m pytest tests/test_graph.py -v 2>&1 | tail -10
```

Expected: all 15 graph tests pass (12 for `build_page_graph` + 3 for `_with_pages`). The wrapper produces identical output, so existing tests continue to validate the same contract.

- [ ] **Step 4: Run wider suite**

```bash
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -3
```

Expected: 1296 passed, no regressions.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/graph.py
git commit -m "refactor(core): #13e build_page_graph thin wrapper around _with_pages"
```

---

## Task 2: `_apply_cap` defensive timestamp sort

**Files:**
- Modify: `claude_mnemos/state/inject_metrics.py`
- Modify: `tests/test_inject_metrics.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_inject_metrics.py`:

```python
def test_apply_cap_drops_oldest_by_timestamp_not_insertion_order(tmp_path: Path) -> None:
    """Defensive: even if events are appended out of order, cap drops by timestamp."""
    log = InjectMetricsLog()
    base = datetime.now(UTC)
    # Insert in reverse-chronological order
    for i in range(MAX_EVENTS + 5):
        ts = base - timedelta(seconds=i)  # newer-to-older
        log.events.append(_make_event(idx=i, ts=ts))
    log.save(tmp_path)

    fresh = InjectMetricsLog.load(tmp_path)
    assert len(fresh.events) == MAX_EVENTS
    # The 5 oldest by timestamp (highest indices, since we reversed) must be dropped.
    kept_timestamps = [e.timestamp for e in fresh.events]
    # The kept events should be the most recent (lowest index = newest).
    kept_indices = sorted(int(e.id.split("-")[1]) for e in fresh.events)
    # Most recent are indices 0..MAX_EVENTS-1 (because reverse insert).
    assert kept_indices[0] == 0  # newest is kept
    assert kept_indices[-1] == MAX_EVENTS - 1  # oldest kept is index MAX-1
    # No event with index ≥ MAX_EVENTS should be present (those were oldest by timestamp).
    assert all(i < MAX_EVENTS for i in kept_indices)
```

- [ ] **Step 2: Run** → expect FAIL (current `_apply_cap` keeps last-N by insertion order, dropping the newest events when reverse-inserted).

```bash
python -m pytest tests/test_inject_metrics.py::test_apply_cap_drops_oldest_by_timestamp_not_insertion_order -v 2>&1 | tail -10
```

- [ ] **Step 3: Add defensive sort**

Edit `claude_mnemos/state/inject_metrics.py`. Find `_apply_cap`:

```python
def _apply_cap(self) -> None:
    if len(self.events) > MAX_EVENTS:
        # Keep the most-recent MAX_EVENTS by drop-from-head (events list
        # is ingest-order, not necessarily timestamp-sorted, but for our
        # use case the difference is negligible).
        self.events = self.events[-MAX_EVENTS:]
```

Replace with:

```python
def _apply_cap(self) -> None:
    if len(self.events) > MAX_EVENTS:
        # Sort by timestamp ascending and keep the most-recent MAX_EVENTS.
        # Defensive: hooks normally append in chronological order, but a
        # backfill / manual edit / future feature could violate that.
        self.events.sort(key=lambda e: e.timestamp)
        self.events = self.events[-MAX_EVENTS:]
```

- [ ] **Step 4: Run → PASS**

```bash
python -m pytest tests/test_inject_metrics.py -v 2>&1 | tail -10
```

Expected: all 9 tests pass (8 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/state/inject_metrics.py tests/test_inject_metrics.py
git commit -m "fix(state): #13e InjectMetricsLog._apply_cap sorts by timestamp before slice"
```

---

## Task 3: `_period_cutoff_dt` helper + unify summaries

**Files:**
- Modify: `claude_mnemos/core/metrics.py`
- Modify: `tests/test_compression_summary.py`

- [ ] **Step 1: Failing test for boundary-day inclusion**

Append to `tests/test_compression_summary.py`:

```python
def test_compression_summary_boundary_day_included(tmp_path: Path) -> None:
    """Event at 22:00 UTC on the cutoff day should be included.

    cutoff_dt = midnight UTC at start of (today - period_days). An event
    later that same day at 22:00 has timestamp >= cutoff_dt → included.
    """
    today = datetime.now(UTC).date()
    boundary_day = today - timedelta(days=30)
    boundary_ts = datetime.combine(boundary_day, datetime.min.time(), UTC) + timedelta(hours=22)
    _seed(tmp_path, [_make_event(idx=1, ts=boundary_ts, tokens_full=1000, tokens_actual=200)])

    out = compression_summary(tmp_path, period_days=30, today=today)
    assert out.events_count == 1, "boundary-day event at 22:00 UTC should be included"
```

(`compression_summary` already has `today: date_class | None` parameter — uses it as cutoff anchor. Test uses today's actual date but explicitly passes it for determinism.)

- [ ] **Step 2: Run → confirm passes already**

```bash
python -m pytest tests/test_compression_summary.py::test_compression_summary_boundary_day_included -v 2>&1 | tail -10
```

The current `compression_summary` already uses `datetime.combine(today - timedelta(days=period_days), datetime.min.time(), UTC)` as cutoff_dt — should pass.

- [ ] **Step 3: Failing test for `usage_summary` boundary parity**

Append to `tests/test_compression_summary.py`:

```python
def test_usage_summary_boundary_day_included_consistent_with_compression(tmp_path: Path) -> None:
    """usage_summary and compression_summary should both include events on
    the boundary day (same UTC midnight cutoff semantics)."""
    from claude_mnemos.core.metrics import usage_summary
    from claude_mnemos.state.manifest import IngestRecord, Manifest
    from claude_mnemos.core.atomic import atomic_write

    today = datetime.now(UTC).date()
    boundary_day = today - timedelta(days=30)
    boundary_ts = datetime.combine(boundary_day, datetime.min.time(), UTC) + timedelta(hours=22)

    # Seed manifest with one ingest record on the boundary day at 22:00 UTC.
    rec = IngestRecord(
        session_id="s1",
        ingested_at=boundary_ts,
        raw_path="raw/s1.md",
        source_path=None,
        created_pages=[],
        skipped_collisions=[],
        model=None,
        input_tokens=100,
        output_tokens=200,
    )
    manifest = Manifest(ingested={"s1": rec})
    atomic_write(tmp_path / ".manifest.json", manifest.serialize_to_string())

    out = usage_summary(tmp_path, period_days=30, today=today)
    assert out.sessions_covered == 1, (
        "boundary-day event at 22:00 UTC should be included by usage_summary"
    )
```

- [ ] **Step 4: Run → expect FAIL**

The current `usage_summary` uses date-level comparison `rec.ingested_at.date() >= cutoff`, where `cutoff = today - timedelta(days=30)`. The boundary-day event has `.date() == cutoff`, so it's actually included. Wait — that means the test passes too. Let me re-check: `cutoff = today - timedelta(days=period_days)`. If today=2026-04-29, cutoff=2026-03-30. Boundary day in test is also `today - timedelta(days=30) = 2026-03-30`. `rec.date() == cutoff` → `>=` is True → included.

The test **actually passes**. The boundary-day events are already counted by both. The "inconsistency" is at sub-day level (e.g., events at `23:59:59` on day before cutoff in `compression_summary` would be excluded, but `usage_summary` only sees dates).

Adjust the test to verify a sub-day case:

```python
def test_usage_summary_excludes_pre_cutoff_event(tmp_path: Path) -> None:
    """usage_summary excludes events from the day before the cutoff,
    matching compression_summary's UTC-midnight cutoff semantics."""
    from claude_mnemos.core.metrics import usage_summary
    from claude_mnemos.state.manifest import IngestRecord, Manifest
    from claude_mnemos.core.atomic import atomic_write

    today = datetime.now(UTC).date()
    pre_boundary = today - timedelta(days=31)  # one day before cutoff
    pre_ts = datetime.combine(pre_boundary, datetime.min.time(), UTC) + timedelta(hours=23, minutes=59)

    rec = IngestRecord(
        session_id="s1",
        ingested_at=pre_ts,
        raw_path="raw/s1.md",
        source_path=None,
        created_pages=[],
        skipped_collisions=[],
        model=None,
        input_tokens=100,
        output_tokens=200,
    )
    manifest = Manifest(ingested={"s1": rec})
    atomic_write(tmp_path / ".manifest.json", manifest.serialize_to_string())

    out = usage_summary(tmp_path, period_days=30, today=today)
    assert out.sessions_covered == 0, (
        "event one day before cutoff at 23:59 UTC should be excluded"
    )
```

Replace the previous boundary-parity test with this one.

- [ ] **Step 5: Run → confirm passes (current `usage_summary` already excludes pre-cutoff dates)**

```bash
python -m pytest tests/test_compression_summary.py::test_usage_summary_excludes_pre_cutoff_event -v 2>&1 | tail -10
```

Should pass without code changes — both summaries already align at the cutoff-day boundary.

- [ ] **Step 6: Add `_period_cutoff_dt` helper for code consistency**

Even though the behavior already matches, the two summaries express the cutoff differently:
- `usage_summary`: `cutoff = today - timedelta(days=period_days)` then `rec.ingested_at.date() >= cutoff`
- `compression_summary`: `cutoff_dt = datetime.combine(today - timedelta(days=period_days), datetime.min.time(), UTC)` then `e.timestamp >= cutoff_dt`

Add the shared helper. Edit `claude_mnemos/core/metrics.py`. After existing imports + before `_records_in_window`, add:

```python
def _period_cutoff_dt(today: date_class, period_days: int) -> datetime:
    """UTC midnight at start of the period window.

    Both :func:`usage_summary` and :func:`compression_summary` use this
    helper so they count the same boundary-day events.
    """
    return datetime.combine(
        today - timedelta(days=period_days), datetime.min.time(), UTC
    )
```

Refactor `usage_summary` to use it via a datetime-level filter. Replace `_records_in_window`:

```python
def _records_in_window(
    manifest: Manifest,
    *,
    cutoff_dt: datetime,
) -> list[IngestRecord]:
    """Return manifest records ingested on or after ``cutoff_dt`` (inclusive)."""
    return [
        rec
        for rec in manifest.ingested.values()
        if rec.ingested_at >= cutoff_dt
    ]
```

Update the call site in `usage_summary`:

```python
def usage_summary(
    vault: Path,
    *,
    period_days: int = 30,
    today: date_class | None = None,
) -> UsageSummary:
    ...
    today = today or datetime.now(UTC).date()
    cutoff_dt = _period_cutoff_dt(today, period_days)

    manifest = Manifest.load(vault)
    records = _records_in_window(manifest, cutoff_dt=cutoff_dt)
    ...
```

Update `compression_summary` to use the helper:

```python
def compression_summary(...):
    ...
    today = today or datetime.now(UTC).date()
    cutoff_dt = _period_cutoff_dt(today, period_days)
    ...
```

- [ ] **Step 7: Run all metrics tests**

```bash
python -m pytest tests/test_compression_summary.py tests/daemon/test_app_metrics.py -v 2>&1 | tail -10
```

All pass. The behavior is equivalent (date `>=` cutoff matches `timestamp >= midnight` for events with `.date() >= cutoff`).

Wait — that's not equivalent for events on the cutoff date itself. With date filter, ANY time-of-day on the cutoff date is included. With datetime filter, only times `>= midnight` (i.e., the entire day is included, since midnight ≤ any time). They ARE equivalent. Confirmed.

- [ ] **Step 8: Wider suite check**

```bash
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -3
```

Expected: still 1296+ passed.

- [ ] **Step 9: Commit**

```bash
git add claude_mnemos/core/metrics.py tests/test_compression_summary.py
git commit -m "refactor(metrics): #13e shared _period_cutoff_dt helper for consistent windowing"
```

---

## Task 4: File lock for concurrent hook writes

**Files:**
- Modify: `claude_mnemos/state/inject_metrics.py`
- Modify: `tests/test_inject_metrics.py`

- [ ] **Step 1: Failing test for concurrent appends**

Append to `tests/test_inject_metrics.py`:

```python
import threading


def test_concurrent_append_to_vault_does_not_lose_events(tmp_path: Path) -> None:
    """Two threads appending in parallel — both events must persist.

    Without a lock, load → modify → save races can drop one event.
    """
    n_events = 20
    barrier = threading.Barrier(2)

    def append_batch(start: int) -> None:
        barrier.wait()
        for i in range(start, start + n_events):
            ts = datetime.now(UTC) + timedelta(microseconds=i)
            event = InjectMetricEvent(
                id=f"evt-{i:06d}",
                timestamp=ts,
                session_id=f"s-{i}",
                operation="session_start",
                mode="full",
                tokens_full=1000,
                tokens_actual=200,
                candidates_total=10,
                candidates_packed=10,
            )
            InjectMetricsLog.append_to_vault(tmp_path, event)

    t1 = threading.Thread(target=append_batch, args=(0,))
    t2 = threading.Thread(target=append_batch, args=(n_events,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    log = InjectMetricsLog.load(tmp_path)
    # Both batches together produced n_events*2 unique IDs; all must persist.
    assert len(log.events) == n_events * 2, (
        f"expected {n_events * 2} events, got {len(log.events)} — "
        "concurrent writes lost data"
    )
```

- [ ] **Step 2: Run → expect FAIL (without lock, race likely loses some events)**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/test_inject_metrics.py::test_concurrent_append_to_vault_does_not_lose_events -v 2>&1 | tail -10
```

May not always fail due to timing, but with 20 events × 2 threads sleeping briefly between each load/save, the race window is wide enough that this test usually loses some events.

If the test passes by chance, increase `n_events` to 50 to widen the window.

- [ ] **Step 3: Add file lock to `append_to_vault`**

Edit `claude_mnemos/state/inject_metrics.py`. Add imports at top of file:

```python
import os
import time
```

(`time` may already be imported via `datetime`'s ecosystem — verify.)

Add a constant near `MAX_EVENTS`:

```python
LOCK_FILENAME = ".inject-metrics.lock"
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_POLL_INTERVAL = 0.05
```

Replace `append_to_vault`:

```python
@classmethod
def append_to_vault(cls, vault_root: Path, event: InjectMetricEvent) -> None:
    """Convenience: load → append → save, with a file lock to serialize
    concurrent writers.

    The lock is a vault-local file created with ``O_EXCL``. Other writers
    poll up to ``LOCK_TIMEOUT_SECONDS``; if the timeout expires (e.g. a
    stale lock from a crashed writer), this function falls back to
    last-writer-wins so the hook never blocks the session.
    """
    lock_path = vault_root / LOCK_FILENAME
    acquired = False
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            fd = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            time.sleep(LOCK_POLL_INTERVAL)

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

- [ ] **Step 4: Run concurrent test → expect PASS**

```bash
python -m pytest tests/test_inject_metrics.py::test_concurrent_append_to_vault_does_not_lose_events -v 2>&1 | tail -10
```

Expected: PASS — both batches persist.

- [ ] **Step 5: Run all inject_metrics tests + wider suite**

```bash
python -m pytest tests/test_inject_metrics.py -v 2>&1 | tail -10
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -3
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/state/inject_metrics.py tests/test_inject_metrics.py
git commit -m "feat(state): #13e file lock for concurrent inject metric writes"
```

---

## Task 5: `compression_timeline` aggregator

**Files:**
- Create: `tests/test_compression_timeline.py`
- Modify: `claude_mnemos/core/metrics.py`

- [ ] **Step 1: Failing test**

`tests/test_compression_timeline.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from claude_mnemos.core.metrics import (
    CompressionTimelinePoint,
    compression_timeline,
)
from claude_mnemos.state.inject_metrics import (
    InjectMetricEvent,
    InjectMetricsLog,
)


def _make_event(
    *,
    idx: int,
    ts: datetime,
    tokens_full: int = 1000,
    tokens_actual: int = 200,
) -> InjectMetricEvent:
    return InjectMetricEvent(
        id=f"evt-{idx:06d}",
        timestamp=ts,
        session_id=f"s-{idx}",
        operation="session_start",
        mode="full",
        tokens_full=tokens_full,
        tokens_actual=tokens_actual,
        candidates_total=10,
        candidates_packed=10,
    )


def _seed(vault: Path, events: list[InjectMetricEvent]) -> None:
    log = InjectMetricsLog(events=events)
    log.save(vault)


def test_compression_timeline_empty(tmp_path: Path) -> None:
    today = date(2026, 4, 29)
    out = compression_timeline(tmp_path, period_days=7, today=today)
    assert len(out) == 7  # zero-filled
    for p in out:
        assert isinstance(p, CompressionTimelinePoint)
        assert p.events_count == 0
        assert p.valid_events_count == 0
        assert p.avg_compression_ratio is None


def test_compression_timeline_buckets_by_date(tmp_path: Path) -> None:
    today = date(2026, 4, 29)
    day1 = datetime(2026, 4, 27, 14, 0, tzinfo=UTC)
    day2 = datetime(2026, 4, 28, 10, 0, tzinfo=UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=day1, tokens_full=1000, tokens_actual=200),  # ratio 5
        _make_event(idx=2, ts=day1, tokens_full=600, tokens_actual=200),   # ratio 3
        _make_event(idx=3, ts=day2, tokens_full=400, tokens_actual=100),   # ratio 4
    ])
    out = compression_timeline(tmp_path, period_days=7, today=today)
    assert len(out) == 7
    by_date = {p.date: p for p in out}
    assert by_date[date(2026, 4, 27)].events_count == 2
    assert by_date[date(2026, 4, 27)].valid_events_count == 2
    assert by_date[date(2026, 4, 27)].avg_compression_ratio == 4.0
    assert by_date[date(2026, 4, 28)].events_count == 1
    assert by_date[date(2026, 4, 28)].avg_compression_ratio == 4.0
    # Other days zero-filled
    assert by_date[date(2026, 4, 29)].events_count == 0
    assert by_date[date(2026, 4, 29)].avg_compression_ratio is None


def test_compression_timeline_ratio_none_for_zero_actual(tmp_path: Path) -> None:
    today = date(2026, 4, 29)
    day1 = datetime(2026, 4, 28, 14, 0, tzinfo=UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=day1, tokens_full=500, tokens_actual=0),
    ])
    out = compression_timeline(tmp_path, period_days=7, today=today)
    by_date = {p.date: p for p in out}
    p = by_date[date(2026, 4, 28)]
    assert p.events_count == 1
    assert p.valid_events_count == 0
    assert p.avg_compression_ratio is None  # no valid events


def test_compression_timeline_excludes_outside_window(tmp_path: Path) -> None:
    today = date(2026, 4, 29)
    pre = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)  # well outside 7d window
    _seed(tmp_path, [
        _make_event(idx=1, ts=pre, tokens_full=999, tokens_actual=99),
    ])
    out = compression_timeline(tmp_path, period_days=7, today=today)
    assert all(p.events_count == 0 for p in out)


def test_compression_timeline_sorted_ascending(tmp_path: Path) -> None:
    today = date(2026, 4, 29)
    out = compression_timeline(tmp_path, period_days=5, today=today)
    dates = [p.date for p in out]
    assert dates == sorted(dates)
    assert dates[0] == date(2026, 4, 24)
    assert dates[-1] == date(2026, 4, 28)
```

(Note: window is `today - period_days` to `today - 1` inclusive — same convention as `timeline()` for usage. If the implementation includes today itself as the last bucket, adjust the assertion accordingly. Verify against the actual implementation step below.)

- [ ] **Step 2: Run → expect FAIL**

```bash
python -m pytest tests/test_compression_timeline.py -v 2>&1 | tail -15
```

- [ ] **Step 3: Implement aggregator**

Edit `claude_mnemos/core/metrics.py`. Add the model anywhere with other Pydantic models (near `CompressionSummary`):

```python
class CompressionTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_class
    events_count: int
    valid_events_count: int
    avg_compression_ratio: float | None
```

Add the aggregator (near `compression_summary`):

```python
def compression_timeline(
    vault: Path,
    *,
    period_days: int = 30,
    today: date_class | None = None,
) -> list[CompressionTimelinePoint]:
    """Per-day buckets of inject events for the last ``period_days`` days.

    Days with no events appear with zero counts and ``avg_compression_ratio
    == None`` so chart axes line up cleanly. Output sorted ascending by
    date. The window matches :func:`timeline` — ``period_days`` days
    ending at ``today - 1`` (inclusive of ``today - period_days``,
    exclusive of ``today``).
    """
    today = today or datetime.now(UTC).date()
    start = today - timedelta(days=period_days)

    # Pre-seed every day with empty buckets so missing days are explicit.
    buckets: dict[date_class, dict] = {
        start + timedelta(days=i): {
            "events": [],
        }
        for i in range(period_days)
    }

    log = InjectMetricsLog.load(vault)
    for evt in log.events:
        evt_date = evt.timestamp.astimezone(UTC).date()
        bucket = buckets.get(evt_date)
        if bucket is None:
            continue
        bucket["events"].append(evt)

    points: list[CompressionTimelinePoint] = []
    for d in sorted(buckets):
        events = buckets[d]["events"]
        valid = [e for e in events if e.tokens_actual > 0]
        avg = (
            sum(e.tokens_full / e.tokens_actual for e in valid) / len(valid)
            if valid
            else None
        )
        points.append(
            CompressionTimelinePoint(
                date=d,
                events_count=len(events),
                valid_events_count=len(valid),
                avg_compression_ratio=avg,
            )
        )

    return points
```

- [ ] **Step 4: Adjust test boundary assertions if needed**

Test asserts `dates[-1] == date(2026, 4, 28)` (yesterday). If `today=2026-04-29` and `period_days=5`, the window is `[24, 25, 26, 27, 28]`. That matches.

- [ ] **Step 5: Run → expect PASS**

```bash
python -m pytest tests/test_compression_timeline.py -v 2>&1 | tail -15
```

- [ ] **Step 6: Run wider suite**

```bash
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -3
```

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/core/metrics.py tests/test_compression_timeline.py
git commit -m "feat(metrics): #13e compression_timeline — daily inject event buckets"
```

---

## Task 6: `/metrics/inject/timeline` daemon route

**Files:**
- Modify: `claude_mnemos/daemon/routes/metrics.py`
- Modify: `tests/daemon/test_app_metrics.py`

- [ ] **Step 1: Failing test**

Append to `tests/daemon/test_app_metrics.py`:

```python
def test_inject_timeline_returns_daily_points(daemon_with_one_vault, tmp_path):
    """/metrics/inject/timeline returns per-day events_count + ratio."""
    from datetime import UTC, datetime, timedelta
    from claude_mnemos.state.inject_metrics import (
        InjectMetricEvent,
        InjectMetricsLog,
    )

    vault, client = daemon_with_one_vault

    today = datetime.now(UTC)
    yesterday = today - timedelta(days=1)
    log = InjectMetricsLog()
    log.events.append(InjectMetricEvent(
        id="e1", timestamp=yesterday, session_id="s1",
        operation="session_start", mode="full",
        tokens_full=1000, tokens_actual=200,
        candidates_total=5, candidates_packed=5,
    ))
    log.save(vault)

    r = client.get("/metrics/inject/timeline", params={"period": "7d"})
    assert r.status_code == 200
    data = r.json()
    assert "points" in data
    assert len(data["points"]) == 7
    by_date = {p["date"]: p for p in data["points"]}
    yesterday_iso = yesterday.date().isoformat()
    assert by_date[yesterday_iso]["events_count"] == 1
    assert by_date[yesterday_iso]["avg_compression_ratio"] == 5.0


def test_inject_timeline_empty_returns_zero_filled(daemon_with_one_vault):
    vault, client = daemon_with_one_vault
    r = client.get("/metrics/inject/timeline", params={"period": "7d"})
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 7
    assert all(p["events_count"] == 0 for p in points)
    assert all(p["avg_compression_ratio"] is None for p in points)
```

(Adapt fixture name `daemon_with_one_vault` to the actual fixture used in `test_app_metrics.py` — check existing tests.)

- [ ] **Step 2: Run → expect FAIL (404 — route doesn't exist)**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/daemon/test_app_metrics.py::test_inject_timeline_returns_daily_points -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement route**

Edit `claude_mnemos/daemon/routes/metrics.py`. Add at top with other imports:

```python
from claude_mnemos.core.metrics import (
    # ... existing imports ...
    compression_timeline,
)
```

Add the route handler (after existing `/metrics/inject/...` or `/metrics/usage/timeline`):

```python
@router.get("/metrics/inject/timeline")
async def inject_timeline_route(
    request: Request,
    period: str = "30d",
) -> dict:
    """Per-day inject event buckets aggregated across all mounted vaults."""
    days = _parse_period(period)
    today = datetime.now(UTC).date()

    aggregated: dict[date_class, dict] = {}
    for runtime in await all_runtimes(request):
        vault_points = compression_timeline(
            runtime.vault_root, period_days=days, today=today,
        )
        for p in vault_points:
            agg = aggregated.setdefault(
                p.date,
                {"events": 0, "valid": 0, "ratio_weighted_sum": 0.0},
            )
            agg["events"] += p.events_count
            agg["valid"] += p.valid_events_count
            if p.avg_compression_ratio is not None:
                agg["ratio_weighted_sum"] += (
                    p.avg_compression_ratio * p.valid_events_count
                )

    points = []
    for d in sorted(aggregated):
        a = aggregated[d]
        avg = (
            a["ratio_weighted_sum"] / a["valid"]
            if a["valid"] > 0
            else None
        )
        points.append({
            "date": d.isoformat(),
            "events_count": a["events"],
            "valid_events_count": a["valid"],
            "avg_compression_ratio": avg,
        })

    return {"points": points}
```

Verify imports include `Request`, `all_runtimes`, `_parse_period`, `datetime`, `UTC`, `date_class`. Match existing patterns in the file.

- [ ] **Step 4: Run → expect PASS**

```bash
python -m pytest tests/daemon/test_app_metrics.py -k "inject_timeline" -v 2>&1 | tail -10
```

- [ ] **Step 5: Run all metrics tests**

```bash
python -m pytest tests/daemon/test_app_metrics.py 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/metrics.py tests/daemon/test_app_metrics.py
git commit -m "feat(daemon): #13e /metrics/inject/timeline daemon route"
```

---

## Task 7: Frontend `<CompressionTimelineChart>` widget

**Files:**
- Create: `frontend/src/types/CompressionTimeline.ts`
- Modify: `frontend/src/api/metrics.api.ts`
- Create: `frontend/src/hooks/useCompressionTimeline.ts`
- Create: `frontend/src/components/widgets/CompressionTimelineChart.tsx`
- Create: `frontend/src/__tests__/CompressionTimelineChart.test.tsx`
- Modify: `frontend/src/pages/Metrics.tsx`
- Modify: `frontend/public/locales/{en,uk,ru}.json`

- [ ] **Step 1: Add types**

Create `frontend/src/types/CompressionTimeline.ts`:

```ts
import { z } from "zod";

export const CompressionTimelinePointSchema = z.object({
  date: z.string(),
  events_count: z.number().int().nonnegative(),
  valid_events_count: z.number().int().nonnegative(),
  avg_compression_ratio: z.number().nullable(),
});
export type CompressionTimelinePoint = z.infer<typeof CompressionTimelinePointSchema>;

export const CompressionTimelineResponseSchema = z.object({
  points: z.array(CompressionTimelinePointSchema),
});
```

- [ ] **Step 2: Add API function**

Edit `frontend/src/api/metrics.api.ts`. Add imports + function:

```ts
import {
  CompressionTimelineResponseSchema,
  type CompressionTimelinePoint,
} from "@/types/CompressionTimeline";

export async function getCompressionTimeline(
  period = "30d",
): Promise<CompressionTimelinePoint[]> {
  const r = await apiClient.get("/metrics/inject/timeline", { params: { period } });
  return CompressionTimelineResponseSchema.parse(r.data).points;
}
```

- [ ] **Step 3: Add hook**

Create `frontend/src/hooks/useCompressionTimeline.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { getCompressionTimeline } from "@/api/metrics.api";

export function useCompressionTimeline(period = "30d") {
  return useQuery({
    queryKey: ["compression-timeline", period],
    queryFn: () => getCompressionTimeline(period),
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 4: Failing test for chart**

Create `frontend/src/__tests__/CompressionTimelineChart.test.tsx`:

```tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { CompressionTimelineChart } from "../components/widgets/CompressionTimelineChart";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      compression_timeline_legend_events: "Inject events",
      compression_timeline_legend_ratio: "Avg ratio",
      compression_timeline_empty: "No inject events in this period",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const POINTS = [
  { date: "2026-04-27", events_count: 2, valid_events_count: 2, avg_compression_ratio: 4.0 },
  { date: "2026-04-28", events_count: 1, valid_events_count: 1, avg_compression_ratio: 5.0 },
];

describe("CompressionTimelineChart", () => {
  it("renders legend labels with non-empty data", () => {
    render(<CompressionTimelineChart points={POINTS} />);
    expect(screen.getByText("Inject events")).toBeInTheDocument();
    expect(screen.getByText("Avg ratio")).toBeInTheDocument();
  });

  it("renders empty state when all points are zero", () => {
    const empty = POINTS.map((p) => ({ ...p, events_count: 0, valid_events_count: 0, avg_compression_ratio: null }));
    render(<CompressionTimelineChart points={empty} />);
    expect(screen.getByText(/no inject events/i)).toBeInTheDocument();
  });

  it("renders empty state when points array is empty", () => {
    render(<CompressionTimelineChart points={[]} />);
    expect(screen.getByText(/no inject events/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run → expect FAIL**

```bash
cd /d/code/claude-mnemos/frontend
pnpm test CompressionTimelineChart 2>&1 | tail -10
```

- [ ] **Step 6: Implement chart widget**

Create `frontend/src/components/widgets/CompressionTimelineChart.tsx`:

```tsx
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Legend, CartesianGrid,
} from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { CompressionTimelinePoint } from "@/types/CompressionTimeline";

interface Props {
  points: CompressionTimelinePoint[];
}

export function CompressionTimelineChart({ points }: Props) {
  const { t } = useTranslation();

  const isEmpty = useMemo(() => {
    if (points.length === 0) return true;
    return points.every((p) => p.events_count === 0);
  }, [points]);

  if (isEmpty) {
    return (
      <div className="flex h-72 items-center justify-center rounded-md border bg-[hsl(var(--muted))] text-sm text-[hsl(var(--muted-foreground))]">
        {t("metrics.compression_timeline_empty")}
      </div>
    );
  }

  return (
    <>
      {/* Sr-only fallback for jsdom legend testability (recharts Legend doesn't render in jsdom). */}
      <span className="sr-only">{t("metrics.compression_timeline_legend_events")}</span>
      <span className="sr-only">{t("metrics.compression_timeline_legend_ratio")}</span>
      <ChartContainer height={320}>
        <ComposedChart data={points} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="date" fontSize={11} />
          <YAxis yAxisId="events" fontSize={11} />
          <YAxis yAxisId="ratio" orientation="right" fontSize={11} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar
            yAxisId="events"
            dataKey="events_count"
            name={t("metrics.compression_timeline_legend_events")}
            fill="var(--chart-input)"
          />
          <Line
            yAxisId="ratio"
            type="monotone"
            dataKey="avg_compression_ratio"
            name={t("metrics.compression_timeline_legend_ratio")}
            stroke="var(--chart-sessions)"
            strokeWidth={2}
            connectNulls={false}
          />
        </ComposedChart>
      </ChartContainer>
    </>
  );
}
```

- [ ] **Step 7: Add locale keys**

Append to `metrics` block in each locale:

- en: `"compression_timeline_title": "Inject events timeline"`, `"compression_timeline_legend_events": "Inject events"`, `"compression_timeline_legend_ratio": "Avg ratio"`, `"compression_timeline_empty": "No inject events in this period"`
- uk: `"Часова шкала ін'єкцій"`, `"Ін'єкції"`, `"Середн. коеф."`, `"Немає ін'єкцій за цей період"`
- ru: `"Временная шкала инъекций"`, `"Инъекции"`, `"Средн. коэф."`, `"Нет инъекций за этот период"`

- [ ] **Step 8: Slot chart into Metrics page**

Edit `frontend/src/pages/Metrics.tsx`. Add imports:

```tsx
import { useCompressionTimeline } from "@/hooks/useCompressionTimeline";
import { CompressionTimelineChart } from "@/components/widgets/CompressionTimelineChart";
```

Add hook usage near `useUsageTimeline`:

```tsx
const compressionTimeline = useCompressionTimeline(period);
```

Insert a new `<Card>` block immediately after the existing timeline card:

```tsx
<Card>
  <CardHeader>
    <CardTitle className="text-base">{t("metrics.compression_timeline_title")}</CardTitle>
  </CardHeader>
  <CardContent>
    {compressionTimeline.isLoading ? (
      <Skeleton className="h-72" />
    ) : (
      <CompressionTimelineChart points={compressionTimeline.data ?? []} />
    )}
  </CardContent>
</Card>
```

- [ ] **Step 9: Run → expect PASS**

```bash
cd /d/code/claude-mnemos/frontend
pnpm test CompressionTimelineChart && pnpm test 2>&1 | tail -5 && pnpm typecheck 2>&1 | tail -3
```

Expected: all 179+ tests pass; tsc clean.

- [ ] **Step 10: Commit**

```bash
cd /d/code/claude-mnemos
git add frontend/src/types/CompressionTimeline.ts frontend/src/api/metrics.api.ts frontend/src/hooks/useCompressionTimeline.ts frontend/src/components/widgets/CompressionTimelineChart.tsx frontend/src/__tests__/CompressionTimelineChart.test.tsx frontend/src/pages/Metrics.tsx frontend/public/locales/
git commit -m "feat(frontend): #13e CompressionTimelineChart widget on Metrics page"
```

---

## Task 8: Per-project compression — backend

**Files:**
- Modify: `claude_mnemos/daemon/routes/metrics.py`
- Modify: `tests/daemon/test_app_metrics.py`

- [ ] **Step 1: Read existing `/metrics/usage/by-project` route**

```bash
grep -n "by-project\|by_project_route\|usage_summary" /d/code/claude-mnemos/claude_mnemos/daemon/routes/metrics.py | head -20
```

- [ ] **Step 2: Failing test**

Append to `tests/daemon/test_app_metrics.py`:

```python
def test_by_project_includes_compression_fields(daemon_with_one_vault, tmp_path):
    """/metrics/usage/by-project includes per-project compression fields."""
    from datetime import UTC, datetime
    from claude_mnemos.state.inject_metrics import (
        InjectMetricEvent,
        InjectMetricsLog,
    )

    vault, client = daemon_with_one_vault

    log = InjectMetricsLog()
    log.events.append(InjectMetricEvent(
        id="e1", timestamp=datetime.now(UTC), session_id="s1",
        operation="session_start", mode="full",
        tokens_full=1000, tokens_actual=200,
        candidates_total=5, candidates_packed=5,
    ))
    log.save(vault)

    r = client.get("/metrics/usage/by-project", params={"period": "30d"})
    assert r.status_code == 200
    data = r.json()
    assert "projects" in data
    assert len(data["projects"]) >= 1
    row = data["projects"][0]
    assert "avg_compression_ratio" in row
    assert "inject_events_count" in row
    assert "valid_events_count" in row
    assert row["avg_compression_ratio"] == 5.0
    assert row["inject_events_count"] == 1
    assert row["valid_events_count"] == 1
```

- [ ] **Step 3: Run → expect FAIL**

```bash
python -m pytest tests/daemon/test_app_metrics.py::test_by_project_includes_compression_fields -v 2>&1 | tail -10
```

- [ ] **Step 4: Extend route response**

Edit `claude_mnemos/daemon/routes/metrics.py`. Find the `by_project_route` (or similar). Inside the per-runtime loop where `usage_summary(...)` is called, also call `compression_summary(...)` and merge the fields into each row dict:

```python
for runtime in await all_runtimes(request):
    s = usage_summary(runtime.vault_root, period_days=days)
    c = compression_summary(runtime.vault_root, period_days=days)
    rows.append({
        "project": runtime.name,
        "period_days": s.period_days,
        "sessions_covered": s.sessions_covered,
        "tokens_input": s.tokens_input,
        "tokens_output": s.tokens_output,
        "tokens_injected": s.tokens_injected,
        "raw_bytes_total": s.raw_bytes_total,
        "tokens_per_byte": s.tokens_per_byte,
        # NEW: per-project compression fields (Plan #13e)
        "avg_compression_ratio": c.avg_compression_ratio,
        "inject_events_count": c.events_count,
        "valid_events_count": c.valid_events_count,
    })
```

(Adapt to the actual response-building style — may already use a dict comprehension or Pydantic model. If it's a Pydantic model, extend the model in `daemon/schemas.py` similarly.)

- [ ] **Step 5: Run → expect PASS**

```bash
python -m pytest tests/daemon/test_app_metrics.py -v 2>&1 | tail -15
```

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/metrics.py tests/daemon/test_app_metrics.py
git commit -m "feat(daemon): #13e /metrics/usage/by-project per-project compression fields"
```

---

## Task 9: Per-project compression — frontend

**Files:**
- Modify: `frontend/src/types/UsageSummary.ts`
- Modify: `frontend/src/components/widgets/UsageByProjectTable.tsx`
- Modify: `frontend/src/__tests__/UsageByProjectTable.test.tsx`
- Modify: `frontend/public/locales/{en,uk,ru}.json`

- [ ] **Step 1: Extend zod schema**

Edit `frontend/src/types/UsageSummary.ts`. Find `UsageByProjectEntrySchema` and add three fields:

```ts
export const UsageByProjectEntrySchema = z.object({
  project: z.string(),
  period_days: z.number().int().nonnegative(),
  sessions_covered: z.number().int().nonnegative(),
  tokens_input: z.number().int().nonnegative(),
  tokens_output: z.number().int().nonnegative(),
  tokens_injected: z.number().int().nonnegative(),
  raw_bytes_total: z.number().int().nonnegative(),
  tokens_per_byte: z.number().nullable(),
  avg_compression_ratio: z.number().nullable().default(null),
  inject_events_count: z.number().int().nonnegative().default(0),
  valid_events_count: z.number().int().nonnegative().default(0),
});
```

- [ ] **Step 2: Add locale key**

Append to each locale's `metrics` block:

- en: `"col_compression": "Compression"`
- uk: `"col_compression": "Стиснення"`
- ru: `"col_compression": "Сжатие"`

- [ ] **Step 3: Failing test for new column**

Append to `frontend/src/__tests__/UsageByProjectTable.test.tsx`:

```tsx
it("renders compression column when ratio is non-null", () => {
  const row = {
    project: "alpha",
    period_days: 30,
    sessions_covered: 10,
    tokens_input: 100,
    tokens_output: 200,
    tokens_injected: 50,
    raw_bytes_total: 1024,
    tokens_per_byte: 0.293,
    avg_compression_ratio: 4.5,
    inject_events_count: 7,
    valid_events_count: 7,
  };
  render(<MemoryRouter><UsageByProjectTable rows={[row]} /></MemoryRouter>);
  // Compression cell renders something like "4.5× (7 events)"
  expect(screen.getByText(/4\.5/)).toBeInTheDocument();
  expect(screen.getByText(/7/)).toBeInTheDocument();
});

it("renders dash in compression column when ratio is null", () => {
  const row = {
    project: "alpha",
    period_days: 30,
    sessions_covered: 0,
    tokens_input: 0,
    tokens_output: 0,
    tokens_injected: 0,
    raw_bytes_total: 0,
    tokens_per_byte: null,
    avg_compression_ratio: null,
    inject_events_count: 0,
    valid_events_count: 0,
  };
  render(<MemoryRouter><UsageByProjectTable rows={[row]} /></MemoryRouter>);
  // The "Compression" header cell exists; the row cell renders "—" or similar.
  expect(screen.getByText(/Compression/i)).toBeInTheDocument();
});
```

(Update the existing test bundle's `metrics` keys to include `col_compression`.)

- [ ] **Step 4: Run → expect FAIL**

```bash
cd /d/code/claude-mnemos/frontend
pnpm test UsageByProjectTable 2>&1 | tail -10
```

- [ ] **Step 5: Add column to UsageByProjectTable**

Edit `frontend/src/components/widgets/UsageByProjectTable.tsx`. Add header cell + body cell:

In `<thead>`, append:

```tsx
<th className="py-1 text-right font-medium">{t("metrics.col_compression")}</th>
```

In each row body, append (last cell):

```tsx
<td className="py-1.5 text-right font-mono text-xs">
  {r.avg_compression_ratio !== null
    ? `${r.avg_compression_ratio.toFixed(1)}× (${r.inject_events_count})`
    : "—"}
</td>
```

- [ ] **Step 6: Run → expect PASS**

```bash
pnpm test UsageByProjectTable 2>&1 | tail -10
```

- [ ] **Step 7: Run all frontend tests + tsc + lint**

```bash
pnpm test && pnpm typecheck && pnpm lint 2>&1 | tail -10
```

Expected: 181+ pass; tsc clean; lint only pre-existing warnings.

- [ ] **Step 8: Commit**

```bash
cd /d/code/claude-mnemos
git add frontend/src/types/UsageSummary.ts frontend/src/components/widgets/UsageByProjectTable.tsx frontend/src/__tests__/UsageByProjectTable.test.tsx frontend/public/locales/
git commit -m "feat(frontend): #13e UsageByProjectTable compression column"
```

---

## Task 10: Final verification

- [ ] **Step 1: Backend full suite**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -3
```

Expected: ~1306+ passed (1296 baseline + ~10 new). 0 failed.

- [ ] **Step 2: ruff clean**

```bash
ruff check claude_mnemos/ tests/ hooks/ 2>&1 | tail -3
```

If errors, run `ruff check --fix` and inspect remaining; fix manually.

- [ ] **Step 3: Frontend full suite**

```bash
cd /d/code/claude-mnemos/frontend
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Expected: 181+ tests pass; tsc + ESLint clean (only 2 pre-existing); build succeeds.

- [ ] **Step 4: Acceptance criteria walk-through (design §6)**

1. ✅ `build_page_graph` thin wrapper.
2. ✅ `_apply_cap` sorts by timestamp.
3. ✅ Both summaries use `_period_cutoff_dt`.
4. ✅ `append_to_vault` acquires file lock.
5. ✅ `/metrics/inject/timeline` returns daily aggregates.
6. ✅ `<CompressionTimelineChart>` renders.
7. ✅ `/metrics/usage/by-project` per-row compression fields.
8. ✅ `<UsageByProjectTable>` shows compression column.
9. ✅ Backend baseline holds.
10. ✅ Frontend baseline holds.
11. ✅ ruff + tsc + ESLint clean.
12. ⚠️ Manual smoke: TBD on user's machine after merge.

- [ ] **Step 5: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

~10 commits, working tree clean.

- [ ] **Step 6: Optional commit if anything dangling**

If small fix-up emerged during verification, commit. Otherwise verification-only.

---

## Spec coverage map

| Design § | Plan task |
|---|---|
| 2.1 build_page_graph wrapper | 1 |
| 2.2 _apply_cap sort | 2 |
| 2.3 unified cutoff helper | 3 |
| 2.4 file lock | 4 |
| 2.5 compression_timeline aggregator | 5 |
| 2.6 timeline daemon route | 6 |
| 2.7 frontend chart | 7 |
| 2.8 per-project breakdown backend | 8 |
| 2.8 per-project breakdown frontend | 9 |
| §6 ACs | 10 |
