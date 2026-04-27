from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from claude_mnemos.state.activity import (
    ACTIVITY_FILENAME,
    ActivityCorruptError,
    ActivityEntry,
    ActivityLog,
)


def _entry(
    *,
    op_type: str = "ingest_extracted",
    can_undo: bool = True,
    undone: bool = False,
    snapshot_path: str | None = ".backups/pre-op-2026-04-26-14-30-00-ingest-abc",
) -> ActivityEntry:
    return ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
        operation_type=op_type,
        status="success",
        snapshot_path=snapshot_path,
        can_undo=can_undo,
        undone=undone,
        affected_pages=["wiki/entities/foo.md"],
        metadata={"session_id": "abc-123"},
    )


def test_load_missing_file_returns_empty_log(tmp_path: Path):
    log = ActivityLog.load(tmp_path)
    assert log.version == 1
    assert log.entries == []


def test_save_then_load_roundtrip(tmp_path: Path):
    log = ActivityLog()
    log.append(_entry(op_type="ingest_extracted"))
    log.save(tmp_path)

    assert (tmp_path / ACTIVITY_FILENAME).exists()

    loaded = ActivityLog.load(tmp_path)
    assert len(loaded.entries) == 1
    assert loaded.entries[0].operation_type == "ingest_extracted"
    assert loaded.entries[0].metadata["session_id"] == "abc-123"


def test_serialize_to_string_matches_save_output(tmp_path: Path):
    log = ActivityLog()
    log.append(_entry())

    serialized = log.serialize_to_string()
    log.save(tmp_path)
    on_disk = (tmp_path / ACTIVITY_FILENAME).read_text(encoding="utf-8")

    assert serialized == on_disk


def test_load_corrupt_json_raises(tmp_path: Path):
    (tmp_path / ACTIVITY_FILENAME).write_text("not json {", encoding="utf-8")
    with pytest.raises(ActivityCorruptError):
        ActivityLog.load(tmp_path)


def test_load_invalid_schema_raises(tmp_path: Path):
    (tmp_path / ACTIVITY_FILENAME).write_text(
        '{"version":1,"entries":[{"unknown_field":1}]}',
        encoding="utf-8",
    )
    with pytest.raises(ActivityCorruptError):
        ActivityLog.load(tmp_path)


def test_load_unknown_top_level_field_raises(tmp_path: Path):
    (tmp_path / ACTIVITY_FILENAME).write_text(
        '{"version":1,"entries":[],"unknown":1}',
        encoding="utf-8",
    )
    with pytest.raises(ActivityCorruptError):
        ActivityLog.load(tmp_path)


def test_append_duplicate_id_raises():
    log = ActivityLog()
    e = _entry()
    log.append(e)
    with pytest.raises(ValueError):
        log.append(_entry(op_type="ingest_raw_only").model_copy(update={"id": e.id}))


def test_find_by_id_present():
    log = ActivityLog()
    e = _entry()
    log.append(e)
    found = log.find_by_id(e.id)
    assert found is not None
    assert found.id == e.id


def test_find_by_id_missing():
    log = ActivityLog()
    log.append(_entry())
    assert log.find_by_id("nonexistent") is None


def test_human_edit_detected_op_type_accepted():
    e = ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 27, 14, 23, 11, tzinfo=UTC),
        operation_type="human_edit_detected",
        status="success",
        snapshot_path=None,
        can_undo=False,
        affected_pages=["wiki/entities/foo.md"],
        metadata={"detected_at": "2026-04-27T14:23:11Z"},
    )
    log = ActivityLog()
    log.append(e)
    assert log.entries[0].operation_type == "human_edit_detected"
    assert log.entries[0].can_undo is False
    assert log.entries[0].snapshot_path is None


