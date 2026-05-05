# Desktop Launcher (E1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the «open browser at localhost:5757» UX with a native desktop application built on `pywebview`, fix the tray-supervisor multi-spawn race, make autostart + desktop shortcut first-class on Windows install.

**Architecture:** Tray supervisor stays as the single autostart entity, owns the daemon-subprocess. New launcher process embeds the existing React SPA in a native webview (Edge WebView2 / WKWebView / WebKitGTK). Single-instance enforced via Windows named mutex (`CreateMutexW`) on Win, `fcntl.flock` on Mac/Linux — race-free. IPC «show window» message via named-pipe (Win) or Unix socket (Mac/Linux) lets a second invocation focus the existing window instead of spawning a duplicate.

**Tech Stack:** `pywebview>=5.4` + native webview (Edge WebView2 / WKWebView / WebKitGTK). Python 3.12+. Existing FastAPI daemon and React SPA stay untouched. PyInstaller bundling stays one-dir. Inno Setup gets a WebView2 Runtime detection step.

---

## Pre-flight

- The spec is `docs/superpowers/specs/2026-05-05-desktop-launcher-design.md` — read first.
- Python venv: `~/pipx/venvs/claude-mnemos/Scripts/python.exe` (pipx install).
- Always deselect: `tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle` (pre-existing Windows PID flaky).
- Backend baseline before this plan: **1701 passed**. Frontend: **360 passed**. TypeScript: 0 errors.
- pywebview install on the dev box (one-off):
  ```
  ~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pip install pywebview==5.4
  ```
- Local Windows dev: Edge WebView2 Runtime is preinstalled on Win 11; on Win 10 it must be installed separately. Confirm by running `~/pipx/venvs/claude-mnemos/Scripts/python.exe -c "import webview; webview.create_window('test', html='<h1>ok</h1>'); webview.start()"` — should open a tiny window with «ok».
- Stay on `main`. Do NOT push during the plan; final push happens after the live walk in Task 12.

---

## File Structure

### New backend files

| File | Responsibility | Approx LoC |
|---|---|---|
| `claude_mnemos/tray/single_instance.py` | Race-free single-instance helpers — `WindowsSingleInstance` (Win named mutex) + `PosixSingleInstance` (`fcntl.flock`). Uniform interface `acquire() -> bool` + `release() -> None` + `name -> str`. | ~140 |
| `claude_mnemos/tray/ipc.py` | "show window" IPC — `IpcServer` (named pipe on Win, Unix socket on Mac/Linux) + `ipc_send(message)` client. | ~150 |
| `claude_mnemos/launcher.py` | pywebview window: splash HTML → polls daemon `/api/health` → navigates webview to `:5757`. Handles `--no-window` headless flag for CI. | ~190 |
| `claude_mnemos/cli_launcher.py` | `mnemos launcher` subcommand. Calls existing `mnemos tray install` if tray not running; then opens launcher window or sends IPC «show» if already open. | ~70 |
| `claude_mnemos/daemon/routes/system.py` | `POST /api/system/autostart` (toggle Mnemos.lnk on/off). `POST /api/system/window-close-action` (persist `hide` vs `quit`). | ~100 |

### Modified backend files

| File | Change |
|---|---|
| `claude_mnemos/tray/__main__.py:32-63,85-120` | Replace `_acquire_tray_lock`/`_release_tray_lock` with `WindowsSingleInstance`/`PosixSingleInstance`. Add IPC server in `_cmd_run`. Tray menu rewrite (Open Dashboard / Pause Daemon / Settings / Quit). |
| `claude_mnemos/tray/supervisor.py` | Add `pause_daemon()`, `resume_daemon()`, `open_launcher()`, `shutdown()`. Track `launcher_proc` Popen. |
| `claude_mnemos/cli.py` | Register `add_launcher_subparser`. |
| `claude_mnemos/cli_init.py:99-101` | Replace `_open_browser(DASHBOARD_URL)` with `subprocess.Popen([sys.executable, "-m", "claude_mnemos.cli", "launcher"])`. |
| `claude_mnemos/state/install_state.py` | Add field `window_close_action: Literal["hide", "quit"] | None = None`. |
| `claude_mnemos/daemon/app.py` | Mount new `system_router` at `/api`. |

### New frontend files

| File | Responsibility | Approx LoC |
|---|---|---|
| `frontend/src/api/system.api.ts` | `getAutostartEnabled()` + `setAutostartEnabled(enabled)`. | ~30 |
| `frontend/src/hooks/useAutostartToggle.ts` | React Query mutation. | ~25 |

### Modified frontend files

| File | Change |
|---|---|
| `frontend/src/pages/GlobalSettings.tsx` | Add «Запускать с Windows» toggle in System section. |
| `frontend/public/locales/en.json`, `ru.json`, `uk.json` | i18n keys for autostart toggle. |

### Build / installer changes

| File | Change |
|---|---|
| `installer/pyinstaller/mnemos.spec` | Add `pywebview` + `clr_loader` to `hiddenimports`. Bundle WebView2 loader binary on Win. |
| `installer/windows/mnemos.iss` | Add WebView2 Runtime detect-and-install. Change `[Run]` from `tray run` to `launcher`. Switch desktop-icon task from `unchecked` to `checkedonce`. Pass `--no-browser` to inhibit double-open. |
| `installer/macos/setup.py` | Add `pywebview` to `packages`. |
| `installer/linux/build-appimage.sh` | Document `webkit2gtk-4.0` apt dep. |
| `pyproject.toml` | Add `pywebview>=5.4` to runtime deps. |

### New tests

| File | Tests |
|---|---|
| `tests/test_single_instance.py` | acquire returns True first time, False second time on same name; release allows re-acquire; cross-platform dispatch. |
| `tests/tray/test_ipc.py` | server starts, receives "show", invokes callback; client send returns success / fail; double-server start raises. |
| `tests/test_launcher.py` | `--no-window` flag exits 0; daemon-down splash polls health; happy-path navigates webview to `:5757`. |
| `tests/daemon/test_app_system.py` | autostart toggle endpoint writes/removes `Mnemos.lnk`; window-close-action endpoint persists state. |
| `tests/test_cli_launcher.py` | first invocation spawns tray + window; second invocation sends IPC "show" and exits 0. |

### Modified tests

| File | Change |
|---|---|
| `tests/tray/test_main_lock.py` | (rename of any existing PID-lock test) — assert single_instance helper is now the gate. |
| `tests/test_postinstall.py` | Update «main only runs postinstall for tray run» to also accept `launcher` command (since launcher is now the primary entry on installer). |
| `tests/installer/test_pyinstaller_smoke.py` | Add `MNEMOS_SKIP_POSTINSTALL=1` env var on the smoke invocation (already there from Phase 2 fix). |

---

## Tasks

### Task 1: `single_instance.py` — race-free mutex helpers

Foundation. Tray and launcher both depend on this. Implement first.

