from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from claude_mnemos.core.locks import LockTimeoutError, pipeline_lock
from claude_mnemos.core.snapshots import PruneResult, prune_old_backups

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
            return result
    except LockTimeoutError:
        logger.warning("backups_cleanup: pipeline busy, skipping")
        return None
    except Exception:
        logger.exception("backups_cleanup failed")
        return None
