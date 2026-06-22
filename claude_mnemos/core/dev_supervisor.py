"""Watchdog for the source/Python daemon (the Smart-App-Control workaround).

Keeps the daemon up, restarts it if it dies, and toasts the user -- the job a
tray supervisor would do, minus the pystray icon that spawns process duplicates
in this environment. A separate process, so it survives the daemon's death and
answers the "who starts it / who tells me it's down" gap.

Run (autostarted on login):  pythonw -m claude_mnemos.core.dev_supervisor
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time
import urllib.request

HEALTH_URL = "http://127.0.0.1:5757/api/health"
POLL_SECONDS = 10
# ~40s of downtime before we act, so a normal update-restart (git button) rides
# through without the watchdog also piling on a restart.
FAIL_THRESHOLD = 4
STARTUP_GRACE = 25

_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
)


def _daemon_ok() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:  # noqa: S310
            return bool(r.status == 200)
    except Exception:  # noqa: BLE001 — any failure means "not healthy"
        return False


def _kill_daemons() -> None:
    """Kill any stale/duplicate daemon so a clean one can bind the port."""
    try:
        import psutil
    except ImportError:
        return
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or [])
            if name in ("python.exe", "pythonw.exe") and "claude_mnemos.daemon" in cmd:
                p.kill()
        except Exception:  # noqa: BLE001 — process vanished / no access
            pass


def _start_daemon() -> None:
    _kill_daemons()
    time.sleep(1.5)
    subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [sys.executable, "-m", "claude_mnemos", "daemon", "start"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_NO_WINDOW,
        close_fds=True,
    )


def _toast(message: str) -> None:
    if sys.platform != "win32":
        return
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        "$n.Visible=$true;"
        f"$n.ShowBalloonTip(6000,'Mnemos','{message}',"
        "[System.Windows.Forms.ToolTipIcon]::Info);"
        "Start-Sleep -Seconds 7;$n.Dispose()"
    )
    with contextlib.suppress(OSError):
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            ["powershell", "-NoProfile", "-Command", ps],
            creationflags=_NO_WINDOW,
            close_fds=True,
        )


_mutex_handle = None  # kept alive for the process lifetime once created


def _is_sole_instance() -> bool:
    """Named-mutex single-instance: the environment spawns a duplicate copy of
    every ``-m claude_mnemos.*`` process, so the first watchdog creates the mutex
    and the copy sees ERROR_ALREADY_EXISTS and exits. One watchdog runs."""
    if sys.platform != "win32":
        return True
    import ctypes

    global _mutex_handle
    error_already_exists = 183
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _mutex_handle = kernel32.CreateMutexW(
        None, False, "claude-mnemos-watchdog-singleton"
    )
    return ctypes.get_last_error() != error_already_exists


def main() -> int:
    if not _is_sole_instance():
        return 0
    if not _daemon_ok():
        _start_daemon()
        time.sleep(STARTUP_GRACE)
    fails = 0
    while True:
        time.sleep(POLL_SECONDS)
        if _daemon_ok():
            fails = 0
            continue
        fails += 1
        if fails >= FAIL_THRESHOLD:
            _start_daemon()
            _toast("Demon Mnemos upal i byl perezapushchen.")
            fails = 0
            time.sleep(STARTUP_GRACE)


if __name__ == "__main__":
    raise SystemExit(main())
