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
        self.shutdown_requested = False

    def _request_shutdown(self) -> None:
        self.shutdown_requested = True


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


async def test_resume_does_not_clear_a_rate_limit_pause(
    client, fake_daemon: _FakeDaemon
) -> None:
    """A rate-limit pause (near-future reset) must survive a user /resume —
    otherwise the worker resumes before the API limit reset and re-trips 429."""
    from datetime import UTC, datetime, timedelta

    js = fake_daemon.runtimes["alpha"].job_store
    reset_at = datetime.now(UTC) + timedelta(seconds=60)
    js.pause_queue(until=reset_at)  # simulate rate-limit pause
    r = await client.post("/api/daemon/resume")
    assert r.status_code == 200
    assert r.json()["resumed"] == 0  # nothing user-resumable
    assert js.is_paused() is True  # rate-limit pause preserved


async def test_pause_route_503_when_no_daemon_bound() -> None:
    app = create_app(daemon=None)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/daemon/pause")
    assert r.status_code == 503


async def test_restart_requests_graceful_shutdown(
    client, fake_daemon: _FakeDaemon, monkeypatch
) -> None:
    """Restart must ask uvicorn to exit gracefully (so run()'s finally cleans up
    the pid file, observers and job store) rather than hard os._exit(0), which
    skips that cleanup and risks .jobs.db WAL damage / pid residue.

    Happy path: graceful shutdown is requested and the hard os._exit fallback
    does NOT fire. The fallback is armed only when there is a live uvicorn
    server still serving after the grace period; the fake daemon has no server
    (``_server`` absent), so the fallback is correctly skipped here.
    """
    import os as _os

    from claude_mnemos.daemon.routes import daemon as daemon_route

    # Zero the sleeps so the background task does not really wait 0.5s + 5s.
    monkeypatch.setattr(daemon_route, "_RESPONSE_FLUSH_SLEEP", 0.0)
    monkeypatch.setattr(daemon_route, "_GRACEFUL_FALLBACK_SLEEP", 0.0)
    hard_exit: dict[str, int] = {}
    monkeypatch.setattr(_os, "_exit", lambda code: hard_exit.setdefault("code", code))

    r = await client.post("/api/daemon/restart")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # ASGITransport awaits BackgroundTasks before returning the response, so the
    # background task has run to completion by now.
    assert fake_daemon.shutdown_requested is True  # graceful path chosen
    assert "code" not in hard_exit  # no hard os._exit on the happy path
