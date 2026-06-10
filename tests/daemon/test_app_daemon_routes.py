"""Tests for /api/daemon/{pause,resume} routes.

The routes pause/resume the per-vault job queues (via job_store.pause_queue /
resume_queue), which the worker actually honours through is_paused — so the
pause has a real effect, unlike the old placebo daemon.paused flag.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore


class _FakeRuntime:
    def __init__(self, vault: Path) -> None:
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)


class _FakeDaemon:
    def __init__(self, vault: Path) -> None:
        self.runtimes = {"alpha": _FakeRuntime(vault)}


@pytest.fixture
def fake_daemon(tmp_path: Path) -> Iterator[_FakeDaemon]:
    d = _FakeDaemon(tmp_path)
    yield d
    d.runtimes["alpha"].job_store.close()


@pytest.fixture
def app(fake_daemon: _FakeDaemon):
    return create_app(daemon=fake_daemon)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_pause_route_actually_pauses_the_queue(
    client, fake_daemon: _FakeDaemon
) -> None:
    js = fake_daemon.runtimes["alpha"].job_store
    assert js.is_paused() is False
    r = await client.post("/api/daemon/pause")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["paused"] is True
    assert body["queues"] == 1
    assert js.is_paused() is True  # the worker honours this


async def test_resume_route_unpauses_the_queue(
    client, fake_daemon: _FakeDaemon
) -> None:
    js = fake_daemon.runtimes["alpha"].job_store
    await client.post("/api/daemon/pause")
    assert js.is_paused() is True
    r = await client.post("/api/daemon/resume")
    assert r.status_code == 200
    assert r.json()["paused"] is False
    assert js.is_paused() is False


async def test_pause_route_503_when_no_daemon_bound() -> None:
    app = create_app(daemon=None)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/daemon/pause")
    assert r.status_code == 503
