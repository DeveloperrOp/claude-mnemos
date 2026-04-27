"""REST routes for token usage metrics (Plan #13a §3.5 Task 8).

All four endpoints are read-only views over the manifest — they don't need a
running daemon. Period parameters use the ``Nd`` shorthand (``"30d"``,
``"7d"``); :func:`_parse_period` raises HTTP 400 on anything else so callers
get a clear error instead of a silent default.

The ``/by-project`` endpoint currently returns a single ``"default"`` entry
because mnemos is single-vault today; Plan #13b promotes it to real
per-project aggregation once vaults gain a project dimension.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import metrics as core_metrics

router = APIRouter()


def _vault(request: Request) -> Path:
    vault = request.app.state.vault_root
    assert isinstance(vault, Path)
    return vault


def _parse_period(period: str) -> int:
    """Parse ``"Nd"`` → ``N``. Raises HTTP 400 on anything else.

    Only ``d`` (days) is supported in Plan #13a. Future scales (``w``, ``m``)
    can be added without breaking callers because the failure mode is a clean
    400 rather than a silent default.
    """
    if period.endswith("d"):
        try:
            value = int(period[:-1])
        except ValueError:
            value = -1
        if value > 0:
            return value
    raise HTTPException(
        status_code=400,
        detail={"error": "invalid_period_format", "expected": "Nd", "got": period},
    )


@router.get("/metrics/usage")
async def usage_route(request: Request, period: str = "30d") -> dict[str, Any]:
    days = _parse_period(period)
    summary = core_metrics.usage_summary(_vault(request), period_days=days)
    dumped: dict[str, Any] = summary.model_dump(mode="json")
    return dumped


@router.get("/metrics/usage/by-project")
async def by_project_route(request: Request) -> dict[str, Any]:
    """Single-vault stub. Plan #13b adds real per-project aggregation."""
    summary = core_metrics.usage_summary(_vault(request))
    return {"projects": [{"project": "default", **summary.model_dump(mode="json")}]}


@router.get("/metrics/usage/top-sessions")
async def top_sessions_route(request: Request, limit: int = 10) -> dict[str, Any]:
    items = core_metrics.top_sessions(_vault(request), limit=limit)
    return {"sessions": [m.model_dump(mode="json") for m in items]}


@router.get("/metrics/usage/timeline")
async def timeline_route(request: Request, period: str = "30d") -> dict[str, Any]:
    days = _parse_period(period)
    points = core_metrics.timeline(_vault(request), period_days=days)
    return {"points": [p.model_dump(mode="json") for p in points]}
