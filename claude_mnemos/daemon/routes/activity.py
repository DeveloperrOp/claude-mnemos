from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

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
    return {
        "entries": [e.model_dump(mode="json") for e in sliced],
        "total": total,
    }


@router.get("/activity/{project}/{op_id}", response_model=ActivityEntry)
async def get_activity(project: str, op_id: str, request: Request) -> ActivityEntry:
    runtime = get_runtime(request, project)
    log = ActivityLog.load(runtime.vault_root)
    entry = log.find_by_id(op_id)
    if entry is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "id": op_id})
    return entry


@router.post("/activity/{project}/{op_id}/undo", response_model=UndoApiResult)
def undo_activity(project: str, op_id: str, request: Request) -> UndoApiResult:
    runtime = get_runtime(request, project)
    # tracker pauses the watchdog around the swap — without it the content-swap
    # fallback floods the alert ring with one external_create per restored page.
    result = undo(
        runtime.vault_root, op_id, tracker=runtime.tracker
    )  # raises UndoError / LockTimeoutError → handled in app
    return UndoApiResult(
        success=result.success,
        op_id=op_id,
        restored_pages=list(result.restored_pages),
        new_entry_id=result.new_entry_id,
    )
