"""REST tests for /vault/{project} route (Plan #13b-β2 Task 9)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.state.activity import ActivityEntry, ActivityLog
from claude_mnemos.state.manifest import IngestRecord, Manifest


class _FakeRuntime:
    """Minimal VaultRuntime shim for vault route tests."""

    def __init__(self, vault: Path) -> None:
        self.vault_root = vault


class _FakeDaemon:
    def __init__(self, alpha_vault: Path) -> None:
        self._alpha_runtime = _FakeRuntime(alpha_vault)
        self.runtimes: dict[str, Any] = {"alpha": self._alpha_runtime}
        self.primary_runtime = self._alpha_runtime
        self.started_at_monotonic = 0.0

    def scheduler_jobs_info(self) -> list[Any]:
        return []


@pytest.fixture
def alpha_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "alpha"
    vault.mkdir()
    return vault


@pytest.fixture
def daemon(alpha_vault: Path) -> _FakeDaemon:
    return _FakeDaemon(alpha_vault)


@pytest.fixture
def app(daemon: _FakeDaemon) -> Any:
    return create_app(vault_root=None, daemon=daemon)


@pytest.fixture
async def client(app: Any) -> Any:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Basic response
# ---------------------------------------------------------------------------


async def test_empty_vault_zero_counts(client: Any, alpha_vault: Path) -> None:
    r = await client.get("/vault/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["vault"] == str(alpha_vault)
    assert body["raw_chats"] == 0
    assert body["wiki_pages"] == 0
    assert body["manifest_processed"] == 0
    assert body["activity_entries"] == 0
    assert body["snapshots"] == 0
    assert body["total_size_bytes"] == 0


async def test_vault_counts_files(client: Any, alpha_vault: Path) -> None:
    (alpha_vault / "raw" / "chats").mkdir(parents=True)
    (alpha_vault / "raw" / "chats" / "a.md").write_text("x", encoding="utf-8")
    (alpha_vault / "raw" / "chats" / "b.md").write_text("y", encoding="utf-8")
    (alpha_vault / "wiki" / "entities").mkdir(parents=True)
    (alpha_vault / "wiki" / "entities" / "foo.md").write_text("z", encoding="utf-8")
    (alpha_vault / "wiki" / "concepts").mkdir(parents=True)
    (alpha_vault / "wiki" / "concepts" / "bar.md").write_text("z", encoding="utf-8")
    (alpha_vault / "wiki" / "concepts" / "baz.md").write_text("z", encoding="utf-8")

    r = await client.get("/vault/alpha")
    body = r.json()
    assert body["raw_chats"] == 2
    assert body["wiki_pages"] == 3
    assert body["total_size_bytes"] > 0


async def test_vault_counts_manifest(client: Any, alpha_vault: Path) -> None:
    manifest = Manifest()
    manifest.add(
        "sha-1",
        IngestRecord(
            session_id="sess-1",
            ingested_at=datetime(2026, 4, 26, tzinfo=UTC),
            raw_path="raw/chats/a.md",
            source_path=None,
            model=None,
            input_tokens=None,
            output_tokens=None,
        ),
    )
    manifest.save(alpha_vault)

    r = await client.get("/vault/alpha")
    assert r.json()["manifest_processed"] == 1


async def test_vault_counts_activity(client: Any, alpha_vault: Path) -> None:
    log = ActivityLog()
    log.append(
        ActivityEntry(
            id=uuid4().hex,
            timestamp=datetime(2026, 4, 26, tzinfo=UTC),
            operation_type="ingest_extracted",
            status="success",
            snapshot_path=None,
            can_undo=True,
        )
    )
    log.save(alpha_vault)

    r = await client.get("/vault/alpha")
    assert r.json()["activity_entries"] == 1


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


async def test_unknown_project_404(client: Any) -> None:
    r = await client.get("/vault/ghost")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


async def test_corrupt_activity_returns_503(client: Any, alpha_vault: Path) -> None:
    (alpha_vault / ".activity.json").write_text("not json", encoding="utf-8")
    r = await client.get("/vault/alpha")
    assert r.status_code == 503
    assert r.json()["error"] == "activity_corrupt"


async def test_corrupt_manifest_returns_503(client: Any, alpha_vault: Path) -> None:
    (alpha_vault / ".manifest.json").write_text("not json", encoding="utf-8")
    r = await client.get("/vault/alpha")
    assert r.status_code == 503
    assert r.json()["error"] == "manifest_corrupt"


async def test_no_daemon_503() -> None:
    app = create_app(vault_root=None, daemon=None)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/vault/alpha")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "daemon_unavailable"
