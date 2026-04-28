"""Cross-vault tests for /lost-sessions/* routes (Plan #13b-β2 Task 10).

Two vaults are mounted; both vaults scan the same MNEMOS_TRANSCRIPTS_ROOT.
After the β2 migration:
- GET  /lost-sessions       returns merged list; every item has project_name.
- POST /lost-sessions/scan  invalidates all per-vault caches then rescans.
- POST /lost-sessions/{sid}/import  requires body.project_name; routes job to
                             that vault's job_store (not the other vault's).
- POST /lost-sessions/{sid}/ignore  requires body.project_name.
- Missing project_name → 400.
- Unknown project_name  → 404.

Note on scan semantics: ``scan_lost_sessions`` uses a single global
``MNEMOS_TRANSCRIPTS_ROOT`` env var — both vaults scan the same transcript
files, cross-referencing each vault's own manifest and ignore list to decide
what is "lost" *for that vault*.  The cross-vault route aggregates all results
and tags each item with ``project_name`` so the caller knows which vault it
came from.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


# ---------------------------------------------------------------------------
# Shared fixture: two-vault real MnemosDaemon (same pattern as
# test_routes_jobs_routing.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def daemon_with_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[MnemosDaemon, TestClient, Path, Path], None, None]:
    """Yield (daemon, client, vault_alpha, vault_beta) with two vaults mounted."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app) as client:
        vault_a = tmp_path / "vault_alpha"
        vault_b = tmp_path / "vault_beta"
        vault_a.mkdir()
        vault_b.mkdir()
        ra = client.post(
            "/projects",
            json={"name": "alpha", "vault_root": str(vault_a), "cwd_patterns": []},
        )
        assert ra.status_code == 201, ra.text
        rb = client.post(
            "/projects",
            json={"name": "beta", "vault_root": str(vault_b), "cwd_patterns": []},
        )
        assert rb.status_code == 201, rb.text
        yield daemon, client, vault_a, vault_b
    asyncio.run(daemon._shutdown_runtimes())
    if daemon.scheduler.running:
        daemon.scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Helper: create a shared transcripts directory and point the env var at it
# ---------------------------------------------------------------------------


def _make_shared_transcripts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *session_ids: str,
) -> Path:
    """Create a shared transcripts dir with .jsonl files; set MNEMOS_TRANSCRIPTS_ROOT."""
    root = tmp_path / "transcripts"
    root.mkdir(exist_ok=True)
    for sid in session_ids:
        (root / f"{sid}.jsonl").write_text(f"{{\"sid\":\"{sid}\"}}", encoding="utf-8")
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    return root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_lost_sessions_cross_vault(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /lost-sessions aggregates both vaults; every item has project_name.

    Both vaults scan the same transcripts root. The total is
    num_files * num_vaults because each vault sees the same files as "lost"
    (neither has ingested them). Every result item must carry project_name.
    """
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "sess-1", "sess-2")

    r = client.get("/lost-sessions")
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["sessions"]

    # Both vaults contribute — 2 files × 2 vaults = 4 items.
    assert body["total"] == 4

    # Every item must have project_name set.
    project_names = {item["project_name"] for item in items}
    assert project_names == {"alpha", "beta"}

    alpha_items = [i for i in items if i["project_name"] == "alpha"]
    beta_items = [i for i in items if i["project_name"] == "beta"]
    assert len(alpha_items) == 2
    assert len(beta_items) == 2
    assert {i["session_id"] for i in alpha_items} == {"sess-1", "sess-2"}
    assert {i["session_id"] for i in beta_items} == {"sess-1", "sess-2"}


def test_scan_invalidates_all_caches(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /lost-sessions/scan invalidates all per-vault caches and returns fresh list."""
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    tr = _make_shared_transcripts(tmp_path, monkeypatch, "before-1")

    # Warm cache via GET.
    r1 = client.get("/lost-sessions")
    assert r1.json()["total"] >= 1

    # Add a new file; without invalidation the cached count stays old.
    (tr / "after-1.jsonl").write_text("2", encoding="utf-8")

    # POST /scan should see the new file in BOTH vaults.
    r2 = client.post("/lost-sessions/scan")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    session_ids = {i["session_id"] for i in body["sessions"]}
    assert "after-1" in session_ids, f"Expected 'after-1' in {session_ids}"
    # Both vaults see the new file.
    new_for_alpha = [
        i for i in body["sessions"]
        if i["session_id"] == "after-1" and i["project_name"] == "alpha"
    ]
    new_for_beta = [
        i for i in body["sessions"]
        if i["session_id"] == "after-1" and i["project_name"] == "beta"
    ]
    assert len(new_for_alpha) == 1
    assert len(new_for_beta) == 1


def test_import_routes_to_specified_project(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /lost-sessions/{sid}/import with project_name='alpha' creates job in alpha's store."""
    daemon, client, _vault_a, _vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "target")

    r = client.post(
        "/lost-sessions/target/import",
        json={"project_name": "alpha"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "ingest"
    assert body["status"] == "queued"
    assert body["payload"]["transcript_path"].endswith("target.jsonl")

    # Job must be in alpha's store, NOT in beta's store.
    alpha_counts = daemon.runtimes["alpha"].job_store.count_by_status()
    beta_counts = daemon.runtimes["beta"].job_store.count_by_status()
    assert sum(alpha_counts.values()) == 1
    assert sum(beta_counts.values()) == 0


def test_import_missing_project_name_returns_400(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /lost-sessions/{sid}/import without project_name → 400."""
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "orphan")

    r = client.post("/lost-sessions/orphan/import", json={})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"] == "missing_project_name"


def test_import_unknown_project_returns_404(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /lost-sessions/{sid}/import with unknown project_name → 404."""
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "orphan")

    r = client.post(
        "/lost-sessions/orphan/import",
        json={"project_name": "ghost"},
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "unknown_project"


def test_ignore_requires_project_name_400(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /lost-sessions/{sid}/ignore without project_name → 400."""
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "skipme")

    r = client.post("/lost-sessions/skipme/ignore", json={})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"] == "missing_project_name"


def test_ignore_routes_to_specified_project(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /lost-sessions/{sid}/ignore with project_name='alpha' ignores in alpha's vault."""
    from claude_mnemos.core.lost_sessions import LostSessionsIgnore

    _daemon, client, vault_a, vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "ignoreme")

    r = client.post(
        "/lost-sessions/ignoreme/ignore",
        json={"project_name": "alpha"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ignored_count"] == 1

    # Persisted in alpha's vault_root, not beta's.
    ig_alpha = LostSessionsIgnore.load(vault_a)
    ig_beta = LostSessionsIgnore.load(vault_b)
    assert len(ig_alpha.ignored_shas) == 1
    assert len(ig_beta.ignored_shas) == 0
