"""REST routes for ontology HITL suggestions.

Per-project routes resolve the target VaultRuntime via
``get_runtime(request, project)`` (404 on unknown project) and use
``runtime.vault_root`` for filesystem operations.

URL structure::

    GET    /ontology/{project}/suggestions                 — list suggestions
    POST   /ontology/{project}/suggestions                 — create suggestion
    POST   /ontology/{project}/suggestions/{id}/approve    — approve and apply
    POST   /ontology/{project}/suggestions/{id}/reject     — reject
    POST   /ontology/{project}/suggestions/{id}/defer      — defer
    PATCH  /ontology/{project}/suggestions/{id}            — update mutable fields
    POST   /ontology/{project}/scan                        — run scanner, create
                                                            pending suggestions
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.config import Config
from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.ontology_apply import (
    OntologyError,
    apply_suggestion,
)
from claude_mnemos.core.ontology_scan import scan_ontology
from claude_mnemos.daemon.routes._helpers import get_runtime
from claude_mnemos.ingest.llm import MissingApiKeyError, make_llm_client
from claude_mnemos.state.ontology import (
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
    generate_suggestion_id,
)

router = APIRouter()


class CreateSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["merge_entities", "rename_entity", "delete_page"]
    affected_pages: list[str] = Field(min_length=1)
    proposed_target: str | None = None
    reason: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class PatchSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    body: str | None = None


def _suggestion_to_dict(s: Suggestion) -> dict[str, Any]:
    fm = s.frontmatter.model_dump(mode="json")
    return {"frontmatter": fm, "body": s.body}


# ---------------------------------------------------------------------------
# GET /ontology/{project}/suggestions
# ---------------------------------------------------------------------------


@router.get("/ontology/{project}/suggestions")
def list_suggestions_endpoint(
    project: str,
    request: Request,
    status: str = Query(default="pending"),
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    store = SuggestionStore(vault)
    include_archive = status in ("all", "approved", "rejected")
    items = store.list(include_archive=include_archive)
    if status not in ("all", ""):
        items = [s for s in items if s.frontmatter.status == status]
    return {
        "suggestions": [_suggestion_to_dict(s) for s in items],
        "total": len(items),
    }


# ---------------------------------------------------------------------------
# POST /ontology/{project}/suggestions  (create)
# ---------------------------------------------------------------------------


@router.post("/ontology/{project}/suggestions", status_code=201)
def create_suggestion_endpoint(
    project: str,
    body: CreateSuggestionRequest,
    request: Request,
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    store = SuggestionStore(vault)

    def _bad(error: str, detail: str) -> HTTPException:
        return HTTPException(status_code=422, detail={"error": error, "detail": detail})

    if body.operation == "merge_entities":
        if body.proposed_target is None:
            raise _bad("missing_target", "merge_entities requires proposed_target")
        if len(body.affected_pages) < 2:
            raise _bad(
                "insufficient_sources", "merge_entities requires at least 2 sources"
            )
    elif body.operation == "rename_entity":
        if body.proposed_target is None:
            raise _bad("missing_target", "rename_entity requires proposed_target")
        if len(body.affected_pages) != 1:
            raise _bad(
                "wrong_source_count", "rename_entity requires exactly 1 source"
            )
    elif body.operation == "delete_page":
        if len(body.affected_pages) != 1:
            raise _bad(
                "wrong_source_count", "delete_page requires exactly 1 source"
            )

    now = datetime.now(UTC)
    sid = generate_suggestion_id(now)
    suggestion = Suggestion(
        frontmatter=SuggestionFrontmatter(
            id=sid,
            created=now,
            operation=body.operation,
            affected_pages=body.affected_pages,
            proposed_target=body.proposed_target,
            reason=body.reason,
            confidence=body.confidence,
        ),
        body=body.reason,
    )
    store.create(suggestion)
    return _suggestion_to_dict(suggestion)


# ---------------------------------------------------------------------------
# POST /ontology/{project}/suggestions/{id}/approve
# ---------------------------------------------------------------------------


@router.post("/ontology/{project}/suggestions/{suggestion_id}/approve")
def approve_suggestion_endpoint(
    project: str,
    suggestion_id: str,
    request: Request,
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    result = apply_suggestion(vault, suggestion_id)
    return {
        "success": result.success,
        "operation": result.operation,
        "suggestion_id": result.suggestion_id,
        "activity_id": result.activity_id,
        "target_path": result.target_path,
        "affected_pages": list(result.affected_pages),
        "wikilinks_rewritten": result.wikilinks_rewritten,
    }


# ---------------------------------------------------------------------------
# POST /ontology/{project}/suggestions/{id}/reject
# ---------------------------------------------------------------------------


@router.post("/ontology/{project}/suggestions/{suggestion_id}/reject")
def reject_suggestion_endpoint(
    project: str,
    suggestion_id: str,
    request: Request,
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    store = SuggestionStore(vault)
    existing = store.get(suggestion_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "id": suggestion_id}
        )
    if existing.frontmatter.status != "pending":
        raise OntologyError(
            f"suggestion already {existing.frontmatter.status}: {suggestion_id}"
        )
    store.update_status(suggestion_id, "rejected")
    store.archive_suggestion(suggestion_id)
    return {"success": True, "suggestion_id": suggestion_id, "status": "rejected"}


# ---------------------------------------------------------------------------
# POST /ontology/{project}/suggestions/{id}/defer
# ---------------------------------------------------------------------------


@router.post("/ontology/{project}/suggestions/{suggestion_id}/defer")
def defer_suggestion_endpoint(
    project: str,
    suggestion_id: str,
    request: Request,
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    store = SuggestionStore(vault)
    existing = store.get(suggestion_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "id": suggestion_id}
        )
    if existing.frontmatter.status != "pending":
        raise OntologyError(
            f"suggestion already {existing.frontmatter.status}: {suggestion_id}"
        )
    store.update_status(suggestion_id, "deferred")
    return {"success": True, "suggestion_id": suggestion_id, "status": "deferred"}


# ---------------------------------------------------------------------------
# PATCH /ontology/{project}/suggestions/{id}
# ---------------------------------------------------------------------------


@router.patch("/ontology/{project}/suggestions/{suggestion_id}")
def patch_suggestion_endpoint(
    project: str,
    suggestion_id: str,
    patch: PatchSuggestionRequest,
    request: Request,
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    store = SuggestionStore(vault)
    existing = store.get(suggestion_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "id": suggestion_id}
        )
    updates: dict[str, object] = {}
    if patch.reason is not None:
        updates["reason"] = patch.reason
    if patch.confidence is not None:
        updates["confidence"] = patch.confidence
    new_fm = existing.frontmatter.model_copy(update=updates)
    new_body = patch.body if patch.body is not None else existing.body
    new_suggestion = Suggestion(frontmatter=new_fm, body=new_body)
    target = store._file_for(suggestion_id)  # noqa: SLF001
    if not target.is_file():
        target = store._archive_file_for(suggestion_id)  # noqa: SLF001
    atomic_write(target, new_suggestion.serialize())
    return _suggestion_to_dict(new_suggestion)


# ---------------------------------------------------------------------------
# POST /ontology/{project}/scan
# ---------------------------------------------------------------------------


@router.post("/ontology/{project}/scan")
async def scan_endpoint(project: str, request: Request) -> dict[str, Any]:
    """Run the ontology scanner and return counts.

    Synchronous from the client's perspective: the request blocks until the
    scan completes. Internally we offload to a worker thread so the event
    loop stays responsive for parallel calls (status, list, etc).

    Returns 503 if no LLM provider is configured (no API key and no
    ``claude`` binary on PATH).
    """
    runtime = get_runtime(request, project)
    cfg = Config.from_env()
    try:
        llm = make_llm_client(cfg)
    except MissingApiKeyError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "llm_unavailable",
                "hint": (
                    "Set ANTHROPIC_API_KEY or install Claude Code CLI "
                    "to enable ontology scanning."
                ),
            },
        ) from exc

    result = await asyncio.to_thread(scan_ontology, runtime.vault_root, llm=llm)
    return {
        "created": result.created,
        "skipped_existing": result.skipped_existing,
        "skipped_distinct": result.skipped_distinct,
        "skipped_capped": result.skipped_capped,
        "errors": [{"pair": p, "error": e} for p, e in result.errors],
        "scanned_pages": result.scanned_pages,
    }
