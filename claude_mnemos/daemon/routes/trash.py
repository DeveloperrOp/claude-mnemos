"""REST routes for trash list/get/restore/dismiss/empty.

Read paths (`GET /trash`, `GET /trash/{id}`) use `core.trash.list_trash`
directly. Write paths route through `core.page_apply` operations under
`pipeline_lock`. `TrashEntryNotFoundError` and `PageRestoreCollisionError`
become 404 / 409 via app-level handlers (Task 8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from claude_mnemos.core.page_apply import (
    EmptyTrashResult,
    RestoreResult,
    apply_restore_from_trash,
    dismiss_trash_entry,
    empty_trash,
)
from claude_mnemos.core.trash import (
    TRASH_DIRNAME,
    TrashEntry,
    list_trash,
)

router = APIRouter()


def _tracker(request: Request) -> Any:
    daemon = request.app.state.daemon
    return getattr(daemon, "tracker", None) if daemon is not None else None


def _entry_to_dict(entry: TrashEntry) -> dict[str, Any]:
    return entry.model_dump(mode="json")


def _restore_result_to_dict(result: RestoreResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
        "activity_id": result.activity_id,
        "restored_path": result.restored_path,
    }


def _empty_result_to_dict(result: EmptyTrashResult) -> dict[str, Any]:
    return {
        "removed_count": result.removed_count,
        "removed_ids": list(result.removed_ids),
        "errors": [list(err) for err in result.errors],
        "activity_id": result.activity_id,
    }


@router.get("/trash")
async def list_trash_endpoint(request: Request) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    entries = list_trash(vault)
    return {
        "entries": [_entry_to_dict(e) for e in entries],
        "total": len(entries),
    }


@router.get("/trash/{trash_id}")
async def get_trash_entry_endpoint(trash_id: str, request: Request) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    trash_dir = vault / TRASH_DIRNAME / trash_id
    if not trash_dir.is_dir():
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "trash_id": trash_id}
        )
    for entry in list_trash(vault):
        if entry.trash_id == trash_id:
            return _entry_to_dict(entry)
    # Defensive: dir exists but list_trash skipped it (e.g. unreadable).
    raise HTTPException(
        status_code=404, detail={"error": "not_found", "trash_id": trash_id}
    )


@router.post("/trash/{trash_id}/restore")
async def restore_trash_endpoint(trash_id: str, request: Request) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    result = apply_restore_from_trash(
        vault, trash_id, tracker=_tracker(request)
    )
    return _restore_result_to_dict(result)


@router.delete("/trash/{trash_id}", status_code=204)
async def dismiss_trash_endpoint(trash_id: str, request: Request) -> Response:
    vault: Path = request.app.state.vault_root
    dismiss_trash_entry(vault, trash_id)
    return Response(status_code=204)


@router.delete("/trash")
async def empty_trash_endpoint(request: Request) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    result = empty_trash(vault)
    return _empty_result_to_dict(result)
