import pytest


def test_launcher_no_window_flag_exits_zero(monkeypatch):
    """Headless mode: launcher initialises but doesn't show a window. CI uses this."""
    from claude_mnemos.launcher import run

    rc = run(["--no-window"])
    assert rc == 0


def test_launcher_polls_daemon_health(monkeypatch):
    """Launcher's _wait_daemon_ready polls /api/health and returns True on 200."""
    polled = {"count": 0}

    class FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def getcode(self): return 200

    def fake_urlopen(url, timeout=None):
        polled["count"] += 1
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    from claude_mnemos.launcher import _wait_daemon_ready
    ok = _wait_daemon_ready(timeout_s=2.0)
    assert ok is True
    assert polled["count"] >= 1


def test_launcher_returns_false_if_daemon_never_ready(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise OSError("daemon down")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    from claude_mnemos.launcher import _wait_daemon_ready
    ok = _wait_daemon_ready(timeout_s=0.5)
    assert ok is False


def test_launcher_no_spawn_tray_flag_does_not_open_window(monkeypatch):
    """--no-window with --no-spawn-tray (used by supervisor as parent) should still exit clean.

    Both flags coexist; --no-window takes precedence for CI.
    """
    from claude_mnemos.launcher import run
    rc = run(["--no-window", "--no-spawn-tray"])
    assert rc == 0


# ── _make_on_closing ────────────────────────────────────────────────


def test_make_on_closing_uses_saved_action_hide(tmp_path, monkeypatch):
    """If saved action is 'hide', handler hides window and returns False."""
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )
    from claude_mnemos.state.install_state import InstallState
    InstallState(window_close_action="hide").save()

    class FakeWindow:
        def __init__(self): self.hidden = False
        def hide(self): self.hidden = True
        def evaluate_js(self, code): raise AssertionError("should not be called")

    from claude_mnemos.launcher import _make_on_closing
    win = FakeWindow()
    handler = _make_on_closing(win)
    assert handler() is False
    assert win.hidden is True


def test_make_on_closing_uses_saved_action_quit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )
    from claude_mnemos.state.install_state import InstallState
    InstallState(window_close_action="quit").save()

    class FakeWindow:
        def hide(self): raise AssertionError("should not be called")
        def evaluate_js(self, code): raise AssertionError("should not be called")

    from claude_mnemos.launcher import _make_on_closing
    handler = _make_on_closing(FakeWindow())
    assert handler() is True


def test_make_on_closing_first_time_asks_and_persists_hide(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )

    class FakeWindow:
        def __init__(self): self.hidden = False
        def hide(self): self.hidden = True
        def evaluate_js(self, code): return True  # OK = minimise

    from claude_mnemos.launcher import _make_on_closing
    win = FakeWindow()
    handler = _make_on_closing(win)
    assert handler() is False
    assert win.hidden is True

    from claude_mnemos.state.install_state import load_install_state
    assert load_install_state().window_close_action == "hide"


def test_make_on_closing_first_time_asks_and_persists_quit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )

    class FakeWindow:
        def hide(self): raise AssertionError("should not be called")
        def evaluate_js(self, code): return False  # Cancel = quit

    from claude_mnemos.launcher import _make_on_closing
    handler = _make_on_closing(FakeWindow())
    assert handler() is True

    from claude_mnemos.state.install_state import load_install_state
    assert load_install_state().window_close_action == "quit"
