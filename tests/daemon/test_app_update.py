from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._CACHE_PATH",
        tmp_path / "update-check.json",
    )
    from claude_mnemos.daemon.app import create_app
    return create_app(daemon=None)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_update_status_returns_has_update(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.9.0", "html_url": "https://example.com/v0.9.0"},
    )
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._current_version", lambda: "0.0.1"
    )
    r = client.get("/api/update-status")
    assert r.status_code == 200
    body = r.json()
    assert body["has_update"] is True
    assert body["latest"] == "0.9.0"


def test_dismiss_silences_banner(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.9.0", "html_url": "https://example.com/v0.9.0"},
    )
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._current_version", lambda: "0.0.1"
    )
    assert client.get("/api/update-status").json()["has_update"] is True
    r = client.post("/api/update-status/dismiss", json={"days": 7})
    assert r.status_code == 200
    assert client.get("/api/update-status").json()["has_update"] is False
