from pathlib import Path

from claude_mnemos.core.wikilinks import (
    Wikilink,
    extract_wikilinks,
    find_files_referencing,
    rewrite_wikilinks,
)


def test_extract_empty():
    assert extract_wikilinks("") == []


def test_extract_no_links():
    assert extract_wikilinks("Just text, no wikilinks here.") == []


def test_extract_single():
    assert extract_wikilinks("Hello [[foo]] world") == [Wikilink(target="foo")]


def test_extract_multiple():
    text = "Both [[a]] and [[b]] are linked."
    assert extract_wikilinks(text) == [Wikilink(target="a"), Wikilink(target="b")]


def test_extract_with_alias():
    assert extract_wikilinks("[[foo|Foo Display]]") == [
        Wikilink(target="foo", alias="Foo Display")
    ]


def test_extract_mixed_alias_and_plain():
    text = "[[foo]] and [[bar|Bar]] but not [text]"
    assert extract_wikilinks(text) == [
        Wikilink(target="foo"),
        Wikilink(target="bar", alias="Bar"),
    ]


def test_extract_ignores_single_brackets():
    """`[text]` (single brackets) is not a wikilink."""
    assert extract_wikilinks("This is [text] not a [[wikilink]] here") == [
        Wikilink(target="wikilink")
    ]


def test_extract_strips_whitespace_inside_link():
    assert extract_wikilinks("[[ foo ]]") == [Wikilink(target="foo")]


def test_rewrite_no_mapping_returns_unchanged():
    text = "Hello [[foo]]"
    assert rewrite_wikilinks(text, {}) == text


def test_rewrite_simple():
    assert rewrite_wikilinks("[[old]]", {"old": "new"}) == "[[new]]"


def test_rewrite_preserves_alias():
    assert (
        rewrite_wikilinks("[[old|Display]]", {"old": "new"}) == "[[new|Display]]"
    )


def test_rewrite_preserves_surrounding_text():
    assert (
        rewrite_wikilinks("foo [[old]] bar", {"old": "new"})
        == "foo [[new]] bar"
    )


def test_rewrite_no_match():
    assert rewrite_wikilinks("[[other]]", {"old": "new"}) == "[[other]]"


def test_rewrite_multiple_partial():
    text = "[[a]] and [[b]] and [[c]]"
    out = rewrite_wikilinks(text, {"a": "x", "c": "z"})
    assert out == "[[x]] and [[b]] and [[z]]"


def test_rewrite_chain_ignored():
    """rewrite is single-pass — `b → c` doesn't apply to result of `a → b`."""
    text = "[[a]]"
    out = rewrite_wikilinks(text, {"a": "b", "b": "c"})
    assert out == "[[b]]"


def test_find_files_empty_vault(tmp_path: Path):
    assert find_files_referencing(tmp_path, "foo") == []


def test_find_files_two_referencing(tmp_path: Path):
    (tmp_path / "wiki/entities").mkdir(parents=True)
    (tmp_path / "wiki/entities/a.md").write_text("link to [[foo]]", encoding="utf-8")
    (tmp_path / "wiki/concepts").mkdir(parents=True)
    (tmp_path / "wiki/concepts/b.md").write_text("[[foo|alias]] here", encoding="utf-8")
    (tmp_path / "wiki/sources").mkdir(parents=True)
    (tmp_path / "wiki/sources/c.md").write_text("nothing", encoding="utf-8")
    matches = find_files_referencing(tmp_path, "foo")
    names = sorted(p.name for p in matches)
    assert names == ["a.md", "b.md"]


def test_find_files_excludes_self(tmp_path: Path):
    (tmp_path / "wiki/entities").mkdir(parents=True)
    self_page = tmp_path / "wiki/entities/foo.md"
    self_page.write_text("self [[foo]] reference", encoding="utf-8")
    (tmp_path / "wiki/entities/other.md").write_text("[[foo]]", encoding="utf-8")
    matches = find_files_referencing(tmp_path, "foo", exclude={self_page})
    names = [p.name for p in matches]
    assert names == ["other.md"]


def test_find_files_searches_raw_chats(tmp_path: Path):
    (tmp_path / "raw/chats").mkdir(parents=True)
    (tmp_path / "raw/chats/2026-01-01-x.md").write_text("[[foo]]", encoding="utf-8")
    matches = find_files_referencing(tmp_path, "foo")
    assert len(matches) == 1


def test_find_files_no_matches(tmp_path: Path):
    (tmp_path / "wiki/entities").mkdir(parents=True)
    (tmp_path / "wiki/entities/a.md").write_text("nothing", encoding="utf-8")
    assert find_files_referencing(tmp_path, "foo") == []
