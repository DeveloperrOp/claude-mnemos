"""Async job worker — pulls ready jobs and dispatches to handlers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import traceback
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from apscheduler.triggers.date import DateTrigger

from claude_mnemos.daemon.jobs.handlers import JobHandler
from claude_mnemos.state.jobs import Job, JobKind, JobStore

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class JobWorker:
    DEFAULT_POLL_INTERVAL_S = 5.0

    def __init__(
        self,
        *,
        store: JobStore,
        handlers: dict[JobKind, JobHandler],
        scheduler: AsyncIOScheduler | None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    ) -> None:
        self._store = store
        self._handlers = handlers
        self._scheduler = scheduler
        self._poll_interval_s = poll_interval_s
        self._stop = asyncio.Event()
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("JobWorker already started")
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self, *, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wakeup.set()  # break out of any wait_for
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except TimeoutError:
                # Task is wedged inside a handler — cancel it so we don't
                # leak the asyncio task across daemon shutdown / unmount.
                # Underlying threads (asyncio.to_thread) may finish later,
                # but their results are discarded.
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):  # noqa: BLE001
                    await self._task
                logger.warning("JobWorker stop timed out, task cancelled")

    def signal_wakeup(self) -> None:
        """Schedule wakeup (called by APScheduler trigger or external signal)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._wakeup.set)

    def try_dequeue_one(self) -> Job | None:
        """Single dequeue entrypoint — honours JobStore.is_paused().

        Returns None when the queue is paused (rate-limited) so callers
        leave queued jobs untouched. Otherwise delegates to
        JobStore.claim_next_ready (atomic claim).
        """
        if self._store.is_paused():
            return None
        return self._store.claim_next_ready(now=datetime.now(UTC))

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self.try_dequeue_one()
            except Exception:
                logger.exception("job claim failed")
                # The claim may have succeeded at SQL level (row marked
                # running) but failed to deserialize, e.g. unknown kind.
                # Sweep any orphaned running rows whose kind has no handler
                # and mark them failed so they don't get stuck.
                self._sweep_orphan_unknown_kinds()
                await self._sleep_or_wakeup()
                continue

            if job is None:
                await self._sleep_or_wakeup()
                continue

            await self._run_job(job)

    def _sweep_orphan_unknown_kinds(self) -> None:
        try:
            running = self._store.list_running_kinds()
        except Exception:
            logger.exception("failed to sweep orphan running rows")
            return
        for job_id, kind in running:
            if kind not in self._handlers:
                logger.warning("sweeping orphan job %s (kind=%s)", job_id, kind)
                try:
                    self._store.mark_failed_with_retry(
                        job_id,
                        error=f"no handler for kind={kind!r}",
                        traceback="",
                        finished_at=datetime.now(UTC),
                    )
                except Exception:
                    logger.exception(
                        "failed to mark orphan job %s as failed", job_id
                    )

    async def _sleep_or_wakeup(self) -> None:
        try:
            await asyncio.wait_for(self._wakeup.wait(), timeout=self._poll_interval_s)
            self._wakeup.clear()
        except TimeoutError:
            pass

    async def _run_job(self, job: Job) -> None:
        handler = self._handlers.get(job.kind)
        if handler is None:
            self._store.mark_failed_with_retry(
                job.id,
                error=f"no handler for kind={job.kind!r}",
                traceback="",
                finished_at=datetime.now(UTC),
            )
            return
        try:
            await handler.run(job)
        except Exception as exc:
            tb = traceback.format_exc()
            updated = self._store.mark_failed_with_retry(
                job.id,
                error=str(exc),
                traceback=tb,
                finished_at=datetime.now(UTC),
            )
            self._schedule_retry_wakeup(updated)
            return
        self._store.mark_succeeded(job.id, finished_at=datetime.now(UTC))

    def _schedule_retry_wakeup(self, job: Job) -> None:
        if self._scheduler is None or job.status != "queued":
            return
        run_at = job.next_attempt_at
        if run_at < datetime.now(UTC):
            run_at = datetime.now(UTC)
        try:
            self._scheduler.add_job(
                self.signal_wakeup,
                trigger=DateTrigger(run_date=run_at),
                id=f"jobs-wakeup-{job.id}-{job.attempt}",
                replace_existing=True,
            )
        except Exception:
            logger.exception("failed to schedule jobs-wakeup")
