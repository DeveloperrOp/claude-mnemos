from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.state.inject_metrics import (
    INJECT_METRICS_FILENAME,
    MAX_EVENTS,
    RETENTION_DAYS,
    InjectMetricEvent,
    InjectMetricsCorruptError,
    InjectMetricsLog,
)


def _make_event(*, idx: int = 0, ts: datetime | None = None) -> InjectMetricEvent:
    return InjectMetricEvent(
        id=f"evt-{idx:06d}",
        timestamp=ts or datetime.now(UTC),
        session_id=f"s-{idx}",
        operation="session_start",
        mode="full",
        tokens_full=1000,
        tokens_actual=200,
        candidates_total=10,
        candidates_packed=10,
    )


def test_load_empty_vault_returns_empty_log(tmp_path: Path) -> None:
    log = InjectMetricsLog.load(tmp_path)
    assert log.events == []


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    log = InjectMetricsLog()
    log.events.append(_make_event(idx=1))
    log.save(tmp_path)

    fresh = InjectMetricsLog.load(tmp_path)
    assert len(fresh.events) == 1
    assert fresh.events[0].id == "evt-000001"


def test_append_to_vault_persists(tmp_path: Path) -> None:
    InjectMetricsLog.append_to_vault(tmp_path, _make_event(idx=1))
    InjectMetricsLog.append_to_vault(tmp_path, _make_event(idx=2))
    log = InjectMetricsLog.load(tmp_path)
    assert [e.id for e in log.events] == ["evt-000001", "evt-000002"]


def test_append_rejects_duplicate_id(tmp_path: Path) -> None:
    InjectMetricsLog.append_to_vault(tmp_path, _make_event(idx=1))
    with pytest.raises(ValueError):
        InjectMetricsLog.append_to_vault(tmp_path, _make_event(idx=1))


def test_save_drops_events_older_than_retention(tmp_path: Path) -> None:
    log = InjectMetricsLog()
    old_ts = datetime.now(UTC) - timedelta(days=RETENTION_DAYS + 5)
    log.events.append(_make_event(idx=0, ts=old_ts))
    log.events.append(_make_event(idx=1))  # fresh
    log.save(tmp_path)

    fresh = InjectMetricsLog.load(tmp_path)
    assert len(fresh.events) == 1
    assert fresh.events[0].id == "evt-000001"


def test_save_caps_at_max_events(tmp_path: Path) -> None:
    log = InjectMetricsLog()
    for i in range(MAX_EVENTS + 50):
        log.events.append(_make_event(idx=i))
    log.save(tmp_path)

    fresh = InjectMetricsLog.load(tmp_path)
    assert len(fresh.events) == MAX_EVENTS
    assert fresh.events[0].id == f"evt-{50:06d}"


def test_load_corrupt_raises(tmp_path: Path) -> None:
    (tmp_path / INJECT_METRICS_FILENAME).write_text("not json", encoding="utf-8")
    with pytest.raises(InjectMetricsCorruptError):
        InjectMetricsLog.load(tmp_path)


def test_load_invalid_schema_raises(tmp_path: Path) -> None:
    (tmp_path / INJECT_METRICS_FILENAME).write_text(
        json.dumps({"version": 1, "events": [{"id": "x"}]}),
        encoding="utf-8",
    )
    with pytest.raises(InjectMetricsCorruptError):
        InjectMetricsLog.load(tmp_path)


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
    kept_indices = sorted(int(e.id.split("-")[1]) for e in fresh.events)
    # The newest events have the lowest indices (because reverse insert).
    # The 5 oldest by timestamp (highest indices) must be dropped.
    assert kept_indices[0] == 0  # newest is kept
    assert kept_indices[-1] == MAX_EVENTS - 1  # oldest kept is index MAX-1
    assert all(i < MAX_EVENTS for i in kept_indices)


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
    assert len(log.events) == n_events * 2, (
        f"expected {n_events * 2} events, got {len(log.events)} — "
        "concurrent writes lost data"
    )
