from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.staging import StagingTransaction
from claude_mnemos.core.wikilinks import find_files_referencing, rewrite_wikilinks
from claude_mnemos.state.activity import ActivityEntry, ActivityLog
from claude_mnemos.state.ontology import (
    Suggestion,
    SuggestionStore,
)

logger = logging.getLogger(__name__)


class OntologyError(RuntimeError):
    """Raised when an ontology suggestion cannot be applied."""


@dataclass(frozen=True)
class ApplyResult:
    success: bool
    operation: str
    suggestion_id: str
    activity_id: str
    target_path: str | None
    affected_pages: list[str] = field(default_factory=list)
    wikilinks_rewritten: int = 0


def _slug_from_relpath(relpath: str) -> str:
    return Path(relpath).stem


def _read_page(vault: Path, relpath: str) -> str:
    path = vault / relpath
    if not path.is_file():
        raise OntologyError(f"page missing: {relpath}")
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    end_marker = "\n---\n"
    end = text.find(end_marker, 4)
    if end < 0:
        return {}, text
    yaml_block = text[4:end]
    body = text[end + len(end_marker) :]
    try:
        data = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return data, body


def _serialize_page(frontmatter: dict[str, object], body: str) -> str:
    yaml_text = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    body_clean = body.lstrip("\n")
    return f"---\n{yaml_text}---\n\n{body_clean}".rstrip() + "\n"


def _merge_frontmatter(
    sources: list[dict[str, object]],
    target_title: str,
    today: datetime,
) -> dict[str, object]:
    """Combine frontmatters of merged source pages into a single target frontmatter.

    Heuristics (intentionally simple — Plan #11+ refines):
    - title: derived from target slug (caller passes)
    - type: from first source (assumed homogeneous; cross-type merge rejected upstream)
    - flavor: union, preserve order
    - sources/related/aliases/tags: union, preserve order, dedup
    - confidence: min (conservative)
    - created: min (oldest)
    - updated: today
    - drop instance fields like update_count
    """
    if not sources:
        return {"title": target_title}
    first = sources[0]
    out: dict[str, object] = {"title": target_title}
    if "type" in first:
        out["type"] = first["type"]

    list_fields = ("flavor", "sources", "related", "aliases", "tags")
    for fld in list_fields:
        merged: list[object] = []
        seen: set[object] = set()
        for fm in sources:
            value = fm.get(fld)
            if not isinstance(value, list):
                continue
            for item in value:
                key = item if not isinstance(item, dict) else repr(item)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        if merged:
            out[fld] = merged

    confidences: list[float] = []
    for fm in sources:
        value = fm.get("confidence")
        if isinstance(value, int | float):
            confidences.append(float(value))
    if confidences:
        out["confidence"] = min(confidences)

    created_dates = [fm.get("created") for fm in sources if fm.get("created") is not None]
    if created_dates:
        out["created"] = min(created_dates)  # type: ignore[type-var]
    out["updated"] = today.date().isoformat()
    return out


def _build_target_body(sources: list[tuple[str, str]]) -> str:
    """Concatenate source bodies with `## From <slug>` separators."""
    parts: list[str] = []
    for slug, body in sources:
        parts.append(f"## From [[{slug}]]\n\n{body.strip()}\n")
    return "\n".join(parts)


def _rewrite_wikilinks_in_vault(
    vault: Path,
    txn: StagingTransaction,
    mapping: dict[str, str],
    *,
    exclude: set[Path],
) -> int:
    """Rewrite wikilinks in every file referencing keys of `mapping`.

    Stages updated content via `txn.write` (relative paths). Returns count of
    files actually updated.
    """
    if not mapping:
        return 0
    rewritten = 0
    affected: set[Path] = set()
    for old_slug in mapping:
        affected.update(find_files_referencing(vault, old_slug, exclude=exclude))
    for path in affected:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("cannot read %s during wikilinks rewrite: %s", path, exc)
            continue
        new_text = rewrite_wikilinks(text, mapping)
        if new_text == text:
            continue
        rel = path.relative_to(vault)
        txn.write(rel, new_text)
        rewritten += 1
    return rewritten