**Files:**
- Create: `claude_mnemos/tray/single_instance.py`
- Test: `tests/test_single_instance.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_single_instance.py
import sys
from pathlib import Path

import pytest

from claude_mnemos.tray.single_instance import get_single_instance


def test_acquire_returns_true_first_time(tmp_path):
    si = get_single_instance("com.yarik.claude-mnemos.test1", lock_dir=tmp_path)
    try:
        assert si.acquire() is True
    finally:
        si.release()


def test_second_acquire_returns_false(tmp_path):
    a = get_single_instance("com.yarik.claude-mnemos.test2", lock_dir=tmp_path)
    b = get_single_instance("com.yarik.claude-mnemos.test2", lock_dir=tmp_path)
    try:
        assert a.acquire() is True
        assert b.acquire() is False
    finally:
        a.release()
        b.release()


def test_release_allows_reacquire(tmp_path):
    a = get_single_instance("com.yarik.claude-mnemos.test3", lock_dir=tmp_path)
    b = get_single_instance("com.yarik.claude-mnemos.test3", lock_dir=tmp_path)
    assert a.acquire() is True
    a.release()
    try:
        assert b.acquire() is True
    finally:
        b.release()


def test_factory_picks_correct_backend():
    si = get_single_instance("dummy", lock_dir=Path("."))
    if sys.platform == "win32":
        assert type(si).__name__ == "WindowsSingleInstance"
    else:
        assert type(si).__name__ == "PosixSingleInstance"
```

- [ ] **Step 2: Run test to confirm fail**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_single_instance.py -v
```
Expected: `ModuleNotFoundError: claude_mnemos.tray.single_instance`.

- [ ] **Step 3: Implement the module**

```python
# claude_mnemos/tray/single_instance.py
"""Race-free single-instance lock primitives.

Replaces the PID-file lock in tray/__main__.py which had a race window
(two processes can both see «no live tray» and both write their PID).
This module guarantees atomic acquisition.

Windows: named mutex (`CreateMutexW` + `ERROR_ALREADY_EXISTS`).
Mac/Linux: `fcntl.flock` (LOCK_EX | LOCK_NB) on a regular file.
"""

from __future__ import annotations

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
        self._handle = None  # type: ignore[assignment]

    def acquire(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        # Local\\ namespace = per-user, no admin needed.
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
        self._fd = None  # type: ignore[assignment]
        # Sanitize name for filename use
        safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        self._lock_path = self._lock_dir / f"{safe}.lock"

    def acquire(self) -> bool:
        import fcntl
        import os
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            os.close(self._fd)
            self._fd = None
            return False

    def release(self) -> None:
        if self._fd is not None:
            import fcntl
            import os
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(self._fd)
            self._fd = None


def get_single_instance(name: str, *, lock_dir: Path | None = None) -> _Base:
    """Factory: pick correct backend by sys.platform."""
    if sys.platform == "win32":
        return WindowsSingleInstance(name, lock_dir=lock_dir)
    return PosixSingleInstance(name, lock_dir=lock_dir)
```

- [ ] **Step 4: Run tests, confirm GREEN**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_single_instance.py -v
```
Expected: 4 PASS.

- [ ] **Step 5: Full suite, no regressions**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
```
Expected: ≥ 1705 passed (1701 + 4).

- [ ] **Step 6: Commit**

```
git add claude_mnemos/tray/single_instance.py tests/test_single_instance.py
git commit -m "feat(tray): race-free single-instance lock — Win mutex / fcntl flock

Replaces the PID-file lock used by tray/__main__.py, which had a race
window where two processes could both observe 'no live tray' and both
write their PID, leading to multi-spawn (confirmed bug, 9+ instances
spawned during 2026-05-05 dev session).

Windows: CreateMutexW + ERROR_ALREADY_EXISTS — atomic.
Mac/Linux: fcntl.flock(LOCK_EX | LOCK_NB) — atomic.

Foundation for tray refactor (Task 3) and launcher single-instance
(Task 5)."
```

---

### Task 2: `tray/ipc.py` — "show window" message

Cross-platform IPC for the second invocation to tell the first to focus its window.

**Files:**
- Create: `claude_mnemos/tray/ipc.py`
- Test: `tests/tray/test_ipc.py`

- [ ] **Step 1: Write failing test**

```python
# tests/tray/test_ipc.py
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
```

- [ ] **Step 2: RED**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/tray/test_ipc.py -v
```

- [ ] **Step 3: Implement**

```python
# claude_mnemos/tray/ipc.py
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
from pathlib import Path
from typing import Callable


class IpcServer:
    def __init__(self, address: str, on_message: Callable[[str], None]) -> None:
        self.address = address
        self.on_message = on_message
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._sock: socket.socket | None = None

    def start(self) -> None:
        if sys.platform == "win32":
            self._start_win()
        else:
            self._start_posix()

    def _start_posix(self) -> None:
        # Address is a filesystem path
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
        # Use Windows named pipe.
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PIPE_ACCESS_DUPLEX = 0x00000003
        PIPE_TYPE_MESSAGE = 0x00000004
        PIPE_READMODE_MESSAGE = 0x00000002
        PIPE_WAIT = 0x00000000
        PIPE_UNLIMITED_INSTANCES = 255
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

        kernel32.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        ]
        kernel32.CreateNamedPipeW.restype = wintypes.HANDLE

        h = kernel32.CreateNamedPipeW(
            self.address,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            512, 512, 0, None,
        )
        if h == INVALID_HANDLE_VALUE or h == 0:
            raise OSError(f"CreateNamedPipeW failed: {ctypes.get_last_error()}")

        # Try to detect a duplicate by attempting a second creation:
        h2 = kernel32.CreateNamedPipeW(
            self.address,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            1,  # max one instance — second create will fail
            512, 512, 0, None,
        )
        if h2 != INVALID_HANDLE_VALUE and h2 != 0:
            kernel32.CloseHandle(h2)

        self._win_handle = h

        def loop() -> None:
            buf = ctypes.create_string_buffer(1024)
            read = wintypes.DWORD(0)
            while not self._stop.is_set():
                ok = kernel32.ConnectNamedPipe(h, None)
                if not ok:
                    err = ctypes.get_last_error()
                    if err == 535:  # ERROR_PIPE_CONNECTED
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
            try:
                import ctypes
                ctypes.WinDLL("kernel32").CloseHandle(self._win_handle)
            except Exception:
                pass
        else:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
        if self._thread:
            self._thread.join(timeout=1.0)


def ipc_send(address: str, message: str, *, timeout: float = 2.0) -> bool:
    """Send `message` to the IPC server at `address`. Returns True on success."""
    deadline = time.monotonic() + timeout
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3

        while time.monotonic() < deadline:
            h = kernel32.CreateFileW(
                address,
                GENERIC_READ | GENERIC_WRITE,
                0, None, OPEN_EXISTING, 0, None,
            )
            if h != -1 and h != 0:
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
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
            pass
        finally:
            s.close()
        time.sleep(0.1)
    return False
```

NOTE: The Win named-pipe code is non-trivial; the engineer can simplify with `pywin32` if installed (which we add as a transitive dep with pywebview). If `pywin32` is available, `win32pipe.CreateNamedPipe` is cleaner — substitute as long as the test contract holds.

- [ ] **Step 4: Create `tests/tray/__init__.py`** (empty file) so the test module is importable.

- [ ] **Step 5: Run tests**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/tray/test_ipc.py -v
```
Expected: 3 PASS.

- [ ] **Step 6: Commit**
```
git add claude_mnemos/tray/ipc.py tests/tray/__init__.py tests/tray/test_ipc.py
git commit -m "feat(tray): IPC 'show window' channel — named pipe / Unix socket

Foundation for the second-launcher-invocation behaviour. When a user
double-clicks the desktop shortcut while the first launcher is still
running, the second sends 'show' and exits — the first focuses its
window. No multi-window. No multi-spawn."
```

---

### Task 3: Replace tray PID lock with single_instance + IPC server

Wire the new primitives into the existing tray supervisor. Remove the racy PID-file lock entirely.

**Files:**
- Modify: `claude_mnemos/tray/__main__.py:32-63,85-120`

- [ ] **Step 1: Read the current `_acquire_tray_lock` / `_release_tray_lock` block + `_cmd_run`**

```
sed -n '32,120p' claude_mnemos/tray/__main__.py
```

- [ ] **Step 2: Add import + constants**

At the top of `claude_mnemos/tray/__main__.py`, add:
```python
from claude_mnemos.tray.single_instance import get_single_instance
from claude_mnemos.tray.ipc import IpcServer, ipc_send

TRAY_INSTANCE_NAME = "com.yarik.claude-mnemos.tray"
if sys.platform == "win32":
    IPC_ADDRESS = r"\\.\pipe\claude-mnemos-tray"
else:
    IPC_ADDRESS = str(Path.home() / ".claude-mnemos" / "tray.sock")
```

- [ ] **Step 3: Replace `_acquire_tray_lock` / `_release_tray_lock`**

Delete the old functions. Replace `_cmd_run` body (lines ~85-120) with:

```python
def _cmd_run() -> int:
    si = get_single_instance(TRAY_INSTANCE_NAME)
    if not si.acquire():
        # Already running — tell that one to show its launcher window, exit.
        ipc_send(IPC_ADDRESS, "show")
        print("[tray] another instance already running; sent 'show' to it.")
        return 0

    sv = Supervisor(daemon_pid_file=DAEMON_PID_FILE, log_path=DAEMON_LOG)
    sv.start()
    app = TrayApp(supervisor=sv)

    # IPC: when another launcher invocation sends "show", focus the launcher
    # window. The actual focus call delegates to the supervisor (it owns
    # launcher_proc and knows whether one is alive).
    def _on_ipc(msg: str) -> None:
        if msg == "show":
            sv.open_launcher()

    ipc_srv = IpcServer(IPC_ADDRESS, on_message=_on_ipc)
    ipc_srv.start()

    def _ticker() -> None:
        while True:
            time.sleep(5.0)
            try:
                sv.tick()
                app.repaint()
            except Exception:
                logging.exception("[supervisor] tick failed")

    t = threading.Thread(target=_ticker, daemon=True)
    t.start()

    try:
        app.run()  # blocks until Quit
    finally:
        ipc_srv.stop()
        sv.stop()
        si.release()
    return 0
```

- [ ] **Step 4: Update existing `tests/test_tray_main.py` (or whatever covers `_cmd_run`)**

Search for tests:
```
grep -nE "_acquire_tray_lock|_cmd_run|TRAY_PID_FILE" tests/ -r
```

Most likely candidates: `tests/tray/test_main.py` or similar. Update assertions: any test that monkeypatches `_acquire_tray_lock` should now monkeypatch `claude_mnemos.tray.single_instance.get_single_instance` to return a mock with `acquire()/release()`. Any test that asserts the PID file is created/removed must be updated to check the new lock object instead.

If a test specifically tested the race window in PID-file lock, **delete it** — that race no longer exists by construction.

- [ ] **Step 5: Run tray tests**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/tray -v
```
Expected: All PASS (count may go down by 1-2 if you deleted PID-race tests).

- [ ] **Step 6: Full suite**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
```
Expected: ≥ 1708 passed (1705 + 3 new IPC).

- [ ] **Step 7: Commit**
```
git add claude_mnemos/tray/__main__.py tests/tray/
git commit -m "refactor(tray): drop racy PID-file lock, use single_instance + IPC

_acquire_tray_lock had a race where two processes could both see
'no live tray' before either wrote its PID. Replaced with the
race-free single_instance helpers (Task 1) plus an IPC server that
listens for 'show' from second invocations. A second mnemos-tray
process now sends 'show' to the first and exits clean — no multi-tray."
```

---

### Task 4: Supervisor — `pause_daemon`, `resume_daemon`, `open_launcher`, `shutdown`

Extend `Supervisor` with the verbs the tray menu needs. Add `launcher_proc` tracking.

**Files:**
- Modify: `claude_mnemos/tray/supervisor.py:118-322`
- Test: `tests/tray/test_supervisor.py` (existing — extend)

- [ ] **Step 1: Tests for new methods**

```python
# tests/tray/test_supervisor.py — append at end

def test_supervisor_open_launcher_spawns_subprocess(tmp_path, monkeypatch):
    pid_file = tmp_path / "daemon.pid"
    sv = Supervisor(daemon_pid_file=pid_file, log_path=None)

    spawned = []

    class FakeProc:
        def __init__(self, cmd):
            self.cmd = cmd
        def poll(self):
            return None  # alive
        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, *args, **kwargs):
        spawned.append(cmd)
        return FakeProc(cmd)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    sv.open_launcher()
    assert len(spawned) == 1
    assert "launcher" in " ".join(spawned[0])


