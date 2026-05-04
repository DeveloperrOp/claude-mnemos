"""REST tests for /api/dashboard/* endpoints."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore


@pytest.fixture(autouse=True)
def _clear_transcripts_cache():
    from claude_mnemos.core.transcript_scanner import invalidate_transcripts_cache
    invalidate_transcripts_cache()
    yield
    invalidate_transcripts_cache()


_PROJECT = "alpha"


class _FakeRuntime:
    def __init__(self, vault: Path) -> None:
        self.name = _PROJECT
        self.vault_root = vault
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.job_worker = None
        self.lost_sessions_cache = None


class _FakeDaemon:
    def __init__(self, vault: Path) -> None:
        self.started_at_monotonic = 0.0
        self._runtime = _FakeRuntime(vault)
        self.runtimes: dict[str, _FakeRuntime] = {_PROJECT: self._runtime}

    def scheduler_jobs_info(self) -> list[Any]:
        return []


@pytest.fixture
def daemon(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    d = _FakeDaemon(vault)
    yield d
    d._runtime.job_store.close()


@pytest.fixture
def app(daemon: _FakeDaemon):
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def transcripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    return root


def _stale_jsonl(root: Path, name: str, cwd: str | None, hours_ago: float) -> Path:
    payload: dict[str, object] = {"sid": name}
    if cwd:
        payload["cwd"] = cwd
    p = root / f"{name}.jsonl"
    p.write_bytes(json.dumps(payload).encode("utf-8"))
    ts = (datetime.now(tz=UTC) - timedelta(hours=hours_ago)).timestamp()
    os.utime(p, (ts, ts))
    return p


async def test_snapshot_empty_returns_zeros(client, transcripts: Path) -> None:
    r = await client.get("/api/dashboard/snapshot")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kpi"]["queue"]["queued"] == 0
    assert body["active_sessions"] == []
    assert body["running_jobs"] == []
    assert body["errors"] == []


async def test_snapshot_includes_active_sessions(client, transcripts: Path) -> None:
    _stale_jsonl(transcripts, "active-1", cwd=None, hours_ago=0.5)
    r = await client.get("/api/dashboard/snapshot")
    assert r.status_code == 200
    body = r.json()
    sids = {s["session_id"] for s in body["active_sessions"]}
    assert "active-1" in sids


async def test_snapshot_kpi_active_counts(client, transcripts: Path) -> None:
    _stale_jsonl(transcripts, "hot-1", cwd=None, hours_ago=0.2)
    _stale_jsonl(transcripts, "cool-1", cwd=None, hours_ago=2)
    r = await client.get("/api/dashboard/snapshot")
    body = r.json()
    assert body["kpi"]["active"]["hot"] >= 1
    assert body["kpi"]["active"]["cooling"] >= 1


async def test_snapshot_returns_errors_field_when_aggregator_fails(
    client, transcripts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If one aggregator raises, snapshot returns partial data with errors[]."""
    async def boom(*a, **kw):
        raise RuntimeError("simulated")

    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.dashboard.scan_active_sessions", boom
    )
    r = await client.get("/api/dashboard/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["active_sessions"] == []
    assert any("active_sessions" in e for e in body["errors"])


async def test_dump_now_missing_project_name_returns_422(client, transcripts: Path) -> None:
    r = await client.post(
        "/api/dashboard/active-sessions/foo/dump-now",
        json={},
    )
    assert r.status_code == 422


async def test_dump_now_unknown_session_returns_404(client, transcripts: Path) -> None:
    r = await client.post(
        "/api/dashboard/active-sessions/no-such/dump-now",
        json={"project_name": _PROJECT},
    )
    assert r.status_code == 404


async def test_dump_now_active_session_enqueues(
    client, daemon, transcripts: Path
) -> None:
    """When session is active and assigned (cwd not given so __unassigned__),
    dump-now uses the session's transcript_path. We pass the same project_name
    in body so the runtime accepts it. The session's project_name is __unassigned__
    in this fixture, but that doesn't matter — body controls target vault."""
    _stale_jsonl(transcripts, "to-dump", cwd=None, hours_ago=0.5)
    r = await client.post(
        f"/api/dashboard/active-sessions/to-dump/dump-now",
        json={"project_name": _PROJECT},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "ingest"
    assert body["payload"]["extract"] is False
    assert body["payload"]["transcript_path"].endswith("to-dump.jsonl")


async def test_scan_active_endpoint(client, transcripts: Path) -> None:
    _stale_jsonl(transcripts, "x", cwd=None, hours_ago=0.5)
    r = await client.post("/api/dashboard/scan-active")
    assert r.status_code == 200
    body = r.json()
    assert body["scanned"] >= 1


async def test_snapshot_includes_per_project_session_counts(client, transcripts: Path) -> None:
    """The Overview's first-session-celebration hook depends on this field."""
    r = await client.get("/api/dashboard/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert "per_project_session_counts" in body
    assert isinstance(body["per_project_session_counts"], dict)
