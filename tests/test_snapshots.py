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


# ---------------------------------------------------------------------------
# Plan #5 extensions: parse_snapshot_name, daily/manual snapshots, list, delete, prune
# ---------------------------------------------------------------------------


def test_parse_snapshot_name_pre_op():
    from claude_mnemos.core.snapshots import parse_snapshot_name

    parsed = parse_snapshot_name("pre-op-2026-04-26-14-30-00-ingest_extracted-abc123")
    assert parsed is not None
    assert parsed.kind == "pre-op"
    assert parsed.timestamp.year == 2026
    assert parsed.timestamp.month == 4
    assert parsed.timestamp.day == 26
    assert parsed.timestamp.hour == 14
    assert parsed.op_type == "ingest_extracted"
    assert parsed.op_id == "abc123"
    assert parsed.label is None


def test_parse_snapshot_name_pre_op_with_dashes_in_id():
    from claude_mnemos.core.snapshots import parse_snapshot_name

    parsed = parse_snapshot_name("pre-op-2026-04-26-14-30-00-ingest_extracted-abc-1-2-3")
    assert parsed is not None
    assert parsed.op_type == "ingest_extracted"
    assert parsed.op_id == "abc-1-2-3"


def test_parse_snapshot_name_daily():
    from claude_mnemos.core.snapshots import parse_snapshot_name

    parsed = parse_snapshot_name("daily-2026-04-26")
    assert parsed is not None
    assert parsed.kind == "daily"
    assert parsed.timestamp.year == 2026
    assert parsed.timestamp.month == 4
    assert parsed.timestamp.day == 26
    assert parsed.timestamp.hour == 0
    assert parsed.op_id is None
    assert parsed.op_type is None
    assert parsed.label is None


def test_parse_snapshot_name_manual_no_label():
    from claude_mnemos.core.snapshots import parse_snapshot_name

    parsed = parse_snapshot_name("manual-2026-04-26-14-30-00")
    assert parsed is not None
    assert parsed.kind == "manual"
    assert parsed.timestamp.hour == 14
    assert parsed.label is None


def test_parse_snapshot_name_manual_with_label():
    from claude_mnemos.core.snapshots import parse_snapshot_name

    parsed = parse_snapshot_name("manual-2026-04-26-14-30-00-pre-release")
    assert parsed is not None
    assert parsed.kind == "manual"
    assert parsed.label == "pre-release"


def test_parse_snapshot_name_junk_returns_none():
    from claude_mnemos.core.snapshots import parse_snapshot_name

    assert parse_snapshot_name("random-junk") is None
    assert parse_snapshot_name("pre-op-malformed") is None
    assert parse_snapshot_name("daily-not-a-date") is None
    assert parse_snapshot_name("") is None


def test_compute_daily_snapshot_path(tmp_path: Path):
    from datetime import date

    from claude_mnemos.core.snapshots import compute_daily_snapshot_path

    vault = tmp_path / "vault"
    path = compute_daily_snapshot_path(vault, date(2026, 4, 26))
    assert path == vault / ".backups" / "daily-2026-04-26"


def test_compute_manual_snapshot_path_no_label(tmp_path: Path):
    from datetime import UTC, datetime

    from claude_mnemos.core.snapshots import compute_manual_snapshot_path

    vault = tmp_path / "vault"
    path = compute_manual_snapshot_path(
        vault, label=None, now=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC)
    )
    assert path == vault / ".backups" / "manual-2026-04-26-14-30-00"


def test_compute_manual_snapshot_path_with_label(tmp_path: Path):
    from datetime import UTC, datetime

    from claude_mnemos.core.snapshots import compute_manual_snapshot_path

    vault = tmp_path / "vault"
    path = compute_manual_snapshot_path(
        vault, label="release-1", now=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC)
    )
    assert path == vault / ".backups" / "manual-2026-04-26-14-30-00-release-1"


def test_compute_manual_snapshot_path_label_sanitized(tmp_path: Path):
    from datetime import UTC, datetime

    from claude_mnemos.core.snapshots import compute_manual_snapshot_path

    vault = tmp_path / "vault"
    path = compute_manual_snapshot_path(
        vault,
        label="my release/v1 alpha",
        now=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
    )
    assert "/" not in path.name
    assert " " not in path.name
    assert path.name.startswith("manual-2026-04-26-14-30-00-")


def test_compute_manual_snapshot_path_rejects_empty_after_sanitize(tmp_path: Path):
    from datetime import UTC, datetime

    from claude_mnemos.core.snapshots import compute_manual_snapshot_path

    vault = tmp_path / "vault"
    with pytest.raises(ValueError):
        compute_manual_snapshot_path(
            vault, label="///", now=datetime(2026, 4, 26, tzinfo=UTC)
        )


