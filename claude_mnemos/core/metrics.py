"""Token usage aggregations over the manifest (Plan #13a §3.4).

Three pure read-only views computed from :class:`~claude_mnemos.state.manifest.Manifest`:

* :func:`usage_summary` — totals over a rolling window (default 30 days).
* :func:`top_sessions` — heaviest sessions by combined input + output tokens.
* :func:`timeline` — per-day buckets with zero-fill for missing days, intended
  for a clean line/bar chart in the dashboard (Plan #14).

Records with ``None`` token counts contribute zero to the aggregates but still
count toward ``sessions_covered`` and per-day session counts. Records with
``ingested_at`` outside the requested window are silently excluded from
``usage_summary``/``timeline`` (but appear in ``top_sessions``, which is
window-agnostic by design — top sessions of all time).

``tokens_per_byte`` is computed as ``tokens_output / raw_bytes_total`` and
is ``None`` whenever the denominator is zero (no raw bytes recorded). It
expresses how many emitted tokens we get per byte of raw transcript — a
rough proxy for ingest density per design doc §3.4. NOT the spec §15
``compression_ratio`` (which compares full vs adaptive token counts and
will land in Plan #13c).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as date_class
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from claude_mnemos.state.inject_metrics import InjectMetricsLog
from claude_mnemos.state.manifest import IngestRecord, Manifest


class UsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_days: int
    sessions_covered: int
    tokens_input: int
    tokens_output: int
    tokens_injected: int
    raw_bytes_total: int
    tokens_per_byte: float | None


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


class CompressionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_days: int
    events_count: int
    valid_events_count: int  # events with tokens_actual > 0 — basis for the ratio
    sessions_covered: int
    avg_compression_ratio: float | None
    total_tokens_full: int
    total_tokens_actual: int


def _records_in_window(
    manifest: Manifest,
    *,
    cutoff: date_class,
) -> list[IngestRecord]:
    """Return manifest records ingested on or after ``cutoff`` (inclusive)."""
    return [
        rec
        for rec in manifest.ingested.values()
        if rec.ingested_at.date() >= cutoff
    ]


def usage_summary(
    vault: Path,
    *,
    period_days: int = 30,
    today: date_class | None = None,
) -> UsageSummary:
    """Aggregate token usage over the last ``period_days`` days.

    Args:
        vault: Vault root containing ``.manifest.json``.
        period_days: Window length in days, ending on ``today`` (inclusive).
        today: Reference date; defaults to today (UTC). Tests inject this
            to keep results deterministic.

    Returns:
        :class:`UsageSummary` with per-window totals and tokens-per-byte ratio.
    """
    today = today or datetime.now(UTC).date()
    cutoff = today - timedelta(days=period_days)

    manifest = Manifest.load(vault)
    records = _records_in_window(manifest, cutoff=cutoff)

    tokens_input = sum((rec.input_tokens or 0) for rec in records)
    tokens_output = sum((rec.output_tokens or 0) for rec in records)
    raw_bytes_total = sum((rec.raw_transcript_bytes or 0) for rec in records)

    # tokens emitted per byte of raw transcript — proxy for ingest density.
    # NOT the spec §15 compression_ratio (which compares full vs adaptive
    # token counts; lands in Plan #13c).
    tokens_per_byte: float | None = (
        tokens_output / raw_bytes_total if raw_bytes_total > 0 else None
    )

    return UsageSummary(
        period_days=period_days,
        sessions_covered=len(records),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tokens_injected=tokens_input + tokens_output,
        raw_bytes_total=raw_bytes_total,
        tokens_per_byte=tokens_per_byte,
    )


def _record_to_metric(record: IngestRecord) -> SessionMetric:
    ti = record.input_tokens
    to = record.output_tokens
    total: int | None = (
        None if ti is None and to is None else (ti or 0) + (to or 0)
    )
    return SessionMetric(
        session_id=record.session_id,
        ingested_at=record.ingested_at,
        tokens_input=ti,
        tokens_output=to,
        tokens_total=total,
        raw_bytes=record.raw_transcript_bytes,
    )


def top_sessions(vault: Path, *, limit: int = 10) -> list[SessionMetric]:
    """Return the ``limit`` heaviest sessions sorted by combined tokens desc.

    Records with both token counts ``None`` rank as zero. Ties keep manifest
    iteration order — adequate for dashboard display where exact ordering
    among ties is not load-bearing.
    """
    manifest = Manifest.load(vault)
    metrics = [_record_to_metric(rec) for rec in manifest.ingested.values()]
    metrics.sort(key=lambda m: m.tokens_total or 0, reverse=True)
    # Clamp negative limit to 0 — Python slice with negative N returns "all
    # but last N" which would be wrong here; treat negative the same as 0.
    return metrics[: max(0, limit)]


def timeline(
    vault: Path,
    *,
    period_days: int = 30,
    today: date_class | None = None,
) -> list[TimelinePoint]:
    """Per-day buckets covering the last ``period_days`` days (inclusive of today).

    Days with no ingests appear with zero counts so chart axes line up cleanly.
    Output is sorted ascending by date.
    """
    today = today or datetime.now(UTC).date()
    start = today - timedelta(days=period_days - 1)

    # Pre-seed every day in the window with zeros so missing days are explicit.
    buckets: dict[date_class, TimelinePoint] = {
        start + timedelta(days=i): TimelinePoint(
            date=start + timedelta(days=i),
            sessions=0,
            tokens_input=0,
            tokens_output=0,
        )
        for i in range(period_days)
    }

    manifest = Manifest.load(vault)
    for rec in manifest.ingested.values():
        rec_date = rec.ingested_at.date()
        bucket = buckets.get(rec_date)
        if bucket is None:
            continue
        # Pydantic models are immutable by default for value semantics, but
        # this model uses default mutable behaviour (no ``frozen=True``), so
        # in-place updates are fine and avoid recomposing a new model per
        # record on hot-path.
        bucket.sessions += 1
        bucket.tokens_input += rec.input_tokens or 0
        bucket.tokens_output += rec.output_tokens or 0

    return [buckets[d] for d in sorted(buckets)]


def compression_summary(
    vault: Path,
    *,
    period_days: int = 30,
    today: date_class | None = None,
) -> CompressionSummary:
    """Aggregate inject-metric events over the last ``period_days`` days.

    ``avg_compression_ratio`` is the mean of ``tokens_full / tokens_actual``
    over events with ``tokens_actual > 0``. Returns ``None`` when no such
    events exist (no division by zero).

    Total token counts include all events in the window — even those with
    ``tokens_actual == 0`` — so the totals match the dashboard's "tokens
    saved" framing.
    """
    today = today or datetime.now(UTC).date()
    cutoff_dt = datetime.combine(
        today - timedelta(days=period_days), datetime.min.time(), UTC
    )

    log = InjectMetricsLog.load(vault)
    events = [e for e in log.events if e.timestamp >= cutoff_dt]

    valid = [e for e in events if e.tokens_actual > 0]
    avg = (
        sum(e.tokens_full / e.tokens_actual for e in valid) / len(valid)
        if valid
        else None
    )

    sessions_covered = len({e.session_id for e in events if e.session_id})

    return CompressionSummary(
        period_days=period_days,
        events_count=len(events),
        valid_events_count=len(valid),
        sessions_covered=sessions_covered,
        avg_compression_ratio=avg,
        total_tokens_full=sum(e.tokens_full for e in events),
        total_tokens_actual=sum(e.tokens_actual for e in events),
    )
