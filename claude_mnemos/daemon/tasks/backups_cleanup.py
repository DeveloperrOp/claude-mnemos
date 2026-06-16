from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from claude_mnemos.core.locks import LockTimeoutError, pipeline_lock
from claude_mnemos.core.snapshots import PruneResult, prune_old_backups
from claude_mnemos.ingest.chunk_cache import ChunkCache

logger = logging.getLogger(__name__)


def backups_cleanup_task(
    vault: Path,
    retention_days: int,
    today: date | None = None,
    *,
    lock_timeout: float = 30.0,
) -> PruneResult | None:
    """Prune snapshots older than retention_days. Designed to be called by APScheduler.

    Returns PruneResult on success, None on lock timeout / failure.
    Never raises.
    """
    today = today or date.today()
    try:
        with pipeline_lock(vault, timeout=lock_timeout):
            result = prune_old_backups(vault, retention_days, today)
            logger.info(
                "backups_cleanup: pruned=%d kept=%d errors=%d",
                len(result.pruned),
                result.kept,
                len(result.errors),
            )
            for name, msg in result.errors:
                logger.warning("backups_cleanup: failed to prune %s: %s", name, msg)
            # Sweep stale per-session chunk-extract caches (rate-limit resume
            # debris). This is the ONLY reaper of caches stranded by a failure
            # that never succeeds (clear-on-success can't reach them), so don't
            # "simplify" it away. Best-effort: a failure here must never break
            # cleanup.
            try:
                swept = ChunkCache.sweep_stale(vault)
                if swept > 0:
                    logger.info("backups_cleanup: swept %d stale chunk-cache dir(s)", swept)
            except Exception:
                logger.exception("backups_cleanup: chunk-cache sweep failed")
            return result
    except LockTimeoutError:
        logger.warning("backups_cleanup: pipeline busy, skipping")
        return None
    except Exception:
        logger.exception("backups_cleanup failed")
        return None
