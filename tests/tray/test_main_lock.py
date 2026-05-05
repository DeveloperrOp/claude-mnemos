"""Verify tray __main__._cmd_run uses the single_instance lock."""

from __future__ import annotations


def test_cmd_run_returns_0_on_lock_held(monkeypatch):
    """If single_instance.acquire() returns False, _cmd_run sends IPC 'show' and returns 0."""

    class FakeSI:
        def acquire(self):
            return False

        def release(self):
            pass

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
