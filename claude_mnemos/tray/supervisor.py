"""Tray supervisor — owns the daemon subprocess and a state machine.

Phase 1 (this file): RestartLimiter only. State enum, Supervisor class,
adopt + main loop are added in subsequent tasks.
"""

from __future__ import annotations

import time
from collections import deque
from enum import Enum


class RestartLimiter:
    """Sliding-window crash counter for daemon auto-restart.

    Allows at most ``max_crashes`` crashes inside any rolling
    ``window_seconds`` interval. Backoff between restarts grows
    exponentially (1, 2, 4 seconds), capped at 4 seconds.
    """

    def __init__(
        self,
        *,
        max_crashes: int = 3,
        window_seconds: float = 300.0,
        backoff_cap_seconds: float = 4.0,
    ) -> None:
        self.max_crashes = max_crashes
        self.window_seconds = window_seconds
        self.backoff_cap_seconds = backoff_cap_seconds
        self._crashes: deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._crashes and self._crashes[0] < cutoff:
            self._crashes.popleft()

    def record_crash(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._prune(now)
        self._crashes.append(now)

    def crash_count(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        self._prune(now)
        return len(self._crashes)

    def should_restart(self, now: float | None = None) -> bool:
        return self.crash_count(now) <= self.max_crashes

    def next_backoff_seconds(self) -> float:
        # 1, 2, 4, 4, 4 ...
        n = len(self._crashes)
        if n == 0:
            return 0.0
        delay = 2 ** (n - 1)
        return min(float(delay), self.backoff_cap_seconds)

    def reset(self) -> None:
        self._crashes.clear()


class SupervisorState(Enum):
    STARTING = "starting"
    RUNNING = "running"
    RESTARTING = "restarting"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"


_VALID_TRANSITIONS: dict[SupervisorState | None, set[SupervisorState]] = {
    None: {SupervisorState.STARTING},
    SupervisorState.STARTING: {SupervisorState.RUNNING, SupervisorState.CRASHED},
    SupervisorState.RUNNING: {
        SupervisorState.RESTARTING,
        SupervisorState.STOPPING,
        SupervisorState.CRASHED,
    },
    SupervisorState.RESTARTING: {SupervisorState.RUNNING, SupervisorState.CRASHED},
    SupervisorState.STOPPING: {SupervisorState.STOPPED},
    SupervisorState.STOPPED: {SupervisorState.STARTING},
    SupervisorState.CRASHED: {SupervisorState.STARTING},
}


def valid_transition(
    from_: SupervisorState | None, to_: SupervisorState
) -> bool:
    return to_ in _VALID_TRANSITIONS.get(from_, set())
