"""REST tests for /ontology/{project}/... routes (Plan #13b-β2 Task 7)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.ontology import (
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
)

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


class _FakeRuntime:
    """Minimal VaultRuntime shim for ontology route tests."""

    def __init__(self, vault: Path) -> None:
        self.vault_root = vault
        self.tracker = OurWritesTracker(ttl_s=60.0)


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
# Helpers
# ---------------------------------------------------------------------------


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
            affected_pages=affected
            or [
                "wiki/entities/foo.md",
                "wiki/entities/bar.md",
            ],
            proposed_target=target,
        ),
        body="reason",
    )


# ---------------------------------------------------------------------------
# POST /ontology/{project}/run
# ---------------------------------------------------------------------------


async def test_run_happy(client: Any) -> None:
    r = await client.post("/ontology/alpha/run")
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_run_unknown_project_404(client: Any) -> None:
    r = await client.post("/ontology/unknown/run")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /ontology/{project}/suggestions
# ---------------------------------------------------------------------------


async def test_list_empty(client: Any) -> None:
    r = await client.get("/ontology/alpha/suggestions")
    assert r.status_code == 200
    assert r.json() == {"suggestions": [], "total": 0}


async def test_list_unknown_project_404(client: Any) -> None:
    r = await client.get("/ontology/unknown/suggestions")
    assert r.status_code == 404


async def test_list_pending_only_by_default(client: Any, alpha_vault: Path) -> None:
    store = SuggestionStore(alpha_vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    store.create(_suggestion(sid="ont-2026-04-26-bbbbbb"))
    store.archive_suggestion("ont-2026-04-26-bbbbbb")

    r = await client.get("/ontology/alpha/suggestions")
    body = r.json()
    assert body["total"] == 1


async def test_list_all_status(client: Any, alpha_vault: Path) -> None:
    store = SuggestionStore(alpha_vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    store.create(_suggestion(sid="ont-2026-04-26-bbbbbb"))
    store.archive_suggestion("ont-2026-04-26-bbbbbb")

    r = await client.get("/ontology/alpha/suggestions?status=all")
    body = r.json()
    assert body["total"] == 2


# ---------------------------------------------------------------------------
# POST /ontology/{project}/suggestions/{id}/approve
# ---------------------------------------------------------------------------


async def test_approve_happy(client: Any, alpha_vault: Path) -> None:
    _write_page(alpha_vault, "wiki/entities/foo.md", body="A")
    _write_page(alpha_vault, "wiki/entities/bar.md", body="B")

    create = await client.post(
        "/ontology/alpha/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md", "wiki/entities/bar.md"],
            "proposed_target": "wiki/entities/foobar.md",
            "reason": "test",
        },
    )
    assert create.status_code == 201
    sid = create.json()["frontmatter"]["id"]

    r = await client.post(f"/ontology/alpha/suggestions/{sid}/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["operation"] == "merge_entities"
    assert (alpha_vault / "wiki/entities/foobar.md").exists()


async def test_approve_already_approved(client: Any, alpha_vault: Path) -> None:
    _write_page(alpha_vault, "wiki/entities/foo.md")
    _write_page(alpha_vault, "wiki/entities/bar.md")
    create = await client.post(
        "/ontology/alpha/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md", "wiki/entities/bar.md"],
            "proposed_target": "wiki/entities/x.md",
        },
    )
    assert create.status_code == 201
    sid = create.json()["frontmatter"]["id"]
    r1 = await client.post(f"/ontology/alpha/suggestions/{sid}/approve")
    assert r1.status_code == 200
    r2 = await client.post(f"/ontology/alpha/suggestions/{sid}/approve")
    assert r2.status_code == 409
    assert r2.json()["error"] == "ontology_apply_failed"


async def test_approve_unknown_project_404(client: Any) -> None:
    r = await client.post("/ontology/unknown/suggestions/ont-2026-04-26-aaaaaa/approve")
    assert r.status_code == 404


async def test_approve_unknown_suggestion_409(client: Any) -> None:
    r = await client.post("/ontology/alpha/suggestions/ont-2026-04-26-zzzzzz/approve")
    assert r.status_code == 409
    assert r.json()["error"] == "ontology_apply_failed"


# ---------------------------------------------------------------------------
# POST /ontology/{project}/suggestions/{id}/reject
# ---------------------------------------------------------------------------


async def test_reject_happy(client: Any, alpha_vault: Path) -> None:
    store = SuggestionStore(alpha_vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    r = await client.post("/ontology/alpha/suggestions/ont-2026-04-26-aaaaaa/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    reloaded = store.get("ont-2026-04-26-aaaaaa")
    assert reloaded is not None
    assert reloaded.frontmatter.status == "rejected"


async def test_reject_404(client: Any) -> None:
    r = await client.post("/ontology/alpha/suggestions/ont-2026-04-26-zzzzzz/reject")
    assert r.status_code == 404


async def test_reject_unknown_project_404(client: Any) -> None:
    r = await client.post("/ontology/unknown/suggestions/ont-2026-04-26-aaaaaa/reject")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /ontology/{project}/suggestions/{id}/defer
# ---------------------------------------------------------------------------


async def test_defer_happy(client: Any, alpha_vault: Path) -> None:
    store = SuggestionStore(alpha_vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    r = await client.post("/ontology/alpha/suggestions/ont-2026-04-26-aaaaaa/defer")
    assert r.status_code == 200
    assert r.json()["status"] == "deferred"


async def test_defer_unknown_project_404(client: Any) -> None:
    r = await client.post("/ontology/unknown/suggestions/ont-2026-04-26-aaaaaa/defer")
    assert r.status_code == 404


async def test_defer_404(client: Any) -> None:
    r = await client.post("/ontology/alpha/suggestions/ont-2026-04-26-zzzzzz/defer")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /ontology/{project}/suggestions/{id}
# ---------------------------------------------------------------------------


async def test_patch_happy(client: Any, alpha_vault: Path) -> None:
    store = SuggestionStore(alpha_vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    r = await client.patch(
        "/ontology/alpha/suggestions/ont-2026-04-26-aaaaaa",
        json={"reason": "updated reason", "confidence": 0.9},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["frontmatter"]["reason"] == "updated reason"
    assert body["frontmatter"]["confidence"] == pytest.approx(0.9)


async def test_patch_body_only(client: Any, alpha_vault: Path) -> None:
    store = SuggestionStore(alpha_vault)
    store.create(_suggestion(sid="ont-2026-04-26-aaaaaa"))
    r = await client.patch(
        "/ontology/alpha/suggestions/ont-2026-04-26-aaaaaa",
        json={"body": "new body text"},
    )
    assert r.status_code == 200
    assert r.json()["body"] == "new body text"


async def test_patch_404(client: Any) -> None:
    r = await client.patch(
        "/ontology/alpha/suggestions/ont-2026-04-26-zzzzzz",
        json={"reason": "x"},
    )
    assert r.status_code == 404


async def test_patch_unknown_project_404(client: Any) -> None:
    r = await client.patch(
        "/ontology/unknown/suggestions/ont-2026-04-26-aaaaaa",
        json={"reason": "x"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /ontology/{project}/suggestions  (create)
# ---------------------------------------------------------------------------


async def test_create_merge_happy(client: Any, alpha_vault: Path) -> None:
    _write_page(alpha_vault, "wiki/entities/foo.md")
    _write_page(alpha_vault, "wiki/entities/bar.md")

    r = await client.post(
        "/ontology/alpha/suggestions",
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


async def test_create_merge_missing_target(client: Any) -> None:
    r = await client.post(
        "/ontology/alpha/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md", "wiki/entities/bar.md"],
        },
    )
    assert r.status_code == 422


async def test_create_merge_one_source(client: Any) -> None:
    r = await client.post(
        "/ontology/alpha/suggestions",
        json={
            "operation": "merge_entities",
            "affected_pages": ["wiki/entities/foo.md"],
            "proposed_target": "wiki/entities/x.md",
        },
    )
    assert r.status_code == 422


async def test_create_invalid_operation(client: Any) -> None:
    r = await client.post(
        "/ontology/alpha/suggestions",
        json={"operation": "weird", "affected_pages": ["x.md"]},
    )
    assert r.status_code == 422


async def test_create_unknown_project_404(client: Any) -> None:
    r = await client.post(
        "/ontology/unknown/suggestions",
        json={
            "operation": "delete_page",
            "affected_pages": ["wiki/entities/foo.md"],
        },
    )
    assert r.status_code == 404
