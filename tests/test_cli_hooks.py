"""Tests for `mnemos hooks {install, uninstall, status}` CLI subgroup."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def tmp_claude_settings(tmp_path, monkeypatch):
    """Redirect CLAUDE_SETTINGS to a tmp file."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    settings_path = fake_home / ".claude" / "settings.json"
    # Re-import to pick up new home
    import importlib
    from claude_mnemos import cli_hooks
    importlib.reload(cli_hooks)
    return cli_hooks, settings_path


def test_install_creates_settings_file_when_absent(tmp_claude_settings):
    cli_hooks, settings_path = tmp_claude_settings
    rc = cli_hooks._cmd_install(mock.Mock())
    assert rc == 0
    assert settings_path.exists()
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "hooks" in data
    assert "SessionStart" in data["hooks"]
    assert "SessionEnd" in data["hooks"]
    ss_cmd = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "session_start.py" in ss_cmd
    assert "claude_mnemos" in ss_cmd or "claude-mnemos" in ss_cmd


def test_install_preserves_unrelated_hooks(tmp_claude_settings):
    cli_hooks, settings_path = tmp_claude_settings
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "powershell beep"}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "python /other/hook.py"}]}],
        }
    }), encoding="utf-8")
    cli_hooks._cmd_install(mock.Mock())
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    # Stop block preserved as-is.
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "powershell beep"
    # SessionStart now has BOTH foreign and mnemos blocks.
    ss_cmds = [h["command"] for block in data["hooks"]["SessionStart"] for h in block["hooks"]]
    assert any("/other/hook.py" in c for c in ss_cmds)
    assert any("session_start.py" in c for c in ss_cmds)


def test_install_replaces_existing_mnemos_block(tmp_claude_settings):
    cli_hooks, settings_path = tmp_claude_settings
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    # Pre-populate with a stale mnemos hook (different path)
    settings_path.write_text(json.dumps({
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "python /old/claude_mnemos/hooks/start.py"}]}],
        }
    }), encoding="utf-8")
    cli_hooks._cmd_install(mock.Mock())
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    ss_cmds = [h["command"] for block in data["hooks"]["SessionStart"] for h in block["hooks"]]
    # Only one mnemos block should remain (the freshly installed one).
    assert sum(1 for c in ss_cmds if "claude_mnemos" in c or "claude-mnemos" in c) == 1
    # And the stale one is gone.
    assert not any("/old/claude_mnemos/hooks/start.py" in c for c in ss_cmds)


def test_uninstall_removes_only_mnemos_hooks(tmp_claude_settings):
    cli_hooks, settings_path = tmp_claude_settings
    cli_hooks._cmd_install(mock.Mock())
    # Add a foreign hook block manually
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    data["hooks"]["SessionStart"].append({"hooks": [{"type": "command", "command": "python /other/hook.py"}]})
    settings_path.write_text(json.dumps(data), encoding="utf-8")
    rc = cli_hooks._cmd_uninstall(mock.Mock())
    assert rc == 0
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    ss_cmds = [h["command"] for block in data["hooks"].get("SessionStart", []) for h in block["hooks"]]
    assert any("/other/hook.py" in c for c in ss_cmds)
    assert not any("session_start.py" in c and "claude_mnemos" in c for c in ss_cmds)


def test_uninstall_when_not_installed(tmp_claude_settings):
    cli_hooks, settings_path = tmp_claude_settings
    rc = cli_hooks._cmd_uninstall(mock.Mock())
    # No file → noop, returncode 0
    assert rc == 0


def test_status_when_installed(tmp_claude_settings, capsys):
    cli_hooks, settings_path = tmp_claude_settings
    cli_hooks._cmd_install(mock.Mock())
    rc = cli_hooks._cmd_status(mock.Mock())
    captured = capsys.readouterr()
    assert rc == 0  # both events have mnemos hooks
    assert "mnemos installed" in captured.out
    assert "session_start.py" in captured.out


def test_status_when_not_installed(tmp_claude_settings, capsys):
    cli_hooks, settings_path = tmp_claude_settings
    rc = cli_hooks._cmd_status(mock.Mock())
    assert rc == 1  # neither event installed → exit 1
