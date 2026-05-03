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
            "/api/projects",
            json={"name": "alpha", "vault_root": str(vault_a), "cwd_patterns": []},
        )
        assert ra.status_code == 201, ra.text
        rb = client.post(
            "/api/projects",
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
    cwd: str | None = None,
) -> Path:
    """Create a shared transcripts dir with .jsonl files; set MNEMOS_TRANSCRIPTS_ROOT.

    Each .jsonl has the same single line with the given ``cwd``. If ``cwd`` is
    None, the file omits cwd and the resolver will mark the session unassigned.
    """
    import json as _json

    root = tmp_path / "transcripts"
    root.mkdir(exist_ok=True)
    for sid in session_ids:
        payload: dict[str, str] = {"sid": sid}
        if cwd is not None:
            payload["cwd"] = cwd
        (root / f"{sid}.jsonl").write_text(_json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    return root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_lost_sessions_cross_vault_dedupe_unassigned(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /lost-sessions: dedupe by sha; cwd-less sessions are __unassigned__.

    With the cwd-based attribution fix, each session appears exactly once.
    Sessions whose cwd does not match any project's cwd_patterns (or has no
    cwd at all) are tagged ``project_name="__unassigned__"`` — NOT attributed
    to whichever vault happened to surface them.
    """
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "sess-1", "sess-2")

    r = client.get("/api/lost-sessions")
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["sessions"]

    # Dedupe: 2 files × 2 vaults = 2 unique sessions, not 4.
    assert body["total"] == 2

    # Both sessions are unassigned because cwd_patterns are empty in both projects
    # AND the test transcripts have no cwd.
    project_names = {item["project_name"] for item in items}
    assert project_names == {"__unassigned__"}
    assert {i["session_id"] for i in items} == {"sess-1", "sess-2"}


def test_list_lost_sessions_attributes_by_cwd(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session whose cwd matches a project's cwd_patterns is attributed there."""
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    # Re-register alpha with a cwd pattern so the resolver attributes the
    # session to alpha. ProjectStore.update is the supported API.
    from claude_mnemos.state.projects import ProjectStore

    work_dir = tmp_path / "alpha-work"
    work_dir.mkdir()
    ProjectStore().update("alpha", cwd_patterns=[str(work_dir)])

    _make_shared_transcripts(
        tmp_path, monkeypatch, "alpha-sess", cwd=str(work_dir)
    )

    r = client.post("/api/lost-sessions/scan")
    assert r.status_code == 200, r.text
    items = r.json()["sessions"]

    target = [i for i in items if i["session_id"] == "alpha-sess"]
    assert len(target) == 1
    assert target[0]["project_name"] == "alpha"


def test_list_lost_sessions_excludes_globally_ingested(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session ingested in ANY vault must not appear as lost in any vault.

    Before the fix, vault_alpha would still show beta's ingested sessions as
    "lost for alpha". After the fix, a session present in any manifest is
    excluded from the cross-vault view entirely.
    """
    daemon, client, vault_a, vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "shared-sess")

    # Manually mark "shared-sess" as ingested in vault_b's manifest.
    from datetime import UTC, datetime

    from claude_mnemos.state.manifest import IngestRecord, Manifest

    # Compute the sha the scanner uses (sha256 of file bytes).
    import hashlib

    transcript_path = tmp_path / "transcripts" / "shared-sess.jsonl"
    sha = hashlib.sha256(transcript_path.read_bytes()).hexdigest()

    manifest = Manifest.load(vault_b)
    manifest.ingested[sha] = IngestRecord(
        session_id="shared-sess",
        ingested_at=datetime.now(tz=UTC),
        raw_path="raw/chats/shared-sess.md",
        source_path=None,
        model=None,
        input_tokens=None,
        output_tokens=None,
        transcript_path=str(transcript_path),
    )
    manifest.save(vault_b)

    # Invalidate caches and rescan.
    r = client.post("/api/lost-sessions/scan")
    assert r.status_code == 200
    items = r.json()["sessions"]

    # shared-sess must NOT appear (it's globally ingested via vault_b).
    assert all(i["session_id"] != "shared-sess" for i in items)


def test_scan_invalidates_all_caches(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /lost-sessions/scan invalidates all per-vault caches and returns fresh list."""
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    tr = _make_shared_transcripts(tmp_path, monkeypatch, "before-1")

    # Warm cache via GET.
    r1 = client.get("/api/lost-sessions")
    assert r1.json()["total"] >= 1

    # Add a new file; without invalidation the cached count stays old.
    (tr / "after-1.jsonl").write_text("2", encoding="utf-8")

    # POST /scan invalidates the per-vault caches so the new file is picked up.
    r2 = client.post("/api/lost-sessions/scan")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    session_ids = {i["session_id"] for i in body["sessions"]}
    # Dedupe: each new file appears exactly once in the aggregated list.
    assert "after-1" in session_ids, f"Expected 'after-1' in {session_ids}"
    new_items = [i for i in body["sessions"] if i["session_id"] == "after-1"]
    assert len(new_items) == 1


def test_import_routes_to_specified_project(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /lost-sessions/{sid}/import with project_name='alpha' creates job in alpha's store."""
    daemon, client, _vault_a, _vault_b = daemon_with_two

    _make_shared_transcripts(tmp_path, monkeypatch, "target")

    r = client.post(
        "/api/lost-sessions/target/import",
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

    r = client.post("/api/lost-sessions/orphan/import", json={})
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
        "/api/lost-sessions/orphan/import",
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

    r = client.post("/api/lost-sessions/skipme/ignore", json={})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"] == "missing_project_name"


def test_transcript_endpoint_404_for_unknown(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
) -> None:
    """GET /lost-sessions/{sid}/transcript with unknown session_id → 404."""
    _daemon, client, _vault_a, _vault_b = daemon_with_two

    r = client.get("/api/lost-sessions/no-such-session/transcript")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "lost_session_not_found"


def test_transcript_endpoint_returns_messages(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /lost-sessions/{sid}/transcript returns parsed user/assistant messages."""
    import json as _json

    _daemon, client, _vault_a, _vault_b = daemon_with_two

    # Build a real JSONL file with two messages and point the env var at it.
    root = tmp_path / "transcripts"
    root.mkdir(exist_ok=True)
    jsonl = root / "live-sess.jsonl"
    jsonl.write_text(
        "\n".join([
            _json.dumps({"type": "user", "content": "what's up"}),
            _json.dumps({"type": "assistant", "content": "not much"}),
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))

    r = client.get("/api/lost-sessions/live-sess/transcript?limit=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == "live-sess"
    assert body["total_messages"] == 2
    assert body["returned_count"] == 2
    assert body["truncated"] is False
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "what's up"


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
        "/api/lost-sessions/ignoreme/ignore",
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
