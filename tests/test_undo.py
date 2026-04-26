from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from claude_mnemos.core.snapshots import RestoreResult
from claude_mnemos.core.undo import UndoError, UndoResult, can_undo, undo
from claude_mnemos.state.activity import ActivityEntry, ActivityLog


def _populate_vault_with_one_ingest(tmp_path: Path) -> tuple[Path, str, Path]:
    """Set up vault with a fake snapshot + one activity entry.

    Returns (vault, op_id, snap_path).
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    snap_dir = vault / ".backups" / "pre-op-2026-04-26-14-30-00-ingest-abc"
    snap_dir.mkdir(parents=True)
    (snap_dir / ".meta.json").write_text(
        '{"timestamp":"2026-04-26T14:30:00+00:00","operation_id":"abc",'
        '"operation_type":"ingest","page_count":0,"vault_size_bytes":0}',
        encoding="utf-8",
    )

    op_id = uuid4().hex
    log = ActivityLog()
    log.append(
        ActivityEntry(
            id=op_id,
            timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
            operation_type="ingest_extracted",
            status="success",
            snapshot_path=".backups/pre-op-2026-04-26-14-30-00-ingest-abc",
            can_undo=True,
            affected_pages=["wiki/entities/foo.md"],
            metadata={"session_id": "abc"},
        )
    )
    log.save(vault)
    return vault, op_id, snap_dir


def test_can_undo_true_for_undoable_entry(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    assert can_undo(entry, vault) is True


def test_can_undo_false_when_undone(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    entry.undone = True
    assert can_undo(entry, vault) is False


def test_can_undo_false_when_can_undo_flag_false(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    entry.can_undo = False
    assert can_undo(entry, vault) is False


def test_can_undo_false_when_snapshot_path_none(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    entry = ActivityEntry(
        id="x",
        timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
        operation_type="manual_restore",
        status="success",
        snapshot_path=None,
        can_undo=False,
        affected_pages=[],
        metadata={},
    )
    assert can_undo(entry, vault) is False


def test_can_undo_false_when_snapshot_dir_missing(tmp_path: Path):
    vault, op_id, snap_dir = _populate_vault_with_one_ingest(tmp_path)
    # Remove snapshot dir
    import shutil
    shutil.rmtree(snap_dir)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    assert can_undo(entry, vault) is False


def test_undo_entry_not_found_raises(tmp_path: Path):
    vault, _, _ = _populate_vault_with_one_ingest(tmp_path)
    with pytest.raises(UndoError, match="not found"):
        undo(vault, "nonexistent-id")


def test_undo_already_undone_raises(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    entry.undone = True
    log.save(vault)

    with pytest.raises(UndoError, match="already undone"):
        undo(vault, op_id)


def test_undo_snapshot_missing_raises(tmp_path: Path):
    vault, op_id, snap_dir = _populate_vault_with_one_ingest(tmp_path)
    import shutil
    shutil.rmtree(snap_dir)
    with pytest.raises(UndoError, match="snapshot"):
        undo(vault, op_id)


def test_undo_success_marks_entry_undone(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)

    # Stub restore to claim success without actually swapping the vault dir
    # (we just want to verify post-restore log update logic)
    def fake_restore(vault_arg, snapshot_arg):
        return RestoreResult(success=True, vault_intact=False)

    with patch("claude_mnemos.core.undo.restore_from_snapshot", side_effect=fake_restore):
        result = undo(vault, op_id)

    assert isinstance(result, UndoResult)
    assert result.success is True
    assert result.new_entry_id is not None

    log = ActivityLog.load(vault)
    original = log.find_by_id(op_id)
    assert original is not None
    assert original.undone is True
    assert original.undone_at is not None
    assert original.undone_by_id == result.new_entry_id

    new_entry = log.find_by_id(result.new_entry_id)
    assert new_entry is not None
    assert new_entry.operation_type == "manual_restore"
    assert new_entry.can_undo is False
    assert new_entry.snapshot_path is None
    assert new_entry.affected_pages == []
    assert new_entry.metadata["undone_id"] == op_id
    assert new_entry.metadata["reverted_pages"] == ["wiki/entities/foo.md"]


def test_undo_restore_failure_raises_with_recovery_hint(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)

    def fake_failed_restore(vault_arg, snapshot_arg):
        return RestoreResult(
            success=False,
            vault_intact=False,
            vault_possibly_corrupted=True,
            error="rename failed",
            recovery_hint="manual recovery needed at /tmp/old",
        )

    with (
        patch(
            "claude_mnemos.core.undo.restore_from_snapshot",
            side_effect=fake_failed_restore,
        ),
        pytest.raises(UndoError, match="restore failed"),
    ):
        undo(vault, op_id)


def test_undo_manual_restore_entry_not_undoable(tmp_path: Path):
    """A manual_restore entry has can_undo=False, so undo refuses."""
    vault = tmp_path / "vault"
    vault.mkdir()
    log = ActivityLog()
    op_id = uuid4().hex
    log.append(
        ActivityEntry(
            id=op_id,
            timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
            operation_type="manual_restore",
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=[],
            metadata={},
        )
    )
    log.save(vault)

    with pytest.raises(UndoError):
        undo(vault, op_id)
