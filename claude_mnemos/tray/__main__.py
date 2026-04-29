"""Entrypoint for `mnemos-tray` and `python -m claude_mnemos.tray`.

Subcommands:
    run         — foreground supervisor + tray icon (used by autostart entry)
    install     — register autostart, then spawn detached `mnemos-tray run`
    uninstall   — unregister autostart (does not kill running tray)
    status      — print human-readable autostart + tray + daemon state
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from claude_mnemos.daemon.lockfile import is_daemon_running
from claude_mnemos.tray.icon import TrayApp
from claude_mnemos.tray.platform import get_autostart_manager, platform_label
from claude_mnemos.tray.supervisor import Supervisor

LOG_DIR = Path.home() / ".claude-mnemos"
TRAY_PID_FILE = LOG_DIR / "tray.pid"
DAEMON_PID_FILE = LOG_DIR / "daemon.pid"
DAEMON_LOG = LOG_DIR / "daemon.log"
SUPERVISOR_LOG = LOG_DIR / "supervisor.log"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(SUPERVISOR_LOG),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _acquire_tray_lock() -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if TRAY_PID_FILE.is_file():
        try:
            old = int(TRAY_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            old = -1
        if old > 0 and psutil.pid_exists(old):
            print(f"another tray running, PID {old}", file=sys.stderr)
            return False
        TRAY_PID_FILE.unlink(missing_ok=True)
    TRAY_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_tray_lock() -> None:
    TRAY_PID_FILE.unlink(missing_ok=True)


def _resolve_target_exe() -> str:
    found = shutil.which("mnemos-tray")
    if found:
        return found
    # Fallback: invoke via python -m
    return f"{sys.executable} -m claude_mnemos.tray"


def _cmd_run() -> int:
    if not _acquire_tray_lock():
        return 1
    sv = Supervisor(daemon_pid_file=DAEMON_PID_FILE, log_path=DAEMON_LOG)
    sv.start()
    app = TrayApp(supervisor=sv)

    def _ticker() -> None:
        while True:
            time.sleep(5.0)
            try:
                sv.tick()
                app.repaint()
            except Exception:  # noqa: BLE001
                logging.exception("[supervisor] tick failed")

    t = threading.Thread(target=_ticker, daemon=True)
    t.start()

    try:
        app.run()  # blocks until Quit
    finally:
        _release_tray_lock()
    return 0


def _cmd_install() -> int:
    mgr = get_autostart_manager(target_exe=_resolve_target_exe())
    mgr.install()
    print(f"Auto-start installed ({platform_label()}).")
    # Detached spawn of `mnemos-tray run` if no tray currently running
    tray_alive = TRAY_PID_FILE.is_file() and psutil.pid_exists(
        int(TRAY_PID_FILE.read_text().strip() or 0)
    )
    if not tray_alive:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [sys.executable, "-m", "claude_mnemos.tray", "run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
            start_new_session=(sys.platform != "win32"),
        )
        print("Tray started.")
    return 0


def _cmd_uninstall() -> int:
    mgr = get_autostart_manager(target_exe=_resolve_target_exe())
    mgr.uninstall()
    print(f"Auto-start removed ({platform_label()}).")
    return 0


def _cmd_status() -> int:
    mgr = get_autostart_manager(target_exe=_resolve_target_exe())
    s = mgr.status()
    tray_pid = None
    if TRAY_PID_FILE.is_file():
        try:
            cand = int(TRAY_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            cand = None
        if cand and psutil.pid_exists(cand):
            tray_pid = cand
    out = {
        "platform": platform_label(),
        "autostart_enabled": s.installed,
        "autostart_path": s.path,
        "tray_running": tray_pid is not None,
        "tray_pid": tray_pid,
        "daemon_pid": is_daemon_running(DAEMON_PID_FILE),
    }
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="mnemos-tray")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("install")
    sub.add_parser("uninstall")
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd == "run":
        return _cmd_run()
    if args.cmd == "install":
        return _cmd_install()
    if args.cmd == "uninstall":
        return _cmd_uninstall()
    if args.cmd == "status":
        return _cmd_status()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
