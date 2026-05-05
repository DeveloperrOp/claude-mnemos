"""Platform-specific autostart implementations behind a common Protocol.

Selection happens via ``get_autostart_manager(target_exe)`` based on
``sys.platform``. Linux returns ``UnsupportedAutostart`` for graceful
degradation in the UI (the Onboarding wizard hides the checkbox).
"""

from __future__ import annotations

import sys

from claude_mnemos.tray.platform.base import AutostartManager, AutostartStatus

PLATFORM_NAME: dict[str, str] = {
    "win32": "windows",
    "darwin": "macos",
    "linux": "linux",
    "linux2": "linux",
}


def platform_label() -> str:
    return PLATFORM_NAME.get(sys.platform, "unsupported")


class UnsupportedAutostart:
    """Stub returned on platforms where autostart is not implemented (Linux MVP)."""

    def install(self) -> None:
        raise NotImplementedError(f"autostart not supported on {sys.platform}")

    def uninstall(self) -> None:
        raise NotImplementedError(f"autostart not supported on {sys.platform}")

    def status(self) -> AutostartStatus:
        return AutostartStatus(installed=False, path=None)

    def is_installed(self) -> bool:
        return False


def get_autostart_manager(
    target_exe: str,
    target_args: list[str] | None = None,
) -> AutostartManager:
    if sys.platform == "win32":
        from claude_mnemos.tray.platform.windows import WindowsAutostart
        return WindowsAutostart(target_exe=target_exe, target_args=target_args)
    if sys.platform == "darwin":
        from claude_mnemos.tray.platform.macos import MacOSAutostart
        return MacOSAutostart(target_exe=target_exe, target_args=target_args)
    return UnsupportedAutostart()


__all__ = [
    "AutostartManager",
    "AutostartStatus",
    "PLATFORM_NAME",
    "UnsupportedAutostart",
    "get_autostart_manager",
    "platform_label",
]
