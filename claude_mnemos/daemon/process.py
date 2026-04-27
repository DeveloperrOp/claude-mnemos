from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.lockfile import cleanup_pid_file, write_pid_file
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.scheduler import build_scheduler
from claude_mnemos.daemon.schemas import SchedulerJobInfo
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler
from claude_mnemos.daemon.watchdog_observer import VaultObserver

logger = logging.getLogger(__name__)


class MnemosDaemon:
    """Long-running daemon: FastAPI server + APScheduler housekeeping +
    real-time vault watchdog (Plan #9).
    """

    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.scheduler: AsyncIOScheduler = build_scheduler(
            config.vault_root, config.retention_days
        )
        self.tracker = OurWritesTracker()
        self.alerts = Alerts()
        self.app: FastAPI = create_app(config.vault_root, daemon=self)
        self.started_at_monotonic: float = 0.0
        self._server: uvicorn.Server | None = None
        self.observer: VaultObserver | None = None

    def scheduler_jobs_info(self) -> list[SchedulerJobInfo]:
        # `next_run_time` attribute exists only after scheduler.start() resolves
        # the trigger; before that the job is "pending" and access raises.
        return [
            SchedulerJobInfo(
                id=j.id,
                next_run_time=getattr(j, "next_run_time", None),
                trigger=str(j.trigger),
            )
            for j in self.scheduler.get_jobs()
        ]

    async def run(self) -> None:
        write_pid_file(self.config.pid_file, os.getpid())
        self.started_at_monotonic = time.monotonic()
        try:
            self._start_observer()
            self.scheduler.start()
            uconfig = uvicorn.Config(
                app=self.app,
                host=self.config.host,
                port=self.config.port,
                log_level=self.config.log_level,
                lifespan="on",
            )
            self._server = uvicorn.Server(uconfig)
            self._install_signal_handlers()
            await self._server.serve()
        finally:
            self._stop_observer()
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("scheduler shutdown failed")
            cleanup_pid_file(self.config.pid_file)

    def _start_observer(self) -> None:
        """Start the watchdog observer. On failure, log an alert and continue —
        the daemon is still useful as REST + scheduler even without watchdog.
        """
        try:
            handler = VaultChangeHandler(
                self.config.vault_root, self.tracker, self.alerts
            )
            observer = VaultObserver(self.config.vault_root, handler)
            observer.start()
            self.observer = observer
        except Exception as exc:
            logger.exception("failed to start watchdog observer")
            self.alerts.add(
                kind="handler_error",
                path=str(self.config.vault_root),
                message=f"failed to start watchdog observer: {exc}",
                detected_at=datetime.now(UTC),
            )
            self.observer = None

    def _stop_observer(self) -> None:
        if self.observer is None:
            return
        try:
            self.observer.stop()
        except Exception:
            logger.exception("observer stop failed")
        finally:
            self.observer = None

    def _install_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except (NotImplementedError, ValueError):
                # Windows ProactorEventLoop / non-main thread: fallback
                if sys.platform != "win32":
                    signal.signal(sig, lambda *_: self._request_shutdown())

    def _request_shutdown(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
