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
