from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.core.snapshots import create_snapshot_at
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker


class _FakeRuntime:
    def __init__(self, vault: Path) -> None:
        self.vault_root = vault
        self.tracker = OurWritesTracker(ttl_s=60.0)


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


async def test_preview_happy(client: Any, alpha_vault: Path) -> None:
    snap_path = alpha_vault / ".backups" / "manual-2026-05-20-10-00-00"
    create_snapshot_at(
        alpha_vault,
        snap_path,
        operation_id="test",
        operation_type="manual",
    )
    r = await client.get("/api/snapshots/alpha/manual-2026-05-20-10-00-00/preview")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_name"] == "manual-2026-05-20-10-00-00"
    assert body["snapshot_kind"] == "manual"


async def test_preview_unknown_project_404(client: Any) -> None:
    r = await client.get("/api/snapshots/unknown/manual-2026-05-20-10-00-00/preview")
    assert r.status_code == 404


async def test_preview_unknown_snapshot_404(client: Any, alpha_vault: Path) -> None:
    r = await client.get("/api/snapshots/alpha/manual-2026-05-20-10-00-00/preview")
    assert r.status_code == 404
