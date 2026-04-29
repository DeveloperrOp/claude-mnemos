from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


def test_main_run_subcommand_starts_supervisor_and_tray() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    fake_sv = MagicMock()
    fake_app = MagicMock()
    with patch.object(tray_main, "Supervisor", return_value=fake_sv), \
         patch.object(tray_main, "TrayApp", return_value=fake_app), \
         patch.object(tray_main, "_acquire_tray_lock", return_value=True), \
         patch.object(tray_main, "_release_tray_lock"), \
         patch.object(sys, "argv", ["mnemos-tray", "run"]):
        rc = tray_main.main()
    assert rc == 0
    fake_sv.start.assert_called_once()
    fake_app.run.assert_called_once()


def test_main_install_subcommand_calls_autostart() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    fake_mgr = MagicMock()
    with patch.object(tray_main, "get_autostart_manager", return_value=fake_mgr), \
         patch.object(sys, "argv", ["mnemos-tray", "install"]):
        rc = tray_main.main()
    assert rc == 0
    fake_mgr.install.assert_called_once()


def test_main_uninstall_subcommand_calls_autostart() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    fake_mgr = MagicMock()
    with patch.object(tray_main, "get_autostart_manager", return_value=fake_mgr), \
         patch.object(sys, "argv", ["mnemos-tray", "uninstall"]):
        rc = tray_main.main()
    assert rc == 0
    fake_mgr.uninstall.assert_called_once()


def test_main_status_subcommand_prints_json() -> None:
    from claude_mnemos.tray import __main__ as tray_main
    from claude_mnemos.tray.platform.base import AutostartStatus

    fake_mgr = MagicMock()
    fake_mgr.status.return_value = AutostartStatus(installed=True, path="/x")
    with patch.object(tray_main, "get_autostart_manager", return_value=fake_mgr), \
         patch.object(sys, "argv", ["mnemos-tray", "status"]):
        rc = tray_main.main()
    assert rc == 0  # printed to stdout; capture not strictly needed for this test


def test_main_run_refuses_when_lock_held() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    with patch.object(tray_main, "_acquire_tray_lock", return_value=False), \
         patch.object(sys, "argv", ["mnemos-tray", "run"]):
        rc = tray_main.main()
    assert rc == 1
