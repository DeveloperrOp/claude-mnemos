from pathlib import Path

import pytest

from claude_mnemos.lint.utils import (
    build_resolvable_targets,
    build_slug_index,
    levenshtein_distance,
)


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


# --- build_resolvable_targets ---


def test_resolvable_targets_collects_wiki_stems(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md")
    _seed(tmp_path, "wiki/concepts/bar.md")
    _seed(tmp_path, "wiki/sources/baz.md")
    targets = build_resolvable_targets(tmp_path)
    assert {"foo", "bar", "baz"} <= targets


def test_resolvable_targets_includes_raw_chats(tmp_path: Path):
    _seed(tmp_path, "raw/chats/00811ba3-b79f-417e-9ebe-6d518e91e481.md")
    targets = build_resolvable_targets(tmp_path)
    assert "00811ba3-b79f-417e-9ebe-6d518e91e481" in targets


def test_resolvable_targets_skips_dot_dirs(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md")
    _seed(tmp_path, ".staging/op-1/wiki/entities/hidden.md")
    _seed(tmp_path, ".backups/old.md")
    _seed(tmp_path, ".trash/gone.md")
    targets = build_resolvable_targets(tmp_path)
    assert "foo" in targets
    assert "hidden" not in targets
    assert "old" not in targets
    assert "gone" not in targets


def test_resolvable_targets_recursive_anywhere(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/deeply/nested/thing.md")
    targets = build_resolvable_targets(tmp_path)
    assert "thing" in targets
