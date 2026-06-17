"""Auto-update REST endpoints — banner status + dismiss snooze."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body

from claude_mnemos.core.update_check import check_for_update, dismiss_for_days

router = APIRouter()


@router.get("/update-status")
def update_status_route() -> dict[str, Any]:
    s = check_for_update(force=False)
    suppress = (
        s.dismissed_until is not None
        and s.dismissed_until > datetime.now(tz=UTC)
    )
    return {
        "current": s.current,
        "latest": s.latest,
        "download_url": s.download_url,
        "asset_url": s.asset_url,
        "has_update": s.has_update and not suppress,
        "checked_at": s.checked_at.isoformat(),
        "dismissed_until": (
            s.dismissed_until.isoformat() if s.dismissed_until else None
        ),
        "error": s.error,
    }


@router.post("/update-status/dismiss")
def dismiss_route(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    days = int(payload.get("days", 7))
    days = max(1, min(days, 30))
    dismiss_for_days(days)
    return {"ok": True, "dismissed_for_days": days}
