from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.daemon.jobs.handlers import IngestHandler, JobDeadLetterError
from claude_mnemos.ingest.llm import TranscriptTooLargeError
from claude_mnemos.ingest.pipeline import IngestResult
from claude_mnemos.ingest.transcript import (
    CorruptTranscriptError,
    EmptyTranscriptError,
)
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, Job, JobStore


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
async def test_ingest_handler_too_large_raises_terminal_signal(tmp_path: Path):
    """An oversized session must FAIL FAST: the handler converts
    TranscriptTooLargeError into a JobDeadLetterError so the worker dead-letters
    it in one step (machine-readable code), instead of burning 4 retries
    (30s/120s/1200s backoff) and dead-lettering with a cryptic message."""

    def too_large(*args, **kwargs):
        raise TranscriptTooLargeError(
            "transcript too large",
            input_tokens=900000,
            max_input_tokens=800000,
        )

    fake_llm = object()
    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: fake_llm,
        ingest_fn=too_large,
    )
    with pytest.raises(JobDeadLetterError) as excinfo:
        await handler.run(_job({"transcript_path": "/x.jsonl"}))

    # Machine-readable code the UI parses: too_large:needs=<input>:max=<limit>
    assert str(excinfo.value) == "too_large:needs=900000:max=800000"


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


@pytest.mark.asyncio
async def test_ingest_handler_applies_max_input_tokens_and_chunk_extract(tmp_path: Path):
    """Task 9: payload max_input_tokens override reaches cfg, chunk_extract reaches ingest()."""
    seen: dict = {}

    class _Cfg:
        def __init__(self):
            self.max_input_tokens = 200_000
            self.overridden_to = None

        def with_overrides(self, *, max_input_tokens=None, **_kwargs):
            self.overridden_to = max_input_tokens
            self.max_input_tokens = max_input_tokens
            return self

    cfg = _Cfg()

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
        chunk_extract=False,
        **kwargs,
    ):
        seen["cfg_max_input_tokens"] = cfg.max_input_tokens
        seen["chunk_extract"] = chunk_extract

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: cfg,
        llm_factory=lambda c: object(),
        ingest_fn=fake_ingest,
    )
    await handler.run(
        _job(
            {
                "transcript_path": "/x.jsonl",
                "extract": True,
                "max_input_tokens": 1_200_000,
                "chunk_extract": True,
            }
        )
    )
    assert cfg.overridden_to == 1_200_000
    assert seen["cfg_max_input_tokens"] == 1_200_000
    assert seen["chunk_extract"] is True


@pytest.mark.asyncio
async def test_extract_requested_but_no_llm_records_warning(tmp_path: Path):
    """When extract is requested but no LLM client is available, the silent
    downgrade to raw-only must surface as a visible job warning (so the user
    knows no knowledge pages were created and can fix their auth)."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    job = store.create(kind="ingest", payload={"transcript_path": "/x.jsonl", "extract": True})

    def fake_ingest(*args, **kwargs):  # no-op: warning is what we assert
        pass

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: None,  # no LLM client available
        ingest_fn=fake_ingest,
        job_store=store,
    )
    await handler.run(job)

    reloaded = store.get_by_id(job.id)
    assert reloaded is not None
    assert reloaded.warning and "llm" in reloaded.warning.lower()
    store.close()


@pytest.mark.asyncio
async def test_extract_with_llm_records_no_warning(tmp_path: Path):
    """When the LLM client IS available, extract proceeds normally and no
    downgrade warning is recorded."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    job = store.create(kind="ingest", payload={"transcript_path": "/x.jsonl", "extract": True})

    def fake_ingest(*args, **kwargs):
        pass

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: object(),  # LLM available
        ingest_fn=fake_ingest,
        job_store=store,
    )
    await handler.run(job)

    reloaded = store.get_by_id(job.id)
    assert reloaded is not None
    assert reloaded.warning is None
    store.close()