def test_create_daily_snapshot_creates_directory(tmp_path: Path):
    from datetime import date

    from claude_mnemos.core.snapshots import create_daily_snapshot

    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_daily_snapshot(vault, date(2026, 4, 26))
    assert snap.exists()
    assert snap.name == "daily-2026-04-26"
    assert (snap / ".meta.json").exists()
    meta = SnapshotMeta.model_validate(json.loads((snap / ".meta.json").read_text()))
    assert meta.operation_type == "daily"


def test_create_daily_snapshot_idempotent(tmp_path: Path):
    from datetime import date

    from claude_mnemos.core.snapshots import create_daily_snapshot

    vault = tmp_path / "vault"
    _populate_vault(vault)

    today = date(2026, 4, 26)
    snap1 = create_daily_snapshot(vault, today)
    # Mutate vault — second call should NOT overwrite the snapshot
    (vault / "wiki" / "entities" / "foo.md").write_text("changed", encoding="utf-8")
    snap2 = create_daily_snapshot(vault, today)

    assert snap1 == snap2
    # Original content preserved
    assert (snap1 / "wiki" / "entities" / "foo.md").read_text(encoding="utf-8") == (
        "---\ntitle: Foo\n---\nbody\n"
    )


def test_create_manual_snapshot_creates_directory(tmp_path: Path):
    from claude_mnemos.core.snapshots import create_manual_snapshot

    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_manual_snapshot(vault, label="smoke")
    assert snap.exists()
    assert snap.name.startswith("manual-")
    assert snap.name.endswith("-smoke")
    meta = SnapshotMeta.model_validate(json.loads((snap / ".meta.json").read_text()))
    assert meta.operation_type == "manual"


def test_list_snapshots_empty(tmp_path: Path):
    from claude_mnemos.core.snapshots import list_snapshots

    vault = tmp_path / "vault"
    vault.mkdir()
    assert list_snapshots(vault) == []


def test_list_snapshots_returns_known_kinds(tmp_path: Path):
    from datetime import date

    from claude_mnemos.core.snapshots import (
        create_daily_snapshot,
        create_manual_snapshot,
        create_snapshot,
        list_snapshots,
    )

    vault = tmp_path / "vault"
    _populate_vault(vault)

    create_snapshot(vault, operation_id="abc", operation_type="ingest_extracted")
    create_daily_snapshot(vault, date(2026, 4, 26))
    create_manual_snapshot(vault, label="release")

    items = list_snapshots(vault)
    kinds = {i.kind for i in items}
    assert kinds == {"pre-op", "daily", "manual"}


def test_list_snapshots_skips_junk(tmp_path: Path):
    from claude_mnemos.core.snapshots import list_snapshots

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    (vault / ".backups" / "random-stuff").mkdir()
    (vault / ".backups" / "another-junk").mkdir()

    assert list_snapshots(vault) == []


def test_list_snapshots_sorted_newest_first(tmp_path: Path):
    from datetime import date

    from claude_mnemos.core.snapshots import compute_daily_snapshot_path, list_snapshots

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)

    # Create directories manually with controlled names — bypass create_daily_snapshot
    # to keep the test pure
    for d in (date(2026, 4, 24), date(2026, 4, 26), date(2026, 4, 25)):
        compute_daily_snapshot_path(vault, d).mkdir()

    items = list_snapshots(vault)
    assert [i.timestamp.day for i in items] == [26, 25, 24]


def test_delete_snapshot_removes_directory(tmp_path: Path):
    from datetime import date

    from claude_mnemos.core.snapshots import create_daily_snapshot, delete_snapshot

    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_daily_snapshot(vault, date(2026, 4, 26))
    assert snap.exists()

    delete_snapshot(vault, snap.name)
    assert not snap.exists()


def test_delete_snapshot_rejects_traversal(tmp_path: Path):
    from claude_mnemos.core.snapshots import delete_snapshot

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    with pytest.raises(ValueError):
        delete_snapshot(vault, "../etc-passwd")


def test_delete_snapshot_rejects_absolute_path(tmp_path: Path):
    from claude_mnemos.core.snapshots import delete_snapshot

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    with pytest.raises(ValueError):
        delete_snapshot(vault, "/tmp/foo")


def test_delete_snapshot_rejects_unknown_prefix(tmp_path: Path):
    from claude_mnemos.core.snapshots import delete_snapshot

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    junk_dir = vault / ".backups" / "random-stuff"
    junk_dir.mkdir()
    with pytest.raises(ValueError):
        delete_snapshot(vault, "random-stuff")
    # Junk dir untouched (we don't delete things we don't own)
    assert junk_dir.exists()


def test_delete_snapshot_missing_raises(tmp_path: Path):
    from claude_mnemos.core.snapshots import delete_snapshot

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        delete_snapshot(vault, "daily-2026-04-26")


