import json
from pathlib import Path

from claude_mnemos.core.trash import (
    TrashMetadata,
    list_trash,
    read_metadata,
)


def _make_trash_dir(
    vault: Path,
    name: str,
    *,
    metadata: dict | None,
    page_basename: str = "foo.md",
    page_content: str = "# foo",
) -> Path:
    d = vault / ".trash" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / page_basename).write_text(page_content, encoding="utf-8")
    (d / ".reason.txt").write_text("test trash entry", encoding="utf-8")
    if metadata is not None:
        (d / ".metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
    return d


def _meta(trash_id: str, original_path: str = "wiki/entities/foo.md") -> dict:
    return {
        "version": 1,
        "trash_id": trash_id,
        "original_path": original_path,
        "deleted_at": "2026-04-27T12:00:00+00:00",
        "operation_id": "op-1",
        "operation_type": "manual_delete",
    }


def test_list_empty(tmp_path: Path):
    assert list_trash(tmp_path) == []


def test_list_returns_entries_with_metadata(tmp_path: Path):
    _make_trash_dir(
        tmp_path, "deleted-foo-2026-04-27-12-00-00-abc12345",
        metadata=_meta("deleted-foo-2026-04-27-12-00-00-abc12345"),
    )
    entries = list_trash(tmp_path)
    assert len(entries) == 1
    assert entries[0].trash_id.startswith("deleted-foo-")
    assert entries[0].original_path == "wiki/entities/foo.md"
    assert entries[0].restorable is True
    assert entries[0].restore_blocked_reason is None


def test_list_marks_missing_metadata_unrestorable(tmp_path: Path):
    _make_trash_dir(tmp_path, "deleted-bar-old-format", metadata=None)
    entries = list_trash(tmp_path)
    assert len(entries) == 1
    assert entries[0].restorable is False
    assert "metadata" in (entries[0].restore_blocked_reason or "").lower()


def test_list_marks_missing_basename_unrestorable(tmp_path: Path):
    d = tmp_path / ".trash" / "deleted-bar-2026-04-27-12-00-00-aaaaaaaa"
    d.mkdir(parents=True)
    # Skip writing the page basename
    (d / ".reason.txt").write_text("r", encoding="utf-8")
    (d / ".metadata.json").write_text(
        json.dumps(_meta("deleted-bar-2026-04-27-12-00-00-aaaaaaaa", "wiki/entities/bar.md")),
        encoding="utf-8",
    )
    entries = list_trash(tmp_path)
    assert len(entries) == 1
    assert entries[0].restorable is False


def test_list_skips_unknown_prefix(tmp_path: Path):
    d = tmp_path / ".trash" / "weird-thing"
    d.mkdir(parents=True)
    (d / "x.md").write_text("x", encoding="utf-8")
    entries = list_trash(tmp_path)
    # 'weird-thing' doesn't start with deleted-/rejected- — list it but mark non-restorable
    # Decision per design §3.10: include all subdirs; restorable=False for unknown prefix
    assert len(entries) == 1
    assert entries[0].restorable is False


def test_list_sorted_desc_by_deleted_at(tmp_path: Path):
    a_id = "deleted-a-2026-04-27-10-00-00-aaaaaaaa"
    b_id = "deleted-b-2026-04-27-12-00-00-bbbbbbbb"
    _make_trash_dir(
        tmp_path, a_id,
        metadata={**_meta(a_id), "deleted_at": "2026-04-27T10:00:00+00:00"},
    )
    _make_trash_dir(
        tmp_path, b_id,
        metadata={**_meta(b_id), "deleted_at": "2026-04-27T12:00:00+00:00"},
    )
    entries = list_trash(tmp_path)
    assert [e.trash_id for e in entries] == [
        "deleted-b-2026-04-27-12-00-00-bbbbbbbb",
        "deleted-a-2026-04-27-10-00-00-aaaaaaaa",
    ]


def test_read_metadata_missing(tmp_path: Path):
    d = tmp_path / ".trash" / "deleted-x-2026-04-27-12-00-00-zzzzzzzz"
    d.mkdir(parents=True)
    assert read_metadata(d) is None


def test_read_metadata_invalid_json(tmp_path: Path):
    d = tmp_path / ".trash" / "deleted-x-2026-04-27-12-00-00-zzzzzzzz"
    d.mkdir(parents=True)
    (d / ".metadata.json").write_text("not json", encoding="utf-8")
    assert read_metadata(d) is None  # tolerate, return None


def test_read_metadata_valid(tmp_path: Path):
    d = tmp_path / ".trash" / "deleted-x-2026-04-27-12-00-00-zzzzzzzz"
    d.mkdir(parents=True)
    (d / ".metadata.json").write_text(
        json.dumps(_meta("deleted-x-2026-04-27-12-00-00-zzzzzzzz")),
        encoding="utf-8",
    )
    meta = read_metadata(d)
    assert meta is not None
    assert isinstance(meta, TrashMetadata)
    assert meta.original_path == "wiki/entities/foo.md"
