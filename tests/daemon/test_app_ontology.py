from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.state.ontology import (
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
)


def _write_page(vault: Path, rel: str, *, body: str = "") -> None:
    fm = "---\ntitle: T\ntype: entity\n---\n\n"
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    (vault / rel).write_text(fm + body, encoding="utf-8")


def _suggestion(
    *,
    sid: str = "ont-2026-04-26-aaaaaa",
    operation: str = "merge_entities",
    affected: list[str] | None = None,
    target: str | None = "wiki/entities/foobar.md",
) -> Suggestion:
    return Suggestion(
        frontmatter=SuggestionFrontmatter(
            id=sid,
            created=datetime(2026, 4, 26, tzinfo=UTC),
            operation=operation,  # type: ignore[arg-type]
            affected_pages=affected or [
                "wiki/entities/foo.md",
                "wiki/entities/bar.md",
            ],
            proposed_target=target,
        ),
        body="reason",
    )


@pytest.fixture
async def client(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    app = create_app(vault)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, vault


async def test_list_empty(client):
    c, _ = client
    r = await c.get("/suggestions")
    assert r.status_code == 200
    assert r.json() == {"suggestions": [], "total": 0}


async def test_list_pending_only_by_default(client):
    c, vault = client
    store = SuggestionStore(vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    store.create(_suggestion(sid="ont-2026-04-26-bbbbbb"))
    store.archive_suggestion("ont-2026-04-26-bbbbbb")

    r = await c.get("/suggestions")
    body = r.json()
    assert body["total"] == 1


async def test_list_all_status(client):
    c, vault = client
    store = SuggestionStore(vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    store.create(_suggestion(sid="ont-2026-04-26-bbbbbb"))
    store.archive_suggestion("ont-2026-04-26-bbbbbb")

    r = await c.get("/suggestions?status=all")
    body = r.json()
    assert body["total"] == 2


async def test_get_known(client):
    c, vault = client
    store = SuggestionStore(vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))

    r = await c.get("/suggestions/ont-2026-04-26-aaaaaa")
    assert r.status_code == 200
    assert r.json()["frontmatter"]["id"] == "ont-2026-04-26-aaaaaa"


async def test_get_404(client):
    c, _ = client
    r = await c.get("/suggestions/ont-2026-04-26-zzzzzz")
    assert r.status_code == 404


async def test_create_merge_happy(client):
    c, vault = client
    _write_page(vault, "wiki/entities/foo.md")
    _write_page(vault, "wiki/entities/bar.md")

    r = await c.post(
        "/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md", "wiki/entities/bar.md"],
            "proposed_target": "wiki/entities/foobar.md",
            "reason": "Both about foo+bar",
        },
    )
    assert r.status_code == 201
    sid = r.json()["frontmatter"]["id"]
    assert sid.startswith("ont-")


async def test_create_merge_missing_target(client):
    c, _ = client
    r = await c.post(
        "/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md", "wiki/entities/bar.md"],
        },
    )
    assert r.status_code == 422


async def test_create_merge_one_source(client):
    c, _ = client
    r = await c.post(
        "/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md"],
            "proposed_target": "wiki/entities/x.md",
        },
    )
    assert r.status_code == 422


async def test_create_invalid_operation(client):
    c, _ = client
    r = await c.post(
        "/suggestions",
        json={"operation": "weird", "affected_pages": ["x.md"]},
    )
    assert r.status_code == 422


async def test_approve_happy(client):
    c, vault = client
    _write_page(vault, "wiki/entities/foo.md", body="A")
    _write_page(vault, "wiki/entities/bar.md", body="B")

    create = await c.post(
        "/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md", "wiki/entities/bar.md"],
            "proposed_target": "wiki/entities/foobar.md",
            "reason": "test",
        },
    )
    sid = create.json()["frontmatter"]["id"]
    r = await c.post(f"/suggestions/{sid}/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["operation"] == "merge_entities"
    assert (vault / "wiki/entities/foobar.md").exists()


async def test_approve_already_approved(client):
    c, vault = client
    _write_page(vault, "wiki/entities/foo.md")
    _write_page(vault, "wiki/entities/bar.md")
    create = await c.post(
        "/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md", "wiki/entities/bar.md"],
            "proposed_target": "wiki/entities/x.md",
        },
    )
    sid = create.json()["frontmatter"]["id"]
    r1 = await c.post(f"/suggestions/{sid}/approve")
    assert r1.status_code == 200
    r2 = await c.post(f"/suggestions/{sid}/approve")
    assert r2.status_code == 409
    assert r2.json()["error"] == "ontology_apply_failed"


async def test_approve_404_unknown(client):
    c, _ = client
    r = await c.post("/suggestions/ont-2026-04-26-zzzzzz/approve")
    assert r.status_code == 409  # OntologyError("not found")
    assert r.json()["error"] == "ontology_apply_failed"


async def test_reject_happy(client):
    c, vault = client
    store = SuggestionStore(vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    r = await c.post("/suggestions/ont-2026-04-26-aaaaaa/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    reloaded = store.get("ont-2026-04-26-aaaaaa")
    assert reloaded is not None
    assert reloaded.frontmatter.status == "rejected"


async def test_defer_happy(client):
    c, vault = client
    store = SuggestionStore(vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    r = await c.post("/suggestions/ont-2026-04-26-aaaaaa/defer")
    assert r.status_code == 200
    assert r.json()["status"] == "deferred"


async def test_reject_404(client):
    c, _ = client
    r = await c.post("/suggestions/ont-2026-04-26-zzzzzz/reject")
    assert r.status_code == 404
