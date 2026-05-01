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
    # Match production wiring: all daemon routers live under /api/*
    app.include_router(hooks_route.router, prefix="/api")
    return TestClient(app), fake_home / ".claude" / "settings.json"


def test_status_when_settings_missing(client_with_fake_home):
    client, _ = client_with_fake_home
    r = client.get("/api/hooks/status")
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
    r = client.get("/api/hooks/status")
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
    r = client.get("/api/hooks/status")
    data = r.json()
    assert data["all_installed"] is False
    assert data["session_start"]["installed"] is False
    assert data["session_start"]["other_commands"] == ["python /other/start.py"]


def test_install_creates_settings_file_when_absent(client_with_fake_home):
    client, settings_path = client_with_fake_home
    assert not settings_path.exists()
    r = client.post("/api/hooks/install")
    assert r.status_code == 200
    data = r.json()
    assert data["install_result"]["ok"] is True
    assert data["status"]["all_installed"] is True
    assert settings_path.exists()


def test_install_idempotent(client_with_fake_home):
    client, settings_path = client_with_fake_home
    r1 = client.post("/api/hooks/install")
    r2 = client.post("/api/hooks/install")
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both events still have exactly one mnemos block after second install.
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    for event in ("SessionStart", "SessionEnd"):
        blocks = settings["hooks"][event]
        mnemos_blocks = [
            b for b in blocks
            if any("claude_mnemos" in h.get("command", "") or "claude-mnemos" in h.get("command", "")
                   for h in b.get("hooks", []))
        ]
        assert len(mnemos_blocks) == 1


def test_errors_when_log_missing(client_with_fake_home, tmp_path, monkeypatch):
    """No hook-errors file → empty list, count 0."""
    monkeypatch.setenv("MNEMOS_HOOK_ERRORS_FILE", str(tmp_path / "missing.jsonl"))
    client, _ = client_with_fake_home
    r = client.get("/api/hooks/errors")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert data["entries"] == []


def test_errors_returns_recent_entries_newest_first(client_with_fake_home, tmp_path, monkeypatch):
    log_path = tmp_path / "errors.jsonl"
    monkeypatch.setenv("MNEMOS_HOOK_ERRORS_FILE", str(log_path))

    # Write three entries chronologically
    import json as _json
    entries_in = [
        {"ts": "2026-05-01T10:00:00Z", "hook": "session_start", "kind": "exception", "message": "first"},
        {"ts": "2026-05-01T11:00:00Z", "hook": "session_end",   "kind": "exception", "message": "second"},
        {"ts": "2026-05-01T12:00:00Z", "hook": "session_start", "kind": "exception", "message": "third"},
    ]
    log_path.write_text("\n".join(_json.dumps(e) for e in entries_in) + "\n", encoding="utf-8")

    client, _ = client_with_fake_home
    r = client.get("/api/hooks/errors?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    # Newest first
    assert [e["message"] for e in data["entries"]] == ["third", "second", "first"]


def test_errors_limit_clamps(client_with_fake_home, tmp_path, monkeypatch):
    log_path = tmp_path / "errors.jsonl"
    monkeypatch.setenv("MNEMOS_HOOK_ERRORS_FILE", str(log_path))
    import json as _json
    log_path.write_text(
        "\n".join(_json.dumps({"ts": "x", "hook": "h", "kind": "info", "message": str(i)}) for i in range(20)) + "\n",
        encoding="utf-8",
    )
    client, _ = client_with_fake_home
    r = client.get("/api/hooks/errors?limit=5")
    assert r.status_code == 200
    assert r.json()["count"] == 5


def test_install_preserves_foreign_hooks(client_with_fake_home):
    client, settings_path = client_with_fake_home
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "echo bye"}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "python /other/start.py"}]}],
        }
    }), encoding="utf-8")
    r = client.post("/api/hooks/install")
    assert r.status_code == 200
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    # Stop block preserved unchanged.
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo bye"
    # SessionStart has BOTH the foreign block AND the new mnemos block.
    ss_cmds = [h["command"] for b in settings["hooks"]["SessionStart"] for h in b["hooks"]]
    assert any("/other/start.py" in c for c in ss_cmds)
    assert any("session_start.py" in c and ("claude_mnemos" in c or "claude-mnemos" in c) for c in ss_cmds)
