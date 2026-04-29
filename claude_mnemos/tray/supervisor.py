"""Tray supervisor — owns the daemon subprocess and a state machine.

Phase 1 (this file): RestartLimiter only. State enum, Supervisor class,
adopt + main loop are added in subsequent tasks.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import httpx
import psutil

from claude_mnemos.daemon.lockfile import is_daemon_running

logger = logging.getLogger(__name__)


@dataclass
class HealthSnapshot:
    reachable: bool
    projects_mounted: int = 0
    uptime_seconds: float | None = None


def _default_health_url() -> str:
    return "http://localhost:5757/health"


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


class Supervisor:
    """Owns daemon subprocess (or adopts an existing one) + state machine.

    Spawned mode: ``self._proc`` is the Popen object we control. ``stop`` and
    ``restart`` terminate it.

    Adopted mode: external process already running per ``daemon_pid_file``.
    ``stop`` only deregisters ourselves; we MUST NOT kill it.
    """

    def __init__(
        self,
        *,
        daemon_pid_file: Path,
        log_path: Path | None = None,
    ) -> None:
        self.daemon_pid_file = daemon_pid_file
        self.log_path = log_path
        self.state: SupervisorState | None = None
        self.daemon_pid: int | None = None
        self.limiter = RestartLimiter()
        self._proc: subprocess.Popen | None = None
        self._spawned: bool = False
        self._log_fh = None
        self.last_health: HealthSnapshot | None = None
        self.health_url = _default_health_url()
        self._http: httpx.Client | None = None

    # ── liveness helper, mockable ───────────────────────────────
    def _is_existing_daemon_running(self) -> int | None:
        return is_daemon_running(self.daemon_pid_file)

    # ── state transitions ───────────────────────────────────────
    def _transition(self, new: SupervisorState) -> None:
        if not valid_transition(self.state, new):
            raise RuntimeError(f"invalid transition {self.state} → {new}")
        logger.info("[supervisor] state %s → %s", self.state, new)
        self.state = new

    def mark_running(self) -> None:
        self._transition(SupervisorState.RUNNING)

    # ── subprocess lifecycle ────────────────────────────────────
    def _spawn_daemon(self) -> subprocess.Popen:
        cmd = [sys.executable, "-m", "claude_mnemos.daemon", "foreground", "--all"]
        creationflags = 0
        if sys.platform == "win32":
            # CREATE_NEW_PROCESS_GROUP so we can send CTRL_BREAK_EVENT later;
            # don't use DETACHED_PROCESS — we want stdout/stderr handles.
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_fh = self.log_path.open("a", encoding="utf-8", buffering=1)
            stdout = self._log_fh
            stderr = self._log_fh
        else:
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL

        proc = subprocess.Popen(
            cmd,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
        return proc

    def start(self) -> None:
        existing = self._is_existing_daemon_running()
        if existing:
            self._proc = None
            self._spawned = False
            self.daemon_pid = existing
            self._transition(SupervisorState.STARTING)
            self._transition(SupervisorState.RUNNING)
            return

        self._proc = self._spawn_daemon()
        self._spawned = True
        self.daemon_pid = self._proc.pid
        self._transition(SupervisorState.STARTING)

    def stop(self, *, grace_seconds: float = 10.0) -> None:
        self._transition(SupervisorState.STOPPING)
        if self._spawned and self._proc is not None:
            try:
                self._proc.terminate()
            except (ProcessLookupError, OSError) as exc:
                logger.warning("[supervisor] terminate() raised %r", exc)
            try:
                self._proc.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                logger.warning("[supervisor] grace expired, killing pid=%s", self._proc.pid)
                with contextlib.suppress(OSError):
                    self._proc.kill()
        self._close_log_fh()
        self._transition(SupervisorState.STOPPED)

    def restart(self, *, grace_seconds: float = 5.0) -> None:
        if not self._spawned:
            raise RuntimeError("cannot restart adopted daemon")
        self._transition(SupervisorState.RESTARTING)
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            except (ProcessLookupError, OSError):
                pass
        self._close_log_fh()
        self._proc = self._spawn_daemon()
        self.daemon_pid = self._proc.pid
        self.limiter.reset()
        # Restarting → Starting needs a separate path; do it directly,
        # bypassing the normal Restarting → Running edge until /health succeeds.
        self.state = SupervisorState.STARTING
        logger.info("[supervisor] restart spawned pid=%s, state=Starting", self._proc.pid)

    def _http_client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=2.0)
        return self._http

    def _check_health(self) -> HealthSnapshot:
        try:
            resp = self._http_client().get(self.health_url)
            if resp.status_code != 200:
                return HealthSnapshot(reachable=False)
            data = resp.json()
            return HealthSnapshot(
                reachable=True,
                projects_mounted=int(data.get("projects_mounted", 0)),
                uptime_seconds=data.get("uptime_seconds"),
            )
        except (httpx.HTTPError, ValueError):
            return HealthSnapshot(reachable=False)

    def _spawned_daemon_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _adopted_daemon_alive(self) -> bool:
        return self.daemon_pid is not None and psutil.pid_exists(self.daemon_pid)

    def tick(self, *, now: float | None = None) -> None:
        """Single iteration of the supervisor loop.

        Called periodically (every ~5s). Polls subprocess liveness and
        /health, drives state transitions.
        """
        now = time.monotonic() if now is None else now

        # User-initiated Stopping → don't react to subprocess exit
        if self.state in (SupervisorState.STOPPING, SupervisorState.STOPPED):
            return
        if self.state == SupervisorState.CRASHED:
            return  # manual restart only

        if self._spawned:
            if not self._spawned_daemon_alive():
                self._handle_crash(now)
                return
        else:
            if not self._adopted_daemon_alive():
                logger.warning(
                    "[supervisor] adopted daemon pid=%s gone — entering Crashed",
                    self.daemon_pid,
                )
                self.state = SupervisorState.CRASHED
                return

        snap = self._check_health()
        self.last_health = snap

        if self.state == SupervisorState.STARTING and snap.reachable:
            self._transition(SupervisorState.RUNNING)

    def _handle_crash(self, now: float) -> None:
        self.limiter.record_crash(now=now)
        if not self.limiter.should_restart(now=now):
            logger.error(
                "[supervisor] crash %d/%d in window — entering Crashed",
                self.limiter.crash_count(now=now), self.limiter.max_crashes,
            )
            self.state = SupervisorState.CRASHED
            return
        backoff = self.limiter.next_backoff_seconds()
        logger.warning(
            "[supervisor] daemon crashed, backoff %.1fs (count=%d)",
            backoff, self.limiter.crash_count(now=now),
        )
        time.sleep(backoff)
        self._close_log_fh()
        self._proc = self._spawn_daemon()
        self.daemon_pid = self._proc.pid
        self.state = SupervisorState.STARTING

    def _close_log_fh(self) -> None:
        if self._log_fh:
            with contextlib.suppress(Exception):
                self._log_fh.close()
            self._log_fh = None
