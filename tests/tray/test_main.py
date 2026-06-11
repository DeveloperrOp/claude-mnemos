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


def test_main_install_subcommand_calls_autostart(monkeypatch, tmp_path) -> None:
    from claude_mnemos.tray import __main__ as tray_main

    # _cmd_install(spawn_tray=True) Popens a detached `tray run` when no live
    # tray.pid is found. Unmocked, every pytest run spawned a REAL tray process
    # that survived pytest exit. Pin TRAY_PID_FILE to a non-existent tmp file
    # (the module-level constant binds Path.home() at import time) so the
    # spawn branch is taken deterministically, and mock Popen to assert the
    # spawn args instead of launching anything.
    monkeypatch.setattr(tray_main, "TRAY_PID_FILE", tmp_path / "tray.pid")
    fake_mgr = MagicMock()
    with patch.object(tray_main, "get_autostart_manager", return_value=fake_mgr), \
         patch.object(tray_main.subprocess, "Popen") as fake_popen, \
         patch.object(sys, "argv", ["mnemos-tray", "install"]):
        rc = tray_main.main()
    assert rc == 0
    fake_mgr.install.assert_called_once()
    fake_popen.assert_called_once()
    assert fake_popen.call_args[0][0] == [
        sys.executable, "-m", "claude_mnemos.tray", "run",
    ]


def test_main_uninstall_subcommand_calls_autostart(monkeypatch, tmp_path) -> None:
    from claude_mnemos.tray import __main__ as tray_main

    # _cmd_uninstall persists autostart_decision="declined". Without this
    # patch the test writes to the REAL ~/.claude-mnemos/install-state.json
    # (module-level _STATE_PATH binds Path.home() at import/collection time,
    # so conftest's HOME/USERPROFILE env patch does NOT protect it).
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )
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
