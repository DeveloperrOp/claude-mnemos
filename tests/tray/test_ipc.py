import sys
import threading
import time
from pathlib import Path

import pytest

from claude_mnemos.tray.ipc import IpcServer, ipc_send


@pytest.fixture
def ipc_addr(tmp_path: Path):
    if sys.platform == "win32":
        return r"\\.\pipe\claude-mnemos-test-" + str(id(tmp_path))
    return str(tmp_path / "test.sock")


def test_server_receives_show_message(ipc_addr):
    received: list[str] = []
    server = IpcServer(ipc_addr, on_message=received.append)
    server.start()
    try:
        time.sleep(0.2)
        ok = ipc_send(ipc_addr, "show")
        time.sleep(0.3)
    finally:
        server.stop()
    assert ok is True
    assert "show" in received


def test_send_to_nothing_returns_false(ipc_addr):
    ok = ipc_send(ipc_addr, "show", timeout=0.5)
    assert ok is False


def test_double_server_start_raises(ipc_addr):
    a = IpcServer(ipc_addr, on_message=lambda _m: None)
    b = IpcServer(ipc_addr, on_message=lambda _m: None)
    a.start()
    try:
        with pytest.raises((OSError, RuntimeError)):
            b.start()
    finally:
        a.stop()
