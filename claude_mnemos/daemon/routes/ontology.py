from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.core.ontology_apply import (
    OntologyError,
    apply_suggestion,
)
from claude_mnemos.state.ontology import (
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
    generate_suggestion_id,
)

router = APIRouter()


def _vault(request: Request) -> Path:
    vault = request.app.state.vault_root
    if vault is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_vault_registered",
                "hint": "Register: mnemos project add NAME --vault PATH",
            },
        )
    assert isinstance(vault, Path)
    return vault


class CreateSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["merge_entities", "rename_entity", "delete_page"]
    affected_pages: list[str] = Field(min_length=1)
    proposed_target: str | None = None
    reason: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


def _suggestion_to_dict(s: Suggestion) -> dict[str, Any]:
    fm = s.frontmatter.model_dump(mode="json")
    return {"frontmatter": fm, "body": s.body}


@router.get("/suggestions")
def list_suggestions_endpoint(
    request: Request,
    status: str = Query(default="pending"),
) -> dict[str, Any]:
    vault = _vault(request)
    store = SuggestionStore(vault)
    include_archive = status in ("all", "approved", "rejected")
    items = store.list(include_archive=include_archive)
    if status not in ("all", ""):
        items = [s for s in items if s.frontmatter.status == status]
    return {
        "suggestions": [_suggestion_to_dict(s) for s in items],
        "total": len(items),
    }


@router.get("/suggestions/{suggestion_id}")
def get_suggestion_endpoint(
    suggestion_id: str, request: Request
) -> dict[str, Any]:
    vault = _vault(request)
    store = SuggestionStore(vault)
    s = store.get(suggestion_id)
    if s is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "id": suggestion_id}
        )
    return _suggestion_to_dict(s)


@router.post("/suggestions", status_code=201)
def create_suggestion_endpoint(
    body: CreateSuggestionRequest, request: Request
) -> dict[str, Any]:
    vault = _vault(request)
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


@router.post("/suggestions/{suggestion_id}/approve")
def approve_suggestion_endpoint(
    suggestion_id: str, request: Request
) -> dict[str, Any]:
    vault = _vault(request)
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


@router.post("/suggestions/{suggestion_id}/reject")
def reject_suggestion_endpoint(
    suggestion_id: str, request: Request
) -> dict[str, Any]:
    vault = _vault(request)
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


@router.post("/suggestions/{suggestion_id}/defer")
def defer_suggestion_endpoint(
    suggestion_id: str, request: Request
) -> dict[str, Any]:
    vault = _vault(request)
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
