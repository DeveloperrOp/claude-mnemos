"""AutostartManager Protocol — common contract for OS-specific autostart impls.

Implementations live in sibling modules ``windows.py`` and ``macos.py``.
Selection happens in ``platform/__init__.py::get_autostart_manager``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AutostartStatus:
    installed: bool
    path: str | None = None


@runtime_checkable
class AutostartManager(Protocol):
    """Install / uninstall / inspect a per-user autostart entry for the tray.

    Implementations MUST be idempotent: ``install`` overwrites existing
    entry, ``uninstall`` is no-op when entry is absent.
    """

    def install(self) -> None: ...
    def uninstall(self) -> None: ...
    def status(self) -> AutostartStatus: ...
