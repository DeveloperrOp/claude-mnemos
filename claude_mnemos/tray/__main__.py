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
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from pathlib import Path

import psutil

from claude_mnemos.daemon.lockfile import is_daemon_running
from claude_mnemos.tray.icon import TrayApp
from claude_mnemos.tray.ipc import IpcServer, ipc_send
from claude_mnemos.tray.platform import get_autostart_manager, platform_label
from claude_mnemos.tray.single_instance import get_single_instance
from claude_mnemos.tray.supervisor import Supervisor

LOG_DIR = Path.home() / ".claude-mnemos"
TRAY_PID_FILE = LOG_DIR / "tray.pid"
DAEMON_PID_FILE = LOG_DIR / "daemon.pid"
DAEMON_LOG = LOG_DIR / "daemon.log"
SUPERVISOR_LOG = LOG_DIR / "supervisor.log"

TRAY_INSTANCE_NAME = "com.yarik.claude-mnemos.tray"
if sys.platform == "win32":
    IPC_ADDRESS = r"\\.\pipe\claude-mnemos-tray"
else:
    IPC_ADDRESS = str(Path.home() / ".claude-mnemos" / "tray.sock")


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(SUPERVISOR_LOG),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _resolve_target() -> tuple[str, list[str]]:
    """Resolve the (executable, args) pair the OS autostart entry should launch.

    Primary: ``mnemos-tray run`` if ``mnemos-tray`` is on PATH (built via the
    ``[project.gui-scripts]`` entry → uses pythonw.exe under Windows, no
    console window).
    Fallback: ``<pythonw>/<python3> -m claude_mnemos.tray run`` — used only
    when the gui-script entry isn't available (e.g. running from a checkout
    without ``pip install``). On Windows we prefer ``pythonw.exe`` (silent
    sibling of ``python.exe``) so the tray doesn't drag a black console
    window into taskbar / alt-tab.
    """
    found = shutil.which("mnemos-tray")
    if found:
        return found, ["run"]
    # Windows fallback: swap python.exe → pythonw.exe to suppress the console.
    exe = sys.executable
    if sys.platform == "win32" and exe.lower().endswith("python.exe"):
        candidate = exe[: -len("python.exe")] + "pythonw.exe"
        if Path(candidate).exists():
            exe = candidate
    return exe, ["-m", "claude_mnemos.tray", "run"]


def _cmd_run() -> int:
    si = get_single_instance(TRAY_INSTANCE_NAME)
    if not si.acquire():
        # Already running — tell that one to show its launcher window, exit clean.
        ok = ipc_send(IPC_ADDRESS, "show")
        if ok:
            print("[tray] another instance running; sent 'show'.")
        else:
            print("[tray] another instance running but IPC unreachable.", file=sys.stderr)
        return 0

    sv = Supervisor(daemon_pid_file=DAEMON_PID_FILE, log_path=DAEMON_LOG)
    sv.start()
    app = TrayApp(supervisor=sv)

    def _on_ipc(msg: str) -> None:
        if msg == "show":
            try:
                getattr(sv, "open_launcher", lambda: None)()
            except Exception:
                logging.exception("[tray] open_launcher failed")

    ipc_srv: IpcServer | None = IpcServer(IPC_ADDRESS, on_message=_on_ipc)
    try:
        ipc_srv.start()
    except Exception:
        logging.exception("[tray] IPC server failed to start; continuing without it")
        ipc_srv = None

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
        if ipc_srv:
            try:
                ipc_srv.stop()
            except Exception:
                logging.exception("[tray] IPC stop failed")
        try:
            sv.stop()
        except Exception:
            logging.exception("[tray] supervisor stop failed")
        si.release()
    return 0


def _cmd_install() -> int:
    target_exe, target_args = _resolve_target()
    mgr = get_autostart_manager(target_exe=target_exe, target_args=target_args)
    mgr.install()
    print(f"Auto-start installed ({platform_label()}).")
    # Detached spawn of `mnemos-tray run` if no tray currently running
    tray_alive = False
    if TRAY_PID_FILE.is_file():
        try:
            tray_pid = int(TRAY_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            tray_pid = 0
        if tray_pid > 0 and psutil.pid_exists(tray_pid):
            tray_alive = True
    if not tray_alive:
        from claude_mnemos import runtime
        # Frozen bundle has its own argparse — `-m` is invalid as a subcommand.
        # In source mode sys.executable is python.exe and we need the explicit
        # module path. Same pattern as cli_launcher._spawn_tray and
        # supervisor._spawn_daemon.
        if runtime.is_frozen():
            cmd = [sys.executable, "tray", "run"]
        else:
            cmd = [sys.executable, "-m", "claude_mnemos.tray", "run"]
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            cmd,
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
    target_exe, target_args = _resolve_target()
    mgr = get_autostart_manager(target_exe=target_exe, target_args=target_args)
    mgr.uninstall()
    print(f"Auto-start removed ({platform_label()}).")
    # Record user decision so daemon's autostart-default-on doesn't re-fire.
    try:
        from claude_mnemos.state.install_state import load_install_state
        state = load_install_state()
        state.autostart_decision = "declined"
        state.save()
    except Exception:
        pass
    return 0


def _cmd_status() -> int:
    target_exe, target_args = _resolve_target()
    mgr = get_autostart_manager(target_exe=target_exe, target_args=target_args)
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
