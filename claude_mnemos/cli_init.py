"""`mnemos init` — single-command bootstrap.

Replaces the three-step flow (`hooks install` + `tray start` + open
browser) for new users. Idempotent: re-running on an already-set-up
machine is safe and prints OK for already-done steps.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
import webbrowser

from claude_mnemos.cli_hooks import install as _hooks_install_impl
from claude_mnemos.tray.__main__ import _cmd_install as _tray_install_impl

DEFAULT_DAEMON_URL = "http://127.0.0.1:5757/api/health"
HEALTH_TIMEOUT_S = 30.0
HEALTH_POLL_INTERVAL_S = 0.5
DASHBOARD_URL = "http://localhost:5757"


def _print(symbol: str, text: str) -> None:
    sys.stdout.write(f"  {symbol} {text}\n")
    sys.stdout.flush()


def _install_hooks_safe() -> dict | None:
    """Wrapper isolating hook-install for monkeypatching in tests."""
    return _hooks_install_impl()


def _install_tray_autostart_safe() -> bool:
    """Returns True on success, False on any failure (Linux unsupported, etc)."""
    try:
        rc = _tray_install_impl()
        return rc == 0
    except Exception:  # noqa: BLE001
        return False


def _wait_daemon_health(url: str = DEFAULT_DAEMON_URL, timeout_s: float = HEALTH_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 300:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(HEALTH_POLL_INTERVAL_S)
    return False


def _open_browser(url: str = DASHBOARD_URL) -> None:
    webbrowser.open(url)


def run(*, open_browser: bool = True) -> int:
    """Returns 0 on success, non-zero only on hook-install failure (the one fatal step)."""
    sys.stdout.write("mnemos init — setting up Claude Code memory\n\n")

    # 1. Hooks
    try:
        _install_hooks_safe()
        _print("OK", "hooks installed (SessionStart, SessionEnd, PreCompact)")
    except Exception as exc:  # noqa: BLE001
        _print("FAIL", f"hooks install failed: {exc}")
        sys.stdout.write("\nFix the error above and re-run `mnemos init`.\n")
        return 2

    # 2. Tray autostart (non-fatal)
    if _install_tray_autostart_safe():
        _print("OK", "tray autostart registered")
        try:
            from claude_mnemos.state.install_state import load_install_state
            s = load_install_state()
            if s.autostart_decision is None:
                s.autostart_decision = "accepted"
                s.save()
        except Exception:
            pass
    else:
        _print("WARN", "tray autostart skipped (unsupported platform or already running)")

    # 3. Wait for daemon health
    if _wait_daemon_health():
        _print("OK", "daemon is responding on :5757")
    else:
        _print(
            "WARN",
            f"daemon did not respond within {int(HEALTH_TIMEOUT_S)}s — open dashboard "
            f"manually at {DASHBOARD_URL} once it starts",
        )

    # 4. Browser
    if open_browser:
        _open_browser(DASHBOARD_URL)
        _print("OK", f"opened {DASHBOARD_URL} in your browser")

    sys.stdout.write("\nDone. Welcome to mnemos.\n")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    return run(open_browser=not args.no_browser)


def add_init_subparser(parent: argparse._SubParsersAction) -> None:
    p = parent.add_parser("init", help="One-command setup: hooks + autostart + dashboard")
    p.add_argument("--no-browser", action="store_true", help="Do not auto-open the dashboard")
    p.set_defaults(func=_cmd_init)
