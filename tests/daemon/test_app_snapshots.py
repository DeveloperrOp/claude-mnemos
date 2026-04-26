from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.config import Config
from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter
from claude_mnemos.core.snapshots import (
    create_daily_snapshot,
    create_manual_snapshot,
    create_snapshot,
)
from claude_mnemos.daemon.app import create_app
from claude_mnemos.ingest.extraction import ExtractionResult
from claude_mnemos.ingest.pipeline import ingest
from claude_mnemos.state.activity import ActivityLog


@pytest.fixture
async def client(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    app = create_app(vault)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, vault


async def test_list_snapshots_empty(client):
    c, _ = client
    r = await c.get("/snapshots")
    assert r.status_code == 200
    assert r.json() == {"snapshots": []}


async def test_list_snapshots_returns_three_kinds(client):
    c, vault = client
    create_snapshot(vault, operation_id="abc", operation_type="ingest_extracted")
    create_daily_snapshot(vault, date(2026, 4, 26))
    create_manual_snapshot(vault, label="release")

    r = await c.get("/snapshots")
    body = r.json()
    assert len(body["snapshots"]) == 3
    kinds = {s["kind"] for s in body["snapshots"]}
    assert kinds == {"pre-op", "daily", "manual"}


async def test_create_manual_snapshot_no_body(client):
    c, vault = client
    r = await c.post("/snapshots", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "manual"
    assert body["name"].startswith("manual-")
    assert (vault / ".backups" / body["name"]).is_dir()


async def test_create_manual_snapshot_with_label(client):
    c, _ = client
    r = await c.post("/snapshots", json={"label": "release-1"})
    assert r.status_code == 201
    assert r.json()["label"] == "release-1"


async def test_create_manual_snapshot_traversal_label_rejected(client):
    """Label that sanitizes to empty must return 400."""
    c, _ = client
    r = await c.post("/snapshots", json={"label": "///"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_name"


async def test_delete_snapshot_known(client):
    c, vault = client
    snap = create_daily_snapshot(vault, date(2026, 4, 26))

    r = await c.request("DELETE", f"/snapshots/{snap.name}")
    assert r.status_code == 200
    assert r.json()["deleted"] == snap.name
    assert not snap.exists()


async def test_delete_snapshot_missing_returns_404(client):
    c, _ = client
    r = await c.request("DELETE", "/snapshots/daily-2026-01-01")
    assert r.status_code == 404


async def test_delete_snapshot_traversal_rejected(client):
    c, _ = client
    r = await c.request("DELETE", "/snapshots/..%2Fetc-passwd")
    # ..%2F → "..\xetc-passwd" — should be 400 invalid_name
    assert r.status_code in (400, 404)  # depending on URL decoding behavior


async def test_delete_snapshot_unknown_prefix(client):
    c, vault = client
    junk = vault / ".backups" / "random-stuff"
    junk.mkdir(parents=True)

    r = await c.request("DELETE", "/snapshots/random-stuff")
    assert r.status_code == 400
    # Junk untouched
    assert junk.exists()


async def test_restore_snapshot_writes_activity_entry(tmp_path: Path):
    vault = tmp_path / "vault"
    config = Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=150_000,
        lock_timeout=60.0,
    )

    def _stub_extractor():
        def _extract(*, messages, cfg, llm_client, today):  # noqa: ARG001
            fm = WikiPageFrontmatter(
                title="X",
                type="entity",
                flavor=[],
                confidence=0.8,
                related=[],
                created=today,
                updated=today,
            )
            page = WikiPage(
                relative_path=Path("wiki/entities/x.md"),
                frontmatter=fm,
                body="X.",
            )
            return ExtractionResult(
                summary="x", skipped_reason=None, pages=[page],
                input_tokens=10, output_tokens=5,
            )

        return _extract

    fixture = Path(__file__).parent.parent / "fixtures" / "sample_session.jsonl"
    ingest(
        fixture, vault,
        cfg=config, llm_client=MagicMock(),
        extractor=_stub_extractor(), today=date(2026, 4, 26),
    )
    # Now there is one pre-op snapshot from the ingest
    log_before = ActivityLog.load(vault)
    snapshot_name = log_before.entries[0].snapshot_path.split("/")[-1]

    app = create_app(vault)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(f"/snapshots/{snapshot_name}/restore")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["snapshot"] == snapshot_name
    assert body["activity_id"]

    # Vault rolled back: no wiki page anymore
    assert not (vault / "wiki" / "entities" / "x.md").exists()
    # Activity log has manual_restore entry
    log_after = ActivityLog.load(vault)
    assert any(
        e.operation_type == "manual_restore"
        and e.metadata.get("restored_from") == f".backups/{snapshot_name}"
        for e in log_after.entries
    )


async def test_restore_missing_snapshot_returns_404(client):
    c, _ = client
    r = await c.post("/snapshots/daily-2099-12-31/restore")
    assert r.status_code == 404


async def test_restore_invalid_name_returns_400(client):
    c, _ = client
    r = await c.post("/snapshots/random-stuff/restore")
    assert r.status_code == 400
