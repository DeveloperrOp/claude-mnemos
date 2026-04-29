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
    assert out.valid_events_count == 0
    assert out.avg_compression_ratio is None


def test_compression_summary_valid_events_count_excludes_zero_actual(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=now, tokens_full=500, tokens_actual=0),
        _make_event(idx=2, ts=now, tokens_full=1000, tokens_actual=200),
        _make_event(idx=3, ts=now, tokens_full=600, tokens_actual=300),
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 3
    assert out.valid_events_count == 2  # only the two with tokens_actual > 0


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


def test_usage_summary_excludes_pre_cutoff_event(tmp_path: Path) -> None:
    """usage_summary excludes events from the day before the cutoff,
    matching compression_summary's UTC-midnight cutoff semantics."""
    from claude_mnemos.core.atomic import atomic_write
    from claude_mnemos.core.metrics import usage_summary
    from claude_mnemos.state.manifest import IngestRecord, Manifest

    today = datetime.now(UTC).date()
    pre_boundary = today - timedelta(days=31)  # one day before cutoff
    pre_ts = datetime.combine(
        pre_boundary, datetime.min.time(), UTC
    ) + timedelta(hours=23, minutes=59)

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


def test_usage_summary_includes_boundary_day_event(tmp_path: Path) -> None:
    """Event at 22:00 UTC on the cutoff day (today - period_days) should be included."""
    from claude_mnemos.core.atomic import atomic_write
    from claude_mnemos.core.metrics import usage_summary
    from claude_mnemos.state.manifest import IngestRecord, Manifest

    today = datetime.now(UTC).date()
    boundary_day = today - timedelta(days=30)
    boundary_ts = datetime.combine(boundary_day, datetime.min.time(), UTC) + timedelta(hours=22)

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
    assert out.sessions_covered == 1
