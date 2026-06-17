"""Auto-update REST endpoints — banner status + dismiss snooze."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from claude_mnemos.core import update_recovery
from claude_mnemos.core.update_apply import (
    UpdateApplyError,
    can_apply,
    spawn_updater,
    stage_update,
)
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
        "last_apply": update_recovery.read_last_apply(),
    }


@router.post("/update-status/dismiss")
def dismiss_route(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    days = int(payload.get("days", 7))
    days = max(1, min(days, 30))
    dismiss_for_days(days)
    return {"ok": True, "dismissed_for_days": days}


@router.post("/update/apply")
def apply_update_route() -> dict[str, Any]:
    """Stage the latest portable-zip release and spawn the elevated updater.

    Refuses (409) on anything but the installed Windows build, so the dev
    venv never spawns a swap. Re-checks the release feed live; on a real
    pending update it downloads + validates the asset, writes the updater
    script, and detaches an elevated PowerShell to perform the in-place swap
    (which kills this daemon).
    """
    ok, reason = can_apply()
    if not ok:
        raise HTTPException(
            status_code=409,
            detail={"error": "cannot_apply", "reason": reason},
        )

    s = check_for_update(force=True)
    if not s.has_update or not s.asset_url or not s.latest:
        raise HTTPException(status_code=409, detail={"error": "no_update"})

    try:
        work = stage_update(s.asset_url, s.latest)
    except UpdateApplyError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "stage_failed", "detail": str(exc)},
        ) from exc

    spawn_updater(work)
    return {"started": True, "version": s.latest}
