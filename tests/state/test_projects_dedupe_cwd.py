from __future__ import annotations

from pathlib import Path

from claude_mnemos.state.projects import (
    ProjectMapEntry,
    ProjectStore,
    _dedupe_cwd_patterns,
)


def test_dedupe_empty():
    assert _dedupe_cwd_patterns([]) == []


def test_dedupe_single_plain_left_alone():
    assert _dedupe_cwd_patterns(["D:\\code\\foo"]) == ["D:\\code\\foo"]


def test_dedupe_single_recursive_left_alone():
    assert _dedupe_cwd_patterns(["D:\\code\\foo\\**"]) == ["D:\\code\\foo\\**"]


def test_dedupe_single_level1_left_alone():
    assert _dedupe_cwd_patterns(["D:\\code\\foo\\*"]) == ["D:\\code\\foo\\*"]


def test_dedupe_collapses_triplet_to_recursive_windows():
    # Legacy OnboardingWelcome.tsx produced this triplet for every project.
    triplet = [
        "D:\\code\\claude-mnemos",
        "D:\\code\\claude-mnemos\\*",
        "D:\\code\\claude-mnemos\\**",
    ]
    assert _dedupe_cwd_patterns(triplet) == ["D:\\code\\claude-mnemos\\**"]


def test_dedupe_collapses_triplet_to_recursive_posix():
    triplet = ["/home/x/code/foo", "/home/x/code/foo/*", "/home/x/code/foo/**"]
    assert _dedupe_cwd_patterns(triplet) == ["/home/x/code/foo/**"]


def test_dedupe_preserves_distinct_bases():
    patterns = [
        "D:\\code\\alpha\\**",
        "D:\\code\\beta",
    ]
    assert _dedupe_cwd_patterns(patterns) == patterns


def test_dedupe_collapses_pair_plain_plus_recursive():
    patterns = ["D:\\code\\foo", "D:\\code\\foo\\**"]
    assert _dedupe_cwd_patterns(patterns) == ["D:\\code\\foo\\**"]


def test_dedupe_drops_exact_duplicates():
    patterns = ["D:\\code\\foo\\**", "D:\\code\\foo\\**"]
    assert _dedupe_cwd_patterns(patterns) == ["D:\\code\\foo\\**"]


def test_project_store_canonicalizes_on_read(tmp_path: Path):
    map_path = tmp_path / "project-map.json"
    # Hand-write a triplet entry (mimics state on disk after pre-fix install).
    map_path.write_text(
        '{"version":1,"projects":[{'
        '"name":"foo",'
        '"display_name":null,'
        '"vault_root":"/v",'
        '"cwd_patterns":["D:\\\\code\\\\foo","D:\\\\code\\\\foo\\\\*","D:\\\\code\\\\foo\\\\**"]'
        "}]}",
        encoding="utf-8",
    )
    store = ProjectStore(map_path=map_path)
    entries = store.list_all()
    assert entries[0].cwd_patterns == ["D:\\code\\foo\\**"]

    # Reading by name also canonicalises.
    by_name = store.get("foo")
    assert by_name.cwd_patterns == ["D:\\code\\foo\\**"]

    # File on disk is NOT rewritten — canonicalisation is read-side only.
    raw = map_path.read_text(encoding="utf-8")
    assert "D:\\\\code\\\\foo\\\\*" in raw  # legacy data still present


def test_project_store_passthrough_when_already_canonical(tmp_path: Path):
    map_path = tmp_path / "project-map.json"
    entry = ProjectMapEntry(
        name="foo",
        vault_root=Path("/v"),
        cwd_patterns=["D:\\code\\foo\\**"],
    )
    store = ProjectStore(map_path=map_path)
    store.add(entry)
    assert store.list_all()[0].cwd_patterns == ["D:\\code\\foo\\**"]
