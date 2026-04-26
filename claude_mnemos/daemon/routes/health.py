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
    if daemon is not None:
        if getattr(daemon, "started_at_monotonic", 0.0) > 0.0:
            uptime_s = max(0.0, time.monotonic() - daemon.started_at_monotonic)
        if hasattr(daemon, "scheduler_jobs_info"):
            jobs = daemon.scheduler_jobs_info()
    return HealthResponse(
        status="ok",
        version=__version__,
        vault=str(request.app.state.vault_root),
        uptime_s=uptime_s,
        scheduler_jobs=jobs,
    )


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(
        version=__version__,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
    )
