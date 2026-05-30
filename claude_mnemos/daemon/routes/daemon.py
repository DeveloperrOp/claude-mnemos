"""Daemon control routes: pause/resume/restart.

The supervisor (and the tray menu) calls these to toggle daemon-wide pause
state. Pause-semantics (skip ingest in scheduler/watchdog) are read by
existing components from ``daemon.paused``; this route only flips the flag.

Restart works by exiting cleanly (`os._exit(0)`) after responding — the
tray supervisor's main loop notices the exit and respawns the daemon
process. On macOS / Linux where no tray supervisor is running the UI
will simply lose connection; in that case the user must relaunch the
app manually (the UI hints at this).
"""

from __future__ import annotations

import asyncio
import os
import platform

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

router = APIRouter()


@router.post("/daemon/pause")
def pause_route(request: Request) -> dict:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, "daemon not bound")
    daemon.paused = True
    return {"ok": True, "paused": True}


@router.post("/daemon/resume")
def resume_route(request: Request) -> dict:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, "daemon not bound")
    daemon.paused = False
    return {"ok": True, "paused": False}


def _is_supervised() -> bool:
    """True if a tray supervisor is likely to respawn us after exit.
    Currently: only Windows (tray.supervisor lives there). On macOS the
    user runs the app via launchd plist but there's no supervised
    subprocess relationship for an in-place restart, so we report False
    and let the UI show a 'please relaunch manually' message."""
    return platform.system() == "Windows"


@router.post("/daemon/restart")
async def restart_route(request: Request, background: BackgroundTasks) -> dict:
    """Schedule a clean daemon exit. On supervised setups the tray
    process notices the exit code and respawns us. Returns whether
    the user will need to relaunch manually."""
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, "daemon not bound")
    supervised = _is_supervised()

    async def _shutdown_after_response() -> None:
        # Give the HTTP response 0.5s to flush over the loopback socket
        # before we tear the process down. os._exit (not sys.exit) so
        # FastAPI's lifespan shutdown handlers don't deadlock on the
        # event loop we're still on.
        await asyncio.sleep(0.5)
        os._exit(0)

    background.add_task(_shutdown_after_response)
    return {"ok": True, "supervised": supervised}
