from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.state.projects import (
    HOME_CONFIG_DIRNAME,
    PROJECT_MAP_FILENAME,
    ProjectMap,
    ProjectMapCorruptError,
    ProjectMapEntry,
    ProjectNameConflictError,
    ProjectNotFoundError,
    ProjectStore,
)


def _project_map_path(home: Path) -> Path:
    return home / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME


def test_project_map_entry_valid_name():
    e = ProjectMapEntry(name="claude-mnemos", vault_root=Path("/v"), cwd_patterns=["~/code/cm*"])
    assert e.name == "claude-mnemos"


@pytest.mark.parametrize("bad", ["", "A-B", "_x", "1@", "имя", "x" * 65])
def test_project_map_entry_rejects_bad_name(bad):
    with pytest.raises(ValidationError):
        ProjectMapEntry(name=bad, vault_root=Path("/v"), cwd_patterns=[])


def test_project_map_entry_rejects_extra_field():
    with pytest.raises(ValidationError):
        ProjectMapEntry(
            name="ok", vault_root=Path("/v"), cwd_patterns=[], stranger="x",
        )


def test_project_map_default_empty():
    pm = ProjectMap()
    assert pm.version == 1
    assert pm.projects == []


def test_project_map_round_trip(tmp_path: Path):
    pm = ProjectMap(projects=[
        ProjectMapEntry(name="a", vault_root=tmp_path / "va", cwd_patterns=["~/a*"]),
    ])
    p = tmp_path / "project-map.json"
    p.write_text(json.dumps(pm.model_dump(mode="json")))
    loaded = ProjectMap.model_validate_json(p.read_text())
    assert loaded.projects[0].name == "a"


def test_store_add_creates_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    store = ProjectStore()
    e = ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=["~/x*"])
    store.add(e)
    f = _project_map_path(tmp_path)
    assert f.is_file()
    data = json.loads(f.read_text())
    assert data["projects"][0]["name"] == "x"


def test_store_add_duplicate_name_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    e = ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=[])
    store.add(e)
    with pytest.raises(ProjectNameConflictError):
        store.add(e)


def test_store_get_missing_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    with pytest.raises(ProjectNotFoundError):
        store.get("nope")


def test_store_update_partial(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    e = ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=["~/x"])
    store.add(e)
    updated = store.update("x", cwd_patterns=["~/y"])
    assert updated.cwd_patterns == ["~/y"]
    assert updated.vault_root == tmp_path / "vx"


def test_store_remove_removes_entry(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    store.add(ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=[]))
    store.remove("x")
    with pytest.raises(ProjectNotFoundError):
        store.get("x")


def test_store_remove_cleans_settings_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    store.add(ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=[]))
    settings_dir = tmp_path / HOME_CONFIG_DIRNAME / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "x.json"
    settings_file.write_text("{}")
    store.remove("x")
    assert not settings_file.exists()


def test_corrupt_json_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    f = _project_map_path(tmp_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json")
    store = ProjectStore()
    with pytest.raises(ProjectMapCorruptError):
        store.list_all()


def test_missing_file_returns_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    assert store.list_all() == []


def test_two_stores_share_lock(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    s1 = ProjectStore()
    s2 = ProjectStore()
    assert s1._lock is s2._lock
