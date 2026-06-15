from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.state.settings import (
    AutoIngestDefaults,
    AutoIngestSettings,
    GlobalSettings,
    LintSettings,
    ProjectSettings,
    SettingsCorruptError,
    SettingsStore,
    SnapshotsSettings,
    deep_merge,
    get_by_dot_path,
    patch_dict_for_dot_path,
    resolve_ingest_flags,
)


def test_global_settings_default_max_input_tokens_is_800k():
    # Synced with claude_mnemos.config.DEFAULT_MAX_INPUT_TOKENS: 1M context
    # window means the old 150k cap was overcautious.
    assert GlobalSettings().default_max_input_tokens == 800_000


def test_project_settings_defaults():
    s = ProjectSettings()
    assert s.version == 1
    # v0.0.31: locale removed from ProjectSettings — it's global-only.
    assert not hasattr(s, "locale")
    # v0.0.10: auto_ingest fields default to None (= "inherit from
    # GlobalSettings.auto_ingest_defaults"), not True/auto.
    assert s.auto_ingest.dump_on_session_end is None
    assert s.auto_ingest.dump_stale_after_24h is None
    assert s.auto_ingest.extract_after_dump is None
    assert s.lint.enabled_rules is None
    assert s.snapshots.schedule == "daily"
    assert s.snapshots.retention_days == 180


def test_subgroup_models_construct_with_defaults():
    # Smoke test that every retained subgroup is independently usable.
    assert isinstance(s := ProjectSettings(), ProjectSettings)
    assert isinstance(s.auto_ingest, AutoIngestSettings)
    assert isinstance(s.lint, LintSettings)
    assert isinstance(s.snapshots, SnapshotsSettings)


def test_snapshots_schedule_migrates_legacy_daily_enabled_true():
    """v0.0.38- on-disk files store ``daily_enabled: true`` — must migrate to
    schedule="daily" without tripping extra='forbid'."""
    s = SnapshotsSettings.model_validate({"daily_enabled": True, "retention_days": 90})
    assert s.schedule == "daily"
    assert s.retention_days == 90
    assert not hasattr(s, "daily_enabled")


def test_snapshots_schedule_migrates_legacy_daily_enabled_false():
    s = SnapshotsSettings.model_validate({"daily_enabled": False})
    assert s.schedule == "off"


def test_snapshots_explicit_schedule_wins_over_legacy():
    """If both fields are present, the explicit schedule is authoritative."""
    s = SnapshotsSettings.model_validate(
        {"daily_enabled": True, "schedule": "weekly"}
    )
    assert s.schedule == "weekly"


def test_snapshots_schedule_rejects_unknown_value():
    with pytest.raises(ValidationError):
        SnapshotsSettings.model_validate({"schedule": "fortnightly"})


def test_snapshots_schedule_round_trip_through_store(tmp_path: Path):
    """A legacy file on disk loads and re-saves as the new schedule field."""
    store = SettingsStore(root=tmp_path)
    f = tmp_path / "settings" / "legacy.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps({"version": 1, "snapshots": {"daily_enabled": False, "retention_days": 30}}),
        encoding="utf-8",
    )
    loaded = store.get_project("legacy")
    assert loaded.snapshots.schedule == "off"
    assert loaded.snapshots.retention_days == 30
    # Patching writes the migrated field out; daily_enabled no longer present.
    updated = store.patch_project("legacy", {"snapshots": {"schedule": "monthly"}})
    assert updated.snapshots.schedule == "monthly"
    data = json.loads(f.read_text())
    assert data["snapshots"]["schedule"] == "monthly"
    assert "daily_enabled" not in data["snapshots"]


def test_global_settings_defaults():
    g = GlobalSettings()
    assert g.locale == "uk"
    assert g.daemon_port == 5757
    assert g.default_model == "claude-sonnet-4-6"


def test_project_settings_ignores_legacy_placebo_groups():
    """v0.0.11- on-disk JSON files contain watchdog/ontology/lifecycle/
    prompts/telemetry/ingest groups that v0.0.12 dropped. The model must
    silently absorb them on load (extra='ignore' at the top level)."""
    legacy = ProjectSettings.model_validate({
        "version": 1,
        "auto_ingest": {},
        "watchdog": {"mode": "merge"},
        "ontology": {"auto_mode": False},
        "lifecycle": {"auto_stale_days": 90},
        "prompts": {"custom_system_path": None},
        "telemetry": {"opt_in": False},
        "ingest": {"model": None},
    })
    assert legacy.version == 1
    assert not hasattr(legacy, "watchdog")
    assert not hasattr(legacy, "ontology")
    assert not hasattr(legacy, "lifecycle")
    assert not hasattr(legacy, "prompts")
    assert not hasattr(legacy, "telemetry")
    assert not hasattr(legacy, "ingest")


