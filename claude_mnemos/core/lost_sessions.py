"""Lost-sessions scanner + ignore list + in-memory cache.

A "lost" session is a transcript file under the Claude Code transcripts root
(``~/.claude/projects/`` by default) whose SHA-256 is not present in the
mnemos manifest *and* not on the user-maintained ignore list. The dashboard
(Plan #14) and the ``mnemos lost-sessions`` CLI surface these so the user can
re-import valuable history that was never ingested or has fallen out of the
manifest.

This module ships three concerns:

* :class:`LostSessionsIgnore` — pydantic model persisted to
  ``<vault>/.lost-sessions-ignore.json`` via :func:`atomic_write`.
* :func:`scan_lost_sessions` — pure scan; SHA-streams every ``.jsonl`` under
  the transcripts root, cross-references manifest + ignore list.
* :class:`LostSessionsCache` — TTL'd in-memory wrapper used by the daemon so
  the GET endpoint does not re-hash hundreds of MB on every request.

The scanner is deliberately tolerant: missing ``transcripts_root``, broken
symlinks, and unreadable files all degrade gracefully to "skip" rather than
raising. Errors that should bubble up (corrupt manifest, malformed ignore
file) come from the dependencies and are not caught here.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.state.manifest import Manifest

LOST_SESSIONS_IGNORE_FILENAME = ".lost-sessions-ignore.json"

_SHA_CHUNK_SIZE = 64 * 1024


class LostSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    transcript_path: str
    sha: str
    size_bytes: int
    mtime: datetime


class LostSessionNotFoundError(LookupError):
    """Raised when an operation targets a SHA/session that is not currently lost."""


class LostSessionsIgnore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    ignored_shas: set[str] = Field(default_factory=set)

    @classmethod
    def load(cls, vault: Path) -> LostSessionsIgnore:
        """Load the ignore file from ``<vault>/.lost-sessions-ignore.json``.

        Returns an empty instance when the file does not exist. Raises
        ``ValueError`` (specifically a ``ValidationError`` or ``JSONDecodeError``
        re-raised as ``ValueError``) when the file is malformed.
        """
        path = vault / LOST_SESSIONS_IGNORE_FILENAME
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"lost-sessions ignore file at {path} is not valid JSON: {exc}"
            ) from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"lost-sessions ignore file at {path} fails schema: {exc}"
            ) from exc

    def serialize_to_string(self) -> str:
        return (
            json.dumps(
                self.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )

    def save(self, vault: Path, *, tracker: object | None = None) -> None:
        """Atomically persist the ignore file to ``<vault>/...``.

        ``tracker`` is accepted for forward compatibility with activity
        tracking but is not consumed here yet — Plan #13a intentionally keeps
        this state file out of the activity log because users edit it directly.
        """
        del tracker  # currently unused; kept for API symmetry with manifest.save
        path = vault / LOST_SESSIONS_IGNORE_FILENAME
        atomic_write(path, self.serialize_to_string())


def _resolve_transcripts_root(transcripts_root: Path | None) -> Path:
    if transcripts_root is not None:
        return transcripts_root
    env_value = os.environ.get("MNEMOS_TRANSCRIPTS_ROOT")
    if env_value:
        return Path(env_value)
    return Path.home() / ".claude" / "projects"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_SHA_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def scan_lost_sessions(
    vault: Path,
    *,
    transcripts_root: Path | None = None,
) -> list[LostSession]:
    """Return all transcripts under ``transcripts_root`` that are neither
    ingested (per manifest) nor explicitly ignored.

    Resolution order for ``transcripts_root``:
        argument > ``MNEMOS_TRANSCRIPTS_ROOT`` env var > ``~/.claude/projects``.

    Missing roots return ``[]`` (no error). Unreadable files are skipped
    silently — losing one entry is preferable to crashing the whole scan
    because of an antivirus lock or a broken symlink.
    """
    root = _resolve_transcripts_root(transcripts_root)
    if not root.is_dir():
        return []

    manifest = Manifest.load(vault)
    known_shas: set[str] = set(manifest.ingested.keys())
    ignored_shas: set[str] = LostSessionsIgnore.load(vault).ignored_shas

    results: list[LostSession] = []
    for path in root.rglob("*.jsonl"):
        # Defensive: rglob may yield broken symlinks or directories named
        # like files on weird filesystems. Skip anything that is not a
        # regular file we can stat.
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            sha = _sha256_file(path)
        except OSError:
            continue
        if sha in known_shas or sha in ignored_shas:
            continue
        results.append(
            LostSession(
                session_id=path.stem,
                transcript_path=str(path.resolve()),
                sha=sha,
                size_bytes=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        )

    results.sort(key=lambda item: item.mtime, reverse=True)
    return results


class LostSessionsCache:
    """In-memory TTL cache around :func:`scan_lost_sessions`.

    The daemon owns one of these. ``get_or_scan`` returns the cached list
    while it is fresh (within ``ttl_s`` seconds), otherwise re-scans
    synchronously. ``invalidate`` discards the cache so the next call
    re-scans regardless of TTL — used by ``POST /lost-sessions/scan``.

    Time source is :func:`time.monotonic` so tests can monkeypatch the
    module-level ``time.monotonic`` reference.
    """

    DEFAULT_TTL_S = 60.0

    def __init__(self, ttl_s: float = DEFAULT_TTL_S) -> None:
        self._items: list[LostSession] | None = None
        self._expires_at: float = 0.0
        self._ttl_s = ttl_s

    def get_or_scan(
        self,
        vault: Path,
        *,
        transcripts_root: Path | None = None,
    ) -> list[LostSession]:
        now = time.monotonic()
        if self._items is not None and now < self._expires_at:
            return self._items
        scanned = scan_lost_sessions(vault, transcripts_root=transcripts_root)
        self._items = scanned
        self._expires_at = now + self._ttl_s
        return scanned

    def invalidate(self) -> None:
        self._items = None
        self._expires_at = 0.0


def add_to_ignore(
    vault: Path,
    sha: str,
    *,
    tracker: object | None = None,
) -> LostSessionsIgnore:
    """Add ``sha`` to the ignore list and persist. Returns the updated model.

    Idempotent: re-adding an already-ignored SHA is a no-op (no error, no
    duplicate write side effects beyond the disk overwrite).
    """
    ignore = LostSessionsIgnore.load(vault)
    ignore.ignored_shas.add(sha)
    ignore.save(vault, tracker=tracker)
    return ignore
