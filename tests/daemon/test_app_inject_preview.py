"""REST tests for /api/projects/{name}/inject-preview."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.routes import inject_preview as inject_preview_module
from claude_mnemos.state.manifest import IngestRecord, Manifest
from claude_mnemos.state.projects import ProjectMapEntry

_PROJECT = "alpha"


class _FakeRuntime:
    def __init__(self, vault: Path) -> None:
        self.name = _PROJECT
        self.vault_root = vault
        self.project = ProjectMapEntry(
            name=_PROJECT,
            display_name=_PROJECT,
            vault_root=vault,
            cwd_patterns=[str(vault.parent / "code")],
        )


class _FakeDaemon:
    def __init__(self, vault: Path) -> None:
        self._runtime = _FakeRuntime(vault)
        self.runtimes: dict[str, _FakeRuntime] = {_PROJECT: self._runtime}


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """Reset the per-project TTLCache between tests so cache-hit assertions
    are deterministic."""
    inject_preview_module._PROJECT_CACHES.clear()


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    (v / "wiki").mkdir(parents=True)
    return v


def _write_page(vault: Path, slug: str, body: str = "alpha body") -> None:
    page_path = vault / "wiki" / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        "---\n"
        f"title: {slug}\n"
        "type: concept\n"
        "status: draft\n"
        "confidence: 0.7\n"
        "flavor: []\n"
        "sources: []\n"
        "related: []\n"
        "created: 2026-04-29\n"
        "updated: 2026-04-29\n"
        "agent_written: true\n"
        "---\n"
    )
    page_path.write_text(fm + body, encoding="utf-8")


def _seed_manifest(vault: Path, pages: list[str]) -> None:
    records = {
        "s1": IngestRecord(
            session_id="s1",
            ingested_at=datetime.now(UTC),
            raw_path="raw/s1.md",
            source_path=None,
            created_pages=pages,
            skipped_collisions=[],
            model=None,
            input_tokens=None,
            output_tokens=None,
        )
    }
    manifest = Manifest(ingested=records)
    atomic_write(vault / ".manifest.json", manifest.serialize_to_string())


@pytest.fixture
def app(vault: Path):
    daemon = _FakeDaemon(vault)
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_inject_preview_returns_expected_shape(
    client: httpx.AsyncClient, vault: Path
) -> None:
    _write_page(vault, "concepts/a", body="alpha body content")
    _seed_manifest(vault, ["wiki/concepts/a.md"])

    r = await client.get(f"/api/projects/{_PROJECT}/inject-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    # Top-level keys per spec.
    assert set(body.keys()) == {
        "tokens_estimate",
        "limit",
        "ratio",
        "pages",
        "preview_text",
        "computed_at",
    }
    assert isinstance(body["tokens_estimate"], int)
    assert body["limit"] > 0
    assert isinstance(body["ratio"], (int, float))
    assert isinstance(body["pages"], list)
    assert isinstance(body["preview_text"], str)
    # ISO 8601 UTC.
    assert body["computed_at"].endswith("Z")
    # Page list items have the documented fields.
    assert len(body["pages"]) >= 1
    page0 = body["pages"][0]
    assert page0["slug"] == "concepts/a"
    assert page0["path"] == "wiki/concepts/a.md"
    assert isinstance(page0["score"], (int, float))
    assert page0["included"] is True
    assert "concepts/a" in body["preview_text"]


async def test_inject_preview_empty_vault_returns_zeros(
    client: httpx.AsyncClient, vault: Path
) -> None:
    # No pages, no manifest.
    r = await client.get(f"/api/projects/{_PROJECT}/inject-preview")
    assert r.status_code == 200
    body = r.json()
    assert body["tokens_estimate"] == 0
    assert body["pages"] == []
    assert body["preview_text"] == ""


async def test_inject_preview_unknown_project_returns_404(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get("/api/projects/no-such-project/inject-preview")
    assert r.status_code == 404
    body = r.json()
    assert body["detail"]["error"] == "unknown_project"


async def test_inject_preview_uses_ttl_cache(
    client: httpx.AsyncClient, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two consecutive calls within the TTL window only run the compute once."""
    _write_page(vault, "concepts/a", body="alpha")
    _seed_manifest(vault, ["wiki/concepts/a.md"])

    calls = {"n": 0}
    real = inject_preview_module._compute_preview_sync

    def _spy(v: Path, cwd: Path) -> dict[str, Any]:
        calls["n"] += 1
        return real(v, cwd)

    monkeypatch.setattr(inject_preview_module, "_compute_preview_sync", _spy)

    r1 = await client.get(f"/api/projects/{_PROJECT}/inject-preview")
    r2 = await client.get(f"/api/projects/{_PROJECT}/inject-preview")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert calls["n"] == 1, "TTLCache should serve the second call from memory"
    # Same payload from cache.
    assert r1.json() == r2.json()
