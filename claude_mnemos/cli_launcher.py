"""`mnemos launcher` — opens the desktop window.

Logic:
- If tray supervisor already running → send IPC 'show' → exit.
- If not → spawn 'mnemos tray run' detached, wait for IPC up, send 'show'.
- If --no-spawn-tray → just open the launcher window directly (used by
  the supervisor calling us as a child).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from claude_mnemos.launcher import run as launcher_run
from claude_mnemos.tray.ipc import ipc_send
from claude_mnemos.tray.single_instance import get_single_instance

if sys.platform == "win32":
    IPC_ADDRESS = r"\\.\pipe\claude-mnemos-tray"
else:
    IPC_ADDRESS = str(Path.home() / ".claude-mnemos" / "tray.sock")

TRAY_INSTANCE_NAME = "com.yarik.claude-mnemos.tray"


def _tray_running() -> bool:
    """Probe the named mutex / file lock — if acquired, tray is NOT running."""
    si = get_single_instance(TRAY_INSTANCE_NAME)
    if si.acquire():
        si.release()
        return False
    return True


def _spawn_tray() -> bool:
    from claude_mnemos import runtime
    # In frozen mode sys.executable IS the bundled claude-mnemos.exe — argparse
    # parses its own argv directly, so `-m claude_mnemos.tray` is invalid as a
    # subcommand and would crash silently. In source mode sys.executable is
    # python.exe and we need the explicit module path.
    if runtime.is_frozen():
        cmd = [sys.executable, "tray", "run"]
    else:
        cmd = [sys.executable, "-m", "claude_mnemos.cli", "tray", "run"]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
            start_new_session=(sys.platform != "win32"),
        )
        return True
    except Exception:
        return False


def _wait_tray_ipc(*, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _tray_running():
            return True
        time.sleep(0.3)
    return False


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mnemos launcher")
    parser.add_argument("--no-spawn-tray", action="store_true",
                        help="Do not spawn tray supervisor; open window directly.")
    args = parser.parse_args(argv)

    if args.no_spawn_tray:
        return launcher_run([])

    if _tray_running():
        ipc_send(IPC_ADDRESS, "show")
        return 0

    if not _spawn_tray():
        print("[launcher] failed to spawn tray supervisor", file=sys.stderr)
        return 2

    if not _wait_tray_ipc():
        print("[launcher] tray didn't come up in 10s", file=sys.stderr)
        return 3

    ipc_send(IPC_ADDRESS, "show")
    return 0


def _cmd_launcher(args: argparse.Namespace) -> int:
    extra = ["--no-spawn-tray"] if getattr(args, "no_spawn_tray", False) else []
    return run(extra)


def add_launcher_subparser(parent: argparse._SubParsersAction) -> None:
    p = parent.add_parser("launcher", help="Open the desktop launcher window")
    p.add_argument("--no-spawn-tray", action="store_true",
                   help="Do not spawn tray supervisor; open window directly.")
    p.set_defaults(func=_cmd_launcher)
