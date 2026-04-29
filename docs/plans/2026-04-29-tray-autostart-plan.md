# Tray + Autostart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При логине в Win/Mac запускается `mnemos-tray` (supervisor), который владеет daemon как subprocess; иконка в трее → один клик открывает дашборд; авто-restart на крашах.

**Architecture:** Pystray supervisor процесс владеет daemon subprocess через `subprocess.Popen`. Платформо-зависимая часть autostart изолирована за `AutostartManager` Protocol (Win — `.lnk` через PowerShell, Mac — `.plist` + `launchctl`). Restart-limiter ограничивает auto-restart до 3 крахов / 5 минут.

**Tech Stack:** Python 3.12+, pystray, Pillow, psutil, httpx (всё уже есть кроме pystray/Pillow), FastAPI для HTTP API, React/TypeScript для UI.

**Design doc:** `docs/plans/2026-04-29-tray-autostart-design.md`.

**Branch:** `feat/tray-autostart` (создан из `main` после merge `7f1560b`).

---

## File Structure

### New files

```
claude_mnemos/tray/__init__.py                    # пустой пакет-маркер
claude_mnemos/tray/__main__.py                    # entrypoint: `mnemos-tray` / `python -m claude_mnemos.tray`
claude_mnemos/tray/supervisor.py                  # State, RestartLimiter, Supervisor
claude_mnemos/tray/icon.py                        # pystray TrayApp (skipped в CI)
claude_mnemos/tray/platform/__init__.py           # get_autostart_manager() factory
claude_mnemos/tray/platform/base.py               # AutostartManager Protocol
claude_mnemos/tray/platform/windows.py            # WindowsAutostart
claude_mnemos/tray/platform/macos.py              # MacOSAutostart
claude_mnemos/tray/assets/icon-running.png        # placeholder, 22x22
claude_mnemos/tray/assets/icon-stopped.png
claude_mnemos/tray/assets/icon-running.ico        # Windows
claude_mnemos/tray/assets/icon-stopped.ico
claude_mnemos/cli_tray.py                         # `mnemos tray ...`
claude_mnemos/daemon/routes/tray.py               # FastAPI router

frontend/src/types/Tray.ts                        # zod schemas
frontend/src/api/tray.api.ts                      # axios client

tests/tray/__init__.py
tests/tray/test_platform_base.py
tests/tray/test_platform_windows.py
tests/tray/test_platform_macos.py
tests/tray/test_platform_factory.py
tests/tray/test_restart_limiter.py
tests/tray/test_supervisor_state.py
tests/tray/test_supervisor_subprocess.py
tests/tray/test_supervisor_adopt_and_loop.py
tests/tray/test_icon.py                           # @pytest.mark.manual
tests/test_cli_tray.py
tests/daemon/routes/test_tray.py
frontend/src/__tests__/api-tray.test.ts
```

### Modified files

```
pyproject.toml                                    # +pystray, +Pillow, +mnemos-tray entry
claude_mnemos/cli.py                              # +tray subcommand
claude_mnemos/daemon/app.py                       # mount tray router
frontend/src/pages/Onboarding.tsx                 # +Auto-start checkbox after success
frontend/src/__tests__/Onboarding.test.tsx        # cover new checkbox
```

---

## Task 1: Tray package skeleton + dependencies

**Files:**
- Create: `claude_mnemos/tray/__init__.py`
- Create: `claude_mnemos/tray/__main__.py` (placeholder)
- Create: `claude_mnemos/tray/platform/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create empty package markers**

```bash
mkdir -p D:/code/claude-mnemos/claude_mnemos/tray/platform
mkdir -p D:/code/claude-mnemos/claude_mnemos/tray/assets
```

Write `claude_mnemos/tray/__init__.py`:
```python
"""Tray-icon supervisor for claude-mnemos daemon (Plan 2026-04-29).

Standalone Python process that owns the daemon as a subprocess, displays a
system-tray icon, and exposes a small menu (Open dashboard / Restart / Show
logs / Quit). See docs/plans/2026-04-29-tray-autostart-design.md.
"""
```

Write `claude_mnemos/tray/platform/__init__.py`:
```python
"""Platform-specific autostart implementations behind a common Protocol."""
```

Write placeholder `claude_mnemos/tray/__main__.py`:
```python
"""Entrypoint for `mnemos-tray` / `python -m claude_mnemos.tray`. Filled in Task 11."""

def main() -> int:
    raise NotImplementedError("Filled in Task 11")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 2: Add dependencies to pyproject.toml**

Modify `pyproject.toml` `dependencies` list (alphabetical, add `Pillow` and `pystray` between `mcp` and `psutil`):

```toml
dependencies = [
    "pydantic>=2.0",
    "filelock>=3.13",
    "pyyaml>=6.0",
    "anthropic>=0.40",
    "unidecode>=1.3",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "apscheduler>=3.10",
    "Pillow>=10",
    "psutil>=5.9",
    "httpx>=0.27",
    "mcp>=1.12",
    "pystray>=0.19",
    "watchdog>=4.0",
]
```

Add `mnemos-tray` to `[project.scripts]`:

```toml
[project.scripts]
mnemos = "claude_mnemos.cli:main"
mnemos-mcp = "claude_mnemos.mcp.__main__:main"
mnemos-tray = "claude_mnemos.tray.__main__:main"
```

- [ ] **Step 3: Reinstall in editable mode and verify imports**

Run:
```bash
cd /d/code/claude-mnemos && python -m pip install -e . 2>&1 | tail -5
```

Expected: `Successfully installed claude-mnemos-0.0.1 ...` (or "Already installed" then a re-collected metadata line).

Verify imports:
```bash
python -c "import pystray; import PIL; import claude_mnemos.tray; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Verify entrypoint registered**

```bash
which mnemos-tray
```

Expected: a path like `/c/Users/68664/AppData/Local/Programs/Python/Python312/Scripts/mnemos-tray` (Windows) or `/usr/local/bin/mnemos-tray` (mac).

Run it (should fail with NotImplementedError):
```bash
mnemos-tray; echo "exit=$?"
```

Expected: traceback ending in `NotImplementedError: Filled in Task 11`, exit code 1.

- [ ] **Step 5: Commit**

```bash
cd /d/code/claude-mnemos && git add pyproject.toml claude_mnemos/tray/ && git commit -m "feat(tray): package skeleton + pystray/Pillow dependencies + entrypoint

Empty marker files for the new tray package. Adds pystray and Pillow to
runtime deps. Registers mnemos-tray entrypoint pointing to a placeholder
main() that raises NotImplementedError until Task 11.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: AutostartManager Protocol

**Files:**
- Create: `claude_mnemos/tray/platform/base.py`
- Create: `tests/tray/__init__.py`
- Create: `tests/tray/test_platform_base.py`

- [ ] **Step 1: Write the failing test**

Create empty `tests/tray/__init__.py`.

Create `tests/tray/test_platform_base.py`:
```python
from __future__ import annotations

from claude_mnemos.tray.platform.base import AutostartManager, AutostartStatus


def test_autostart_status_dataclass_fields() -> None:
    status = AutostartStatus(installed=True, path="/tmp/x.lnk")
    assert status.installed is True
    assert status.path == "/tmp/x.lnk"


def test_autostart_status_default_path_none() -> None:
    status = AutostartStatus(installed=False)
    assert status.path is None


def test_autostart_manager_is_runtime_checkable_protocol() -> None:
    """A class with the right methods should pass isinstance check."""

    class Stub:
        def install(self) -> None: ...
        def uninstall(self) -> None: ...
        def status(self) -> AutostartStatus:
            return AutostartStatus(installed=False)

    assert isinstance(Stub(), AutostartManager)


def test_autostart_manager_rejects_class_missing_methods() -> None:
    class Incomplete:
        def install(self) -> None: ...

    assert not isinstance(Incomplete(), AutostartManager)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /d/code/claude-mnemos && python -m pytest tests/tray/test_platform_base.py -v 2>&1 | tail -10
```

Expected: ImportError / ModuleNotFoundError on `claude_mnemos.tray.platform.base`.

- [ ] **Step 3: Write the Protocol**

Create `claude_mnemos/tray/platform/base.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/tray/test_platform_base.py -v 2>&1 | tail -10
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/platform/base.py tests/tray/__init__.py tests/tray/test_platform_base.py && git commit -m "feat(tray): AutostartManager Protocol + AutostartStatus dataclass

Common contract for OS-specific autostart impls. Used by Windows/macOS
modules in subsequent tasks. runtime_checkable so duck-typed stubs in
tests pass isinstance checks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Windows AutostartManager (.lnk via PowerShell)

**Files:**
- Create: `claude_mnemos/tray/platform/windows.py`
- Create: `tests/tray/test_platform_windows.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tray/test_platform_windows.py`:
```python
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from claude_mnemos.tray.platform.windows import (
    SHORTCUT_NAME,
    WindowsAutostart,
)


