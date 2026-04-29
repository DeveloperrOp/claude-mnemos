from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_install_python_m_fallback_uses_arguments_field(fake_appdata: Path) -> None:
    """Fallback path: target_exe=python.exe, args=['-m','claude_mnemos.tray','run'].

    Critical that '-m' / 'claude_mnemos.tray' / 'run' end up in Arguments,
    NOT concatenated into TargetPath (which would be a broken .lnk).
    """
    mgr = WindowsAutostart(
        target_exe="C:\\Python\\python.exe",
        target_args=["-m", "claude_mnemos.tray", "run"],
    )
    with patch("claude_mnemos.tray.platform.windows.subprocess.run") as run:
        run.return_value = _stub_completed(0)
        mgr.install()
    cmd = run.call_args[0][0]
    joined = " ".join(cmd)
    # TargetPath must be ONLY the executable path
    assert "$Shortcut.TargetPath = 'C:\\Python\\python.exe'" in joined
    # Args go into Arguments, not TargetPath
    assert "-m" in joined
    assert "claude_mnemos.tray" in joined
    # And TargetPath does NOT contain the args
    assert "python.exe -m claude_mnemos.tray" not in joined
