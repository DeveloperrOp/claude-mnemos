"""Daemon control routes: pause/resume/restart.

Pause/resume halt the JOB QUEUE across all mounted vaults — they reuse the
same per-vault ``job_store.pause_queue``/``resume_queue`` mechanism the
worker already honours (``is_paused``), so the pause actually stops work
instead of flipping a flag nobody read. (The old ``daemon.paused`` flag was
a placebo — set by these routes, read by nothing.)

Restart works by asking uvicorn to shut down gracefully after responding
(``daemon._request_shutdown()`` flips ``server.should_exit``), so
``MnemosDaemon.run()``'s ``finally`` block runs its cleanup (pid-file
removal, runtime unmount, scheduler/job-store flush) before the process
exits — a hard ``os._exit(0)`` would skip that and risk pid residue and
``.jobs.db`` WAL damage on repeated UI restarts. A bounded ``os._exit(0)``
remains only as a last-resort fallback if graceful shutdown wedges. The
tray supervisor's main loop notices the exit and respawns the daemon
process. On macOS / Linux where no tray supervisor is running the UI
will simply lose connection; in that case the user must relaunch the
app manually (the UI hints at this).
"""

from __future__ import annotations

import asyncio
import os
import platform
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

router = APIRouter()

# Restart shutdown timings (module-level so tests can monkeypatch them to 0
# instead of really sleeping for 5.5s in the background task).
_RESPONSE_FLUSH_SLEEP = 0.5  # let the HTTP response flush over loopback first
_GRACEFUL_FALLBACK_SLEEP = 5.0  # grace window before the last-resort os._exit

# "Pause indefinitely" sentinel — the queue stays paused until an explicit
# /daemon/resume (or a rate-limit pause with an earlier reset). is_paused()
# only compares now < until, so a far-future UTC time means "paused".
_PAUSE_SENTINEL = datetime(9999, 1, 1, tzinfo=UTC)


def _job_stores(daemon: object) -> list[Any]:
    stores = []
    for rt in getattr(daemon, "runtimes", {}).values():
        js = getattr(rt, "job_store", None)
        if js is not None:
            stores.append(js)
    return stores


@router.post("/daemon/pause")
def pause_route(request: Request) -> dict[str, Any]:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, "daemon not bound")
    stores = _job_stores(daemon)
    for js in stores:
        js.pause_queue(until=_PAUSE_SENTINEL)
    return {"ok": True, "paused": True, "queues": len(stores)}


@router.post("/daemon/resume")
def resume_route(request: Request) -> dict[str, Any]:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, "daemon not bound")
    stores = _job_stores(daemon)
    resumed = 0
    for js in stores:
        # Only clear a USER pause (the far-future sentinel). A rate-limit
        # pause sets a near-future reset_at; clearing it here would resume
        # dequeuing before the API limit reset and re-trip the 429 immediately.
        until = js.paused_until()
        if until is not None and until >= _PAUSE_SENTINEL:
            js.resume_queue()
            resumed += 1
    return {"ok": True, "paused": False, "queues": len(stores), "resumed": resumed}


def _is_supervised() -> bool:
    """True if a tray supervisor is likely to respawn us after exit.
    Currently: only Windows (tray.supervisor lives there). On macOS the
    user runs the app via launchd plist but there's no supervised
    subprocess relationship for an in-place restart, so we report False
    and let the UI show a 'please relaunch manually' message."""
    return platform.system() == "Windows"


@router.post("/daemon/restart")
async def restart_route(request: Request, background: BackgroundTasks) -> dict[str, Any]:
    """Schedule a clean daemon exit. On supervised setups the tray
    process notices the exit code and respawns us. Returns whether
    the user will need to relaunch manually."""
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, "daemon not bound")
    supervised = _is_supervised()

    async def _shutdown_after_response() -> None:
        # Give the HTTP response time to flush over the loopback socket, then ask
        # uvicorn to exit gracefully so run()'s finally cleans up the pid file,
        # observers and job store (avoids the .jobs.db WAL damage / pid residue
        # that a hard os._exit causes). _request_shutdown only flips
        # server.should_exit (no await), so there is no event-loop deadlock —
        # await self._server.serve() returns and the process exits naturally
        # (the tray supervisor respawns it). os._exit is kept ONLY as a bounded
        # last-resort fallback if graceful shutdown wedges with the server still
        # up, so a restart still happens regardless.
        await asyncio.sleep(_RESPONSE_FLUSH_SLEEP)
        daemon._request_shutdown()
        await asyncio.sleep(_GRACEFUL_FALLBACK_SLEEP)
        # Only force-exit if a live server is still serving (graceful wedged).
        # When serve() already returned, run()'s finally has cleaned up and the
        # loop is torn down — this point is normally unreachable in production.
        if getattr(daemon, "_server", None) is not None:
            os._exit(0)

    background.add_task(_shutdown_after_response)
    return {"ok": True, "supervised": supervised}
