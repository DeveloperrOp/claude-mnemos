import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_mnemos.core.snapshots import (
    SnapshotError,
    SnapshotMeta,
    create_snapshot,
    restore_from_snapshot,
)


def _populate_vault(vault: Path) -> None:
    """Create a sample vault with raw, wiki, manifest, and noisy internal dirs."""
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "raw" / "chats").mkdir(parents=True, exist_ok=True)
    (vault / "raw" / "chats" / "abc.md").write_text("# Transcript\n", encoding="utf-8")
    (vault / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
    (vault / "wiki" / "entities" / "foo.md").write_text(
        "---\ntitle: Foo\n---\nbody\n", encoding="utf-8"
    )
    (vault / ".manifest.json").write_text('{"version":1,"ingested":{}}\n', encoding="utf-8")
    # Noise that MUST be excluded:
    (vault / ".staging").mkdir()
    (vault / ".staging" / "leftover.md").write_text("staged junk", encoding="utf-8")
    (vault / ".backups").mkdir()
    (vault / ".backups" / "old-snapshot").mkdir()
    (vault / ".trash").mkdir()
    (vault / ".trash" / "rejected").mkdir()
    (vault / ".pipeline.lock").write_text("", encoding="utf-8")


def test_create_snapshot_copies_vault_contents(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    assert snap.exists()
    assert snap.is_dir()
    assert (snap / "raw" / "chats" / "abc.md").read_text(encoding="utf-8") == "# Transcript\n"
    assert (snap / "wiki" / "entities" / "foo.md").exists()
    assert (snap / ".manifest.json").exists()


def test_create_snapshot_excludes_internal_dirs(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    assert not (snap / ".staging").exists()
    assert not (snap / ".backups").exists()
    assert not (snap / ".trash").exists()
    assert not (snap / ".pipeline.lock").exists()


def test_create_snapshot_writes_meta_json(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    meta_path = snap / ".meta.json"
    assert meta_path.exists()
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    meta = SnapshotMeta.model_validate(data)
    assert meta.operation_id == "abc-123"
    assert meta.operation_type == "ingest"
    assert meta.page_count >= 1
    assert meta.vault_size_bytes > 0


def test_create_snapshot_path_format(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    parent = snap.parent
    assert parent == vault / ".backups"
    assert snap.name.startswith("pre-op-")
    assert "-ingest-" in snap.name
    assert snap.name.endswith("-abc-123")


def test_create_snapshot_with_empty_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()

    snap = create_snapshot(vault, operation_id="empty", operation_type="ingest")

    assert snap.exists()
    assert (snap / ".meta.json").exists()
    meta = SnapshotMeta.model_validate(json.loads((snap / ".meta.json").read_text()))
    assert meta.page_count == 0
    assert meta.vault_size_bytes == 0


def test_create_snapshot_collision_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap1 = create_snapshot(vault, operation_id="abc", operation_type="ingest")
    # Trying to create the exact same path again should raise
    fixed_ts = snap1.name.split("pre-op-")[1].rsplit("-ingest-", 1)[0]
    with (
        patch("claude_mnemos.core.snapshots._timestamp", return_value=fixed_ts),
        pytest.raises(SnapshotError),
    ):
        create_snapshot(vault, operation_id="abc", operation_type="ingest")


def test_restore_swaps_vault_atomically(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    # Mutate vault after snapshot
    (vault / "wiki" / "entities" / "foo.md").write_text("CHANGED", encoding="utf-8")
    (vault / "wiki" / "entities" / "new.md").write_text("new content", encoding="utf-8")

    result = restore_from_snapshot(vault, snap)

    assert result.success is True
    assert result.vault_intact is False  # vault was swapped
    # foo.md restored to original
    restored = (vault / "wiki" / "entities" / "foo.md").read_text(encoding="utf-8")
    assert restored == "---\ntitle: Foo\n---\nbody\n"
    # new.md gone (didn't exist in snapshot)
    assert not (vault / "wiki" / "entities" / "new.md").exists()


def test_restore_drops_meta_json_from_swap(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    restore_from_snapshot(vault, snap)

    # Restored vault must not contain `.meta.json` (that's snapshot bookkeeping, not vault content)
    assert not (vault / ".meta.json").exists()


def test_restore_preserves_old_state_on_stage_failure(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    # Sabotage shutil.copytree to fail during restore staging
    real_copytree = shutil.copytree

    def boom(src, dst, **kw):
        if "mnemos-restore" in str(dst):
            raise OSError("disk full")
        return real_copytree(src, dst, **kw)

    monkeypatch.setattr("claude_mnemos.core.snapshots.shutil.copytree", boom)

    result = restore_from_snapshot(vault, snap)

    assert result.success is False
    assert result.vault_intact is True
    # Vault still has the un-restored content
    assert (vault / "wiki" / "entities" / "foo.md").exists()
    # No partial restore directory left around
    leftovers = [p for p in vault.parent.iterdir() if "mnemos-restore" in p.name]
    assert leftovers == []


def test_restore_aside_rename_failure_keeps_vault(tmp_path: Path, monkeypatch):
    """If renaming vault -> .mnemos-old fails, vault stays intact and temp is cleaned."""
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    real_rename = Path.rename

    def boom_aside(self, target):
        # Fail only on the aside-rename (vault -> .mnemos-old-...)
        if ".mnemos-old" in str(target):
            raise OSError("simulated aside-rename failure")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", boom_aside)

    result = restore_from_snapshot(vault, snap)

    assert result.success is False
    assert result.vault_intact is True
    assert result.error is not None
    # Vault content untouched
    assert (vault / "wiki" / "entities" / "foo.md").exists()
    # No temp left over
    leftovers = [p for p in vault.parent.iterdir() if p.name.startswith(".mnemos-")]
    assert leftovers == []


def test_restore_final_rename_failure_returns_recovery_hint(tmp_path: Path, monkeypatch):
    """If the final temp->vault rename fails, both paths are reported via recovery_hint."""
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    real_rename = Path.rename

    def boom_final(self, target):
        # Fail only when temp_root -> vault rename happens (target.name == "vault")
        if target.name == "vault":
            raise OSError("simulated final-rename failure")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", boom_final)

    result = restore_from_snapshot(vault, snap)

    assert result.success is False
    assert result.vault_possibly_corrupted is True
    assert result.recovery_hint is not None
    # The recovery hint must mention BOTH the old vault path and the temp root path
    assert ".mnemos-old" in result.recovery_hint
    assert ".mnemos-restore" in result.recovery_hint
    # The original vault should be at .mnemos-old-... (un-restored state preserved)
    old_vaults = [p for p in vault.parent.iterdir() if p.name.startswith(".mnemos-old-")]
    assert len(old_vaults) == 1


def test_create_snapshot_at_uses_provided_path(tmp_path: Path):
    """create_snapshot_at writes to the exact path provided, not auto-generated."""
    from claude_mnemos.core.snapshots import create_snapshot_at

    vault = tmp_path / "vault"
    _populate_vault(vault)

    custom_path = vault / ".backups" / "custom-name-here"
    snap = create_snapshot_at(
        vault, custom_path, operation_id="abc-123", operation_type="ingest"
    )

    assert snap == custom_path
    assert snap.exists()
    assert (snap / ".meta.json").exists()
    assert (snap / "wiki" / "entities" / "foo.md").exists()


def test_create_snapshot_at_collision_raises(tmp_path: Path):
    """Reuses spec'd 'collision raises' behavior."""
    from claude_mnemos.core.snapshots import SnapshotError, create_snapshot_at

    vault = tmp_path / "vault"
    _populate_vault(vault)
    target = vault / ".backups" / "fixed-name"
    create_snapshot_at(vault, target, operation_id="abc", operation_type="ingest")

    with pytest.raises(SnapshotError):
        create_snapshot_at(vault, target, operation_id="abc", operation_type="ingest")


def test_create_snapshot_delegates_to_create_snapshot_at(tmp_path: Path):
    """create_snapshot still works (back-compat) and produces same shape as before."""
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc", operation_type="ingest")

    assert snap.parent == vault / ".backups"
    assert snap.name.startswith("pre-op-")
    assert snap.name.endswith("-abc")
    assert (snap / ".meta.json").exists()


def test_compute_snapshot_path_format(tmp_path: Path):
    """Single source of truth for snapshot path format."""
    from claude_mnemos.core.snapshots import compute_snapshot_path

    vault = tmp_path / "vault"
    path = compute_snapshot_path(vault, operation_id="abc-123", operation_type="ingest")

    assert path.parent == vault / ".backups"
    assert path.name.startswith("pre-op-")
    assert "-ingest-" in path.name
    assert path.name.endswith("-abc-123")


def test_restore_preserves_backups_dir(tmp_path: Path):
    """After restore, all earlier snapshots in .backups/ must still exist."""
    vault = tmp_path / "vault"
    _populate_vault(vault)
    # First snapshot
    snap1 = create_snapshot(vault, operation_id="op-1", operation_type="ingest")
    # Mutate vault, take a second snapshot
    (vault / "wiki" / "entities" / "foo.md").write_text("changed", encoding="utf-8")
    snap2 = create_snapshot(vault, operation_id="op-2", operation_type="ingest")

    # Restore from snap2
    result = restore_from_snapshot(vault, snap2)

    assert result.success is True
    # Both snapshots must still exist after restore
    assert snap1.exists()
    assert snap2.exists()
    assert (snap1 / ".meta.json").exists()
    assert (snap2 / ".meta.json").exists()


def test_restore_preserves_trash_dir(tmp_path: Path):
    """Trash dir survives restore (rejected staging from prior dry runs)."""
    vault = tmp_path / "vault"
    _populate_vault(vault)
    # Create a fake rejected staging in trash
    rejected = vault / ".trash" / "rejected-test-123"
    rejected.mkdir(parents=True)
    (rejected / ".reason.txt").write_text("test rejection", encoding="utf-8")

    snap = create_snapshot(vault, operation_id="op-1", operation_type="ingest")
    restore_from_snapshot(vault, snap)

    assert rejected.exists()
    assert (rejected / ".reason.txt").read_text(encoding="utf-8") == "test rejection"
