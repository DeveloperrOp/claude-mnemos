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
    def __init__(
        self,
        target_exe: str,
        target_args: list[str] | None = None,
    ) -> None:
        self.target_exe = target_exe
        # `target_args` are the .lnk's Arguments field. Default ["run"] preserves
        # the convention that Target is the mnemos-tray binary; for the fallback
        # "python -m claude_mnemos.tray" path the caller passes ["-m",
        # "claude_mnemos.tray", "run"] with target_exe=sys.executable.
        self.target_args = target_args if target_args is not None else ["run"]
        self.shortcut_path = _startup_folder() / SHORTCUT_NAME

    def install(self) -> None:
        # PowerShell one-liner builds and saves the .lnk via WScript.Shell COM.
        # Single-quote PS strings to avoid escape headaches; .replace("'", "''")
        # is the PS-safe escape for embedded apostrophes.
        target = self.target_exe.replace("'", "''")
        sc_path = str(self.shortcut_path).replace("'", "''")
        # Build "Arguments" string; quote individual args containing spaces.
        joined = " ".join(
            f'"{a}"' if " " in a else a for a in self.target_args
        ).replace("'", "''")
        ps = (
            f"$WshShell = New-Object -ComObject WScript.Shell; "
            f"$Shortcut = $WshShell.CreateShortcut('{sc_path}'); "
            f"$Shortcut.TargetPath = '{target}'; "
            f"$Shortcut.Arguments = '{joined}'; "
            f"$Shortcut.WorkingDirectory = ([System.IO.Path]::GetDirectoryName('{target}')); "
            f"$Shortcut.WindowStyle = 7; "  # 7 = minimized; tray app has no main window
            f"$Shortcut.Save()"
        )
        # CREATE_NO_WINDOW: powershell.exe is a console subsystem program;
        # without this flag, calling it from a windowed parent (the bundled
        # claude-mnemos.exe is console=False) flashes a black console window
        # for ~50ms while powershell starts. The WScript.Shell COM call
        # finishes in milliseconds, so the flash is brief but visible —
        # users see it during postinstall autostart registration.
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
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

    def is_installed(self) -> bool:
        return self.shortcut_path.is_file()
