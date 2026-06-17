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
    # Resume-on-boot outcome is always surfaced (None when no swap pending).
    assert "last_apply" in body


def test_update_status_includes_asset_url(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {
            "tag_name": "v0.9.0",
            "html_url": "https://example.com/v0.9.0",
            "assets": [
                {
                    "name": "claude-mnemos-portable-x64.zip",
                    "browser_download_url": "https://example/portable.zip",
                },
            ],
        },
    )
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._current_version", lambda: "0.0.1"
    )
    r = client.get("/api/update-status")
    assert r.status_code == 200
    body = r.json()
    assert body["asset_url"] == "https://example/portable.zip"


def test_check_now_forces_live_recheck(client, monkeypatch):
    # GET caches for 24h; POST /check must bypass the cache (force=True) and
    # hit the release feed every time.
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        return {"tag_name": "v0.9.0", "html_url": "https://example.com/v0.9.0"}

    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release", fake_fetch
    )
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._current_version", lambda: "0.0.1"
    )

    # Prime the cache via GET (1 fetch).
    client.get("/api/update-status")
    assert calls["n"] == 1
    # A second GET is served from cache — no new fetch.
    client.get("/api/update-status")
    assert calls["n"] == 1
    # POST /check forces a fresh fetch despite the warm cache.
    r = client.post("/api/update-status/check")
    assert r.status_code == 200
    assert calls["n"] == 2
    body = r.json()
    assert body["has_update"] is True
    assert body["latest"] == "0.9.0"
    assert "last_apply" in body


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


# ---------------------------------------------------------------------------
# POST /api/update/apply
# ---------------------------------------------------------------------------


def test_apply_refuses_in_dev(client, monkeypatch):
    # In the dev venv runtime.is_frozen() is False → can_apply() returns
    # (False, reason). The route must 409 and NEVER spawn anything.
    spawned = []
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.spawn_updater",
        lambda work: spawned.append(work),
    )
    r = client.post("/api/update/apply")
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["error"] == "cannot_apply"
    assert body["reason"]
    assert spawned == []  # never spawned in dev


def test_apply_starts_when_frozen(client, monkeypatch):
    spawned = []
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.can_apply",
        lambda: (True, ""),
    )

    from claude_mnemos.core.update_check import UpdateStatus
    from datetime import UTC, datetime

    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.check_for_update",
        lambda *, force=False: UpdateStatus(
            current="0.0.1",
            latest="0.9.0",
            download_url="https://example.com/v0.9.0",
            has_update=True,
            checked_at=datetime.now(tz=UTC),
            asset_url="https://example/portable.zip",
        ),
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.stage_update",
        lambda asset_url, version: Path("/fake/work"),
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.spawn_updater",
        lambda work: spawned.append(work),
    )

    r = client.post("/api/update/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True
    assert body["version"] == "0.9.0"
    assert len(spawned) == 1


def test_apply_409_when_no_update(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.can_apply",
        lambda: (True, ""),
    )
    from claude_mnemos.core.update_check import UpdateStatus
    from datetime import UTC, datetime

    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.check_for_update",
        lambda *, force=False: UpdateStatus(
            current="0.9.0",
            latest="0.9.0",
            download_url=None,
            has_update=False,
            checked_at=datetime.now(tz=UTC),
            asset_url=None,
        ),
    )
    spawned = []
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.spawn_updater",
        lambda work: spawned.append(work),
    )
    r = client.post("/api/update/apply")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "no_update"
    assert spawned == []


def test_apply_502_when_stage_fails(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.can_apply",
        lambda: (True, ""),
    )
    from claude_mnemos.core.update_apply import UpdateApplyError
    from claude_mnemos.core.update_check import UpdateStatus
    from datetime import UTC, datetime

    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.check_for_update",
        lambda *, force=False: UpdateStatus(
            current="0.0.1",
            latest="0.9.0",
            download_url="https://example.com/v0.9.0",
            has_update=True,
            checked_at=datetime.now(tz=UTC),
            asset_url="https://example/portable.zip",
        ),
    )

    def _boom(asset_url, version):
        raise UpdateApplyError("download failed")

    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.stage_update", _boom
    )
    spawned = []
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.update.spawn_updater",
        lambda work: spawned.append(work),
    )
    r = client.post("/api/update/apply")
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "stage_failed"
    assert spawned == []