def test_prune_old_backups_removes_old_keeps_new(tmp_path: Path):
    from datetime import date

    from claude_mnemos.core.snapshots import (
        compute_daily_snapshot_path,
        compute_snapshot_path,
        prune_old_backups,
    )

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)

    # Old daily snapshot (250 days back)
    compute_daily_snapshot_path(vault, date(2025, 8, 19)).mkdir()
    # New daily snapshot (1 day back)
    compute_daily_snapshot_path(vault, date(2026, 4, 25)).mkdir()
    # Old pre-op (manually create with old timestamp in name)
    old_pre_op = vault / ".backups" / "pre-op-2025-08-19-12-00-00-ingest-old"
    old_pre_op.mkdir()
    new_pre_op = compute_snapshot_path(
        vault, operation_id="new", operation_type="ingest"
    )
    new_pre_op.mkdir()

    result = prune_old_backups(vault, retention_days=180, today=date(2026, 4, 26))

    pruned_names = set(result.pruned)
    assert "daily-2025-08-19" in pruned_names
    assert "pre-op-2025-08-19-12-00-00-ingest-old" in pruned_names
    assert "daily-2026-04-25" not in pruned_names
    assert new_pre_op.name not in pruned_names
    assert result.kept == 2
    assert result.errors == []


def test_prune_old_backups_skips_junk(tmp_path: Path):
    from datetime import date

    from claude_mnemos.core.snapshots import prune_old_backups

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    junk = vault / ".backups" / "random-stuff"
    junk.mkdir()

    result = prune_old_backups(vault, retention_days=30, today=date(2026, 4, 26))
    assert result.pruned == []
    # Junk not deleted, not counted as kept either (not ours)
    assert junk.exists()


def test_prune_old_backups_handles_rmtree_failure(tmp_path: Path, monkeypatch):
    from datetime import date

    from claude_mnemos.core.snapshots import compute_daily_snapshot_path, prune_old_backups

    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    old = compute_daily_snapshot_path(vault, date(2025, 1, 1))
    old.mkdir()

    def boom(_path, **_kw):
        raise OSError("permission denied")

    monkeypatch.setattr("claude_mnemos.core.snapshots.shutil.rmtree", boom)

    result = prune_old_backups(vault, retention_days=180, today=date(2026, 4, 26))
    assert result.pruned == []
    assert len(result.errors) == 1
    assert result.errors[0][0] == old.name


# Plan #9 — tracker pause integration


def test_restore_pauses_tracker_during_swap(tmp_path: Path):
    from claude_mnemos.daemon.our_writes import OurWritesTracker

    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="op-pause", operation_type="ingest")

    pause_seen: list[bool] = []

    class _SpyTracker(OurWritesTracker):
        def __init__(self) -> None:
            super().__init__(ttl_s=60.0, pause_cooldown_s=0.0)

        def paused(self):  # type: ignore[override]
            cm = super().paused()

            outer = self

            class _Wrapped:
                def __enter__(_inner):
                    cm.__enter__()
                    pause_seen.append(outer.is_paused)
                    return None

                def __exit__(_inner, exc_type, exc, tb):
                    return cm.__exit__(exc_type, exc, tb)

            return _Wrapped()

    tracker = _SpyTracker()
    result = restore_from_snapshot(vault, snap, tracker=tracker)

    assert result.success is True
    assert pause_seen == [True]
    assert tracker.is_paused is False


def test_restore_without_tracker_unchanged(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="op-none", operation_type="ingest")

    # Modify post-snapshot, restore should bring back snapshot state.
    (vault / "wiki" / "entities" / "foo.md").write_text(
        "---\ntitle: Foo\n---\nMODIFIED\n", encoding="utf-8"
    )
    result = restore_from_snapshot(vault, snap)
    assert result.success is True
    assert "body" in (vault / "wiki" / "entities" / "foo.md").read_text()


def test_restore_pauses_tracker_on_snapshot_missing(tmp_path: Path):
    """Even on early-fail paths, tracker pause must release."""
    from claude_mnemos.daemon.our_writes import OurWritesTracker

    vault = tmp_path / "vault"
    _populate_vault(vault)
    tracker = OurWritesTracker(ttl_s=60.0)
    nonexistent = vault / ".backups" / "nope"

    result = restore_from_snapshot(vault, nonexistent, tracker=tracker)
    assert result.success is False
    assert tracker.is_paused is False


def test_snapshot_excludes_jobs_db(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    # Seed the jobs DB and its WAL companions
    (vault / ".jobs.db").write_bytes(b"sqlite db content")
    (vault / ".jobs.db-wal").write_bytes(b"wal")
    (vault / ".jobs.db-shm").write_bytes(b"shm")
    snap = create_snapshot(vault, operation_id="op-jobs", operation_type="ingest")
    assert not (snap / ".jobs.db").exists()
    assert not (snap / ".jobs.db-wal").exists()
    assert not (snap / ".jobs.db-shm").exists()
