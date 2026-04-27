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
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    new = ProjectSettings(
        snapshots=SnapshotsSettings(daily_enabled=False, retention_days=10)
    )
    d.reload_settings(new)
    assert d.project_settings.snapshots.daily_enabled is False
    assert d.project_settings.snapshots.retention_days == 10


def test_daemon_reload_removes_daily_snapshot_job_when_disabled(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    SettingsStore().patch_project("x", {"snapshots": {"daily_enabled": True}})
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    assert d.scheduler.get_job("daily_snapshot") is not None
    new = ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False))
    d.reload_settings(new)
    assert d.scheduler.get_job("daily_snapshot") is None


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


def test_daemon_reload_reschedules_backups_cleanup_when_retention_changes(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    job_before = d.scheduler.get_job("backups_cleanup")
    assert job_before is not None
    new = ProjectSettings(snapshots=SnapshotsSettings(retention_days=42))
    d.reload_settings(new)
    job_after = d.scheduler.get_job("backups_cleanup")
    assert job_after is not None
    # args should reflect the new retention_days
    assert 42 in job_after.args


def test_daemon_alert_for_unregistered_uses_handler_error_kind(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    alerts = [a for a in d.alerts.list() if "not registered" in a.message]
    assert alerts and alerts[0].kind == "handler_error"
