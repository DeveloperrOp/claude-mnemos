from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker


class _FakeDaemon:
    def __init__(self) -> None:
        self.alerts = Alerts()
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.started_at_monotonic = 0.0
        # Routes read tracker from primary_runtime; self-shim preserves behaviour.
        self.primary_runtime = self

    def scheduler_jobs_info(self):
        return []


@pytest.fixture
def daemon() -> _FakeDaemon:
    return _FakeDaemon()


@pytest.fixture
def app(tmp_path: Path, daemon: _FakeDaemon):
    return create_app(tmp_path, daemon=daemon)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_results_404_when_no_run(client):
    r = await client.get("/lint/results")
    assert r.status_code == 404


async def test_run_then_results_round_trip(client, tmp_path: Path):
    r = await client.post("/lint/run")
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert "summary" in body

    r = await client.get("/lint/results")
    assert r.status_code == 200
    assert r.json()["run_id"] == body["run_id"]


async def test_autofix_409_without_cached_run(client):
    r = await client.post("/lint/autofix")
    assert r.status_code == 409


async def test_autofix_after_run(client, tmp_path: Path):
    p = tmp_path / "wiki/entities/foo.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: T\ntype: entity\ncreated: 2026-04-26\nupdated: 2026-04-26\n"
        "agent_written: true\n---\nbody  \n",
        encoding="utf-8",
    )

    r = await client.post("/lint/run")
    assert r.status_code == 200

    r = await client.post("/lint/autofix")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["snapshot_path"]
    assert body["activity_id"]
    assert "body  " not in (tmp_path / "wiki/entities/foo.md").read_text(encoding="utf-8")
