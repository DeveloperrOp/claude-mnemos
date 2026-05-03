"""Single source-of-truth scanner for ~/.claude/projects/*.jsonl.

Both core.lost_sessions and core.active_sessions consume the result of
scan_transcripts(); this avoids duplicate disk IO and SHA-256 of the
same files.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from claude_mnemos.core.transcript_helpers import (
    _extract_cwd_and_preview,
    _resolve_transcripts_root,
    _sha256_file,
)


class TranscriptEntry(BaseModel):
    session_id: str
    transcript_path: str
    sha: str
    size_bytes: int
    mtime: datetime
    cwd: str | None = None
    preview: str | None = None


def _scan_sync(transcripts_root: Path | None) -> list[TranscriptEntry]:
    root = _resolve_transcripts_root(transcripts_root)
    if not root.is_dir():
        return []
    out: list[TranscriptEntry] = []
    for path in root.rglob("*.jsonl"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            sha = _sha256_file(path)
            cwd, preview = _extract_cwd_and_preview(path)
        except OSError:
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
    """Async wrapper — runs blocking scan in default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _scan_sync, transcripts_root)
