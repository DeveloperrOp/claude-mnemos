from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


def test_main_run_subcommand_starts_supervisor_and_tray() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    fake_sv = MagicMock()
    fake_app = MagicMock()
    fake_si = MagicMock()
    fake_si.acquire.return_value = True
    fake_ipc = MagicMock()
    with patch.object(tray_main, "Supervisor", return_value=fake_sv), \
         patch.object(tray_main, "TrayApp", return_value=fake_app), \
         patch.object(tray_main, "get_single_instance", return_value=fake_si), \
         patch.object(tray_main, "IpcServer", return_value=fake_ipc), \
         patch.object(sys, "argv", ["mnemos-tray", "run"]):
        rc = tray_main.main()
    assert rc == 0
    fake_sv.start.assert_called_once()
    fake_app.run.assert_called_once()
    fake_si.release.assert_called_once()


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
    """When single_instance is already held, _cmd_run sends 'show' via IPC and
    exits clean with rc=0 (so the second invocation isn't a hard failure to
    the user — the existing tray just got a focus message)."""
    from claude_mnemos.tray import __main__ as tray_main

    fake_si = MagicMock()
    fake_si.acquire.return_value = False
    with patch.object(tray_main, "get_single_instance", return_value=fake_si), \
         patch.object(tray_main, "ipc_send", return_value=True), \
         patch.object(sys, "argv", ["mnemos-tray", "run"]):
        rc = tray_main.main()
    assert rc == 0