def test_extra_fields_ignored_at_top_level():
    # v0.0.12: ProjectSettings uses extra="ignore" so v0.0.11- on-disk
    # files with the dropped placebo subgroups (watchdog/ontology/
    # lifecycle/prompts/telemetry/ingest) load cleanly. See
    # ``test_project_settings_ignores_legacy_placebo_groups`` below.
    s = ProjectSettings.model_validate({"foo": "bar"})
    assert not hasattr(s, "foo")
    # Retained subgroups still validate strictly: an unknown field
    # inside e.g. ``snapshots`` raises (extra="forbid" on subgroups).
    with pytest.raises(ValidationError):
        ProjectSettings.model_validate({"snapshots": {"bogus": 1}})


def test_auto_ingest_settings_ignores_unknown_fields():
    """AutoIngestSettings uses extra="ignore" so on-disk JSON written by
    v0.0.9 (old `enabled`/`mode`) or v0.0.30 (per-project locale, legacy
    fields) loads cleanly without forcing the user to nuke ~/.claude-mnemos."""
    legacy = AutoIngestSettings.model_validate({
        "enabled": True, "mode": "auto", "garbage_field": "value",
    })
    assert not hasattr(legacy, "enabled")
    assert not hasattr(legacy, "mode")
    # New fields default to None in absence.
    assert legacy.dump_on_session_end is None


def test_round_trip_json():
    s = ProjectSettings(
        auto_ingest=AutoIngestSettings(
            dump_on_session_end=True, extract_after_dump=False,
        ),
    )
    js = s.model_dump_json()
    loaded = ProjectSettings.model_validate_json(js)
    assert loaded.auto_ingest.dump_on_session_end is True
    assert loaded.auto_ingest.extract_after_dump is False


def test_get_by_dot_path():
    s = ProjectSettings()
    assert get_by_dot_path(s, "lint.enabled_rules") is None
    assert get_by_dot_path(s, "snapshots.retention_days") == 180
    assert get_by_dot_path(s, "auto_ingest.dump_on_session_end") is None
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


# ---------------------------------------------------------------------------
# v0.0.10: resolve_ingest_flags — single source of truth for hooks /
# auto_dump / worker. Per-project field wins over GlobalSettings default;
# None on a project field means "inherit".
# ---------------------------------------------------------------------------


def test_resolve_ingest_flags_uses_global_when_project_is_none():
    """No project context (e.g. unassigned cwd in a hook) → globals only."""
    g = GlobalSettings(auto_ingest_defaults=AutoIngestDefaults(
        dump_on_session_end=True,
        dump_stale_after_24h=False,
        extract_after_dump=True,
    ))
    assert resolve_ingest_flags(None, g) == (True, False, True)


def test_resolve_ingest_flags_default_globals():
    """Fresh install: dump on /exit AND stale-safety-net both ON (free,
    just file IO), extract OFF (the only LLM-spending toggle is opt-in)."""
    assert resolve_ingest_flags(None, GlobalSettings()) == (True, True, False)


def test_resolve_ingest_flags_per_project_overrides_global_per_field():
    """Project override is per-field: a project setting True wins even if global is False."""
    g = GlobalSettings(auto_ingest_defaults=AutoIngestDefaults(
        dump_on_session_end=False,
        dump_stale_after_24h=False,
        extract_after_dump=False,
    ))
    p = ProjectSettings(auto_ingest=AutoIngestSettings(
        dump_on_session_end=True,  # only this overridden
    ))
    assert resolve_ingest_flags(p, g) == (True, False, False)


def test_resolve_ingest_flags_project_none_field_inherits_global():
    """A None field on the project means "inherit" — not "force False"."""
    g = GlobalSettings(auto_ingest_defaults=AutoIngestDefaults(
        dump_on_session_end=True,
        dump_stale_after_24h=True,
        extract_after_dump=True,
    ))
    p = ProjectSettings(auto_ingest=AutoIngestSettings(
        dump_on_session_end=False,  # project override: False wins
        # other two None → inherit True
    ))
    assert resolve_ingest_flags(p, g) == (False, True, True)


def test_resolve_ingest_flags_project_false_overrides_global_true():
    """Distinguishes ``None`` (inherit) from ``False`` (explicit opt-out)."""
    g = GlobalSettings(auto_ingest_defaults=AutoIngestDefaults(
        extract_after_dump=True,
    ))
    p = ProjectSettings(auto_ingest=AutoIngestSettings(extract_after_dump=False))
    _, _, extract = resolve_ingest_flags(p, g)
    assert extract is False


