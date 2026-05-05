"""Tray icon tests — tagged @pytest.mark.manual since pystray needs a display."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.manual

skip_in_ci = pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="pystray requires a display; not available in headless CI",
)


@skip_in_ci
def test_tray_app_constructs_without_running() -> None:
    from claude_mnemos.tray.icon import TrayApp

    app = TrayApp(supervisor=None, dashboard_url="http://localhost:5757/")
    # Don't call .run() — that blocks on Win32 message loop
    assert app.dashboard_url == "http://localhost:5757/"
    assert app.icon is not None


# ── Action-method tests (no display needed — pystray mocked) ────────────────


@pytest.fixture
def tray_app(monkeypatch):
    """TrayApp with pystray.Icon mocked so we don't need a display."""
    import claude_mnemos.tray.icon as icon_mod

    monkeypatch.setattr(icon_mod, "pystray", MagicMock())
    monkeypatch.setattr(icon_mod, "_load_image", lambda *a, **kw: None)

    sv = MagicMock()
    sv.state = None
    sv._spawned = False
    sv.daemon_paused = False

    return icon_mod.TrayApp(supervisor=sv), sv


def test_open_dashboard_calls_supervisor_open_launcher(tray_app):
    app, sv = tray_app
    app._open_dashboard(None, None)
    sv.open_launcher.assert_called_once()


def test_quit_calls_supervisor_shutdown(tray_app):
    app, sv = tray_app
    app._quit(None, None)
    sv.shutdown.assert_called_once()


def test_toggle_pause_calls_pause_when_running(tray_app):
    app, sv = tray_app
    sv.daemon_paused = False
    app._toggle_pause(None, None)
    sv.pause_daemon.assert_called_once()
    sv.resume_daemon.assert_not_called()


def test_toggle_pause_calls_resume_when_paused(tray_app):
    app, sv = tray_app
    sv.daemon_paused = True
    app._toggle_pause(None, None)
    sv.resume_daemon.assert_called_once()
    sv.pause_daemon.assert_not_called()
