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

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write

INJECT_METRICS_FILENAME = ".inject-metrics.json"
RETENTION_DAYS = 365
MAX_EVENTS = 10_000


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
            data = json.loads(path.read_text(encoding="utf-8"))
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
        """Convenience: load → append → save."""
        log = cls.load(vault_root)
        log.append(event)
        log.save(vault_root)

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
