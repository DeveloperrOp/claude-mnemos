"""Single source-of-truth scanner for ~/.claude/projects/*.jsonl.

Both core.lost_sessions and core.active_sessions consume the result of
scan_transcripts(); this avoids duplicate disk IO and SHA-256 of the
same files.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from claude_mnemos.core.transcript_helpers import (
    _extract_cwd_and_preview,
    _resolve_transcripts_root,
    _sha256_file,
)
from claude_mnemos.core.ttl_cache import TTLCache

log = logging.getLogger(__name__)


class TranscriptEntry(BaseModel):
    session_id: str
    transcript_path: str
    sha: str
    size_bytes: int
    mtime: datetime
    cwd: str | None = None
    preview: str | None = None


_TRANSCRIPTS_CACHE: TTLCache[list[TranscriptEntry]] = TTLCache(ttl_s=10.0)


def _scan_sync(transcripts_root: Path | None) -> list[TranscriptEntry]:
    root = _resolve_transcripts_root(transcripts_root)
    if not root.is_dir():
        return []
    out: list[TranscriptEntry] = []
    for path in root.rglob("*.jsonl"):
        if not path.is_file():
            continue
        # Skip subagent transcripts. Claude Code writes Agent-tool runs into
        # `<project>/<session>/subagents/agent-*.jsonl`; their payload is
        # already in the parent transcript via tool_use/tool_result, so
        # surfacing them as separate sessions inflates active/lost counters
        # and would double-ingest the same content.
        if "subagents" in path.parts:
            continue
        try:
            stat = path.stat()
            sha = _sha256_file(path)
            cwd, preview = _extract_cwd_and_preview(path)
        except OSError as exc:
            log.warning("scan_transcripts: skipping %s: %s", path, exc)
            continue
        out.append(
            TranscriptEntry(
                session_id=path.stem,
                transcript_path=str(path.resolve()),
                sha=sha,
                size_bytes=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                cwd=cwd,
                preview=preview,
            )
        )
    out.sort(key=lambda e: e.mtime, reverse=True)
    return out


async def scan_transcripts(
    *, transcripts_root: Path | None = None
) -> list[TranscriptEntry]:
    """Async scanner with 10s TTL cache.

    NOTE: cache key is implicit (single global cache). If multiple
    transcripts_root values are used in the same process, the cache
    will conflate them. This is fine for production (one root per
    daemon) but tests that switch transcripts_root via monkeypatch
    must call invalidate_transcripts_cache() between calls.
    """
    async def _compute() -> list[TranscriptEntry]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _scan_sync, transcripts_root)

    return await _TRANSCRIPTS_CACHE.get_or_compute(_compute)


def invalidate_transcripts_cache() -> None:
    """Drop the cache. Used by tests + POST /lost-sessions/scan / scan-active."""
    _TRANSCRIPTS_CACHE.invalidate()