def _append_activity_via_staging(
    vault: Path,
    txn: StagingTransaction,
    *,
    activity_id: str,
    operation: str,
    suggestion_id: str,
    affected_pages: list[str],
    wikilinks_rewritten: int,
    target_path: str | None,
    snapshot_relpath: str,
) -> None:
    log = ActivityLog.load(vault)
    metadata: dict[str, object] = {
        "suggestion_id": suggestion_id,
        "operation": operation,
        "wikilinks_rewritten": wikilinks_rewritten,
    }
    if target_path is not None:
        metadata["target"] = target_path
    log.append(
        ActivityEntry(
            id=activity_id,
            timestamp=datetime.now(UTC),
            operation_type="ontology_apply",
            status="success",
            snapshot_path=snapshot_relpath,
            can_undo=True,
            affected_pages=affected_pages,
            metadata=metadata,
        )
    )
    txn.write(Path(".activity.json"), log.serialize_to_string())


def apply_merge_entities(
    vault: Path,
    suggestion: Suggestion,
    *,
    today: datetime | None = None,
    lock_timeout: float = 60.0,
) -> ApplyResult:
    today = today or datetime.now(UTC)
    fm = suggestion.frontmatter
    if fm.proposed_target is None:
        raise OntologyError("merge_entities requires proposed_target")
    if len(fm.affected_pages) < 2:
        raise OntologyError("merge_entities requires at least 2 source pages")

    sources = list(fm.affected_pages)
    target_relpath = fm.proposed_target

    for src in sources:
        if not (vault / src).is_file():
            raise OntologyError(f"source page missing: {src}")
    if (vault / target_relpath).exists():
        raise OntologyError(f"target page already exists: {target_relpath}")

    activity_id = uuid4().hex

    with pipeline_lock(vault, timeout=lock_timeout), StagingTransaction(
        vault, operation_id=activity_id, operation_type="ontology"
    ) as txn:
        snapshot_path = txn.pre_promote_snapshot_path()
        snapshot_relpath = (
            f".backups/{snapshot_path.name}"
            if snapshot_path.parent.name == ".backups"
            else snapshot_path.relative_to(vault).as_posix()
        )

        source_pages: list[tuple[str, str]] = []
        source_frontmatters: list[dict[str, object]] = []
        for src_rel in sources:
            text = _read_page(vault, src_rel)
            src_fm, src_body = _split_frontmatter(text)
            source_pages.append((_slug_from_relpath(src_rel), src_body))
            source_frontmatters.append(src_fm)

        target_title = Path(target_relpath).stem.replace("-", " ").replace("_", " ").title()
        target_fm = _merge_frontmatter(source_frontmatters, target_title, today)
        target_body = _build_target_body(source_pages)
        txn.write(Path(target_relpath), _serialize_page(target_fm, target_body))

        for src_rel in sources:
            txn.delete(src_rel)

        target_slug = _slug_from_relpath(target_relpath)
        mapping = {_slug_from_relpath(src): target_slug for src in sources}
        exclude = {vault / src for src in sources} | {vault / target_relpath}
        rewritten = _rewrite_wikilinks_in_vault(vault, txn, mapping, exclude=exclude)

        _append_activity_via_staging(
            vault,
            txn,
            activity_id=activity_id,
            operation="merge_entities",
            suggestion_id=fm.id,
            affected_pages=[*sources, target_relpath],
            wikilinks_rewritten=rewritten,
            target_path=target_relpath,
            snapshot_relpath=snapshot_relpath,
        )

        txn.promote_to_vault()

    return ApplyResult(
        success=True,
        operation="merge_entities",
        suggestion_id=fm.id,
        activity_id=activity_id,
        target_path=target_relpath,
        affected_pages=[*sources, target_relpath],
        wikilinks_rewritten=rewritten,
    )


