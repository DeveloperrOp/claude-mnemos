from pathlib import Path

import pytest

from claude_mnemos.mcp.errors import PageRefError
from claude_mnemos.mcp.read_tools.pages import (
    list_pages,
    read_page,
    search_pages,
)


def _populate(vault: Path) -> None:
    for sub in ("wiki/entities", "wiki/concepts", "wiki/sources", "raw/chats"):
        (vault / sub).mkdir(parents=True, exist_ok=True)


def _write_page(
    vault: Path,
    rel: str,
    *,
    title: str,
    page_type: str,
    flavor: list[str] | None = None,
    body: str = "Body text\n",
) -> None:
    fm_lines = [
        "---",
        f"title: {title}",
        f"type: {page_type}",
    ]
    if flavor is not None:
        fm_lines.append(f"flavor: [{', '.join(flavor)}]")
    fm_lines.append("---")
    text = "\n".join(fm_lines) + "\n" + body
    (vault / rel).write_text(text, encoding="utf-8")


def test_list_pages_empty(tmp_path: Path):
    _populate(tmp_path)
    assert list_pages(tmp_path) == []


def test_list_pages_returns_three(tmp_path: Path):
    _populate(tmp_path)
    _write_page(tmp_path, "wiki/entities/foo.md", title="Foo", page_type="entity")
    _write_page(tmp_path, "wiki/concepts/bar.md", title="Bar", page_type="concept")
    _write_page(tmp_path, "wiki/sources/baz.md", title="Baz", page_type="source")
    items = list_pages(tmp_path)
    assert len(items) == 3
    titles = {i["title"] for i in items}
    assert titles == {"Foo", "Bar", "Baz"}


def test_list_pages_filter_by_type(tmp_path: Path):
    _populate(tmp_path)
    _write_page(tmp_path, "wiki/entities/foo.md", title="Foo", page_type="entity")
    _write_page(tmp_path, "wiki/concepts/bar.md", title="Bar", page_type="concept")
    items = list_pages(tmp_path, type="entity")
    assert len(items) == 1
    assert items[0]["title"] == "Foo"


def test_list_pages_filter_by_flavor(tmp_path: Path):
    _populate(tmp_path)
    _write_page(
        tmp_path,
        "wiki/entities/foo.md",
        title="Foo",
        page_type="entity",
        flavor=["pattern"],
    )
    _write_page(
        tmp_path,
        "wiki/entities/bar.md",
        title="Bar",
        page_type="entity",
        flavor=["mistake"],
    )
    items = list_pages(tmp_path, flavor="pattern")
    assert len(items) == 1
    assert items[0]["title"] == "Foo"


def test_list_pages_unknown_type(tmp_path: Path):
    _populate(tmp_path)
    _write_page(tmp_path, "wiki/entities/foo.md", title="Foo", page_type="entity")
    assert list_pages(tmp_path, type="rubbish") == []


def test_list_pages_limit(tmp_path: Path):
    _populate(tmp_path)
    for i in range(5):
        _write_page(
            tmp_path, f"wiki/entities/f{i}.md", title=f"F{i}", page_type="entity"
        )
    items = list_pages(tmp_path, limit=2)
    assert len(items) == 2


def test_read_page_with_frontmatter(tmp_path: Path):
    _populate(tmp_path)
    _write_page(
        tmp_path,
        "wiki/entities/foo.md",
        title="Foo",
        page_type="entity",
        body="The body.\n",
    )
    page = read_page(tmp_path, "foo")
    assert page["path"] == "wiki/entities/foo.md"
    assert page["frontmatter"]["title"] == "Foo"
    assert "The body." in page["body"]


def test_read_page_no_frontmatter(tmp_path: Path):
    _populate(tmp_path)
    (tmp_path / "raw/chats/x.md").write_text("Just body\n", encoding="utf-8")
    page = read_page(tmp_path, "raw/chats/x.md")
    assert page["frontmatter"] == {}
    assert page["body"].startswith("Just body")


def test_read_page_traversal(tmp_path: Path):
    _populate(tmp_path)
    with pytest.raises(PageRefError):
        read_page(tmp_path, "../etc/passwd")


def test_read_page_not_found(tmp_path: Path):
    _populate(tmp_path)
    with pytest.raises(PageRefError):
        read_page(tmp_path, "nope")


def test_search_pages_substring_in_body(tmp_path: Path):
    _populate(tmp_path)
    _write_page(
        tmp_path,
        "wiki/entities/foo.md",
        title="Foo",
        page_type="entity",
        body="Mentions FastAPI here.",
    )
    matches = search_pages(tmp_path, "fastapi")
    assert len(matches) == 1
    assert matches[0]["matched_in_body"] is True
    assert "FastAPI" in matches[0]["snippet"]


def test_search_pages_substring_in_name(tmp_path: Path):
    _populate(tmp_path)
    _write_page(
        tmp_path,
        "wiki/entities/fastapi.md",
        title="FastAPI",
        page_type="entity",
        body="Body.",
    )
    matches = search_pages(tmp_path, "fastapi")
    assert len(matches) == 1
    assert matches[0]["matched_in_name"] is True


def test_search_pages_case_insensitive(tmp_path: Path):
    _populate(tmp_path)
    _write_page(
        tmp_path,
        "wiki/entities/foo.md",
        title="Foo",
        page_type="entity",
        body="lowercase fastapi mention",
    )
    matches = search_pages(tmp_path, "FASTAPI")
    assert len(matches) == 1


def test_search_pages_limit(tmp_path: Path):
    _populate(tmp_path)
    for i in range(5):
        _write_page(
            tmp_path,
            f"wiki/entities/p{i}.md",
            title=f"P{i}",
            page_type="entity",
            body="needle",
        )
    matches = search_pages(tmp_path, "needle", limit=2)
    assert len(matches) == 2


def test_search_pages_no_matches(tmp_path: Path):
    _populate(tmp_path)
    _write_page(tmp_path, "wiki/entities/foo.md", title="Foo", page_type="entity")
    assert search_pages(tmp_path, "xyzqwer") == []


def test_search_pages_empty_query(tmp_path: Path):
    _populate(tmp_path)
    _write_page(tmp_path, "wiki/entities/foo.md", title="Foo", page_type="entity")
    assert search_pages(tmp_path, "") == []
