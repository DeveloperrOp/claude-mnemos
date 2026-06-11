"""Pystray-backed system tray icon.

Not unit-tested in CI (pystray requires a display). Manual smoke checklist
lives in docs/plans/2026-04-29-tray-autostart-design.md §12.

NOTE: ``import pystray`` is wrapped in try/except because on Linux pystray's
``_xorg`` backend connects to the X DISPLAY at module-import time. CI runners
have no DISPLAY → import would crash any module that transitively imports
this one (e.g. daemon/app.py via daemon/routes/tray.py). When pystray fails
to import, ``TrayApp`` raises a clear error at instantiation but module
import succeeds — REST routes can still serve.
"""

from __future__ import annotations

import logging
import re
import webbrowser
from pathlib import Path

try:
    import pystray  # type: ignore[import-not-found]
except Exception as _pystray_err:  # noqa: BLE001
    pystray = None  # type: ignore[assignment]
    _PYSTRAY_IMPORT_ERROR: Exception | None = _pystray_err
else:
    _PYSTRAY_IMPORT_ERROR = None

try:
    from PIL import Image  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    Image = None  # type: ignore[assignment]

from claude_mnemos.runtime import tray_assets_dir as _runtime_tray_assets_dir
from claude_mnemos.tray.supervisor import Supervisor, SupervisorState

logger = logging.getLogger(__name__)

ASSETS = _runtime_tray_assets_dir()

SUPERVISOR_LOG = Path.home() / ".claude-mnemos" / "supervisor.log"
RECENT_EVENTS_LIMIT = 8

# Match Python logging default format:
#   2026-04-30 14:30:01,123 [INFO] claude_mnemos.tray.supervisor: state Starting → Running
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.]\d+\s+\[(\w+)\]\s+[\w.]+:\s*(.+)$"
)


def _load_image(name: str) -> Image.Image:
    path = ASSETS / name
    return Image.open(str(path))


def read_recent_events(
    log_path: Path = SUPERVISOR_LOG,
    limit: int = RECENT_EVENTS_LIMIT,
) -> list[str]:
    """Read the last ``limit`` parsed events from the supervisor log.

    Each result is a one-line summary: ``HH:MM:SS  <message>``. Returns
    empty list if the log doesn't exist yet or can't be read.

    Designed for the tray-icon submenu — keep entries short, don't crash
    on malformed lines.
    """
    if not log_path.is_file():
        return []
    try:
        # Tail-read by reading the whole file (supervisor.log is small).
        # If it ever grows large we can switch to seek-from-end, but for now
        # this is simpler and safe.
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    events: list[str] = []
    # Walk from the end and collect last `limit` parseable lines.
    for line in reversed(lines):
        m = _LOG_LINE_RE.match(line)
        if not m:
            continue
        timestamp, _level, msg = m.group(1), m.group(2), m.group(3)
        # Show only HH:MM:SS portion to keep menu narrow.
        time_only = timestamp.split(" ", 1)[1] if " " in timestamp else timestamp
        # Truncate long messages to fit a tray menu reasonably.
        if len(msg) > 70:
            msg = msg[:67] + "…"
        events.append(f"{time_only}  {msg}")
        if len(events) >= limit:
            break
    events.reverse()  # oldest first
    return events


class TrayApp:
    """Pystray icon + menu + simple repaint loop driven by the supervisor."""

    def __init__(
        self,
        *,
        supervisor: Supervisor | None,
        dashboard_url: str = "http://localhost:5757/",
    ) -> None:
        if pystray is None:
            raise RuntimeError(
                f"pystray is not available in this environment: {_PYSTRAY_IMPORT_ERROR}. "
                "Run a desktop session with X DISPLAY (Linux) or use a Windows/Mac runtime."
            )
        self.supervisor = supervisor
        self.dashboard_url = dashboard_url
        self.icon = pystray.Icon(
            "mnemos",
            icon=_load_image("icon-running.png"),
            title="Mnemos",
            menu=self._build_menu(),
        )

    # ── menu actions ────────────────────────────────────────────
    def _open_dashboard(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        if self.supervisor is None:
            # Fallback: no supervisor → just open browser
            webbrowser.open(self.dashboard_url)
            return
        try:
            self.supervisor.open_launcher()
        except Exception:
            logger.exception("[tray] open_launcher failed; falling back to browser")
            webbrowser.open(self.dashboard_url)

    def _toggle_pause(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        if self.supervisor is None:
            return
        if getattr(self.supervisor, "daemon_paused", False):
            self.supervisor.resume_daemon()
        else:
            self.supervisor.pause_daemon()

    def _open_settings(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        """Open the launcher and let the React SPA route to /settings/global itself."""
        self._open_dashboard(_icon, _item)

    def _quit(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        if self.supervisor is not None:
            try:
                self.supervisor.shutdown()
            except Exception:
                logger.exception("[tray] supervisor.shutdown failed")
        self.icon.stop()

    # ── menu / state predicates ─────────────────────────────────
    def _is_running(self) -> bool:
        if self.supervisor is None:
            return False
        return self.supervisor.state == SupervisorState.RUNNING

    def _is_spawned(self) -> bool:
        return self.supervisor is not None and self.supervisor._spawned

    def _build_menu(self) -> pystray.Menu:
        def _daemon_status_label(_item) -> str:
            sv = self.supervisor
            if sv is None:
                return "Daemon: no supervisor"
            if getattr(sv, "daemon_paused", False):
                return "Daemon: Paused"
            if self._is_running():
                return "Daemon: Running"
            return "Daemon: Stopped"

        def _toggle_label(_item) -> str:
            if self.supervisor is not None and getattr(self.supervisor, "daemon_paused", False):
                return "Resume Daemon"
            return "Pause Daemon"

        return pystray.Menu(
            pystray.MenuItem("Open Dashboard", self._open_dashboard, default=True),
            pystray.MenuItem(_daemon_status_label, None, enabled=False),
            pystray.MenuItem(_toggle_label, self._toggle_pause,
                             enabled=lambda _: self.supervisor is not None),
            pystray.MenuItem("Settings...", self._open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    # ── repaint ─────────────────────────────────────────────────
    def repaint(self) -> None:
        if self.supervisor is None:
            self.icon.title = "Mnemos · no supervisor"
            return
        st = self.supervisor.state
        if st in (SupervisorState.RUNNING, SupervisorState.STARTING, SupervisorState.RESTARTING):
            self.icon.icon = _load_image("icon-running.png")
        else:
            self.icon.icon = _load_image("icon-stopped.png")
        snap = self.supervisor.last_health
        if snap and snap.reachable:
            mounted = snap.projects_mounted
            self.icon.title = f"Mnemos · {mounted} project{'s' if mounted != 1 else ''} mounted"
        else:
            self.icon.title = f"Mnemos · {st.value if st else 'unknown'}"

    def run(self) -> None:
        self.icon.run()
