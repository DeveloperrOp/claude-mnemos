"""Tests for `claude_mnemos.core.sessions` — merged manifest + jobs view."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.sessions import (
    SessionNotFoundError,
    SessionStatus,
    SessionView,
    get_session,
    list_sessions,
)
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.manifest import IngestRecord, Manifest


def _ingest_record(
    sid: str,
    *,
    ingested_at: datetime,
    transcript_path: str | None = None,
    raw_transcript_bytes: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    model: str | None = None,
    created_pages: list[str] | None = None,
) -> IngestRecord:
    return IngestRecord(
        session_id=sid,
        ingested_at=ingested_at,
        raw_path=f"raw/chats/{sid}.md",
        source_path=f"wiki/sources/{sid}.md",
        created_pages=created_pages or [],
        skipped_collisions=[],
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        transcript_path=transcript_path,
        raw_transcript_bytes=raw_transcript_bytes,
    )


def test_list_sessions_empty_vault_returns_empty_list(tmp_path: Path) -> None:
    assert list_sessions(tmp_path) == []


def test_list_sessions_two_succeeded_sorted_desc(tmp_path: Path) -> None:
    older = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    newer = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)

    m = Manifest()
    m.add("sha-old", _ingest_record("old-sid", ingested_at=older))
    m.add("sha-new", _ingest_record("new-sid", ingested_at=newer))
    m.save(tmp_path)

    result = list_sessions(tmp_path)
    assert len(result) == 2
    assert all(isinstance(s, SessionView) for s in result)
    assert all(s.status == SessionStatus.SUCCEEDED for s in result)
    # Newest first
    assert result[0].session_id == "new-sid"
    assert result[1].session_id == "old-sid"
    assert result[0].ingested_at == newer
    assert result[1].ingested_at == older


def test_list_sessions_succeeded_plus_queued_job_different_sids(
    tmp_path: Path,
) -> None:
    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "ok-sid", ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
        ),
    )
    m.save(tmp_path)

    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        store.create(
            kind="ingest",
            payload={"transcript_path": "/abs/path/queued-sid.jsonl"},
        )

    result = list_sessions(tmp_path)
    assert len(result) == 2

    succeeded = [s for s in result if s.status == SessionStatus.SUCCEEDED]
    queued = [s for s in result if s.status == SessionStatus.QUEUED]
    assert len(succeeded) == 1
    assert len(queued) == 1
    assert succeeded[0].session_id == "ok-sid"
    assert queued[0].session_id == "queued-sid"
    assert queued[0].transcript_path == "/abs/path/queued-sid.jsonl"
    assert queued[0].ingested_at is None


def test_list_sessions_succeeded_wins_over_dead_letter_same_sid(
    tmp_path: Path,
) -> None:
    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "shared-sid", ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
        ),
    )
    m.save(tmp_path)

    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        job = store.create(
            kind="ingest",
            payload={"transcript_path": "/abs/path/shared-sid.jsonl"},
        )
        # Force into dead_letter status
        store.mark_failed_with_retry(
            job.id,
            error="boom",
            traceback="tb",
            finished_at=datetime.now(UTC),
        )
        # Multiple retries to get to dead_letter (MAX_ATTEMPTS=4)
        for _ in range(4):
            current = store.get_by_id(job.id)
            assert current is not None
            if current.status == "dead_letter":
                break
            # If queued (after retry), claim and fail again
            if current.status == "queued":
                # Bypass timing — directly mark failed again
                store.mark_failed_with_retry(
                    job.id,
                    error="boom",
                    traceback="tb",
                    finished_at=datetime.now(UTC),
                )

    result = list_sessions(tmp_path)
    assert len(result) == 1
    assert result[0].session_id == "shared-sid"
    assert result[0].status == SessionStatus.SUCCEEDED


def test_get_session_raises_session_not_found_error(tmp_path: Path) -> None:
    with pytest.raises(SessionNotFoundError):
        get_session(tmp_path, "missing-sid")


def test_get_session_returns_existing(tmp_path: Path) -> None:
    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "real-sid",
            ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
            input_tokens=100,
            output_tokens=200,
            model="claude-sonnet-4-6",
        ),
    )
    m.save(tmp_path)

    result = get_session(tmp_path, "real-sid")
    assert result.session_id == "real-sid"
    assert result.status == SessionStatus.SUCCEEDED
    assert result.input_tokens == 100
    assert result.output_tokens == 200
    assert result.model == "claude-sonnet-4-6"


def test_session_view_surfaces_new_ingest_record_fields(tmp_path: Path) -> None:
    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "rich-sid",
            ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
            transcript_path="/abs/path/rich-sid.jsonl",
            raw_transcript_bytes=98765,
            created_pages=["wiki/sources/x.md", "wiki/entities/y.md"],
        ),
    )
    m.save(tmp_path)

    result = list_sessions(tmp_path)
    assert len(result) == 1
    view = result[0]
    assert view.transcript_path == "/abs/path/rich-sid.jsonl"
    assert view.raw_transcript_bytes == 98765
    assert view.created_pages == ["wiki/sources/x.md", "wiki/entities/y.md"]
    assert view.error is None


def test_list_sessions_job_without_transcript_path_falls_back_to_id(
    tmp_path: Path,
) -> None:
    """Job missing transcript_path → session_id derived from job id."""
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        job = store.create(kind="ingest", payload={})

    result = list_sessions(tmp_path)
    assert len(result) == 1
    expected_sid = f"job-{job.id[:8]}"
    assert result[0].session_id == expected_sid
    assert result[0].status == SessionStatus.QUEUED
    assert result[0].transcript_path is None


def test_session_view_populates_cwd_and_preview_from_transcript(
    tmp_path: Path,
) -> None:
    """Succeeded SessionView includes cwd+preview parsed from the transcript file."""
    import json

    transcript = tmp_path / "rich-sid.jsonl"
    transcript.write_text(
        "\n".join([
            json.dumps({"type": "user", "cwd": "/home/u/proj", "content": "hi there"}),
        ]),
        encoding="utf-8",
    )

    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "rich-sid",
            ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
            transcript_path=str(transcript),
        ),
    )
    m.save(tmp_path)

    result = list_sessions(tmp_path)
    assert len(result) == 1
    view = result[0]
    assert view.cwd == "/home/u/proj"
    assert view.preview == "hi there"


def test_session_view_cwd_preview_none_when_transcript_missing(
    tmp_path: Path,
) -> None:
    """SessionView tolerates missing/None transcript_path → cwd/preview both None."""
    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "no-tp",
            ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
            transcript_path=None,
        ),
    )
    m.add(
        "sha-2",
        _ingest_record(
            "bad-tp",
            ingested_at=datetime(2026, 4, 26, 13, 0, 0, tzinfo=UTC),
            transcript_path="/no/such/file.jsonl",
        ),
    )
    m.save(tmp_path)

    result = list_sessions(tmp_path)
    assert len(result) == 2
    for view in result:
        assert view.cwd is None
        assert view.preview is None


def test_list_sessions_dead_letter_propagates_error(tmp_path: Path) -> None:
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        job = store.create(
            kind="ingest",
            payload={"transcript_path": "/abs/path/dl-sid.jsonl"},
        )
        # Drive job into dead_letter
        for _ in range(4):
            current = store.get_by_id(job.id)
            assert current is not None
            if current.status == "dead_letter":
                break
            store.mark_failed_with_retry(
                job.id,
                error="exploded",
                traceback="tb",
                finished_at=datetime.now(UTC),
            )

    result = list_sessions(tmp_path)
    assert len(result) == 1
    assert result[0].status == SessionStatus.DEAD_LETTER
    assert result[0].error == "exploded"
    assert result[0].session_id == "dl-sid"
