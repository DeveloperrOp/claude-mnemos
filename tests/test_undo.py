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
    def fake_restore(vault_arg, snapshot_arg, **kwargs):
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

    def fake_failed_restore(vault_arg, snapshot_arg, **kwargs):
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


def test_undo_preserves_other_snapshots_for_chain_undo(tmp_path: Path):
    """After undo of op2, op1's snapshot must still be available for undo."""
    from claude_mnemos.core.snapshots import create_snapshot

    vault = tmp_path / "vault"
    vault.mkdir()

    # Simulate op1: snapshot the empty pre-op state, then log op1's entry.
    snap1 = create_snapshot(vault, operation_id="op1", operation_type="ingest")
    op1_id = uuid4().hex
    log = ActivityLog.load(vault)
    log.append(
        ActivityEntry(
            id=op1_id,
            timestamp=datetime(2026, 4, 26, 14, 0, 0, tzinfo=UTC),
            operation_type="ingest_extracted",
            status="success",
            snapshot_path=str(snap1.relative_to(vault)).replace("\\", "/"),
            can_undo=True,
            affected_pages=["wiki/entities/foo.md"],
            metadata={"session_id": "op1"},
        )
    )
    log.save(vault)

    # Simulate op2: snapshot vault (now contains op1's log entry), then log op2.
    snap2 = create_snapshot(vault, operation_id="op2", operation_type="ingest")
    op2_id = uuid4().hex
    log = ActivityLog.load(vault)
    log.append(
        ActivityEntry(
            id=op2_id,
            timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
            operation_type="ingest_extracted",
            status="success",
            snapshot_path=str(snap2.relative_to(vault)).replace("\\", "/"),
            can_undo=True,
            affected_pages=["wiki/entities/bar.md"],
            metadata={"session_id": "op2"},
        )
    )
    log.save(vault)

    result = undo(vault, op2_id)

    assert result.success is True
    # CRITICAL: snap1 must still exist after the undo
    assert snap1.exists(), "earlier snapshot was lost during undo — chain undo broken"
    assert snap2.exists(), "current snapshot also expected to survive"

    # Now undo op1 — it should still work (chain undo)
    result2 = undo(vault, op1_id)
    assert result2.success is True


def test_undo_succeeds_with_open_jobs_db(tmp_path: Path):
    """undo() runs inside the daemon where <vault>/.jobs.db is always open —
    on Windows that blocks the whole-vault rename, so undo must succeed via
    the per-entry content-swap fallback (v0.0.43)."""
    from claude_mnemos.core.snapshots import create_snapshot

    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "page.md").write_text("original", encoding="utf-8")
    (vault / ".jobs.db").write_text("sqlite-stand-in", encoding="utf-8")
    snap = create_snapshot(vault, operation_id="u1", operation_type="ingest")

    op_id = uuid4().hex
    log = ActivityLog()
    log.append(
        ActivityEntry(
            id=op_id,
            timestamp=datetime.now(UTC),
            operation_type="ingest_extracted",
            status="success",
            snapshot_path=str(snap.relative_to(vault)),
            can_undo=True,
            affected_pages=["wiki/page.md"],
            metadata={},
        )
    )
    log.save(vault)
    (vault / "wiki" / "page.md").write_text("MUTATED", encoding="utf-8")

    with open(vault / ".jobs.db", "r+b"):  # the daemon's open handle
        result = undo(vault, op_id)

    assert result.success is True, result.error
    assert (vault / "wiki" / "page.md").read_text(encoding="utf-8") == "original"


def test_undo_passes_tracker_to_restore(tmp_path: Path, monkeypatch):
    """The daemon route passes its OurWritesTracker so the watchdog is paused
    around the swap — without it the content-swap fallback floods the alert
    ring with one external_create per restored page."""
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    seen = {}

    def fake_restore(vault_root, snap_path, *, tracker=None, **kwargs):
        seen["tracker"] = tracker
        return RestoreResult(success=True, vault_intact=False)

    monkeypatch.setattr("claude_mnemos.core.undo.restore_from_snapshot", fake_restore)
    sentinel = object()
    undo(vault, op_id, tracker=sentinel)  # type: ignore[arg-type]
    assert seen["tracker"] is sentinel
