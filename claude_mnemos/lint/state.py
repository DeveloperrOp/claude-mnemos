"""Persistent cache of the last LintReport in <vault>/.lint-results.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.lint.exceptions import LintCorruptError
from claude_mnemos.lint.models import LintReport

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker

LINT_RESULTS_FILENAME = ".lint-results.json"


def load_last_report(vault: Path) -> LintReport | None:
    """Load <vault>/.lint-results.json. Returns None if missing.

    Raises LintCorruptError if the file is invalid JSON or fails Pydantic
    schema validation. Two-step parse so each error path produces an
    accurate message.
    """
    path = vault / LINT_RESULTS_FILENAME
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LintCorruptError(
            f"lint results at {path} is not valid JSON: {exc}"
        ) from exc
    try:
        return LintReport.model_validate(data)
    except ValidationError as exc:
        raise LintCorruptError(
            f"lint results at {path} fails schema: {exc}"
        ) from exc


def save_report(
    vault: Path,
    report: LintReport,
    *,
    tracker: OurWritesTracker | None = None,
) -> None:
    """Atomically write <vault>/.lint-results.json. Tracker (optional) is
    notified before the write and after, so a parallel watchdog can suppress
    its own self-write event for this dotfile (defensive — dotfile path is
    already filtered by the handler).
    """
    path = vault / LINT_RESULTS_FILENAME
    if tracker is not None:
        tracker.add(path)
    try:
        atomic_write(path, report.model_dump_json(indent=2) + "\n")
    finally:
        if tracker is not None:
            tracker.remove(path)
