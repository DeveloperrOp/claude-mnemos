"""REST tests for /metrics/* routes (Plan #13a Task 8).

Reads don't require a daemon; we pass ``daemon=None`` so the tests stay
isolated from the jobs subsystem.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.state.manifest import IngestRecord, Manifest


@pytest.fixture
def app(tmp_path: Path):
    return create_app(tmp_path, daemon=None)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _seed(vault: Path, *, sha: str, sid: str, ti: int, to: int) -> None:
    m = Manifest.load(vault)
    m.add(
        sha,
        IngestRecord(
            session_id=sid,
            ingested_at=datetime.now(UTC),
            raw_path=f"raw/chats/{sid}.md",
            source_path=None,
            created_pages=[],
            skipped_collisions=[],
            model="claude-opus-4-7",
            input_tokens=ti,
            output_tokens=to,
            transcript_path=f"/abs/{sid}.jsonl",
            raw_transcript_bytes=4096,
        ),
    )
    m.save(vault)


async def test_usage_default_period(client, tmp_path: Path):
    _seed(tmp_path, sha="sha-a", sid="a", ti=10, to=20)
    _seed(tmp_path, sha="sha-b", sid="b", ti=30, to=40)
    r = await client.get("/metrics/usage")
    assert r.status_code == 200
    body = r.json()
    assert body["period_days"] == 30
    assert body["sessions_covered"] == 2
    assert body["tokens_input"] == 40
    assert body["tokens_output"] == 60
    assert body["tokens_injected"] == 100
    assert body["raw_bytes_total"] == 8192


async def test_usage_explicit_period(client, tmp_path: Path):
    _seed(tmp_path, sha="sha-x", sid="x", ti=1, to=2)
    r = await client.get("/metrics/usage?period=7d")
    assert r.status_code == 200
    body = r.json()
    assert body["period_days"] == 7


async def test_usage_by_project_returns_single_entry(client, tmp_path: Path):
    _seed(tmp_path, sha="sha-p", sid="p", ti=5, to=10)
    r = await client.get("/metrics/usage/by-project")
    assert r.status_code == 200
    body = r.json()
    assert len(body["projects"]) == 1
    entry = body["projects"][0]
    assert entry["project"] == "default"
    assert entry["sessions_covered"] == 1


async def test_usage_top_sessions(client, tmp_path: Path):
    _seed(tmp_path, sha="sha-1", sid="small", ti=1, to=1)
    _seed(tmp_path, sha="sha-2", sid="big", ti=100, to=200)
    r = await client.get("/metrics/usage/top-sessions?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body["sessions"]) == 2
    assert body["sessions"][0]["session_id"] == "big"
    assert body["sessions"][0]["tokens_total"] == 300


async def test_usage_timeline(client, tmp_path: Path):
    _seed(tmp_path, sha="sha-t", sid="t", ti=10, to=20)
    r = await client.get("/metrics/usage/timeline?period=7d")
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) == 7
    # Today's bucket has the seeded session
    last = body["points"][-1]
    assert last["sessions"] == 1
    assert last["tokens_input"] == 10
    assert last["tokens_output"] == 20


async def test_usage_bad_period_400(client):
    r = await client.get("/metrics/usage?period=oops")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_period_format"
