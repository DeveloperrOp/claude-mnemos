from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.ingest.llm.auth import AuthStatus


def _make_client() -> TestClient:
    return TestClient(MnemosDaemon(DaemonConfig(boot_filter=None)).app)


def test_health_claude_cli_reports_installed_authenticated() -> None:
    with patch(
        "claude_mnemos.daemon.routes.health.check_claude_cli_auth",
        return_value=AuthStatus(installed=True, authenticated=True, binary_path="/x/claude"),
    ):
        resp = _make_client().get("/api/health/claude-cli")
    assert resp.status_code == 200
    body = resp.json()
    assert body["installed"] is True
    assert body["authenticated"] is True
    assert body["binary_path"] == "/x/claude"


def test_health_claude_cli_reports_not_installed() -> None:
    with patch(
        "claude_mnemos.daemon.routes.health.check_claude_cli_auth",
        return_value=AuthStatus(installed=False, authenticated=False),
    ):
        resp = _make_client().get("/api/health/claude-cli")
    assert resp.status_code == 200
    assert resp.json()["installed"] is False
