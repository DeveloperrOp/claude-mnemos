"""REST tests for /snapshots/{project}/... routes (Plan #13b-β2 Task 3)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.config import Config
from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter
from claude_mnemos.core.snapshots import (
    create_daily_snapshot,
    create_manual_snapshot,
    create_snapshot,
)
from claude_mnemos.daemon.app import create_app
from claude_mnemos.ingest.extraction import ExtractionResult
from claude_mnemos.ingest.pipeline import ingest
from claude_mnemos.state.activity import ActivityLog


class _FakeRuntime:
    """Minimal VaultRuntime shim for snapshot route tests."""

    def __init__(self, vault: Path) -> None:
        self.vault_root = vault

    async def restore_with_quiesce(self, snapshot: Path) -> Any:
        # No open jobs.db in the shim — just run the real core swap.
        from claude_mnemos.core.snapshots import restore_from_snapshot

        return restore_from_snapshot(self.vault_root, snapshot)


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
# List
# ---------------------------------------------------------------------------

async def test_list_snapshots_empty(client: Any) -> None:
    r = await client.get("/api/snapshots/alpha")
    assert r.status_code == 200
    assert r.json() == {"snapshots": []}


async def test_list_snapshots_returns_three_kinds(client: Any, alpha_vault: Path) -> None:
    create_snapshot(alpha_vault, operation_id="abc", operation_type="ingest_extracted")
    create_daily_snapshot(alpha_vault, date(2026, 4, 26))
    create_manual_snapshot(alpha_vault, label="release")

    r = await client.get("/api/snapshots/alpha")
    body = r.json()
    assert len(body["snapshots"]) == 3
    kinds = {s["kind"] for s in body["snapshots"]}
    assert kinds == {"pre-op", "daily", "manual"}


async def test_list_snapshots_unknown_project_404(client: Any) -> None:
    r = await client.get("/api/snapshots/ghost")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def test_create_manual_snapshot_no_body(client: Any, alpha_vault: Path) -> None:
    r = await client.post("/api/snapshots/alpha", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "manual"
    assert body["name"].startswith("manual-")
    assert (alpha_vault / ".backups" / body["name"]).is_dir()


async def test_create_manual_snapshot_with_label(client: Any) -> None:
    r = await client.post("/api/snapshots/alpha", json={"label": "release-1"})
    assert r.status_code == 201
    assert r.json()["label"] == "release-1"


async def test_create_manual_snapshot_traversal_label_rejected(client: Any) -> None:
    """Label that sanitizes to empty must return 400."""
    r = await client.post("/api/snapshots/alpha", json={"label": "///"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_name"


async def test_create_snapshot_unknown_project_404(client: Any) -> None:
    r = await client.post("/api/snapshots/ghost", json={})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def test_delete_snapshot_known(client: Any, alpha_vault: Path) -> None:
    snap = create_daily_snapshot(alpha_vault, date(2026, 4, 26))

    r = await client.request("DELETE", f"/api/snapshots/alpha/{snap.name}")
    assert r.status_code == 200
    assert r.json()["deleted"] == snap.name
    assert not snap.exists()


async def test_delete_snapshot_missing_returns_404(client: Any) -> None:
    r = await client.request("DELETE", "/api/snapshots/alpha/daily-2026-01-01")
    assert r.status_code == 404


def test_delete_snapshot_traversal_rejected():
    """Validator rejects path-traversal segments. Tested at the validator
    level rather than over HTTP because httpx percent-decodes the URL
    before the ASGI app sees it, which makes the routing path the actual
    test variable instead of the validator behaviour we care about.
    """
    import pytest as pt
    from fastapi import HTTPException

    from claude_mnemos.daemon.routes.snapshots import _validate_snapshot_name

    bad_names = ["../etc-passwd", "../../foo", "foo/../bar", "/abs/path"]
    for name in bad_names:
        with pt.raises(HTTPException) as exc:
            _validate_snapshot_name(name)
        assert exc.value.status_code == 400, f"expected 400 for {name!r}"


async def test_delete_snapshot_unknown_prefix(client: Any, alpha_vault: Path) -> None:
    junk = alpha_vault / ".backups" / "random-stuff"
    junk.mkdir(parents=True)

    r = await client.request("DELETE", "/api/snapshots/alpha/random-stuff")
    assert r.status_code == 400
    assert junk.exists()


async def test_delete_snapshot_unknown_project_404(client: Any) -> None:
    r = await client.request("DELETE", "/api/snapshots/ghost/daily-2026-01-01")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

async def test_restore_snapshot_writes_activity_entry(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    config = Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=150_000,
        lock_timeout=60.0,
    )

    def _stub_extractor():
        def _extract(*, messages, cfg, llm_client, today, chunk_extract=False):  # noqa: ARG001
            fm = WikiPageFrontmatter(
                title="X",
                type="entity",
                flavor=[],
                confidence=0.8,
                related=[],
                created=today,
                updated=today,
            )
            page = WikiPage(
                relative_path=Path("wiki/entities/x.md"),
                frontmatter=fm,
                body="X.",
            )
            return ExtractionResult(
                summary="x", skipped_reason=None, pages=[page],
                input_tokens=10, output_tokens=5,
            )

        return _extract

    fixture = Path(__file__).parent.parent / "fixtures" / "sample_session.jsonl"
    ingest(
        fixture, vault,
        cfg=config, llm_client=MagicMock(),
        extractor=_stub_extractor(), today=date(2026, 4, 26),
    )
    # Now there is one pre-op snapshot from the ingest
    log_before = ActivityLog.load(vault)
    snapshot_name = log_before.entries[0].snapshot_path.split("/")[-1]

    # Wire up with _FakeRuntime/_FakeDaemon pointing at this vault
    runtime = _FakeRuntime(vault)
    daemon: Any = MagicMock()
    daemon.runtimes = {"myvault": runtime}
    daemon.started_at_monotonic = 0.0
    daemon.scheduler_jobs_info.return_value = []

    app = create_app(daemon=daemon)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(f"/api/snapshots/myvault/{snapshot_name}/restore")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["snapshot"] == snapshot_name
    assert body["activity_id"]

    # Vault rolled back: no wiki page anymore
    assert not (vault / "wiki" / "entities" / "x.md").exists()
    # Activity log has manual_restore entry
    log_after = ActivityLog.load(vault)
    assert any(
        e.operation_type == "manual_restore"
        and e.metadata.get("restored_from") == f".backups/{snapshot_name}"
        for e in log_after.entries
    )


async def test_restore_missing_snapshot_returns_404(client: Any) -> None:
    r = await client.post("/api/snapshots/alpha/daily-2099-12-31/restore")
    assert r.status_code == 404


async def test_restore_invalid_name_returns_400(client: Any) -> None:
    r = await client.post("/api/snapshots/alpha/random-stuff/restore")
    assert r.status_code == 400


async def test_restore_snapshot_unknown_project_404(client: Any) -> None:
    r = await client.post("/api/snapshots/ghost/daily-2026-01-01/restore")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


# ---------------------------------------------------------------------------
# Trash (soft-delete recovery) — v0.0.39
# ---------------------------------------------------------------------------

async def test_list_trash_empty(client: Any) -> None:
    r = await client.get("/api/snapshots/alpha/trash")
    assert r.status_code == 200
    assert r.json() == {"snapshots": []}


async def test_list_trash_after_delete(client: Any, alpha_vault: Path) -> None:
    snap = create_daily_snapshot(alpha_vault, date(2026, 4, 26))
    await client.request("DELETE", f"/api/snapshots/alpha/{snap.name}")

    # Gone from the live list...
    live = await client.get("/api/snapshots/alpha")
    assert live.json()["snapshots"] == []
    # ...present in trash under its original name.
    r = await client.get("/api/snapshots/alpha/trash")
    body = r.json()
    assert len(body["snapshots"]) == 1
    assert body["snapshots"][0]["name"] == "daily-2026-04-26"


async def test_restore_from_trash_brings_back(client: Any, alpha_vault: Path) -> None:
    snap = create_daily_snapshot(alpha_vault, date(2026, 4, 26))
    await client.request("DELETE", f"/api/snapshots/alpha/{snap.name}")

    r = await client.post("/api/snapshots/alpha/daily-2026-04-26/restore-from-trash")
    assert r.status_code == 200
    assert r.json()["restored"] == "daily-2026-04-26"
    assert snap.exists()
    trash = await client.get("/api/snapshots/alpha/trash")
    assert trash.json()["snapshots"] == []


async def test_restore_from_trash_missing_404(client: Any) -> None:
    r = await client.post("/api/snapshots/alpha/daily-2099-12-31/restore-from-trash")
    assert r.status_code == 404


async def test_restore_from_trash_conflict_409(client: Any, alpha_vault: Path) -> None:
    snap = create_daily_snapshot(alpha_vault, date(2026, 4, 26))
    await client.request("DELETE", f"/api/snapshots/alpha/{snap.name}")
    # A live snapshot of the same name re-appears before restore.
    create_daily_snapshot(alpha_vault, date(2026, 4, 26))
    r = await client.post("/api/snapshots/alpha/daily-2026-04-26/restore-from-trash")
    assert r.status_code == 409


async def test_restore_from_trash_invalid_name_400(client: Any) -> None:
    r = await client.post("/api/snapshots/alpha/random-stuff/restore-from-trash")
    assert r.status_code == 400


async def test_purge_trash_removes_permanently(client: Any, alpha_vault: Path) -> None:
    snap = create_daily_snapshot(alpha_vault, date(2026, 4, 26))
    await client.request("DELETE", f"/api/snapshots/alpha/{snap.name}")

    r = await client.request(
        "DELETE", "/api/snapshots/alpha/daily-2026-04-26/purge"
    )
    assert r.status_code == 200
    assert r.json()["purged"] == "daily-2026-04-26"
    assert not (alpha_vault / ".backups" / f"_trash-{snap.name}").exists()
    trash = await client.get("/api/snapshots/alpha/trash")
    assert trash.json()["snapshots"] == []


async def test_purge_trash_missing_404(client: Any) -> None:
    r = await client.request(
        "DELETE", "/api/snapshots/alpha/daily-2099-12-31/purge"
    )
    assert r.status_code == 404


async def test_trash_unknown_project_404(client: Any) -> None:
    r = await client.get("/api/snapshots/ghost/trash")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"
