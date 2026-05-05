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

from datetime import datetime, timezone

from claude_mnemos import runtime
from claude_mnemos.state.install_state import load_install_state


def _silent_init() -> None:
    """Run hook install + tray autostart silently. Failures are swallowed —
    the user can re-run `mnemos init` from a terminal to see diagnostics."""
    try:
        from claude_mnemos.cli_hooks import install as _hooks_install_impl
        _hooks_install_impl()
    except Exception:  # noqa: BLE001
        pass

    try:
        from claude_mnemos.tray.__main__ import _cmd_install as _tray_install_impl
        rc = _tray_install_impl()
        if rc == 0:
            state = load_install_state()
            if state.autostart_decision is None:
                state.autostart_decision = "accepted"
                state.save()
    except Exception:  # noqa: BLE001
        pass


def maybe_run_first_time_init() -> None:
    """Run the silent first-time init exactly once per fresh install. Idempotent."""
    if not runtime.is_frozen():
        return
    state = load_install_state()
    if state.first_run_ts is not None:
        return
    _silent_init()
    state = load_install_state()  # _silent_init may have updated autostart_decision
    state.first_run_ts = datetime.now(tz=timezone.utc)
    state.save()
