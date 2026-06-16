from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from claude_mnemos.core.undo import can_undo as live_can_undo
from claude_mnemos.core.undo import undo
from claude_mnemos.daemon.routes._helpers import get_runtime
from claude_mnemos.daemon.schemas import UndoApiResult
from claude_mnemos.state.activity import ActivityEntry, ActivityLog

router = APIRouter()


@router.get("/activity/{project}")
async def list_activity(
    project: str,
    request: Request,
    limit: int = Query(default=20, ge=0, le=10000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    log = ActivityLog.load(runtime.vault_root)
    entries = list(reversed(log.entries))  # newest first
    total = len(entries)
    sliced = entries[offset:] if limit == 0 else entries[offset : offset + limit]
    # Recompute can_undo LIVE: the stored flag is set at write time and goes
    # stale if the user later deletes the underlying snapshot. Without this
    # the UI keeps an enabled Undo button that fails with a cryptic error.
    out: list[dict[str, Any]] = []
    for e in sliced:
        d = e.model_dump(mode="json")
        d["can_undo"] = live_can_undo(e, runtime.vault_root)
        out.append(d)
    return {"entries": out, "total": total}


@router.get("/activity/{project}/{op_id}", response_model=ActivityEntry)
async def get_activity(project: str, op_id: str, request: Request) -> ActivityEntry:
    runtime = get_runtime(request, project)
    log = ActivityLog.load(runtime.vault_root)
    entry = log.find_by_id(op_id)
    if entry is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "id": op_id})
    # Live can_undo (see list_activity) — a deleted snapshot flips it to false.
    return entry.model_copy(
        update={"can_undo": live_can_undo(entry, runtime.vault_root)}
    )


@router.post("/activity/{project}/{op_id}/undo", response_model=UndoApiResult)
def undo_activity(project: str, op_id: str, request: Request) -> UndoApiResult:
    runtime = get_runtime(request, project)
    # tracker pauses the watchdog around the swap — without it the content-swap
    # fallback floods the alert ring with one external_create per restored page.
    result = undo(
        runtime.vault_root, op_id, tracker=runtime.tracker
    )  # raises UndoError / LockTimeoutError → handled in app
    # The undo restored a snapshot IN PLACE — the observer survived, so its
    # signature cache is now stale (pre-undo content). Reseed from disk or the
    # next read of a restored page would be misread as a human edit and
    # false-flip its provenance. (Sync route → runs in a threadpool, so the
    # disk walk doesn't block the event loop.)
    runtime.reseed_watchdog()
    return UndoApiResult(
        success=result.success,
        op_id=op_id,
        restored_pages=list(result.restored_pages),
        new_entry_id=result.new_entry_id,
    )
