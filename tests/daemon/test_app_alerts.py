from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app


class _FakeDaemon:
    def __init__(self) -> None:
        self.alerts = Alerts()
        self.started_at_monotonic = 0.0

    def scheduler_jobs_info(self):
        return []


@pytest.fixture
def daemon() -> _FakeDaemon:
    return _FakeDaemon()


@pytest.fixture
def app(tmp_path: Path, daemon: _FakeDaemon):
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_alerts_empty(client):
    r = await client.get("/api/alerts")
    assert r.status_code == 200
    assert r.json() == []


async def test_alerts_returns_newest_first(client, daemon: _FakeDaemon):
    a1 = daemon.alerts.add(
        kind="parse_failed",
        path="/a.md",
        message="oldest",
        detected_at=datetime(2026, 4, 27, 14, 0, tzinfo=UTC),
    )
    a2 = daemon.alerts.add(
        kind="external_create",
        path="/b.md",
        message="middle",
        detected_at=datetime(2026, 4, 27, 14, 1, tzinfo=UTC),
    )
    a3 = daemon.alerts.add(
        kind="lock_timeout",
        path="/c.md",
        message="newest",
        detected_at=datetime(2026, 4, 27, 14, 2, tzinfo=UTC),
    )

    r = await client.get("/api/alerts")
    assert r.status_code == 200
    body = r.json()
    assert [item["id"] for item in body] == [a3.id, a2.id, a1.id]


async def test_delete_existing_returns_204(client, daemon: _FakeDaemon):
    a = daemon.alerts.add(
        kind="handler_error",
        path="/x.md",
        message="m",
        detected_at=datetime(2026, 4, 27, 14, 0, tzinfo=UTC),
    )
    r = await client.delete(f"/api/alerts/{a.id}")
    assert r.status_code == 204
    r = await client.get("/api/alerts")
    assert all(item["id"] != a.id for item in r.json())


async def test_delete_missing_returns_404(client):
    r = await client.delete("/api/alerts/nonexistent")
    assert r.status_code == 404


async def test_alerts_no_daemon_returns_empty(tmp_path: Path):
    app = create_app(daemon=None)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/alerts")
    assert r.status_code == 200
    assert r.json() == []


async def test_alerts_no_daemon_delete_returns_404(tmp_path: Path):
    app = create_app(daemon=None)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.delete("/api/alerts/anything")
    assert r.status_code == 404