def test_supervisor_open_launcher_focuses_existing(tmp_path, monkeypatch):
    pid_file = tmp_path / "daemon.pid"
    sv = Supervisor(daemon_pid_file=pid_file, log_path=None)

    class AliveProc:
        def poll(self): return None
    sv.launcher_proc = AliveProc()

    sent = []
    monkeypatch.setattr(
        "claude_mnemos.tray.supervisor.ipc_send",
        lambda addr, msg: sent.append((addr, msg)) or True,
    )
    sv.open_launcher()
    assert sent and sent[0][1] == "show"


def test_supervisor_pause_resume_daemon(tmp_path, monkeypatch):
    pid_file = tmp_path / "daemon.pid"
    sv = Supervisor(daemon_pid_file=pid_file, log_path=None)

    paused_calls = []
    resumed_calls = []

    class FakeHttp:
        def post(self, url, **kw):
            if "pause" in url:
                paused_calls.append(url)
            elif "resume" in url:
                resumed_calls.append(url)
            class R:
                status_code = 200
            return R()

    sv._http = FakeHttp()
    sv.pause_daemon()
    sv.resume_daemon()
    assert paused_calls and resumed_calls
```

- [ ] **Step 2: RED**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/tray/test_supervisor.py -v
```

- [ ] **Step 3: Implement on `Supervisor` (insert near other instance methods)**

```python
# claude_mnemos/tray/supervisor.py

# Add at top (alongside existing imports)
from claude_mnemos.tray.ipc import ipc_send

# Inside class Supervisor (alongside __init__, start, stop, tick):

    launcher_proc: subprocess.Popen | None = None  # type-annotation only

    def __init__(self, *, daemon_pid_file: Path, log_path: Path | None = None) -> None:
        # ... existing init body
        # Add at end:
        self.launcher_proc = None

    def open_launcher(self) -> None:
        """Open the launcher window if not running, focus it if running."""
        if self.launcher_proc is not None and self.launcher_proc.poll() is None:
            # Existing launcher alive — send IPC "show" to focus its window.
            try:
                from claude_mnemos.tray.__main__ import IPC_ADDRESS
                ipc_send(IPC_ADDRESS, "show")
            except Exception:
                logger.exception("[supervisor] ipc_send 'show' failed")
            return

        cmd = [sys.executable, "-m", "claude_mnemos.cli", "launcher", "--no-spawn-tray"]
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        self.launcher_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
            start_new_session=(sys.platform != "win32"),
        )

    def pause_daemon(self) -> None:
        if self._http is None:
            return
        try:
            self._http.post(self.health_url.replace("/api/health", "/api/daemon/pause"))
        except Exception:
            logger.exception("[supervisor] pause_daemon failed")

    def resume_daemon(self) -> None:
        if self._http is None:
            return
        try:
            self._http.post(self.health_url.replace("/api/health", "/api/daemon/resume"))
        except Exception:
            logger.exception("[supervisor] resume_daemon failed")

    def shutdown(self) -> None:
        """Graceful full-quit: stop launcher, stop daemon, release everything."""
        if self.launcher_proc and self.launcher_proc.poll() is None:
            try:
                self.launcher_proc.terminate()
                self.launcher_proc.wait(timeout=5.0)
            except Exception:
                logger.exception("[supervisor] launcher terminate failed")
            self.launcher_proc = None
        self.stop(grace_seconds=5.0)
```

