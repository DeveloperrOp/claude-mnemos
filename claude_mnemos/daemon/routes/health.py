from __future__ import annotations

import platform
import sys
import time

from fastapi import APIRouter, Request

from claude_mnemos import __version__
from claude_mnemos.daemon.schemas import HealthResponse, SchedulerJobInfo, VersionResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    daemon = request.app.state.daemon
    uptime_s = 0.0
    jobs: list[SchedulerJobInfo] = []
    watchdog_running = False
    alerts_count = 0
    if daemon is not None:
        if getattr(daemon, "started_at_monotonic", 0.0) > 0.0:
            uptime_s = max(0.0, time.monotonic() - daemon.started_at_monotonic)
        if hasattr(daemon, "scheduler_jobs_info"):
            jobs = daemon.scheduler_jobs_info()
        observer = getattr(daemon, "observer", None)
        watchdog_running = bool(observer is not None and observer.is_running)
        alerts = getattr(daemon, "alerts", None)
        if alerts is not None:
            alerts_count = len(alerts.list())
    return HealthResponse(
        status="ok",
        version=__version__,
        vault=str(request.app.state.vault_root),
        uptime_s=uptime_s,
        scheduler_jobs=jobs,
        watchdog_running=watchdog_running,
        alerts_count=alerts_count,
    )


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(
        version=__version__,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
    )
