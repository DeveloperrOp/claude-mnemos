"""Resume-on-boot reconciliation for the Windows in-app self-update swap.

When :mod:`claude_mnemos.core.update_apply` stages a swap it writes a
``swap.pending`` marker BEFORE the elevated inner script renames the install
dir, and that inner script writes ``updates_dir()/<version>/result.txt``
(``OK <ver>`` or ``FAILED: <err>``). If the machine reboots — or the daemon
restarts — mid-swap, the marker survives. This module is invoked once per
daemon process at startup to:

  * detect a swap that SUCCEEDED (we are now running the target version) and
    finish the cleanup the outer script may not have reached (drop the backup
    + clear the marker), or
  * detect a swap that did NOT reach the target (rolled back / interrupted /
    old build relaunched) and record a "failed" outcome — leaving the backup
    in place — so the dashboard can surface it instead of failing silently.

The outcome is persisted to ``updates_dir()/last_apply.json`` and surfaced via
``GET /api/update-status`` (``last_apply``). Every file operation is wrapped so
a corrupt marker is treated as "no pending swap", and
:func:`reconcile_on_startup` never raises — it must never block daemon startup.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_mnemos import __version__
from claude_mnemos.core import update_apply

logger = logging.getLogger(__name__)


def last_apply_path() -> Path:
    return update_apply.updates_dir() / "last_apply.json"


def read_last_apply() -> dict[str, Any] | None:
    """Parse ``last_apply.json``; tolerate a missing/corrupt file (→ ``None``)."""
    path = last_apply_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_last_apply(record: dict[str, Any]) -> None:
    path = last_apply_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("failed to write last_apply.json")


def _result_error(target: str) -> str:
    """First line of ``<target>/result.txt`` (sans ``FAILED: `` prefix), or default."""
    result_path = update_apply.updates_dir() / target / "result.txt"
    try:
        first_line = result_path.read_text(encoding="utf-8-sig").splitlines()[0].strip()
    except (OSError, IndexError):
        return "update did not complete"
    if not first_line:
        return "update did not complete"
    prefix = "FAILED: "
    if first_line.startswith(prefix):
        first_line = first_line[len(prefix):].strip()
    return first_line or "update did not complete"


def _swap_in_progress() -> bool:
    """True when the updater's exclusive ``swap.lock`` is still held by a live
    outer script — i.e. a swap is actively in flight.

    The outer ``relaunch.ps1`` holds the lock with ``FileShare.None`` for the
    whole update, so any other open conflicts. A missing lock file, or one we
    can open, means no swap is running. The OS drops the handle when the outer
    exits, so a crashed updater never wedges this on ``True``.
    """
    lock = update_apply.updates_dir() / "swap.lock"
    if not lock.exists():
        return False
    try:
        with open(lock, "rb"):
            return False
    except OSError:
        return True


def reconcile_pending(running_version: str = __version__) -> dict[str, Any] | None:
    """Reconcile a pending swap marker against the running version.

    Returns the persisted ``last_apply`` record (and writes ``last_apply.json``)
    when a marker was present, else ``None``. A corrupt/unreadable marker is
    treated as "no pending swap" and never raises.
    """
    marker_path = update_apply.pending_marker_path()
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Absent OR corrupt — nothing actionable, never raise.
        return None
    if not isinstance(marker, dict):
        return None

    target = marker.get("version")
    if not isinstance(target, str):
        return None
    old_dir = marker.get("old_dir")

    if running_version == target:
        # We ARE the new build → the swap succeeded. Finish cleanup best-effort.
        status = "ok"
        error: str | None = None
        if isinstance(old_dir, str) and old_dir:
            shutil.rmtree(old_dir, ignore_errors=True)
        _remove_marker(marker_path)
    elif _swap_in_progress():
        # We are NOT the target, but the updater's exclusive swap.lock is still
        # held → the swap is mid-flight and the tray supervisor merely respawned
        # the OLD build in the kill→rename window. Recording 'failed' + clearing
        # the marker here would stamp a phantom failure over a swap that then
        # succeeds. Leave the marker untouched so the REAL new build reconciles
        # it to 'ok' once the swap completes.
        return None
    else:
        # The swap is no longer running and we are not the target: it rolled
        # back / was interrupted. Record the failure; KEEP the backup (old_dir).
        status = "failed"
        error = _result_error(target)
        _remove_marker(marker_path)

    record = {
        "version": target,
        "status": status,
        "error": error,
        "at": datetime.now(UTC).isoformat(),
    }
    _write_last_apply(record)
    return record


def _remove_marker(marker_path: Path) -> None:
    try:
        marker_path.unlink()
    except OSError:
        logger.exception("failed to clear swap.pending marker")


def reconcile_on_startup() -> None:
    """Best-effort startup hook: reconcile a pending swap. Never raises."""
    try:
        reconcile_pending()
    except Exception:  # noqa: BLE001 — must never break daemon startup
        logger.exception("update reconcile_on_startup failed")
