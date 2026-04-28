"""REST tests for /trash/{project}/... routes (Plan #13b-β2 Task 5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.core.page_apply import apply_soft_delete
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker


class _FakeRuntime:
    """Minimal VaultRuntime shim for trash route tests."""

    def __init__(self, vault: Path) -> None:
        self.vault_root = vault
        self.tracker = OurWritesTracker(ttl_s=60.0)


class _FakeDaemon:
    def __init__(self, alpha_vault: Path) -> None:
        self._alpha_runtime = _FakeRuntime(alpha_vault)
        self.runtimes: dict[str, Any] = {"alpha": self._alpha_runtime}
        self.started_at_monotonic = 0.0

    def scheduler_jobs_info(self) -> list[Any]:
        return []


def _seed(vault: Path, rel: str = "wiki/entities/foo.md") -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: Foo\ntype: entity\nstatus: draft\nconfidence: 0.7\n"
        "flavor: []\nsources: []\nrelated: []\n"
        "created: 2026-04-26\nupdated: 2026-04-26\n"
        "agent_written: true\n---\noriginal body\n",
        encoding="utf-8",
    )
    return p


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
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app: Any) -> Any:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /trash/{project}
# ---------------------------------------------------------------------------


async def test_get_empty_list(client: Any) -> None:
    r = await client.get("/trash/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body == {"entries": [], "total": 0}


async def test_get_with_entries(client: Any, alpha_vault: Path) -> None:
    p = _seed(alpha_vault)
    apply_soft_delete(alpha_vault, p)
    r = await client.get("/trash/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["trash_id"].startswith("deleted-foo-")
    assert entry["original_path"] == "wiki/entities/foo.md"
    assert entry["restorable"] is True


async def test_get_unknown_project_404(client: Any) -> None:
    r = await client.get("/trash/unknown_project")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /trash/{project}/{id}/restore
# ---------------------------------------------------------------------------


async def test_post_restore_success(client: Any, alpha_vault: Path) -> None:
    p = _seed(alpha_vault)
    delete = apply_soft_delete(alpha_vault, p)
    assert not p.exists()
    r = await client.post(f"/trash/alpha/{delete.trash_id}/restore")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["restored_path"] == "wiki/entities/foo.md"
    assert body["activity_id"]
    # Page is back at original path; trash dir gone.
    assert p.exists()
    assert not (alpha_vault / ".trash" / delete.trash_id).exists()


async def test_post_restore_collision_returns_409(
    client: Any, alpha_vault: Path
) -> None:
    p = _seed(alpha_vault)
    delete = apply_soft_delete(alpha_vault, p)
    # Recreate at the original path so restore would collide.
    _seed(alpha_vault)
    r = await client.post(f"/trash/alpha/{delete.trash_id}/restore")
    assert r.status_code == 409, r.text


async def test_post_restore_unknown_project_404(client: Any) -> None:
    r = await client.post("/trash/unknown_project/some-id/restore")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /trash/{project}/{id}  — permanent delete (dismiss)
# ---------------------------------------------------------------------------


async def test_delete_one_dismisses(client: Any, alpha_vault: Path) -> None:
    p = _seed(alpha_vault)
    delete = apply_soft_delete(alpha_vault, p)
    r = await client.delete(f"/trash/alpha/{delete.trash_id}")
    assert r.status_code == 204
    assert not (alpha_vault / ".trash" / delete.trash_id).exists()


async def test_delete_one_404(client: Any) -> None:
    r = await client.delete(
        "/trash/alpha/deleted-nonexistent-2026-04-27-12-00-00-aaaaaaaa"
    )
    assert r.status_code == 404


async def test_delete_one_unknown_project_404(client: Any) -> None:
    r = await client.delete("/trash/unknown_project/some-id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /trash/{project}  — empty trash (Tier 2)
# ---------------------------------------------------------------------------


async def test_delete_all_empties(client: Any, alpha_vault: Path) -> None:
    p1 = _seed(alpha_vault, "wiki/entities/foo.md")
    p2 = _seed(alpha_vault, "wiki/entities/bar.md")
    apply_soft_delete(alpha_vault, p1)
    apply_soft_delete(alpha_vault, p2)
    r = await client.delete("/trash/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["removed_count"] == 2
    assert len(body["removed_ids"]) == 2
    assert body["errors"] == []


async def test_delete_all_unknown_project_404(client: Any) -> None:
    r = await client.delete("/trash/unknown_project")
    assert r.status_code == 404
