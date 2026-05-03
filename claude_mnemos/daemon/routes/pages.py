"""REST routes for page edit / verify / archive / soft-delete / list / show / backlinks.

All per-project routes resolve the target VaultRuntime via
``get_runtime(request, project)`` (404 on unknown project) and use
``runtime.vault_root`` for filesystem operations and ``runtime.tracker``
for our-writes registration.

URL refs (`page_ref`) are resolved via ``core/pages.page_ref_to_path``
(404 on PageRefError, registered as an app-level exception handler), and
then dispatch to ``core/page_apply`` operations under the daemon's
``pipeline_lock``.
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
from claude_mnemos.core.page_io import PageParseError, read_page
from claude_mnemos.core.pages import PageRefError, page_ref_to_path
from claude_mnemos.core.wikilinks import find_files_referencing
from claude_mnemos.daemon.routes._helpers import get_runtime

router = APIRouter()


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


def _resolve_page(vault: Path, page_ref: str) -> Path:
    """Resolve page_ref to an absolute path, raising HTTP 404 on error."""
    try:
        return page_ref_to_path(vault, page_ref)
    except PageRefError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "page_not_found", "detail": str(exc)},
        ) from exc


@router.get("/pages/{project}")
async def list_pages(project: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    pages: list[str] = []
    for root_name in ("wiki", "raw"):
        root = vault / root_name
        if root.is_dir():
            for p in sorted(root.rglob("*.md")):
                if p.is_file():
                    pages.append(p.relative_to(vault).as_posix())
    return {"pages": pages}


@router.get("/pages/{project}/{page_ref:path}/backlinks")
async def get_page_backlinks(project: str, page_ref: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    page_path = _resolve_page(vault, page_ref)
    # Derive slug from stem for wikilink lookup
    slug = page_path.stem
    referrers = find_files_referencing(vault, slug, exclude={page_path})
    return {
        "backlinks": [r.relative_to(vault).as_posix() for r in referrers],
    }


@router.get("/pages/{project}/{page_ref:path}")
async def get_page(project: str, page_ref: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    page_path = _resolve_page(vault, page_ref)
    rel = page_path.relative_to(vault).as_posix()
    # Wiki pages have YAML frontmatter; raw transcripts under raw/chats/ do
    # not. Return either the parsed wiki page OR a raw dump with frontmatter:
    # null so the frontend can render either form gracefully.
    try:
        parsed = read_page(page_path)
        return {
            "path": rel,
            "frontmatter": parsed.frontmatter.model_dump(mode="json"),
            "body": parsed.body,
            "raw": False,
        }
    except PageParseError:
        body = page_path.read_text(encoding="utf-8")
        return {
            "path": rel,
            "frontmatter": None,
            "body": body,
            "raw": True,
        }


@router.patch("/pages/{project}/{page_ref:path}")
async def patch_page(project: str, page_ref: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    page_path = _resolve_page(vault, page_ref)
    body = await request.json()
    fm_patch, body_text = _validate_patch_body(body)
    result = apply_patch(
        vault,
        page_path,
        frontmatter_patch=fm_patch,
        body=body_text,
        tracker=runtime.tracker,
    )
    return _patch_result_to_dict(result)


@router.post("/pages/{project}/{page_ref:path}/verify")
async def verify_page(project: str, page_ref: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    page_path = _resolve_page(vault, page_ref)
    result = apply_patch(
        vault,
        page_path,
        frontmatter_patch={"status": "verified"},
        body=None,
        tracker=runtime.tracker,
    )
    return _patch_result_to_dict(result)


@router.post("/pages/{project}/{page_ref:path}/archive")
async def archive_page(project: str, page_ref: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    page_path = _resolve_page(vault, page_ref)
    result = apply_patch(
        vault,
        page_path,
        frontmatter_patch={"status": "archived"},
        body=None,
        tracker=runtime.tracker,
    )
    return _patch_result_to_dict(result)


@router.delete("/pages/{project}/{page_ref:path}")
async def delete_page(project: str, page_ref: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    page_path = _resolve_page(vault, page_ref)
    result = apply_soft_delete(
        vault,
        page_path,
        tracker=runtime.tracker,
    )
    return _delete_result_to_dict(result)
