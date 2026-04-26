from __future__ import annotations

from pathlib import Path

import psutil

DAEMON_CMDLINE_MARKER = "claude_mnemos.daemon"


def is_daemon_running(pid_file: Path) -> int | None:
    """Return live daemon PID, or None if not running / stale.

    Stale-PID recovery per spec §5.5:
    1. PID file missing → None.
    2. PID file unreadable / not int → delete, return None.
    3. PID dead → delete, return None.
    4. PID alive but cmdline lacks our marker (PID reused) → delete, return None.
    5. PID alive and cmdline matches → return pid.
    """
    if not pid_file.is_file():
        return None
    try:
        raw = pid_file.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (ValueError, OSError):
        cleanup_pid_file(pid_file)
        return None

    if not psutil.pid_exists(pid):
        cleanup_pid_file(pid_file)
        return None

    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline())
        if DAEMON_CMDLINE_MARKER not in cmdline:
            cleanup_pid_file(pid_file)
            return None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        cleanup_pid_file(pid_file)
        return None

    return pid


def write_pid_file(pid_file: Path, pid: int) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid), encoding="utf-8")


def cleanup_pid_file(pid_file: Path) -> None:
    pid_file.unlink(missing_ok=True)
