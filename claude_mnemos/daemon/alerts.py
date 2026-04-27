"""In-memory alerts buffer for daemon-side issues.

Used by the watchdog handler to surface things that need user attention but
aren't full activity entries: parse failures on edited pages, lock timeouts,
external creates/renames the daemon can't follow, and uncaught exceptions in
the handler. Frontend in Plan #14 will poll /alerts to render them.

Ring buffer with cap MAX=200; persistence is intentionally out of scope for
Plan #9 (in-memory only) — Plan #11+ moves alerts onto disk alongside the
dead-letter queue.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import uuid4

WatchdogAlertKind = Literal[
    "external_create",
    "external_rename",
    "lock_timeout",
    "parse_failed",
    "handler_error",
]


@dataclass(frozen=True)
class WatchdogAlert:
    id: str
    kind: WatchdogAlertKind
    path: str
    message: str
    detected_at: datetime


class Alerts:
    MAX = 200

    def __init__(self) -> None:
        self._items: deque[WatchdogAlert] = deque(maxlen=self.MAX)
        self._lock = threading.Lock()

    def add(
        self,
        *,
        kind: WatchdogAlertKind,
        path: str,
        message: str,
        detected_at: datetime,
    ) -> WatchdogAlert:
        alert = WatchdogAlert(
            id=uuid4().hex,
            kind=kind,
            path=path,
            message=message,
            detected_at=detected_at,
        )
        with self._lock:
            self._items.appendleft(alert)
        return alert

    def list(self) -> list[WatchdogAlert]:
        with self._lock:
            return list(self._items)

    def clear(self, alert_id: str) -> bool:
        with self._lock:
            for i, a in enumerate(self._items):
                if a.id == alert_id:
                    del self._items[i]
                    return True
        return False