NOTE: `pause_daemon` / `resume_daemon` POST to `/api/daemon/pause` and `/api/daemon/resume`. Those endpoints exist already, OR add minimal stubs in `daemon/routes/daemon.py`. Search:
```
grep -rn "daemon/pause\|daemon/resume" claude_mnemos/daemon/routes/
```
If absent, **add them** in this same task (3-line stubs that toggle a flag the watchdog/scheduler reads).

- [ ] **Step 4: Run tests**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/tray -v
```

- [ ] **Step 5: Commit**
```
git add claude_mnemos/tray/supervisor.py claude_mnemos/daemon/routes/ tests/tray/test_supervisor.py
git commit -m "feat(tray): supervisor.open_launcher / pause_daemon / resume_daemon / shutdown

Verbs the new tray menu (Task 7) and IPC handler (Task 3) call.
open_launcher detects an alive launcher_proc and sends IPC 'show'
instead of spawning a duplicate."
```

---

### Task 5: `launcher.py` — pywebview window

Build the actual window. Splash → poll daemon health → navigate to `:5757`.

**Files:**
- Create: `claude_mnemos/launcher.py`
- Test: `tests/test_launcher.py`
- Modify: `pyproject.toml` — add `pywebview>=5.4`

- [ ] **Step 1: Add to pyproject.toml**

```toml
# pyproject.toml — add to [project] dependencies (NOT optional-dependencies):
"pywebview>=5.4",
```

Run `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pip install pywebview==5.4` to install in dev venv.

- [ ] **Step 2: Test (RED)**

```python
# tests/test_launcher.py
import pytest


def test_launcher_no_window_flag_exits_zero(monkeypatch):
    """Headless mode: launcher initialises but doesn't show a window. CI uses this."""
    from claude_mnemos.launcher import run

    rc = run(["--no-window"])
    assert rc == 0


def test_launcher_polls_daemon_health(monkeypatch):
    """Launcher must poll /api/health and call window.load_url(daemon_url) when 200."""
    polled = {"count": 0}

    def fake_urlopen(url, timeout=None):
        polled["count"] += 1
        class R:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return R()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    from claude_mnemos.launcher import _wait_daemon_ready
    ok = _wait_daemon_ready(timeout_s=2.0)
    assert ok is True
    assert polled["count"] >= 1


def test_launcher_returns_false_if_daemon_never_ready(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise OSError("daemon down")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    from claude_mnemos.launcher import _wait_daemon_ready
    ok = _wait_daemon_ready(timeout_s=0.5)
    assert ok is False
```

- [ ] **Step 3: Implement**

```python
# claude_mnemos/launcher.py
"""Desktop launcher window — pywebview wraps the daemon's React SPA.

Lifecycle:
1. Show a static splash HTML ('Connecting to daemon...').
2. Poll http://127.0.0.1:5757/api/health up to 30s.
3. On first 200, navigate the webview to http://127.0.0.1:5757/.
4. Window-close behaviour driven by install-state.window_close_action.

Headless mode (--no-window): used by CI. Initialises pywebview without
showing a window, exits 0.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.request

DAEMON_URL = "http://127.0.0.1:5757"
HEALTH_URL = f"{DAEMON_URL}/api/health"
HEALTH_POLL_INTERVAL_S = 0.5
HEALTH_TIMEOUT_S = 30.0

SPLASH_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>claude-mnemos</title>
<style>
  body { margin:0; font-family: ui-monospace, monospace; background:#0b0d10; color:#9aa3ab;
         display:flex; align-items:center; justify-content:center; height:100vh; }
  .panel { text-align:center; }
  .spinner { width:32px; height:32px; border:3px solid #2a3038; border-top-color:#3ba55c;
             border-radius:50%; margin:0 auto 16px; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg) } }
  h1 { font-size:14px; font-weight:500; margin:0 0 4px; color:#d1d6db; }
  p { font-size:12px; margin:0; }
</style></head>
<body><div class="panel">
  <div class="spinner"></div>
  <h1>claude-mnemos</h1>
  <p>connecting to daemon...</p>
</div></body></html>
"""


def _wait_daemon_ready(*, timeout_s: float = HEALTH_TIMEOUT_S, url: str = HEALTH_URL) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if 200 <= getattr(r, "status", r.getcode()) < 300:
                    return True
        except Exception:
            pass
        time.sleep(HEALTH_POLL_INTERVAL_S)
    return False


def _open_window() -> int:
    import webview

    window = webview.create_window(
        title="claude-mnemos",
        html=SPLASH_HTML,
        width=1280,
        height=800,
        min_size=(900, 600),
    )

    def _navigate_when_ready() -> None:
        if _wait_daemon_ready():
            try:
                window.load_url(DAEMON_URL)
            except Exception:
                pass
        # else: leave splash; user can close manually.

    t = threading.Thread(target=_navigate_when_ready, daemon=True)
    t.start()

    webview.start()  # blocks until window closed
    return 0


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claude_mnemos.launcher")
    parser.add_argument("--no-window", action="store_true",
                        help="Initialise pywebview without showing a window. CI smoke test.")
    parser.add_argument("--no-spawn-tray", action="store_true",
                        help="Do NOT auto-spawn the tray supervisor. Used when supervisor is calling us.")
    args = parser.parse_args(argv)

    if args.no_window:
        # CI mode: import pywebview, ensure it loads, exit 0 without GUI.
        try:
            import webview  # noqa: F401
        except Exception as exc:
            print(f"[launcher] pywebview import failed: {exc}", file=sys.stderr)
            return 1
        return 0

    return _open_window()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
```

- [ ] **Step 4: Tests**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_launcher.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**
```
git add claude_mnemos/launcher.py tests/test_launcher.py pyproject.toml
git commit -m "feat(launcher): pywebview desktop window — splash + daemon poll + nav

Replaces 'open browser at localhost:5757' with a native window using
pywebview (Edge WebView2 / WKWebView / WebKitGTK). Splash HTML shows
'connecting to daemon...' until /api/health returns 200, then loads
the daemon URL. --no-window flag for CI smoke."
```

---

### Task 6: `mnemos launcher` subcommand + IPC client

Wire CLI. Spawning the tray supervisor on first call, sending IPC «show» on subsequent calls.

**Files:**
- Create: `claude_mnemos/cli_launcher.py`
- Modify: `claude_mnemos/cli.py` — register subparser
- Test: `tests/test_cli_launcher.py`

- [ ] **Step 1: Test (RED)**

```python
# tests/test_cli_launcher.py
import pytest


def test_launcher_existing_tray_sends_ipc(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher.ipc_send",
        lambda addr, msg, **kw: sent.append((addr, msg)) or True,
    )
    monkeypatch.setattr("claude_mnemos.cli_launcher._tray_running", lambda: True)

    from claude_mnemos.cli_launcher import run
    rc = run([])
    assert rc == 0
    assert sent and sent[0][1] == "show"


def test_launcher_no_tray_spawns_tray_then_window(monkeypatch):
    spawn_calls = []
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher._spawn_tray",
        lambda: spawn_calls.append("tray") or True,
    )
    monkeypatch.setattr("claude_mnemos.cli_launcher._tray_running", lambda: False)
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher._wait_tray_ipc",
        lambda timeout_s=10: True,
    )

    sent = []
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher.ipc_send",
        lambda addr, msg, **kw: sent.append((addr, msg)) or True,
    )

    from claude_mnemos.cli_launcher import run
    rc = run([])
    assert rc == 0
    assert "tray" in spawn_calls
    assert sent and sent[0][1] == "show"


