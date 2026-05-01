"""Cross-vault aggregation tests for /metrics/* routes (Task 13, Plan #13b-β2).

Uses real MnemosDaemon with two mounted vaults, each pre-seeded with manifest
records so we get predictable assertion values.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.state.manifest import IngestRecord, Manifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_metrics(
    vault: Path,
    *,
    sessions: int,
    tokens_input: int,
    tokens_output: int,
) -> None:
    """Write ``sessions`` IngestRecord entries into <vault>/.manifest.json.

    All records are timestamped today (UTC) so they fall within any rolling
    window.  SHA keys are made unique per session so there are no collisions.
    """
    manifest = Manifest.load(vault)
    for i in range(sessions):
        sha = f"sha-{vault.name}-{i:04d}"
        sid = f"sess-{vault.name}-{i:04d}"
        manifest.add(
            sha,
            IngestRecord(
                session_id=sid,
                ingested_at=datetime.now(UTC),
                raw_path=f"raw/chats/{sid}.md",
                source_path=None,
                created_pages=[],
                skipped_collisions=[],
                model="claude-opus-4-7",
                input_tokens=tokens_input,
                output_tokens=tokens_output,
                transcript_path=f"/abs/{sid}.jsonl",
                raw_transcript_bytes=4096,
            ),
        )
    manifest.save(vault)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def daemon_with_two_vaults_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Real MnemosDaemon, alpha + beta mounted, each with seeded manifest records.

    alpha: 5 sessions × (1000 in + 500 out) = 5 sessions, 5000 in, 2500 out
    beta:  10 sessions × (2000 in + 1000 out) = 10 sessions, 20000 in, 10000 out
    Total: 15 sessions, 25000 in, 12500 out, 37500 injected
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()

    # Seed BEFORE mounting so initial scan picks them up cleanly.
    _seed_metrics(a, sessions=5, tokens_input=1000, tokens_output=500)
    _seed_metrics(b, sessions=10, tokens_input=2000, tokens_output=1000)

    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app) as client:
        for name, vault in (("alpha", a), ("beta", b)):
            r = client.post(
                "/api/projects",
                json={"name": name, "vault_root": str(vault), "cwd_patterns": []},
            )
            assert r.status_code == 201, f"POST /projects for {name} failed: {r.text}"
        yield daemon, client
    asyncio.run(daemon._shutdown_runtimes())
    if daemon.scheduler.running:
        daemon.scheduler.shutdown(wait=False)


@pytest.fixture
def empty_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Real MnemosDaemon with no vaults mounted."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app) as client:
        yield daemon, client
    asyncio.run(daemon._shutdown_runtimes())
    if daemon.scheduler.running:
        daemon.scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Tests: /metrics/usage
# ---------------------------------------------------------------------------

def test_usage_aggregates_sessions_across_vaults(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sessions_covered"] == 5 + 10  # 15


def test_usage_aggregates_tokens_across_vaults(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage")
    assert r.status_code == 200, r.text
    body = r.json()
    # alpha: 5×1000=5000 in, 5×500=2500 out → 7500 injected
    # beta: 10×2000=20000 in, 10×1000=10000 out → 30000 injected
    assert body["tokens_input"] == 5000 + 20000  # 25000
    assert body["tokens_output"] == 2500 + 10000  # 12500
    assert body["tokens_injected"] == 7500 + 30000  # 37500


def test_usage_empty_runtimes(
    empty_daemon: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = empty_daemon
    r = client.get("/api/metrics/usage")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sessions_covered"] == 0
    assert body["tokens_injected"] == 0


def test_usage_bad_period_returns_400(
    empty_daemon: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = empty_daemon
    r = client.get("/api/metrics/usage?period=oops")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_period_format"


# ---------------------------------------------------------------------------
# Tests: /metrics/usage/by-project
# ---------------------------------------------------------------------------

def test_usage_by_project_real_breakdown(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage/by-project")
    assert r.status_code == 200, r.text
    projects = {p["project"]: p for p in r.json()["projects"]}
    assert "alpha" in projects
    assert "beta" in projects


def test_usage_by_project_has_correct_values(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage/by-project")
    assert r.status_code == 200, r.text
    projects = {p["project"]: p for p in r.json()["projects"]}
    assert projects["alpha"]["sessions_covered"] == 5
    assert projects["beta"]["sessions_covered"] == 10


def test_usage_by_project_empty_when_no_runtimes(
    empty_daemon: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = empty_daemon
    r = client.get("/api/metrics/usage/by-project")
    assert r.status_code == 200, r.text
    assert r.json() == {"projects": []}


# ---------------------------------------------------------------------------
# Tests: /metrics/usage/top-sessions
# ---------------------------------------------------------------------------

def test_top_sessions_cross_vault_contains_both_vaults(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage/top-sessions?limit=20")
    assert r.status_code == 200, r.text
    sessions = r.json()["sessions"]
    projects_seen = {s["project"] for s in sessions}
    assert projects_seen == {"alpha", "beta"}


def test_top_sessions_sorted_descending(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage/top-sessions?limit=5")
    assert r.status_code == 200, r.text
    sessions = r.json()["sessions"]
    if len(sessions) >= 2:
        totals = [s["tokens_total"] for s in sessions]
        # tokens_total may be None — treat None as 0 for the check
        numeric = [(t or 0) for t in totals]
        assert numeric == sorted(numeric, reverse=True)


def test_top_sessions_respects_limit(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage/top-sessions?limit=3")
    assert r.status_code == 200, r.text
    assert len(r.json()["sessions"]) == 3


def test_top_sessions_empty_runtimes(
    empty_daemon: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = empty_daemon
    r = client.get("/api/metrics/usage/top-sessions")
    assert r.status_code == 200, r.text
    assert r.json() == {"sessions": []}


# ---------------------------------------------------------------------------
# Tests: /metrics/usage/timeline
# ---------------------------------------------------------------------------

def test_timeline_merges_daily_no_duplicate_dates(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage/timeline?period=30d")
    assert r.status_code == 200, r.text
    points = r.json()["points"]
    dates = [p["date"] for p in points]
    assert len(dates) == len(set(dates)), "Duplicate dates in merged timeline"


def test_timeline_today_bucket_has_combined_sessions(
    daemon_with_two_vaults_metrics: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/api/metrics/usage/timeline?period=30d")
    assert r.status_code == 200, r.text
    points = r.json()["points"]
    # The last point in the sorted list is today.
    last = points[-1]
    # 5 alpha + 10 beta sessions all seeded today
    assert last["sessions"] == 15


def test_timeline_empty_runtimes(
    empty_daemon: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = empty_daemon
    r = client.get("/api/metrics/usage/timeline?period=7d")
    assert r.status_code == 200, r.text
    points = r.json()["points"]
    # 7 zero-filled days
    assert len(points) == 7
    assert all(p["sessions"] == 0 for p in points)
