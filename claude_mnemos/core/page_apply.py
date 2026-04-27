"""Page mutation operations: edit, soft-delete, restore-from-trash, dismiss, empty."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from claude_mnemos.config import Config
from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.models import WikiPageFrontmatter
from claude_mnemos.core.page_io import ParsedPage, read_page, serialize_page
from claude_mnemos.core.staging import StagingTransaction
from claude_mnemos.core.trash import (
    TRASH_DIRNAME,
    TrashEntryNotFoundError,
    list_trash,
    read_metadata,
)
from claude_mnemos.state.activity import (
    ACTIVITY_FILENAME,
    ActivityEntry,
    ActivityLog,
)

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker


class PageRestoreCollisionError(RuntimeError):
    """Raised when restore_from_trash would overwrite an existing file."""


@dataclass(frozen=True)
class PatchResult:
    success: bool
    snapshot_path: Path | None = None
    activity_id: str | None = None


@dataclass(frozen=True)
class DeleteResult:
    success: bool
    snapshot_path: Path | None = None
    activity_id: str | None = None
    trash_id: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    snapshot_path: Path | None = None
    activity_id: str | None = None
    restored_path: str | None = None


@dataclass(frozen=True)
class EmptyTrashResult:
    removed_count: int = 0
    removed_ids: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    activity_id: str | None = None


# `created` is locked because changing creation date doesn't make sense for an edit;
# `type` is locked because changing it would imply moving the file to a different
# wiki/<type>/ subdirectory, which is out of scope for apply_patch (use ontology
# pipeline for re-categorization).
_FORBIDDEN_FRONTMATTER_KEYS = frozenset({"created", "type"})


def apply_patch(
    vault: Path,
    page_path: Path,
    *,
    frontmatter_patch: Mapping[str, Any] | None = None,
    body: str | None = None,
    tracker: OurWritesTracker | None = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> PatchResult:
    """Apply a frontmatter and/or body patch to an existing page.

    Empty patch (no frontmatter and no body) is a no-op — returns success without
    a snapshot/activity entry.

    Side-effects of any non-empty patch:
    - `agent_written` set to False
    - `last_human_edit` set to now (UTC)
    - `updated` set to today

    Caller may override these by including them explicitly in `frontmatter_patch`.
    """
    cfg = cfg or Config.from_env()
    today = today or date.today()
    rel = page_path.relative_to(vault).as_posix()

    if not frontmatter_patch and body is None:
        return PatchResult(success=True, snapshot_path=None, activity_id=None)

    parsed = read_page(page_path)
    new_fm = parsed.frontmatter
    fields_changed: list[str] = []

    if frontmatter_patch:
        forbidden = set(frontmatter_patch.keys()) & _FORBIDDEN_FRONTMATTER_KEYS
        if forbidden:
            raise ValueError(f"forbidden frontmatter keys: {forbidden}")
        update = dict(frontmatter_patch)
        # Auto side-effects: caller-provided values take precedence (setdefault).
        update.setdefault("agent_written", False)
        update.setdefault("last_human_edit", datetime.now(UTC))
        update.setdefault("updated", today)
        # Merge into a dict and re-validate via model_validate — model_copy(update=)
        # bypasses validation, so invalid status/confidence/etc. would slip through.
        merged = parsed.frontmatter.model_dump(mode="python")
        merged.update(update)
        new_fm = WikiPageFrontmatter.model_validate(merged)
        fields_changed = sorted(set(frontmatter_patch.keys()))

    new_body = body if body is not None else parsed.body
    if body is not None:
        fields_changed.append("body")

    new_parsed = ParsedPage(frontmatter=new_fm, extra_fm=parsed.extra_fm, body=new_body)
    op_id = uuid4().hex

    with (
        pipeline_lock(vault, timeout=cfg.lock_timeout),
        StagingTransaction(vault, op_id, operation_type="manual_edit") as txn,
    ):
        txn.write(Path(rel), serialize_page(new_parsed))
        snap = txn.pre_promote_snapshot_path()
        log = ActivityLog.load(vault)
        log.append(
            ActivityEntry(
                id=op_id,
                timestamp=datetime.now(UTC),
                operation_type="manual_edit",
                status="success",
                snapshot_path=snap.relative_to(vault).as_posix(),
                can_undo=True,
                affected_pages=[rel],
                metadata={"page_path": rel, "fields_changed": fields_changed},
            )
        )
        txn.write(Path(ACTIVITY_FILENAME), log.serialize_to_string())
        promote = txn.promote_to_vault(tracker=tracker)

    return PatchResult(success=True, snapshot_path=promote.snapshot, activity_id=op_id)


def apply_soft_delete(
    vault: Path,
    page_path: Path,
    *,
    tracker: OurWritesTracker | None = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> DeleteResult:
    """Soft-delete a page to .trash/ via StagingTransaction.

    Snapshot+activity make this undoable via mnemos undo <activity_id>.
    After undo, the originating .trash/<id>/ dir REMAINS as an orphan with
    stale metadata pointing at the now-restored page. List/dismiss/empty
    commands handle these orphans normally; trying to restore one will 409
    because the original_path is now occupied.

    Caller-pinned trash_id ensures the returned DeleteResult.trash_id is
    authoritative (matches the on-disk dir).
    """
    cfg = cfg or Config.from_env()
    rel = page_path.relative_to(vault).as_posix()
    op_id = uuid4().hex
    slug = Path(rel).stem or "page"
    ts = datetime.now(UTC).strftime("%Y-%m-%d-%H-%M-%S")
    trash_id = f"deleted-{slug}-{ts}-{op_id[:8]}"

    with (
        pipeline_lock(vault, timeout=cfg.lock_timeout),
        StagingTransaction(vault, op_id, operation_type="manual_delete") as txn,
    ):
        txn.delete(rel, to_trash=True, trash_id=trash_id)
        snap = txn.pre_promote_snapshot_path()
        log = ActivityLog.load(vault)
        log.append(
            ActivityEntry(
                id=op_id,
                timestamp=datetime.now(UTC),
                operation_type="manual_delete",
                status="success",
                snapshot_path=snap.relative_to(vault).as_posix(),
                can_undo=True,
                affected_pages=[rel],
                metadata={"page_path": rel, "trash_id": trash_id},
            )
        )
        txn.write(Path(ACTIVITY_FILENAME), log.serialize_to_string())
        promote = txn.promote_to_vault(tracker=tracker)

    return DeleteResult(
        success=True,
        snapshot_path=promote.snapshot,
        activity_id=op_id,
        trash_id=trash_id,
    )


def apply_restore_from_trash(
    vault: Path,
    trash_id: str,
    *,
    tracker: OurWritesTracker | None = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> RestoreResult:
    """Restore a trashed page back to its original path via StagingTransaction.

    Raises:
        TrashEntryNotFoundError: trash_id doesn't resolve to a directory.
        PageRestoreCollisionError: original path is already occupied, or trash
            entry is missing metadata / page file.
    """
    cfg = cfg or Config.from_env()
    trash_dir = vault / TRASH_DIRNAME / trash_id
    if not trash_dir.is_dir():
        raise TrashEntryNotFoundError(trash_id)
    meta = read_metadata(trash_dir)
    if meta is None:
        raise PageRestoreCollisionError(f"no metadata for trash entry {trash_id}")

    target = vault / meta.original_path
    if target.exists():
        raise PageRestoreCollisionError(
            f"original path {meta.original_path} already exists"
        )

    page_basename: str | None = None
    for f in trash_dir.iterdir():
        if f.is_file() and not f.name.startswith(".") and f.suffix == ".md":
            page_basename = f.name
            break
    if page_basename is None:
        raise PageRestoreCollisionError(f"trash entry {trash_id} has no page file")

    op_id = uuid4().hex
    src_rel = (Path(TRASH_DIRNAME) / trash_id / page_basename).as_posix()
    dst_rel = meta.original_path

    # Note: pipeline_lock and StagingTransaction can't be combined in one `with`
    # here because cleanup of the orphaned trash dir must run AFTER the txn
    # exits but BEFORE the lock releases.
    with pipeline_lock(vault, timeout=cfg.lock_timeout):  # noqa: SIM117
        with StagingTransaction(
            vault, op_id, operation_type="manual_restore_trash"
        ) as txn:
            txn.move(src_rel, dst_rel)
            snap = txn.pre_promote_snapshot_path()
            log = ActivityLog.load(vault)
            log.append(
                ActivityEntry(
                    id=op_id,
                    timestamp=datetime.now(UTC),
                    operation_type="manual_restore_trash",
                    status="success",
                    snapshot_path=snap.relative_to(vault).as_posix(),
                    can_undo=True,
                    affected_pages=[dst_rel],
                    metadata={"trash_id": trash_id, "restored_path": dst_rel},
                )
            )
            txn.write(Path(ACTIVITY_FILENAME), log.serialize_to_string())
            promote = txn.promote_to_vault(tracker=tracker)

        # Clean up empty trash dir (orchestration outside transaction; the .md
        # file is gone via the queued move, but .reason.txt + .metadata.json
        # remain behind in the now-orphaned trash dir).
        shutil.rmtree(trash_dir, ignore_errors=True)

    return RestoreResult(
        success=True,
        snapshot_path=promote.snapshot,
        activity_id=op_id,
        restored_path=dst_rel,
    )


def dismiss_trash_entry(
    vault: Path,
    trash_id: str,
    *,
    today: date | None = None,
    cfg: Config | None = None,
) -> None:
    """Permanently remove a single trash entry (non-undoable).

    Raises TrashEntryNotFoundError if the trash_id doesn't exist.
    """
    cfg = cfg or Config.from_env()
    trash_dir = vault / TRASH_DIRNAME / trash_id
    if not trash_dir.is_dir():
        raise TrashEntryNotFoundError(trash_id)
    op_id = uuid4().hex
    had_metadata = (trash_dir / ".metadata.json").is_file()

    with pipeline_lock(vault, timeout=cfg.lock_timeout):
        shutil.rmtree(trash_dir, ignore_errors=False)
        log = ActivityLog.load(vault)
        log.append(
            ActivityEntry(
                id=op_id,
                timestamp=datetime.now(UTC),
                operation_type="trash_dismissed",
                status="success",
                snapshot_path=None,
                can_undo=False,
                affected_pages=[],
                metadata={"trash_id": trash_id, "had_metadata": had_metadata},
            )
        )
        log.save(vault)


def empty_trash(
    vault: Path,
    *,
    today: date | None = None,
    cfg: Config | None = None,
) -> EmptyTrashResult:
    """Permanently remove all trash entries (non-undoable). Best-effort: per-entry
    failures are recorded in `errors` and don't abort the run."""
    cfg = cfg or Config.from_env()
    op_id = uuid4().hex
    entries = list_trash(vault)
    removed: list[str] = []
    errors: list[tuple[str, str]] = []

    with pipeline_lock(vault, timeout=cfg.lock_timeout):
        for entry in entries:
            d = vault / TRASH_DIRNAME / entry.trash_id
            try:
                shutil.rmtree(d, ignore_errors=False)
                removed.append(entry.trash_id)
            except OSError as exc:
                errors.append((entry.trash_id, str(exc)))

        log = ActivityLog.load(vault)
        log.append(
            ActivityEntry(
                id=op_id,
                timestamp=datetime.now(UTC),
                operation_type="trash_emptied",
                status="success",
                snapshot_path=None,
                can_undo=False,
                affected_pages=[],
                metadata={
                    "removed_count": len(removed),
                    "removed_ids": removed,
                    "errors": errors,
                },
            )
        )
        log.save(vault)

    return EmptyTrashResult(
        removed_count=len(removed),
        removed_ids=removed,
        errors=errors,
        activity_id=op_id,
    )
