"""REST routes for session lifecycle (Plan #13b-β2 §3.1 Task 2).

Per-project endpoints under ``/sessions/{project}/...``. The project name is
resolved to a ``VaultRuntime`` via :func:`get_runtime`; unknown projects yield
HTTP 404 ``unknown_project`` (not 503).

Read paths (list, get) use only ``runtime.vault_root`` and are safe even when
the job subsystem is not running. The ingest endpoint requires
``runtime.job_store`` and returns 503 when it is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import sessions as core_sessions
from claude_mnemos.core.transcript_helpers import _resolve_transcripts_root
from claude_mnemos.daemon.routes._helpers import get_runtime
from claude_mnemos.state.jobs import JobStore

router = APIRouter()


@router.get("/sessions/{project}")
async def list_sessions_route(
    project: str,
    request: Request,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List session views for *project*, optionally filtered by status.

    ``total`` reflects the size *after* status filtering but *before* the
    limit cut so the dashboard can display "showing N of M".
    """
    runtime = get_runtime(request, project)
    items = core_sessions.list_sessions(runtime.vault_root)
    if status:
        items = [s for s in items if s.status.value == status]
    return {
        "sessions": [s.model_dump(mode="json") for s in items[:limit]],
        "total": len(items),
    }


@router.get("/sessions/{project}/{session_id}")
async def get_session_route(
    project: str,
    session_id: str,
    request: Request,
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    try:
        session = core_sessions.get_session(runtime.vault_root, session_id)
    except core_sessions.SessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "session_id": session_id},
        ) from exc
    return session.model_dump(mode="json")


@router.post("/sessions/{project}/{session_id}/ingest", status_code=201)
async def ingest_session_route(
    project: str,
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Enqueue an ingest job for *session_id* within *project*.

    Body must contain ``transcript_path`` pointing to an existing file. The
    ``session_id`` path parameter is informational — the actual session_id is
    derived downstream from the transcript filename — but is preserved in the
    URL for symmetry with GET.
    """
    del session_id  # informational only; payload carries the path
    runtime = get_runtime(request, project)
    transcript_path = body.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_or_invalid_transcript_path",
                "message": "Путь к файлу транскрипта не указан или невалидный.",
            },
        )
    if not Path(transcript_path).is_file():
        # The most common case in production: Claude Code or a cleanup
        # job deleted the original .jsonl (e.g. subagent transcripts are
        # ephemeral). The session record in our DB still points at the
        # old path. The previous error message ("Request failed with
        # status code 400") was opaque; spell it out.
        raise HTTPException(
            status_code=400,
            detail={
                "error": "transcript_file_missing",
                "message": (
                    "Файл транскрипта чата не найден на диске. "
                    "Возможно Claude Code удалил его (subagent-сессии и "
                    "очень старые чаты чистятся автоматически). "
                    "Эта сессия больше не может быть переингестирована."
                ),
                "path": transcript_path,
            },
        )
    # Reject path-traversal: client-supplied path must live under the
    # canonical transcripts root (MNEMOS_TRANSCRIPTS_ROOT or
    # ~/.claude/projects/).
    root = _resolve_transcripts_root(None).resolve()
    try:
        Path(transcript_path).resolve().relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "transcript_outside_root",
                "detail": f"transcript_path must be under {root}",
            },
        ) from exc
    if runtime.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "vault_unavailable", "project": project},
        )
    # v0.0.10: ``extract`` is now an explicit body field with a False default.
    # Pre-v0.0.10 omitting it meant ``payload.get("extract", True)`` in the
    # worker — silently spending LLM tokens. Callers (UI buttons, scripts)
    # must opt in by passing ``extract: true`` if they want extraction.
    extract = bool(body.get("extract", False))
    # Task 9: per-session ingest controls.
    #   max_input_tokens — raise the model's input budget for one oversized
    #     session (>= 1024; a tinier budget extracts nothing).
    #   chunk_extract — split-and-merge an over-budget transcript instead of
    #     dead-lettering it.
    # Both are threaded into the job payload only when provided, so callers
    # that omit them keep the pre-Task-9 payload shape.
    payload: dict[str, Any] = {"transcript_path": transcript_path, "extract": extract}
    max_input_tokens = body.get("max_input_tokens")
    if max_input_tokens is not None:
        if not isinstance(max_input_tokens, int) or isinstance(max_input_tokens, bool):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_max_input_tokens",
                    "message": "max_input_tokens должен быть целым числом >= 1024.",
                },
            )
        if max_input_tokens < 1024:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_max_input_tokens",
                    "message": "max_input_tokens слишком мал (минимум 1024).",
                },
            )
        payload["max_input_tokens"] = max_input_tokens
    if bool(body.get("chunk_extract", False)):
        payload["chunk_extract"] = True
    store: JobStore = runtime.job_store
    job = store.create(kind="ingest", payload=payload)
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    dumped: dict[str, Any] = job.model_dump(mode="json")
    return dumped
