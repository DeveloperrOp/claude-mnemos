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

import hashlib
import logging
import re
import threading
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

# Atomic-save marker that Obsidian / VSCode / many other text editors
# use: `note.md.{hex32}.tmp` first, then rename to `note.md`. We treat
# this exact pattern as an editor save, not as an alert-worthy external
# rename. The hex character set is deliberately strict so a real user
# rename can't accidentally match.
_EDITOR_TMP_SUFFIX_RE = re.compile(r"\.[a-f0-9]{6,}\.tmp$", re.IGNORECASE)


def _looks_like_editor_atomic_save(src: Path, dst: Path) -> bool:
    """Return True if src/dst look like a text editor's atomic save."""
    s = str(src)
    m = _EDITOR_TMP_SUFFIX_RE.search(s)
    if m is None:
        return False
    # Strip the `.{hex}.tmp` suffix from src and compare to dst.
    stripped = s[: m.start()]
    return stripped == str(dst)


logger = logging.getLogger(__name__)

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
        # Content-signature cache (sha256 hex, byte length) per page. Tells a
        # real content edit from a metadata/atime touch — on Windows a mere read
        # bumps last-access-time, which surfaces as a FileModifiedEvent
        # indistinguishable from a write. Without this gate, reading/linting/
        # opening the vault in Obsidian would falsely flip agent_written.
        self._sigs: dict[Path, tuple[str, int]] = {}
        self._sigs_lock = threading.Lock()
        self._seed_signatures()

    def _content_signature(self, path: Path) -> tuple[str, int] | None:
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return (hashlib.sha256(data).hexdigest(), len(data))

    def _seed_signatures(self) -> None:
        """Baseline every existing wiki page so the first event after start is
        compared, not assumed. Best-effort."""
        wiki = self.vault / "wiki"
        if not wiki.is_dir():
            return
        for p in wiki.rglob("*.md"):
            if any(part.startswith(".") for part in p.relative_to(self.vault).parts):
                continue
            sig = self._content_signature(p.resolve())
            if sig is not None:
                with self._sigs_lock:
                    self._sigs[p.resolve()] = sig

    def _rebaseline(self, path: Path) -> None:
        sig = self._content_signature(path)
        with self._sigs_lock:
            if sig is None:
                self._sigs.pop(path, None)
            else:
                self._sigs[path] = sig

    def reseed_signatures(self) -> None:
        """Drop and rebuild the whole signature cache from current on-disk bytes.

        Call after a bulk vault swap that the observer SURVIVED — e.g. an
        activity undo, which restores a snapshot in place without rebuilding the
        handler. Without this, every restored page differs from its stale cached
        signature, so the next event (even a read) reads as a content edit and
        false-flips the restored page to human-edited. (The snapshot-restore
        route rebuilds the handler instead, so it doesn't need this.)
        """
        with self._sigs_lock:
            self._sigs.clear()
        self._seed_signatures()

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
                # Daemon's own write (ingest/flip/etc). Re-baseline so the next
                # external event compares against the freshly-written content
                # instead of stale bytes (which would look like an edit).
                self._rebaseline(path)
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
            # Suppress alerts for moves that the daemon initiated itself —
            # StagingTransaction registers move sources/destinations in the
            # tracker before shutil.move runs.
            if self.tracker.contains(src) or self.tracker.contains(dst):
                return
            # v0.0.38: also suppress the Obsidian/VSCode-style atomic
            # save pattern: `note.md.{hexUUID}.tmp` → `note.md`. These
            # produce one external_rename alert per save and flood the
            # Health page with noise even though the user did nothing
            # we'd want to surface. The hex-suffix-before-.tmp marker
            # is specific enough to atomic-write editors not to misfire
            # on a real manual rename.
            if _looks_like_editor_atomic_save(src, dst):
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
        # Gate on a real content change BEFORE parsing. A metadata/atime/attrib
        # event (e.g. a read on a last-access-enabled volume) must produce NO
        # side effects — not even a parse_failed alert on an already-broken
        # page, which would re-flood Health with the same read-triggered noise
        # this gate exists to kill.
        cur_sig = self._content_signature(path)
        with self._sigs_lock:
            prev_sig = self._sigs.get(path)
        if prev_sig is None:
            # First time we see this page — baseline it and do NOT flip. Don't
            # treat an unverifiable first observation as a human edit.
            if cur_sig is not None:
                with self._sigs_lock:
                    self._sigs[path] = cur_sig
            return
        if cur_sig == prev_sig:
            # Byte-identical: a metadata/atime/attrib event, not a content edit.
            return

        # Content genuinely changed. Re-baseline up front so that if the new
        # content has broken frontmatter, later metadata events on the same
        # broken bytes don't re-emit parse_failed — we alert once per change.
        self._rebaseline(path)

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

        # Re-baseline to the post-flip bytes so the flip's own write event
        # (the atomic_write above) won't be re-read as a fresh human edit.
        self._rebaseline(path)

        # Activity append is best-effort: page mutation already succeeded, so
        # a failure here (e.g. ActivityCorruptError) must not propagate and
        # leave the page partially "marked but unlogged". Surface as alert.
        try:
            self._append_activity(path)
        except Exception as exc:
            logger.exception("watchdog handler: activity append failed for %s", path)
            self.alerts.add(
                kind="handler_error",
                path=str(path),
                message=f"page marked human-edited but activity log append failed: {exc}",
                detected_at=self.clock(),
            )

    def _append_activity(self, path: Path) -> None:
        rel = path.relative_to(self.vault).as_posix()
        ts = self.clock()
        log = ActivityLog.load(self.vault)
        entry = ActivityEntry(
            id=uuid4().hex,
            timestamp=ts,
            operation_type="human_edit_detected",
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=[rel],
            metadata={"detected_at": ts.isoformat()},
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
