from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


def _make_client() -> TestClient:
    daemon = MnemosDaemon(DaemonConfig(boot_filter=None))
    return TestClient(daemon.app)


def test_get_tray_status_returns_platform_info() -> None:
    client = _make_client()
    fake_status = MagicMock(installed=False, path="/tmp/x")
    fake_mgr = MagicMock(status=MagicMock(return_value=fake_status))
    with patch("claude_mnemos.daemon.routes.tray.get_autostart_manager", return_value=fake_mgr), \
         patch("claude_mnemos.daemon.routes.tray.platform_label", return_value="windows"):
        resp = client.get("/api/tray/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "windows"
    assert body["autostart_enabled"] is False


def test_post_tray_install_runs_subprocess() -> None:
    client = _make_client()
    fake_completed = MagicMock(returncode=0, stderr="")
    with patch(
        "claude_mnemos.daemon.routes.tray.subprocess.run",
        return_value=fake_completed,
    ) as run:
        resp = client.post("/api/tray/install")
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
        resp = client.post("/api/tray/install")
    assert resp.status_code == 500
    assert "powershell" in resp.json()["detail"]


def test_post_tray_uninstall_runs_subprocess() -> None:
    client = _make_client()
    fake_completed = MagicMock(returncode=0, stderr="")
    with patch("claude_mnemos.daemon.routes.tray.subprocess.run", return_value=fake_completed):
        resp = client.post("/api/tray/uninstall")
    assert resp.status_code == 200
    assert resp.json() == {"installed": False}


def test_post_tray_install_returns_501_on_unsupported_platform() -> None:
    client = _make_client()
    with patch("claude_mnemos.daemon.routes.tray.platform_label", return_value="unsupported"):
        resp = client.post("/api/tray/install")
    assert resp.status_code == 501
