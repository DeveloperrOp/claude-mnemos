"""Persistent health-alert store at ``~/.claude-mnemos/alerts.json``.

Used by the cron-driven health detectors (``core/health_checks.py``).
The in-memory ``daemon/alerts.py`` is a separate concern (watchdog file events);
this store is for semantic detectors (auto-dump-overdue, ingest-failure-streak,
runaway-job, hook-silence, disk-low, project-map-broken, daemon-uptime-warning).

Concurrency:
- Writes go through ``atomic_write`` (sibling tmp + os.replace; Windows-safe).
- Inside the daemon process the store is a singleton owned by ``MnemosDaemon``;
  a per-instance ``threading.RLock`` guards upsert/silence/dismiss sequences
  against concurrent cron ticks. (asyncio.Lock would force converting all
  callers to async; the existing codebase pattern is threading.RLock and the
  guarded sections are CPU-only.)
- Outside the daemon (CLI, tests) callers use ``AlertsStore.load(path)``
  which reads from disk into a fresh instance.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.clock import utcnow

HOME_CONFIG_DIRNAME = ".claude-mnemos"
ALERTS_FILENAME = "alerts.json"

Severity = Literal["info", "warning", "critical"]

DEFAULT_PURGE_RETENTION_DAYS = 30


def home_alerts_path() -> Path:
    return Path.home() / HOME_CONFIG_DIRNAME / ALERTS_FILENAME


class StoredAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    detector: str
    severity: Severity
    message: str  # English fallback; kept for v0.0.11- on-disk alerts
    # v0.0.12: structured payload for client-side localization. The
    # frontend renders `t(i18n_key, i18n_params)` when i18n_key is set,
    # otherwise falls back to the literal `message`. Detectors may emit
    # both — the frontend prefers i18n_key.
    i18n_key: str | None = None
    i18n_params: dict[str, Any] = Field(default_factory=dict)
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
    _path: Path | None = PrivateAttr(default=None)
    # Per-instance lock — guards mutations against concurrent cron ticks
    # within the daemon process. ``default_factory`` ensures each instance
    # gets its own lock (a class-level ``threading.RLock()`` would be shared).
    _lock: threading.RLock = PrivateAttr(default_factory=threading.RLock)

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

    @classmethod
    def load_from_disk(cls, path: Path | None = None) -> "AlertsStore":
        """Load the singleton-style instance for the daemon process.

        Identical to ``load()`` but additionally runs ``purge_old()`` so the
        daemon never starts with stale dismissed alerts. The result is intended
        to live for the daemon's lifetime; route handlers should reuse it
        rather than calling ``load()`` per request.
        """
        inst = cls.load(path)
        inst.purge_old()
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
        with self._lock:
            for i, existing in enumerate(self.alerts):
                if existing.id == alert.id:
                    merged = existing.model_copy(
                        update={
                            "detector": alert.detector,
                            "severity": alert.severity,
                            "message": alert.message,
                            "context": alert.context,
                            "last_seen": alert.last_seen,
                            "i18n_key": alert.i18n_key,
                            "i18n_params": alert.i18n_params,
                        }
                    )
                    self.alerts[i] = merged
                    self.purge_old()
                    return merged
            self.alerts.append(alert)
            self.purge_old()
            return alert

    def silence(self, alert_id: str, duration: timedelta) -> StoredAlert | None:
        with self._lock:
            for i, a in enumerate(self.alerts):
                if a.id == alert_id:
                    self.alerts[i] = a.model_copy(
                        update={"silenced_until": utcnow() + duration}
                    )
                    self.purge_old()
                    return self.alerts[i]
            return None

    def dismiss(self, alert_id: str) -> StoredAlert | None:
        with self._lock:
            for i, a in enumerate(self.alerts):
                if a.id == alert_id:
                    self.alerts[i] = a.model_copy(update={"dismissed": True})
                    self.purge_old()
                    return self.alerts[i]
            return None

    def purge_old(
        self, retention_days: int = DEFAULT_PURGE_RETENTION_DAYS
    ) -> int:
        """Remove dismissed alerts whose ``last_seen`` is older than
        ``retention_days`` days. Returns the count of removed entries.

        Called once at load_from_disk() and after every mutation so the file
        cannot grow unboundedly.
        """
        with self._lock:
            cutoff = utcnow() - timedelta(days=retention_days)
            before = len(self.alerts)
            self.alerts = [
                a for a in self.alerts
                if not (a.dismissed and a.last_seen < cutoff)
            ]
            return before - len(self.alerts)

    # ─── Queries ──────────────────────────────────────────────────

    def active_alerts(self, *, now: datetime | None = None) -> list[StoredAlert]:
        n = now if now is not None else utcnow()
        out: list[StoredAlert] = []
        for a in self.alerts:
            if a.dismissed:
                continue
            if a.silenced_until is not None and a.silenced_until > n:
                continue
            out.append(a)
        return out

    def silenced_alerts(self, *, now: datetime | None = None) -> list[StoredAlert]:
        n = now if now is not None else utcnow()
        return [
            a for a in self.alerts
            if not a.dismissed
            and a.silenced_until is not None
            and a.silenced_until > n
        ]