def test_human_edit_detected_roundtrip(tmp_path: Path):
    log = ActivityLog()
    log.append(
        ActivityEntry(
            id=uuid4().hex,
            timestamp=datetime(2026, 4, 27, 14, 23, 11, tzinfo=UTC),
            operation_type="human_edit_detected",
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=["wiki/entities/foo.md"],
            metadata={"detected_at": "2026-04-27T14:23:11Z"},
        )
    )
    log.save(tmp_path)
    loaded = ActivityLog.load(tmp_path)
    assert loaded.entries[0].operation_type == "human_edit_detected"


def test_last_undoable_returns_newest_undoable():
    log = ActivityLog()
    e_old = _entry()
    log.append(e_old)
    # Newer entry but not undoable
    e_mid = _entry(can_undo=False).model_copy(
        update={"id": uuid4().hex, "timestamp": datetime(2026, 4, 26, 15, 0, 0, tzinfo=UTC)}
    )
    log.append(e_mid)
    # Newest undoable
    e_new = _entry().model_copy(
        update={"id": uuid4().hex, "timestamp": datetime(2026, 4, 26, 16, 0, 0, tzinfo=UTC)}
    )
    log.append(e_new)

    found = log.last_undoable()
    assert found is not None
    assert found.id == e_new.id


def test_last_undoable_returns_none_when_all_undone():
    log = ActivityLog()
    log.append(_entry(undone=True))
    log.append(_entry(can_undo=False).model_copy(update={"id": uuid4().hex}))
    assert log.last_undoable() is None


def test_save_uses_atomic_write_no_partial_file(tmp_path: Path, monkeypatch):
    log = ActivityLog()
    log.append(_entry())

    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-write crash")

    monkeypatch.setattr("claude_mnemos.core.atomic.os.replace", boom)
    with pytest.raises(RuntimeError):
        log.save(tmp_path)

    leftovers = list(tmp_path.glob(f"{ACTIVITY_FILENAME}*"))
    assert leftovers == []


def test_entry_with_none_snapshot_path():
    """manual_restore entries have snapshot_path=None."""
    e = ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
        operation_type="manual_restore",
        status="success",
        snapshot_path=None,
        can_undo=False,
        affected_pages=[],
        metadata={"undone_id": "abc"},
    )
    assert e.snapshot_path is None
    assert e.can_undo is False


def test_append_rejects_out_of_order_timestamp():
    log = ActivityLog()
    log.append(
        _entry().model_copy(
            update={"timestamp": datetime(2026, 4, 26, 15, 0, 0, tzinfo=UTC)}
        )
    )
    older = _entry().model_copy(
        update={"id": uuid4().hex, "timestamp": datetime(2026, 4, 26, 14, 0, 0, tzinfo=UTC)}
    )
    with pytest.raises(ValueError, match="chronological"):
        log.append(older)


def test_entry_validate_assignment_rejects_bad_field():
    """validate_assignment catches typos when mutating fields after construction."""
    e = _entry()
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        e.undone = "not-a-bool"  # type: ignore[assignment]  # not coercible to bool


def test_entry_accepts_ontology_apply_op_type():
    """Plan #8 extends ActivityOperationType with `ontology_apply`."""
    e = ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
        operation_type="ontology_apply",
        status="success",
        snapshot_path=".backups/pre-op-2026-04-26-14-30-00-ontology-abc",
        can_undo=True,
        affected_pages=["wiki/entities/foo.md"],
        metadata={"suggestion_id": "ont-2026-04-26-aaaaaa", "operation": "merge_entities"},
    )
    assert e.operation_type == "ontology_apply"


def test_lint_fix_op_type_accepted():
    e = ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC),
        operation_type="lint_fix",
        status="success",
        snapshot_path=".backups/pre-op-2026-04-27-14-00-00-lint_fix-abc",
        can_undo=True,
        affected_pages=["wiki/entities/foo.md"],
        metadata={"fixed_finding_ids": ["trailing_whitespace:abcd1234"]},
    )
    log = ActivityLog()
    log.append(e)
    assert log.entries[0].operation_type == "lint_fix"
