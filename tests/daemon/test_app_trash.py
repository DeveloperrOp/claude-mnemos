"""Tests for Plan #12 REST /trash/* routes."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.core.page_apply import apply_soft_delete
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker


class _FakeDaemon:
    def __init__(self) -> None:
        self.alerts = Alerts()
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.started_at_monotonic = 0.0

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


async def test_get_empty_list(client):
    r = await client.get("/trash")
    assert r.status_code == 200
    body = r.json()
    assert body == {"entries": [], "total": 0}


async def test_get_with_entries(client, tmp_path: Path):
    p = _seed(tmp_path)
    apply_soft_delete(tmp_path, p)
    r = await client.get("/trash")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["trash_id"].startswith("deleted-foo-")
    assert entry["original_path"] == "wiki/entities/foo.md"
    assert entry["restorable"] is True


async def test_get_by_id(client, tmp_path: Path):
    p = _seed(tmp_path)
    delete = apply_soft_delete(tmp_path, p)
    r = await client.get(f"/trash/{delete.trash_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["trash_id"] == delete.trash_id
    assert body["original_path"] == "wiki/entities/foo.md"


async def test_get_by_id_404(client):
    r = await client.get("/trash/deleted-nonexistent-2026-04-27-12-00-00-aaaaaaaa")
    assert r.status_code == 404


async def test_post_restore_success(client, tmp_path: Path):
    p = _seed(tmp_path)
    delete = apply_soft_delete(tmp_path, p)
    assert not p.exists()
    r = await client.post(f"/trash/{delete.trash_id}/restore")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["restored_path"] == "wiki/entities/foo.md"
    assert body["activity_id"]
    # Page is back at original path; trash dir gone.
    assert p.exists()
    assert not (tmp_path / ".trash" / delete.trash_id).exists()


async def test_post_restore_collision_returns_409(client, tmp_path: Path):
    p = _seed(tmp_path)
    delete = apply_soft_delete(tmp_path, p)
    # Recreate at the original path so restore would collide.
    _seed(tmp_path)
    r = await client.post(f"/trash/{delete.trash_id}/restore")
    assert r.status_code == 409, r.text


async def test_delete_one_dismisses(client, tmp_path: Path):
    p = _seed(tmp_path)
    delete = apply_soft_delete(tmp_path, p)
    r = await client.delete(f"/trash/{delete.trash_id}")
    assert r.status_code == 204
    assert not (tmp_path / ".trash" / delete.trash_id).exists()


async def test_delete_one_404(client):
    r = await client.delete("/trash/deleted-nonexistent-2026-04-27-12-00-00-aaaaaaaa")
    assert r.status_code == 404


async def test_delete_all_empties(client, tmp_path: Path):
    p1 = _seed(tmp_path, "wiki/entities/foo.md")
    p2 = _seed(tmp_path, "wiki/entities/bar.md")
    apply_soft_delete(tmp_path, p1)
    apply_soft_delete(tmp_path, p2)
    r = await client.delete("/trash")
    assert r.status_code == 200
    body = r.json()
    assert body["removed_count"] == 2
    assert len(body["removed_ids"]) == 2
    assert body["errors"] == []
