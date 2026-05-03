"""REST API tests for /api/health-alerts/* endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.state.alerts_store import AlertsStore, StoredAlert


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    (home / ".claude-mnemos").mkdir()
    return home


@pytest.fixture
def app():
    return create_app(daemon=None)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _seed_alert(id_: str = "x", **overrides) -> StoredAlert:
    base = dict(
        id=id_,
        detector="test",
        severity="warning",
        message="m",
        context={},
        first_seen=_utcnow(),
        last_seen=_utcnow(),
    )
    base.update(overrides)
    return StoredAlert(**base)


async def test_list_empty(isolated_home: Path, client) -> None:
    r = await client.get("/api/health-alerts")
    assert r.status_code == 200
    body = r.json()
    assert body == {"alerts": [], "silenced": []}


async def test_list_returns_active_and_silenced(isolated_home: Path, client) -> None:
    s = AlertsStore.load()
    s.upsert(_seed_alert("active1"))
    s.upsert(_seed_alert("silenced1"))
    s.silence("silenced1", timedelta(hours=1))
    s.save()

    r = await client.get("/api/health-alerts")
    assert r.status_code == 200
    body = r.json()
    active_ids = {a["id"] for a in body["alerts"]}
    silenced_ids = {a["id"] for a in body["silenced"]}
    assert active_ids == {"active1"}
    assert silenced_ids == {"silenced1"}


async def test_silence_endpoint_persists(isolated_home: Path, client) -> None:
    s = AlertsStore.load()
    s.upsert(_seed_alert("a"))
    s.save()

    r = await client.post(
        "/api/health-alerts/a/silence", json={"duration_hours": 2}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    s2 = AlertsStore.load()
    [a] = s2.alerts
    assert a.silenced_until is not None


async def test_silence_unknown_returns_404(isolated_home: Path, client) -> None:
    r = await client.post(
        "/api/health-alerts/missing/silence", json={"duration_hours": 1}
    )
    assert r.status_code == 404


async def test_silence_invalid_body_returns_422(isolated_home: Path, client) -> None:
    s = AlertsStore.load()
    s.upsert(_seed_alert("a"))
    s.save()
    r = await client.post(
        "/api/health-alerts/a/silence", json={"duration_hours": -1}
    )
    assert r.status_code == 422


async def test_dismiss_endpoint_persists(isolated_home: Path, client) -> None:
    s = AlertsStore.load()
    s.upsert(_seed_alert("a"))
    s.save()

    r = await client.post("/api/health-alerts/a/dismiss")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    s2 = AlertsStore.load()
    [a] = s2.alerts
    assert a.dismissed is True


async def test_dismiss_unknown_returns_404(isolated_home: Path, client) -> None:
    r = await client.post("/api/health-alerts/missing/dismiss")
    assert r.status_code == 404


async def test_silence_then_list_excludes_from_active(isolated_home: Path, client) -> None:
    s = AlertsStore.load()
    s.upsert(_seed_alert("a"))
    s.save()

    await client.post("/api/health-alerts/a/silence", json={"duration_hours": 1})
    r = await client.get("/api/health-alerts")
    body = r.json()
    assert all(a["id"] != "a" for a in body["alerts"])
    assert any(a["id"] == "a" for a in body["silenced"])
