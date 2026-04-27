from pathlib import Path

import pytest

from claude_mnemos.lint.utils import build_slug_index, levenshtein_distance


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("", "", 0),
        ("a", "a", 0),
        ("a", "b", 1),
        ("kitten", "sitting", 3),
        ("foo", "foo-bar", 4),
        ("file-lock-bug", "file-lock-bub", 1),
    ],
)
def test_levenshtein(a, b, expected):
    assert levenshtein_distance(a, b) == expected


def test_levenshtein_symmetric():
    assert levenshtein_distance("abc", "xyz") == levenshtein_distance("xyz", "abc")


def _seed(vault: Path, rel: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n"
        "title: T\n"
        "type: entity\n"
        "created: 2026-04-26\n"
        "updated: 2026-04-26\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    return p


def test_slug_index_basic(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md")
    _seed(tmp_path, "wiki/concepts/bar.md")
    _seed(tmp_path, "wiki/sources/baz.md")
    index = build_slug_index(tmp_path)
    assert "foo" in index
    assert "bar" in index
    assert "baz" in index
    assert index["foo"].name == "foo.md"


def test_slug_index_skips_dotfiles(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md")
    _seed(tmp_path, ".staging/op-1/wiki/entities/foo.md")
    index = build_slug_index(tmp_path)
    assert len(index) == 1


def test_slug_index_priority_entity_over_concept(tmp_path: Path):
    _seed(tmp_path, "wiki/concepts/foo.md")
    _seed(tmp_path, "wiki/entities/foo.md")
    index = build_slug_index(tmp_path)
    assert "entities" in str(index["foo"])
