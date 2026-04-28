"""Tests that routes read per-vault state from daemon.primary_runtime.

These tests exercise each previously-affected endpoint against a REAL
MnemosDaemon with one mounted vault, confirming they return sensible
responses (not 503) after the primary_runtime fix.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon_with_one_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[MnemosDaemon, TestClient, Path], None, None]:
    """Yield (daemon, TestClient, vault_path) with one vault mounted.

    We do NOT call daemon.scheduler.start() here — AsyncIOScheduler requires
    a running event loop, which only exists inside the TestClient context.
    The scheduler is started lazily by APScheduler the first time an async
    job fires; for our tests we only need the watchdog (started in a thread
    by VaultRuntime.mount) and the JobStore, both of which work without it.

    vault registration (POST /projects) happens inside the TestClient context
    so the async VaultRuntime.mount() runs inside anyio's event loop.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app, raise_server_exceptions=True) as client:
        vault = tmp_path / "alpha"
        vault.mkdir()
        r = client.post(
            "/projects",
            json={"name": "alpha", "vault_root": str(vault), "cwd_patterns": []},
        )
        assert r.status_code == 201, r.text
        yield daemon, client, vault
    asyncio.run(daemon._shutdown_runtimes())
    if daemon.scheduler.running:
        daemon.scheduler.shutdown(wait=False)


# ── /dead-letter ──────────────────────────────────────────────────────────────

def test_dead_letter_list_returns_200_with_real_daemon(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    r = client.get("/dead-letter")
    assert r.status_code == 200, r.text
    assert "jobs" in r.json()


def test_dead_letter_dismiss_unknown_returns_404(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    r = client.delete("/dead-letter/nonexistent-id")
    # 404, not 503
    assert r.status_code == 404, r.text


# ── /sessions/{project}/{sid}/ingest ─────────────────────────────────────────

def test_sessions_ingest_bad_path_returns_400_not_503(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    # valid daemon + known project → reaches body validation, not 404/503
    r = client.post(
        "/sessions/alpha/some-sid/ingest",
        json={"transcript_path": "/does/not/exist.jsonl"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"] == "missing_or_invalid_transcript_path"


def test_sessions_ingest_enqueues_job(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
    tmp_path: Path,
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}")
    r = client.post(
        "/sessions/alpha/some-sid/ingest",
        json={"transcript_path": str(transcript)},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "ingest"
    assert body["status"] == "queued"


# ── /lost-sessions ────────────────────────────────────────────────────────────

def test_lost_sessions_scan_returns_200(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    r = client.post("/lost-sessions/scan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sessions" in body
    assert "total" in body


def test_lost_sessions_list_returns_200(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    r = client.get("/lost-sessions")
    assert r.status_code == 200, r.text


def test_lost_sessions_import_unknown_returns_404_not_503(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    # β2: project_name is required in body; "alpha" is the mounted project.
    # Session "nonexistent" is not in the scan → 404 (not 503).
    r = client.post(
        "/lost-sessions/nonexistent/import",
        json={"project_name": "alpha"},
    )
    assert r.status_code == 404, r.text


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_watchdog_running_with_real_daemon(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    # Per-vault dict shape: watchdog state lives under vaults["alpha"]
    assert body["vaults"]["alpha"]["watchdog_running"] is True


def test_health_jobs_counters_with_real_daemon(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    _daemon, client, _vault = daemon_with_one_vault
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    # Counters live under vaults["alpha"] (not stuck at 0 due to missing job_store)
    vault_alpha = body["vaults"]["alpha"]
    assert isinstance(vault_alpha["jobs_queued"], int)
    assert isinstance(vault_alpha["jobs_running"], int)
    assert isinstance(vault_alpha["jobs_dead_letter"], int)


# ── /pages (tracker wiring) ───────────────────────────────────────────────────

def test_pages_patch_uses_tracker_from_primary_runtime(
    daemon_with_one_vault: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    """PATCH /pages must succeed and the route must have received a non-None
    tracker from primary_runtime (not silently None due to the old daemon.*
    attribute lookup that was removed).

    The tracker.writing() context manager is ephemeral — entries are removed
    after the write completes — so we verify correctness by:
      1. Confirming the request returns 200 (i.e. the apply_patch ran fully).
      2. Confirming primary_runtime.tracker is the real OurWritesTracker (not
         None), meaning the route wired it through correctly.
    """
    daemon, client, vault = daemon_with_one_vault
    # Create a wiki page with all required WikiPageFrontmatter fields.
    pages_dir = vault / "pages"
    pages_dir.mkdir()
    page = pages_dir / "test-page.md"
    page.write_text(
        "---\n"
        "title: Test\n"
        "type: entity\n"
        "status: draft\n"
        "confidence: 0.8\n"
        "flavor: []\n"
        "sources: []\n"
        "related: []\n"
        "created: 2026-04-28\n"
        "updated: 2026-04-28\n"
        "agent_written: true\n"
        "---\n\nBody text.\n",
        encoding="utf-8",
    )

    r = client.patch(
        "/pages/alpha/pages/test-page.md",
        json={"frontmatter": {"status": "verified"}},
    )
    assert r.status_code == 200, r.text

    # Confirm the primary_runtime's tracker is wired (non-None) so that
    # apply_patch received it and the watchdog won't misfire on our writes.
    primary = daemon.primary_runtime
    assert primary is not None
    from claude_mnemos.daemon.our_writes import OurWritesTracker
    assert isinstance(primary.tracker, OurWritesTracker)
