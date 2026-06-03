"""REST tests for /lint/{project}/... routes (Plan #13b-β2 Task 6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.settings import LintSettings, ProjectSettings


class _FakeRuntime:
    """Minimal VaultRuntime shim for lint route tests."""

    def __init__(self, vault: Path, enabled_rules: list[str] | None = None) -> None:
        self.vault_root = vault
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.settings = ProjectSettings(lint=LintSettings(enabled_rules=enabled_rules))


class _FakeDaemon:
    def __init__(self, alpha_vault: Path) -> None:
        self._alpha_runtime = _FakeRuntime(alpha_vault)
        self.runtimes: dict[str, Any] = {"alpha": self._alpha_runtime}
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
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app: Any) -> Any:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /lint/{project}/results
# ---------------------------------------------------------------------------


async def test_results_404_when_no_run(client: Any) -> None:
    r = await client.get("/api/lint/alpha/results")
    assert r.status_code == 404


async def test_results_unknown_project_404(client: Any) -> None:
    r = await client.get("/api/lint/unknown_project/results")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /lint/{project}/run
# ---------------------------------------------------------------------------


async def test_run_then_results_round_trip(client: Any) -> None:
    r = await client.post("/api/lint/alpha/run")
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert "summary" in body

    r = await client.get("/api/lint/alpha/results")
    assert r.status_code == 200
    assert r.json()["run_id"] == body["run_id"]


async def test_run_unknown_project_404(client: Any) -> None:
    r = await client.post("/api/lint/unknown_project/run")
    assert r.status_code == 404


async def test_run_respects_enabled_rules(tmp_path: Path) -> None:
    # Vault with two orphan pages (would trip orphan_pages) + one broken
    # page (page_parse_failed). enabled_rules restricts to page_parse_failed.
    vault = tmp_path / "beta"
    vault.mkdir()
    for rel in ("wiki/entities/foo.md", "wiki/entities/bar.md"):
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "---\ntitle: T\ntype: entity\ncreated: 2026-04-26\nupdated: 2026-04-26\n"
            "agent_written: true\n---\nbody\n",
            encoding="utf-8",
        )
    (vault / "wiki/entities/broken.md").write_text("invalid", encoding="utf-8")

    daemon = _FakeDaemon(vault)
    daemon.runtimes = {"alpha": _FakeRuntime(vault, enabled_rules=["page_parse_failed"])}
    app = create_app(daemon=daemon)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/lint/alpha/run")
        assert r.status_code == 200
        rule_ids = {f["rule_id"] for f in r.json()["findings"]}
        assert "page_parse_failed" in rule_ids
        assert "orphan_pages" not in rule_ids


# ---------------------------------------------------------------------------
# POST /lint/{project}/autofix
# ---------------------------------------------------------------------------


async def test_autofix_409_without_cached_run(client: Any) -> None:
    r = await client.post("/api/lint/alpha/autofix")
    assert r.status_code == 409


async def test_autofix_unknown_project_404(client: Any) -> None:
    r = await client.post("/api/lint/unknown_project/autofix")
    assert r.status_code == 404


async def test_autofix_after_run(client: Any, alpha_vault: Path) -> None:
    p = alpha_vault / "wiki/entities/foo.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: T\ntype: entity\ncreated: 2026-04-26\nupdated: 2026-04-26\n"
        "agent_written: true\n---\nbody  \n",
        encoding="utf-8",
    )

    r = await client.post("/api/lint/alpha/run")
    assert r.status_code == 200

    r = await client.post("/api/lint/alpha/autofix")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["snapshot_path"]
    assert body["activity_id"]
    assert "body  " not in (alpha_vault / "wiki/entities/foo.md").read_text(encoding="utf-8")
