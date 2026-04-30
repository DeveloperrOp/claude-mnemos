"""Pystray-backed system tray icon.

Not unit-tested in CI (pystray requires a display). Manual smoke checklist
lives in docs/plans/2026-04-29-tray-autostart-design.md §12.
"""

from __future__ import annotations

import logging
import re
import webbrowser
from pathlib import Path

import pystray
from PIL import Image

from claude_mnemos.tray.supervisor import Supervisor, SupervisorState

logger = logging.getLogger(__name__)

ASSETS = Path(__file__).parent / "assets"

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
        webbrowser.open(self.dashboard_url)

    def _restart_daemon(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        if self.supervisor is None:
            return
        try:
            self.supervisor.restart()
        except RuntimeError as exc:
            logger.warning("restart failed: %s", exc)

    def _show_logs(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        log = Path.home() / ".claude-mnemos" / "daemon.log"
        if not log.is_file():
            return
        import os
        import subprocess
        import sys

        if sys.platform == "win32":
            os.startfile(str(log))  # noqa: SIM115
        elif sys.platform == "darwin":
            subprocess.run(["open", str(log)], check=False)

    def _quit(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        if self.supervisor is not None:
            self.supervisor.stop()
        self.icon.stop()

    # ── menu / state predicates ─────────────────────────────────
    def _is_running(self) -> bool:
        if self.supervisor is None:
            return False
        return self.supervisor.state == SupervisorState.RUNNING

    def _is_spawned(self) -> bool:
        return self.supervisor is not None and self.supervisor._spawned

    def _build_menu(self) -> pystray.Menu:
        # «Recent events» submenu — built lazily each time menu opens so it
        # reflects current supervisor.log state. pystray.Menu accepts a
        # callable that returns an iterable of MenuItems.
        def recent_events_factory() -> tuple[pystray.MenuItem, ...]:
            events = read_recent_events()
            if not events:
                return (
                    pystray.MenuItem("(no events yet)", None, enabled=False),
                )
            return tuple(
                # Each entry rendered as a disabled item — display only.
                pystray.MenuItem(line, None, enabled=False)
                for line in events
            )

        return pystray.Menu(
            pystray.MenuItem("Open dashboard", self._open_dashboard, default=True,
                             enabled=lambda _: self._is_running()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart daemon", self._restart_daemon,
                             enabled=lambda _: self._is_spawned()),
            pystray.MenuItem("Recent events", pystray.Menu(recent_events_factory)),
            pystray.MenuItem("Show full log", self._show_logs),
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
