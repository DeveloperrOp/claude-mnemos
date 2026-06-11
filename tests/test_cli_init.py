from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _isolated_install_state(tmp_path, monkeypatch):
    """cli_init.run() persists autostart_decision="accepted" after a successful
    tray-autostart step. Without this patch the happy-path tests write to the
    REAL ~/.claude-mnemos/install-state.json (module-level _STATE_PATH binds
    Path.home() at import/collection time, so conftest's HOME/USERPROFILE env
    patch does NOT protect it)."""
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )


def _patch_init(monkeypatch, *, hooks_ok=True, tray_ok=True, daemon_ok=True, browser=True):
    """Patch all external side-effects of cli_init.run()."""
    calls = {"hooks": 0, "tray_install": 0, "tray_run_started": 0, "browser": 0, "wait_health": 0}

    def fake_install():
        calls["hooks"] += 1
        if hooks_ok:
            return {"ok": True}
        raise RuntimeError("hooks broke")

    def fake_tray_install():
        calls["tray_install"] += 1
        return tray_ok

    def fake_wait_health():
        calls["wait_health"] += 1
        return daemon_ok

    def fake_open_browser(url):
        calls["browser"] += 1

    monkeypatch.setattr("claude_mnemos.cli_init._install_hooks_safe", fake_install)
    monkeypatch.setattr("claude_mnemos.cli_init._install_tray_autostart_safe", fake_tray_install)
    monkeypatch.setattr("claude_mnemos.cli_init._wait_daemon_health", fake_wait_health)
    monkeypatch.setattr("claude_mnemos.cli_init._open_browser", fake_open_browser)
    return calls


def test_init_happy_path(monkeypatch) -> None:
    from claude_mnemos.cli_init import run

    calls = _patch_init(monkeypatch)
    rc = run(open_browser=True)
    assert rc == 0
    assert calls == {"hooks": 1, "tray_install": 1, "tray_run_started": 0, "wait_health": 1, "browser": 1}


def test_init_skips_browser_when_flag_off(monkeypatch) -> None:
    from claude_mnemos.cli_init import run

    calls = _patch_init(monkeypatch)
    rc = run(open_browser=False)
    assert rc == 0
    assert calls["browser"] == 0


def test_init_returns_nonzero_on_hook_failure(monkeypatch) -> None:
    from claude_mnemos.cli_init import run

    _patch_init(monkeypatch, hooks_ok=False)
    rc = run(open_browser=False)
    assert rc != 0


def test_init_continues_when_tray_install_fails(monkeypatch) -> None:
    """Tray install failure (e.g. unsupported platform) must not block daemon-start path."""
    from claude_mnemos.cli_init import run

    calls = _patch_init(monkeypatch, tray_ok=False)
    rc = run(open_browser=True)
    assert calls["wait_health"] == 1
    assert calls["browser"] == 1
    assert rc == 0