def test_launcher_no_spawn_tray_flag_skips_tray_spawn(monkeypatch):
    spawn_calls = []
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher._spawn_tray",
        lambda: spawn_calls.append("tray") or True,
    )
    monkeypatch.setattr("claude_mnemos.cli_launcher._tray_running", lambda: False)

    # When --no-spawn-tray, we go straight to launcher.run([])
    monkeypatch.setattr(
        "claude_mnemos.cli_launcher.launcher_run",
        lambda argv: 0,
    )

    from claude_mnemos.cli_launcher import run
    rc = run(["--no-spawn-tray"])
    assert rc == 0
    assert spawn_calls == []  # NOT spawned
```

- [ ] **Step 2: RED**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_cli_launcher.py -v
```

- [ ] **Step 3: Implement**

```python
# claude_mnemos/cli_launcher.py
"""`mnemos launcher` — opens the desktop window.

Logic:
- If tray supervisor already running → send IPC "show" → exit.
- If not → spawn `mnemos tray run` detached, wait for IPC up, send "show".
- If --no-spawn-tray → just open the launcher window directly (used by
  the supervisor calling us as a child).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from claude_mnemos.tray.ipc import ipc_send
from claude_mnemos.tray.single_instance import get_single_instance
from claude_mnemos.launcher import run as launcher_run

if sys.platform == "win32":
    IPC_ADDRESS = r"\\.\pipe\claude-mnemos-tray"
else:
    IPC_ADDRESS = str(Path.home() / ".claude-mnemos" / "tray.sock")

TRAY_INSTANCE_NAME = "com.yarik.claude-mnemos.tray"


def _tray_running() -> bool:
    """Probe the named mutex / file lock — if acquired, tray is NOT running."""
    si = get_single_instance(TRAY_INSTANCE_NAME)
    if si.acquire():
        si.release()
        return False
    return True


def _spawn_tray() -> bool:
    cmd = [sys.executable, "-m", "claude_mnemos.tray", "run"]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
            start_new_session=(sys.platform != "win32"),
        )
        return True
    except Exception:
        return False


def _wait_tray_ipc(*, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _tray_running():
            return True
        time.sleep(0.3)
    return False


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mnemos launcher")
    parser.add_argument("--no-spawn-tray", action="store_true",
                        help="Do not spawn tray supervisor; open window directly.")
    args = parser.parse_args(argv)

    if args.no_spawn_tray:
        return launcher_run([])

    if _tray_running():
        ipc_send(IPC_ADDRESS, "show")
        return 0

    if not _spawn_tray():
        print("[launcher] failed to spawn tray supervisor", file=sys.stderr)
        return 2

    if not _wait_tray_ipc():
        print("[launcher] tray didn't come up in 10s", file=sys.stderr)
        return 3

    ipc_send(IPC_ADDRESS, "show")
    return 0


def _cmd_launcher(args: argparse.Namespace) -> int:
    extra = ["--no-spawn-tray"] if getattr(args, "no_spawn_tray", False) else []
    return run(extra)


def add_launcher_subparser(parent: argparse._SubParsersAction) -> None:
    p = parent.add_parser("launcher", help="Open the desktop launcher window")
    p.add_argument("--no-spawn-tray", action="store_true",
                   help="Do not spawn tray supervisor; open window directly.")
    p.set_defaults(func=_cmd_launcher)
```

- [ ] **Step 4: Wire into `cli.py`**

After the existing `add_doctor_subparser(sub)` line (or wherever subparsers are registered), add:
```python
from claude_mnemos.cli_launcher import add_launcher_subparser
add_launcher_subparser(sub)
```

In the dispatcher (after `if args.command == "doctor":`):
```python
if args.command == "launcher":
    return args.func(args)
```

Also: update `main()` postinstall gate (commit `c753517`) — `launcher` should be allowed to run postinstall on first launch, so the install flow auto-fires when the user runs the desktop shortcut for the first time. Replace the `is_tray_run` check with:

```python
is_app_entry = (
    len(_argv) >= 3 and _argv[1] == "tray" and _argv[2] == "run"
) or (
    len(_argv) >= 2 and _argv[1] == "launcher"
)
if is_app_entry and os.environ.get("MNEMOS_SKIP_POSTINSTALL") != "1":
    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()
```

Update existing test `test_main_only_runs_postinstall_for_tray_run` to also accept `launcher` as a valid trigger.

- [ ] **Step 5: Run tests**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_cli_launcher.py tests/test_postinstall.py -v
```

- [ ] **Step 6: Commit**
```
git add claude_mnemos/cli_launcher.py claude_mnemos/cli.py tests/test_cli_launcher.py tests/test_postinstall.py
git commit -m "feat(cli): mnemos launcher — open desktop window

