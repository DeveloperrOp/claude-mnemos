from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore

# Project name used throughout the existing tests.
_PROJECT = "test-vault"


class _FakeRuntime:
    """Minimal stand-in for VaultRuntime — only the job-related attributes."""

    def __init__(self, vault: Path, name: str) -> None:
        self.name = name
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.job_worker = None


class _FakeDaemon:
    def __init__(self, vault: Path) -> None:
        self.alerts = Alerts()
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.started_at_monotonic = 0.0

        runtime = _FakeRuntime(vault, name=_PROJECT)
        # runtimes dict satisfies both cross-vault aggregation via
        # all_runtimes() and any per-project resolution via get_runtime().
        self.runtimes: dict[str, _FakeRuntime] = {_PROJECT: runtime}

    @property
    def job_store(self) -> JobStore:
        """Convenience for tests that create/inspect jobs directly."""
        return self.runtimes[_PROJECT].job_store

    def scheduler_jobs_info(self):
        return []


@pytest.fixture
def daemon(tmp_path: Path):
    d = _FakeDaemon(tmp_path)
    yield d
    d.job_store.close()


@pytest.fixture
def app(tmp_path: Path, daemon: _FakeDaemon):
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _force_dead_letter(daemon, job_id: str) -> None:
    daemon.job_store._conn.execute(
        "UPDATE jobs SET status='dead_letter', attempt=4, error='boom' WHERE id=?",
        (job_id,),
    )


async def test_dead_letter_list(client, daemon):
    job = daemon.job_store.create(kind="ingest", payload={"transcript_path": "/x"})
    _force_dead_letter(daemon, job.id)
    r = await client.get("/api/dead-letter")
    assert r.status_code == 200
    body = r.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["id"] == job.id


async def test_dead_letter_retry(client, daemon):
    job = daemon.job_store.create(kind="ingest", payload={"transcript_path": "/x"})
    _force_dead_letter(daemon, job.id)
    r = await client.post(f"/api/dead-letter/{job.id}/retry")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert body["attempt"] == 0


async def test_dead_letter_retry_404(client):
    r = await client.post("/api/dead-letter/nonexistent/retry")
    assert r.status_code == 404


async def test_dead_letter_dismiss(client, daemon):
    job = daemon.job_store.create(kind="ingest", payload={"transcript_path": "/x"})
    _force_dead_letter(daemon, job.id)
    r = await client.delete(f"/api/dead-letter/{job.id}")
    assert r.status_code == 204
    assert daemon.job_store.get_by_id(job.id) is None


async def test_dead_letter_dismiss_404(client):
    r = await client.delete("/api/dead-letter/nonexistent")
    assert r.status_code == 404
