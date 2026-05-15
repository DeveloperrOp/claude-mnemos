"""First-run-after-install: silently set up hooks + tray autostart on the
very first launch of the bundled executable.

Skipped entirely in source mode (development via pipx) — devs run
`mnemos init` explicitly when they want to.

Why silent (not `mnemos init`):
  The bundled `claude-mnemos.exe` is windowed (console=False), so stdout
  output from cli_init.run() goes nowhere visible. More importantly,
  cli_init waits up to 30s for daemon health and then opens a browser —
  but the launcher window itself already polls health on a splash screen
  and IS the UI, so the legacy "open browser" step is redundant and the
  30s blocking wait would just delay the launcher window from appearing.

  This silent path does only the two installs that have to happen exactly
  once (hooks → ~/.claude/settings.json, autostart → Startup folder).
  Everything else (daemon spawn, dashboard) is the launcher's job.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from claude_mnemos import runtime
from claude_mnemos.state.install_state import load_install_state

logger = logging.getLogger(__name__)


def _silent_init() -> list[str]:
    """Run hook install + tray autostart silently.

    Returns the list of error messages from sub-steps that failed. Callers
    persist this on ``InstallState.last_install_error`` so a "looks fine but
    nothing ingests" symptom has a visible breadcrumb instead of silent
    ``except: pass``.
    """
    errors: list[str] = []
    try:
        from claude_mnemos.cli_hooks import install as _hooks_install_impl
        _hooks_install_impl()
    except Exception as exc:  # noqa: BLE001
        msg = f"hooks install failed: {exc!r}"
        logger.exception("postinstall: hooks install failed")
        errors.append(msg)

    try:
        from claude_mnemos.tray.__main__ import _cmd_install as _tray_install_impl
        rc = _tray_install_impl()
        if rc == 0:
            state = load_install_state()
            if state.autostart_decision is None:
                state.autostart_decision = "accepted"
                state.save()
        else:
            errors.append(f"tray autostart install returned non-zero rc={rc}")
    except Exception as exc:  # noqa: BLE001
        msg = f"tray autostart install failed: {exc!r}"
        logger.exception("postinstall: tray autostart install failed")
        errors.append(msg)

    return errors


def maybe_run_first_time_init() -> None:
    """Run the silent first-time init exactly once per fresh install. Idempotent."""
    if not runtime.is_frozen():
        return
    state = load_install_state()
    if state.first_run_ts is not None:
        return
    errors = _silent_init()
    state = load_install_state()  # _silent_init may have updated autostart_decision
    state.first_run_ts = datetime.now(tz=timezone.utc)
    state.last_install_error = "; ".join(errors) if errors else None
    state.save()