@pytest.mark.asyncio
async def test_warning_cleared_when_retry_has_llm(tmp_path: Path):
    """A job may carry a stale 'saved raw only' warning from a prior attempt that
    ran with no LLM client. If a later attempt HAS an LLM and succeeds WITH
    extraction, the warning must be cleared — it must reflect the CURRENT
    attempt's outcome, not a dead one."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    job = store.create(
        kind="ingest", payload={"transcript_path": "/x.jsonl", "extract": True}
    )
    # Simulate a prior no-LLM attempt that left a stale warning behind.
    store.set_warning(job.id, "extract requested but no LLM client available — saved raw only")
    stale = store.get_by_id(job.id)
    assert stale is not None and stale.warning is not None  # precondition

    def fake_ingest(*args, **kwargs):
        pass

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: object(),  # LLM now available
        ingest_fn=fake_ingest,
        job_store=store,
    )
    await handler.run(job)

    reloaded = store.get_by_id(job.id)
    assert reloaded is not None
    assert reloaded.warning is None  # stale warning cleared
    store.close()


@pytest.mark.asyncio
async def test_ingest_handler_no_override_passes_chunk_extract_false(tmp_path: Path):
    """Task 9: without the new payload keys, no override is applied and chunk_extract=False."""
    seen: dict = {}

    class _Cfg:
        def __init__(self) -> None:
            self.max_input_tokens = 200_000
            self.override_called = False

        def with_overrides(self, **_kwargs):  # pragma: no cover - must NOT be called
            self.override_called = True
            return self

    cfg = _Cfg()

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
        chunk_extract=False,
        **kwargs,
    ):
        seen["chunk_extract"] = chunk_extract

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: cfg,
        llm_factory=lambda c: object(),
        ingest_fn=fake_ingest,
    )
    await handler.run(_job({"transcript_path": "/x.jsonl", "extract": True}))
    assert cfg.override_called is False
    assert seen["chunk_extract"] is False


@pytest.mark.asyncio
async def test_skipped_collisions_recorded_on_job(tmp_path: Path):
    """When ingest skips pages because an older version already exists, that
    must surface on the job's warning (Queue/Overview render it) — otherwise the
    user thinks 'nothing interesting happened' and silently misses pages."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    job = store.create(
        kind="ingest", payload={"transcript_path": "/x.jsonl", "extract": True}
    )

    def fake_ingest(*args, **kwargs):
        return IngestResult(
            status="extracted",
            session_id="sess-1",
            raw_path=tmp_path / "raw.md",
            skipped_collisions=["wiki/concepts/foo.md", "wiki/concepts/bar.md"],
        )

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: object(),  # LLM present → no downgrade
        ingest_fn=fake_ingest,
        job_store=store,
    )
    await handler.run(job)

    reloaded = store.get_by_id(job.id)
    assert reloaded is not None
    assert reloaded.warning is not None
    assert "foo.md" in reloaded.warning
    assert "skipped" in reloaded.warning.lower()
    store.close()


@pytest.mark.asyncio
async def test_skipped_collisions_combine_with_downgrade_warning(tmp_path: Path):
    """Both the no-LLM downgrade warning AND skipped collisions can apply in the
    same run (raw-only ingest can still collide). They must COMBINE on the job's
    warning rather than one clobbering the other."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    job = store.create(
        kind="ingest", payload={"transcript_path": "/x.jsonl", "extract": True}
    )

    def fake_ingest(*args, **kwargs):
        return IngestResult(
            status="raw_only",
            session_id="sess-2",
            raw_path=tmp_path / "raw.md",
            skipped_collisions=["raw/chats/baz.md"],
        )

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: None,  # no LLM → downgrade warning applies
        ingest_fn=fake_ingest,
        job_store=store,
    )
    await handler.run(job)

    reloaded = store.get_by_id(job.id)
    assert reloaded is not None
    assert reloaded.warning is not None
    # Both signals present, neither clobbered the other.
    assert "llm" in reloaded.warning.lower()
    assert "baz.md" in reloaded.warning
    store.close()


@pytest.mark.asyncio
async def test_no_skipped_collisions_keeps_clean_warning(tmp_path: Path):
    """A clean run (LLM present, no skips) leaves warning as None — the success
    path must not write a spurious warning when there is nothing to surface."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    job = store.create(
        kind="ingest", payload={"transcript_path": "/x.jsonl", "extract": True}
    )

    def fake_ingest(*args, **kwargs):
        return IngestResult(
            status="extracted",
            session_id="sess-3",
            raw_path=tmp_path / "raw.md",
            skipped_collisions=[],
        )

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: object(),
        ingest_fn=fake_ingest,
        job_store=store,
    )
    await handler.run(job)

    reloaded = store.get_by_id(job.id)
    assert reloaded is not None
    assert reloaded.warning is None
    store.close()
