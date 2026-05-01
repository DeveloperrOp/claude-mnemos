"""Tests for /hooks/status endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_fake_home(tmp_path, monkeypatch):
    """Build a TestClient with ~/.claude redirected to tmp."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # Re-import cli_hooks to pick up new home
    import importlib
    from claude_mnemos import cli_hooks
    importlib.reload(cli_hooks)

    # Build app with reloaded hooks router
    from claude_mnemos.daemon.routes import hooks as hooks_route
    importlib.reload(hooks_route)

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(hooks_route.router)
    return TestClient(app), fake_home / ".claude" / "settings.json"


def test_status_when_settings_missing(client_with_fake_home):
    client, _ = client_with_fake_home
    r = client.get("/hooks/status")
    assert r.status_code == 200
    data = r.json()
    assert data["settings_exists"] is False
    assert data["all_installed"] is False
    assert data["session_start"]["installed"] is False
    assert data["session_end"]["installed"] is False


def test_status_when_mnemos_installed(client_with_fake_home):
    client, settings_path = client_with_fake_home
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "python /path/to/claude_mnemos/hooks/session_start.py"}]}],
            "SessionEnd": [{"hooks": [{"type": "command", "command": "python /path/to/claude-mnemos/hooks/session_end.py"}]}],
        }
    }), encoding="utf-8")
    r = client.get("/hooks/status")
    assert r.status_code == 200
    data = r.json()
    assert data["settings_exists"] is True
    assert data["all_installed"] is True
    assert data["session_start"]["installed"] is True
    assert data["session_end"]["installed"] is True


def test_status_with_foreign_only(client_with_fake_home):
    """Foreign hooks present but no mnemos -> all_installed False."""
    client, settings_path = client_with_fake_home
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "python /other/start.py"}]}],
        }
    }), encoding="utf-8")
    r = client.get("/hooks/status")
    data = r.json()
    assert data["all_installed"] is False
    assert data["session_start"]["installed"] is False
    assert data["session_start"]["other_commands"] == ["python /other/start.py"]
