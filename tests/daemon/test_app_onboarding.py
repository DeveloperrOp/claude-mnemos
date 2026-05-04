# tests/daemon/test_app_onboarding.py
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.core.cwd_detection import DetectedCwd
from claude_mnemos.daemon.app import create_app


@pytest.fixture
def app(tmp_path: Path):
    return create_app(daemon=None)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_detected_cwds_returns_list(client, monkeypatch) -> None:
    fake_now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.detect_cwds",
        lambda *, now=None, exclude_cwds=(): [
            DetectedCwd(cwd="D:/code/app1", session_count=12, last_seen=fake_now),
            DetectedCwd(cwd="D:/code/app2", session_count=3, last_seen=fake_now),
        ],
    )
    r = client.get("/api/onboarding/detected-cwds")
    assert r.status_code == 200
    body = r.json()
    assert "cwds" in body
    assert len(body["cwds"]) == 2
    assert body["cwds"][0]["cwd"] == "D:/code/app1"
    assert body["cwds"][0]["session_count"] == 12


def test_detected_cwds_excludes_registered(client, monkeypatch) -> None:
    captured_excludes: list[set[str]] = []

    def fake_detect(*, now=None, exclude_cwds=()):
        captured_excludes.append(set(exclude_cwds))
        return []

    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.detect_cwds",
        fake_detect,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding._registered_cwds",
        lambda req: {"D:/already/registered"},
    )
    r = client.get("/api/onboarding/detected-cwds")
    assert r.status_code == 200
    assert captured_excludes == [{"D:/already/registered"}]


def test_setup_status_all_ok(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_claude_cli_installed",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_hooks_present",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_vault_writable",
        lambda roots: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding._project_count",
        lambda req: 2,
    )
    r = client.get("/api/onboarding/setup-status")
    assert r.status_code == 200
    body = r.json()
    assert body["all_ok"] is True
    assert body["claude_cli"]["status"] == "ok"
    assert body["hooks"]["status"] == "ok"
    assert body["vaults"]["status"] == "ok"
    assert body["projects"]["status"] == "ok"
    assert body["projects"]["count"] == 2


def test_setup_status_reports_critical(client, monkeypatch) -> None:
    from datetime import UTC, datetime

    from claude_mnemos.state.alerts_store import StoredAlert

    now = datetime(2026, 5, 4, tzinfo=UTC)
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_claude_cli_installed",
        lambda: StoredAlert(
            id="claude_cli_not_installed",
            detector="x",
            severity="critical",
            message="missing",
            context={},
            first_seen=now,
            last_seen=now,
            silenced_until=None,
            dismissed=False,
        ),
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_hooks_present",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_vault_writable",
        lambda roots: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding._project_count",
        lambda req: 1,
    )
    r = client.get("/api/onboarding/setup-status")
    assert r.status_code == 200
    body = r.json()
    assert body["all_ok"] is False
    assert body["claude_cli"]["status"] == "critical"
    assert body["claude_cli"]["message"] == "missing"
