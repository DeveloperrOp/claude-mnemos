"""Daemon control routes: pause/resume.

The supervisor (and the tray menu) calls these to toggle daemon-wide pause
state. Pause-semantics (skip ingest in scheduler/watchdog) are read by
existing components from ``daemon.paused``; this route only flips the flag.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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
