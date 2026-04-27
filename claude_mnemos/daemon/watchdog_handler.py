"""Watchdog handler — classifies filesystem events into self-writes,
external edits, parse failures, and other anomalies.

External edits to wiki/*.md pages are reflected back into frontmatter:
agent_written goes False, last_human_edit gets a timestamp, and an
ActivityEntry of type human_edit_detected is appended. Other event kinds
become alerts.

Anything unexpected is caught and surfaced as an alert too — the observer
thread must never die from an uncaught exception.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from watchdog.events import (
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.locks import LockTimeoutError, pipeline_lock
from claude_mnemos.core.page_io import (
    PageParseError,
    ParsedPage,
    read_page,
    serialize_page,
)
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.activity import (
    ActivityEntry,
    ActivityLog,
)

logger = logging.getLogger(__name__)

# Files whose mtime is younger than this and whose frontmatter looks fully
# agent-written are assumed to be ingest writes that arrived as MODIFIED via
# atomic replace. The handler skips them to avoid false-positive marks. Trade-
# off: concurrent CLI ingest within a 10s window will not be flagged. Documented
# in design §3.2 as a known limitation; closed when daemon becomes the ingest
# orchestrator (Plan #11+).
INGEST_FRESHNESS_S = 10.0

DEFAULT_LOCK_TIMEOUT_S = 5.0


def _as_str(value: str | bytes) -> str:
    """watchdog event paths are typed `str | bytes`; bring them to str."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class VaultChangeHandler(FileSystemEventHandler):
    def __init__(
        self,
        vault: Path,
        tracker: OurWritesTracker,
        alerts: Alerts,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
    ) -> None:
        self.vault = vault.resolve()
        self.tracker = tracker
        self.alerts = alerts
        self.clock = clock
        self.lock_timeout_s = lock_timeout_s

    # ------------------------------------------------------------------ events

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event, kind="modified")

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event, kind="created")

    def on_moved(self, event: FileSystemEvent) -> None:
        self._handle_moved(event)

    # ------------------------------------------------------------------ logic

    def _handle(self, event: FileSystemEvent, *, kind: str) -> None:
        try:
            if event.is_directory:
                return
            if self.tracker.is_paused:
                return
            path = Path(_as_str(event.src_path)).resolve()
            if not self._is_watched(path):
                return
            if self.tracker.contains(path):
                return
            if kind == "created":
                self.alerts.add(
                    kind="external_create",
                    path=str(path),
                    message="External create detected — ingest manually if needed",
                    detected_at=self.clock(),
                )
                return
            self._mark_human_edited(path)
        except Exception as exc:
            self._record_handler_failure(_as_str(getattr(event, "src_path", "")), exc)

    def _handle_moved(self, event: FileSystemEvent) -> None:
        try:
            if event.is_directory:
                return
            if self.tracker.is_paused:
                return
            assert isinstance(event, FileMovedEvent)
            dst = Path(_as_str(event.dest_path)).resolve()
            src = Path(_as_str(event.src_path)).resolve()
            if not (self._is_watched(dst) or self._is_watched(src)):
                return
            self.alerts.add(
                kind="external_rename",
                path=str(dst),
                message=f"External rename: {src} -> {dst}",
                detected_at=self.clock(),
            )
        except Exception as exc:
            self._record_handler_failure(_as_str(getattr(event, "src_path", "")), exc)

    def _is_watched(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.vault)
        except ValueError:
            return False
        if any(p.startswith(".") for p in rel.parts):
            return False
        if rel.parts[:1] != ("wiki",):
            return False
        return path.suffix == ".md"

    def _mark_human_edited(self, path: Path) -> None:
        try:
            with pipeline_lock(self.vault, timeout=self.lock_timeout_s):
                self._mark_under_lock(path)
        except LockTimeoutError as exc:
            self.alerts.add(
                kind="lock_timeout",
                path=str(path),
                message=str(exc),
                detected_at=self.clock(),
            )

    def _mark_under_lock(self, path: Path) -> None:
        try:
            parsed = read_page(path)
        except PageParseError as exc:
            self.alerts.add(
                kind="parse_failed",
                path=str(path),
                message=f"frontmatter invalid after edit: {exc}",
                detected_at=self.clock(),
            )
            return

        if self._looks_like_recent_ingest_write(path, parsed):
            return

        new_fm = parsed.frontmatter.model_copy(
            update={
                "agent_written": False,
                "last_human_edit": self.clock(),
            }
        )
        new_parsed = ParsedPage(
            frontmatter=new_fm,
            extra_fm=parsed.extra_fm,
            body=parsed.body,
        )
        self.tracker.add(path)
        try:
            atomic_write(path, serialize_page(new_parsed))
        finally:
            self.tracker.remove(path)

        self._append_activity(path)

    def _looks_like_recent_ingest_write(self, path: Path, parsed: ParsedPage) -> bool:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return False
        age_s = time.time() - mtime
        if age_s >= INGEST_FRESHNESS_S:
            return False
        if not parsed.frontmatter.agent_written:
            return False
        return parsed.frontmatter.last_human_edit is None

    def _append_activity(self, path: Path) -> None:
        rel = path.relative_to(self.vault).as_posix()
        log = ActivityLog.load(self.vault)
        entry = ActivityEntry(
            id=uuid4().hex,
            timestamp=self.clock(),
            operation_type="human_edit_detected",
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=[rel],
            metadata={"detected_at": self.clock().isoformat()},
        )
        log.append(entry)
        activity_path = self.vault / ".activity.json"
        self.tracker.add(activity_path)
        try:
            log.save(self.vault)
        finally:
            self.tracker.remove(activity_path)

    def _record_handler_failure(self, raw_path: str, exc: Exception) -> None:
        logger.exception("watchdog handler failed for %s", raw_path)
        try:
            self.alerts.add(
                kind="handler_error",
                path=str(raw_path) if raw_path else "",
                message=str(exc),
                detected_at=self.clock(),
            )
        except Exception:
            # If alerts.add itself fails (e.g. in tests), swallow — we already
            # logged the original exception. The observer thread MUST stay alive.
            logger.exception("alerts.add failed inside handler error path")
