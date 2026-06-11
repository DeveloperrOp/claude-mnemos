"""Stale-session auto-dump scheduler — opt-in safety net.

For each registered project, find transcripts that:
  * resolve to that project (cwd matches a project's cwd_patterns),
  * have ``mtime`` older than ``stale_threshold_hours`` (default 24h),
  * are NOT yet ingested in any vault,
  * AND the project has ``dump_stale_after_24h`` opted in (per-project or
    via ``GlobalSettings.auto_ingest_defaults``).

For matches, enqueue an ingest job. ``extract`` is decided by the
project's ``extract_after_dump`` flag — default OFF. Without that flag the
job is a raw dump only (zero LLM tokens), and the user can still trigger
extract manually from the page UI.

v0.0.10 changes vs v0.0.9:
  * Switched the trigger zone from "cooling" (30min–24h) to "stale" (>24h).
    Pre-v0.0.10 the cron would auto-dump sessions that were merely "yellow"
    in the dashboard — sessions the user might still resume via
    ``claude --resume``. That dumped a half-written transcript and surfaced
    queued jobs from a source the user didn't recognise.
  * Reads per-project + global ``auto_ingest`` settings. If both say "no",
    the cron is a no-op for that project — there is no longer a hidden
    background path that ingests without consent.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from claude_mnemos.core.transcript_scanner import scan_transcripts
from claude_mnemos.core.uningested_sessions import global_ingested_shas
from claude_mnemos.mapping.resolver import (
    ProjectResolver,
    ResolverAmbiguityError,
)
from claude_mnemos.state.settings import (
    GlobalSettings,
    SettingsStore,
    resolve_ingest_flags,
)

if TYPE_CHECKING:
    from pathlib import Path

    from claude_mnemos.daemon.vault_runtime import VaultRuntime

log = logging.getLogger(__name__)

DEFAULT_STALE_THRESHOLD_HOURS = 24
MAX_PER_RUN = 50


async def auto_dump_stale(
    runtimes: dict[str, VaultRuntime],
    *,
    stale_threshold_hours: int = DEFAULT_STALE_THRESHOLD_HOURS,
    max_per_run: int = MAX_PER_RUN,
    settings_store: SettingsStore | None = None,
) -> int:
    """Enqueue ingest jobs for project-assigned, stale, non-ingested sessions.

    Returns the number of jobs queued. Safe to call repeatedly (idempotent
    via manifest filter in the worker).

    ``settings_store`` is injectable for tests; defaults to a fresh
    ``SettingsStore()`` reading from ``~/.claude-mnemos/``.
    """
    if not runtimes:
        return 0

    store = settings_store or SettingsStore()
    try:
        glob = store.get_global()
    except Exception as exc:  # noqa: BLE001
        log.warning("auto_dump: failed to load GlobalSettings (%s); using built-in defaults", exc)
        glob = GlobalSettings()

    runtimes_list = list(runtimes.values())
    entries = await scan_transcripts()
    if not entries:
        return 0

    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(hours=stale_threshold_hours)
    ingested = global_ingested_shas(runtimes_list)

    # Pre-fetch project entries once; reuse for cwd resolutions across all entries.
    _resolver_entries_source = ProjectResolver()
    resolver = ProjectResolver(entries=_resolver_entries_source.list_all())

    queued = 0
    for e in entries:
        if queued >= max_per_run:
            break
        # Stale = mtime BEFORE cutoff (i.e. older than threshold). The previous
        # impl used "cooling" (between 30min and 24h ago) and dumped sessions
        # mid-resume; switching to strict ">threshold" closes that hole.
        if e.mtime > cutoff:
            continue
        if e.sha in ingested:
            continue
        if not e.cwd:
            continue
        try:
            entry = resolver.resolve_by_cwd(_path(e.cwd), git_fallback=True)
        except (ResolverAmbiguityError, OSError):
            continue
        if entry is None:
            continue
        runtime = runtimes.get(entry.name)
        if runtime is None or runtime.job_store is None:
            continue

        _, dump_stale, extract = resolve_ingest_flags(runtime.settings, glob)
        if not dump_stale:
            continue

        try:
            runtime.job_store.create(
                kind="ingest",
                payload={
                    "transcript_path": e.transcript_path,
                    "extract": extract,
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("auto_dump: failed to enqueue %s: %s", e.session_id, exc)
            continue
        queued += 1
        if runtime.job_worker is not None:
            runtime.job_worker.signal_wakeup()

    log.info("auto_dump: queued=%d (cap=%d)", queued, max_per_run)
    return queued


def _path(cwd: str) -> Path:
    from pathlib import Path
    return Path(cwd)
