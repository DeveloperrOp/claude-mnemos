from datetime import UTC, datetime
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
        # runtimes dict satisfies both POST routing (by project_name) and
        # the cross-vault GET/DELETE aggregation via all_runtimes().
        self.runtimes: dict[str, _FakeRuntime] = {_PROJECT: runtime}

    @property
    def job_store(self) -> JobStore:
        """Convenience for tests that create jobs directly on the daemon."""
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


@pytest.fixture
def transcript_file(tmp_path: Path) -> str:
    """Real on-disk transcript path so POST /jobs validation passes."""
    p = tmp_path / "session.jsonl"
    p.write_text("[]", encoding="utf-8")
    return str(p)


async def test_post_creates_job(client, transcript_file):
    r = await client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"project_name": _PROJECT, "transcript_path": transcript_file},
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "queued"
    assert body["kind"] == "ingest"
    assert body["id"]


async def test_get_lists_jobs(client, tmp_path: Path):
    a = tmp_path / "a.jsonl"
    a.write_text("[]", encoding="utf-8")
    b = tmp_path / "b.jsonl"
    b.write_text("[]", encoding="utf-8")
    await client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"project_name": _PROJECT, "transcript_path": str(a)},
        },
    )
    await client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"project_name": _PROJECT, "transcript_path": str(b)},
        },
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


async def test_get_by_id(client, transcript_file):
    create = await client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"project_name": _PROJECT, "transcript_path": transcript_file},
        },
    )
    job_id = create.json()["id"]
    r = await client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["id"] == job_id


async def test_get_by_id_404(client):
    r = await client.get("/jobs/nonexistent")
    assert r.status_code == 404


async def test_delete_cancels_queued(client, transcript_file):
    create = await client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"project_name": _PROJECT, "transcript_path": transcript_file},
        },
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


async def test_post_rejects_missing_project_name(client, transcript_file):
    # New contract: project_name is required in POST payload.
    r = await client.post(
        "/jobs",
        json={"kind": "ingest", "payload": {"transcript_path": transcript_file}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_project_name"


async def test_post_rejects_unknown_project(client, transcript_file):
    r = await client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {
                "project_name": "no-such-project",
                "transcript_path": transcript_file,
            },
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unknown_project"


async def test_post_rejects_missing_transcript_path(client):
    r = await client.post(
        "/jobs",
        json={"kind": "ingest", "payload": {"project_name": _PROJECT}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_transcript_path"


async def test_post_rejects_nonexistent_transcript(client):
    r = await client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {
                "project_name": _PROJECT,
                "transcript_path": "/no/such/file.jsonl",
            },
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "transcript_not_found"


async def test_post_accepts_existing_transcript(client, tmp_path: Path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("[]", encoding="utf-8")
    r = await client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {
                "project_name": _PROJECT,
                "transcript_path": str(transcript),
            },
        },
    )
    assert r.status_code == 201
