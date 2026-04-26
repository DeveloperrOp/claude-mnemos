from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from claude_mnemos.core.undo import undo
from claude_mnemos.daemon.schemas import UndoApiResult
from claude_mnemos.state.activity import ActivityEntry, ActivityLog

router = APIRouter()


@router.get("/activity")
async def list_activity(
    request: Request,
    limit: int = Query(default=20, ge=0, le=10000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    log = ActivityLog.load(vault)
    entries = list(reversed(log.entries))  # newest first
    total = len(entries)
    sliced = entries[offset:] if limit == 0 else entries[offset : offset + limit]
    return {
        "entries": [e.model_dump(mode="json") for e in sliced],
        "total": total,
    }


@router.get("/activity/{op_id}", response_model=ActivityEntry)
async def get_activity(op_id: str, request: Request) -> ActivityEntry:
    vault: Path = request.app.state.vault_root
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    if entry is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "id": op_id}
        )
    return entry


@router.post("/activity/{op_id}/undo", response_model=UndoApiResult)
def undo_activity(op_id: str, request: Request) -> UndoApiResult:
    vault: Path = request.app.state.vault_root
    result = undo(vault, op_id)  # raises UndoError / LockTimeoutError → handled in app
    return UndoApiResult(
        success=result.success,
        op_id=op_id,
        restored_pages=list(result.restored_pages),
        new_entry_id=result.new_entry_id,
    )
