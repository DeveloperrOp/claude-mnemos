"""REST tests for /metrics/* routes (Plan #13a Task 8, updated for β2 cross-vault).

Tests now use a real MnemosDaemon with a single mounted vault (instead of the
old ``daemon=None`` / ``create_app`` approach) so they exercise the cross-vault
aggregation code path introduced in Plan #13b-β2 Task 13.

The ``daemon=None`` fixture is kept only for the period-validation test which
doesn't need a mounted vault.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.state.manifest import IngestRecord, Manifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def daemon_with_one_vault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[MnemosDaemon, TestClient, Path], None, None]:
    """Real MnemosDaemon with a single 'default' vault mounted at tmp_path/v."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    vault = tmp_path / "v"
    vault.mkdir()

    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app) as client:
        r = client.post(
            "/projects",
            json={"name": "default", "vault_root": str(vault), "cwd_patterns": []},
        )
        assert r.status_code == 201, f"POST /projects failed: {r.text}"
        yield daemon, client, vault
    asyncio.run(daemon._shutdown_runtimes())
    if daemon.scheduler.running:
        daemon.scheduler.shutdown(wait=False)


@pytest.fixture
def no_vault_app(tmp_path: Path):
    """App with daemon=None, used only for period-validation tests."""
    return create_app(daemon=None)


@pytest.fixture
async def no_vault_client(no_vault_app):
    transport = ASGITransport(app=no_vault_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_usage_default_period(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, vault = daemon_with_one_vault
    _seed(vault, sha="sha-a", sid="a", ti=10, to=20)
    _seed(vault, sha="sha-b", sid="b", ti=30, to=40)
    r = client.get("/metrics/usage")
    assert r.status_code == 200
    body = r.json()
    assert body["period_days"] == 30
    assert body["sessions_covered"] == 2
    assert body["tokens_input"] == 40
    assert body["tokens_output"] == 60
    assert body["tokens_injected"] == 100
    assert body["raw_bytes_total"] == 8192


def test_usage_explicit_period(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, vault = daemon_with_one_vault
    _seed(vault, sha="sha-x", sid="x", ti=1, to=2)
    r = client.get("/metrics/usage?period=7d")
    assert r.status_code == 200
    body = r.json()
    assert body["period_days"] == 7


def test_usage_by_project_returns_single_entry(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, vault = daemon_with_one_vault
    _seed(vault, sha="sha-p", sid="p", ti=5, to=10)
    r = client.get("/metrics/usage/by-project")
    assert r.status_code == 200
    body = r.json()
    assert len(body["projects"]) == 1
    entry = body["projects"][0]
    assert entry["project"] == "default"
    assert entry["sessions_covered"] == 1


def test_usage_top_sessions(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, vault = daemon_with_one_vault
    _seed(vault, sha="sha-1", sid="small", ti=1, to=1)
    _seed(vault, sha="sha-2", sid="big", ti=100, to=200)
    r = client.get("/metrics/usage/top-sessions?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body["sessions"]) == 2
    assert body["sessions"][0]["session_id"] == "big"
    assert body["sessions"][0]["tokens_total"] == 300


def test_usage_timeline(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, vault = daemon_with_one_vault
    _seed(vault, sha="sha-t", sid="t", ti=10, to=20)
    r = client.get("/metrics/usage/timeline?period=7d")
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) == 7
    # Today's bucket has the seeded session.
    last = body["points"][-1]
    assert last["sessions"] == 1
    assert last["tokens_input"] == 10
    assert last["tokens_output"] == 20


async def test_usage_bad_period_400(no_vault_client) -> None:
    r = await no_vault_client.get("/metrics/usage?period=oops")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_period_format"


def test_parse_period_accepts_weeks():
    from claude_mnemos.daemon.routes.metrics import _parse_period
    assert _parse_period("1w") == 7
    assert _parse_period("4w") == 28


def test_parse_period_accepts_months():
    from claude_mnemos.daemon.routes.metrics import _parse_period
    assert _parse_period("1m") == 30
    assert _parse_period("3m") == 90


def test_parse_period_accepts_years():
    from claude_mnemos.daemon.routes.metrics import _parse_period
    assert _parse_period("1y") == 365


def test_parse_period_accepts_days_unchanged():
    from claude_mnemos.daemon.routes.metrics import _parse_period
    assert _parse_period("30d") == 30
    assert _parse_period("1d") == 1


def test_parse_period_rejects_garbage():
    import pytest as pt
    from fastapi import HTTPException

    from claude_mnemos.daemon.routes.metrics import _parse_period
    for bad in ("0d", "-1d", "abc", "30x", "30dd", ""):
        with pt.raises(HTTPException) as exc:
            _parse_period(bad)
        assert exc.value.status_code == 400
