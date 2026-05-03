"""24h auto-dump scheduler task — safety net against missed SessionEnd hook.

For every assigned (cwd resolves to a project) transcript whose mtime is
older than COOLING_THRESHOLD_HOURS and is not yet ingested in any vault,
enqueue an ingest job with extract=False (raw dump, no LLM stage).

Idempotency: relies on the worker's manifest filter to make duplicate
jobs a no-op. We do NOT pre-check pending jobs; the cap+manifest combo
is simpler and correct.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from claude_mnemos.core.active_sessions import (
    COOLING_THRESHOLD_HOURS,
    UNASSIGNED_PROJECT,
    scan_active_sessions,
)

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime

log = logging.getLogger(__name__)

MAX_PER_RUN = 50


async def auto_dump_stale(
    runtimes: dict[str, "VaultRuntime"],
    *,
    threshold_hours: int = COOLING_THRESHOLD_HOURS,
    max_per_run: int = MAX_PER_RUN,
) -> int:
    """Enqueue ingest jobs for assigned, stale, non-ingested sessions.

    Returns the number of jobs queued. Safe to call repeatedly (idempotent
    via manifest filter in the worker).
    """
    if not runtimes:
        return 0

    runtimes_list = list(runtimes.values())
    sessions = await scan_active_sessions(
        runtimes_list, cooling_threshold_hours=threshold_hours
    )

    queued = 0
    for s in sessions:
        if queued >= max_per_run:
            break
        if s.project_name == UNASSIGNED_PROJECT:
            continue
        if s.status != "cooling":
            continue
        runtime = runtimes.get(s.project_name)
        if runtime is None or runtime.job_store is None:
            continue
        try:
            runtime.job_store.create(
                kind="ingest",
                payload={"transcript_path": s.transcript_path, "extract": False},
            )
        except Exception as exc:
            log.warning("auto_dump: failed to enqueue %s: %s", s.session_id, exc)
            continue
        queued += 1
        if runtime.job_worker is not None:
            runtime.job_worker.signal_wakeup()

    log.info("auto_dump: queued=%d (cap=%d)", queued, max_per_run)
    return queued
