"""Tests for `claude_mnemos.core.metrics` — token usage aggregations."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from claude_mnemos.core.metrics import (
    SessionMetric,
    TimelinePoint,
    UsageSummary,
    timeline,
    top_sessions,
    usage_summary,
)
from claude_mnemos.state.manifest import IngestRecord, Manifest


def _ingest_record(
    sid: str,
    *,
    ingested_at: datetime,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    raw_transcript_bytes: int | None = None,
) -> IngestRecord:
    return IngestRecord(
        session_id=sid,
        ingested_at=ingested_at,
        raw_path=f"raw/chats/{sid}.md",
        source_path=f"wiki/sources/{sid}.md",
        created_pages=[],
        skipped_collisions=[],
        model=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        transcript_path=None,
        raw_transcript_bytes=raw_transcript_bytes,
    )


# ---------------------------------------------------------------------------
# usage_summary
# ---------------------------------------------------------------------------


def test_usage_summary_empty_manifest_returns_all_zero(tmp_path: Path) -> None:
    summary = usage_summary(tmp_path)
    assert isinstance(summary, UsageSummary)
    assert summary.period_days == 30
    assert summary.sessions_covered == 0
    assert summary.tokens_input == 0
    assert summary.tokens_output == 0
    assert summary.tokens_injected == 0
    assert summary.raw_bytes_total == 0
    assert summary.tokens_per_byte is None


def test_usage_summary_sums_three_records_with_mixed_none_tokens(
    tmp_path: Path,
) -> None:
    today = date(2026, 4, 27)
    base = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)

    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "a",
            ingested_at=base,
            input_tokens=100,
            output_tokens=200,
            raw_transcript_bytes=1000,
        ),
    )
    m.add(
        "sha-2",
        _ingest_record(
            "b",
            ingested_at=base,
            input_tokens=None,
            output_tokens=50,
            raw_transcript_bytes=500,
        ),
    )
    m.add(
        "sha-3",
        _ingest_record(
            "c",
            ingested_at=base,
            input_tokens=10,
            output_tokens=None,
            raw_transcript_bytes=None,
        ),
    )
    m.save(tmp_path)

    summary = usage_summary(tmp_path, period_days=30, today=today)
    assert summary.sessions_covered == 3
    assert summary.tokens_input == 110  # 100 + 0 + 10
    assert summary.tokens_output == 250  # 200 + 50 + 0
    assert summary.tokens_injected == 360
    assert summary.raw_bytes_total == 1500  # 1000 + 500 + 0
    assert summary.tokens_per_byte is not None
    assert summary.tokens_per_byte == 250 / 1500


def test_usage_summary_period_days_filter_excludes_old_entries(
    tmp_path: Path,
) -> None:
    today = date(2026, 4, 27)
    in_window = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)
    out_of_window = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

    m = Manifest()
    m.add(
        "sha-fresh",
        _ingest_record(
            "fresh",
            ingested_at=in_window,
            input_tokens=10,
            output_tokens=20,
            raw_transcript_bytes=100,
        ),
    )
    m.add(
        "sha-old",
        _ingest_record(
            "old",
            ingested_at=out_of_window,
            input_tokens=5000,
            output_tokens=5000,
            raw_transcript_bytes=99999,
        ),
    )
    m.save(tmp_path)

    summary = usage_summary(tmp_path, period_days=7, today=today)
    assert summary.sessions_covered == 1
    assert summary.tokens_input == 10
    assert summary.tokens_output == 20
    assert summary.raw_bytes_total == 100


def test_usage_summary_tokens_per_byte_none_when_raw_bytes_zero(
    tmp_path: Path,
) -> None:
    today = date(2026, 4, 27)
    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "a",
            ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
            input_tokens=10,
            output_tokens=20,
            raw_transcript_bytes=None,
        ),
    )
    m.save(tmp_path)

    summary = usage_summary(tmp_path, period_days=30, today=today)
    assert summary.raw_bytes_total == 0
    assert summary.tokens_per_byte is None


# ---------------------------------------------------------------------------
# top_sessions
# ---------------------------------------------------------------------------


def test_top_sessions_sorts_by_total_tokens_desc_and_respects_limit(
    tmp_path: Path,
) -> None:
    base = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    m = Manifest()
    # Five records with varying totals.
    cases = [
        ("a", 10, 10),    # 20
        ("b", 100, 200),  # 300  → top
        ("c", None, 50),  # 50
        ("d", 80, 100),   # 180  → second
        ("e", 5, 5),      # 10
    ]
    for sid, ti, to in cases:
        m.add(
            f"sha-{sid}",
            _ingest_record(
                sid,
                ingested_at=base,
                input_tokens=ti,
                output_tokens=to,
                raw_transcript_bytes=10,
            ),
        )
    m.save(tmp_path)

    result = top_sessions(tmp_path, limit=2)
    assert len(result) == 2
    assert all(isinstance(item, SessionMetric) for item in result)
    assert result[0].session_id == "b"
    assert result[0].tokens_total == 300
    assert result[1].session_id == "d"
    assert result[1].tokens_total == 180


def test_top_sessions_negative_limit_returns_empty(tmp_path: Path) -> None:
    base = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    m = Manifest()
    m.add(
        "sha-only",
        _ingest_record(
            "only",
            ingested_at=base,
            input_tokens=100,
            output_tokens=200,
            raw_transcript_bytes=10,
        ),
    )
    m.save(tmp_path)

    # Without clamping, negative limits use Python's "all but last N" slice
    # semantics, which is the wrong behaviour for a "top N" function.
    assert top_sessions(tmp_path, limit=-1) == []
    assert top_sessions(tmp_path, limit=-100) == []


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------


def test_timeline_buckets_per_day_with_zero_fill(tmp_path: Path) -> None:
    today = date(2026, 4, 27)
    period_days = 7

    same_day = datetime(2026, 4, 26, 9, 0, 0, tzinfo=UTC)
    same_day_other_hour = datetime(2026, 4, 26, 18, 30, 0, tzinfo=UTC)

    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "a",
            ingested_at=same_day,
            input_tokens=10,
            output_tokens=20,
            raw_transcript_bytes=100,
        ),
    )
    m.add(
        "sha-2",
        _ingest_record(
            "b",
            ingested_at=same_day_other_hour,
            input_tokens=5,
            output_tokens=15,
            raw_transcript_bytes=50,
        ),
    )
    m.save(tmp_path)

    points = timeline(tmp_path, period_days=period_days, today=today)
    assert len(points) == period_days
    assert all(isinstance(p, TimelinePoint) for p in points)

    # Ordered ascending by date and ends on `today`.
    expected_first = today - timedelta(days=period_days - 1)
    assert points[0].date == expected_first
    assert points[-1].date == today
    for i in range(1, len(points)):
        assert points[i].date == points[i - 1].date + timedelta(days=1)

    by_date = {p.date: p for p in points}
    bucket = by_date[date(2026, 4, 26)]
    assert bucket.sessions == 2
    assert bucket.tokens_input == 15
    assert bucket.tokens_output == 35

    # Days without records have zeros.
    other = by_date[date(2026, 4, 25)]
    assert other.sessions == 0
    assert other.tokens_input == 0
    assert other.tokens_output == 0
