"""Tray icon tests — tagged @pytest.mark.manual since pystray needs a display."""

from __future__ import annotations

import os

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
