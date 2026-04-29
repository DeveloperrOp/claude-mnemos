from __future__ import annotations

from datetime import UTC, date, datetime
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
    assert len(out) == 7
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
    by_date = {p.date: p for p in out}
    assert by_date[date(2026, 4, 27)].events_count == 2
    assert by_date[date(2026, 4, 27)].valid_events_count == 2
    assert by_date[date(2026, 4, 27)].avg_compression_ratio == 4.0
    assert by_date[date(2026, 4, 28)].events_count == 1
    assert by_date[date(2026, 4, 28)].avg_compression_ratio == 4.0


def test_compression_timeline_ratio_none_for_zero_actual(tmp_path: Path) -> None:
    today = date(2026, 4, 29)
    day1 = datetime(2026, 4, 28, 14, 0, tzinfo=UTC)
    _seed(tmp_path, [_make_event(idx=1, ts=day1, tokens_full=500, tokens_actual=0)])
    out = compression_timeline(tmp_path, period_days=7, today=today)
    by_date = {p.date: p for p in out}
    p = by_date[date(2026, 4, 28)]
    assert p.events_count == 1
    assert p.valid_events_count == 0
    assert p.avg_compression_ratio is None


def test_compression_timeline_excludes_outside_window(tmp_path: Path) -> None:
    today = date(2026, 4, 29)
    pre = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    _seed(tmp_path, [_make_event(idx=1, ts=pre, tokens_full=999, tokens_actual=99)])
    out = compression_timeline(tmp_path, period_days=7, today=today)
    assert all(p.events_count == 0 for p in out)


def test_compression_timeline_sorted_ascending(tmp_path: Path) -> None:
    today = date(2026, 4, 29)
    out = compression_timeline(tmp_path, period_days=5, today=today)
    dates = [p.date for p in out]
    assert dates == sorted(dates)
    assert dates[0] == date(2026, 4, 24)
    assert dates[-1] == date(2026, 4, 28)
