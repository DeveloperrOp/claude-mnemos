from __future__ import annotations

import platform
import sys
import time
from datetime import datetime

from fastapi import APIRouter, Request

from claude_mnemos import __version__
from claude_mnemos.daemon.schemas import (
    HealthResponse,
    SchedulerJobInfo,
    VaultHealth,
    VersionResponse,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    daemon = request.app.state.daemon
    uptime_s = 0.0
    jobs: list[SchedulerJobInfo] = []
    alerts_count = 0
    vaults: dict[str, VaultHealth] = {}
    total_dead_letter = 0
    paused_until_set: list[datetime] = []
    if daemon is not None:
        if getattr(daemon, "started_at_monotonic", 0.0) > 0.0:
            uptime_s = max(0.0, time.monotonic() - daemon.started_at_monotonic)
        if hasattr(daemon, "scheduler_jobs_info"):
            jobs = daemon.scheduler_jobs_info()
        alerts = getattr(daemon, "alerts", None)
        if alerts is not None:
            alerts_count = len(alerts.list())
        runtimes: dict[str, object] = getattr(daemon, "runtimes", {}) or {}
        for name, runtime in sorted(runtimes.items()):
            observer = getattr(runtime, "observer", None)
            store = getattr(runtime, "job_store", None)
            counts: dict[str, int] = {}
            if store is not None:
                try:
                    counts = store.count_by_status()
                except Exception:
                    counts = {}
                try:
                    paused = store.paused_until()
                except Exception:
                    paused = None
                if paused is not None:
                    paused_until_set.append(paused)
            vh_dead = int(counts.get("dead_letter", 0))
            total_dead_letter += vh_dead
            vaults[name] = VaultHealth(
                watchdog_running=bool(observer is not None and observer.is_running),
                jobs_queued=int(counts.get("queued", 0)),
                jobs_running=int(counts.get("running", 0)),
                jobs_dead_letter=vh_dead,
            )
    jobs_alert = total_dead_letter > 10
    degraded = jobs_alert or any(
        not v.watchdog_running for v in vaults.values()
    )
    queue_paused_until = max(paused_until_set) if paused_until_set else None
    return HealthResponse(
        status="degraded" if degraded else "ok",
        version=__version__,
        uptime_s=uptime_s,
        scheduler_jobs=jobs,
        alerts_count=alerts_count,
        vaults=vaults,
        jobs_alert=jobs_alert,
        queue_paused_until=queue_paused_until,
    )


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(
        version=__version__,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
    )
