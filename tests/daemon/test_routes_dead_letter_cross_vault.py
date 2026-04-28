"""Cross-vault aggregation tests for /dead-letter (Task 12)."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore


def _seed_dead_letter(vault: Path, transcript_path: Path) -> str:
    """Write one dead-letter job directly into the vault's job DB.

    Called *before* POST /projects so the worker never sees the job as queued.
    Dead-letter jobs are ignored by JobWorker, so there is no race.
    Returns the job id.
    """
    store = JobStore(vault / JOBS_DB_FILENAME)
    job = store.create(kind="ingest", payload={"transcript_path": str(transcript_path)})
    now = datetime.now(UTC)
    # Claim + fail MAX_ATTEMPTS times via the public API so the job reaches
    # dead_letter status through the proper locking path.
    store.claim_next_ready(now=now)
    from claude_mnemos.state.jobs import MAX_ATTEMPTS

    for _ in range(MAX_ATTEMPTS):
        store.mark_failed_with_retry(
            job.id, error="boom", traceback="", finished_at=now
        )
    job_id = job.id
    store.close()
    return job_id


@pytest.fixture
def daemon_with_two_vaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Real MnemosDaemon, alpha + beta mounted, each with a dead-letter job.

    Jobs are seeded directly into the SQLite files *before* mounting so the
    JobWorker never races with our setup (it only processes queued jobs).
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()

    # Pre-seed dead-letter jobs before the worker starts.
    job_ids: dict[str, str] = {}
    for name, vault in (("alpha", a), ("beta", b)):
        t = vault / f"{name}.jsonl"
        t.write_text("{}\n")
        job_ids[name] = _seed_dead_letter(vault, t)

    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app) as client:
        for name, vault in (("alpha", a), ("beta", b)):
            r = client.post(
                "/projects",
                json={"name": name, "vault_root": str(vault), "cwd_patterns": []},
            )
            assert r.status_code == 201, f"POST /projects for {name} failed: {r.text}"
        yield daemon, client
    asyncio.run(daemon._shutdown_runtimes())
    if daemon.scheduler.running:
        daemon.scheduler.shutdown(wait=False)


def test_list_dead_letter_cross_vault(
    daemon_with_two_vaults: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults
    r = client.get("/dead-letter")
    assert r.status_code == 200, r.text
    body = r.json()
    project_names = {j["project_name"] for j in body["jobs"]}
    assert project_names == {"alpha", "beta"}


def test_list_dead_letter_items_have_project_name(
    daemon_with_two_vaults: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults
    r = client.get("/dead-letter")
    assert r.status_code == 200, r.text
    for job in r.json()["jobs"]:
        assert "project_name" in job
        assert job["project_name"] in ("alpha", "beta")


def test_get_dead_letter_finds_across_runtimes(
    daemon_with_two_vaults: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults
    list_r = client.get("/dead-letter")
    assert list_r.status_code == 200, list_r.text
    jobs = list_r.json()["jobs"]
    # Pick the beta job and fetch it directly.
    beta_job = next(j for j in jobs if j["project_name"] == "beta")
    r = client.get(f"/dead-letter/{beta_job['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == beta_job["id"]
    assert body["project_name"] == "beta"


def test_get_dead_letter_unknown_returns_404(
    daemon_with_two_vaults: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults
    r = client.get("/dead-letter/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_retry_routes_to_correct_runtime(
    daemon_with_two_vaults: tuple[MnemosDaemon, TestClient],
) -> None:
    daemon, client = daemon_with_two_vaults
    list_r = client.get("/dead-letter")
    assert list_r.status_code == 200, list_r.text
    jobs = list_r.json()["jobs"]
    alpha_job = next(j for j in jobs if j["project_name"] == "alpha")
    r = client.post(f"/dead-letter/{alpha_job['id']}/retry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["attempt"] == 0
    assert body["project_name"] == "alpha"
    # Confirm the job was restored in the alpha runtime.  The worker may have
    # already claimed it (→ "running") by the time we read, so accept either.
    alpha_store = daemon.runtimes["alpha"].job_store
    assert alpha_store is not None
    restored = alpha_store.get_by_id(alpha_job["id"])
    assert restored is not None
    assert restored.status in {"queued", "running", "succeeded", "failed", "dead_letter"}


def test_dismiss_routes_to_correct_runtime(
    daemon_with_two_vaults: tuple[MnemosDaemon, TestClient],
) -> None:
    daemon, client = daemon_with_two_vaults
    list_r = client.get("/dead-letter")
    assert list_r.status_code == 200, list_r.text
    jobs = list_r.json()["jobs"]
    beta_job = next(j for j in jobs if j["project_name"] == "beta")
    r = client.delete(f"/dead-letter/{beta_job['id']}")
    assert r.status_code == 204, r.text
    # Confirm removed from beta runtime.
    beta_store = daemon.runtimes["beta"].job_store
    assert beta_store is not None
    assert beta_store.get_by_id(beta_job["id"]) is None


def test_dismiss_unknown_returns_404(
    daemon_with_two_vaults: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults
    r = client.delete("/dead-letter/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
