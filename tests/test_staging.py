from pathlib import Path

import pytest

from claude_mnemos.core.staging import (
    PromoteResult,
    StagingPromoteError,
    StagingTransaction,
)


def test_init_creates_staging_dir(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1"):
        assert (vault / ".staging" / "op-1").exists()
        assert (vault / ".staging" / "op-1").is_dir()
    # After exit (no promote called) — staging должен быть rejected → ушёл в .trash
    assert not (vault / ".staging" / "op-1").exists()


def test_write_creates_file_in_staging(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("wiki/entities/foo.md"), "body")
        # File must be in staging, NOT in vault
        assert (vault / ".staging" / "op-1" / "wiki" / "entities" / "foo.md").exists()
        assert not (vault / "wiki" / "entities" / "foo.md").exists()
        txn.promote_to_vault()


def test_write_creates_intermediate_dirs(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a/b/c/d.md"), "deep content")
        staged = vault / ".staging" / "op-1" / "a" / "b" / "c" / "d.md"
        assert staged.read_text(encoding="utf-8") == "deep content"
        txn.promote_to_vault()


def test_promote_moves_files_to_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("wiki/entities/foo.md"), "foo body")
        txn.write(Path("raw/chats/abc.md"), "raw content")
        result = txn.promote_to_vault()

    assert isinstance(result, PromoteResult)
    assert result.success is True
    assert (vault / "wiki" / "entities" / "foo.md").read_text(encoding="utf-8") == "foo body"
    assert (vault / "raw" / "chats" / "abc.md").read_text(encoding="utf-8") == "raw content"


def test_promote_creates_snapshot(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "preexisting.md").write_text("before", encoding="utf-8")

    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("new.md"), "added")
        result = txn.promote_to_vault()

    assert result.snapshot is not None
    assert result.snapshot.exists()
    # Snapshot has pre-op state (preexisting.md, no new.md)
    assert (result.snapshot / "preexisting.md").read_text(encoding="utf-8") == "before"
    assert not (result.snapshot / "new.md").exists()


def test_promote_cleans_up_staging(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a.md"), "x")
        txn.promote_to_vault()
    assert not (vault / ".staging" / "op-1").exists()


def test_promote_twice_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a.md"), "x")
        txn.promote_to_vault()
        with pytest.raises(RuntimeError):
            txn.promote_to_vault()


def test_reject_moves_staging_to_trash(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a.md"), "x")
        txn.reject("user requested cancel")

    assert not (vault / ".staging" / "op-1").exists()
    rejected = list((vault / ".trash").glob("rejected-op-1-*"))
    assert len(rejected) == 1
    assert (rejected[0] / "a.md").exists()
    reason_file = rejected[0] / ".reason.txt"
    assert "user requested cancel" in reason_file.read_text(encoding="utf-8")


def test_exit_without_promote_rejects(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a.md"), "forgotten")
        # caller forgot to call promote_to_vault()

    # On clean exit without promote — staging must be rejected
    assert not (vault / ".staging" / "op-1").exists()
    rejected = list((vault / ".trash").glob("rejected-op-1-*"))
    assert len(rejected) == 1


def test_exit_with_exception_rejects(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with (
        pytest.raises(RuntimeError, match="caller bug"),
        StagingTransaction(vault, operation_id="op-1") as txn,
    ):
        txn.write(Path("a.md"), "before crash")
        raise RuntimeError("caller bug")

    assert not (vault / ".staging" / "op-1").exists()
    rejected = list((vault / ".trash").glob("rejected-op-1-*"))
    assert len(rejected) == 1


def test_promote_failure_restores_from_snapshot(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "preexisting.md").write_text("original", encoding="utf-8")

    import shutil as _shutil
    real_move = _shutil.move
    calls = {"n": 0}

    def flaky_move(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("simulated mid-promote disk error")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr("claude_mnemos.core.staging.shutil.move", flaky_move)

    with (
        pytest.raises(StagingPromoteError),
        StagingTransaction(vault, operation_id="op-1") as txn,
    ):
        txn.write(Path("first.md"), "page one")
        txn.write(Path("second.md"), "page two")
        txn.promote_to_vault()

    # Vault must be restored to pre-op state: preexisting.md present, no first.md / second.md
    assert (vault / "preexisting.md").read_text(encoding="utf-8") == "original"
    assert not (vault / "first.md").exists()
    assert not (vault / "second.md").exists()
    # Staging should also be cleaned up by __exit__ reject path
    assert not (vault / ".staging" / "op-1").exists()


def test_promote_failure_when_snapshot_create_fails(tmp_path: Path, monkeypatch):
    """If snapshot itself can't be created, vault is untouched and StagingPromoteError fires."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "preexisting.md").write_text("intact", encoding="utf-8")

    def boom_snapshot(*args, **kwargs):
        from claude_mnemos.core.snapshots import SnapshotError
        raise SnapshotError("simulated snapshot failure")

    monkeypatch.setattr("claude_mnemos.core.staging.create_snapshot", boom_snapshot)

    with (
        pytest.raises(StagingPromoteError),
        StagingTransaction(vault, operation_id="op-1") as txn,
    ):
        txn.write(Path("a.md"), "would-be content")
        txn.promote_to_vault()

    # Vault never touched
    assert (vault / "preexisting.md").read_text(encoding="utf-8") == "intact"
    assert not (vault / "a.md").exists()
