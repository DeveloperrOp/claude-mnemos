from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
    assert f"{BUNDLE_ID}.plist" == PLIST_FILENAME


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


def test_install_python_m_fallback_renders_argv_correctly(fake_home: Path) -> None:
    """Fallback: target_exe=python, args=['-m','claude_mnemos.tray','run'] must
    each become a separate <string> in ProgramArguments — NOT concatenated.
    """
    mgr = MacOSAutostart(
        target_exe="/usr/local/bin/python3",
        target_args=["-m", "claude_mnemos.tray", "run"],
    )
    with patch("claude_mnemos.tray.platform.macos.subprocess.run") as run:
        run.return_value = _stub_completed(0)
        mgr.install()

    plist_path = fake_home / PLIST_FILENAME
    content = plist_path.read_text(encoding="utf-8")
    # All four argv elements present as separate <string> tags
    assert "<string>/usr/local/bin/python3</string>" in content
    assert "<string>-m</string>" in content
    assert "<string>claude_mnemos.tray</string>" in content
    assert "<string>run</string>" in content
