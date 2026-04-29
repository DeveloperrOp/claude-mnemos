"""Windows autostart via Startup-folder .lnk created by PowerShell WScript.Shell.

The shortcut points at ``mnemos-tray run`` (foreground mode). Uses PowerShell
because creating .lnk from pure stdlib Python requires COM bindings (pywin32),
which we don't want as a dep.

Idempotency:
- ``install`` always (re)writes the .lnk via PowerShell; safe to call twice.
- ``uninstall`` ``unlink(missing_ok=True)``.
- ``status`` only checks file existence — does not validate Target inside.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from claude_mnemos.tray.platform.base import AutostartManager, AutostartStatus

SHORTCUT_NAME = "Mnemos.lnk"


def _startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA env var not set; not a Windows session?")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


class WindowsAutostart(AutostartManager):
    def __init__(self, target_exe: str) -> None:
        self.target_exe = target_exe
        self.shortcut_path = _startup_folder() / SHORTCUT_NAME

    def install(self) -> None:
        # PowerShell one-liner builds and saves the .lnk via WScript.Shell COM.
        # Single-quote PS strings to avoid escape headaches; .replace("'", "''")
        # is the PS-safe escape for embedded apostrophes.
        target = self.target_exe.replace("'", "''")
        sc_path = str(self.shortcut_path).replace("'", "''")
        ps = (
            f"$WshShell = New-Object -ComObject WScript.Shell; "
            f"$Shortcut = $WshShell.CreateShortcut('{sc_path}'); "
            f"$Shortcut.TargetPath = '{target}'; "
            f"$Shortcut.Arguments = 'run'; "
            f"$Shortcut.WorkingDirectory = ([System.IO.Path]::GetDirectoryName('{target}')); "
            f"$Shortcut.WindowStyle = 7; "  # 7 = minimized; tray app has no main window
            f"$Shortcut.Save()"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"powershell exit {result.returncode}: {result.stderr.strip()}"
            )

    def uninstall(self) -> None:
        self.shortcut_path.unlink(missing_ok=True)

    def status(self) -> AutostartStatus:
        return AutostartStatus(
            installed=self.shortcut_path.is_file(),
            path=str(self.shortcut_path),
        )
