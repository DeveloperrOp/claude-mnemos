"""Frozen-mode behaviour of daemon /tray routes.

In the installed bundle sys.executable is claude-mnemos.exe, which parses
its own subcommands — invoking it with `-m claude_mnemos ...` exits 2
("invalid choice"), so the dashboard autostart toggle answered HTTP 500 on
every pure-frozen install (no `mnemos` on PATH).
"""

from __future__ import annotations

import sys

from claude_mnemos.daemon.routes import tray as tray_routes


def test_resolve_target_frozen(monkeypatch):
    monkeypatch.setattr("claude_mnemos.runtime.is_frozen", lambda: True)
    exe, args = tray_routes._resolve_target()
    assert exe == sys.executable
    assert args == ["tray", "run"]


def test_resolve_target_source_prefers_gui_script(monkeypatch):
    monkeypatch.setattr("claude_mnemos.runtime.is_frozen", lambda: False)
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.tray.shutil.which",
        lambda name: r"C:\venv\Scripts\mnemos-tray.exe" if name == "mnemos-tray" else None,
    )
    exe, args = tray_routes._resolve_target()
    assert exe.endswith("mnemos-tray.exe")
    assert args == ["run"]


def test_exec_tray_frozen_invokes_bare_subcommand(monkeypatch):
    monkeypatch.setattr("claude_mnemos.runtime.is_frozen", lambda: True)

    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr("claude_mnemos.daemon.routes.tray.subprocess.run", fake_run)

    tray_routes._exec_tray("install")
    assert captured["cmd"] == [sys.executable, "tray", "install"]


def test_exec_tray_source_falls_back_to_module_invocation(monkeypatch):
    monkeypatch.setattr("claude_mnemos.runtime.is_frozen", lambda: False)
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.tray.shutil.which", lambda name: None
    )

    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr("claude_mnemos.daemon.routes.tray.subprocess.run", fake_run)

    tray_routes._exec_tray("uninstall")
    assert captured["cmd"] == [sys.executable, "-m", "claude_mnemos", "tray", "uninstall"]
