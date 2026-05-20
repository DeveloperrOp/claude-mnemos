from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from claude_mnemos.core.snapshots import (
    RestorePreview,
    compute_restore_preview,
    create_snapshot_at,
)


def _make_page(path: Path, content: str = "body") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_snap(vault: Path, name: str) -> Path:
    snap_path = vault / ".backups" / name
    return create_snapshot_at(
        vault,
        snap_path,
        operation_id="test",
        operation_type="manual",
    )


def test_preview_will_create(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _make_page(vault / "wiki" / "a.md", "alpha")
    snap = _create_snap(vault, "manual-2026-05-20-10-00-00")
    # Remove vault file after snapshot — so restoring would re-create it
    (vault / "wiki" / "a.md").unlink()
    preview = compute_restore_preview(vault, "manual-2026-05-20-10-00-00")
    assert isinstance(preview, RestorePreview)
    assert "wiki/a.md" in preview.will_create
    assert preview.will_delete == []
    assert preview.will_overwrite == []


def test_preview_will_overwrite(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _make_page(vault / "wiki" / "a.md", "old content")
    snap = _create_snap(vault, "manual-2026-05-20-10-00-00")
    # Change file after snapshot
    (vault / "wiki" / "a.md").write_text("new content", encoding="utf-8")
    preview = compute_restore_preview(vault, "manual-2026-05-20-10-00-00")
    assert "wiki/a.md" in preview.will_overwrite
    assert preview.will_create == []


def test_preview_unchanged(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _make_page(vault / "wiki" / "a.md", "same content")
    _create_snap(vault, "manual-2026-05-20-10-00-00")
    preview = compute_restore_preview(vault, "manual-2026-05-20-10-00-00")
    assert preview.unchanged_count == 1
    assert preview.will_overwrite == []
    assert preview.will_create == []


def test_preview_will_delete(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _create_snap(vault, "manual-2026-05-20-10-00-00")
    # Add file to vault after snapshot — restoring would delete it
    _make_page(vault / "wiki" / "orphan.md", "orphan")
    preview = compute_restore_preview(vault, "manual-2026-05-20-10-00-00")
    assert "wiki/orphan.md" in preview.will_delete


def test_preview_truncated(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    for i in range(30):
        _make_page(vault / "wiki" / f"p{i}.md", f"body{i}")
    _create_snap(vault, "manual-2026-05-20-10-00-00")
    # Remove all vault files so all 30 will be in will_create
    shutil.rmtree(vault / "wiki")
    preview = compute_restore_preview(vault, "manual-2026-05-20-10-00-00", sample_limit=5)
    assert preview.truncated is True
    assert len(preview.will_create) <= 5


def test_preview_snapshot_not_found(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(FileNotFoundError):
        compute_restore_preview(vault, "nonexistent")


def test_preview_snapshot_kind_extracted(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _create_snap(vault, "manual-2026-05-20-10-00-00")
    preview = compute_restore_preview(vault, "manual-2026-05-20-10-00-00")
    assert preview.snapshot_kind == "manual"
    assert preview.snapshot_name == "manual-2026-05-20-10-00-00"
