from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from claude_mnemos.core.locks import LockTimeoutError, pipeline_lock
from claude_mnemos.core.snapshots import create_daily_snapshot

logger = logging.getLogger(__name__)


def daily_snapshot_task(
    vault: Path,
    today: date | None = None,
    *,
    lock_timeout: float = 30.0,
) -> Path | None:
    """Create today's daily snapshot if not exists. Idempotent.

    Returns the snapshot path on success, None on lock timeout / failure.
    Designed to be called by APScheduler — never raises.
    """
    today = today or date.today()
    try:
        with pipeline_lock(vault, timeout=lock_timeout):
            snap = create_daily_snapshot(vault, today)
            logger.info("daily snapshot created/exists at %s", snap)
            return snap
    except LockTimeoutError:
        logger.warning(
            "daily_snapshot: pipeline busy, skipping daily snapshot for %s", today
        )
        return None
    except Exception:
        logger.exception("daily_snapshot failed for %s", today)
        return None
