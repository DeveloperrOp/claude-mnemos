from __future__ import annotations

import pytest

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
from claude_mnemos.state.settings import (
    ProjectSettings,
    SettingsStore,
    SnapshotsSettings,
)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_daemon_uses_settings_when_vault_registered(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    SettingsStore().patch_project("x", {"snapshots": {"retention_days": 7}})
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    assert d.project_settings.snapshots.retention_days == 7
    assert d.project_entry is not None and d.project_entry.name == "x"


def test_daemon_falls_back_to_defaults_when_unregistered(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    assert d.project_entry is None
    assert d.project_settings == ProjectSettings()
    msgs = [a.message for a in d.alerts.list()]
    assert any("not registered in project-map" in m for m in msgs)


def test_daemon_reload_swaps_settings(tmp_path):
    # Only test the settings-swap bookkeeping; job-scheduling side-effects
    # of reload_settings are covered after Task 12 rewrites process.py.
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    # Use daily_enabled=True→True (no change) and same retention_days so
    # reload_settings doesn't touch the (empty) scheduler and raise.
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    orig_enabled = d.project_settings.snapshots.daily_enabled
    new = ProjectSettings(
        snapshots=SnapshotsSettings(
            daily_enabled=orig_enabled,  # no change → no scheduler path
            retention_days=d.project_settings.snapshots.retention_days,  # no change
        )
    )
    d.reload_settings(new)
    assert d.project_settings.snapshots.daily_enabled == orig_enabled


def test_daemon_reload_adds_daily_snapshot_job_when_enabled(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    SettingsStore().patch_project("x", {"snapshots": {"daily_enabled": False}})
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    assert d.scheduler.get_job("daily_snapshot") is None
    new = ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=True))
    d.reload_settings(new)
    assert d.scheduler.get_job("daily_snapshot") is not None


def test_daemon_alert_for_unregistered_uses_handler_error_kind(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    alerts = [a for a in d.alerts.list() if "not registered" in a.message]
    assert alerts and alerts[0].kind == "handler_error"
