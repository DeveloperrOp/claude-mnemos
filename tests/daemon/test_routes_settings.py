from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    app = create_app(daemon=None)
    return TestClient(app), tmp_path


def test_get_settings_returns_defaults(client):
    c, _ = client
    r = c.get("/api/settings/foo")
    assert r.status_code == 200
    data = r.json()
    assert data["snapshots"]["retention_days"] == 180
    # v0.0.10: legacy ``enabled``/``mode`` fields default to None now;
    # the active toggles are the new dump_*/extract_* flags, also None
    # by default (= "inherit from GlobalSettings.auto_ingest_defaults").
    assert data["auto_ingest"]["enabled"] is None
    assert data["auto_ingest"]["dump_on_session_end"] is None
    assert data["auto_ingest"]["dump_stale_after_24h"] is None
    assert data["auto_ingest"]["extract_after_dump"] is None


def test_patch_settings_partial_persists(client):
    c, _ = client
    r = c.patch("/api/settings/foo", json={"snapshots": {"retention_days": 30}})
    assert r.status_code == 200
    assert r.json()["snapshots"]["retention_days"] == 30
    assert r.json()["snapshots"]["daily_enabled"] is True
    r2 = c.get("/api/settings/foo")
    assert r2.json()["snapshots"]["retention_days"] == 30


def test_patch_invalid_value_returns_422(client):
    c, _ = client
    r = c.patch("/api/settings/foo", json={"snapshots": {"retention_days": -1}})
    assert r.status_code == 422


def test_get_global_returns_defaults(client):
    c, _ = client
    r = c.get("/api/settings/global")
    assert r.status_code == 200
    assert r.json()["locale"] == "uk"
    assert r.json()["daemon_port"] == 5757


def test_patch_global_persists(client):
    c, _ = client
    r = c.patch("/api/settings/global", json={"locale": "en"})
    assert r.status_code == 200
    assert r.json()["locale"] == "en"


def test_patch_settings_triggers_daemon_reload_project_settings(tmp_path, monkeypatch):
    """PATCH /settings/{name} calls daemon.reload_project_settings for any project."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    fake_daemon = MagicMock()
    fake_daemon.reload_project_settings = AsyncMock()
    app = create_app(daemon=fake_daemon)
    c = TestClient(app)
    r = c.patch("/api/settings/foo", json={"snapshots": {"daily_enabled": False}})
    assert r.status_code == 200
    fake_daemon.reload_project_settings.assert_called_once()
    call_args = fake_daemon.reload_project_settings.call_args
    assert call_args.args[0] == "foo"


def test_patch_settings_triggers_reload_regardless_of_vault(tmp_path, monkeypatch):
    """reload_project_settings is called for any project name — vault-path
    filtering is the daemon's responsibility, not the route's."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    fake_daemon = MagicMock()
    fake_daemon.reload_project_settings = AsyncMock()
    app = create_app(daemon=fake_daemon)
    c = TestClient(app)
    r = c.patch("/api/settings/bar", json={"snapshots": {"daily_enabled": False}})
    assert r.status_code == 200
    fake_daemon.reload_project_settings.assert_called_once()
    assert fake_daemon.reload_project_settings.call_args.args[0] == "bar"


def test_corrupt_global_returns_503(client):
    c, home = client
    f = home / ".claude-mnemos" / "global-settings.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json")
    r = c.get("/api/settings/global")
    assert r.status_code == 503
