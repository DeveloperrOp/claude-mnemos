from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.state.settings import (
    AutoIngestSettings,
    GlobalSettings,
    IngestOverrides,
    LifecycleSettings,
    LintSettings,
    OntologySettings,
    ProjectSettings,
    PromptsSettings,
    SettingsCorruptError,
    SettingsStore,
    SnapshotsSettings,
    TelemetrySettings,
    WatchdogSettings,
    deep_merge,
    get_by_dot_path,
    patch_dict_for_dot_path,
)


def test_project_settings_defaults():
    s = ProjectSettings()
    assert s.version == 1
    assert s.locale is None
    assert s.auto_ingest.enabled is True
    assert s.auto_ingest.mode == "auto"
    assert s.lint.enabled_rules is None
    assert s.snapshots.daily_enabled is True
    assert s.snapshots.retention_days == 180
    assert s.lifecycle.auto_stale_days == 90
    assert s.telemetry.opt_in is False


def test_subgroup_models_construct_with_defaults():
    # Smoke test that every spec §12.8 subgroup is independently usable.
    assert isinstance(s := ProjectSettings(), ProjectSettings)
    assert isinstance(s.auto_ingest, AutoIngestSettings)
    assert isinstance(s.lint, LintSettings)
    assert isinstance(s.ontology, OntologySettings)
    assert isinstance(s.watchdog, WatchdogSettings)
    assert isinstance(s.snapshots, SnapshotsSettings)
    assert isinstance(s.lifecycle, LifecycleSettings)
    assert isinstance(s.prompts, PromptsSettings)
    assert isinstance(s.telemetry, TelemetrySettings)
    assert isinstance(s.ingest, IngestOverrides)


def test_global_settings_defaults():
    g = GlobalSettings()
    assert g.locale == "uk"
    assert g.daemon_port == 5757
    assert g.default_model == "claude-sonnet-4-6"


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        ProjectSettings.model_validate({"foo": "bar"})
    with pytest.raises(ValidationError):
        AutoIngestSettings(enabled=True, mode="auto", extra="x")


def test_round_trip_json():
    s = ProjectSettings(
        locale="ru",
        auto_ingest=AutoIngestSettings(enabled=False, mode="manual"),
    )
    js = s.model_dump_json()
    loaded = ProjectSettings.model_validate_json(js)
    assert loaded.auto_ingest.enabled is False
    assert loaded.locale == "ru"


def test_get_by_dot_path():
    s = ProjectSettings()
    assert get_by_dot_path(s, "lint.enabled_rules") is None
    assert get_by_dot_path(s, "snapshots.retention_days") == 180
    assert get_by_dot_path(s, "auto_ingest.mode") == "auto"
    assert get_by_dot_path(s, "lint") == s.lint


def test_get_by_dot_path_missing():
    s = ProjectSettings()
    with pytest.raises(AttributeError):
        get_by_dot_path(s, "nope")
    with pytest.raises(AttributeError):
        get_by_dot_path(s, "lint.no_such_field")


def test_patch_dict_for_dot_path_simple():
    assert patch_dict_for_dot_path("lint.schedule", "* * * * *") == {
        "lint": {"schedule": "* * * * *"}
    }


def test_patch_dict_for_dot_path_nested_three():
    assert patch_dict_for_dot_path("a.b.c", 42) == {"a": {"b": {"c": 42}}}


def test_deep_merge_basic():
    a = {"x": 1, "y": {"z": 2}}
    b = {"y": {"w": 3}}
    assert deep_merge(a, b) == {"x": 1, "y": {"z": 2, "w": 3}}


def test_deep_merge_overrides_scalar():
    a = {"x": {"y": 1}}
    b = {"x": {"y": 2}}
    assert deep_merge(a, b) == {"x": {"y": 2}}


def test_deep_merge_replaces_lists():
    a = {"x": [1, 2]}
    b = {"x": [3]}
    assert deep_merge(a, b) == {"x": [3]}


def test_settings_store_get_project_returns_defaults_if_missing(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    s = store.get_project("missing")
    assert s == ProjectSettings()


def test_settings_store_patch_project_persists(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    updated = store.patch_project("foo", {"auto_ingest": {"enabled": False}})
    assert updated.auto_ingest.enabled is False
    f = tmp_path / "settings" / "foo.json"
    assert f.is_file()
    data = json.loads(f.read_text())
    assert data["auto_ingest"]["enabled"] is False


def test_settings_store_patch_partial_preserves_others(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    store.patch_project("foo", {"snapshots": {"retention_days": 30}})
    updated = store.patch_project("foo", {"lint": {"autofix_on_save": True}})
    assert updated.snapshots.retention_days == 30
    assert updated.lint.autofix_on_save is True


def test_settings_store_patch_invalid_value_raises(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    with pytest.raises(ValidationError):
        store.patch_project("foo", {"snapshots": {"retention_days": -1}})


def test_settings_store_corrupt_file_raises(tmp_path: Path):
    f = tmp_path / "settings" / "bad.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json")
    store = SettingsStore(root=tmp_path)
    with pytest.raises(SettingsCorruptError):
        store.get_project("bad")


def test_settings_store_global_round_trip(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    g = store.patch_global({"locale": "en", "daemon_port": 6000})
    assert g.locale == "en"
    assert g.daemon_port == 6000
    g2 = store.get_global()
    assert g2.locale == "en"


def test_settings_store_global_defaults(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    assert store.get_global() == GlobalSettings()


def test_settings_store_reset_project(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    store.patch_project("foo", {"snapshots": {"retention_days": 5}})
    assert (tmp_path / "settings" / "foo.json").exists()
    store.reset_project("foo")
    assert not (tmp_path / "settings" / "foo.json").exists()
    assert store.get_project("foo") == ProjectSettings()


def test_settings_store_reset_global(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    store.patch_global({"locale": "en"})
    store.reset_global()
    assert store.get_global() == GlobalSettings()


def test_lock_key_stable_across_root_creation(tmp_path: Path):
    """SettingsStore lock must persist across root-directory creation."""
    nonexistent_root = tmp_path / "subdir" / "config"
    s_before = SettingsStore(root=nonexistent_root)
    lock_before = s_before._lock
    nonexistent_root.mkdir(parents=True)
    s_after = SettingsStore(root=nonexistent_root)
    assert s_after._lock is lock_before


def test_global_settings_ignores_unknown_fields(tmp_path, monkeypatch):
    """extra='ignore' must silently absorb β1-written files that contain primary_project."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    import json as _json
    from claude_mnemos.state.settings import GlobalSettings, SettingsStore, global_settings_path

    # Write a β1-style file with primary_project still present.
    path = global_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _json.dumps({"version": 1, "primary_project": "old-vault", "daemon_port": 5757}),
        encoding="utf-8",
    )
    g = SettingsStore().get_global()
    assert not hasattr(g, "primary_project")
    assert g.daemon_port == 5757
