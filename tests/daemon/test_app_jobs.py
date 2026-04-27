from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore


class _FakeDaemon:
    def __init__(self, vault: Path) -> None:
        self.alerts = Alerts()
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.started_at_monotonic = 0.0
        self.job_worker = None

    def scheduler_jobs_info(self):
        return []


@pytest.fixture
def daemon(tmp_path: Path):
    d = _FakeDaemon(tmp_path)
    yield d
    d.job_store.close()


@pytest.fixture
def app(tmp_path: Path, daemon: _FakeDaemon):
    return create_app(tmp_path, daemon=daemon)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_post_creates_job(client):
    r = await client.post(
        "/jobs",
        json={"kind": "ingest", "payload": {"transcript_path": "/x.jsonl"}},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "queued"
    assert body["kind"] == "ingest"
    assert body["id"]


async def test_get_lists_jobs(client):
    await client.post(
        "/jobs",
        json={"kind": "ingest", "payload": {"transcript_path": "/a"}},
    )
    await client.post(
        "/jobs",
        json={"kind": "ingest", "payload": {"transcript_path": "/b"}},
    )
    r = await client.get("/jobs")
    assert r.status_code == 200
    body = r.json()
    assert len(body["jobs"]) == 2
    assert body["counts"]["queued"] == 2


async def test_get_filters_by_status(client):
    r = await client.get("/jobs?status=running")
    assert r.status_code == 200
    body = r.json()
    assert body["jobs"] == []


async def test_get_by_id(client):
    create = await client.post(
        "/jobs", json={"kind": "ingest", "payload": {"transcript_path": "/x"}}
    )
    job_id = create.json()["id"]
    r = await client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["id"] == job_id


async def test_get_by_id_404(client):
    r = await client.get("/jobs/nonexistent")
    assert r.status_code == 404


async def test_delete_cancels_queued(client):
    create = await client.post(
        "/jobs", json={"kind": "ingest", "payload": {"transcript_path": "/x"}}
    )
    job_id = create.json()["id"]
    r = await client.delete(f"/jobs/{job_id}")
    assert r.status_code == 204
    assert (await client.get(f"/jobs/{job_id}")).status_code == 404


async def test_delete_nonqueued_returns_409(client, daemon):
    job = daemon.job_store.create(kind="ingest", payload={"transcript_path": "/x"})
    daemon.job_store.claim_next_ready(now=datetime.now(UTC))
    r = await client.delete(f"/jobs/{job.id}")
    assert r.status_code == 409
