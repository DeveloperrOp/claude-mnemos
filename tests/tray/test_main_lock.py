"""Verify tray __main__._cmd_run uses the single_instance lock."""

from __future__ import annotations

import sys

import pytest


class FakeSI:
    def acquire(self):
        return False

    def release(self):
        pass


def test_cmd_run_returns_0_on_lock_held(monkeypatch):
    """If single_instance.acquire() returns False, _cmd_run sends IPC 'show' and returns 0."""

    monkeypatch.setattr(
        "claude_mnemos.tray.__main__.get_single_instance",
        lambda *a, **kw: FakeSI(),
    )

    sent = []
    monkeypatch.setattr(
        "claude_mnemos.tray.__main__.ipc_send",
        lambda addr, msg, **kw: sent.append((addr, msg)) or True,
    )

    from claude_mnemos.tray import __main__ as m
    rc = m._cmd_run()
    assert rc == 0
    assert sent and sent[0][1] == "show"


def test_cmd_run_notifies_user_when_lock_holder_unreachable(monkeypatch):
    """Lock held + IPC dead = stale tray from another install. The 2026-06-10
    incident: a dev-venv tray held the mutex, the installed exe exited in
    silence and the user saw 'nothing opened'. The user must get a message."""

    monkeypatch.setattr(
        "claude_mnemos.tray.__main__.get_single_instance",
        lambda *a, **kw: FakeSI(),
    )
    monkeypatch.setattr(
        "claude_mnemos.tray.__main__.ipc_send",
        lambda addr, msg, **kw: False,
    )

    notified = []
    monkeypatch.setattr(
        "claude_mnemos.tray.__main__._notify_stale_lock",
        lambda: notified.append(True),
    )

    from claude_mnemos.tray import __main__ as m
    rc = m._cmd_run()
    assert rc == 0
    assert notified, "user was not notified about the unreachable lock holder"


def test_cmd_run_does_not_notify_when_ipc_reachable(monkeypatch):
    """Healthy double-launch (IPC answers) keeps the quiet 'show window' UX."""

    monkeypatch.setattr(
        "claude_mnemos.tray.__main__.get_single_instance",
        lambda *a, **kw: FakeSI(),
    )
    monkeypatch.setattr(
        "claude_mnemos.tray.__main__.ipc_send",
        lambda addr, msg, **kw: True,
    )

    notified = []
    monkeypatch.setattr(
        "claude_mnemos.tray.__main__._notify_stale_lock",
        lambda: notified.append(True),
    )

    from claude_mnemos.tray import __main__ as m
    rc = m._cmd_run()
    assert rc == 0
    assert not notified


@pytest.mark.skipif(sys.platform != "win32", reason="MessageBoxW is Windows-only")
def test_notify_stale_lock_shows_messagebox(monkeypatch):
    """The windowed exe has no console — stderr is invisible. On Windows the
    notification must surface as a MessageBox."""
    import ctypes

    calls = []

    def fake_messagebox(hwnd, text, caption, flags):
        calls.append((text, caption))
        return 1

    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", fake_messagebox)

    from claude_mnemos.tray import __main__ as m
    m._notify_stale_lock()
    assert calls, "MessageBoxW was not invoked"
    text, caption = calls[0]
    assert "claude-mnemos" in caption
    assert "not responding" in text


def test_cmd_run_writes_and_cleans_pid_file(monkeypatch, tmp_path):
    """The mutex refactor dropped the tray.pid write but kept its readers
    (/tray/status tray_running, _cmd_install tray-alive) — permanently false.
    _cmd_run must record its PID while alive and clean it up on exit."""
    import os

    from claude_mnemos.tray import __main__ as m

    pid_path = tmp_path / "tray.pid"
    monkeypatch.setattr(m, "TRAY_PID_FILE", pid_path)

    class OkSI:
        def acquire(self):
            return True

        def release(self):
            pass

    monkeypatch.setattr(m, "get_single_instance", lambda *a, **kw: OkSI())

    class FakeSupervisor:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def tick(self):
            pass

    monkeypatch.setattr(m, "Supervisor", FakeSupervisor)

    seen = {}

    class FakeApp:
        def __init__(self, supervisor):
            pass

        def run(self):
            seen["pid_text"] = pid_path.read_text(encoding="utf-8") if pid_path.is_file() else None

        def repaint(self):
            pass

    monkeypatch.setattr(m, "TrayApp", FakeApp)

    class FakeIpc:
        def __init__(self, addr, on_message):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(m, "IpcServer", FakeIpc)

    rc = m._cmd_run()
    assert rc == 0
    assert seen["pid_text"] == str(os.getpid()), "pid file absent/wrong while tray runs"
    assert not pid_path.exists(), "pid file must be removed on clean exit"


def test_cmd_install_spawn_tray_false_does_not_spawn(monkeypatch):
    """postinstall runs _cmd_install DURING `tray run` — spawning another
    tray there races the host for the single-instance mutex and the loser
    pops a spurious stale-lock warning at first sign-in."""
    from claude_mnemos.tray import __main__ as m

    class FakeMgr:
        def install(self):
            pass

    monkeypatch.setattr(m, "get_autostart_manager", lambda **kw: FakeMgr())

    spawned = []
    monkeypatch.setattr(
        m.subprocess, "Popen", lambda *a, **kw: spawned.append(a) or None
    )

    rc = m._cmd_install(spawn_tray=False)
    assert rc == 0
    assert not spawned


def test_postinstall_silent_init_does_not_spawn_tray(monkeypatch, tmp_path):
    """_silent_init must call _cmd_install with spawn_tray=False."""
    import claude_mnemos.postinstall as pi

    monkeypatch.setattr(
        "claude_mnemos.cli_hooks.install", lambda: None
    )

    calls = []

    def fake_install(*, spawn_tray=True):
        calls.append(spawn_tray)
        return 0

    monkeypatch.setattr(
        "claude_mnemos.tray.__main__._cmd_install", fake_install
    )
    # Redirect install-state to tmp so reads/writes never touch the real
    # home dir. NOTE: postinstall.py binds load_install_state at import
    # time, so patching the function on its source module is dead — patch
    # the state path instead (same pattern as tests/test_postinstall.py).
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )

    errors = pi._silent_init()
    assert errors == []
    assert calls == [False]


def test_resolve_target_frozen_uses_bare_subcommand(monkeypatch):
    """Frozen bundle: the exe parses its own subcommands — `-m` exits 2.
    The autostart .lnk written with '-m claude_mnemos.tray run' meant
    autostart NEVER worked from a frozen first-run install."""
    monkeypatch.setattr("claude_mnemos.runtime.is_frozen", lambda: True)

    from claude_mnemos.tray import __main__ as m
    exe, args = m._resolve_target()
    assert exe == sys.executable
    assert args == ["tray", "run"]
    assert "-m" not in args
