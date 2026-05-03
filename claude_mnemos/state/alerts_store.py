"""Persistent health-alert store at ``~/.claude-mnemos/alerts.json``.

Used by the cron-driven health detectors (``core/health_checks.py``).
The in-memory ``daemon/alerts.py`` is a separate concern (watchdog file events);
this store is for semantic detectors (auto-dump-overdue, ingest-failure-streak,
runaway-job, hook-silence, disk-low, project-map-broken, daemon-uptime-warning).

Concurrency:
- Writes go through ``atomic_write`` (sibling tmp + os.replace; Windows-safe).
- Reads always reload from disk so multiple processes (CLI + daemon) see fresh state.
- Within the daemon process a re-entrant lock guards upsert/silence/dismiss
  sequences against concurrent cron ticks.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.core.atomic import atomic_write

HOME_CONFIG_DIRNAME = ".claude-mnemos"
ALERTS_FILENAME = "alerts.json"

Severity = Literal["info", "warning", "critical"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def home_alerts_path() -> Path:
    return Path.home() / HOME_CONFIG_DIRNAME / ALERTS_FILENAME


_LOCK = threading.RLock()


class StoredAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    detector: str
    severity: Severity
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    first_seen: datetime
    last_seen: datetime
    silenced_until: datetime | None = None
    dismissed: bool = False


class AlertsStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    alerts: list[StoredAlert] = Field(default_factory=list)

    # Path used for save() — not part of the persisted schema. Excluded from
    # model_dump output.
    _path: Path | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> "AlertsStore":
        target = path if path is not None else home_alerts_path()
        if not target.exists():
            inst = cls()
            inst._path = target
            return inst
        try:
            raw = target.read_text(encoding="utf-8")
            data = json.loads(raw)
            inst = cls.model_validate(data)
        except (json.JSONDecodeError, ValueError, OSError):
            # Corrupt file: start fresh in memory; first save() rewrites it.
            inst = cls()
        inst._path = target
        return inst

    def save(self) -> None:
        target = self._path if self._path is not None else home_alerts_path()
        atomic_write(
            target,
            json.dumps(self.model_dump(mode="json"), indent=2) + "\n",
        )

    # ─── Mutations ────────────────────────────────────────────────

    def upsert(self, alert: StoredAlert) -> StoredAlert:
        """Insert or update by ``id``.

        On update, preserves ``first_seen``, ``silenced_until``, and ``dismissed``
        from the stored copy and refreshes ``last_seen`` / ``message`` /
        ``context`` from the incoming alert. (A new alert object from a detector
        always carries first_seen=last_seen=now; we keep the original first_seen
        so the UI can show "first detected 2h ago".)
        """
        with _LOCK:
            for i, existing in enumerate(self.alerts):
                if existing.id == alert.id:
                    merged = existing.model_copy(
                        update={
                            "detector": alert.detector,
                            "severity": alert.severity,
                            "message": alert.message,
                            "context": alert.context,
                            "last_seen": alert.last_seen,
                        }
                    )
                    self.alerts[i] = merged
                    return merged
            self.alerts.append(alert)
            return alert

    def silence(self, alert_id: str, duration: timedelta) -> StoredAlert | None:
        with _LOCK:
            for i, a in enumerate(self.alerts):
                if a.id == alert_id:
                    self.alerts[i] = a.model_copy(
                        update={"silenced_until": _utcnow() + duration}
                    )
                    return self.alerts[i]
            return None

    def dismiss(self, alert_id: str) -> StoredAlert | None:
        with _LOCK:
            for i, a in enumerate(self.alerts):
                if a.id == alert_id:
                    self.alerts[i] = a.model_copy(update={"dismissed": True})
                    return self.alerts[i]
            return None

    # ─── Queries ──────────────────────────────────────────────────

    def active_alerts(self, *, now: datetime | None = None) -> list[StoredAlert]:
        n = now if now is not None else _utcnow()
        out: list[StoredAlert] = []
        for a in self.alerts:
            if a.dismissed:
                continue
            if a.silenced_until is not None and a.silenced_until > n:
                continue
            out.append(a)
        return out

    def silenced_alerts(self, *, now: datetime | None = None) -> list[StoredAlert]:
        n = now if now is not None else _utcnow()
        return [
            a for a in self.alerts
            if not a.dismissed
            and a.silenced_until is not None
            and a.silenced_until > n
        ]
