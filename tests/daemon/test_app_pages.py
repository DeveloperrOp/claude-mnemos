"""Tests for Plan #12 REST /pages/* routes."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker


class _FakeDaemon:
    def __init__(self) -> None:
        self.alerts = Alerts()
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.started_at_monotonic = 0.0
        # Routes read tracker from primary_runtime; self-shim preserves behaviour.
        self.primary_runtime = self

    def scheduler_jobs_info(self):
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
def daemon():
    return _FakeDaemon()


@pytest.fixture
def app(tmp_path: Path, daemon: _FakeDaemon):
    return create_app(tmp_path, daemon=daemon)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_patch_frontmatter_success(client, tmp_path: Path):
    _seed(tmp_path)
    r = await client.patch(
        "/pages/wiki/entities/foo.md",
        json={"frontmatter": {"status": "verified"}, "body": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["activity_id"]
    assert body["snapshot_path"]
    # Verify the on-disk file was updated.
    from claude_mnemos.core.page_io import read_page
    parsed = read_page(tmp_path / "wiki/entities/foo.md")
    assert parsed.frontmatter.status == "verified"


async def test_patch_invalid_value_returns_422(client, tmp_path: Path):
    _seed(tmp_path)
    r = await client.patch(
        "/pages/wiki/entities/foo.md",
        json={"frontmatter": {"status": "not_a_status"}, "body": None},
    )
    assert r.status_code == 422, r.text


async def test_post_verify_sets_verified_status(client, tmp_path: Path):
    _seed(tmp_path)
    r = await client.post("/pages/wiki/entities/foo.md/verify")
    assert r.status_code == 200, r.text
    from claude_mnemos.core.page_io import read_page
    parsed = read_page(tmp_path / "wiki/entities/foo.md")
    assert parsed.frontmatter.status == "verified"


async def test_post_archive_sets_archived_status(client, tmp_path: Path):
    _seed(tmp_path)
    r = await client.post("/pages/wiki/entities/foo.md/archive")
    assert r.status_code == 200, r.text
    from claude_mnemos.core.page_io import read_page
    parsed = read_page(tmp_path / "wiki/entities/foo.md")
    assert parsed.frontmatter.status == "archived"


async def test_delete_creates_trash_entry(client, tmp_path: Path):
    p = _seed(tmp_path)
    r = await client.delete("/pages/wiki/entities/foo.md")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["trash_id"]
    assert body["activity_id"]
    assert body["snapshot_path"]
    # Original file is gone, trash dir exists.
    assert not p.exists()
    trash_root = tmp_path / ".trash"
    assert trash_root.is_dir()
    assert any(d.name == body["trash_id"] for d in trash_root.iterdir() if d.is_dir())


async def test_patch_unknown_page_returns_404(client):
    r = await client.patch(
        "/pages/wiki/entities/nonexistent.md",
        json={"frontmatter": {"status": "verified"}, "body": None},
    )
    assert r.status_code == 404, r.text
