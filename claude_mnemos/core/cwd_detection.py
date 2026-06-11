"""Scan ~/.claude/projects/ to detect cwds where Claude Code sessions live.

Used by the Welcome onboarding screen to suggest workspaces a user
might want to track. Reads the first JSON object from every JSONL
transcript and aggregates by `cwd` field.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

_DEFAULT_LOOKBACK_DAYS = 30
_MAX_RESULTS = 10


class DetectedCwd(BaseModel):
    cwd: str
    session_count: int
    last_seen: datetime


def _transcripts_root() -> Path:
    return Path.home() / ".claude" / "projects"


def _read_cwd(jsonl_path: Path) -> str | None:
    """Return the `cwd` field of the first JSON line, or None on parse error."""
    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            line = f.readline()
        if not line:
            return None
        obj = json.loads(line)
        cwd = obj.get("cwd")
        return cwd if isinstance(cwd, str) and cwd else None
    except (OSError, json.JSONDecodeError):
        return None


def detect_cwds(
    *,
    now: datetime | None = None,
    exclude_cwds: Iterable[str] = (),
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
) -> list[DetectedCwd]:
    """Return up to 10 cwds ranked by session count in the last lookback window."""
    now = now or datetime.now(tz=UTC)
    cutoff = now - timedelta(days=lookback_days)
    excluded = set(exclude_cwds)

    root = _transcripts_root()
    if not root.is_dir():
        return []

    counts: dict[str, int] = {}
    last_seen_by_cwd: dict[str, datetime] = {}

    for jsonl in root.rglob("*.jsonl"):
        try:
            mtime_ts = jsonl.stat().st_mtime
        except OSError:
            continue
        mtime = datetime.fromtimestamp(mtime_ts, tz=UTC)
        if mtime < cutoff:
            continue
        cwd = _read_cwd(jsonl)
        if not cwd or cwd in excluded:
            continue
        counts[cwd] = counts.get(cwd, 0) + 1
        prev = last_seen_by_cwd.get(cwd)
        if prev is None or mtime > prev:
            last_seen_by_cwd[cwd] = mtime

    items = [
        DetectedCwd(cwd=k, session_count=v, last_seen=last_seen_by_cwd[k])
        for k, v in counts.items()
    ]
    items.sort(key=lambda d: (-d.session_count, -d.last_seen.timestamp()))
    return items[:_MAX_RESULTS]
