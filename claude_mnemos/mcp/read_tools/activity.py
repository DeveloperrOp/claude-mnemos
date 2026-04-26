from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_mnemos.state.activity import ActivityLog


def get_recent_activity(vault: Path, *, limit: int = 10) -> list[dict[str, Any]]:
    """Return last `limit` activity entries newest-first."""
    log = ActivityLog.load(vault)
    entries = list(reversed(log.entries))
    sliced = entries[:limit] if limit > 0 else entries
    return [e.model_dump(mode="json") for e in sliced]
