"""REST tests for /sessions/{project}/... routes (Plan #13b-β2 Task 2)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.manifest import IngestRecord, Manifest


class _FakeRuntime:
    """Minimal VaultRuntime shim for session route tests."""

    def __init__(self, vault: Path) -> None:
        self.vault_root = vault
        self.alerts = Alerts()
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.job_worker = None

    def close(self) -> None:
        self.job_store.close()


class _FakeDaemon:
    def __init__(self, alpha_vault: Path) -> None:
        self._alpha_runtime = _FakeRuntime(alpha_vault)
        self.runtimes: dict[str, Any] = {"alpha": self._alpha_runtime}
        self.started_at_monotonic = 0.0

    def scheduler_jobs_info(self) -> list[Any]:
        return []

    def close(self) -> None:
        self._alpha_runtime.close()


@pytest.fixture
def alpha_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "alpha"
    vault.mkdir()
    return vault


@pytest.fixture
def daemon(alpha_vault: Path) -> _FakeDaemon:  # type: ignore[misc]
    d = _FakeDaemon(alpha_vault)
    yield d  # type: ignore[misc]
    d.close()


@pytest.fixture
def app(daemon: _FakeDaemon) -> Any:
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app: Any) -> Any:
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


# ── GET /sessions/{project} ───────────────────────────────────────────────────


async def test_list_empty(client: Any) -> None:
    r = await client.get("/api/sessions/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body == {"sessions": [], "total": 0}


async def test_list_with_manifest_entries(client: Any, alpha_vault: Path) -> None:
    _seed_manifest(alpha_vault, sha="sha-aaa", session_id="abc")
    _seed_manifest(alpha_vault, sha="sha-bbb", session_id="def")
    r = await client.get("/api/sessions/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    sids = {s["session_id"] for s in body["sessions"]}
    assert sids == {"abc", "def"}
    for s in body["sessions"]:
        assert s["status"] == "succeeded"
        assert s["model"] == "claude-opus-4-7"


async def test_list_unknown_project_404(client: Any) -> None:
    r = await client.get("/api/sessions/ghost")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


# ── GET /sessions/{project}/{session_id} ──────────────────────────────────────


async def test_get_by_id(client: Any, alpha_vault: Path) -> None:
    _seed_manifest(alpha_vault, sha="sha-xyz", session_id="target")
    r = await client.get("/api/sessions/alpha/target")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "target"
    assert body["status"] == "succeeded"
    assert body["transcript_path"] == "/abs/target.jsonl"
    assert body["raw_transcript_bytes"] == 4096


async def test_get_404(client: Any) -> None:
    r = await client.get("/api/sessions/alpha/nonexistent")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "not_found"


# ── POST /sessions/{project}/{session_id}/ingest ──────────────────────────────


async def test_post_ingest_creates_job(
    client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(tmp_path))
    transcript = tmp_path / "newone.jsonl"
    transcript.write_text("[]", encoding="utf-8")
    r = await client.post(
        "/api/sessions/alpha/newone/ingest",
        json={"transcript_path": str(transcript)},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "ingest"
    assert body["status"] == "queued"
    assert body["payload"]["transcript_path"] == str(transcript)


async def test_post_ingest_routes_to_alpha_job_store(
    client: Any, daemon: _FakeDaemon, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Job is created in alpha's job_store, not some other vault's."""
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(tmp_path))
    transcript = tmp_path / "check.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    r = await client.post(
        "/api/sessions/alpha/check/ingest",
        json={"transcript_path": str(transcript)},
    )
    assert r.status_code == 201
    job_id = r.json()["id"]
    # Verify the job lives in alpha's store
    job = daemon.runtimes["alpha"].job_store.get_by_id(job_id)
    assert job is not None
    assert job.kind == "ingest"


async def test_post_ingest_400_missing_path(client: Any) -> None:
    r = await client.post("/api/sessions/alpha/somesid/ingest", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_or_invalid_transcript_path"


async def test_post_ingest_unknown_project_404(
    client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(tmp_path))
    transcript = tmp_path / "x.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    r = await client.post(
        "/api/sessions/ghost/somesid/ingest",
        json={"transcript_path": str(transcript)},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


async def test_post_ingest_rejects_path_outside_transcripts_root(
    client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Path-traversal: existing file outside MNEMOS_TRANSCRIPTS_ROOT → 400."""
    root = tmp_path / "transcripts_root"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}", encoding="utf-8")
    r = await client.post(
        "/api/sessions/alpha/sid-x/ingest",
        json={"transcript_path": str(outside)},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "transcript_outside_root"
