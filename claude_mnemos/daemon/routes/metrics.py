"""REST routes for token usage metrics — cross-vault aggregation (Plan #13b-β2 Task 13).

All four endpoints aggregate across every mounted VaultRuntime via
``all_runtimes(request)``.  When no vaults are mounted the aggregations return
zero-totals / empty lists instead of HTTP 503.

Period parameters use the ``Nd`` shorthand (``"30d"``, ``"7d"``);
:func:`_parse_period` raises HTTP 400 on anything else so callers get a clear
error instead of a silent default.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import date as date_class

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import metrics as core_metrics
from claude_mnemos.daemon.routes._helpers import all_runtimes

router = APIRouter()


_PERIOD_RE = re.compile(r"^(?P<n>\d+)(?P<unit>[dwmy])$")
_PERIOD_UNIT_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}


def _parse_period(period: str) -> int:
    """Parse ``"Nd"`` / ``"Nw"`` / ``"Nm"`` / ``"Ny"`` → number of days.

    Raises HTTP 400 on anything else. Months and years use approximations
    (30 / 365) — sufficient for dashboard windowing, where exact calendar
    boundaries are not load-bearing.
    """
    m = _PERIOD_RE.match(period)
    if m:
        n = int(m.group("n"))
        unit = m.group("unit")
        if n > 0:
            return n * _PERIOD_UNIT_DAYS[unit]
    raise HTTPException(
        status_code=400,
        detail={"error": "invalid_period_format", "expected": "Nd|Nw|Nm|Ny", "got": period},
    )


@router.get("/metrics/usage")
async def usage_route(request: Request, period: str = "30d") -> dict[str, Any]:
    """Aggregate token usage totals across all mounted vaults."""
    days = _parse_period(period)
    total_input = 0
    total_output = 0
    sessions_covered = 0
    raw_bytes_total = 0
    compression_per_vault: list[core_metrics.CompressionSummary] = []
    for runtime in all_runtimes(request):
        s = core_metrics.usage_summary(runtime.vault_root, period_days=days)
        total_input += s.tokens_input
        total_output += s.tokens_output
        sessions_covered += s.sessions_covered
        raw_bytes_total += s.raw_bytes_total
        compression_per_vault.append(
            core_metrics.compression_summary(runtime.vault_root, period_days=days)
        )
    tokens_injected = total_input + total_output
    tokens_per_byte: float | None = (
        total_output / raw_bytes_total if raw_bytes_total > 0 else None
    )

    # Weighted average across vaults: weight = valid_events_count (events
    # with tokens_actual > 0), which is the basis for each vault's local
    # avg_compression_ratio. Using events_count instead would over-weight
    # vaults where most events have tokens_actual == 0.
    weighted_sum = sum(
        (c.avg_compression_ratio or 0.0) * c.valid_events_count
        for c in compression_per_vault
        if c.avg_compression_ratio is not None
    )
    valid_events_total = sum(
        c.valid_events_count
        for c in compression_per_vault
        if c.avg_compression_ratio is not None
    )
    avg_compression_ratio: float | None = (
        weighted_sum / valid_events_total if valid_events_total > 0 else None
    )
    inject_events_count = sum(c.events_count for c in compression_per_vault)

    return {
        "period": period,
        "period_days": days,
        "sessions_covered": sessions_covered,
        "tokens_input": total_input,
        "tokens_output": total_output,
        "tokens_injected": tokens_injected,
        "raw_bytes_total": raw_bytes_total,
        "tokens_per_byte": tokens_per_byte,
        "avg_compression_ratio": avg_compression_ratio,
        "inject_events_count": inject_events_count,
    }


@router.get("/metrics/usage/by-project")
async def by_project_route(request: Request, period: str = "30d") -> dict[str, Any]:
    """Per-project breakdown — one entry per mounted vault."""
    days = _parse_period(period)
    projects = []
    for runtime in all_runtimes(request):
        s = core_metrics.usage_summary(runtime.vault_root, period_days=days)
        c = core_metrics.compression_summary(runtime.vault_root, period_days=days)
        entry: dict[str, Any] = {"project": runtime.name}
        entry.update(s.model_dump(mode="json"))
        # Per-project compression fields (Plan #13e)
        entry["avg_compression_ratio"] = c.avg_compression_ratio
        entry["inject_events_count"] = c.events_count
        entry["valid_events_count"] = c.valid_events_count
        projects.append(entry)
    return {"projects": projects}


@router.get("/metrics/usage/top-sessions")
async def top_sessions_route(request: Request, limit: int = 10) -> dict[str, Any]:
    """Top N sessions by combined token count, merged across all vaults."""
    aggregated: list[dict[str, Any]] = []
    for runtime in all_runtimes(request):
        for m in core_metrics.top_sessions(runtime.vault_root, limit=limit):
            d = m.model_dump(mode="json")
            d["project"] = runtime.name
            aggregated.append(d)
    aggregated.sort(key=lambda x: x.get("tokens_total") or 0, reverse=True)
    return {"sessions": aggregated[:limit]}


@router.get("/metrics/usage/timeline")
async def timeline_route(request: Request, period: str = "30d") -> dict[str, Any]:
    """Per-day token usage merged across all vaults, zero-filled for missing days."""
    days = _parse_period(period)
    by_date: dict[str, dict[str, Any]] = {}
    for runtime in all_runtimes(request):
        for p in core_metrics.timeline(runtime.vault_root, period_days=days):
            d = p.model_dump(mode="json")
            date_key = str(d["date"])
            entry = by_date.setdefault(
                date_key,
                {
                    "date": date_key,
                    "sessions": 0,
                    "tokens_input": 0,
                    "tokens_output": 0,
                },
            )
            entry["sessions"] += d.get("sessions", 0)
            entry["tokens_input"] += d.get("tokens_input", 0)
            entry["tokens_output"] += d.get("tokens_output", 0)
    # When no runtimes are mounted produce a zero-filled timeline for the
    # requested window so callers always get a usable structure.
    if not by_date:
        today = datetime.now(UTC).date()
        start = today - timedelta(days=days - 1)
        for i in range(days):
            d_str = str(start + timedelta(days=i))
            by_date[d_str] = {
                "date": d_str,
                "sessions": 0,
                "tokens_input": 0,
                "tokens_output": 0,
            }
    points = sorted(by_date.values(), key=lambda p: p["date"])
    return {"points": points}


@router.get("/metrics/inject/timeline")
async def inject_timeline_route(
    request: Request,
    period: str = "30d",
) -> dict[str, Any]:
    """Per-day inject event buckets aggregated across all mounted vaults.

    Each bucket carries ``events_count`` (all events that day),
    ``valid_events_count`` (events with ``tokens_actual > 0``), and
    ``avg_compression_ratio`` weighted by ``valid_events_count`` across
    vaults. Days with no valid events return ``avg_compression_ratio = None``.
    Output is zero-filled for the full window so chart axes line up.
    """
    days = _parse_period(period)
    today = datetime.now(UTC).date()

    aggregated: dict[date_class, dict[str, Any]] = {}
    for runtime in all_runtimes(request):
        vault_points = core_metrics.compression_timeline(
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

    # When no vaults are mounted, zero-fill the window so callers always
    # get a usable structure (mirrors /metrics/usage/timeline).
    if not aggregated:
        start = today - timedelta(days=days)
        for i in range(days):
            aggregated[start + timedelta(days=i)] = {
                "events": 0,
                "valid": 0,
                "ratio_weighted_sum": 0.0,
            }

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
