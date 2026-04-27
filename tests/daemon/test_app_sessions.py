"""REST tests for /sessions/* routes (Plan #13a Task 6)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.manifest import IngestRecord, Manifest


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


def _seed_manifest(vault: Path, *, sha: str, session_id: str) -> None:
    """Append a single succeeded record to the manifest at ``vault``."""
    manifest = Manifest.load(vault)
    manifest.add(
        sha,
        IngestRecord(
            session_id=session_id,
            ingested_at=datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC),
            raw_path=f"raw/chats/{session_id}.md",
            source_path=None,
            created_pages=[],
            skipped_collisions=[],
            model="claude-opus-4-7",
            input_tokens=100,
            output_tokens=200,
            transcript_path=f"/abs/{session_id}.jsonl",
            raw_transcript_bytes=4096,
        ),
    )
    manifest.save(vault)


async def test_list_empty(client):
    r = await client.get("/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body == {"sessions": [], "total": 0}


async def test_list_with_manifest_entries(client, tmp_path: Path):
    _seed_manifest(tmp_path, sha="sha-aaa", session_id="abc")
    _seed_manifest(tmp_path, sha="sha-bbb", session_id="def")
    r = await client.get("/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    sids = {s["session_id"] for s in body["sessions"]}
    assert sids == {"abc", "def"}
    for s in body["sessions"]:
        assert s["status"] == "succeeded"
        assert s["model"] == "claude-opus-4-7"


async def test_get_by_id(client, tmp_path: Path):
    _seed_manifest(tmp_path, sha="sha-xyz", session_id="target")
    r = await client.get("/sessions/target")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "target"
    assert body["status"] == "succeeded"
    assert body["transcript_path"] == "/abs/target.jsonl"
    assert body["raw_transcript_bytes"] == 4096


async def test_get_404(client):
    r = await client.get("/sessions/nonexistent")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "not_found"


async def test_post_ingest_creates_job(client, tmp_path: Path):
    transcript = tmp_path / "newone.jsonl"
    transcript.write_text("[]", encoding="utf-8")
    r = await client.post(
        "/sessions/newone/ingest",
        json={"transcript_path": str(transcript)},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "ingest"
    assert body["status"] == "queued"
    assert body["payload"]["transcript_path"] == str(transcript)


async def test_post_ingest_400_missing_path(client):
    r = await client.post("/sessions/somesid/ingest", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_or_invalid_transcript_path"
