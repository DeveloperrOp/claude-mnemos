"""Desktop launcher window — pywebview wraps the daemon's React SPA.

Lifecycle:
1. Show a static splash HTML ("Connecting to daemon...").
2. Poll http://127.0.0.1:5757/api/health up to 30s.
3. On first 200, navigate the webview to http://127.0.0.1:5757/.
4. Window-close behaviour driven by install-state.window_close_action
   (Task 8 wires that in; this task just opens/closes the window).

Headless mode (--no-window): used by CI smoke tests. Initialises pywebview
without showing a window, exits 0.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

DAEMON_URL = "http://127.0.0.1:5757"
HEALTH_URL = f"{DAEMON_URL}/api/health"
HEALTH_POLL_INTERVAL_S = 0.5
HEALTH_TIMEOUT_S = 30.0

# Separate IPC channel from tray's. Tray IPC receives "show" from `mnemos
# launcher` invocations (CLI / desktop shortcut clicks). Tray then forwards
# "show" to the LIVE launcher process via THIS launcher channel — which
# triggers window.show() on the existing hidden window instead of spawning
# a duplicate. Different name → no message-loopback.
if sys.platform == "win32":
    LAUNCHER_IPC_ADDRESS = r"\\.\pipe\claude-mnemos-launcher"
else:
    LAUNCHER_IPC_ADDRESS = str(Path.home() / ".claude-mnemos" / "launcher.sock")

SPLASH_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>claude-mnemos</title>
<style>
  body { margin:0; font-family: ui-monospace, monospace; background:#0b0d10; color:#9aa3ab;
         display:flex; align-items:center; justify-content:center; height:100vh; }
  .panel { text-align:center; }
  .spinner { width:32px; height:32px; border:3px solid #2a3038; border-top-color:#3ba55c;
             border-radius:50%; margin:0 auto 16px; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg) } }
  h1 { font-size:14px; font-weight:500; margin:0 0 4px; color:#d1d6db; }
  p { font-size:12px; margin:0; }
</style></head>
<body><div class="panel">
  <div class="spinner"></div>
  <h1>claude-mnemos</h1>
  <p>connecting to daemon...</p>
</div></body></html>
"""


def _wait_daemon_ready(*, timeout_s: float = HEALTH_TIMEOUT_S, url: str = HEALTH_URL) -> bool:
    """Poll the daemon health endpoint up to timeout_s. Return True on 2xx, False on timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                code = getattr(r, "status", None) or r.getcode()
                if 200 <= code < 300:
                    return True
        except Exception:
            pass
        time.sleep(HEALTH_POLL_INTERVAL_S)
    return False


def _make_on_closing(window) -> Callable[[], bool]:
    """Build a window-closing handler that respects install_state.window_close_action.

    Return value semantics (matches pywebview window.events.closing):
    - True  → allow window to close (quit launcher process).
    - False → cancel the close (we hide window instead).

    Default behavior: hide window (Discord/Slack convention). User can opt-out
    in Settings → System → "Close window quits the app" toggle.

    Earlier versions tried to ask via window.evaluate_js("confirm(...)") on
    first close. That deadlocked the GUI thread because evaluate_js blocks
    the Python main thread until JS returns, and JS confirm() can't be
    interacted with while the host process appears 'Not Responding'.
    """
    from claude_mnemos.state.install_state import load_install_state

    def _handler() -> bool:
        state = load_install_state()
        if state.window_close_action == "quit":
            return True
        # Default and "hide" both → hide window, keep tray + daemon alive.
        try:
            window.hide()
        except Exception:
            pass
        return False

    return _handler


def _make_show_handler(window) -> Callable[[str], None]:
    """IPC callback: 'show' messages → unhide + restore + focus the window.

    Tray supervisor sends 'show' to LAUNCHER_IPC_ADDRESS when the user
    re-clicks the desktop shortcut while the launcher process is still alive
    with a hidden window. Without this, the click would be a no-op.
    """
    def _on_msg(msg: str) -> None:
        if msg != "show":
            return
        try:
            window.show()
        except Exception:
            pass
        try:
            window.restore()
        except Exception:
            pass

    return _on_msg


def _open_window() -> int:
    """Open a pywebview window. Blocks until the user closes it."""
    import webview
    from claude_mnemos.tray.ipc import IpcServer

    window = webview.create_window(
        title="claude-mnemos",
        html=SPLASH_HTML,
        width=1280,
        height=800,
        min_size=(900, 600),
    )

    # Wire window-close handler
    handler = _make_on_closing(window)
    try:
        # pywebview ≥4 has `window.events.closing` Event
        window.events.closing += handler
    except Exception:
        pass

    # IPC server for "show" messages from supervisor (re-click shortcut while
    # window is hidden).
    ipc_srv: IpcServer | None = None
    try:
        ipc_srv = IpcServer(LAUNCHER_IPC_ADDRESS, on_message=_make_show_handler(window))
        ipc_srv.start()
    except Exception:
        ipc_srv = None  # not fatal — re-click just won't focus existing window

    def _navigate_when_ready() -> None:
        if _wait_daemon_ready():
            try:
                window.load_url(DAEMON_URL)
            except Exception:
                pass
        # else: leave splash; user can close manually.

    t = threading.Thread(target=_navigate_when_ready, daemon=True)
    t.start()

    try:
        webview.start()
    finally:
        if ipc_srv is not None:
            try:
                ipc_srv.stop()
            except Exception:
                pass
    return 0


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claude_mnemos.launcher")
    parser.add_argument("--no-window", action="store_true",
                        help="Initialise pywebview without showing a window. CI smoke test.")
    parser.add_argument("--no-spawn-tray", action="store_true",
                        help="Do NOT auto-spawn the tray supervisor. Used when supervisor is calling us.")
    args = parser.parse_args(argv)

    if args.no_window:
        try:
            import webview  # noqa: F401
        except Exception as exc:
            print(f"[launcher] pywebview import failed: {exc}", file=sys.stderr)
            return 1
        return 0

    return _open_window()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
