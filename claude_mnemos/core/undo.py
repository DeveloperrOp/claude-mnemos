from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.snapshots import restore_from_snapshot
from claude_mnemos.state.activity import ActivityEntry, ActivityLog


class UndoError(RuntimeError):
    """Raised when undo cannot proceed (entry missing, not undoable, restore failed)."""


@dataclass(frozen=True)
class UndoResult:
    success: bool
    restored_pages: list[str]
    new_entry_id: str | None
    error: str | None = None
    recovery_hint: str | None = None


def can_undo(entry: ActivityEntry, vault_root: Path) -> bool:
    """Pure check: entry undone? snapshot path set? snapshot dir exists?"""
    if entry.undone:
        return False
    if not entry.can_undo:
        return False
    if entry.snapshot_path is None:
        return False
    return (vault_root / entry.snapshot_path).is_dir()


def undo(
    vault_root: Path,
    op_id: str,
    *,
    lock_timeout: float = 60.0,
) -> UndoResult:
    """Atomically undo the operation identified by op_id.

    Steps:
    1. Acquire pipeline_lock.
    2. Load activity log; find entry by id (raise UndoError if missing).
    3. Verify can_undo (raise UndoError with reason if not).
    4. restore_from_snapshot — on failure, raise UndoError with recovery_hint.
    5. After restore: vault is now in pre-op state. Re-load activity log
       (it was swapped along with vault), append manual_restore entry,
       mark original as undone, save.
    """
    with pipeline_lock(vault_root, timeout=lock_timeout):
        log = ActivityLog.load(vault_root)
        entry = log.find_by_id(op_id)
        if entry is None:
            raise UndoError(f"activity entry not found: {op_id}")
        if entry.undone:
            raise UndoError(f"entry {op_id} already undone at {entry.undone_at}")
        if not entry.can_undo:
            raise UndoError(f"entry {op_id} is not undoable")
        if entry.snapshot_path is None:
            raise UndoError(f"entry {op_id} has no snapshot_path")
        snap_path = vault_root / entry.snapshot_path
        if not snap_path.is_dir():
            raise UndoError(
                f"snapshot at {snap_path} not found (manually deleted?)"
            )

        result = restore_from_snapshot(vault_root, snap_path)
        if not result.success:
            raise UndoError(
                f"restore failed: {result.error}"
                + (
                    f". recovery hint: {result.recovery_hint}"
                    if result.recovery_hint
                    else ""
                )
            )

        # Vault was swapped — re-load activity log from the restored vault.
        # The snapshot was taken BEFORE the op being undone, so the snapshot's
        # .activity.json does NOT contain the op's entry. After restore, log
        # lacks the entry — we add it back explicitly with undone=True, then
        # append manual_restore.
        log = ActivityLog.load(vault_root)

        new_id = uuid4().hex
        now = datetime.now(UTC)

        # Add the original entry (now flagged undone) so the user sees their history.
        original = entry.model_copy(
            update={
                "undone": True,
                "undone_at": now,
                "undone_by_id": new_id,
            }
        )
        # Idempotent-safe: if an older snapshot somehow already contains this
        # entry, replace in-place; else append.
        if log.find_by_id(original.id) is None:
            log.append(original)
        else:
            for i, e in enumerate(log.entries):
                if e.id == original.id:
                    log.entries[i] = original
                    break

        manual_restore_entry = ActivityEntry(
            id=new_id,
            timestamp=now,
            operation_type="manual_restore",
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=[],
            metadata={
                "undone_id": original.id,
                "reverted_pages": list(original.affected_pages),
            },
        )
        log.append(manual_restore_entry)
        log.save(vault_root)

        return UndoResult(
            success=True,
            restored_pages=list(original.affected_pages),
            new_entry_id=new_id,
        )
