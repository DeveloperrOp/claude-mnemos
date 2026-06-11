"""Append-only, line-bounded log of hook-script errors.

Hook scripts run as standalone Python invocations spawned by Claude Code.
They have no daemon connection at the moment of failure, so they log
exceptions to a file instead. The daemon reads the same file to surface
recent failures in the dashboard.

Schema (one JSON object per line, newest at the bottom):

    {
      "ts":         "<ISO 8601 UTC timestamp>",
      "hook":       "session_start" | "session_end",
      "kind":       "exception" | "skipped" | "info",
      "message":    "<one-line summary>",
      "traceback":  "<multi-line, optional>",
      "context":    {<event-specific extras, e.g. session_id, cwd>}
    }

The file is rotated at MAX_LINES (default 200): when adding a new entry
brings the line count over the cap, the oldest lines are dropped.

Storage path: ``~/.claude-mnemos/hook-errors.jsonl`` (configurable via
MNEMOS_HOOK_ERRORS_FILE env var for tests).
"""

from __future__ import annotations

import json
import os
import sys
import traceback as tb_module
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

MAX_LINES = 200


def _log_path() -> Path:
    override = os.environ.get("MNEMOS_HOOK_ERRORS_FILE")
    if override:
        return Path(override)
    return Path.home() / ".claude-mnemos" / "hook-errors.jsonl"


def record(
    *,
    hook: str,
    kind: str,
    message: str,
    traceback: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Append a single record to the log. Tolerates I/O failure silently."""
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "hook": hook,
        "kind": kind,
        "message": message,
        "traceback": traceback,
        "context": context or {},
    }
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Read existing (cheap — capped at MAX_LINES), append, trim, write.
        existing: list[str] = []
        if path.exists():
            try:
                existing = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                existing = []
        existing.append(json.dumps(entry, ensure_ascii=False))
        if len(existing) > MAX_LINES:
            existing = existing[-MAX_LINES:]
        path.write_text("\n".join(existing) + "\n", encoding="utf-8")
    except Exception:
        # Never let logging itself break a hook.
        pass


def record_exception(
    *,
    hook: str,
    exc: BaseException,
    context: dict[str, Any] | None = None,
) -> None:
    """Convenience wrapper that captures exception details."""
    record(
        hook=hook,
        kind="exception",
        message=f"{type(exc).__name__}: {exc}",
        traceback=tb_module.format_exc(),
        context=context,
    )


def read_recent(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` entries (newest first), or [] if no log."""
    path = _log_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


def install_excepthook(hook_name: str) -> None:
    """Install a sys.excepthook that records uncaught exceptions to the log.

    Call this at the very top of session_start.py / session_end.py so any
    crash is captured even if the hook script doesn't have an explicit
    try/except around its main flow.
    """
    original = sys.excepthook

    def _hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        tb: TracebackType | None,
    ) -> None:
        try:
            record(
                hook=hook_name,
                kind="exception",
                message=f"{exc_type.__name__}: {exc_value}",
                traceback="".join(tb_module.format_exception(exc_type, exc_value, tb)),
            )
        finally:
            original(exc_type, exc_value, tb)

    sys.excepthook = _hook
