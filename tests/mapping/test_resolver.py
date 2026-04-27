from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from claude_mnemos.mapping.resolver import ProjectResolver, ResolverAmbiguityError
from claude_mnemos.state.projects import (
    HOME_CONFIG_DIRNAME,
    PROJECT_MAP_FILENAME,
    ProjectMap,
    ProjectMapEntry,
)


def _seed_map(home: Path, entries: list[ProjectMapEntry]) -> Path:
    f = home / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME
    f.parent.mkdir(parents=True, exist_ok=True)
    pm = ProjectMap(projects=entries)
    f.write_text(json.dumps(pm.model_dump(mode="json")))
    return f


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_resolve_by_name_hit(tmp_path: Path):
    _seed_map(tmp_path, [
        ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=[]),
    ])
    r = ProjectResolver()
    e = r.resolve_by_name("x")
    assert e is not None and e.name == "x"


def test_resolve_by_name_miss(tmp_path: Path):
    _seed_map(tmp_path, [])
    r = ProjectResolver()
    assert r.resolve_by_name("nope") is None


def test_resolve_by_vault_hit(tmp_path: Path):
    vault = tmp_path / "v"
    vault.mkdir()
    _seed_map(tmp_path, [
        ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]),
    ])
    r = ProjectResolver()
    e = r.resolve_by_vault(vault)
    assert e is not None and e.name == "x"


def test_resolve_by_vault_miss(tmp_path: Path):
    _seed_map(tmp_path, [])
    r = ProjectResolver()
    assert r.resolve_by_vault(tmp_path / "x") is None


def test_resolve_by_cwd_no_match_returns_none(tmp_path: Path):
    _seed_map(tmp_path, [
        ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=["~/code/x*"]),
    ])
    r = ProjectResolver()
    assert r.resolve_by_cwd(tmp_path / "elsewhere") is None


def test_resolve_by_cwd_exact_glob_match(tmp_path: Path):
    cwd = tmp_path / "code" / "foo"
    cwd.mkdir(parents=True)
    _seed_map(tmp_path, [
        ProjectMapEntry(name="foo", vault_root=tmp_path / "v", cwd_patterns=[str(cwd)]),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(cwd)
    assert e is not None and e.name == "foo"


def test_resolve_by_cwd_wildcard(tmp_path: Path):
    project_dir = tmp_path / "code" / "foo-experiments"
    project_dir.mkdir(parents=True)
    _seed_map(tmp_path, [
        ProjectMapEntry(
            name="foo", vault_root=tmp_path / "v",
            cwd_patterns=[str(tmp_path / "code" / "foo*")],
        ),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(project_dir)
    assert e is not None and e.name == "foo"


def test_resolve_by_cwd_most_specific_wins(tmp_path: Path):
    target = tmp_path / "code" / "foo"
    target.mkdir(parents=True)
    _seed_map(tmp_path, [
        ProjectMapEntry(
            name="catchall", vault_root=tmp_path / "vall",
            cwd_patterns=[str(tmp_path / "code" / "*")],
        ),
        ProjectMapEntry(
            name="specific", vault_root=tmp_path / "vfoo",
            cwd_patterns=[str(target)],
        ),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(target)
    assert e is not None and e.name == "specific"


def test_resolve_by_cwd_tie_raises(tmp_path: Path):
    cwd = tmp_path / "code" / "x"
    cwd.mkdir(parents=True)
    # Two distinct entries with literal-equal patterns force a same-length tie.
    _seed_map(tmp_path, [
        ProjectMapEntry(name="a", vault_root=tmp_path / "va", cwd_patterns=[str(cwd)]),
        ProjectMapEntry(name="b", vault_root=tmp_path / "vb", cwd_patterns=[str(cwd)]),
    ])
    r = ProjectResolver()
    with pytest.raises(ResolverAmbiguityError):
        r.resolve_by_cwd(cwd)


def test_resolve_by_cwd_expanduser(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cwd = tmp_path / "x"
    cwd.mkdir()
    _seed_map(tmp_path, [
        ProjectMapEntry(name="x", vault_root=tmp_path / "v", cwd_patterns=["~/x"]),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(cwd)
    assert e is not None and e.name == "x"


def test_resolve_by_cwd_windows_case_insensitive(tmp_path: Path):
    if sys.platform != "win32":
        pytest.skip("Windows-only behavior")
    cwd = tmp_path / "Code" / "Foo"
    cwd.mkdir(parents=True)
    _seed_map(tmp_path, [
        ProjectMapEntry(
            name="foo", vault_root=tmp_path / "v",
            cwd_patterns=[str(tmp_path / "code" / "foo")],
        ),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(cwd)
    assert e is not None and e.name == "foo"


def test_resolve_by_cwd_handles_corrupt_via_exception(tmp_path: Path):
    f = tmp_path / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME
    f.parent.mkdir(parents=True)
    f.write_text("{invalid")
    r = ProjectResolver()
    from claude_mnemos.state.projects import ProjectMapCorruptError
    with pytest.raises(ProjectMapCorruptError):
        r.resolve_by_cwd(tmp_path / "x")


def test_list_all(tmp_path: Path):
    _seed_map(tmp_path, [
        ProjectMapEntry(name="a", vault_root=tmp_path / "va", cwd_patterns=[]),
        ProjectMapEntry(name="b", vault_root=tmp_path / "vb", cwd_patterns=[]),
    ])
    r = ProjectResolver()
    names = sorted(e.name for e in r.list_all())
    assert names == ["a", "b"]
