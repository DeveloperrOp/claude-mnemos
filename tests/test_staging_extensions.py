"""Tests for Plan #8 StagingTransaction.move/delete extensions."""

from pathlib import Path

import pytest

from claude_mnemos.core.snapshots import restore_from_snapshot
from claude_mnemos.core.staging import StagingPromoteError, StagingTransaction


def _populate(vault: Path) -> None:
    (vault / "wiki/entities").mkdir(parents=True)
    (vault / "wiki/entities/foo.md").write_text("Foo body\n", encoding="utf-8")
    (vault / "wiki/entities/bar.md").write_text("Bar body\n", encoding="utf-8")
    (vault / "wiki/concepts").mkdir(parents=True)
    (vault / "wiki/concepts/baz.md").write_text("Baz body\n", encoding="utf-8")


def test_move_renames_file_after_promote(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-1", operation_type="ontology") as txn:
        txn.move("wiki/entities/foo.md", "wiki/entities/foo-renamed.md")
        txn.promote_to_vault()

    assert not (vault / "wiki/entities/foo.md").exists()
    assert (vault / "wiki/entities/foo-renamed.md").read_text() == "Foo body\n"


def test_move_with_missing_source_rolls_back(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-2", operation_type="ontology") as txn:
        txn.move("wiki/entities/missing.md", "wiki/entities/dst.md")
        with pytest.raises(StagingPromoteError):
            txn.promote_to_vault()

    # Vault unchanged
    assert (vault / "wiki/entities/foo.md").exists()
    assert not (vault / "wiki/entities/dst.md").exists()


def test_move_into_new_subdir(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-3", operation_type="ontology") as txn:
        txn.move("wiki/entities/foo.md", "wiki/sources/foo.md")
        txn.promote_to_vault()

    assert (vault / "wiki/sources/foo.md").read_text() == "Foo body\n"


def test_delete_with_to_trash_default(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-4", operation_type="ontology") as txn:
        txn.delete("wiki/entities/foo.md")
        txn.promote_to_vault()

    assert not (vault / "wiki/entities/foo.md").exists()
    trash_root = vault / ".trash"
    assert trash_root.is_dir()
    deleted_dirs = [
        p for p in trash_root.iterdir()
        if p.is_dir() and p.name.startswith("deleted-foo-")
    ]
    assert len(deleted_dirs) == 1
    moved = deleted_dirs[0] / "foo.md"
    assert moved.read_text() == "Foo body\n"
    reason = (deleted_dirs[0] / ".reason.txt").read_text()
    assert "ontology" in reason
    assert "op-4" in reason


def test_delete_hard(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-5", operation_type="ontology") as txn:
        txn.delete("wiki/entities/foo.md", to_trash=False)
        txn.promote_to_vault()

    assert not (vault / "wiki/entities/foo.md").exists()
    trash_root = vault / ".trash"
    if trash_root.exists():
        assert all(
            not p.name.startswith("deleted-foo-") for p in trash_root.iterdir()
        )


def test_delete_missing_is_silent(tmp_path: Path):
    """Deleting a non-existent file is a no-op (e.g. already moved earlier in txn)."""
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-6", operation_type="ontology") as txn:
        txn.delete("wiki/entities/nope.md")
        txn.promote_to_vault()

    assert (vault / "wiki/entities/foo.md").exists()


def test_combined_write_move_delete(tmp_path: Path):
    """Realistic ontology merge: write target, delete two sources, all atomic."""
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-merge-1", operation_type="ontology") as txn:
        txn.write(
            Path("wiki/entities/concurrency.md"),
            "Combined Foo + Bar body\n",
        )
        txn.delete("wiki/entities/foo.md")
        txn.delete("wiki/entities/bar.md")
        txn.promote_to_vault()

    assert (vault / "wiki/entities/concurrency.md").read_text() == "Combined Foo + Bar body\n"
    assert not (vault / "wiki/entities/foo.md").exists()
    assert not (vault / "wiki/entities/bar.md").exists()
    # Baz untouched
    assert (vault / "wiki/concepts/baz.md").exists()


def test_snapshot_captures_pre_move_state(tmp_path: Path):
    """After promote, the snapshot directory contains the original (pre-move) files —
    so manual restore via restore_from_snapshot reverts move/delete.
    """
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-snap-1", operation_type="ontology") as txn:
        txn.move("wiki/entities/foo.md", "wiki/entities/foo-new.md")
        txn.delete("wiki/entities/bar.md")
        promote = txn.promote_to_vault()

    snapshot = promote.snapshot
    assert snapshot is not None
    assert (snapshot / "wiki/entities/foo.md").exists()
    assert (snapshot / "wiki/entities/bar.md").exists()
    assert not (snapshot / "wiki/entities/foo-new.md").exists()

    restore = restore_from_snapshot(vault, snapshot)
    assert restore.success is True
    assert (vault / "wiki/entities/foo.md").read_text() == "Foo body\n"
    assert (vault / "wiki/entities/bar.md").read_text() == "Bar body\n"
    assert not (vault / "wiki/entities/foo-new.md").exists()


def test_move_rejected_via_exception_does_not_touch_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)

    with (
        pytest.raises(RuntimeError, match="oh no"),
        StagingTransaction(vault, "op-7", operation_type="ontology") as txn,
    ):
        txn.move("wiki/entities/foo.md", "wiki/entities/foo-new.md")
        raise RuntimeError("oh no")

    # Vault unchanged: foo.md still there, no foo-new.md
    assert (vault / "wiki/entities/foo.md").read_text() == "Foo body\n"
    assert not (vault / "wiki/entities/foo-new.md").exists()


def test_move_validates_arguments(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-8", operation_type="ontology") as txn:
        with pytest.raises(ValueError):
            txn.move("", "dst.md")
        with pytest.raises(ValueError):
            txn.move("src.md", "")
        with pytest.raises(ValueError):
            txn.move("same.md", "same.md")
        # txn never promoted — __exit__ rejects to trash; that's expected


def test_delete_validates_arguments(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)

    with (
        StagingTransaction(vault, "op-9", operation_type="ontology") as txn,
        pytest.raises(ValueError),
    ):
        txn.delete("")


def test_move_after_finalize_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate(vault)
    txn = StagingTransaction(vault, "op-10", operation_type="ontology")
    txn.staging_dir.mkdir(parents=True, exist_ok=True)
    txn.write(Path("wiki/entities/x.md"), "x")
    txn.promote_to_vault()
    with pytest.raises(RuntimeError):
        txn.move("a.md", "b.md")
    with pytest.raises(RuntimeError):
        txn.delete("a.md")
