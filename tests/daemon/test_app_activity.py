from datetime import UTC, datetime
from pathlib import Path
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
def vault_with_ingested(tmp_path: Path):
    vault = tmp_path / "vault"
    from datetime import date

    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=date(2026, 4, 26),
    )
    return vault


@pytest.fixture
async def client(tmp_path: Path):
    app = create_app(tmp_path)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, tmp_path


async def test_list_activity_empty(client):
    c, _ = client
    r = await c.get("/activity")
    assert r.status_code == 200
    assert r.json() == {"entries": [], "total": 0}


async def test_list_activity_returns_entries(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
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
    log.save(vault)

    app = create_app(vault)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/activity")
    body = r.json()
    assert body["total"] == 2
    # Newest first
    assert body["entries"][0]["id"] == e2.id
    assert body["entries"][1]["id"] == e1.id


async def test_list_activity_pagination(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
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
    log.save(vault)

    app = create_app(vault)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/activity?limit=2&offset=1")
    body = r.json()
    assert body["total"] == 5
    assert len(body["entries"]) == 2


async def test_get_activity_unknown_id(client):
    c, _ = client
    r = await c.get("/activity/does-not-exist")
    assert r.status_code == 404


async def test_get_activity_known_id(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
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
    log.save(vault)

    app = create_app(vault)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/activity/abcdef")
    assert r.status_code == 200
    assert r.json()["id"] == "abcdef"


async def test_undo_activity_success(vault_with_ingested):
    vault = vault_with_ingested
    log = ActivityLog.load(vault)
    assert len(log.entries) == 1
    op_id = log.entries[0].id

    app = create_app(vault)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(f"/activity/{op_id}/undo")
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


async def test_undo_activity_already_undone_returns_409(vault_with_ingested):
    vault = vault_with_ingested
    log = ActivityLog.load(vault)
    op_id = log.entries[0].id

    app = create_app(vault)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r1 = await c.post(f"/activity/{op_id}/undo")
        assert r1.status_code == 200
        r2 = await c.post(f"/activity/{op_id}/undo")
    assert r2.status_code == 409
    assert r2.json()["error"] == "undo_failed"


async def test_undo_unknown_id_returns_409(client):
    c, _ = client
    r = await c.post("/activity/no-such-entry/undo")
    assert r.status_code == 409
    assert r.json()["error"] == "undo_failed"
