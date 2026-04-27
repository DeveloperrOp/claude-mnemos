"""Job handlers — one async entrypoint per JobKind."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.pipeline import ingest as default_ingest
from claude_mnemos.state.jobs import Job

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
    ) -> None:
        self._vault = vault
        self._cfg_factory = cfg_factory
        self._llm_factory = llm_factory
        self._ingest_fn = ingest_fn

    async def run(self, job: Job) -> None:
        transcript_path = Path(job.payload["transcript_path"])
        extract = bool(job.payload.get("extract", True))
        dry_run = bool(job.payload.get("dry_run", False))

        cfg = self._cfg_factory()
        llm = self._llm_factory(cfg) if extract else None

        await asyncio.to_thread(
            self._ingest_fn,
            transcript_path,
            self._vault,
            cfg=cfg,
            llm_client=llm,
            extract=extract,
            dry_run=dry_run,
            today=date.today(),
        )
