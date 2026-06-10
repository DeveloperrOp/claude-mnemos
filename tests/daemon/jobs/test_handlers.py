from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.daemon.jobs.handlers import IngestHandler
from claude_mnemos.ingest.transcript import (
    CorruptTranscriptError,
    EmptyTranscriptError,
)
from claude_mnemos.state.jobs import Job


def _job(payload: dict) -> Job:
    return Job(
        id="abc",
        kind="ingest",
        payload=payload,
        status="running",
        attempt=0,
        next_attempt_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_ingest_handler_invokes_ingest_with_payload(tmp_path: Path):
    calls: list[dict] = []

    def fake_ingest(
        jsonl_path,
        vault_root,
        *,
        cfg,
        llm_client,
        extract,
        dry_run,
        today,
        raw_filename_suffix="",
        **kwargs,
    ):
        calls.append(
            {
                "jsonl_path": jsonl_path,
                "vault_root": vault_root,
                "extract": extract,
                "dry_run": dry_run,
                "llm_client": llm_client,
            }
        )

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: None,
        ingest_fn=fake_ingest,
    )
    await handler.run(_job({"transcript_path": str(tmp_path / "session.jsonl")}))

    assert len(calls) == 1
    assert calls[0]["vault_root"] == tmp_path
    # extract downgraded to False because llm_factory returned None (no API key)
    assert calls[0]["extract"] is False
    assert calls[0]["dry_run"] is False
    assert calls[0]["llm_client"] is None


@pytest.mark.asyncio
async def test_ingest_handler_propagates_exception(tmp_path: Path):
    def boom(*args, **kwargs):
        raise RuntimeError("ingest failed")

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: None,
        ingest_fn=boom,
    )
    with pytest.raises(RuntimeError, match="ingest failed"):
        await handler.run(_job({"transcript_path": "/x.jsonl"}))


@pytest.mark.asyncio
async def test_ingest_handler_swallows_empty_transcript(tmp_path: Path):
    """A pure-tool session (no text messages) must NOT be a retryable failure —
    returning normally marks the job succeeded instead of burning 4 retries
    and dead-lettering with a cryptic 'no message entries' the user can't fix."""
    def empty(*args, **kwargs):
        raise EmptyTranscriptError("no message entries in /x.jsonl")

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: None,
        ingest_fn=empty,
    )
    # Must NOT raise — job completes as a no-op success.
    await handler.run(_job({"transcript_path": "/x.jsonl"}))


@pytest.mark.asyncio
async def test_ingest_handler_propagates_corrupt_transcript(tmp_path: Path):
    """A fully-corrupt JSONL must NOT be swallowed as success (that would hide
    data loss) — CorruptTranscriptError propagates so the job dead-letters."""
    def corrupt(*args, **kwargs):
        raise CorruptTranscriptError("no parseable JSON lines in /x.jsonl")

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: None,
        ingest_fn=corrupt,
    )
    with pytest.raises(CorruptTranscriptError):
        await handler.run(_job({"transcript_path": "/x.jsonl"}))


@pytest.mark.asyncio
async def test_ingest_handler_payload_overrides(tmp_path: Path):
    seen: dict = {}

    def fake_ingest(
        jsonl_path,
        vault_root,
        *,
        cfg,
        llm_client,
        extract,
        dry_run,
        today,
        raw_filename_suffix="",
        **kwargs,
    ):
        seen["extract"] = extract
        seen["dry_run"] = dry_run

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: None,
        ingest_fn=fake_ingest,
    )
    await handler.run(
        _job(
            {
                "transcript_path": "/x.jsonl",
                "extract": False,
                "dry_run": True,
            }
        )
    )
    assert seen["extract"] is False
    assert seen["dry_run"] is True


@pytest.mark.asyncio
async def test_ingest_handler_keeps_extract_true_when_llm_present(tmp_path: Path):
    seen: dict = {}

    def fake_ingest(
        jsonl_path,
        vault_root,
        *,
        cfg,
        llm_client,
        extract,
        dry_run,
        today,
        raw_filename_suffix="",
        **kwargs,
    ):
        seen["extract"] = extract
        seen["llm_client"] = llm_client

    fake_llm = object()
    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: fake_llm,
        ingest_fn=fake_ingest,
    )
    await handler.run(_job({"transcript_path": "/x.jsonl"}))
    assert seen["extract"] is True
    assert seen["llm_client"] is fake_llm


@pytest.mark.asyncio
async def test_ingest_handler_downgrades_extract_when_no_llm(tmp_path: Path):
    seen: dict = {}

    def fake_ingest(
        jsonl_path,
        vault_root,
        *,
        cfg,
        llm_client,
        extract,
        dry_run,
        today,
        raw_filename_suffix="",
        **kwargs,
    ):
        seen["extract"] = extract

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: None,
        ingest_fn=fake_ingest,
    )
    # Payload requests extract=True, but llm is None → downgrade
    await handler.run(_job({"transcript_path": "/x.jsonl", "extract": True}))
    assert seen["extract"] is False