def _stub_completed(returncode: int = 0, stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stderr = stderr
    return m


@pytest.fixture
def fake_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    startup = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return startup


def test_status_when_shortcut_absent(fake_appdata: Path) -> None:
    mgr = WindowsAutostart(target_exe="C:\\Python\\Scripts\\mnemos-tray.exe")
    status = mgr.status()
    assert status.installed is False
    assert status.path == str(fake_appdata / SHORTCUT_NAME)


def test_status_when_shortcut_present(fake_appdata: Path) -> None:
    (fake_appdata / SHORTCUT_NAME).write_bytes(b"\x00")  # any content
    mgr = WindowsAutostart(target_exe="C:\\Python\\Scripts\\mnemos-tray.exe")
    assert mgr.status().installed is True


def test_install_runs_powershell_with_target(fake_appdata: Path) -> None:
    mgr = WindowsAutostart(target_exe="C:\\Python\\Scripts\\mnemos-tray.exe")
    with patch("claude_mnemos.tray.platform.windows.subprocess.run") as run:
        run.return_value = _stub_completed(0)
        mgr.install()
        assert run.called
        cmd = run.call_args[0][0]
        # First two args are powershell + flags
        assert cmd[0].lower().endswith("powershell.exe") or cmd[0].lower() == "powershell"
        joined = " ".join(cmd)
        assert "mnemos-tray.exe" in joined
        assert "WScript.Shell" in joined
        assert "CreateShortcut" in joined
        assert SHORTCUT_NAME in joined
        assert "run" in joined  # passes "run" arg to mnemos-tray


def test_install_raises_runtime_error_on_powershell_failure(fake_appdata: Path) -> None:
    mgr = WindowsAutostart(target_exe="C:\\X\\mnemos-tray.exe")
    with patch("claude_mnemos.tray.platform.windows.subprocess.run") as run:
        run.return_value = _stub_completed(1, stderr="permission denied")
        with pytest.raises(RuntimeError, match="powershell exit 1"):
            mgr.install()


def test_uninstall_deletes_shortcut(fake_appdata: Path) -> None:
    shortcut = fake_appdata / SHORTCUT_NAME
    shortcut.write_bytes(b"\x00")
    mgr = WindowsAutostart(target_exe="C:\\X\\mnemos-tray.exe")
    mgr.uninstall()
    assert not shortcut.exists()


def test_uninstall_idempotent_when_absent(fake_appdata: Path) -> None:
    mgr = WindowsAutostart(target_exe="C:\\X\\mnemos-tray.exe")
    mgr.uninstall()  # must not raise
    assert mgr.status().installed is False


def test_install_overwrites_existing_shortcut(fake_appdata: Path) -> None:
    (fake_appdata / SHORTCUT_NAME).write_bytes(b"old")
    mgr = WindowsAutostart(target_exe="C:\\X\\mnemos-tray.exe")
    with patch("claude_mnemos.tray.platform.windows.subprocess.run") as run:
        run.return_value = _stub_completed(0)
        mgr.install()  # idempotent — no exception
        assert run.called
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/tray/test_platform_windows.py -v 2>&1 | tail -10
```

Expected: ModuleNotFoundError for `claude_mnemos.tray.platform.windows`.

- [ ] **Step 3: Implement WindowsAutostart**

Create `claude_mnemos/tray/platform/windows.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/tray/test_platform_windows.py -v 2>&1 | tail -15
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/platform/windows.py tests/tray/test_platform_windows.py && git commit -m "feat(tray): WindowsAutostart via Startup-folder .lnk

PowerShell WScript.Shell creates the .lnk; no pywin32 dep. Idempotent
install (overwrite) and uninstall (unlink missing_ok). Status only checks
file existence.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: macOS AutostartManager (launchd plist)

**Files:**
- Create: `claude_mnemos/tray/platform/macos.py`
- Create: `tests/tray/test_platform_macos.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tray/test_platform_macos.py`:
```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from claude_mnemos.tray.platform.macos import (
    BUNDLE_ID,
    PLIST_FILENAME,
    MacOSAutostart,
)


def _stub_completed(returncode: int = 0, stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stderr = stderr
    return m


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    return agents


def test_bundle_id_format() -> None:
    assert BUNDLE_ID == "com.claude-mnemos.tray"
    assert PLIST_FILENAME == f"{BUNDLE_ID}.plist"


def test_status_absent(fake_home: Path) -> None:
    mgr = MacOSAutostart(target_exe="/usr/local/bin/mnemos-tray")
    s = mgr.status()
    assert s.installed is False
    assert s.path == str(fake_home / PLIST_FILENAME)


def test_status_present(fake_home: Path) -> None:
    (fake_home / PLIST_FILENAME).write_text("<?xml ?>")
    mgr = MacOSAutostart(target_exe="/usr/local/bin/mnemos-tray")
    assert mgr.status().installed is True


def test_install_writes_plist_and_runs_launchctl_load(fake_home: Path) -> None:
    mgr = MacOSAutostart(target_exe="/usr/local/bin/mnemos-tray")
    with patch("claude_mnemos.tray.platform.macos.subprocess.run") as run:
        run.return_value = _stub_completed(0)
        mgr.install()

    plist_path = fake_home / PLIST_FILENAME
    assert plist_path.is_file()
    content = plist_path.read_text(encoding="utf-8")
    assert "<?xml" in content
    assert "<plist" in content
    assert f"<string>{BUNDLE_ID}</string>" in content
    assert "<string>/usr/local/bin/mnemos-tray</string>" in content
    assert "<string>run</string>" in content
    assert "<key>RunAtLoad</key>" in content
    assert "<true/>" in content

    # Verify launchctl invocation
    cmd = run.call_args[0][0]
    assert cmd[0] == "launchctl"
    assert "load" in cmd
    assert str(plist_path) in cmd


def test_install_raises_on_launchctl_failure(fake_home: Path) -> None:
    mgr = MacOSAutostart(target_exe="/usr/local/bin/mnemos-tray")
    with patch("claude_mnemos.tray.platform.macos.subprocess.run") as run:
        run.return_value = _stub_completed(1, stderr="boom")
        with pytest.raises(RuntimeError, match="launchctl"):
            mgr.install()


def test_uninstall_unloads_and_deletes(fake_home: Path) -> None:
    plist_path = fake_home / PLIST_FILENAME
    plist_path.write_text("<?xml ?>")
    mgr = MacOSAutostart(target_exe="/usr/local/bin/mnemos-tray")
    with patch("claude_mnemos.tray.platform.macos.subprocess.run") as run:
        run.return_value = _stub_completed(0)
        mgr.uninstall()
    assert not plist_path.exists()
    cmd = run.call_args[0][0]
    assert "launchctl" in cmd[0]
    assert "unload" in cmd


def test_uninstall_idempotent_when_plist_absent(fake_home: Path) -> None:
    mgr = MacOSAutostart(target_exe="/usr/local/bin/mnemos-tray")
    with patch("claude_mnemos.tray.platform.macos.subprocess.run") as run:
        mgr.uninstall()  # no plist file → must NOT call launchctl, must NOT raise
        assert not run.called
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/tray/test_platform_macos.py -v 2>&1 | tail -10
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement MacOSAutostart**

Create `claude_mnemos/tray/platform/macos.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/tray/test_platform_macos.py -v 2>&1 | tail -15
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/platform/macos.py tests/tray/test_platform_macos.py && git commit -m "feat(tray): MacOSAutostart via launchd LaunchAgent plist

Plist at ~/Library/LaunchAgents/com.claude-mnemos.tray.plist with
RunAtLoad+KeepAlive. launchctl load/unload via subprocess. Idempotent.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Platform factory + unsupported sentinel

**Files:**
- Modify: `claude_mnemos/tray/platform/__init__.py`
- Create: `tests/tray/test_platform_factory.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tray/test_platform_factory.py`:
```python
from __future__ import annotations

from unittest.mock import patch

from claude_mnemos.tray.platform import (
    PLATFORM_NAME,
    UnsupportedAutostart,
    get_autostart_manager,
)
from claude_mnemos.tray.platform.macos import MacOSAutostart
from claude_mnemos.tray.platform.windows import WindowsAutostart


def test_get_autostart_manager_windows() -> None:
    with patch("claude_mnemos.tray.platform.sys.platform", "win32"):
        mgr = get_autostart_manager(target_exe="C:\\X\\mnemos-tray.exe")
        assert isinstance(mgr, WindowsAutostart)
        assert PLATFORM_NAME["win32"] == "windows"


def test_get_autostart_manager_macos() -> None:
    with patch("claude_mnemos.tray.platform.sys.platform", "darwin"):
        mgr = get_autostart_manager(target_exe="/usr/local/bin/mnemos-tray")
        assert isinstance(mgr, MacOSAutostart)


def test_get_autostart_manager_linux_returns_unsupported() -> None:
    with patch("claude_mnemos.tray.platform.sys.platform", "linux"):
        mgr = get_autostart_manager(target_exe="/x/mnemos-tray")
        assert isinstance(mgr, UnsupportedAutostart)


def test_unsupported_autostart_raises_on_install() -> None:
    mgr = UnsupportedAutostart()
    import pytest

    with pytest.raises(NotImplementedError, match="not supported"):
        mgr.install()
    with pytest.raises(NotImplementedError):
        mgr.uninstall()


def test_unsupported_autostart_status_returns_false() -> None:
    s = UnsupportedAutostart().status()
    assert s.installed is False
    assert s.path is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/tray/test_platform_factory.py -v 2>&1 | tail -10
```

Expected: ImportError on `PLATFORM_NAME`, `UnsupportedAutostart`, `get_autostart_manager`.

- [ ] **Step 3: Implement factory**

Replace `claude_mnemos/tray/platform/__init__.py` content:
```python
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


def get_autostart_manager(target_exe: str) -> AutostartManager:
    if sys.platform == "win32":
        from claude_mnemos.tray.platform.windows import WindowsAutostart
        return WindowsAutostart(target_exe=target_exe)
    if sys.platform == "darwin":
        from claude_mnemos.tray.platform.macos import MacOSAutostart
        return MacOSAutostart(target_exe=target_exe)
    return UnsupportedAutostart()


__all__ = [
    "AutostartManager",
    "AutostartStatus",
    "PLATFORM_NAME",
    "UnsupportedAutostart",
    "get_autostart_manager",
    "platform_label",
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/tray/test_platform_factory.py -v 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/platform/__init__.py tests/tray/test_platform_factory.py && git commit -m "feat(tray): platform factory + UnsupportedAutostart for Linux

get_autostart_manager() returns Windows/macOS impl based on sys.platform,
or UnsupportedAutostart stub on Linux. UI hides the autostart checkbox
when status() reports unsupported.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: RestartLimiter (sliding-window crash counter)

**Files:**
- Create: `claude_mnemos/tray/supervisor.py` (RestartLimiter only)
- Create: `tests/tray/test_restart_limiter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tray/test_restart_limiter.py`:
```python
from __future__ import annotations

from claude_mnemos.tray.supervisor import RestartLimiter


def test_initial_state_allows_restart() -> None:
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    assert lim.crash_count() == 0
    assert lim.should_restart() is True


def test_records_crashes_and_blocks_after_threshold() -> None:
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    # Three crashes at the same monotonic time
    lim.record_crash(now=100.0)
    lim.record_crash(now=100.5)
    lim.record_crash(now=101.0)
    assert lim.crash_count(now=101.0) == 3
    assert lim.should_restart(now=101.0) is True  # exactly == max, still allow

    lim.record_crash(now=101.5)
    assert lim.crash_count(now=101.5) == 4
    assert lim.should_restart(now=101.5) is False


def test_old_crashes_outside_window_are_pruned() -> None:
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    lim.record_crash(now=0.0)
    lim.record_crash(now=10.0)
    lim.record_crash(now=20.0)
    lim.record_crash(now=30.0)
    # All 4 are within 5min — limiter blocks
    assert lim.should_restart(now=30.0) is False
    # Skip ahead 6 minutes — all 4 fall outside the 300s window
    assert lim.crash_count(now=400.0) == 0
    assert lim.should_restart(now=400.0) is True


def test_reset_clears_counter() -> None:
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    lim.record_crash(now=0.0)
    lim.record_crash(now=1.0)
    lim.record_crash(now=2.0)
    lim.record_crash(now=3.0)
    assert lim.should_restart(now=3.0) is False
    lim.reset()
    assert lim.crash_count() == 0
    assert lim.should_restart() is True


def test_backoff_seconds_progression() -> None:
    """1st crash → 1s, 2nd → 2s, 3rd → 4s, then capped at 4s."""
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    lim.record_crash(now=0.0)
    assert lim.next_backoff_seconds() == 1.0
    lim.record_crash(now=1.0)
    assert lim.next_backoff_seconds() == 2.0
    lim.record_crash(now=2.0)
    assert lim.next_backoff_seconds() == 4.0
    lim.record_crash(now=3.0)
    assert lim.next_backoff_seconds() == 4.0  # capped
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/tray/test_restart_limiter.py -v 2>&1 | tail -10
```

Expected: ModuleNotFoundError on `claude_mnemos.tray.supervisor`.

- [ ] **Step 3: Implement RestartLimiter**

Create `claude_mnemos/tray/supervisor.py`:
```python
"""Tray supervisor — owns the daemon subprocess and a state machine.

Phase 1 (this file): RestartLimiter only. State enum, Supervisor class,
adopt + main loop are added in subsequent tasks.
"""

from __future__ import annotations

import time
from collections import deque


class RestartLimiter:
    """Sliding-window crash counter for daemon auto-restart.

    Allows at most ``max_crashes`` crashes inside any rolling
    ``window_seconds`` interval. Backoff between restarts grows
    exponentially (1, 2, 4 seconds), capped at 4 seconds.
    """

    def __init__(
        self,
        *,
        max_crashes: int = 3,
        window_seconds: float = 300.0,
        backoff_cap_seconds: float = 4.0,
    ) -> None:
        self.max_crashes = max_crashes
        self.window_seconds = window_seconds
        self.backoff_cap_seconds = backoff_cap_seconds
        self._crashes: deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._crashes and self._crashes[0] < cutoff:
            self._crashes.popleft()

    def record_crash(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._prune(now)
        self._crashes.append(now)

    def crash_count(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        self._prune(now)
        return len(self._crashes)

    def should_restart(self, now: float | None = None) -> bool:
        return self.crash_count(now) <= self.max_crashes

    def next_backoff_seconds(self) -> float:
        # 1, 2, 4, 4, 4 ...
        n = len(self._crashes)
        if n == 0:
            return 0.0
        delay = 2 ** (n - 1)
        return min(float(delay), self.backoff_cap_seconds)

    def reset(self) -> None:
        self._crashes.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/tray/test_restart_limiter.py -v 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/supervisor.py tests/tray/test_restart_limiter.py && git commit -m "feat(tray): RestartLimiter sliding-window crash counter

Allows up to max_crashes inside window_seconds; exponential backoff
capped at backoff_cap_seconds. Pure-logic, easy to unit-test with
explicit 'now' parameter.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: SupervisorState enum + state transitions

**Files:**
- Modify: `claude_mnemos/tray/supervisor.py` (extend with State enum)
- Create: `tests/tray/test_supervisor_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tray/test_supervisor_state.py`:
```python
from __future__ import annotations

import pytest

from claude_mnemos.tray.supervisor import SupervisorState, valid_transition


def test_state_enum_values() -> None:
    expected = {"starting", "running", "restarting", "stopping", "stopped", "crashed"}
    actual = {s.value for s in SupervisorState}
    assert actual == expected


def test_initial_states_allowed() -> None:
    # Any → Starting is allowed (initial transition from None)
    assert valid_transition(None, SupervisorState.STARTING) is True


@pytest.mark.parametrize("from_, to_, ok", [
    (SupervisorState.STARTING, SupervisorState.RUNNING, True),
    (SupervisorState.STARTING, SupervisorState.CRASHED, True),  # spawn failed
    (SupervisorState.STARTING, SupervisorState.STOPPED, False),  # weird, must Stop first
    (SupervisorState.RUNNING, SupervisorState.RESTARTING, True),
    (SupervisorState.RUNNING, SupervisorState.STOPPING, True),
    (SupervisorState.RUNNING, SupervisorState.CRASHED, True),
    (SupervisorState.RUNNING, SupervisorState.STARTING, False),
    (SupervisorState.RESTARTING, SupervisorState.RUNNING, True),
    (SupervisorState.RESTARTING, SupervisorState.CRASHED, True),
    (SupervisorState.STOPPING, SupervisorState.STOPPED, True),
    (SupervisorState.STOPPING, SupervisorState.RUNNING, False),
    (SupervisorState.STOPPED, SupervisorState.STARTING, True),  # manual restart
    (SupervisorState.STOPPED, SupervisorState.RUNNING, False),
    (SupervisorState.CRASHED, SupervisorState.STARTING, True),  # manual restart from menu
    (SupervisorState.CRASHED, SupervisorState.RUNNING, False),
])
def test_valid_transitions(from_: SupervisorState, to_: SupervisorState, ok: bool) -> None:
    assert valid_transition(from_, to_) is ok
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/tray/test_supervisor_state.py -v 2>&1 | tail -10
```

Expected: ImportError on `SupervisorState`, `valid_transition`.

- [ ] **Step 3: Add SupervisorState and valid_transition**

Append to `claude_mnemos/tray/supervisor.py` (after RestartLimiter class, BEFORE any final blank line):

```python


from enum import Enum


class SupervisorState(Enum):
    STARTING = "starting"
    RUNNING = "running"
    RESTARTING = "restarting"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"


_VALID_TRANSITIONS: dict[SupervisorState | None, set[SupervisorState]] = {
    None: {SupervisorState.STARTING},
    SupervisorState.STARTING: {SupervisorState.RUNNING, SupervisorState.CRASHED},
    SupervisorState.RUNNING: {
        SupervisorState.RESTARTING,
        SupervisorState.STOPPING,
        SupervisorState.CRASHED,
    },
    SupervisorState.RESTARTING: {SupervisorState.RUNNING, SupervisorState.CRASHED},
    SupervisorState.STOPPING: {SupervisorState.STOPPED},
    SupervisorState.STOPPED: {SupervisorState.STARTING},
    SupervisorState.CRASHED: {SupervisorState.STARTING},
}


def valid_transition(
    from_: SupervisorState | None, to_: SupervisorState
) -> bool:
    return to_ in _VALID_TRANSITIONS.get(from_, set())
```

Make sure `from enum import Enum` lives at the top of the file with the other imports — move it there if your edit dropped it lower:

```python
from __future__ import annotations

import time
from collections import deque
from enum import Enum
```

(Remove the duplicate `from enum import Enum` lower if you accidentally created one.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/tray/test_supervisor_state.py -v 2>&1 | tail -10
```

Expected: `16 passed` (1 + 15 parametrized).

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/supervisor.py tests/tray/test_supervisor_state.py && git commit -m "feat(tray): SupervisorState enum + valid_transition predicate

State machine: Starting → Running → Restarting/Stopping/Crashed →
Stopped/Crashed. Manual restart from Stopped/Crashed allowed.
valid_transition() centralises legal transitions for the Supervisor
class to enforce in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Supervisor subprocess lifecycle (start / stop / restart)

**Files:**
- Modify: `claude_mnemos/tray/supervisor.py` (add Supervisor class)
- Create: `tests/tray/test_supervisor_subprocess.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tray/test_supervisor_subprocess.py`:
```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_mnemos.tray.supervisor import Supervisor, SupervisorState


@pytest.fixture
def fake_pid_file(tmp_path: Path) -> Path:
    return tmp_path / "daemon.pid"


def _make_popen(pid: int = 4242, alive: bool = True) -> MagicMock:
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = None if alive else 0
    return proc


def test_start_spawns_subprocess_and_transitions_to_starting(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    fake_proc = _make_popen()
    with patch("claude_mnemos.tray.supervisor.subprocess.Popen", return_value=fake_proc) as popen, \
         patch.object(sv, "_is_existing_daemon_running", return_value=False):
        sv.start()
    assert sv.state == SupervisorState.STARTING
    assert sv.daemon_pid == 4242
    assert sv._spawned is True
    popen.assert_called_once()
    cmd = popen.call_args[0][0]
    assert "claude_mnemos.daemon" in " ".join(cmd)
    assert "foreground" in cmd
    assert "--all" in cmd


def test_start_adopts_existing_daemon_without_spawning(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    with patch("claude_mnemos.tray.supervisor.subprocess.Popen") as popen, \
         patch.object(sv, "_is_existing_daemon_running", return_value=9999):
        sv.start()
    assert sv.state == SupervisorState.RUNNING  # adopted = already up
    assert sv.daemon_pid == 9999
    assert sv._spawned is False
    popen.assert_not_called()


def test_mark_running_transitions_starting_to_running(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv.state = SupervisorState.STARTING
    sv.mark_running()
    assert sv.state == SupervisorState.RUNNING


def test_stop_terminates_spawned_subprocess(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    fake_proc = _make_popen()
    sv._proc = fake_proc
    sv._spawned = True
    sv.state = SupervisorState.RUNNING

    sv.stop(grace_seconds=0.01)
    assert sv.state == SupervisorState.STOPPED
    fake_proc.terminate.assert_called_once()


def test_stop_does_not_kill_adopted_daemon(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    fake_proc = _make_popen()
    sv._proc = fake_proc
    sv._spawned = False  # adopted
    sv.state = SupervisorState.RUNNING

    sv.stop(grace_seconds=0.01)
    assert sv.state == SupervisorState.STOPPED
    fake_proc.terminate.assert_not_called()
    fake_proc.kill.assert_not_called()


def test_stop_kills_after_grace_timeout(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    fake_proc = _make_popen()
    fake_proc.wait.side_effect = __import__("subprocess").TimeoutExpired(cmd="x", timeout=0.01)
    sv._proc = fake_proc
    sv._spawned = True
    sv.state = SupervisorState.RUNNING

    sv.stop(grace_seconds=0.01)
    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_called_once()


def test_restart_only_works_when_spawned(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = _make_popen()
    sv._spawned = False  # adopted
    sv.state = SupervisorState.RUNNING

    with pytest.raises(RuntimeError, match="adopted"):
        sv.restart()


def test_restart_spawns_new_subprocess(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = _make_popen()
    sv._spawned = True
    sv.state = SupervisorState.RUNNING

    new_proc = _make_popen(pid=5555)
    with patch("claude_mnemos.tray.supervisor.subprocess.Popen", return_value=new_proc):
        sv.restart()
    assert sv.daemon_pid == 5555
    assert sv.state == SupervisorState.STARTING
    # Crash counter must reset on manual restart
    assert sv.limiter.crash_count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/tray/test_supervisor_subprocess.py -v 2>&1 | tail -10
```

Expected: ImportError on `Supervisor`.

- [ ] **Step 3: Implement Supervisor class**

Append to `claude_mnemos/tray/supervisor.py` (after `valid_transition`):

```python


import logging
import os
import subprocess
import sys
from pathlib import Path

from claude_mnemos.daemon.lockfile import is_daemon_running

logger = logging.getLogger(__name__)


class Supervisor:
    """Owns daemon subprocess (or adopts an existing one) + state machine.

    Spawned mode: ``self._proc`` is the Popen object we control. ``stop`` and
    ``restart`` terminate it.

    Adopted mode: external process already running per ``daemon_pid_file``.
    ``stop`` only deregisters ourselves; we MUST NOT kill it.
    """

    def __init__(
        self,
        *,
        daemon_pid_file: Path,
        log_path: Path | None = None,
    ) -> None:
        self.daemon_pid_file = daemon_pid_file
        self.log_path = log_path
        self.state: SupervisorState | None = None
        self.daemon_pid: int | None = None
        self.limiter = RestartLimiter()
        self._proc: subprocess.Popen | None = None
        self._spawned: bool = False
        self._log_fh = None

    # ── liveness helper, mockable ───────────────────────────────
    def _is_existing_daemon_running(self) -> int | None:
        return is_daemon_running(self.daemon_pid_file)

    # ── state transitions ───────────────────────────────────────
    def _transition(self, new: SupervisorState) -> None:
        if not valid_transition(self.state, new):
            raise RuntimeError(f"invalid transition {self.state} → {new}")
        logger.info("[supervisor] state %s → %s", self.state, new)
        self.state = new

    def mark_running(self) -> None:
        self._transition(SupervisorState.RUNNING)

    # ── subprocess lifecycle ────────────────────────────────────
    def _spawn_daemon(self) -> subprocess.Popen:
        cmd = [sys.executable, "-m", "claude_mnemos.daemon", "foreground", "--all"]
        creationflags = 0
        if sys.platform == "win32":
            # CREATE_NEW_PROCESS_GROUP so we can send CTRL_BREAK_EVENT later;
            # don't use DETACHED_PROCESS — we want stdout/stderr handles.
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_fh = self.log_path.open("a", encoding="utf-8", buffering=1)
            stdout = self._log_fh
            stderr = self._log_fh
        else:
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL

        proc = subprocess.Popen(
            cmd,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
        return proc

    def start(self) -> None:
        existing = self._is_existing_daemon_running()
        if existing:
            self._proc = None
            self._spawned = False
            self.daemon_pid = existing
            self._transition(SupervisorState.STARTING)
            self._transition(SupervisorState.RUNNING)
            return

        self._proc = self._spawn_daemon()
        self._spawned = True
        self.daemon_pid = self._proc.pid
        self._transition(SupervisorState.STARTING)

    def stop(self, *, grace_seconds: float = 10.0) -> None:
        self._transition(SupervisorState.STOPPING)
        if self._spawned and self._proc is not None:
            try:
                self._proc.terminate()
            except (ProcessLookupError, OSError) as exc:
                logger.warning("[supervisor] terminate() raised %r", exc)
            try:
                self._proc.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                logger.warning("[supervisor] grace expired, killing pid=%s", self._proc.pid)
                with contextlib_suppress(OSError):
                    self._proc.kill()
        self._close_log_fh()
        self._transition(SupervisorState.STOPPED)

    def restart(self, *, grace_seconds: float = 5.0) -> None:
        if not self._spawned:
            raise RuntimeError("cannot restart adopted daemon")
        self._transition(SupervisorState.RESTARTING)
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            except (ProcessLookupError, OSError):
                pass
        self._close_log_fh()
        self._proc = self._spawn_daemon()
        self.daemon_pid = self._proc.pid
        self.limiter.reset()
        # Restarting → Starting needs a separate path; do it directly,
        # bypassing the normal Restarting → Running edge until /health succeeds.
        self.state = SupervisorState.STARTING
        logger.info("[supervisor] restart spawned pid=%s, state=Starting", self._proc.pid)

    def _close_log_fh(self) -> None:
        if self._log_fh:
            try:
                self._log_fh.close()
            except Exception:  # noqa: BLE001
                pass
            self._log_fh = None


import contextlib as contextlib_suppress_ctx

contextlib_suppress = contextlib_suppress_ctx.suppress
```

The `contextlib_suppress` rebinding at the bottom dodges name-shadowing inside `stop()`; a cleaner alternative is `import contextlib` at the top and use `contextlib.suppress(...)` inline. If the file already imports `contextlib`, prefer that.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/tray/test_supervisor_subprocess.py -v 2>&1 | tail -15
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/supervisor.py tests/tray/test_supervisor_subprocess.py && git commit -m "feat(tray): Supervisor subprocess lifecycle + state machine glue

start() spawns daemon (or adopts existing via PID-file), stop() honours
spawned/adopted distinction (never kills adopted), restart() refuses on
adopted and resets crash counter on manual trigger. Logs route to
~/.claude-mnemos/daemon.log.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Supervisor crash-detection loop + adopt + health polling

**Files:**
- Modify: `claude_mnemos/tray/supervisor.py` (add tick + health helpers)
- Create: `tests/tray/test_supervisor_adopt_and_loop.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tray/test_supervisor_adopt_and_loop.py`:
```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_mnemos.tray.supervisor import (
    HealthSnapshot,
    Supervisor,
    SupervisorState,
)


@pytest.fixture
def fake_pid_file(tmp_path: Path) -> Path:
    return tmp_path / "daemon.pid"


def test_health_snapshot_defaults() -> None:
    snap = HealthSnapshot(reachable=False)
    assert snap.reachable is False
    assert snap.projects_mounted == 0
    assert snap.uptime_seconds is None


def test_tick_promotes_starting_to_running_on_health_ok(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = MagicMock(poll=MagicMock(return_value=None), pid=1)
    sv._spawned = True
    sv.state = SupervisorState.STARTING
    with patch.object(
        sv, "_check_health",
        return_value=HealthSnapshot(reachable=True, projects_mounted=2, uptime_seconds=5.0),
    ):
        sv.tick(now=10.0)
    assert sv.state == SupervisorState.RUNNING
    assert sv.last_health.projects_mounted == 2


def test_tick_detects_subprocess_crash_and_records(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = MagicMock(poll=MagicMock(return_value=1), pid=1)
    sv._spawned = True
    sv.state = SupervisorState.RUNNING
    with patch.object(sv, "_spawn_daemon") as spawn:
        spawn.return_value = MagicMock(poll=MagicMock(return_value=None), pid=2)
        sv.tick(now=100.0)
    # First crash → restart attempted, state=Starting
    assert sv.limiter.crash_count(now=100.0) == 1
    assert sv.state == SupervisorState.STARTING


def test_tick_does_not_treat_user_stop_as_crash(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = MagicMock(poll=MagicMock(return_value=0), pid=1)
    sv._spawned = True
    sv.state = SupervisorState.STOPPING  # user-initiated
    with patch.object(sv, "_spawn_daemon") as spawn:
        sv.tick(now=100.0)
        spawn.assert_not_called()
    assert sv.limiter.crash_count(now=100.0) == 0


def test_tick_blocks_restart_after_threshold_and_enters_crashed(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = MagicMock(poll=MagicMock(return_value=1), pid=1)
    sv._spawned = True
    sv.state = SupervisorState.RUNNING

    # Pre-load 3 prior crashes
    sv.limiter.record_crash(now=0.0)
    sv.limiter.record_crash(now=1.0)
    sv.limiter.record_crash(now=2.0)
    with patch.object(sv, "_spawn_daemon") as spawn:
        sv.tick(now=3.0)  # 4th crash exceeds threshold
        spawn.assert_not_called()
    assert sv.state == SupervisorState.CRASHED
    assert sv.limiter.crash_count(now=3.0) == 4


def test_tick_does_nothing_for_adopted_daemon_when_pid_alive(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = None
    sv._spawned = False
    sv.state = SupervisorState.RUNNING
    sv.daemon_pid = 9999
    with patch("claude_mnemos.tray.supervisor.psutil") as psutil_mod, \
         patch.object(sv, "_check_health", return_value=HealthSnapshot(reachable=True, projects_mounted=1)):
        psutil_mod.pid_exists.return_value = True
        sv.tick(now=1.0)
    assert sv.state == SupervisorState.RUNNING


def test_tick_marks_adopted_daemon_crashed_when_pid_gone(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = None
    sv._spawned = False
    sv.state = SupervisorState.RUNNING
    sv.daemon_pid = 9999
    with patch("claude_mnemos.tray.supervisor.psutil") as psutil_mod:
        psutil_mod.pid_exists.return_value = False
        sv.tick(now=1.0)
    # Adopted daemon disappeared — we don't auto-respawn (we don't own it).
    assert sv.state == SupervisorState.CRASHED
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/tray/test_supervisor_adopt_and_loop.py -v 2>&1 | tail -10
```

Expected: ImportError on `HealthSnapshot`.

- [ ] **Step 3: Implement HealthSnapshot, _check_health, tick**

Append to `claude_mnemos/tray/supervisor.py`:

```python


from dataclasses import dataclass, field

import httpx
import psutil


@dataclass
class HealthSnapshot:
    reachable: bool
    projects_mounted: int = 0
    uptime_seconds: float | None = None


def _default_health_url() -> str:
    return "http://localhost:5757/health"


# Patch back the Supervisor class with new methods. Add these as methods inside
# the existing `class Supervisor:` block (NOT at module level). Concretely:
# 1) Add `last_health: HealthSnapshot | None = None` as instance attr in __init__
# 2) Add the methods below as `def _check_health(self) -> HealthSnapshot:` etc.

# The helper text below is informational; place all of it inside class Supervisor.
```

The block above is documentation for the editor. The actual edit: open `class Supervisor:` and add the new pieces. Insert into `__init__` (after `self._log_fh = None`):

```python
        self.last_health: HealthSnapshot | None = None
        self.health_url = _default_health_url()
        self._http: httpx.Client | None = None
```

Add new methods inside `class Supervisor:` (just before `_close_log_fh`):

```python
    def _http_client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=2.0)
        return self._http

    def _check_health(self) -> HealthSnapshot:
        try:
            resp = self._http_client().get(self.health_url)
            if resp.status_code != 200:
                return HealthSnapshot(reachable=False)
            data = resp.json()
            return HealthSnapshot(
                reachable=True,
                projects_mounted=int(data.get("projects_mounted", 0)),
                uptime_seconds=data.get("uptime_seconds"),
            )
        except (httpx.HTTPError, ValueError):
            return HealthSnapshot(reachable=False)

    def _spawned_daemon_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _adopted_daemon_alive(self) -> bool:
        return self.daemon_pid is not None and psutil.pid_exists(self.daemon_pid)

    def tick(self, *, now: float | None = None) -> None:
        """Single iteration of the supervisor loop.

        Called periodically (every ~5s). Polls subprocess liveness and
        /health, drives state transitions.
        """
        now = time.monotonic() if now is None else now

        # User-initiated Stopping → don't react to subprocess exit
        if self.state in (SupervisorState.STOPPING, SupervisorState.STOPPED):
            return
        if self.state == SupervisorState.CRASHED:
            return  # manual restart only

        if self._spawned:
            if not self._spawned_daemon_alive():
                self._handle_crash(now)
                return
        else:
            if not self._adopted_daemon_alive():
                logger.warning(
                    "[supervisor] adopted daemon pid=%s gone — entering Crashed",
                    self.daemon_pid,
                )
                self.state = SupervisorState.CRASHED
                return

        snap = self._check_health()
        self.last_health = snap

        if self.state == SupervisorState.STARTING and snap.reachable:
            self._transition(SupervisorState.RUNNING)

    def _handle_crash(self, now: float) -> None:
        self.limiter.record_crash(now=now)
        if not self.limiter.should_restart(now=now):
            logger.error(
                "[supervisor] crash %d/%d in window — entering Crashed",
                self.limiter.crash_count(now=now), self.limiter.max_crashes,
            )
            self.state = SupervisorState.CRASHED
            return
        backoff = self.limiter.next_backoff_seconds()
        logger.warning(
            "[supervisor] daemon crashed, backoff %.1fs (count=%d)",
            backoff, self.limiter.crash_count(now=now),
        )
        time.sleep(backoff)
        self._close_log_fh()
        self._proc = self._spawn_daemon()
        self.daemon_pid = self._proc.pid
        self.state = SupervisorState.STARTING
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/tray/ -v 2>&1 | tail -20
```

Expected: all tests in `tests/tray/` pass (RestartLimiter + Supervisor state + Supervisor subprocess + adopt/loop = 27+ tests).

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/supervisor.py tests/tray/test_supervisor_adopt_and_loop.py && git commit -m "feat(tray): Supervisor.tick crash detection + /health polling + adopted

Periodic tick polls subprocess liveness via Popen.poll() (spawned) or
psutil.pid_exists (adopted), then GET /health for projects count. Drives
Starting→Running transition on first 200 response. Crash detection:
spawned exits → record_crash + backoff + respawn; adopted dies → enter
Crashed (we don't auto-respawn what we don't own).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Tray icon module (pystray, marked manual)

**Files:**
- Create: `claude_mnemos/tray/icon.py`
- Create: `tests/tray/test_icon.py`

- [ ] **Step 1: Write the failing test**

Create `tests/tray/test_icon.py`:
```python
"""Tray icon tests — tagged @pytest.mark.manual since pystray needs a display."""

from __future__ import annotations

import os
import sys
import pytest

pytestmark = pytest.mark.manual

skip_in_ci = pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="pystray requires a display; not available in headless CI",
)


@skip_in_ci
def test_tray_app_constructs_without_running() -> None:
    from claude_mnemos.tray.icon import TrayApp

    app = TrayApp(supervisor=None, dashboard_url="http://localhost:5757/")
    # Don't call .run() — that blocks on Win32 message loop
    assert app.dashboard_url == "http://localhost:5757/"
    assert app.icon is not None
```

Add a marker to `pyproject.toml` `[tool.pytest.ini_options]` `markers` list. Modify the existing `markers = [...]`:

```toml
markers = [
    "slow: tests that hit external services or take >1s",
    "manual: tests requiring display/network/external setup; skipped in CI",
]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/tray/test_icon.py -v 2>&1 | tail -10
```

Expected: ModuleNotFoundError on `claude_mnemos.tray.icon`.

- [ ] **Step 3: Implement TrayApp**

Create `claude_mnemos/tray/icon.py`:
```python
"""Pystray-backed system tray icon.

Not unit-tested in CI (pystray requires a display). Manual smoke checklist
lives in docs/plans/2026-04-29-tray-autostart-design.md §12.
"""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

import pystray
from PIL import Image

from claude_mnemos.tray.supervisor import Supervisor, SupervisorState

logger = logging.getLogger(__name__)

ASSETS = Path(__file__).parent / "assets"


def _load_image(name: str) -> Image.Image:
    path = ASSETS / name
    return Image.open(str(path))


class TrayApp:
    """Pystray icon + menu + simple repaint loop driven by the supervisor."""

    def __init__(
        self,
        *,
        supervisor: Supervisor | None,
        dashboard_url: str = "http://localhost:5757/",
    ) -> None:
        self.supervisor = supervisor
        self.dashboard_url = dashboard_url
        self.icon = pystray.Icon(
            "mnemos",
            icon=_load_image("icon-running.png"),
            title="Mnemos",
            menu=self._build_menu(),
        )

    # ── menu actions ────────────────────────────────────────────
    def _open_dashboard(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        webbrowser.open(self.dashboard_url)

    def _restart_daemon(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        if self.supervisor is None:
            return
        try:
            self.supervisor.restart()
        except RuntimeError as exc:
            logger.warning("restart failed: %s", exc)

    def _show_logs(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        log = Path.home() / ".claude-mnemos" / "daemon.log"
        if not log.is_file():
            return
        import os
        import subprocess
        import sys

        if sys.platform == "win32":
            os.startfile(str(log))  # noqa: SIM115
        elif sys.platform == "darwin":
            subprocess.run(["open", str(log)], check=False)

    def _quit(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        if self.supervisor is not None:
            self.supervisor.stop()
        self.icon.stop()

    # ── menu / state predicates ─────────────────────────────────
    def _is_running(self) -> bool:
        if self.supervisor is None:
            return False
        return self.supervisor.state == SupervisorState.RUNNING

    def _is_spawned(self) -> bool:
        return self.supervisor is not None and self.supervisor._spawned

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Open dashboard", self._open_dashboard, default=True,
                             enabled=lambda _: self._is_running()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart daemon", self._restart_daemon,
                             enabled=lambda _: self._is_spawned()),
            pystray.MenuItem("Show logs", self._show_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    # ── repaint ─────────────────────────────────────────────────
    def repaint(self) -> None:
        if self.supervisor is None:
            self.icon.title = "Mnemos · no supervisor"
            return
        st = self.supervisor.state
        if st in (SupervisorState.RUNNING, SupervisorState.STARTING, SupervisorState.RESTARTING):
            self.icon.icon = _load_image("icon-running.png")
        else:
            self.icon.icon = _load_image("icon-stopped.png")
        snap = self.supervisor.last_health
        if snap and snap.reachable:
            mounted = snap.projects_mounted
            self.icon.title = f"Mnemos · {mounted} project{'s' if mounted != 1 else ''} mounted"
        else:
            self.icon.title = f"Mnemos · {st.value if st else 'unknown'}"

    def run(self) -> None:
        self.icon.run()
```

- [ ] **Step 4: Skip test in CI / mark manual**

```bash
python -m pytest tests/tray/test_icon.py -v 2>&1 | tail -5
```

Expected: `1 deselected` or `1 skipped` (depending on whether pystray imports cleanly without display). The test is `pytestmark = pytest.mark.manual` so it is deselected by default unless explicitly invoked.

Try with the marker explicitly:
```bash
python -m pytest tests/tray/test_icon.py -v -m manual 2>&1 | tail -5
```

This runs it. May fail if pystray fails to construct in current environment — that's fine, tag is `manual` for a reason.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/icon.py tests/tray/test_icon.py pyproject.toml && git commit -m "feat(tray): TrayApp pystray icon + menu

Menu: Open dashboard (default action) / Restart daemon (only when
spawned) / Show logs / Quit. Icon and tooltip repaint based on
Supervisor.state and last health. Tests marked @pytest.mark.manual
since pystray needs a display.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Tray entrypoint + main loop

**Files:**
- Modify: `claude_mnemos/tray/__main__.py`

- [ ] **Step 1: Write the failing test**

Create `tests/tray/test_main.py`:
```python
from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest


def test_main_run_subcommand_starts_supervisor_and_tray() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    fake_sv = MagicMock()
    fake_app = MagicMock()
    with patch.object(tray_main, "Supervisor", return_value=fake_sv), \
         patch.object(tray_main, "TrayApp", return_value=fake_app), \
         patch.object(tray_main, "_acquire_tray_lock", return_value=True), \
         patch.object(tray_main, "_release_tray_lock"), \
         patch.object(sys, "argv", ["mnemos-tray", "run"]):
        rc = tray_main.main()
    assert rc == 0
    fake_sv.start.assert_called_once()
    fake_app.run.assert_called_once()


def test_main_install_subcommand_calls_autostart() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    fake_mgr = MagicMock()
    with patch.object(tray_main, "get_autostart_manager", return_value=fake_mgr), \
         patch.object(sys, "argv", ["mnemos-tray", "install"]):
        rc = tray_main.main()
    assert rc == 0
    fake_mgr.install.assert_called_once()


def test_main_uninstall_subcommand_calls_autostart() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    fake_mgr = MagicMock()
    with patch.object(tray_main, "get_autostart_manager", return_value=fake_mgr), \
         patch.object(sys, "argv", ["mnemos-tray", "uninstall"]):
        rc = tray_main.main()
    assert rc == 0
    fake_mgr.uninstall.assert_called_once()


def test_main_status_subcommand_prints_json() -> None:
    from claude_mnemos.tray import __main__ as tray_main
    from claude_mnemos.tray.platform.base import AutostartStatus

    fake_mgr = MagicMock()
    fake_mgr.status.return_value = AutostartStatus(installed=True, path="/x")
    with patch.object(tray_main, "get_autostart_manager", return_value=fake_mgr), \
         patch.object(sys, "argv", ["mnemos-tray", "status"]):
        rc = tray_main.main()
    assert rc == 0  # printed to stdout; capture not strictly needed for this test


def test_main_run_refuses_when_lock_held() -> None:
    from claude_mnemos.tray import __main__ as tray_main

    with patch.object(tray_main, "_acquire_tray_lock", return_value=False), \
         patch.object(sys, "argv", ["mnemos-tray", "run"]):
        rc = tray_main.main()
    assert rc == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/tray/test_main.py -v 2>&1 | tail -10
```

Expected: AttributeError on `Supervisor`/`TrayApp`/`_acquire_tray_lock` because `__main__.py` is still a placeholder.

- [ ] **Step 3: Implement main**

Replace `claude_mnemos/tray/__main__.py`:
```python
"""Entrypoint for `mnemos-tray` and `python -m claude_mnemos.tray`.

Subcommands:
    run         — foreground supervisor + tray icon (used by autostart entry)
    install     — register autostart, then spawn detached `mnemos-tray run`
    uninstall   — unregister autostart (does not kill running tray)
    status      — print human-readable autostart + tray + daemon state
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from claude_mnemos.daemon.lockfile import is_daemon_running
from claude_mnemos.tray.icon import TrayApp
from claude_mnemos.tray.platform import get_autostart_manager, platform_label
from claude_mnemos.tray.supervisor import Supervisor

LOG_DIR = Path.home() / ".claude-mnemos"
TRAY_PID_FILE = LOG_DIR / "tray.pid"
DAEMON_PID_FILE = LOG_DIR / "daemon.pid"
DAEMON_LOG = LOG_DIR / "daemon.log"
SUPERVISOR_LOG = LOG_DIR / "supervisor.log"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(SUPERVISOR_LOG),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _acquire_tray_lock() -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if TRAY_PID_FILE.is_file():
        try:
            old = int(TRAY_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            old = -1
        if old > 0 and psutil.pid_exists(old):
            print(f"another tray running, PID {old}", file=sys.stderr)
            return False
        TRAY_PID_FILE.unlink(missing_ok=True)
    TRAY_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_tray_lock() -> None:
    TRAY_PID_FILE.unlink(missing_ok=True)


def _resolve_target_exe() -> str:
    found = shutil.which("mnemos-tray")
    if found:
        return found
    # Fallback: invoke via python -m
    return f"{sys.executable} -m claude_mnemos.tray"


def _cmd_run() -> int:
    if not _acquire_tray_lock():
        return 1
    sv = Supervisor(daemon_pid_file=DAEMON_PID_FILE, log_path=DAEMON_LOG)
    sv.start()
    app = TrayApp(supervisor=sv)

    def _ticker() -> None:
        while True:
            time.sleep(5.0)
            try:
                sv.tick()
                app.repaint()
            except Exception:  # noqa: BLE001
                logging.exception("[supervisor] tick failed")

    t = threading.Thread(target=_ticker, daemon=True)
    t.start()

    try:
        app.run()  # blocks until Quit
    finally:
        _release_tray_lock()
    return 0


def _cmd_install() -> int:
    mgr = get_autostart_manager(target_exe=_resolve_target_exe())
    mgr.install()
    print(f"Auto-start installed ({platform_label()}).")
    # Detached spawn of `mnemos-tray run` if no tray currently running
    if not (TRAY_PID_FILE.is_file() and psutil.pid_exists(int(TRAY_PID_FILE.read_text().strip() or 0))):
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [sys.executable, "-m", "claude_mnemos.tray", "run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
            start_new_session=(sys.platform != "win32"),
        )
        print("Tray started.")
    return 0


def _cmd_uninstall() -> int:
    mgr = get_autostart_manager(target_exe=_resolve_target_exe())
    mgr.uninstall()
    print(f"Auto-start removed ({platform_label()}).")
    return 0


def _cmd_status() -> int:
    mgr = get_autostart_manager(target_exe=_resolve_target_exe())
    s = mgr.status()
    tray_pid = None
    if TRAY_PID_FILE.is_file():
        try:
            cand = int(TRAY_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            cand = None
        if cand and psutil.pid_exists(cand):
            tray_pid = cand
    out = {
        "platform": platform_label(),
        "autostart_enabled": s.installed,
        "autostart_path": s.path,
        "tray_running": tray_pid is not None,
        "tray_pid": tray_pid,
        "daemon_pid": is_daemon_running(DAEMON_PID_FILE),
    }
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="mnemos-tray")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("install")
    sub.add_parser("uninstall")
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd == "run":
        return _cmd_run()
    if args.cmd == "install":
        return _cmd_install()
    if args.cmd == "uninstall":
        return _cmd_uninstall()
    if args.cmd == "status":
        return _cmd_status()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/tray/test_main.py -v 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/tray/__main__.py tests/tray/test_main.py && git commit -m "feat(tray): mnemos-tray entrypoint with run/install/uninstall/status

run holds tray.pid lock, spawns Supervisor + TrayApp + tick thread.
install registers autostart and detached-spawns 'run' if not running.
uninstall removes autostart only (does not kill tray).
status prints JSON with platform, autostart, tray PID, daemon PID.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Wire `mnemos tray` subcommand into main CLI

**Files:**
- Modify: `claude_mnemos/cli.py` (add tray subcommand dispatcher)
- Create: `claude_mnemos/cli_tray.py` (thin wrapper that delegates to tray.__main__)
- Create: `tests/test_cli_tray.py`

- [ ] **Step 1: Inspect existing cli.py to find subcommand registration pattern**

Open `claude_mnemos/cli.py` and locate the section that registers existing subcommands (look for `daemon_sub.add_parser` or similar). Note the surrounding pattern. Modifications must follow the same convention.

- [ ] **Step 2: Write the failing test**

Create `tests/test_cli_tray.py`:
```python
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


def test_mnemos_tray_run_routes_to_tray_main() -> None:
    """`mnemos tray run` should delegate to claude_mnemos.tray.__main__:main."""
    import claude_mnemos.cli as cli

    with patch("claude_mnemos.cli_tray.tray_main.main", return_value=0) as fake_main, \
         patch.object(sys, "argv", ["mnemos", "tray", "run"]):
        rc = cli.main()
    assert rc == 0
    fake_main.assert_called_once()


@pytest.mark.parametrize("subcmd", ["install", "uninstall", "status"])
def test_mnemos_tray_subcommands_route(subcmd: str) -> None:
    import claude_mnemos.cli as cli

    with patch("claude_mnemos.cli_tray.tray_main.main", return_value=0) as fake_main, \
         patch.object(sys, "argv", ["mnemos", "tray", subcmd]):
        rc = cli.main()
    assert rc == 0
    fake_main.assert_called_once()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m pytest tests/test_cli_tray.py -v 2>&1 | tail -10
```

Expected: AttributeError or ArgumentError because `tray` subcommand not registered yet.

- [ ] **Step 4: Implement cli_tray.py + wire it in**

Create `claude_mnemos/cli_tray.py`:
```python
"""`mnemos tray ...` subcommand — thin shim over claude_mnemos.tray.__main__.

Registered by claude_mnemos.cli.main(). The actual logic lives in the tray
module so the entrypoint `mnemos-tray` and the CLI subcommand share code.
"""

from __future__ import annotations

import sys

from claude_mnemos.tray import __main__ as tray_main


def run(argv: list[str]) -> int:
    """Replace argv[0] so argparse inside tray_main sees correct prog name."""
    saved = sys.argv
    sys.argv = ["mnemos-tray", *argv]
    try:
        return tray_main.main()
    finally:
        sys.argv = saved
```

Modify `claude_mnemos/cli.py`. Find the subparsers registration (where `daemon_sub` etc. are added) and add a `tray` parser. Open the file and locate the subparsers block; add the following entry alongside:

```python
    # Existing pattern probably looks like:
    # subparsers = parser.add_subparsers(dest="command")
    # daemon_p = subparsers.add_parser("daemon", ...)
    # ...
    #
    # Add:
    tray_p = subparsers.add_parser("tray", help="Tray icon + autostart")
    tray_p.add_argument("tray_cmd", choices=["run", "install", "uninstall", "status"])
```

Then in the dispatch section (where `if args.command == "daemon": ...` etc.), add:

```python
    if args.command == "tray":
        from claude_mnemos.cli_tray import run as tray_run
        return tray_run([args.tray_cmd])
```

If the existing CLI uses a slightly different subcommand pattern (e.g. nested subparsers with their own dispatch), match that convention instead. The contract tests in `test_cli_tray.py` only require that `mnemos tray <X>` ends up calling `claude_mnemos.tray.__main__:main`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_cli_tray.py -v 2>&1 | tail -10
```

Expected: `4 passed` (1 + 3 parametrized).

Run the broader CLI test suite to ensure no regressions:
```bash
python -m pytest tests/test_cli*.py -v 2>&1 | tail -10
```

Expected: all pre-existing CLI tests still green.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/cli.py claude_mnemos/cli_tray.py tests/test_cli_tray.py && git commit -m "feat(cli): mnemos tray {run,install,uninstall,status} subcommand

Thin shim cli_tray.run delegates to claude_mnemos.tray.__main__:main with
adjusted argv so argparse sees prog='mnemos-tray'. Same code path as the
mnemos-tray entrypoint.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: HTTP API routes (/tray/install, /uninstall, /status)

**Files:**
- Create: `claude_mnemos/daemon/routes/tray.py`
- Modify: `claude_mnemos/daemon/app.py` (mount router)
- Create: `tests/daemon/routes/test_tray.py`

- [ ] **Step 1: Inspect daemon/app.py to find router registration pattern**

```bash
grep -n "include_router\|APIRouter" /d/code/claude-mnemos/claude_mnemos/daemon/app.py | head
```

Note the pattern. New router must follow it.

- [ ] **Step 2: Write the failing test**

Create `tests/daemon/routes/test_tray.py`:
```python
from __future__ import annotations

from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.daemon.config import DaemonConfig


def _make_client() -> TestClient:
    daemon = MnemosDaemon(DaemonConfig(boot_filter=None))
    return TestClient(daemon.app)


def test_get_tray_status_returns_platform_info() -> None:
    client = _make_client()
    fake_status = MagicMock(installed=False, path="/tmp/x")
    fake_mgr = MagicMock(status=MagicMock(return_value=fake_status))
    with patch("claude_mnemos.daemon.routes.tray.get_autostart_manager", return_value=fake_mgr), \
         patch("claude_mnemos.daemon.routes.tray.platform_label", return_value="windows"):
        resp = client.get("/tray/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "windows"
    assert body["autostart_enabled"] is False


def test_post_tray_install_runs_subprocess() -> None:
    client = _make_client()
    fake_completed = MagicMock(returncode=0, stderr="")
    with patch("claude_mnemos.daemon.routes.tray.subprocess.run", return_value=fake_completed) as run:
        resp = client.post("/tray/install")
    assert resp.status_code == 200
    assert resp.json() == {"installed": True}
    cmd = run.call_args[0][0]
    assert "mnemos" in cmd[0] or cmd[0].endswith("python") or "python" in cmd[0]
    assert "tray" in cmd
    assert "install" in cmd


def test_post_tray_install_returns_500_on_failure() -> None:
    client = _make_client()
    fake_completed = MagicMock(returncode=1, stderr="powershell exit 1: nope")
    with patch("claude_mnemos.daemon.routes.tray.subprocess.run", return_value=fake_completed):
        resp = client.post("/tray/install")
    assert resp.status_code == 500
    assert "powershell" in resp.json()["detail"]


def test_post_tray_uninstall_runs_subprocess() -> None:
    client = _make_client()
    fake_completed = MagicMock(returncode=0, stderr="")
    with patch("claude_mnemos.daemon.routes.tray.subprocess.run", return_value=fake_completed):
        resp = client.post("/tray/uninstall")
    assert resp.status_code == 200
    assert resp.json() == {"installed": False}


def test_post_tray_install_returns_501_on_unsupported_platform() -> None:
    client = _make_client()
    with patch("claude_mnemos.daemon.routes.tray.platform_label", return_value="unsupported"):
        resp = client.post("/tray/install")
    assert resp.status_code == 501
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m pytest tests/daemon/routes/test_tray.py -v 2>&1 | tail -10
```

Expected: 404 / ImportError on `claude_mnemos.daemon.routes.tray`.

- [ ] **Step 4: Implement tray router**

Create `claude_mnemos/daemon/routes/tray.py`:
```python
"""Tray + autostart HTTP API.

POST /tray/install     — exec `mnemos tray install`
POST /tray/uninstall   — exec `mnemos tray uninstall`
GET  /tray/status      — autostart status + tray PID + daemon PID
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import psutil
from fastapi import APIRouter, HTTPException

from claude_mnemos.daemon.lockfile import is_daemon_running
from claude_mnemos.tray.platform import (
    get_autostart_manager,
    platform_label,
)
from claude_mnemos.tray.__main__ import (
    DAEMON_PID_FILE,
    TRAY_PID_FILE,
)

router = APIRouter(prefix="/tray", tags=["tray"])


def _resolve_target_exe() -> str:
    found = shutil.which("mnemos-tray")
    if found:
        return found
    return f"{sys.executable} -m claude_mnemos.tray"


def _exec_tray(action: str) -> None:
    cmd = [sys.executable, "-m", "claude_mnemos.tray", action]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.stderr or result.stdout or "tray subprocess failed").strip(),
        )


@router.post("/install")
def install() -> dict[str, bool]:
    if platform_label() not in ("windows", "macos"):
        raise HTTPException(status_code=501, detail="Autostart not supported on this platform")
    _exec_tray("install")
    return {"installed": True}


@router.post("/uninstall")
def uninstall() -> dict[str, bool]:
    if platform_label() not in ("windows", "macos"):
        raise HTTPException(status_code=501, detail="Autostart not supported on this platform")
    _exec_tray("uninstall")
    return {"installed": False}


@router.get("/status")
def status() -> dict[str, object]:
    mgr = get_autostart_manager(target_exe=_resolve_target_exe())
    s = mgr.status()
    tray_pid = None
    if TRAY_PID_FILE.is_file():
        try:
            cand = int(TRAY_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            cand = None
        if cand and psutil.pid_exists(cand):
            tray_pid = cand
    return {
        "platform": platform_label(),
        "autostart_enabled": s.installed,
        "autostart_path": s.path,
        "tray_running": tray_pid is not None,
        "tray_pid": tray_pid,
        "daemon_pid": is_daemon_running(DAEMON_PID_FILE),
    }
```

Mount router in `claude_mnemos/daemon/app.py`. Find existing `app.include_router(...)` calls and add:

```python
from claude_mnemos.daemon.routes import tray as tray_routes
app.include_router(tray_routes.router)
```

at the same place where other routers are included.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/daemon/routes/test_tray.py -v 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/tray.py claude_mnemos/daemon/app.py tests/daemon/routes/test_tray.py && git commit -m "feat(daemon): /tray/{install,uninstall,status} routes

Install/uninstall execute subprocess 'python -m claude_mnemos.tray
{action}' and surface failure as HTTP 500 with stderr. Status returns
platform + autostart + tray PID + daemon PID. 501 on unsupported
platforms.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Frontend zod schemas + API client

**Files:**
- Create: `frontend/src/types/Tray.ts`
- Create: `frontend/src/api/tray.api.ts`
- Create: `frontend/src/__tests__/api-tray.test.ts`

- [ ] **Step 1: Inspect existing api/ pattern**

```bash
ls /d/code/claude-mnemos/frontend/src/api/ && head -20 /d/code/claude-mnemos/frontend/src/api/metrics.api.ts
```

Note the imports (axios instance, schemas, etc.). New file follows the same shape.

- [ ] **Step 2: Write failing tests**

Create `frontend/src/__tests__/api-tray.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { TrayStatusSchema } from "../types/Tray";
import { getTrayStatus, installTray, uninstallTray } from "../api/tray.api";

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
});

describe("tray API", () => {
  it("GET /tray/status parses with zod schema", async () => {
    mock.onGet("/tray/status").reply(200, {
      platform: "windows",
      autostart_enabled: true,
      autostart_path: "C:\\X\\Mnemos.lnk",
      tray_running: true,
      tray_pid: 1234,
      daemon_pid: 5678,
    });
    const status = await getTrayStatus();
    expect(status.platform).toBe("windows");
    expect(status.autostart_enabled).toBe(true);
  });

  it("POST /tray/install returns installed=true", async () => {
    mock.onPost("/tray/install").reply(200, { installed: true });
    const res = await installTray();
    expect(res.installed).toBe(true);
  });

  it("POST /tray/uninstall returns installed=false", async () => {
    mock.onPost("/tray/uninstall").reply(200, { installed: false });
    const res = await uninstallTray();
    expect(res.installed).toBe(false);
  });

  it("TrayStatusSchema permissive: missing optional fields default", () => {
    const parsed = TrayStatusSchema.parse({
      platform: "macos",
      autostart_enabled: false,
    });
    expect(parsed.autostart_path).toBeNull();
    expect(parsed.tray_pid).toBeNull();
  });
});
```

Verify `axios-mock-adapter` is already in devDependencies:
```bash
grep "axios-mock-adapter" /d/code/claude-mnemos/frontend/package.json
```

If not present, add it:
```bash
cd /d/code/claude-mnemos/frontend && pnpm add -D axios-mock-adapter
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/api-tray.test.ts 2>&1 | tail -10
```

Expected: import errors on missing types and API module.

- [ ] **Step 4: Implement Tray types + API**

Create `frontend/src/types/Tray.ts`:
```typescript
import { z } from "zod";

export const TrayStatusSchema = z.object({
  platform: z.enum(["windows", "macos", "linux", "unsupported"]),
  autostart_enabled: z.boolean(),
  autostart_path: z.string().nullable().default(null),
  tray_running: z.boolean().default(false),
  tray_pid: z.number().int().nullable().default(null),
  daemon_pid: z.number().int().nullable().default(null),
});
export type TrayStatus = z.infer<typeof TrayStatusSchema>;

export const InstallResultSchema = z.object({
  installed: z.boolean(),
});
export type InstallResult = z.infer<typeof InstallResultSchema>;
```

Create `frontend/src/api/tray.api.ts`:
```typescript
import axios from "axios";
import {
  InstallResultSchema,
  TrayStatusSchema,
  type InstallResult,
  type TrayStatus,
} from "@/types/Tray";

export async function getTrayStatus(): Promise<TrayStatus> {
  const { data } = await axios.get("/tray/status");
  return TrayStatusSchema.parse(data);
}

export async function installTray(): Promise<InstallResult> {
  const { data } = await axios.post("/tray/install");
  return InstallResultSchema.parse(data);
}

export async function uninstallTray(): Promise<InstallResult> {
  const { data } = await axios.post("/tray/uninstall");
  return InstallResultSchema.parse(data);
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/api-tray.test.ts 2>&1 | tail -10
```

Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/types/Tray.ts frontend/src/api/tray.api.ts frontend/src/__tests__/api-tray.test.ts frontend/package.json frontend/pnpm-lock.yaml && git commit -m "feat(frontend): tray API client + zod schemas

getTrayStatus / installTray / uninstallTray with permissive parsing.
Adds axios-mock-adapter dev dep if missing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(If `pnpm-lock.yaml` was untouched because dep already present, drop it from `git add`.)

---

## Task 15: Onboarding wizard — auto-start checkbox

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx` (add checkbox + post-create install)
- Modify: `frontend/src/__tests__/Onboarding.test.tsx` (cover new behaviour)
- Modify: `frontend/public/locales/{en,uk,ru}.json` (new strings)

- [ ] **Step 1: Inspect existing Onboarding.tsx + test**

```bash
wc -l /d/code/claude-mnemos/frontend/src/pages/Onboarding.tsx
wc -l /d/code/claude-mnemos/frontend/src/__tests__/Onboarding.test.tsx
```

Read both files in full. Key insertion point: the `submit` function's `onSuccess` handler — after `navigate(...)` we must dispatch `installTray()` if checkbox checked.

- [ ] **Step 2: Write the failing tests**

Append to `frontend/src/__tests__/Onboarding.test.tsx` (within the existing `describe("Onboarding", ...)` block; if the file uses a different harness style, match it):

```typescript
  it("renders auto-start checkbox when platform supported", async () => {
    mock.onGet("/tray/status").reply(200, {
      platform: "windows",
      autostart_enabled: false,
    });
    renderOnboarding(); // existing helper

    expect(await screen.findByLabelText(/auto.?start|автоматически.*при.*логине/i)).toBeInTheDocument();
  });

  it("hides auto-start checkbox on unsupported platform", async () => {
    mock.onGet("/tray/status").reply(200, {
      platform: "unsupported",
      autostart_enabled: false,
    });
    renderOnboarding();
    expect(screen.queryByLabelText(/auto.?start|автоматически.*при.*логине/i)).not.toBeInTheDocument();
  });

  it("calls /tray/install when checkbox checked and form submitted", async () => {
    mock.onGet("/tray/status").reply(200, {
      platform: "windows",
      autostart_enabled: false,
    });
    mock.onPost("/projects").reply(200, { name: "p1", vault_root: "/x", cwd_patterns: [] });
    mock.onPost("/tray/install").reply(200, { installed: true });

    renderOnboarding();
    await userEvent.type(screen.getByLabelText(/имя проекта|name/i), "p1");
    await userEvent.type(screen.getByLabelText(/путь.*vault|vault.*path/i), "/x");
    await userEvent.click(await screen.findByLabelText(/auto.?start|автоматически/i));
    await userEvent.click(screen.getByRole("button", { name: /создать проект|create/i }));

    await waitFor(() => {
      const installCalls = mock.history.post.filter((c) => c.url === "/tray/install");
      expect(installCalls.length).toBe(1);
    });
  });
```

If `renderOnboarding` and other helpers don't exist, copy the harness from the surrounding file. The exact import names depend on what's already there.

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/Onboarding.test.tsx 2>&1 | tail -15
```

Expected: assertion failures (checkbox not found, install never called).

- [ ] **Step 4: Modify Onboarding.tsx**

Open `frontend/src/pages/Onboarding.tsx` and apply these changes:

Add imports near the top:
```tsx
import { getTrayStatus, installTray } from "@/api/tray.api";
import type { TrayStatus } from "@/types/Tray";
```

Add to component state (after existing `useState` calls):
```tsx
  const [trayStatus, setTrayStatus] = useState<TrayStatus | null>(null);
  const [autostartChecked, setAutostartChecked] = useState<boolean>(true);
```

Add an effect right after the state block:
```tsx
  // Fetch platform info on mount to decide whether to show the autostart checkbox
  // (hidden on Linux / unsupported per design §8).
  // Errors are ignored — checkbox stays hidden.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  React.useEffect(() => {
    getTrayStatus().then(setTrayStatus).catch(() => setTrayStatus(null));
  }, []);
```

(If `React` is not already imported as namespace, use `useEffect` directly.)

Modify the `submit` function. Locate `onSuccess: (entry) => navigate(...)` and replace with:
```tsx
        onSuccess: (entry) => {
          if (autostartChecked && trayStatus && (trayStatus.platform === "windows" || trayStatus.platform === "macos")) {
            installTray().catch(() => {
              // Surface as toast in a future polish; for now silent — checkbox optional
            });
          }
          navigate(`/project/${encodeURIComponent(entry.name)}`);
        },
```

Add the checkbox JSX after the CWD textarea section, before the submit buttons:
```tsx
      {trayStatus && (trayStatus.platform === "windows" || trayStatus.platform === "macos") && (
        <div className="mt-4">
          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={autostartChecked}
              onChange={(e) => setAutostartChecked(e.target.checked)}
            />
            {t("onboarding.autostart_label")}
          </label>
          <p className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">
            {t("onboarding.autostart_hint")}
          </p>
        </div>
      )}
```

Add locale keys. Edit each of `frontend/public/locales/{en,uk,ru}.json`. Inside the `onboarding` object:

`en.json`:
```json
"autostart_label": "Auto-start mnemos on login",
"autostart_hint": "Adds a tray icon and starts the daemon automatically when you sign in."
```

`ru.json`:
```json
"autostart_label": "Запускать mnemos автоматически при логине",
"autostart_hint": "Добавит иконку в трей и будет запускать демона при входе в систему."
```

`uk.json`:
```json
"autostart_label": "Запускати mnemos автоматично при вході",
"autostart_hint": "Додасть іконку в трей і запускатиме демона при вході в систему."
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/Onboarding.test.tsx 2>&1 | tail -15
```

Expected: all Onboarding tests passing (including 3 new ones).

Run the full Vitest suite to catch regressions:
```bash
pnpm test --run 2>&1 | tail -8
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/pages/Onboarding.tsx frontend/src/__tests__/Onboarding.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): Onboarding auto-start checkbox

Fetches /tray/status on mount; shows checkbox only on supported
platforms (windows, macos). On submit with checkbox checked, calls
installTray() before navigation. New locale keys: onboarding.autostart_*.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Icon assets + final verification + manual checklist

**Files:**
- Create: `claude_mnemos/tray/assets/icon-running.png`, `icon-stopped.png` (22×22 PNG)
- Create: `claude_mnemos/tray/assets/icon-running.ico`, `icon-stopped.ico` (16/32/48px ICO)
- Create: `docs/plans/2026-04-29-tray-autostart-manual-checklist.md`

- [ ] **Step 1: Generate placeholder PNG icons via PIL**

Run this Python one-liner from repo root to create deterministic placeholder icons (no external assets, pure PIL):

```bash
cd /d/code/claude-mnemos && python -c "
from PIL import Image, ImageDraw
import os

assets = 'claude_mnemos/tray/assets'
os.makedirs(assets, exist_ok=True)

def make_png(path, fill):
    img = Image.new('RGBA', (22, 22), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 19, 19), fill=fill)
    d.text((6, 4), 'M', fill=(255, 255, 255, 255))
    img.save(path, format='PNG')

def make_ico(path, fill):
    sizes = [(16, 16), (32, 32), (48, 48)]
    images = []
    for s in sizes:
        img = Image.new('RGBA', s, (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((1, 1, s[0]-2, s[1]-2), fill=fill)
        images.append(img)
    images[0].save(path, format='ICO', sizes=sizes)

make_png(f'{assets}/icon-running.png', (60, 200, 80, 255))   # green
make_png(f'{assets}/icon-stopped.png', (220, 60, 60, 255))   # red
make_ico(f'{assets}/icon-running.ico', (60, 200, 80, 255))
make_ico(f'{assets}/icon-stopped.ico', (220, 60, 60, 255))
print('icons written')
"
```

Expected: `icons written`.

Verify files exist:
```bash
ls -la D:/code/claude-mnemos/claude_mnemos/tray/assets/
```

Expected: 4 files (running/stopped × png/ico).

- [ ] **Step 2: Smoke-test icon load**

```bash
cd /d/code/claude-mnemos && python -c "
from claude_mnemos.tray.icon import _load_image
img = _load_image('icon-running.png')
print(img.size, img.mode)
"
```

Expected: `(22, 22) RGBA` (or `(22, 22) P`/similar — point is, no exception).

- [ ] **Step 3: Run full backend test suite**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -5
```

Expected: `1XXX passed, 3 skipped` (X being the new tests added; should be ~1370+).

- [ ] **Step 4: Run full frontend test suite + ruff + tsc + lint**

```bash
cd /d/code/claude-mnemos && python -m ruff check . 2>&1 | tail -3
```
Expected: `All checks passed!`.

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run 2>&1 | tail -6
```
Expected: all tests pass (181 + new Onboarding + api-tray = ~187+).

```bash
cd /d/code/claude-mnemos/frontend && pnpm tsc --noEmit 2>&1 | tail -3
```
Expected: no errors.

```bash
cd /d/code/claude-mnemos/frontend && pnpm lint 2>&1 | tail -3
```
Expected: only pre-existing button.tsx warning, 0 errors.

```bash
cd /d/code/claude-mnemos/frontend && pnpm build 2>&1 | tail -5
```
Expected: build succeeds, bundle generated to `claude_mnemos/daemon/static/`.

- [ ] **Step 5: Write manual integration checklist**

Create `docs/plans/2026-04-29-tray-autostart-manual-checklist.md`:
```markdown
# Tray + Autostart — Manual Integration Checklist

These checks cannot run in CI (require display, real OS autostart, reboot). Run them by hand on Win11 (and macOS if available) after merge.

## Windows 11

- [ ] `pip install -e .` succeeds.
- [ ] `mnemos-tray --help` prints subcommands.
- [ ] `mnemos tray install` creates `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Mnemos.lnk` (verify in File Explorer).
- [ ] Tray icon appears (right of taskbar). Right-click → menu has Open dashboard / Restart daemon / Show logs / Quit.
- [ ] Open Settings → Apps → Startup. "Mnemos" appears in the list, toggle works.
- [ ] Reboot. After login, tray icon appears within ~10s; `curl http://localhost:5757/health` → 200.
- [ ] Open Task Manager → find Python process running daemon. `Stop-Process -Force` → wait 5s → daemon respawns; supervisor.log shows the crash + restart entries.
- [ ] Stop-Process 4× rapidly (within ~1min) → tray icon turns red, tooltip says "crashed". Restart from menu works.
- [ ] `mnemos tray uninstall` removes the .lnk. Tray keeps running. `mnemos tray status` reports `autostart_enabled=false`.
- [ ] Reboot. Tray does NOT start. `curl http://localhost:5757/health` fails (no daemon).
- [ ] Onboarding wizard at fresh install: checkbox visible, defaults to checked, on Done invokes /tray/install.

## macOS

- [ ] `pip install -e .` succeeds.
- [ ] `mnemos tray install` creates `~/Library/LaunchAgents/com.claude-mnemos.tray.plist`. `launchctl list | grep claude-mnemos` → entry visible.
- [ ] Tray icon appears in menu bar. Menu items match Win.
- [ ] Logout / login. Icon appears, daemon up.
- [ ] `kill -9 <daemon_pid>` → respawn within seconds (visible in supervisor.log).
- [ ] `mnemos tray uninstall` → `launchctl list | grep claude-mnemos` → empty. Plist deleted.
- [ ] Logout / login. No tray, no daemon.

## Common

- [ ] Onboarding wizard does NOT show autostart checkbox on Linux (test in any Linux env).
- [ ] `GET /tray/status` returns sane JSON in browser (open dashboard → DevTools).
- [ ] `mnemos tray install` while tray is running: idempotent, prints "Auto-start installed", no second tray spawned (verify `tray.pid` unchanged).
```

- [ ] **Step 6: Final commit**

```bash
cd /d/code/claude-mnemos && git add claude_mnemos/tray/assets/ docs/plans/2026-04-29-tray-autostart-manual-checklist.md && git commit -m "feat(tray): icon assets + manual integration checklist

Placeholder icons generated via PIL (green=running, red=stopped),
both PNG (mac) and ICO (win) with multi-size. Manual checklist
covers Win11+macOS install/reboot/crash/uninstall scenarios that
can't run in CI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-review notes

The plan above derives 1:1 from `2026-04-29-tray-autostart-design.md` sections 1-18.

**Coverage check:**
- §2 architecture → tasks 6-11 (supervisor + tray app + entrypoint)
- §3 components → all tasks split by file
- §4 state machine → task 7 (enum + transitions) + task 8 (subprocess) + task 9 (tick/crash)
- §5 behaviors → task 9 (crash detection) + task 11 (entrypoint orchestrates)
- §6 CLI → tasks 11 + 12
- §7 HTTP API → task 13
- §8 UI → task 15
- §9 deps → task 1
- §10 file/OS-impact → tasks 3 + 4 (paths) + 11 (PID files)
- §11 logging → task 8 (daemon.log via subprocess.PIPE) + task 11 (supervisor.log via logging)
- §12 tests → every task has TDD steps; manual checklist in task 16
- §13 error handling → covered in tasks 3 (PowerShell exit), 4 (launchctl exit), 8 (terminate fallback to kill), 11 (lock conflict), 13 (501 unsupported)
- §14 backwards-compat → task 8 adopt logic; warning of pre-existing entries is **not in plan** — accepted YAGNI for MVP, can add later
- §15 risks → restart-loop limiter (task 6), unsupported platform (task 5), display-less env for icon (task 10 manual marker)
- §17 success criteria → 1-7 verifiable in manual checklist (task 16); 8 in CI

**Type/name consistency:**
- `AutostartManager`/`AutostartStatus` defined in task 2, used unchanged in 3,4,5,11,13
- `SupervisorState` defined in task 7, referenced by name in 8,9,10
- `RestartLimiter` defined in task 6, referenced in 8 (`self.limiter`) and 9 (`record_crash` etc.)
- `TRAY_PID_FILE` / `DAEMON_PID_FILE` defined in task 11, re-imported in task 13
- `installTray`/`uninstallTray`/`getTrayStatus` defined in task 14, referenced in 15

**Skipped intentionally (YAGNI):**
- Warning of pre-existing daemon-only autostart entries (§14) — added if user complains.
- Icon mtime / dirty-state (§5 «icon flicker on restart») — kept simple: supervisor sets icon on each repaint regardless.
- Notification balloon on crash (rejected in design Q3 → silent).

**Plan complete and saved.**