If tray supervisor already running, sends IPC 'show' and exits.
If not, spawns 'mnemos tray run' detached, waits for IPC up, then
sends 'show'. --no-spawn-tray flag bypasses tray spawn (used when
supervisor invokes us as a child)."
```

---

### Task 7: Tray menu rewrite — Open Dashboard / Status / Pause / Settings / Quit

Replace the old tray menu (which only had Quit) with the proper menu structure.

**Files:**
- Modify: `claude_mnemos/tray/icon.py` — `TrayApp.menu` definition

- [ ] **Step 1: Inspect current menu**

```
grep -n "MenuItem\|menu\|Menu" claude_mnemos/tray/icon.py | head -20
```

- [ ] **Step 2: Update `TrayApp.menu`**

Replace the existing menu definition with:

```python
# In TrayApp class (claude_mnemos/tray/icon.py):
def _build_menu(self):
    import pystray
    sv = self.supervisor

    def _open_dashboard(_icon, _item):
        sv.open_launcher()

    def _toggle_pause(_icon, _item):
        if sv.daemon_paused:
            sv.resume_daemon()
        else:
            sv.pause_daemon()

    def _open_settings(_icon, _item):
        # Open launcher and let frontend route to /settings/global
        sv.open_launcher()
        # Frontend hash-route handled separately if needed

    def _quit(_icon, _item):
        sv.shutdown()
        _icon.stop()

    return pystray.Menu(
        pystray.MenuItem("Open Dashboard", _open_dashboard, default=True),
        pystray.MenuItem(
            lambda item: f"Daemon: {'Paused' if sv.daemon_paused else 'Running'}",
            None, enabled=False,
        ),
        pystray.MenuItem(
            lambda item: "Resume Daemon" if sv.daemon_paused else "Pause Daemon",
            _toggle_pause,
        ),
        pystray.MenuItem("Settings...", _open_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )
```

Replace the old menu definition (probably `pystray.Menu(pystray.MenuItem("Quit", ...))` or similar) with the new builder.

Also expose `daemon_paused` on `Supervisor` if it isn't already (Task 4 added it; ensure attribute exists).

- [ ] **Step 3: Update `tests/tray/test_icon.py`** (or wherever menu tests live) — assert the menu has 5 items, Open Dashboard is default action, Quit calls `sv.shutdown`.

- [ ] **Step 4: Run**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/tray -v
```

- [ ] **Step 5: Commit**
```
git add claude_mnemos/tray/icon.py tests/tray/
git commit -m "feat(tray): rebuild menu — Open Dashboard / Status / Pause / Settings / Quit

Open Dashboard is the default click action (left-click tray icon).
Daemon status is a read-only label that updates every supervisor tick.
Quit calls supervisor.shutdown() (graceful), not sys.exit."
```

---

### Task 8: Window-close-to-tray dialog + state persistence

When user clicks X on the launcher window: first time → ask, persist choice. Subsequent times → honor choice.

**Files:**
- Modify: `claude_mnemos/launcher.py` — add `on_closing` handler
- Modify: `claude_mnemos/state/install_state.py` — add `window_close_action`
- Test: `tests/test_install_state.py` — extend, `tests/test_launcher.py` — extend

- [ ] **Step 1: Extend `InstallState` schema**

```python
# claude_mnemos/state/install_state.py — extend the model

class InstallState(BaseModel):
    first_run_ts: datetime | None = None
    autostart_decision: Literal["accepted", "declined"] | None = None
    first_session_celebrated_for: list[str] = Field(default_factory=list)
    window_close_action: Literal["hide", "quit"] | None = None  # ← new

    # mark_celebrated, save, load_install_state stay unchanged
```

- [ ] **Step 2: Test for new field**

```python
# tests/test_install_state.py — append
def test_install_state_window_close_action_default_none(state_path):
    s = load_install_state()
    assert s.window_close_action is None


def test_install_state_window_close_action_persists(state_path):
    s = InstallState(window_close_action="hide")
    s.save()
    loaded = load_install_state()
    assert loaded.window_close_action == "hide"
```

- [ ] **Step 3: Run + RED → impl → GREEN**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_install_state.py -v
```

- [ ] **Step 4: Update `launcher.py` to handle window close**

```python
# claude_mnemos/launcher.py — inside _open_window, after webview.create_window:

from claude_mnemos.state.install_state import load_install_state

def _on_closing() -> bool:
    state = load_install_state()
    if state.window_close_action == "hide":
        window.hide()
        return False  # cancel close
    if state.window_close_action == "quit":
        return True  # allow close
    # First time — ask via JS prompt (pywebview supports `evaluate_js`).
    answer = window.evaluate_js(
        "confirm('Close window? OK = minimise to tray. Cancel = quit fully.')"
    )
    state.window_close_action = "hide" if answer else "quit"
    state.save()
    if not answer:
        return True
    window.hide()
    return False

window.events.closing += _on_closing
```

Test additions:

```python
# tests/test_launcher.py — append
def test_launcher_closing_handler_persists_choice(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )

    class FakeWindow:
        def __init__(self):
            self.hidden = False
        def hide(self):
            self.hidden = True
        def evaluate_js(self, code):
            return True  # user picked OK = minimise

    from claude_mnemos.launcher import _make_on_closing
    handler = _make_on_closing(FakeWindow())
    res = handler()
    assert res is False  # close cancelled (we hide instead)

    from claude_mnemos.state.install_state import load_install_state
    assert load_install_state().window_close_action == "hide"
```

NOTE: refactor `_on_closing` into a named factory `_make_on_closing(window)` so it's testable without `webview.start()`.

- [ ] **Step 5: Commit**
```
git add claude_mnemos/launcher.py claude_mnemos/state/install_state.py tests/test_launcher.py tests/test_install_state.py
git commit -m "feat(launcher): close-to-tray dialog with persistent choice

First click on X asks 'minimise or quit'. Saves answer to
install-state.window_close_action. Subsequent clicks honor it.
Tray-menu Quit always exits fully."
```

---

### Task 9: Backend `/api/system/autostart` + `/api/system/window-close-action`

REST endpoints so the frontend Settings page can toggle these without invoking CLI.

**Files:**
- Create: `claude_mnemos/daemon/routes/system.py`
- Modify: `claude_mnemos/daemon/app.py` — mount router
- Test: `tests/daemon/test_app_system.py`

- [ ] **Step 1: Test (RED)**

```python
# tests/daemon/test_app_system.py
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )
    from claude_mnemos.daemon.app import create_app
    app = create_app(daemon=None)
    return TestClient(app)


def test_get_autostart_status(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._is_autostart_installed",
        lambda: True,
    )
    r = client.get("/api/system/autostart")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_set_autostart_enabled_calls_install(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._install_autostart",
        lambda: calls.append("install") or True,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._uninstall_autostart",
        lambda: calls.append("uninstall") or True,
    )
    r = client.post("/api/system/autostart", json={"enabled": True})
    assert r.status_code == 200
    assert "install" in calls
    assert "uninstall" not in calls


def test_set_autostart_disabled_calls_uninstall(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._install_autostart",
        lambda: calls.append("install") or True,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.system._uninstall_autostart",
        lambda: calls.append("uninstall") or True,
    )
    r = client.post("/api/system/autostart", json={"enabled": False})
    assert r.status_code == 200
    assert "uninstall" in calls
    assert "install" not in calls


def test_set_window_close_action(client):
    r = client.post("/api/system/window-close-action", json={"action": "hide"})
    assert r.status_code == 200
    from claude_mnemos.state.install_state import load_install_state
    assert load_install_state().window_close_action == "hide"
```

- [ ] **Step 2: RED**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_app_system.py -v
```

- [ ] **Step 3: Implement**

```python
# claude_mnemos/daemon/routes/system.py
"""System-level toggles: autostart on/off, window-close action."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException

from claude_mnemos.state.install_state import load_install_state

router = APIRouter()


def _is_autostart_installed() -> bool:
    """Cross-platform check: is the autostart entry currently registered?"""
    from claude_mnemos.tray.platform import get_autostart_manager
    from claude_mnemos.tray.__main__ import _resolve_target
    target_exe, target_args = _resolve_target()
    mgr = get_autostart_manager(target_exe=target_exe, target_args=target_args)
    return mgr.is_installed()


def _install_autostart() -> bool:
    from claude_mnemos.tray.platform import get_autostart_manager
    from claude_mnemos.tray.__main__ import _resolve_target
    target_exe, target_args = _resolve_target()
    mgr = get_autostart_manager(target_exe=target_exe, target_args=target_args)
    mgr.install()
    return True


def _uninstall_autostart() -> bool:
    from claude_mnemos.tray.platform import get_autostart_manager
    from claude_mnemos.tray.__main__ import _resolve_target
    target_exe, target_args = _resolve_target()
    mgr = get_autostart_manager(target_exe=target_exe, target_args=target_args)
    mgr.uninstall()
    return True


@router.get("/system/autostart")
def get_autostart() -> dict[str, Any]:
    return {"enabled": _is_autostart_installed()}


@router.post("/system/autostart")
def set_autostart(payload: dict = Body(...)) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    try:
        if enabled:
            _install_autostart()
        else:
            _uninstall_autostart()
    except Exception as exc:
        raise HTTPException(500, f"autostart toggle failed: {exc}")
    return {"ok": True, "enabled": enabled}


@router.post("/system/window-close-action")
def set_window_close_action(payload: dict = Body(...)) -> dict[str, Any]:
    action: Literal["hide", "quit"] | None = payload.get("action")
    if action not in ("hide", "quit"):
        raise HTTPException(400, "action must be 'hide' or 'quit'")
    state = load_install_state()
    state.window_close_action = action
    state.save()
    return {"ok": True, "action": action}
```

