"""Job handlers — one async entrypoint per JobKind."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.llm.rate_limit import RateLimitError
from claude_mnemos.ingest.pipeline import ingest as default_ingest
from claude_mnemos.state.jobs import Job, JobStore

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
    ) -> None:
        self._vault = vault
        self._cfg_factory = cfg_factory
        self._llm_factory = llm_factory
        self._ingest_fn = ingest_fn
        self._job_store = job_store

    async def run(self, job: Job) -> None:
        transcript_path = Path(job.payload["transcript_path"])
        extract_requested = bool(job.payload.get("extract", True))
        dry_run = bool(job.payload.get("dry_run", False))

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
                today=date.today(),
            )
        except RateLimitError as exc:
            # Pause the queue so worker stops dequeuing until reset_at.
            # Re-raise so the job is retried (not dead-lettered immediately —
            # JobWorker's retry path keeps it queued; once paused_until passes,
            # is_paused() returns False and the job is picked up again).
            if self._job_store is not None:
                self._job_store.pause_queue(until=exc.reset_at)
            raise
