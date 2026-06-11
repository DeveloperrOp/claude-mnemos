from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )
    from claude_mnemos.daemon.app import create_app
    app = create_app(daemon=None)
    return TestClient(app)


def test_get_autostart_returns_status(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._is_autostart_installed",
        lambda: True,
    )
    r = client.get("/api/system/autostart")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True


def test_get_autostart_returns_false_when_not_installed(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._is_autostart_installed",
        lambda: False,
    )
    r = client.get("/api/system/autostart")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_set_autostart_enabled_calls_install(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._install_autostart",
        lambda: calls.append("install") or True,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._uninstall_autostart",
        lambda: calls.append("uninstall") or True,
    )
    r = client.post("/api/system/autostart", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert "install" in calls
    assert "uninstall" not in calls


def test_set_autostart_disabled_calls_uninstall(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._install_autostart",
        lambda: calls.append("install") or True,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._uninstall_autostart",
        lambda: calls.append("uninstall") or True,
    )
    r = client.post("/api/system/autostart", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert "uninstall" in calls
    assert "install" not in calls


def test_set_window_close_action_persists_hide(client):
    r = client.post("/api/system/window-close-action", json={"action": "hide"})
    assert r.status_code == 200
    assert r.json()["action"] == "hide"
    from claude_mnemos.state.install_state import load_install_state
    assert load_install_state().window_close_action == "hide"


def test_set_window_close_action_persists_quit(client):
    r = client.post("/api/system/window-close-action", json={"action": "quit"})
    assert r.status_code == 200
    from claude_mnemos.state.install_state import load_install_state
    assert load_install_state().window_close_action == "quit"


def test_set_window_close_action_rejects_invalid(client):
    r = client.post("/api/system/window-close-action", json={"action": "bogus"})
    assert r.status_code == 400


def test_get_window_close_action_defaults_to_hide(client):
    r = client.get("/api/system/window-close-action")
    assert r.status_code == 200
    assert r.json() == {"action": "hide"}


def test_get_window_close_action_roundtrip(client):
    r = client.post("/api/system/window-close-action", json={"action": "quit"})
    assert r.status_code == 200
    r = client.get("/api/system/window-close-action")
    assert r.json() == {"action": "quit"}
