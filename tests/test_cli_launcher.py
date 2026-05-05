import pytest


def test_launcher_existing_tray_sends_ipc(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher.ipc_send",
        lambda addr, msg, **kw: sent.append((addr, msg)) or True,
    )
    monkeypatch.setattr("claude_mnemos.cli_launcher._tray_running", lambda: True)

    from claude_mnemos.cli_launcher import run
    rc = run([])
    assert rc == 0
    assert sent and sent[0][1] == "show"


def test_launcher_no_tray_spawns_tray_then_window(monkeypatch):
    spawn_calls = []
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher._spawn_tray",
        lambda: spawn_calls.append("tray") or True,
    )
    monkeypatch.setattr("claude_mnemos.cli_launcher._tray_running", lambda: False)
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher._wait_tray_ipc",
        lambda timeout_s=10: True,
    )

    sent = []
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher.ipc_send",
        lambda addr, msg, **kw: sent.append((addr, msg)) or True,
    )

    from claude_mnemos.cli_launcher import run
    rc = run([])
    assert rc == 0
    assert "tray" in spawn_calls
    assert sent and sent[0][1] == "show"


def test_launcher_no_spawn_tray_flag_skips_tray_spawn(monkeypatch):
    spawn_calls = []
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher._spawn_tray",
        lambda: spawn_calls.append("tray") or True,
    )
    monkeypatch.setattr("claude_mnemos.cli_launcher._tray_running", lambda: False)

    monkeypatch.setattr(
        "claude_mnemos.cli_launcher.launcher_run",
        lambda argv: 0,
    )

    from claude_mnemos.cli_launcher import run
    rc = run(["--no-spawn-tray"])
    assert rc == 0
    assert spawn_calls == []
