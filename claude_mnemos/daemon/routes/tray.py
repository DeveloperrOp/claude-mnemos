"""Tray + autostart HTTP API.

POST /tray/install     — exec `mnemos tray install`
POST /tray/uninstall   — exec `mnemos tray uninstall`
GET  /tray/status      — autostart status + tray PID + daemon PID
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import psutil
from fastapi import APIRouter, HTTPException

from claude_mnemos import runtime
from claude_mnemos.daemon.lockfile import is_daemon_running
from claude_mnemos.tray.__main__ import (
    DAEMON_PID_FILE,
    TRAY_PID_FILE,
)
from claude_mnemos.tray.__main__ import (
    _resolve_target as _resolve_target,
)
from claude_mnemos.tray.platform import (
    get_autostart_manager,
    platform_label,
)

router = APIRouter(prefix="/tray", tags=["tray"])


def _exec_tray(action: str) -> None:
    if runtime.is_frozen():
        # Bundled exe parses its own subcommands; `-m claude_mnemos ...`
        # exits 2 → every dashboard autostart toggle answered HTTP 500 on
        # installs without a `mnemos` on PATH.
        cmd = [sys.executable, "tray", action]
    else:
        mnemos_exe = shutil.which("mnemos")
        if mnemos_exe:
            cmd = [mnemos_exe, "tray", action]
        else:
            cmd = [sys.executable, "-m", "claude_mnemos", "tray", action]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.stderr or result.stdout or "tray subprocess failed").strip(),
        )


@router.post("/install")
def install() -> dict[str, bool]:
    if platform_label() not in ("windows", "macos"):
        raise HTTPException(status_code=501, detail="Autostart not supported on this platform")
    _exec_tray("install")
    return {"installed": True}


@router.post("/uninstall")
def uninstall() -> dict[str, bool]:
    if platform_label() not in ("windows", "macos"):
        raise HTTPException(status_code=501, detail="Autostart not supported on this platform")
    _exec_tray("uninstall")
    return {"installed": False}


@router.get("/status")
def status() -> dict[str, object]:
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
    return {
        "platform": platform_label(),
        "autostart_enabled": s.installed,
        "autostart_path": s.path,
        "tray_running": tray_pid is not None,
        "tray_pid": tray_pid,
        "daemon_pid": is_daemon_running(DAEMON_PID_FILE),
    }
