from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.state.activity import ActivityEntry, ActivityLog
from claude_mnemos.state.manifest import IngestRecord, Manifest


@pytest.fixture
async def client(tmp_path: Path):
    app = create_app(tmp_path)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, tmp_path


async def test_empty_vault_zero_counts(client):
    c, vault = client
    r = await c.get("/vault/info")
    assert r.status_code == 200
    body = r.json()
    assert body["vault"] == str(vault)
    assert body["raw_chats"] == 0
    assert body["wiki_pages"] == 0
    assert body["manifest_processed"] == 0
    assert body["activity_entries"] == 0
    assert body["snapshots"] == 0
    assert body["total_size_bytes"] == 0


async def test_vault_info_counts_files(client):
    c, vault = client
    (vault / "raw" / "chats").mkdir(parents=True)
    (vault / "raw" / "chats" / "a.md").write_text("x", encoding="utf-8")
    (vault / "raw" / "chats" / "b.md").write_text("y", encoding="utf-8")
    (vault / "wiki" / "entities").mkdir(parents=True)
    (vault / "wiki" / "entities" / "foo.md").write_text("z", encoding="utf-8")
    (vault / "wiki" / "concepts").mkdir(parents=True)
    (vault / "wiki" / "concepts" / "bar.md").write_text("z", encoding="utf-8")
    (vault / "wiki" / "concepts" / "baz.md").write_text("z", encoding="utf-8")

    r = await c.get("/vault/info")
    body = r.json()
    assert body["raw_chats"] == 2
    assert body["wiki_pages"] == 3
    assert body["total_size_bytes"] > 0


async def test_vault_info_counts_manifest(client):
    c, vault = client
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
    manifest.save(vault)

    r = await c.get("/vault/info")
    assert r.json()["manifest_processed"] == 1


async def test_vault_info_counts_activity(client):
    c, vault = client
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
    log.save(vault)

    r = await c.get("/vault/info")
    assert r.json()["activity_entries"] == 1


async def test_corrupt_activity_returns_503(client):
    c, vault = client
    (vault / ".activity.json").write_text("not json", encoding="utf-8")
    r = await c.get("/vault/info")
    assert r.status_code == 503
    assert r.json()["error"] == "activity_corrupt"


async def test_corrupt_manifest_returns_503(client):
    c, vault = client
    (vault / ".manifest.json").write_text("not json", encoding="utf-8")
    r = await c.get("/vault/info")
    assert r.status_code == 503
    assert r.json()["error"] == "manifest_corrupt"
