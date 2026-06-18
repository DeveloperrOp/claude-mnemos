"""Job handlers — one async entrypoint per JobKind."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import LLMClient, TranscriptTooLargeError
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


class JobDeadLetterError(Exception):
    """Terminal signal: dead-letter this job NOW, skipping the retry ladder.

    Handlers raise this when a failure is *deterministic* — retrying with the
    same input cannot succeed (e.g. a transcript too large for the model's
    context window). The worker recognises it and routes the job straight to
    dead_letter in one step instead of burning MAX_ATTEMPTS retries (and the
    30s/120s/1200s backoff between them) on a guaranteed-to-fail job.

    The message carries a machine-readable error code the dashboard parses to
    offer the user a choice (e.g. ``too_large:needs=<N>:max=<M>``).
    """


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
        chunk_extract = bool(job.payload.get("chunk_extract", False))
        max_input_tokens = job.payload.get("max_input_tokens")

        cfg = self._cfg_factory()
        # Per-session override (Task 9): raise the model's input budget for one
        # oversized session without touching project-wide config.
        if max_input_tokens is not None:
            cfg = cfg.with_overrides(max_input_tokens=int(max_input_tokens))
        llm = self._llm_factory(cfg) if extract_requested else None
        # If extract was requested but no LLM client available (e.g. no API
        # key), downgrade to raw_only ingest. Avoids dead_letter spam for
        # users without ANTHROPIC_API_KEY — the transcript still lands in
        # raw/chats/, just no wiki extraction.
        effective_extract = extract_requested and llm is not None
        # Don't fail the job (raw-only still lands the transcript), but make the
        # silent downgrade VISIBLE so the user knows no wiki pages were created
        # and can fix their LLM/auth setup. Write the warning UNCONDITIONALLY
        # (computed value, or None) so a RETRY where the downgrade no longer
        # applies clears the stale warning from the prior attempt — the warning
        # must reflect THIS attempt's outcome, not a dead one.
        downgrade_warning = (
            (
                "extract requested but no LLM client available — saved raw only, "
                "no knowledge pages created (check Claude CLI / API auth)"
            )
            if (extract_requested and not effective_extract)
            else None
        )
        if self._job_store is not None:
            self._job_store.set_warning(job.id, downgrade_warning)

        try:
            result = await asyncio.to_thread(
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
                chunk_extract=chunk_extract,
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
        except TranscriptTooLargeError as exc:
            # Deterministic failure: the transcript exceeds the model's input
            # budget, so every retry would fail identically. FAIL FAST — raise
            # the terminal signal so the worker dead-letters the job in one
            # step with a machine-readable code, instead of burning 4 retries
            # (30s/120s/1200s backoff) before dead-lettering with a cryptic
            # message. The dashboard parses this code to offer the user a
            # choice (split/skip/raise the limit).
            _LOG.warning(
                "ingest: %s too large (%s tokens vs limit %s) — "
                "dead-lettering immediately (no retry)",
                transcript_path,
                exc.input_tokens,
                exc.max_input_tokens,
            )
            raise JobDeadLetterError(
                f"too_large:needs={exc.input_tokens}:max={exc.max_input_tokens}"
            ) from exc
        except RateLimitError as exc:
            # Pause the queue so worker stops dequeuing until reset_at.
            # Re-raise so the job is retried (not dead-lettered immediately —
            # JobWorker's retry path keeps it queued; once paused_until passes,
            # is_paused() returns False and the job is picked up again).
            if self._job_store is not None:
                self._job_store.pause_queue(until=exc.reset_at)
            raise

        # SUCCESS path (only the normal completion reaches here — the early
        # `return`/`raise` branches above don't). If ingest skipped pages
        # because an older version already exists, surface that on the job's
        # warning so it shows in Queue/Overview — otherwise the user thinks
        # "nothing happened" and silently misses pages. Combine with the
        # downgrade warning (if any) instead of clobbering it, and only
        # re-write when there ARE skips so the downgrade-only and clean cases
        # keep the value already written before the ingest call.
        skipped = getattr(result, "skipped_collisions", None) if result is not None else None
        if skipped:
            n = len(skipped)
            preview = ", ".join(skipped[:5])
            skip_msg = f"skipped {n} page(s) — already exist: {preview}"
            parts = [p for p in (downgrade_warning, skip_msg) if p]
            if self._job_store is not None:
                self._job_store.set_warning(job.id, " | ".join(parts))
