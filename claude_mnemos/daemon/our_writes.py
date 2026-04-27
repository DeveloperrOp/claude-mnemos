"""Self-write tracker for the daemon.

The watchdog handler differentiates daemon-originated writes from external
edits by consulting an in-memory set of paths the daemon is currently writing.
A path is added before a vault mutation begins and removed after it completes;
during that window any filesystem event for the path is ignored.

Two refinements over the spec's plain set:

- TTL: filesystem events arrive asynchronously. Even after the write call
  returns, the OS may still emit a delayed CREATE/MODIFIED. A TTL keeps the
  path in the set long enough for delayed events to be matched.

- pause flag: bulk operations like restore_from_snapshot create dozens of
  events that we cannot enumerate ahead of time. The pause flag tells the
  handler to ignore everything until the bulk op finishes.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_TTL_S = 5.0
DEFAULT_PAUSE_COOLDOWN_S = 1.0


class OurWritesTracker:
    """Thread-safe path set with TTL and a pause flag.

    The pause flag has a trailing cooldown: after `paused()` exits, the tracker
    still reports `is_paused == True` for `pause_cooldown_s` seconds. This
    absorbs straggler filesystem events that the OS emits with delay (e.g. from
    a bulk snapshot restore) and would otherwise leak past the pause boundary
    and trigger spurious human_edit_detected entries.
    """

    def __init__(
        self,
        ttl_s: float = DEFAULT_TTL_S,
        pause_cooldown_s: float = DEFAULT_PAUSE_COOLDOWN_S,
    ) -> None:
        self._entries: dict[Path, float] = {}
        self._lock = threading.Lock()
        self._paused: int = 0
        self._pause_cooldown_until: float = 0.0
        self._ttl_s = ttl_s
        self._pause_cooldown_s = pause_cooldown_s

    def add(self, path: Path, *, ttl_s: float | None = None) -> None:
        ttl = ttl_s if ttl_s is not None else self._ttl_s
        deadline = time.monotonic() + ttl
        with self._lock:
            self._entries[path.resolve()] = deadline
            self._gc_locked()

    def remove(self, path: Path) -> None:
        with self._lock:
            self._entries.pop(path.resolve(), None)

    def contains(self, path: Path) -> bool:
        with self._lock:
            self._gc_locked()
            return path.resolve() in self._entries

    @contextmanager
    def writing(self, paths: Iterable[Path]) -> Iterator[None]:
        normalized = [p.resolve() for p in paths]
        for p in normalized:
            self.add(p)
        try:
            yield
        finally:
            for p in normalized:
                self.remove(p)

    @contextmanager
    def paused(self) -> Iterator[None]:
        with self._lock:
            self._paused += 1
        try:
            yield
        finally:
            with self._lock:
                self._paused -= 1
                if self._paused == 0 and self._pause_cooldown_s > 0:
                    self._pause_cooldown_until = (
                        time.monotonic() + self._pause_cooldown_s
                    )

    @property
    def is_paused(self) -> bool:
        with self._lock:
            if self._paused > 0:
                return True
            return time.monotonic() < self._pause_cooldown_until

    def _gc_locked(self) -> None:
        now = time.monotonic()
        expired = [p for p, exp in self._entries.items() if exp < now]
        for p in expired:
            del self._entries[p]
