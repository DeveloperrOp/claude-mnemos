"""Single-message IPC: second mnemos-launcher invocation tells the first
to focus its window.

Windows: named pipe (`\\\\.\\pipe\\claude-mnemos-tray`).
Mac/Linux: Unix domain socket (`~/.claude-mnemos/tray.sock`).
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from typing import Callable


class IpcServer:
    def __init__(self, address: str, on_message: Callable[[str], None]) -> None:
        self.address = address
        self.on_message = on_message
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._win_handle = None

    def start(self) -> None:
        if sys.platform == "win32":
            self._start_win()
        else:
            self._start_posix()

    def _start_posix(self) -> None:
        from os import unlink
        try:
            unlink(self.address)
        except FileNotFoundError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.address)
        s.listen(4)
        s.settimeout(0.2)
        self._sock = s

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    conn, _ = s.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with conn:
                    data = conn.recv(1024)
                    if data:
                        self.on_message(data.decode("utf-8", errors="replace").strip())

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def _start_win(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PIPE_ACCESS_DUPLEX = 0x00000003
        PIPE_TYPE_MESSAGE = 0x00000004
        PIPE_READMODE_MESSAGE = 0x00000002
        PIPE_WAIT = 0x00000000
        FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

        kernel32.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        ]
        kernel32.CreateNamedPipeW.restype = wintypes.HANDLE

        # FIRST_PIPE_INSTANCE flag → second create on same name fails with
        # ERROR_ACCESS_DENIED. This gives us atomic single-server semantics.
        h = kernel32.CreateNamedPipeW(
            self.address,
            PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            1,  # max one instance
            512, 512, 0, None,
        )
        if h == INVALID_HANDLE_VALUE or h == 0:
            err = ctypes.get_last_error()
            raise OSError(f"CreateNamedPipeW failed (err={err}) on {self.address}")

        self._win_handle = h

        def loop() -> None:
            buf = ctypes.create_string_buffer(1024)
            read = wintypes.DWORD(0)
            while not self._stop.is_set():
                ok = kernel32.ConnectNamedPipe(h, None)
                if not ok:
                    err = ctypes.get_last_error()
                    if err == 535:  # ERROR_PIPE_CONNECTED — already connected, OK
                        ok = True
                if ok:
                    if kernel32.ReadFile(h, buf, 1024, ctypes.byref(read), None):
                        msg = buf.raw[:read.value].decode("utf-8", errors="replace").strip()
                        self.on_message(msg)
                kernel32.DisconnectNamedPipe(h)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if sys.platform == "win32":
            # Wake the worker out of its blocking ConnectNamedPipe by
            # connecting to ourselves; then close the handle. CloseHandle
            # alone does not cancel the synchronous wait.
            if self._win_handle is not None:
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CreateFileW.argtypes = [
                    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
                ]
                kernel32.CreateFileW.restype = wintypes.HANDLE
                GENERIC_WRITE = 0x40000000
                OPEN_EXISTING = 3
                INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
                wake = kernel32.CreateFileW(
                    self.address, GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None,
                )
                if wake != INVALID_HANDLE_VALUE and wake != 0:
                    kernel32.CloseHandle(wake)
                try:
                    kernel32.CloseHandle(self._win_handle)
                except Exception:
                    pass
                self._win_handle = None
        else:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        if self._thread:
            self._thread.join(timeout=1.0)


def ipc_send(address: str, message: str, *, timeout: float = 2.0) -> bool:
    """Send `message` to the IPC server at `address`. Returns True on success."""
    deadline = time.monotonic() + timeout
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

        while time.monotonic() < deadline:
            h = kernel32.CreateFileW(
                address,
                GENERIC_READ | GENERIC_WRITE,
                0, None, OPEN_EXISTING, 0, None,
            )
            if h != INVALID_HANDLE_VALUE and h != 0:
                try:
                    written = wintypes.DWORD(0)
                    data = message.encode("utf-8")
                    ok = kernel32.WriteFile(h, data, len(data), ctypes.byref(written), None)
                    return bool(ok)
                finally:
                    kernel32.CloseHandle(h)
            time.sleep(0.1)
        return False

    while time.monotonic() < deadline:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.settimeout(0.5)
            s.connect(address)
            s.sendall(message.encode("utf-8"))
            return True
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError):
            pass
        finally:
            s.close()
        time.sleep(0.1)
    return False
