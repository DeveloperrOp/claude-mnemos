"""REST tests for /pages/{project}/... routes (Plan #13b-β2 Task 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker


class _FakeRuntime:
    """Minimal VaultRuntime shim for pages route tests."""

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
# PATCH /pages/{project}/{page_id}
# ---------------------------------------------------------------------------


async def test_patch_frontmatter_success(client: Any, alpha_vault: Path) -> None:
    _seed(alpha_vault)
    r = await client.patch(
        "/api/pages/alpha/wiki/entities/foo.md",
        json={"frontmatter": {"status": "verified"}, "body": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["activity_id"]
    assert body["snapshot_path"]
    # Verify the on-disk file was updated.
    from claude_mnemos.core.page_io import read_page
    parsed = read_page(alpha_vault / "wiki/entities/foo.md")
    assert parsed.frontmatter.status == "verified"


async def test_get_page_returns_version(client: Any, alpha_vault: Path) -> None:
    _seed(alpha_vault)
    r = await client.get("/api/pages/alpha/wiki/entities/foo.md")
    assert r.status_code == 200, r.text
    assert r.json()["version"], "GET must expose a content version for optimistic concurrency"


async def test_patch_with_matching_base_version_succeeds(
    client: Any, alpha_vault: Path
) -> None:
    _seed(alpha_vault)
    version = (await client.get("/api/pages/alpha/wiki/entities/foo.md")).json()["version"]
    r = await client.patch(
        "/api/pages/alpha/wiki/entities/foo.md",
        json={"frontmatter": {"status": "verified"}, "body": None, "base_version": version},
    )
    assert r.status_code == 200, r.text


async def test_patch_with_stale_base_version_returns_409(
    client: Any, alpha_vault: Path
) -> None:
    """Editor opened the page, then an extract job rewrote it. Saving with the
    now-stale version must 409, not silently overwrite the newer content."""
    _seed(alpha_vault)
    r = await client.patch(
        "/api/pages/alpha/wiki/entities/foo.md",
        json={
            "frontmatter": {"status": "verified"},
            "body": None,
            "base_version": "deadbeef-stale-version",
        },
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "stale_page"


async def test_patch_without_base_version_still_works(
    client: Any, alpha_vault: Path
) -> None:
    """Backward-compat: omitting base_version skips the concurrency check."""
    _seed(alpha_vault)
    r = await client.patch(
        "/api/pages/alpha/wiki/entities/foo.md",
        json={"frontmatter": {"status": "verified"}, "body": None},
    )
    assert r.status_code == 200, r.text


async def test_patch_invalid_value_returns_422(client: Any, alpha_vault: Path) -> None:
    _seed(alpha_vault)
    r = await client.patch(
        "/api/pages/alpha/wiki/entities/foo.md",
        json={"frontmatter": {"status": "not_a_status"}, "body": None},
    )
    assert r.status_code == 422, r.text


async def test_patch_unknown_project_returns_404(client: Any) -> None:
    r = await client.patch(
        "/api/pages/unknown-project/wiki/entities/foo.md",
        json={"frontmatter": {"status": "verified"}, "body": None},
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_project"


async def test_patch_unknown_page_returns_404(client: Any, alpha_vault: Path) -> None:
    r = await client.patch(
        "/api/pages/alpha/wiki/entities/nonexistent.md",
        json={"frontmatter": {"status": "verified"}, "body": None},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# POST /pages/{project}/{page_id}/verify
# ---------------------------------------------------------------------------


async def test_post_verify_sets_verified_status(client: Any, alpha_vault: Path) -> None:
    _seed(alpha_vault)
    r = await client.post("/api/pages/alpha/wiki/entities/foo.md/verify")
    assert r.status_code == 200, r.text
    from claude_mnemos.core.page_io import read_page
    parsed = read_page(alpha_vault / "wiki/entities/foo.md")
    assert parsed.frontmatter.status == "verified"


async def test_verify_unknown_project_returns_404(client: Any) -> None:
    r = await client.post("/api/pages/unknown-project/wiki/entities/foo.md/verify")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# POST /pages/{project}/{page_id}/archive
# ---------------------------------------------------------------------------


async def test_post_archive_sets_archived_status(client: Any, alpha_vault: Path) -> None:
    _seed(alpha_vault)
    r = await client.post("/api/pages/alpha/wiki/entities/foo.md/archive")
    assert r.status_code == 200, r.text
    from claude_mnemos.core.page_io import read_page
    parsed = read_page(alpha_vault / "wiki/entities/foo.md")
    assert parsed.frontmatter.status == "archived"


async def test_archive_unknown_project_returns_404(client: Any) -> None:
    r = await client.post("/api/pages/unknown-project/wiki/entities/foo.md/archive")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# DELETE /pages/{project}/{page_id}
# ---------------------------------------------------------------------------


async def test_delete_creates_trash_entry(client: Any, alpha_vault: Path) -> None:
    p = _seed(alpha_vault)
    r = await client.delete("/api/pages/alpha/wiki/entities/foo.md")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["trash_id"]
    assert body["activity_id"]
    assert body["snapshot_path"]
    # Original file is gone, trash dir exists.
    assert not p.exists()
    trash_root = alpha_vault / ".trash"
    assert trash_root.is_dir()
    assert any(d.name == body["trash_id"] for d in trash_root.iterdir() if d.is_dir())


async def test_delete_unknown_project_returns_404(client: Any) -> None:
    r = await client.delete("/api/pages/unknown-project/wiki/entities/foo.md")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# GET /pages/{project}/{page_id}/backlinks
# ---------------------------------------------------------------------------


async def test_backlinks_unknown_project_returns_404(client: Any) -> None:
    r = await client.get("/api/pages/unknown-project/wiki/entities/foo.md/backlinks")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_project"


async def test_backlinks_unknown_page_returns_404(client: Any, alpha_vault: Path) -> None:
    r = await client.get("/api/pages/alpha/wiki/entities/nonexistent.md/backlinks")
    assert r.status_code == 404, r.text


async def test_backlinks_empty_for_isolated_page(client: Any, alpha_vault: Path) -> None:
    _seed(alpha_vault)
    r = await client.get("/api/pages/alpha/wiki/entities/foo.md/backlinks")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "backlinks" in body
    assert body["backlinks"] == []


# ---------------------------------------------------------------------------
# GET /pages/{project}  (list)
# ---------------------------------------------------------------------------


async def test_list_pages_unknown_project_returns_404(client: Any) -> None:
    r = await client.get("/api/pages/unknown-project")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_project"


async def test_list_pages_empty_vault(client: Any) -> None:
    r = await client.get("/api/pages/alpha")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pages" in body
    assert body["pages"] == []


async def test_list_pages_returns_seeded_page(client: Any, alpha_vault: Path) -> None:
    _seed(alpha_vault)
    r = await client.get("/api/pages/alpha")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["pages"]) == 1
    assert "wiki/entities/foo.md" in body["pages"][0]


# ---------------------------------------------------------------------------
# GET /pages/{project}/{page_id}  (show)
# ---------------------------------------------------------------------------


async def test_get_page_unknown_project_returns_404(client: Any) -> None:
    r = await client.get("/api/pages/unknown-project/wiki/entities/foo.md")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_project"


async def test_get_page_unknown_page_returns_404(client: Any, alpha_vault: Path) -> None:
    r = await client.get("/api/pages/alpha/wiki/entities/nonexistent.md")
    assert r.status_code == 404, r.text


async def test_get_page_returns_content(client: Any, alpha_vault: Path) -> None:
    _seed(alpha_vault)
    r = await client.get("/api/pages/alpha/wiki/entities/foo.md")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "wiki/entities/foo.md"
    assert "frontmatter" in body
    assert "body" in body
    assert body["frontmatter"]["title"] == "Foo"
    assert body.get("raw") is False


async def test_get_raw_chat_page_returns_null_frontmatter(
    client: Any, alpha_vault: Path
) -> None:
    """Raw chat dumps under raw/chats/ have no YAML frontmatter; the route must
    return a graceful raw form instead of raising 500 (PageParseError)."""
    raw = alpha_vault / "raw" / "chats" / "session-2026-04-29.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("# Chat dump\n\njust some markdown without frontmatter\n", encoding="utf-8")
    r = await client.get("/api/pages/alpha/raw/chats/session-2026-04-29.md")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "raw/chats/session-2026-04-29.md"
    assert body["frontmatter"] is None
    assert body["raw"] is True
    assert "Chat dump" in body["body"]