def apply_rename_entity(
    vault: Path,
    suggestion: Suggestion,
    *,
    today: datetime | None = None,
    lock_timeout: float = 60.0,
) -> ApplyResult:
    today = today or datetime.now(UTC)
    fm = suggestion.frontmatter
    if fm.proposed_target is None:
        raise OntologyError("rename_entity requires proposed_target")
    if len(fm.affected_pages) != 1:
        raise OntologyError("rename_entity requires exactly 1 source page")

    src_rel = fm.affected_pages[0]
    target_relpath = fm.proposed_target

    if not (vault / src_rel).is_file():
        raise OntologyError(f"source page missing: {src_rel}")
    if (vault / target_relpath).exists():
        raise OntologyError(f"target page already exists: {target_relpath}")

    activity_id = uuid4().hex

    with pipeline_lock(vault, timeout=lock_timeout), StagingTransaction(
        vault, operation_id=activity_id, operation_type="ontology"
    ) as txn:
        snapshot_path = txn.pre_promote_snapshot_path()
        snapshot_relpath = f".backups/{snapshot_path.name}"

        txn.move(src_rel, target_relpath)

        old_slug = _slug_from_relpath(src_rel)
        new_slug = _slug_from_relpath(target_relpath)
        mapping = {old_slug: new_slug}
        exclude = {vault / src_rel, vault / target_relpath}
        rewritten = _rewrite_wikilinks_in_vault(vault, txn, mapping, exclude=exclude)

        _append_activity_via_staging(
            vault,
            txn,
            activity_id=activity_id,
            operation="rename_entity",
            suggestion_id=fm.id,
            affected_pages=[src_rel, target_relpath],
            wikilinks_rewritten=rewritten,
            target_path=target_relpath,
            snapshot_relpath=snapshot_relpath,
        )

        txn.promote_to_vault()

    return ApplyResult(
        success=True,
        operation="rename_entity",
        suggestion_id=fm.id,
        activity_id=activity_id,
        target_path=target_relpath,
        affected_pages=[src_rel, target_relpath],
        wikilinks_rewritten=rewritten,
    )


def apply_delete_page(
    vault: Path,
    suggestion: Suggestion,
    *,
    today: datetime | None = None,
    lock_timeout: float = 60.0,
) -> ApplyResult:
    today = today or datetime.now(UTC)
    fm = suggestion.frontmatter
    if len(fm.affected_pages) != 1:
        raise OntologyError("delete_page requires exactly 1 affected page")

    src_rel = fm.affected_pages[0]
    if not (vault / src_rel).is_file():
        raise OntologyError(f"source page missing: {src_rel}")

    activity_id = uuid4().hex

    with pipeline_lock(vault, timeout=lock_timeout), StagingTransaction(
        vault, operation_id=activity_id, operation_type="ontology"
    ) as txn:
        snapshot_path = txn.pre_promote_snapshot_path()
        snapshot_relpath = f".backups/{snapshot_path.name}"

        txn.delete(src_rel)

        _append_activity_via_staging(
            vault,
            txn,
            activity_id=activity_id,
            operation="delete_page",
            suggestion_id=fm.id,
            affected_pages=[src_rel],
            wikilinks_rewritten=0,
            target_path=None,
            snapshot_relpath=snapshot_relpath,
        )

        txn.promote_to_vault()

    return ApplyResult(
        success=True,
        operation="delete_page",
        suggestion_id=fm.id,
        activity_id=activity_id,
        target_path=None,
        affected_pages=[src_rel],
        wikilinks_rewritten=0,
    )


_APPLY_DISPATCH = {
    "merge_entities": apply_merge_entities,
    "rename_entity": apply_rename_entity,
    "delete_page": apply_delete_page,
}


def apply_suggestion(
    vault: Path,
    suggestion_id: str,
    *,
    today: datetime | None = None,
    lock_timeout: float = 60.0,
) -> ApplyResult:
    """Load a suggestion, dispatch by operation, archive on success."""
    store = SuggestionStore(vault)
    suggestion = store.get(suggestion_id)
    if suggestion is None:
        raise OntologyError(f"suggestion not found: {suggestion_id}")
    if suggestion.frontmatter.status != "pending":
        raise OntologyError(
            f"suggestion already {suggestion.frontmatter.status}: {suggestion_id}"
        )

    operation = suggestion.frontmatter.operation
    apply_fn = _APPLY_DISPATCH.get(operation)
    if apply_fn is None:
        raise OntologyError(f"unsupported operation: {operation}")

    result = apply_fn(vault, suggestion, today=today, lock_timeout=lock_timeout)

    store.update_status(
        suggestion_id,
        "approved",
        applied_at=datetime.now(UTC),
        applied_op_id=result.activity_id,
    )
    store.archive_suggestion(suggestion_id)
    return result
