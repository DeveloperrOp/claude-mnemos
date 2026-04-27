from pathlib import Path

import pytest

from claude_mnemos.core.pages import PageRefError, page_ref_to_path


def _seed(vault: Path, rel: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: T\ntype: entity\ncreated: 2026-04-26\nupdated: 2026-04-26\n---\nbody",
        encoding="utf-8",
    )
    return p


def test_resolve_bare_slug_entity(tmp_path: Path):
    p = _seed(tmp_path, "wiki/entities/foo.md")
    assert page_ref_to_path(tmp_path, "foo") == p


def test_resolve_slug_prefers_entity_over_concept(tmp_path: Path):
    _seed(tmp_path, "wiki/concepts/foo.md")
    entity = _seed(tmp_path, "wiki/entities/foo.md")
    assert page_ref_to_path(tmp_path, "foo") == entity


def test_resolve_relative_with_md(tmp_path: Path):
    p = _seed(tmp_path, "wiki/entities/foo.md")
    assert page_ref_to_path(tmp_path, "wiki/entities/foo.md") == p


def test_resolve_relative_without_md(tmp_path: Path):
    p = _seed(tmp_path, "wiki/entities/foo.md")
    assert page_ref_to_path(tmp_path, "wiki/entities/foo") == p


def test_unknown_slug_raises(tmp_path: Path):
    with pytest.raises(PageRefError):
        page_ref_to_path(tmp_path, "nonexistent")


def test_traversal_rejected(tmp_path: Path):
    with pytest.raises(PageRefError):
        page_ref_to_path(tmp_path, "../../etc/passwd")


def test_absolute_path_rejected(tmp_path: Path):
    with pytest.raises(PageRefError):
        page_ref_to_path(tmp_path, "/etc/passwd")
