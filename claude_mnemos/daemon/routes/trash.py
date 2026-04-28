"""REST routes for trash list / restore / dismiss / empty.

Per-project routes resolve the target VaultRuntime via
``get_runtime(request, project)`` (404 on unknown project) and use
``runtime.vault_root`` for filesystem operations and ``runtime.tracker``
for our-writes registration.

URL structure::

    GET    /trash/{project}               — list trash entries
    POST   /trash/{project}/{id}/restore  — restore a trash entry
    DELETE /trash/{project}/{id}          — permanently delete (dismiss) entry
    DELETE /trash/{project}               — empty trash (Tier 2)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from claude_mnemos.core.page_apply import (
    EmptyTrashResult,
    RestoreResult,
    apply_restore_from_trash,
    dismiss_trash_entry,
    empty_trash,
)
from claude_mnemos.core.trash import (
    TrashEntry,
    list_trash,
)
from claude_mnemos.daemon.routes._helpers import get_runtime

router = APIRouter()


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


@router.get("/trash/{project}")
async def list_trash_endpoint(project: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    entries = list_trash(vault)
    return {
        "entries": [_entry_to_dict(e) for e in entries],
        "total": len(entries),
    }


@router.post("/trash/{project}/{trash_id}/restore")
async def restore_trash_endpoint(
    project: str, trash_id: str, request: Request
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    result = apply_restore_from_trash(
        vault, trash_id, tracker=runtime.tracker
    )
    return _restore_result_to_dict(result)


@router.delete("/trash/{project}/{trash_id}", status_code=204)
async def dismiss_trash_endpoint(
    project: str, trash_id: str, request: Request
) -> Response:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    dismiss_trash_entry(vault, trash_id)
    return Response(status_code=204)


@router.delete("/trash/{project}")
async def empty_trash_endpoint(
    project: str, request: Request
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    result = empty_trash(vault)
    return _empty_result_to_dict(result)
