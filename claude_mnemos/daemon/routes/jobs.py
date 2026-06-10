from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, Response

from claude_mnemos.core.transcript_helpers import _resolve_transcripts_root
from claude_mnemos.daemon.routes._helpers import all_runtimes, get_runtime

router = APIRouter()


@router.post("/jobs", status_code=201)
async def create_job(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, detail={"error": "daemon_unavailable"})

    kind = body.get("kind")
    payload = body.get("payload", {})
    if kind != "ingest":
        raise HTTPException(400, detail={"error": "unknown_kind", "kind": kind})
    if not isinstance(payload, dict):
        raise HTTPException(400, detail={"error": "payload_must_be_object"})

    project_name = payload.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(400, detail={"error": "missing_project_name"})

    runtimes = getattr(daemon, "runtimes", None)
    if runtimes is None:
        raise HTTPException(503, detail={"error": "jobs_subsystem_unavailable"})

    runtime = runtimes.get(project_name)
    if runtime is None:
        raise HTTPException(
            400,
            detail={"error": "unknown_project", "project_name": project_name},
        )

    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        raise HTTPException(400, detail={"error": "missing_transcript_path"})
    if not Path(transcript_path).is_file():
        raise HTTPException(
            400,
            detail={
                "error": "transcript_not_found",
                "transcript_path": transcript_path,
            },
        )
    # Path traversal: the daemon is local-only, but any local process can
    # POST here — without this check an arbitrary readable file would be
    # ingested into the vault (and shipped to the LLM on extract). Same
    # check as routes/sessions.py and routes/lost_sessions.py.
    #
    # normcase both sides before comparing: on Windows resolve() preserves the
    # drive/dir letter case as typed, so "C:\Users\Yaroslav\..." vs a home of
    # "C:\Users\yaroslav" would spuriously fail relative_to and 400 a legit
    # file. normcase lowercases on Windows, no-op on POSIX.
    root = _resolve_transcripts_root(None).resolve()
    root_cmp = os.path.normcase(str(root))
    tp_cmp = os.path.normcase(str(Path(transcript_path).resolve()))
    try:
        outside = os.path.commonpath([root_cmp, tp_cmp]) != root_cmp
    except ValueError:
        # Different drives (Windows) → no common path → definitely outside.
        outside = True
    if outside:
        raise HTTPException(
            400,
            detail={
                "error": "transcript_outside_root",
                "detail": f"transcript_path must be under {root}",
            },
        )

    try:
        job = runtime.job_store.create(kind=kind, payload=payload)
    except sqlite3.ProgrammingError as exc:
        raise HTTPException(
            503,
            detail={
                "error": "vault_unavailable",
                "project_name": project_name,
                "detail": str(exc),
            },
        ) from exc
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    return cast(dict[str, Any], job.model_dump(mode="json"))


@router.get("/jobs")
async def list_jobs(
    request: Request,
    project: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    daemon = request.app.state.daemon
    if daemon is None:
        return {"jobs": [], "counts": {}}

    if project is not None:
        runtime = get_runtime(request, project)
        store = runtime.job_store
        if store is None:
            return {"jobs": [], "counts": {}}
        jobs = store.list_by_status(status, limit=limit, offset=offset)  # type: ignore[arg-type]
        counts = store.count_by_status()
        return {
            "jobs": [
                {**j.model_dump(mode="json"), "project_name": project}
                for j in jobs
            ],
            "counts": counts,
        }

    # Cross-vault aggregation.
    # Per-store offset is meaningless when the cross-vault sort key can order
    # items from different vaults interleaved.  We must load all items from
    # every store, merge, sort globally, then apply (offset, limit) to the
    # combined list.  _CROSS_VAULT_MAX is a safety cap; real-world job queues
    # are small, so this is acceptable.
    _CROSS_VAULT_MAX = 100_000
    aggregated_jobs: list[dict[str, Any]] = []
    aggregated_counts: dict[str, int] = {}
    for runtime in all_runtimes(request):
        store = runtime.job_store
        if store is None:
            continue
        jobs = store.list_by_status(status, limit=_CROSS_VAULT_MAX, offset=0)  # type: ignore[arg-type]
        for j in jobs:
            d = j.model_dump(mode="json")
            d["project_name"] = runtime.name
            aggregated_jobs.append(d)
        for k, v in store.count_by_status().items():
            aggregated_counts[k] = aggregated_counts.get(k, 0) + v
    # Secondary sort on id ensures a fully deterministic order when created_at
    # timestamps tie (sub-microsecond races during seeding or rapid creation).
    aggregated_jobs.sort(key=lambda x: (x["created_at"], x["id"]), reverse=True)
    return {
        "jobs": aggregated_jobs[offset : offset + limit],
        "counts": aggregated_counts,
    }


def _find_job_owner(
    request: Request, job_id: str
) -> tuple[Any, Any]:
    """Iterate runtimes, return (runtime, job) for the owning store. 404 if none."""
    for runtime in all_runtimes(request):
        store = runtime.job_store
        if store is None:
            continue
        job = store.get_by_id(job_id)
        if job is not None:
            return runtime, job
    raise HTTPException(
        status_code=404, detail={"error": "not_found", "job_id": job_id}
    )


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    runtime, job = _find_job_owner(request, job_id)
    d = job.model_dump(mode="json")
    d["project_name"] = runtime.name
    return cast(dict[str, Any], d)


@router.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str, request: Request) -> Response:
    runtime, job = _find_job_owner(request, job_id)
    if job.status != "queued":
        raise HTTPException(
            status_code=409,
            detail={"error": "not_queued", "current_status": job.status},
        )
    if not runtime.job_store.cancel_queued(job_id):
        raise HTTPException(status_code=409, detail={"error": "race_lost"})
    return Response(status_code=204)