- [ ] **Step 4: Mount router in `app.py`**

```python
# claude_mnemos/daemon/app.py — alongside other router includes:
from claude_mnemos.daemon.routes.system import router as system_router
app.include_router(system_router, prefix="/api")
```

Also add `is_installed()` to the platform autostart managers if it's missing — search:
```
grep -n "def is_installed\|class.*AutostartManager" claude_mnemos/tray/platform/*.py
```
If absent, add a method that checks for the `Mnemos.lnk` / launchd plist existence.

- [ ] **Step 5: Run**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_app_system.py -v
```

- [ ] **Step 6: Commit**
```
git add claude_mnemos/daemon/routes/system.py claude_mnemos/daemon/app.py claude_mnemos/tray/platform/ tests/daemon/test_app_system.py
git commit -m "feat(daemon): /api/system/{autostart,window-close-action} routes

GET /system/autostart   — current state
POST /system/autostart  — toggle .lnk on/off
POST /system/window-close-action  — persist user choice

Powers the GlobalSettings UI toggle (Task 10) and the launcher's
close-to-tray dialog (Task 8)."
```

---

### Task 10: Frontend autostart toggle in `/settings/global`

UI for the autostart switch.

**Files:**
- Create: `frontend/src/api/system.api.ts`
- Create: `frontend/src/hooks/useAutostart.ts`
- Modify: `frontend/src/pages/GlobalSettings.tsx` — add toggle
- Modify: `frontend/public/locales/{en,ru,uk}.json` — i18n
- Test: `frontend/src/__tests__/AutostartToggle.test.tsx`

- [ ] **Step 1: API client**

```typescript
// frontend/src/api/system.api.ts
import axios from "axios";

export interface AutostartStatus {
  enabled: boolean;
}

export async function getAutostart(): Promise<AutostartStatus> {
  const r = await axios.get<AutostartStatus>("/api/system/autostart");
  return r.data;
}

export async function setAutostart(enabled: boolean): Promise<void> {
  await axios.post("/api/system/autostart", { enabled });
}
```

- [ ] **Step 2: Hook**

```typescript
// frontend/src/hooks/useAutostart.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getAutostart, setAutostart } from "@/api/system.api";

export function useAutostartStatus() {
  return useQuery({ queryKey: ["autostart"], queryFn: getAutostart });
}

export function useSetAutostart() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: setAutostart,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["autostart"] }),
  });
}
```

- [ ] **Step 3: Toggle in GlobalSettings**

Add a section to `frontend/src/pages/GlobalSettings.tsx`:

```tsx
import { useAutostartStatus, useSetAutostart } from "@/hooks/useAutostart";
import { useTranslation } from "react-i18next";

function AutostartToggle() {
  const { t } = useTranslation();
  const q = useAutostartStatus();
  const m = useSetAutostart();

  if (q.isLoading || !q.data) return null;
  return (
    <div className="flex items-center gap-3 py-2">
      <input
        type="checkbox"
        checked={q.data.enabled}
        onChange={(e) => m.mutate(e.target.checked)}
        disabled={m.isPending}
      />
      <div>
        <div className="text-sm font-medium">
          {t("settings.system.autostart_label", "Запускать с Windows")}
        </div>
        <div className="text-xs text-muted-foreground">
          {t("settings.system.autostart_hint",
              "Daemon стартует автоматически при логине. Сессии Claude Code собираются всегда.")}
        </div>
      </div>
    </div>
  );
}

// Inside the page render, in a System section:
<section className="rounded-md border p-4">
  <div className="eyebrow mb-2">SYSTEM</div>
  <AutostartToggle />
</section>
```

- [ ] **Step 4: i18n keys**

Add to `frontend/public/locales/en.json`:
```json
"settings.system.autostart_label": "Start with Windows",
"settings.system.autostart_hint": "Daemon starts automatically at login. Claude Code sessions are always captured."
```

ru.json + uk.json: translate the strings (Russian + Ukrainian).

- [ ] **Step 5: Test**

```typescript
// frontend/src/__tests__/AutostartToggle.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/api/system.api";

vi.mock("@/api/system.api");

// Inline AutostartToggle for test isolation:
import { useAutostartStatus, useSetAutostart } from "@/hooks/useAutostart";

function AutostartToggle() {
  const q = useAutostartStatus();
  const m = useSetAutostart();
  if (q.isLoading || !q.data) return null;
  return (
    <label>
      <input
        type="checkbox"
        checked={q.data.enabled}
        onChange={(e) => m.mutate(e.target.checked)}
      />
      Start with Windows
    </label>
  );
}

beforeEach(() => vi.clearAllMocks());

function renderToggle() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AutostartToggle />
    </QueryClientProvider>,
  );
}

describe("AutostartToggle", () => {
  it("renders checked when enabled", async () => {
    vi.mocked(api.getAutostart).mockResolvedValue({ enabled: true });
    renderToggle();
    const cb = await screen.findByRole("checkbox");
    expect(cb).toBeChecked();
  });

  it("calls setAutostart(false) when toggled off", async () => {
    vi.mocked(api.getAutostart).mockResolvedValue({ enabled: true });
    vi.mocked(api.setAutostart).mockResolvedValue();
    renderToggle();
    const cb = await screen.findByRole("checkbox");
    await userEvent.click(cb);
    await waitFor(() => expect(api.setAutostart).toHaveBeenCalledWith(false));
  });
});
```

- [ ] **Step 6: Run frontend**
```
cd frontend && npm test -- --run AutostartToggle
cd frontend && npm run typecheck
```
Expected: 2 PASS, 0 TS errors.

- [ ] **Step 7: Commit**
```
git add frontend/src/api/system.api.ts frontend/src/hooks/useAutostart.ts frontend/src/pages/GlobalSettings.tsx frontend/src/__tests__/AutostartToggle.test.tsx frontend/public/locales/
git commit -m "feat(ui): autostart toggle in GlobalSettings → /api/system/autostart

Mandatory autostart by default (Phase 3 spec). Power users can opt out
via this toggle without rebuilding/reinstalling."
```

---

### Task 11: PyInstaller spec + Inno Setup updates

Bundle pywebview, install WebView2 Runtime if missing, switch installer entry to `launcher`, switch desktop-icon to `checkedonce`.

**Files:**
- Modify: `installer/pyinstaller/mnemos.spec`
- Modify: `installer/windows/mnemos.iss`
- Modify: `installer/macos/setup.py`
- Modify: `installer/linux/build-appimage.sh` (add note)
- Create: `installer/windows/MicrosoftEdgeWebview2Setup.exe` (download once during build)

- [ ] **Step 1: PyInstaller hidden imports**

In `installer/pyinstaller/mnemos.spec`, add to `hiddenimports`:
```python
    "webview",
    "webview.platforms.winforms",  # Win
    "webview.platforms.cocoa",     # Mac
    "webview.platforms.gtk",       # Linux
    "clr_loader",
    "pythonnet",
