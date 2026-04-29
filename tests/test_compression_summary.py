from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from claude_mnemos.core.metrics import CompressionSummary, compression_summary
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
    session_id: str | None = None,
) -> InjectMetricEvent:
    return InjectMetricEvent(
        id=f"evt-{idx:06d}",
        timestamp=ts,
        session_id=session_id or f"s-{idx}",
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


def test_compression_summary_empty(tmp_path: Path) -> None:
    out = compression_summary(tmp_path, period_days=30)
    assert isinstance(out, CompressionSummary)
    assert out.events_count == 0
    assert out.sessions_covered == 0
    assert out.avg_compression_ratio is None
    assert out.total_tokens_full == 0
    assert out.total_tokens_actual == 0


def test_compression_summary_one_event(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [_make_event(idx=1, ts=now, tokens_full=1000, tokens_actual=200)])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 1
    assert out.sessions_covered == 1
    assert out.avg_compression_ratio == 5.0
    assert out.total_tokens_full == 1000
    assert out.total_tokens_actual == 200


def test_compression_summary_avg_is_mean_of_ratios(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=now, tokens_full=1000, tokens_actual=200),
        _make_event(idx=2, ts=now, tokens_full=600, tokens_actual=200),
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 2
    assert out.avg_compression_ratio == 4.0


def test_compression_summary_excludes_old_events(tmp_path: Path) -> None:
    today = datetime.now(UTC)
    old = today - timedelta(days=60)
    _seed(tmp_path, [
        _make_event(idx=1, ts=old, tokens_full=999, tokens_actual=99),
        _make_event(idx=2, ts=today, tokens_full=1000, tokens_actual=200),
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 1
    assert out.avg_compression_ratio == 5.0


def test_compression_summary_skips_zero_actual(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=now, tokens_full=500, tokens_actual=0),
        _make_event(idx=2, ts=now, tokens_full=1000, tokens_actual=200),
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 2
    assert out.avg_compression_ratio == 5.0
    assert out.total_tokens_full == 1500
    assert out.total_tokens_actual == 200


def test_compression_summary_all_zero_actual_returns_none(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [_make_event(idx=1, ts=now, tokens_full=500, tokens_actual=0)])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 1
    assert out.avg_compression_ratio is None


def test_compression_summary_sessions_covered_counts_unique(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=now, session_id="s-shared"),
        _make_event(idx=2, ts=now, session_id="s-shared"),
        _make_event(idx=3, ts=now, session_id="s-other"),
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 3
    assert out.sessions_covered == 2
