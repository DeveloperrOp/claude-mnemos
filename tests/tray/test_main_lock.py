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
