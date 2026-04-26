from pathlib import Path

import pytest

from claude_mnemos.mcp.errors import PageRefError
from claude_mnemos.mcp.vault_access import resolve_page_path


def _populate(vault: Path) -> None:
    for sub in ("wiki/entities", "wiki/concepts", "wiki/sources", "raw/chats"):
        (vault / sub).mkdir(parents=True, exist_ok=True)


def test_resolve_with_md_suffix(tmp_path: Path):
    _populate(tmp_path)
    page = tmp_path / "wiki/entities/foo.md"
    page.write_text("body", encoding="utf-8")
    p = resolve_page_path(tmp_path, "wiki/entities/foo.md")
    assert p == page.resolve()


def test_resolve_bare_name_in_entities(tmp_path: Path):
    _populate(tmp_path)
    (tmp_path / "wiki/entities/foo.md").write_text("body", encoding="utf-8")
    p = resolve_page_path(tmp_path, "foo")
    assert p == (tmp_path / "wiki/entities/foo.md").resolve()


def test_resolve_bare_name_in_concepts(tmp_path: Path):
    _populate(tmp_path)
    (tmp_path / "wiki/concepts/bar.md").write_text("body", encoding="utf-8")
    p = resolve_page_path(tmp_path, "bar")
    assert p == (tmp_path / "wiki/concepts/bar.md").resolve()


def test_resolve_bare_name_in_raw_chats(tmp_path: Path):
    _populate(tmp_path)
    (tmp_path / "raw/chats/2026-04-26-x.md").write_text("body", encoding="utf-8")
    p = resolve_page_path(tmp_path, "2026-04-26-x")
    assert p == (tmp_path / "raw/chats/2026-04-26-x.md").resolve()


def test_resolve_ambiguous(tmp_path: Path):
    _populate(tmp_path)
    (tmp_path / "wiki/entities/dup.md").write_text("a", encoding="utf-8")
    (tmp_path / "wiki/concepts/dup.md").write_text("b", encoding="utf-8")
    with pytest.raises(PageRefError, match="ambiguous"):
        resolve_page_path(tmp_path, "dup")


def test_resolve_not_found(tmp_path: Path):
    _populate(tmp_path)
    with pytest.raises(PageRefError, match="not found"):
        resolve_page_path(tmp_path, "nope")


def test_resolve_traversal_rejected(tmp_path: Path):
    _populate(tmp_path)
    with pytest.raises(PageRefError, match="unsafe"):
        resolve_page_path(tmp_path, "../etc/passwd")


def test_resolve_absolute_path_rejected(tmp_path: Path):
    _populate(tmp_path)
    with pytest.raises(PageRefError, match="unsafe"):
        resolve_page_path(tmp_path, "/etc/passwd")


def test_resolve_empty_rejected(tmp_path: Path):
    _populate(tmp_path)
    with pytest.raises(PageRefError, match="unsafe"):
        resolve_page_path(tmp_path, "")


def test_resolve_md_suffix_not_found(tmp_path: Path):
    _populate(tmp_path)
    with pytest.raises(PageRefError, match="not found"):
        resolve_page_path(tmp_path, "wiki/entities/missing.md")
