"""Session view: merged manifest (succeeded ingests) + jobs queue (in-flight)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.core.transcript_helpers import _extract_cwd_and_preview
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, Job, JobStore
from claude_mnemos.state.manifest import IngestRecord, Manifest


class SessionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class SessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: SessionStatus
    transcript_path: str | None
    ingested_at: datetime | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    raw_transcript_bytes: int | None
    created_pages: list[str] = Field(default_factory=list)
    # Pages the extract produced but could NOT write because a same-slug file
    # already existed. Surfaced so the UI can warn "N pages not saved" instead
    # of silently claiming full success (these knowledge bits are lost).
    skipped_collisions: list[str] = Field(default_factory=list)
    error: str | None = None
    cwd: str | None = None
    preview: str | None = None


class SessionNotFoundError(LookupError):
    """Raised by `get_session` when the requested session_id is unknown."""


# Map JobStore status strings to SessionStatus members.
_JOB_STATUS_TO_SESSION_STATUS: dict[str, SessionStatus] = {
    "queued": SessionStatus.QUEUED,
    "running": SessionStatus.RUNNING,
    "failed": SessionStatus.FAILED,
    "dead_letter": SessionStatus.DEAD_LETTER,
    # "succeeded" jobs are not surfaced from the queue — manifest is the
    # source of truth for completed ingests.
}


def _safe_cwd_preview(transcript_path: str | None) -> tuple[str | None, str | None]:
    """Best-effort cwd+preview lookup; tolerate missing/unreadable transcript."""
    if not transcript_path:
        return None, None
    try:
        path = Path(transcript_path)
        if not path.is_file():
            return None, None
        return _extract_cwd_and_preview(path)
    except OSError:
        return None, None


def _session_view_from_record(record: IngestRecord) -> SessionView:
    cwd, preview = _safe_cwd_preview(record.transcript_path)
    return SessionView(
        session_id=record.session_id,
        status=SessionStatus.SUCCEEDED,
        transcript_path=record.transcript_path,
        ingested_at=record.ingested_at,
        model=record.model,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        raw_transcript_bytes=record.raw_transcript_bytes,
        created_pages=list(record.created_pages),
        skipped_collisions=list(record.skipped_collisions),
        error=None,
        cwd=cwd,
        preview=preview,
    )


def _sid_from_job(job: Job) -> str:
    """Derive a stable session_id from a job's payload.

    Prefers the transcript filename stem; falls back to a short prefix of the
    job id when no transcript_path is recorded. The fallback shape mirrors
    the design doc — `job-<8-hex>` — so dashboards have a deterministic
    label even for malformed payloads.
    """
    raw = job.payload.get("transcript_path", "")
    if isinstance(raw, str) and raw:
        stem = Path(raw).stem
        if stem:
            return stem
    return f"job-{job.id[:8]}"


def _session_view_from_job(job: Job) -> SessionView | None:
    status = _JOB_STATUS_TO_SESSION_STATUS.get(job.status)
    if status is None:
        return None
    raw = job.payload.get("transcript_path", "")
    transcript_path = raw if isinstance(raw, str) and raw else None
    cwd, preview = _safe_cwd_preview(transcript_path)
    return SessionView(
        session_id=_sid_from_job(job),
        status=status,
        transcript_path=transcript_path,
        ingested_at=None,
        model=None,
        input_tokens=None,
        output_tokens=None,
        raw_transcript_bytes=None,
        created_pages=[],
        error=job.error,
        cwd=cwd,
        preview=preview,
    )


# Sort key fallback for entries without a real timestamp (jobs in flight or
# manifest entries with a missing ingested_at — the latter shouldn't happen
# in practice but keeps types honest).
_MIN_DT = datetime.min.replace(tzinfo=UTC)


def list_sessions(vault: Path) -> list[SessionView]:
    """Return SessionView entries merged from the manifest and the jobs queue.

    Succeeded entries (from the manifest) take precedence over in-flight or
    dead-letter jobs that share a session_id (re-ingest scenario). Output is
    ordered newest-first using ``ingested_at`` for succeeded entries and
    ``created_at`` for jobs.
    """
    manifest = Manifest.load(vault)

    succeeded_views: list[SessionView] = []
    succeeded_sids: set[str] = set()
    for record in manifest.ingested.values():
        view = _session_view_from_record(record)
        succeeded_views.append(view)
        succeeded_sids.add(view.session_id)

    # Pair each job-derived view with its created_at for stable sorting,
    # then drop the timestamp before merging into the final list.
    pending: list[tuple[datetime, SessionView]] = []

    db_path = vault / JOBS_DB_FILENAME
    if db_path.is_file():
        with JobStore(db_path) as store:
            for job in store.list_by_status(None, limit=10_000):
                if job.kind != "ingest":
                    continue
                job_view = _session_view_from_job(job)
                if job_view is None:
                    continue
                if job_view.session_id in succeeded_sids:
                    # Succeeded wins (Plan #13a §3.2 conflict resolution).
                    continue
                pending.append((job.created_at, job_view))

    succeeded_views.sort(
        key=lambda v: v.ingested_at or _MIN_DT,
        reverse=True,
    )
    pending.sort(key=lambda pair: pair[0], reverse=True)

    return succeeded_views + [view for _, view in pending]


def get_session(vault: Path, session_id: str) -> SessionView:
    """Return the SessionView for ``session_id``.

    Raises:
        SessionNotFoundError: when no manifest entry or job matches.
    """
    for view in list_sessions(vault):
        if view.session_id == session_id:
            return view
    raise SessionNotFoundError(session_id)
