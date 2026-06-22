"""Auto-update REST endpoints — banner status + dismiss snooze."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from claude_mnemos.core import update_git, update_recovery
from claude_mnemos.core.update_apply import (
    UpdateApplyError,
    can_apply,
    spawn_updater,
    stage_update,
    update_in_progress,
)
from claude_mnemos.core.update_check import check_for_update, dismiss_for_days

router = APIRouter()


def _serialize_status(force: bool) -> dict[str, Any]:
    s = check_for_update(force=force)
    suppress = (
        s.dismissed_until is not None
        and s.dismissed_until > datetime.now(tz=UTC)
    )
    git_pullable = update_git.can_git_pull()
    return {
        # On a source checkout show git describe (the real checked-out state)
        # instead of the 0.0.1 source placeholder.
        "current": update_git.display_version() if git_pullable else s.current,
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
        # Source checkout (Python under a signed interpreter): updating is a
        # git pull + rebuild, not a SAC-blocked exe swap. Drives the in-app
        # "update from git" button.
        "can_git_pull": git_pullable,
    }


@router.get("/update-status")
def update_status_route() -> dict[str, Any]:
    return _serialize_status(force=False)


@router.post("/update-status/check")
def check_now_route() -> dict[str, Any]:
    """Force a live re-check against the release feed (bypasses the 24h cache).

    Backs the Overview "check for updates" button. Same response shape as
    GET /update-status so the frontend can reuse one type.
    """
    return _serialize_status(force=True)


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

    if update_in_progress():
        raise HTTPException(status_code=409, detail={"error": "in_progress"})

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


@router.post("/update/pull")
def pull_update_route() -> dict[str, Any]:
    """Source-mode self-update: ``git pull`` + frontend rebuild.

    For a git checkout running under a signed Python (the Smart-App-Control
    workaround) there's no exe to swap — pull the new code and rebuild the
    dashboard. The caller then restarts the daemon (POST /daemon/restart) so the
    tray respawns it on the new code. Refuses (409) when not a source checkout.
    """
    if not update_git.can_git_pull():
        raise HTTPException(
            status_code=409,
            detail={"error": "not_source_checkout"},
        )
    pulled, git_out = update_git.git_pull()
    if not pulled:
        raise HTTPException(
            status_code=502,
            detail={"error": "git_pull_failed", "detail": git_out},
        )
    built, build_out = update_git.frontend_build()
    # Restart so backend changes take effect. Tray-less: a detached helper
    # kills + relaunches the daemon after this response flushes. The dashboard
    # then polls /api/version and reloads once the fresh daemon answers.
    if built:
        update_git.restart_daemon_detached()
    return {
        "pulled": True,
        "git": git_out,
        "built": built,
        "build_detail": build_out,
        "restarting": built,
    }