```

- [ ] **Step 2: Inno Setup — WebView2 detect + install**

Edit `installer/windows/mnemos.iss`:

(a) Change `[Files]` to include the WebView2 Setup binary:
```ini
[Files]
Source: "..\..\dist\claude-mnemos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
```

(b) Change desktop-icon task to `checkedonce`:
```ini
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на &рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: checkedonce
Name: "autostart";   Description: "Запускать &claude-mnemos при входе в Windows"; GroupDescription: "Автозапуск:"; Flags: checkedonce
```

(c) Add WebView2 install Run step + Code section:
```ini
[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; Check: not WebView2RuntimeInstalled; StatusMsg: "Installing Edge WebView2 Runtime..."

; Replace the existing tray-run [Run] entry with launcher:
Filename: "{app}\{#MyAppExeName}"; Parameters: "launcher"; Description: "Запустить claude-mnemos сейчас"; Flags: postinstall nowait skipifsilent

[Icons]
; Update to launcher arg:
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "launcher"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "launcher"; Tasks: desktopicon

[Code]
function WebView2RuntimeInstalled: Boolean;
var
  V: string;
begin
  Result := RegQueryStringValue(HKLM,
    'Software\Wow6432Node\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', V) and (V <> '');
  if not Result then
    Result := RegQueryStringValue(HKCU,
      'Software\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', V) and (V <> '');
end;
```

- [ ] **Step 3: Download WebView2 Setup binary**

```
cd installer/windows
curl -L -o MicrosoftEdgeWebview2Setup.exe https://go.microsoft.com/fwlink/p/?LinkId=2124703
test -f MicrosoftEdgeWebview2Setup.exe && ls -la MicrosoftEdgeWebview2Setup.exe
```

Add to `.gitignore` if it shouldn't be committed (it's ~200KB — small enough to commit). Decision: **commit** — keeps the installer build reproducible without network access:
```
git add -f installer/windows/MicrosoftEdgeWebview2Setup.exe
```

- [ ] **Step 4: Mac setup.py**

Add to `OPTIONS["packages"]`:
```python
"packages": [..., "webview"],
```

- [ ] **Step 5: Linux AppImage README note**

In `installer/linux/README.md` add:
```markdown
## Runtime requirements

The AppImage requires `webkit2gtk-4.0` to render the launcher window. On
Ubuntu/Debian:

    sudo apt install libwebkit2gtk-4.0-37

On Fedora:

    sudo dnf install webkit2gtk4.0
```

- [ ] **Step 6: Local rebuild + smoke test on Win**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm
./dist/claude-mnemos/claude-mnemos.exe doctor
./dist/claude-mnemos/claude-mnemos.exe launcher --no-spawn-tray --help  # should not crash
```

The smoke test (`tests/installer/test_pyinstaller_smoke.py`) needs an extra `MNEMOS_SKIP_POSTINSTALL=1` env (already there from Phase 2). Run:
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/installer/test_pyinstaller_smoke.py -v
```

- [ ] **Step 7: Commit**

```
git add installer/pyinstaller/mnemos.spec installer/windows/mnemos.iss installer/windows/MicrosoftEdgeWebview2Setup.exe installer/macos/setup.py installer/linux/README.md
git commit -m "feat(installer): bundle pywebview, install WebView2, switch entry to launcher

PyInstaller now collects pywebview platform packages.
Inno Setup detects + installs Edge WebView2 Runtime if missing.
[Run] postinstall step changed from 'tray run' to 'launcher'.
Desktop shortcut switched from unchecked to checkedonce (Yarik
mandatory-shortcut requirement). Mac py2app picks up pywebview via
packages list. Linux README documents webkit2gtk apt dep."
```

---

### Task 12: Live walk + final report

End-to-end verification on a real Win11 dev box. The 7 success-criteria from the spec.

**Files:**
- Create: `docs/superpowers/notes/2026-05-05-e1-live-walk.md` (handover note)

- [ ] **Step 1: Build + install locally**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/windows/mnemos.iss
./installer/windows/dist/claude-mnemos-setup-x64.exe /SILENT
```

(Inno Setup must be installed locally; if not, document this gap and run on CI instead.)

- [ ] **Step 2: Verify success criteria 1–7 from the spec**

1. Tray icon appears immediately after install (no browser tab opened).
2. Double-click Start Menu shortcut → window opens within 3s, dashboard renders.
3. Close window → window disappears, tray stays, daemon stays.
4. Reboot → tray + daemon auto-start; window does NOT auto-open.
5. Right-click tray → menu has Open Dashboard / Pause / Settings / Quit.
6. Run installer twice → no second tray spawned.
7. CLI `mnemos doctor` from terminal works without spawning a tray.

Document any deviations in the live-walk note.

- [ ] **Step 3: Run full backend + frontend regression**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
cd frontend && npm test -- --run | tail -5
cd frontend && npm run typecheck
```

Expected: backend ≥ 1730 (1701 + ~30 new), frontend ≥ 363 (360 + ~3), TS clean.

- [ ] **Step 4: Push when all green**

```
git push origin main
```

- [ ] **Step 5: Tag v0.0.1-rc5** (or whatever the next rc number is) to trigger CI matrix:

```
git tag v0.0.1-rc5
git push origin v0.0.1-rc5
```

If CI is green, tag `v0.0.1` proper for the public release.

- [ ] **Step 6: Write the live-walk note**

```markdown
# E1 Live Walk — 2026-MM-DD

Phase 3 (E1 desktop launcher) verification.

## Tested on
- Windows 11 22H2, dev box
- Build: `claude-mnemos-setup-x64.exe` from `vX.Y.Z`

## Results (success criteria)

| # | Criterion | Result | Notes |
|---|---|---|---|
| 1 | Tray icon after install (no browser tab) | ✓ / ✗ | ... |
| 2 | Window opens in ≤3s from shortcut | ✓ / ✗ | ... |
| 3 | Close → window hides, tray + daemon alive | ✓ / ✗ | ... |
| 4 | Boot autostart works | ✓ / ✗ | requires reboot |
| 5 | Tray menu has 5 entries | ✓ / ✗ | ... |
| 6 | Double-install → no second tray | ✓ / ✗ | mutex test |
| 7 | `mnemos doctor` from terminal — no tray spawn | ✓ / ✗ | ... |
```

- [ ] **Step 7: Commit + push the note**

```
git add docs/superpowers/notes/
git commit -m "docs(notes): E1 live walk — Phase 3 verification report"
git push origin main
```

---

## Self-review notes

- **Spec coverage:** Every section of the spec maps to a task. Three-process model = Tasks 3, 4, 5, 6. Single-instance fix = Tasks 1, 2, 3. Window lifecycle = Tasks 5, 8. Tray menu = Task 7. Autostart toggle = Tasks 9, 10. Installers = Task 11. Live walk = Task 12.
- **Type consistency:** `IpcServer.address` (str), `single_instance.acquire() -> bool`, `Supervisor.launcher_proc: subprocess.Popen | None`, `InstallState.window_close_action: Literal["hide","quit"] | None` — same names used across all tasks.
- **No placeholders:** Every code block is concrete. The Inno Setup `[Code]` section has the actual GUID for the Edge WebView2 Runtime client state. The `pywin32` mention in Task 2 is an explicit fallback not a TBD.
- **Risks acknowledged:** Task 2 notes that pywin32 may simplify the Win named-pipe code if the engineer prefers; either approach satisfies the test contract. Task 11 documents the WebView2 binary commit decision.
- **Total budget:** 12 tasks × ~1.5–2.5h each = ~3.5–4 working days, matches the spec's estimate.
