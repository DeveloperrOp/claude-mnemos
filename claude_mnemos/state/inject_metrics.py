"""Per-vault inject-metrics log (Plan #13d, spec §15).

Records every SessionStart inject event so the dashboard can compute
``avg_compression_ratio = mean(tokens_full / tokens_actual)`` and per-period
event counts. Mirrors the patterns in :mod:`claude_mnemos.state.activity`.

Per-vault file ``.inject-metrics.json`` (mnemos convention overrides spec's
literal ``state/inject-metrics.json`` global path; consistent with the
multi-vault refactor in Plan #13b-β1 where every state file lives at vault
root).

Retention: events older than ``RETENTION_DAYS`` (365) are dropped on every
save. Hard cap ``MAX_EVENTS`` (10000) — oldest dropped when exceeded — to
bound disk on extreme usage.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write

_LOG = logging.getLogger(__name__)

INJECT_METRICS_FILENAME = ".inject-metrics.json"
RETENTION_DAYS = 365
MAX_EVENTS = 10_000
LOCK_FILENAME = ".inject-metrics.lock"
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_POLL_INTERVAL = 0.05
# A healthy writer holds the lock for milliseconds, so a lock this old can
# only be the leftover of a crashed writer and is safe to break.
STALE_LOCK_SECONDS = 60.0


InjectMode = Literal["full", "trimmed", "empty"]
InjectOperation = Literal["session_start"]


class InjectMetricsCorruptError(ValueError):
    """Raised when the inject-metrics log file is unreadable / fails schema."""


class InjectMetricEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    timestamp: datetime
    session_id: str | None
    operation: InjectOperation
    mode: InjectMode
    tokens_full: int = Field(ge=0)
    tokens_actual: int = Field(ge=0)
    candidates_total: int = Field(ge=0)
    candidates_packed: int = Field(ge=0)


class InjectMetricsLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    events: list[InjectMetricEvent] = Field(default_factory=list)

    @classmethod
    def load(cls, vault_root: Path) -> InjectMetricsLog:
        path = vault_root / INJECT_METRICS_FILENAME
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))  # tolerate BOM
        except json.JSONDecodeError as exc:
            raise InjectMetricsCorruptError(
                f"inject-metrics log at {path} is not valid JSON: {exc}"
            ) from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise InjectMetricsCorruptError(
                f"inject-metrics log at {path} fails schema: {exc}"
            ) from exc

    def serialize_to_string(self) -> str:
        return (
            json.dumps(
                self.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=False,
            )
            + "\n"
        )

    def save(self, vault_root: Path) -> None:
        """Apply retention + cap, then atomically write."""
        self._apply_retention()
        self._apply_cap()
        path = vault_root / INJECT_METRICS_FILENAME
        atomic_write(path, self.serialize_to_string())

    def append(self, event: InjectMetricEvent) -> None:
        if any(e.id == event.id for e in self.events):
            raise ValueError(
                f"inject-metrics log already contains event id {event.id}"
            )
        self.events.append(event)

    @classmethod
    def append_to_vault(cls, vault_root: Path, event: InjectMetricEvent) -> None:
        """Convenience: load → append → save, with a file lock to serialize
        concurrent writers.

        The lock is a vault-local file created with ``O_EXCL``. Other writers
        poll up to ``LOCK_TIMEOUT_SECONDS``. If the timeout expires, the event
        is DROPPED with a warning rather than written without the lock: a
        lock-free read-modify-write races every other writer and silently
        loses their events (corrupting the whole file), whereas these metrics
        are cosmetic (usage stats), so dropping one is strictly better than
        losing many.

        A lock older than ``STALE_LOCK_SECONDS`` (a healthy writer holds it
        for milliseconds) is the leftover of a crashed writer and is broken
        before polling — otherwise every future append would wait out the
        timeout and drop its event forever, until manual cleanup.
        """
        lock_path = vault_root / LOCK_FILENAME

        # Break a stale lock from a crashed writer (checked once, before the
        # poll loop: if the lock turns stale mid-poll, the next hook breaks it).
        try:
            lock_age = time.time() - lock_path.stat().st_mtime
        except OSError:
            lock_age = None  # no lock file (or it vanished) — nothing to break
        if lock_age is not None and lock_age > STALE_LOCK_SECONDS:
            _LOG.warning(
                "breaking stale inject-metrics lock at %s (age %.0fs > %.0fs) "
                "left behind by a crashed writer",
                lock_path,
                lock_age,
                STALE_LOCK_SECONDS,
            )
            with contextlib.suppress(OSError):
                lock_path.unlink(missing_ok=True)

        acquired = False
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                fd = os.open(
                    str(lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                time.sleep(LOCK_POLL_INTERVAL)

        if not acquired:
            _LOG.warning(
                "inject-metrics lock at %s held longer than %.0fs — dropping "
                "event %s rather than risk a lock-free write clobbering other "
                "writers' events",
                lock_path,
                LOCK_TIMEOUT_SECONDS,
                event.id,
            )
            return

        try:
            log = cls.load(vault_root)
            log.append(event)
            log.save(vault_root)
        finally:
            with contextlib.suppress(FileNotFoundError):
                lock_path.unlink()

    def _apply_retention(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        self.events = [e for e in self.events if e.timestamp >= cutoff]

    def _apply_cap(self) -> None:
        if len(self.events) > MAX_EVENTS:
            # Sort by timestamp ascending and keep the most-recent MAX_EVENTS.
            # Defensive: hooks normally append in chronological order, but a
            # backfill / manual edit / future feature could violate that.
            self.events.sort(key=lambda e: e.timestamp)
            self.events = self.events[-MAX_EVENTS:]
