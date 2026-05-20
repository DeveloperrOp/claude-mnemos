from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker


class _FakeRuntime:
    def __init__(self, vault: Path) -> None:
        self.vault_root = vault
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.lost_sessions_cache = None


class _FakeDaemon:
    def __init__(self, vault: Path) -> None:
        self._alpha_runtime = _FakeRuntime(vault)
        self.runtimes: dict[str, Any] = {"alpha": self._alpha_runtime}
        self.started_at_monotonic = 0.0

    def scheduler_jobs_info(self) -> list[Any]:
        return []


@pytest.fixture
def alpha_vault(tmp_path: Path) -> Path:
    v = tmp_path / "alpha"
    v.mkdir()
    return v


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


def _write_ignore(vault: Path, shas: list[str]) -> None:
    ignore_path = vault / ".lost-sessions-ignore.json"
    ignore_path.write_text(
        json.dumps({"version": 1, "ignored_shas": shas}), encoding="utf-8"
    )


async def test_list_ignored_empty(client: Any) -> None:
    r = await client.get("/api/lost-sessions/ignored")
    assert r.status_code == 200
    body = r.json()
    assert body["ignored"] == []
    assert body["total"] == 0


async def test_list_ignored_with_entries(client: Any, alpha_vault: Path) -> None:
    _write_ignore(alpha_vault, ["sha1", "sha2"])
    r = await client.get("/api/lost-sessions/ignored")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    shas = {item["sha"] for item in body["ignored"]}
    assert shas == {"sha1", "sha2"}


async def test_unignore_selection_happy(client: Any, alpha_vault: Path) -> None:
    _write_ignore(alpha_vault, ["sha1", "sha2", "sha3"])
    r = await client.post(
        "/api/lost-sessions/un-ignore-selection",
        json={"project_name": "alpha", "shas": ["sha1", "sha3"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["removed"] == 2
    assert body["ignored_count"] == 1


async def test_unignore_unknown_project_404(client: Any) -> None:
    r = await client.post(
        "/api/lost-sessions/un-ignore-selection",
        json={"project_name": "nonexistent", "shas": ["sha1"]},
    )
    assert r.status_code == 404


async def test_unignore_missing_project_422(client: Any) -> None:
    r = await client.post(
        "/api/lost-sessions/un-ignore-selection",
        json={"shas": ["sha1"]},
    )
    assert r.status_code == 422
