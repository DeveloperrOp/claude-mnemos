"""REST routes for page edit / verify / archive / soft-delete.

All routes resolve the URL `page_ref` via `core/pages.page_ref_to_path` (404 on
PageRefError, registered as an app-level exception handler) and then dispatch
to `core/page_apply` operations under the daemon's `pipeline_lock`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core.page_apply import (
    DeleteResult,
    PatchResult,
    apply_patch,
    apply_soft_delete,
)
from claude_mnemos.core.pages import page_ref_to_path

router = APIRouter()


def _tracker(request: Request) -> Any:
    daemon = request.app.state.daemon
    return getattr(daemon, "tracker", None) if daemon is not None else None


def _patch_result_to_dict(result: PatchResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
        "activity_id": result.activity_id,
    }


def _delete_result_to_dict(result: DeleteResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
        "activity_id": result.activity_id,
        "trash_id": result.trash_id,
    }


def _validate_patch_body(body: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Return (frontmatter_patch, body_text) or raise HTTPException(422)."""
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_body", "detail": "body must be a JSON object"},
        )
    fm_raw = body.get("frontmatter")
    if fm_raw is not None and not isinstance(fm_raw, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_frontmatter",
                "detail": "frontmatter must be an object or null",
            },
        )
    body_raw = body.get("body")
    if body_raw is not None and not isinstance(body_raw, str):
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_body_field", "detail": "body must be a string or null"},
        )
    return fm_raw, body_raw


@router.patch("/pages/{page_ref:path}")
async def patch_page(page_ref: str, request: Request) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    page_path = page_ref_to_path(vault, page_ref)
    body = await request.json()
    fm_patch, body_text = _validate_patch_body(body)
    result = apply_patch(
        vault,
        page_path,
        frontmatter_patch=fm_patch,
        body=body_text,
        tracker=_tracker(request),
    )
    return _patch_result_to_dict(result)


@router.post("/pages/{page_ref:path}/verify")
async def verify_page(page_ref: str, request: Request) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    page_path = page_ref_to_path(vault, page_ref)
    result = apply_patch(
        vault,
        page_path,
        frontmatter_patch={"status": "verified"},
        body=None,
        tracker=_tracker(request),
    )
    return _patch_result_to_dict(result)


@router.post("/pages/{page_ref:path}/archive")
async def archive_page(page_ref: str, request: Request) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    page_path = page_ref_to_path(vault, page_ref)
    result = apply_patch(
        vault,
        page_path,
        frontmatter_patch={"status": "archived"},
        body=None,
        tracker=_tracker(request),
    )
    return _patch_result_to_dict(result)


@router.delete("/pages/{page_ref:path}")
async def delete_page(page_ref: str, request: Request) -> dict[str, Any]:
    vault: Path = request.app.state.vault_root
    page_path = page_ref_to_path(vault, page_ref)
    result = apply_soft_delete(
        vault,
        page_path,
        tracker=_tracker(request),
    )
    return _delete_result_to_dict(result)
