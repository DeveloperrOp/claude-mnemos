"""File-backed cache of per-chunk extraction payloads, keyed by content hash.

When a big transcript is chunk-extracted, the extractor calls the LLM once per
chunk. If chunk *K* hits a rate limit, the whole ingest job fails and is retried
from scratch — re-extracting chunks 1..K-1 and burning the user's Claude
subscription. This cache persists each chunk's :class:`ExtractionPayload` keyed
by the sha256 of the chunk's *rendered transcript text*, so a retry resumes from
where it stopped.

Content-addressing (not chunk index) means identical chunk content is reused
regardless of order, and changing the budget/limit between retries simply misses
safely — a different split produces different hashes and never serves a stale
payload for the wrong content. Reads are corruption-tolerant: a missing,
unreadable, or schema-mismatched cache file yields ``None`` rather than crashing
extraction.

The pipeline owns the lifecycle: the cache is cleared on a successful extract
and deliberately *kept* on any failure (rate-limit must resume). Stale session
dirs are swept by the daemon's backups-cleanup task.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.models import ExtractionPayload

logger = logging.getLogger(__name__)

CHUNK_CACHE_DIRNAME = ".chunk-cache"


def hash_chunk_text(text: str) -> str:
    """sha256 hexdigest of *text* — the content-address key for a chunk payload."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ChunkCache:
    """Per-session, content-addressed cache of chunk :class:`ExtractionPayload`s.

    The on-disk layout is ``<vault_root>/.chunk-cache/<session_id>/<hash>.json``.
    """

    def __init__(self, vault_root: Path, session_id: str) -> None:
        self.vault_root = vault_root
        self.session_id = session_id
        self.dir = vault_root / CHUNK_CACHE_DIRNAME / session_id

    def _path(self, chunk_hash: str) -> Path:
        return self.dir / f"{chunk_hash}.json"

    def get(self, chunk_hash: str) -> ExtractionPayload | None:
        """Return the cached payload for *chunk_hash*, or ``None``.

        Corruption-tolerant: a missing, unreadable, invalid-JSON or
        schema-mismatched file yields ``None`` so a bad cache entry never
        crashes extraction (it is simply re-extracted).
        """
        path = self._path(chunk_hash)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            return ExtractionPayload.model_validate_json(text)
        except ValueError:
            logger.warning("chunk-cache: ignoring corrupt entry %s", path.name)
            return None

    def put(self, chunk_hash: str, payload: ExtractionPayload) -> None:
        """Persist *payload* under *chunk_hash* (atomic write), best-effort.

        Caching is an optimization, never a correctness dependency: a write
        failure (disk full, permission, read-only FS) must not abort an
        otherwise-successful extraction — the chunk is simply re-extracted on a
        later retry. Mirrors :meth:`get`'s corruption-tolerance so the cache can
        never turn a good extraction into a failed job.
        """
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            atomic_write(self._path(chunk_hash), payload.model_dump_json())
        except OSError as exc:
            logger.warning(
                "chunk-cache: failed to persist %s: %s", chunk_hash[:12], exc
            )

    def clear(self) -> None:
        """Best-effort removal of this session's cache dir (suppress errors)."""
        with suppress(OSError):
            shutil.rmtree(self.dir, ignore_errors=True)

    @staticmethod
    def sweep_stale(vault_root: Path, *, max_age_days: int = 7) -> int:
        """Remove session dirs under ``<vault>/.chunk-cache`` older than the cutoff.

        A dir is stale when its mtime is older than ``now - max_age_days``.
        Best-effort: per-dir failures are suppressed. Returns the count removed
        (0 if the ``.chunk-cache`` dir doesn't exist).
        """
        root = vault_root / CHUNK_CACHE_DIRNAME
        if not root.is_dir():
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        removed = 0
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            try:
                mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
            except OSError:
                continue
            if mtime < cutoff:
                with suppress(OSError):
                    shutil.rmtree(entry)
                    removed += 1
        return removed
