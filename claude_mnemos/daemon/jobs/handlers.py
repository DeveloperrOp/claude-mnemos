"""Job handlers — one async entrypoint per JobKind."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.llm.rate_limit import RateLimitError
from claude_mnemos.ingest.pipeline import ingest as default_ingest
from claude_mnemos.ingest.transcript import EmptyTranscriptError
from claude_mnemos.state.jobs import Job, JobStore

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker

_LOG = logging.getLogger(__name__)

CfgFactory = Callable[[], Config]
LLMFactory = Callable[[Config], LLMClient | None]
IngestFn = Callable[..., Any]


class JobHandler(Protocol):
    async def run(self, job: Job) -> None: ...


class IngestHandler:
    """Runs the synchronous ingest pipeline in a worker thread."""

    def __init__(
        self,
        *,
        vault: Path,
        cfg_factory: CfgFactory,
        llm_factory: LLMFactory,
        ingest_fn: IngestFn = default_ingest,
        job_store: JobStore | None = None,
        tracker: OurWritesTracker | None = None,
    ) -> None:
        self._vault = vault
        self._cfg_factory = cfg_factory
        self._llm_factory = llm_factory
        self._ingest_fn = ingest_fn
        self._tracker = tracker
        self._job_store = job_store

    async def run(self, job: Job) -> None:
        transcript_path = Path(job.payload["transcript_path"])
        extract_requested = bool(job.payload.get("extract", True))
        dry_run = bool(job.payload.get("dry_run", False))
        raw_filename_suffix = str(job.payload.get("raw_filename_suffix", ""))

        cfg = self._cfg_factory()
        llm = self._llm_factory(cfg) if extract_requested else None
        # If extract was requested but no LLM client available (e.g. no API
        # key), downgrade to raw_only ingest. Avoids dead_letter spam for
        # users without ANTHROPIC_API_KEY — the transcript still lands in
        # raw/chats/, just no wiki extraction.
        effective_extract = extract_requested and llm is not None

        try:
            await asyncio.to_thread(
                self._ingest_fn,
                transcript_path,
                self._vault,
                cfg=cfg,
                llm_client=llm,
                extract=effective_extract,
                dry_run=dry_run,
                # UTC to match the rest of the codebase — date.today() uses the
                # OS local zone, so a session finishing near local midnight
                # could file its source page under the wrong day.
                today=datetime.now(UTC).date(),
                raw_filename_suffix=raw_filename_suffix,
                tracker=self._tracker,
            )
        except EmptyTranscriptError:
            # A valid session can have zero text messages (pure tool_use /
            # tool_result — the user only ran commands). That is a legitimate
            # no-op, NOT a failure: returning normally marks the job succeeded
            # so it never burns 4 retries and lands in dead-letter with a
            # cryptic "no message entries" message the user can't act on.
            _LOG.info(
                "ingest: %s has no text messages (pure-tool session) — "
                "nothing to ingest, marking job done",
                transcript_path,
            )
            return
        except RateLimitError as exc:
            # Pause the queue so worker stops dequeuing until reset_at.
            # Re-raise so the job is retried (not dead-lettered immediately —
            # JobWorker's retry path keeps it queued; once paused_until passes,
            # is_paused() returns False and the job is picked up again).
            if self._job_store is not None:
                self._job_store.pause_queue(until=exc.reset_at)
            raise
