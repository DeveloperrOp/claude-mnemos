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
{program_arguments}
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


def _home_dir() -> str:
    home = os.environ.get("HOME")
    if not home:
        raise RuntimeError("HOME env var not set; not a POSIX session?")
    return home


def _agents_folder() -> Path:
    return Path(_home_dir()) / "Library" / "LaunchAgents"


class MacOSAutostart(AutostartManager):
    def __init__(
        self,
        target_exe: str,
        target_args: list[str] | None = None,
    ) -> None:
        self.target_exe = target_exe
        # Default ["run"] preserves the convention that target_exe is the
        # mnemos-tray binary; for the Python -m fallback the caller passes
        # ["-m", "claude_mnemos.tray", "run"] with target_exe=sys.executable.
        self.target_args = target_args if target_args is not None else ["run"]
        self.plist_path = _agents_folder() / PLIST_FILENAME

    def _render_plist(self) -> str:
        # XML-escape angle brackets/ampersands in argv tokens (paths shouldn't
        # have them but defence in depth).
        def _escape(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        argv = [self.target_exe, *self.target_args]
        program_arguments = "\n".join(
            f"        <string>{_escape(a)}</string>" for a in argv
        )
        return PLIST_TEMPLATE.format(
            bundle_id=BUNDLE_ID,
            program_arguments=program_arguments,
            home=_home_dir(),
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
