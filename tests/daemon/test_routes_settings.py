from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    app = create_app(vault, daemon=None)
    return TestClient(app), tmp_path


def test_get_settings_returns_defaults(client):
    c, _ = client
    r = c.get("/settings/foo")
    assert r.status_code == 200
    data = r.json()
    assert data["snapshots"]["retention_days"] == 180
    assert data["auto_ingest"]["enabled"] is True


def test_patch_settings_partial_persists(client):
    c, _ = client
    r = c.patch("/settings/foo", json={"snapshots": {"retention_days": 30}})
    assert r.status_code == 200
    assert r.json()["snapshots"]["retention_days"] == 30
    assert r.json()["snapshots"]["daily_enabled"] is True
    r2 = c.get("/settings/foo")
    assert r2.json()["snapshots"]["retention_days"] == 30


def test_patch_invalid_value_returns_422(client):
    c, _ = client
    r = c.patch("/settings/foo", json={"snapshots": {"retention_days": -1}})
    assert r.status_code == 422


def test_get_global_returns_defaults(client):
    c, _ = client
    r = c.get("/settings/global")
    assert r.status_code == 200
    assert r.json()["locale"] == "uk"
    assert r.json()["daemon_port"] == 5757


def test_patch_global_persists(client):
    c, _ = client
    r = c.patch("/settings/global", json={"locale": "en"})
    assert r.status_code == 200
    assert r.json()["locale"] == "en"


def test_patch_settings_triggers_daemon_reload_when_matching_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    ProjectStore().add(ProjectMapEntry(name="foo", vault_root=vault, cwd_patterns=[]))
    fake_daemon = MagicMock()
    fake_daemon.reload_settings = MagicMock()
    fake_daemon.config = MagicMock()
    fake_daemon.config.vault_root = vault
    app = create_app(vault, daemon=fake_daemon)
    c = TestClient(app)
    r = c.patch("/settings/foo", json={"snapshots": {"daily_enabled": False}})
    assert r.status_code == 200
    fake_daemon.reload_settings.assert_called_once()


def test_patch_other_project_settings_does_not_trigger_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    other_vault = tmp_path / "other_vault"
    other_vault.mkdir()
    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    s = ProjectStore()
    s.add(ProjectMapEntry(name="foo", vault_root=vault, cwd_patterns=[]))
    s.add(ProjectMapEntry(name="bar", vault_root=other_vault, cwd_patterns=[]))
    fake_daemon = MagicMock()
    fake_daemon.reload_settings = MagicMock()
    fake_daemon.config = MagicMock()
    fake_daemon.config.vault_root = vault
    app = create_app(vault, daemon=fake_daemon)
    c = TestClient(app)
    c.patch("/settings/bar", json={"snapshots": {"daily_enabled": False}})
    fake_daemon.reload_settings.assert_not_called()


def test_corrupt_global_returns_503(client):
    c, home = client
    f = home / ".claude-mnemos" / "global-settings.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json")
    r = c.get("/settings/global")
    assert r.status_code == 503
