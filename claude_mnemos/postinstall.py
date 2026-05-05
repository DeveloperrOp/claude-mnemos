"""First-run-after-install: auto-run mnemos init on the very first launch
of the bundled executable.

Skipped entirely in source mode (development via pipx) — devs run
`mnemos init` explicitly when they want to.
"""

from __future__ import annotations

from datetime import datetime, timezone

from claude_mnemos import runtime
from claude_mnemos.cli_init import run as cli_init_run
from claude_mnemos.state.install_state import load_install_state


def maybe_run_first_time_init() -> None:
    """Run cli_init.run() exactly once per fresh install. Idempotent."""
    if not runtime.is_frozen():
        return
    state = load_install_state()
    if state.first_run_ts is not None:
        return
    cli_init_run(open_browser=True)
    state = load_install_state()  # cli_init may have updated autostart_decision
    state.first_run_ts = datetime.now(tz=timezone.utc)
    state.save()
