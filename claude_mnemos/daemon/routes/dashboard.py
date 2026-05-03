"""REST aggregator endpoints for the operational Overview dashboard.

Single endpoint /api/dashboard/snapshot wraps three hot data sources
(KPI, active sessions, running jobs) in per-aggregator try/except so a
single failure does not nuke the whole response.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core.active_sessions import scan_active_sessions
from claude_mnemos.core.transcript_scanner import (
    invalidate_transcripts_cache,
    scan_transcripts as _scan_transcripts_async,
)
from claude_mnemos.daemon.routes._helpers import all_runtimes, get_runtime
from claude_mnemos.state.manifest import Manifest

router = APIRouter()
log = logging.getLogger(__name__)


_INGEST_OPS = {"ingest_extracted", "ingest_raw_only"}


def _kpi_for(runtimes: list[Any]) -> dict[str, Any]:
    queue = {"queued": 0, "running": 0, "failed": 0}
    today_ingest = 0
    today_pages = 0
    today_start = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    for rt in runtimes:
        if rt.job_store is None:
            continue
        try:
            counts = rt.job_store.count_by_status()
            queue["queued"] += counts.get("queued", 0)
            queue["running"] += counts.get("running", 0)
            queue["failed"] += counts.get("failed_permanent", 0)
        except Exception as exc:
            log.debug("kpi job-status read failed for %s: %s", rt.name, exc)

        try:
            from claude_mnemos.state.activity import ActivityLog
            entries = ActivityLog.load(rt.vault_root).entries
            for entry in entries:
                if entry.timestamp < today_start:
                    continue
                if entry.operation_type in _INGEST_OPS:
                    today_ingest += 1
                    today_pages += len(entry.affected_pages)
        except Exception as exc:
            log.debug("kpi activity-read failed for %s: %s", rt.name, exc)

    return {
        "queue": queue,
        "today": {"ingest_count": today_ingest, "pages_count": today_pages},
        # TODO(v2): tokens_today aggregator from inject_metrics
        "tokens_today": 0,
        "lost_total": 0,
    }


async def _compute_lost_total(runtimes: list[Any]) -> int:
    """Count of transcripts not ingested in any vault.

    Same union-manifest approach as scan_active_sessions, no mtime filter.
    """
    entries = await _scan_transcripts_async()
    if not entries:
        return 0
    ingested: set[str] = set()
    for rt in runtimes:
        try:
            m = Manifest.load(rt.vault_root)
        except Exception as exc:
            log.debug("lost_total manifest-load failed for %s: %s", rt.name, exc)
            continue
        ingested.update(m.ingested.keys())
    return sum(1 for e in entries if e.sha not in ingested)


def _running_jobs_for(runtimes: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rt in runtimes:
        if rt.job_store is None:
            continue
        try:
            for job in rt.job_store.list_by_status("running"):
                d = job.model_dump(mode="json")
                d["project_name"] = rt.name
                out.append(d)
        except Exception as exc:
            log.warning("running_jobs read failed for %s: %s", rt.name, exc)
    return out


@router.get("/dashboard/snapshot")
async def dashboard_snapshot(request: Request) -> dict[str, Any]:
    """Single-call aggregator for the Overview dashboard.

    Per-aggregator try/except — partial data + errors[] on failure.
    """
    runtimes = list(all_runtimes(request))
    errors: list[str] = []
    kpi: dict[str, Any] = {
        "queue": {"queued": 0, "running": 0, "failed": 0},
        "active": {"hot": 0, "cooling": 0},
        "today": {"ingest_count": 0, "pages_count": 0},
        "tokens_today": 0,
        "lost_total": 0,
    }
    active_sessions: list[dict[str, Any]] = []
    running_jobs: list[dict[str, Any]] = []

    try:
        kpi.update(_kpi_for(runtimes))
    except Exception as exc:
        log.warning("kpi aggregator failed: %s", exc)
        errors.append(f"kpi: {exc}")

    try:
        kpi["lost_total"] = await _compute_lost_total(runtimes)
    except Exception as exc:
        log.warning("lost_total aggregator failed: %s", exc)
        errors.append(f"lost_total: {exc}")

    try:
        sessions = await scan_active_sessions(runtimes)
        active_sessions = [s.model_dump(mode="json") for s in sessions]
        kpi["active"]["hot"] = sum(1 for s in sessions if s.status == "hot")
        kpi["active"]["cooling"] = sum(1 for s in sessions if s.status == "cooling")
    except Exception as exc:
        log.warning("active_sessions aggregator failed: %s", exc)
        errors.append(f"active_sessions: {exc}")

    try:
        running_jobs = _running_jobs_for(runtimes)
    except Exception as exc:
        log.warning("running_jobs aggregator failed: %s", exc)
        errors.append(f"running_jobs: {exc}")

    return {
        "kpi": kpi,
        "active_sessions": active_sessions,
        "running_jobs": running_jobs,
        "errors": errors,
    }


@router.post("/dashboard/active-sessions/{session_id}/dump-now", status_code=201)
async def dump_now_route(
    session_id: str, request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(status_code=422, detail={"error": "missing_project_name"})
    runtime = get_runtime(request, project_name)
    if runtime.job_store is None:
        raise HTTPException(status_code=503, detail={"error": "vault_unavailable"})
    sessions = await scan_active_sessions([runtime])
    match = next((s for s in sessions if s.session_id == session_id), None)
    if match is None:
        raise HTTPException(
            status_code=404, detail={"error": "active_session_not_found"}
        )
    job = runtime.job_store.create(
        kind="ingest",
        payload={"transcript_path": match.transcript_path, "extract": False},
    )
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    return job.model_dump(mode="json")


@router.post("/dashboard/scan-active")
async def scan_active_route(request: Request) -> dict[str, Any]:
    invalidate_transcripts_cache()
    runtimes = list(all_runtimes(request))
    sessions = await scan_active_sessions(runtimes)
    return {"scanned": len(sessions)}
