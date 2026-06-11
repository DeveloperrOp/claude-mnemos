"""Race-free single-instance lock primitives.

Replaces the PID-file lock in tray/__main__.py which had a race window
(two processes could both see «no live tray» and both write their PID).
This module guarantees atomic acquisition.

Windows: named mutex (`CreateMutexW` + `ERROR_ALREADY_EXISTS`).
Mac/Linux: `fcntl.flock(LOCK_EX | LOCK_NB)` on a regular file.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path


class _Base:
    name: str

    def acquire(self) -> bool:
        raise NotImplementedError

    def release(self) -> None:
        raise NotImplementedError


class WindowsSingleInstance(_Base):
    def __init__(self, name: str, lock_dir: Path | None = None) -> None:
        self.name = name
        self._handle: int | None = None

    def acquire(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        full_name = f"Local\\{self.name}"
        self._handle = kernel32.CreateMutexW(None, True, full_name)
        ERROR_ALREADY_EXISTS = 183
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(self._handle)
            self._handle = None
            return False
        return self._handle != 0

    def release(self) -> None:
        if self._handle:
            import ctypes
            ctypes.WinDLL("kernel32").CloseHandle(self._handle)
            self._handle = None


class PosixSingleInstance(_Base):
    def __init__(self, name: str, lock_dir: Path | None = None) -> None:
        self.name = name
        self._lock_dir = lock_dir or (Path.home() / ".claude-mnemos")
        self._fd: int | None = None
        safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        self._lock_path = self._lock_dir / f"{safe}.lock"

    def acquire(self) -> bool:
        import fcntl
        import os
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            # POSIX-only path (factory guards on sys.platform); fcntl attrs
            # are invisible to mypy when analyzing on win32.
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined, unused-ignore]
            return True
        except (BlockingIOError, OSError):
            os.close(self._fd)
            self._fd = None
            return False

    def release(self) -> None:
        if self._fd is not None:
            import fcntl
            import os
            with contextlib.suppress(OSError):
                # POSIX-only path — see acquire() note about win32 analysis.
                fcntl.flock(self._fd, fcntl.LOCK_UN)  # type: ignore[attr-defined, unused-ignore]
            os.close(self._fd)
            self._fd = None


def get_single_instance(name: str, *, lock_dir: Path | None = None) -> _Base:
    """Factory: pick correct backend by sys.platform."""
    if sys.platform == "win32":
        return WindowsSingleInstance(name, lock_dir=lock_dir)
    return PosixSingleInstance(name, lock_dir=lock_dir)