def test_settings_store_get_project_returns_defaults_if_missing(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    s = store.get_project("missing")
    assert s == ProjectSettings()


def test_settings_store_patch_project_persists(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    updated = store.patch_project(
        "foo", {"auto_ingest": {"dump_on_session_end": False}},
    )
    assert updated.auto_ingest.dump_on_session_end is False
    f = tmp_path / "settings" / "foo.json"
    assert f.is_file()
    data = json.loads(f.read_text())
    assert data["auto_ingest"]["dump_on_session_end"] is False


def test_settings_store_patch_partial_preserves_others(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    store.patch_project("foo", {"snapshots": {"retention_days": 30}})
    updated = store.patch_project(
        "foo", {"lint": {"schedule": "0 4 * * *"}},
    )
    assert updated.snapshots.retention_days == 30
    assert updated.lint.schedule == "0 4 * * *"


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


# ---------------------------------------------------------------------------
# v0.0.49: one-time migration of the stale placebo `default_max_input_tokens`.
# Before this release the field did NOTHING (extraction read the env-default
# 800k). Task 2 made the field really control the cut, and Task 1 raised the
# default 150000→800000. Existing users still have the OLD placebo literal
# 150000 on disk — which NOBODY deliberately chose, since the field was inert.
# On their next restart extraction would silently regress to a 150k cut. The
# migration bumps exactly-150000 legacy files to 800000, gated by a one-time
# marker so a user who LATER sets 150000 on purpose keeps it.
# ---------------------------------------------------------------------------


def test_migrates_legacy_150k_to_800k(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    path = store.global_path
    path.parent.mkdir(parents=True, exist_ok=True)
    # A legacy file: the placebo default 150000 and NO migration marker.
    path.write_text(
        json.dumps({"version": 1, "default_max_input_tokens": 150000}),
        encoding="utf-8",
    )
    g = store.get_global()
    # Loaded value is migrated to the new default.
    assert g.default_max_input_tokens == 800_000
    # Persisted to disk (true one-time migration, not just an in-memory bump).
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["default_max_input_tokens"] == 800_000
    assert data["default_max_input_tokens_migrated"] is True


def test_does_not_touch_deliberate_value(tmp_path: Path):
    """Once the marker is set, a deliberate 150000 survives — the migration
    has already run and must not re-fire."""
    store = SettingsStore(root=tmp_path)
    path = store.global_path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Marker already True: the user deliberately set 150000 AFTER migration.
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "default_max_input_tokens": 150000,
                "default_max_input_tokens_migrated": True,
            }
        ),
        encoding="utf-8",
    )
    g = store.get_global()
    assert g.default_max_input_tokens == 150000  # untouched
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["default_max_input_tokens"] == 150000


def test_leaves_other_values_alone(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    path = store.global_path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Legacy file (no marker) but a value other than the placebo 150000.
    path.write_text(
        json.dumps({"version": 1, "default_max_input_tokens": 300000}),
        encoding="utf-8",
    )
    g = store.get_global()
    assert g.default_max_input_tokens == 300000


def test_missing_field_uses_new_default(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    path = store.global_path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Legacy file with no default_max_input_tokens at all → new default.
    path.write_text(json.dumps({"version": 1, "locale": "en"}), encoding="utf-8")
    g = store.get_global()
    assert g.default_max_input_tokens == 800_000


def test_migration_does_not_refire_for_deliberate_150k_after_load(tmp_path: Path):
    """End-to-end one-time gate: a legacy 150000 migrates to 800000 and stamps
    the marker; if the user then deliberately patches it back to 150000, a
    subsequent load keeps 150000 (marker present → no re-fire)."""
    store = SettingsStore(root=tmp_path)
    path = store.global_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "default_max_input_tokens": 150000}),
        encoding="utf-8",
    )
    assert store.get_global().default_max_input_tokens == 800_000
    # User deliberately sets it back to 150000 via patch.
    store.patch_global({"default_max_input_tokens": 150000})
    # Reload: marker is set, so the deliberate 150000 is preserved.
    assert store.get_global().default_max_input_tokens == 150000


def test_global_settings_ignores_unknown_fields(tmp_path, monkeypatch):
    """extra='ignore' must silently absorb β1-written files that contain primary_project."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    import json as _json

    from claude_mnemos.state.settings import SettingsStore, global_settings_path

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
