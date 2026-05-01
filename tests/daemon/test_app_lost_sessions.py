"""REST tests for /lost-sessions/* routes (Plan #13b-β2 Task 10 update).

After β2, every import/ignore call requires ``project_name`` in the body.
GET and POST /scan are cross-vault (no project param needed).

The _FakeDaemon shim is updated to expose a ``runtimes`` dict so the new
``all_runtimes`` / ``get_runtime`` helpers can resolve the single test vault.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.core.lost_sessions import LOST_SESSIONS_IGNORE_FILENAME, LostSessionsIgnore
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore

_PROJECT_NAME = "test-vault"


class _FakeRuntime:
    """Minimal VaultRuntime shim for single-vault lost-sessions tests."""

    def __init__(self, vault: Path) -> None:
        self.name = _PROJECT_NAME
        self.vault_root = vault
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.job_worker = None
        self.lost_sessions_cache = None  # no TTL cache → synchronous scan


class _FakeDaemon:
    def __init__(self, vault: Path) -> None:
        self.alerts = Alerts()
        self.started_at_monotonic = 0.0
        self._runtime = _FakeRuntime(vault)
        # Expose runtimes dict so all_runtimes() / get_runtime() work.
        self.runtimes: dict[str, _FakeRuntime] = {_PROJECT_NAME: self._runtime}

    def scheduler_jobs_info(self) -> list[object]:
        return []


@pytest.fixture
def daemon(tmp_path: Path):
    d = _FakeDaemon(tmp_path)
    yield d
    d._runtime.job_store.close()


@pytest.fixture
def app(tmp_path: Path, daemon: _FakeDaemon):
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def transcripts_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Empty fake transcripts root, point env var at it."""
    root = tmp_path / "transcripts_root"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    return root


# ---------------------------------------------------------------------------
# GET /lost-sessions
# ---------------------------------------------------------------------------


async def test_list_empty(client, transcripts_root: Path):
    r = await client.get("/api/lost-sessions")
    assert r.status_code == 200
    assert r.json() == {"sessions": [], "total": 0}


async def test_list_with_sessions(client, transcripts_root: Path):
    (transcripts_root / "alpha.jsonl").write_text("hi", encoding="utf-8")
    (transcripts_root / "beta.jsonl").write_text("ho", encoding="utf-8")
    r = await client.get("/api/lost-sessions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    sids = {s["session_id"] for s in body["sessions"]}
    assert sids == {"alpha", "beta"}
    # β2: every item has project_name.
    for item in body["sessions"]:
        assert item["project_name"] == _PROJECT_NAME


# ---------------------------------------------------------------------------
# POST /lost-sessions/scan
# ---------------------------------------------------------------------------


async def test_post_scan_invalidates_and_rescans(client, transcripts_root: Path):
    (transcripts_root / "before.jsonl").write_text("x", encoding="utf-8")
    # Warm cache via list
    r1 = await client.get("/api/lost-sessions")
    assert r1.json()["total"] == 1
    # Add a new file; rescan should pick it up
    (transcripts_root / "after.jsonl").write_text("y", encoding="utf-8")
    r = await client.post("/api/lost-sessions/scan")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2


# ---------------------------------------------------------------------------
# POST /lost-sessions/{sid}/import
# ---------------------------------------------------------------------------


async def test_post_import_success(client, tmp_path: Path, transcripts_root: Path):
    (transcripts_root / "lostie.jsonl").write_text("body", encoding="utf-8")
    r = await client.post(
        "/api/lost-sessions/lostie/import",
        json={"project_name": _PROJECT_NAME},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "ingest"
    assert body["status"] == "queued"
    # Payload carries the resolved transcript path from the scan.
    assert body["payload"]["transcript_path"].endswith("lostie.jsonl")


async def test_post_import_missing_project_name_returns_400(
    client, transcripts_root: Path
):
    """β2: missing project_name in body → 400."""
    (transcripts_root / "lostie.jsonl").write_text("body", encoding="utf-8")
    r = await client.post("/api/lost-sessions/lostie/import", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_project_name"


async def test_post_import_with_nonexistent_transcript_returns_400(
    client, daemon, transcripts_root: Path
):
    r = await client.post(
        "/api/lost-sessions/sid-x/import",
        json={
            "project_name": _PROJECT_NAME,
            "transcript_path": "/no/such/file.jsonl",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "transcript_not_found"


# ---------------------------------------------------------------------------
# POST /lost-sessions/{sid}/ignore
# ---------------------------------------------------------------------------


async def test_post_ignore_adds_sha(client, tmp_path: Path, transcripts_root: Path):
    (transcripts_root / "skipme.jsonl").write_text("zzz", encoding="utf-8")
    r = await client.post(
        "/api/lost-sessions/skipme/ignore",
        json={"project_name": _PROJECT_NAME},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ignored_count"] == 1

    # Persisted on disk and the SHA is now ignored.
    ig_path = tmp_path / LOST_SESSIONS_IGNORE_FILENAME
    assert ig_path.is_file()
    loaded = LostSessionsIgnore.load(tmp_path)
    assert len(loaded.ignored_shas) == 1


async def test_post_ignore_missing_project_name_returns_400(
    client, transcripts_root: Path
):
    """β2: missing project_name in body → 400."""
    (transcripts_root / "skipme.jsonl").write_text("zzz", encoding="utf-8")
    r = await client.post("/api/lost-sessions/skipme/ignore", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_project_name"
