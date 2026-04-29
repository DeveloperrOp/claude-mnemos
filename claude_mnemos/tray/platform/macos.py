"""macOS autostart via launchd LaunchAgent plist.

Plist lives at ``~/Library/LaunchAgents/com.claude-mnemos.tray.plist``.
``launchctl load -w`` registers it (with -w persisting across reboots),
``unload -w`` deregisters.

Idempotency:
- ``install`` (re)writes plist and (re-)loads via launchctl.
- ``uninstall`` only calls launchctl if plist exists, then unlinks.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from claude_mnemos.tray.platform.base import AutostartManager, AutostartStatus

BUNDLE_ID = "com.claude-mnemos.tray"
PLIST_FILENAME = f"{BUNDLE_ID}.plist"

PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyLists-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{bundle_id}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{target_exe}</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{home}/.claude-mnemos/supervisor.log</string>
    <key>StandardErrorPath</key>
    <string>{home}/.claude-mnemos/supervisor.log</string>
</dict>
</plist>
"""


def _agents_folder() -> Path:
    home = os.environ.get("HOME")
    if not home:
        raise RuntimeError("HOME env var not set; not a POSIX session?")
    return Path(home) / "Library" / "LaunchAgents"


class MacOSAutostart(AutostartManager):
    def __init__(self, target_exe: str) -> None:
        self.target_exe = target_exe
        self.plist_path = _agents_folder() / PLIST_FILENAME

    def _render_plist(self) -> str:
        return PLIST_TEMPLATE.format(
            bundle_id=BUNDLE_ID,
            target_exe=self.target_exe,
            home=os.environ["HOME"],
        )

    def install(self) -> None:
        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        self.plist_path.write_text(self._render_plist(), encoding="utf-8")
        result = subprocess.run(
            ["launchctl", "load", "-w", str(self.plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"launchctl load exit {result.returncode}: {result.stderr.strip()}"
            )

    def uninstall(self) -> None:
        if not self.plist_path.is_file():
            return
        subprocess.run(
            ["launchctl", "unload", "-w", str(self.plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        # Whether unload succeeded or not, drop the file — install will reload it cleanly.
        self.plist_path.unlink(missing_ok=True)

    def status(self) -> AutostartStatus:
        return AutostartStatus(
            installed=self.plist_path.is_file(),
            path=str(self.plist_path),
        )
