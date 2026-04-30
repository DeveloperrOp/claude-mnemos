from __future__ import annotations

from pathlib import Path

from claude_mnemos.state.projects import ProjectMap, ProjectMapEntry


def test_default_display_name_is_none() -> None:
    entry = ProjectMapEntry(name="x", vault_root=Path("/tmp/x"))
    assert entry.display_name is None


def test_display_name_accepts_unicode() -> None:
    entry = ProjectMapEntry(
        name="x",
        display_name="Конструктор сайтов",
        vault_root=Path("/tmp/x"),
    )
    assert entry.display_name == "Конструктор сайтов"


def test_load_legacy_json_without_display_name() -> None:
    """Existing project-map.json files (no display_name key) must load."""
    raw = {
        "version": 1,
        "projects": [
            {"name": "test-cli", "vault_root": "/tmp/test-cli", "cwd_patterns": []}
        ],
    }
    parsed = ProjectMap.model_validate(raw)
    assert len(parsed.projects) == 1
    assert parsed.projects[0].display_name is None
    assert parsed.projects[0].name == "test-cli"


def test_load_json_with_display_name() -> None:
    raw = {
        "version": 1,
        "projects": [
            {
                "name": "test-cli",
                "display_name": "Test Project",
                "vault_root": "/tmp/test-cli",
                "cwd_patterns": [],
            }
        ],
    }
    parsed = ProjectMap.model_validate(raw)
    assert parsed.projects[0].display_name == "Test Project"


def test_serialize_includes_display_name_when_set() -> None:
    entry = ProjectMapEntry(
        name="x",
        display_name="X Project",
        vault_root=Path("/tmp/x"),
    )
    data = entry.model_dump(mode="json")
    assert data["display_name"] == "X Project"


def test_serialize_includes_none_display_name() -> None:
    """Pydantic by default serialises None fields. Verify behaviour explicit."""
    entry = ProjectMapEntry(name="x", vault_root=Path("/tmp/x"))
    data = entry.model_dump(mode="json")
    assert "display_name" in data
    assert data["display_name"] is None


def test_update_clears_display_name_with_empty_string(tmp_path: Path) -> None:
    """ProjectStore.update with display_name="" clears the field back to None."""
    from claude_mnemos.state.projects import ProjectStore

    pm_path = tmp_path / "project-map.json"
    store = ProjectStore(map_path=pm_path)
    store.add(ProjectMapEntry(
        name="x",
        vault_root=tmp_path / "vault",
        display_name="Original Name",
    ))
    assert store.get("x").display_name == "Original Name"
    store.update("x", display_name="")
    assert store.get("x").display_name is None


def test_update_keeps_display_name_when_none_passed(tmp_path: Path) -> None:
    """ProjectStore.update with display_name=None leaves field unchanged."""
    from claude_mnemos.state.projects import ProjectStore

    pm_path = tmp_path / "project-map.json"
    store = ProjectStore(map_path=pm_path)
    store.add(ProjectMapEntry(
        name="x",
        vault_root=tmp_path / "vault",
        display_name="Original Name",
    ))
    store.update("x", vault_root=tmp_path / "v2")
    assert store.get("x").display_name == "Original Name"
