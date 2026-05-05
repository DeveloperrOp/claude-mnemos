"""Tests for /api/daemon/{pause,resume} routes added by Task 4 of E1
desktop launcher plan.

The routes flip ``daemon.paused`` on the bound MnemosDaemon. Pause-semantics
(skip ingest, etc.) is intentionally out of scope — the routes only set the
flag so the supervisor and tray UI can drive it.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app


class _FakeDaemon:
    def __init__(self) -> None:
        self.paused: bool = False


@pytest.fixture
def fake_daemon() -> _FakeDaemon:
    return _FakeDaemon()


@pytest.fixture
def app(fake_daemon: _FakeDaemon):
    return create_app(daemon=fake_daemon)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_pause_route_sets_paused_true(client, fake_daemon: _FakeDaemon) -> None:
    r = await client.post("/api/daemon/pause")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["paused"] is True
    assert fake_daemon.paused is True


async def test_resume_route_sets_paused_false(client, fake_daemon: _FakeDaemon) -> None:
    fake_daemon.paused = True
    r = await client.post("/api/daemon/resume")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["paused"] is False
    assert fake_daemon.paused is False


async def test_pause_route_503_when_no_daemon_bound() -> None:
    app = create_app(daemon=None)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/daemon/pause")
    assert r.status_code == 503
