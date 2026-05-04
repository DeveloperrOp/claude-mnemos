"""`mnemos doctor` — human-readable health check.

Hits the daemon's /api/onboarding/setup-status when reachable, falls
back to running install_checks directly if daemon is down. Prints
colored [OK]/[WARN]/[FAIL] rows. Exit 0 on all-OK, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

from claude_mnemos.core.install_checks import (
    check_claude_cli_installed,
    check_hooks_present,
)

DAEMON_STATUS_URL = "http://127.0.0.1:5757/api/onboarding/setup-status"
ROW_NAMES = ("claude_cli", "hooks", "vaults", "projects")


def _fetch_setup_status() -> dict[str, Any] | None:
    """Try the daemon first; return None on any error."""
    try:
        with urllib.request.urlopen(DAEMON_STATUS_URL, timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _local_setup_status() -> dict[str, Any]:
    """Daemon-down fallback: run only the local install checks."""
    cli = check_claude_cli_installed()
    hooks = check_hooks_present()
    rows = {
        "claude_cli": (
            {"status": "ok", "message": "Claude CLI installed"}
            if cli is None
            else {"status": cli.severity, "message": cli.message}
        ),
        "hooks": (
            {"status": "ok", "message": "Hooks installed"}
            if hooks is None
            else {"status": hooks.severity, "message": hooks.message}
        ),
        "vaults": {"status": "warning", "message": "Daemon offline; cannot check vault writability."},
        "projects": {"status": "warning", "message": "Daemon offline; cannot count projects."},
    }
    return {
        "all_ok": all(r["status"] == "ok" for r in rows.values()),
        **rows,
    }


def _label(status: str) -> str:
    return {
        "ok": "[OK]  ",
        "info": "[INFO]",
        "warning": "[WARN]",
        "critical": "[FAIL]",
    }.get(status, "[????]")


def run() -> int:
    status = _fetch_setup_status() or _local_setup_status()
    sys.stdout.write("mnemos doctor — install + operational health check\n\n")
    for name in ROW_NAMES:
        row = status.get(name, {"status": "warning", "message": "missing"})
        sys.stdout.write(f"  {_label(row['status'])} {name:<14} {row['message']}\n")
    sys.stdout.write("\n")
    if status["all_ok"]:
        sys.stdout.write("All systems nominal.\n")
        return 0
    sys.stdout.write("One or more issues detected. Run `mnemos hooks install` or visit\n")
    sys.stdout.write("the dashboard's Diagnostics tab at http://localhost:5757/diagnostics\n")
    return 1


def _cmd_doctor(_args: argparse.Namespace) -> int:
    return run()


def add_doctor_subparser(parent: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = parent.add_parser("doctor", help="Print install + operational health check")
    p.set_defaults(func=_cmd_doctor)
