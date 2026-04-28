"""REST tests for /activity/{project}/... routes (Plan #13b-β2 Task 8)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.config import Config
from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter
from claude_mnemos.daemon.app import create_app
from claude_mnemos.ingest.extraction import ExtractionResult
from claude_mnemos.ingest.pipeline import ingest
from claude_mnemos.state.activity import ActivityEntry, ActivityLog

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_session.jsonl"


class _FakeRuntime:
    """Minimal VaultRuntime shim for activity route tests."""

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


def _cfg() -> Config:
    return Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=150_000,
        lock_timeout=60.0,
    )


def _stub_extractor():
    def _extract(*, messages, cfg, llm_client, today):  # noqa: ARG001
        fm = WikiPageFrontmatter(
            title="FastAPI",
            type="entity",
            flavor=[],
            confidence=0.8,
            related=[],
            created=today,
            updated=today,
        )
        page = WikiPage(
            relative_path=Path("wiki/entities/fastapi.md"),
            frontmatter=fm,
            body="FastAPI is a framework.",
        )
        return ExtractionResult(
            summary="Talked about FastAPI.",
            skipped_reason=None,
            pages=[page],
            input_tokens=1000,
            output_tokens=200,
        )

    return _extract


@pytest.fixture
def vault_with_ingested(tmp_path: Path) -> Path:
    from datetime import date

    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=date(2026, 4, 26),
    )
    return vault


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_activity_empty(client: Any) -> None:
    r = await client.get("/activity/alpha")
    assert r.status_code == 200
    assert r.json() == {"entries": [], "total": 0}


async def test_list_activity_returns_entries(alpha_vault: Path, daemon: _FakeDaemon) -> None:
    log = ActivityLog()
    e1 = ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
        operation_type="ingest_extracted",
        status="success",
        snapshot_path=None,
        can_undo=True,
    )
    e2 = ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 26, 13, 0, tzinfo=UTC),
        operation_type="ingest_raw_only",
        status="success",
        snapshot_path=None,
        can_undo=True,
    )
    log.append(e1)
    log.append(e2)
    log.save(alpha_vault)

    app = create_app(vault_root=None, daemon=daemon)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/activity/alpha")
    body = r.json()
    assert body["total"] == 2
    # Newest first
    assert body["entries"][0]["id"] == e2.id
    assert body["entries"][1]["id"] == e1.id


async def test_list_activity_pagination(alpha_vault: Path, daemon: _FakeDaemon) -> None:
    log = ActivityLog()
    for hour in range(5):
        log.append(
            ActivityEntry(
                id=uuid4().hex,
                timestamp=datetime(2026, 4, 26, hour, 0, tzinfo=UTC),
                operation_type="ingest_extracted",
                status="success",
                snapshot_path=None,
                can_undo=True,
            )
        )
    log.save(alpha_vault)

    app = create_app(vault_root=None, daemon=daemon)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/activity/alpha?limit=2&offset=1")
    body = r.json()
    assert body["total"] == 5
    assert len(body["entries"]) == 2


async def test_list_activity_unknown_project_404(client: Any) -> None:
    r = await client.get("/activity/ghost")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# Get by ID
# ---------------------------------------------------------------------------


async def test_get_activity_unknown_id(client: Any) -> None:
    r = await client.get("/activity/alpha/does-not-exist")
    assert r.status_code == 404


async def test_get_activity_known_id(alpha_vault: Path, daemon: _FakeDaemon) -> None:
    log = ActivityLog()
    e = ActivityEntry(
        id="abcdef",
        timestamp=datetime(2026, 4, 26, tzinfo=UTC),
        operation_type="ingest_extracted",
        status="success",
        snapshot_path=None,
        can_undo=True,
    )
    log.append(e)
    log.save(alpha_vault)

    app = create_app(vault_root=None, daemon=daemon)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/activity/alpha/abcdef")
    assert r.status_code == 200
    assert r.json()["id"] == "abcdef"


async def test_get_activity_unknown_project_404(client: Any) -> None:
    r = await client.get("/activity/ghost/some-id")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------


async def test_undo_activity_success(tmp_path: Path) -> None:
    from datetime import date

    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=date(2026, 4, 26),
    )
    log = ActivityLog.load(vault)
    assert len(log.entries) == 1
    op_id = log.entries[0].id

    runtime = _FakeRuntime(vault)
    daemon_mock: Any = MagicMock()
    daemon_mock.runtimes = {"myvault": runtime}
    daemon_mock.primary_runtime = runtime
    daemon_mock.started_at_monotonic = 0.0
    daemon_mock.scheduler_jobs_info.return_value = []

    app = create_app(vault_root=None, daemon=daemon_mock)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(f"/activity/myvault/{op_id}/undo")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["op_id"] == op_id
    assert body["new_entry_id"] is not None

    # Vault rolled back: no wiki page anymore
    assert not (vault / "wiki" / "entities" / "fastapi.md").exists()
    # Activity log has manual_restore appended
    log_after = ActivityLog.load(vault)
    assert any(e.operation_type == "manual_restore" for e in log_after.entries)


async def test_undo_activity_already_undone_returns_409(tmp_path: Path) -> None:
    from datetime import date

    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=date(2026, 4, 26),
    )
    log = ActivityLog.load(vault)
    op_id = log.entries[0].id

    runtime = _FakeRuntime(vault)
    daemon_mock: Any = MagicMock()
    daemon_mock.runtimes = {"myvault": runtime}
    daemon_mock.primary_runtime = runtime
    daemon_mock.started_at_monotonic = 0.0
    daemon_mock.scheduler_jobs_info.return_value = []

    app = create_app(vault_root=None, daemon=daemon_mock)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r1 = await c.post(f"/activity/myvault/{op_id}/undo")
        assert r1.status_code == 200
        r2 = await c.post(f"/activity/myvault/{op_id}/undo")
    assert r2.status_code == 409
    assert r2.json()["error"] == "undo_failed"


async def test_undo_unknown_id_returns_409(client: Any) -> None:
    r = await client.post("/activity/alpha/no-such-entry/undo")
    assert r.status_code == 409
    assert r.json()["error"] == "undo_failed"


async def test_undo_unknown_project_404(client: Any) -> None:
    r = await client.post("/activity/ghost/some-id/undo")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"
