"""Cross-vault aggregation tests for /jobs GET / {id} / DELETE (Task 11)."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon_with_two_vaults_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Real MnemosDaemon, alpha + beta mounted, each with a queued job."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # POST /jobs rejects transcripts outside the transcripts root; the test
    # transcripts live under tmp_path, so point the root there.
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app) as client:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        client.post(
            "/api/projects",
            json={"name": "alpha", "vault_root": str(a), "cwd_patterns": []},
        )
        client.post(
            "/api/projects",
            json={"name": "beta", "vault_root": str(b), "cwd_patterns": []},
        )
        # Pause the queue so enqueued jobs deterministically STAY queued — the
        # worker would otherwise dequeue and complete the (empty) transcripts,
        # leaving status=queued empty and the cancel/listing assertions flaky.
        client.post("/api/daemon/pause")
        # Enqueue one job in each
        for name, vault in (("alpha", a), ("beta", b)):
            t = vault / f"{name}.jsonl"
            t.write_text("{}\n")
            r = client.post(
                "/api/jobs",
                json={
                    "kind": "ingest",
                    "payload": {"project_name": name, "transcript_path": str(t)},
                },
            )
            assert r.status_code == 201, f"POST /jobs for {name} failed: {r.text}"
        yield daemon, client
    asyncio.run(daemon._shutdown_runtimes())
    if daemon.scheduler.running:
        daemon.scheduler.shutdown(wait=False)


@pytest.fixture
def daemon_with_two_vaults_many_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Real MnemosDaemon, alpha + beta mounted, each with 5 queued jobs (10 total).

    Used to verify cross-vault pagination correctness at offset>0.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # POST /jobs rejects transcripts outside the transcripts root; the test
    # transcripts live under tmp_path, so point the root there.
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app) as client:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        client.post(
            "/api/projects",
            json={"name": "alpha", "vault_root": str(a), "cwd_patterns": []},
        )
        client.post(
            "/api/projects",
            json={"name": "beta", "vault_root": str(b), "cwd_patterns": []},
        )
        # Pause so the 10 jobs stay queued for the pagination assertions
        # instead of being completed out from under the test by the worker.
        client.post("/api/daemon/pause")
        # Enqueue 5 jobs in each vault
        for name, vault in (("alpha", a), ("beta", b)):
            for i in range(5):
                t = vault / f"{name}_{i}.jsonl"
                t.write_text("{}\n")
                r = client.post(
                    "/api/jobs",
                    json={
                        "kind": "ingest",
                        "payload": {"project_name": name, "transcript_path": str(t)},
                    },
                )
                assert r.status_code == 201, f"POST /jobs #{i} for {name} failed: {r.text}"
        yield daemon, client
    asyncio.run(daemon._shutdown_runtimes())
    if daemon.scheduler.running:
        daemon.scheduler.shutdown(wait=False)


def test_list_jobs_cross_vault(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/api/jobs")
    assert r.status_code == 200, r.text
    body = r.json()
    project_names = {j["project_name"] for j in body["jobs"]}
    assert project_names == {"alpha", "beta"}


def test_list_jobs_filtered_by_project(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/api/jobs?project=alpha")
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert len(jobs) >= 1
    assert all(j["project_name"] == "alpha" for j in jobs)


def test_list_jobs_unknown_project_returns_404(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/api/jobs?project=ghost")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


def test_get_job_searches_across_runtimes(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    list_r = client.get("/api/jobs?project=beta")
    assert list_r.status_code == 200, list_r.text
    jobs = list_r.json()["jobs"]
    assert jobs, "expected at least one job in beta"
    job_id = jobs[0]["id"]
    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["project_name"] == "beta"


def test_get_job_unknown_returns_404(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_cancel_job_finds_correct_runtime(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/api/jobs?project=alpha&status=queued")
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert jobs, "expected a queued job in alpha"
    job_id = jobs[0]["id"]
    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 204


def test_list_jobs_cross_vault_pagination(
    daemon_with_two_vaults_many_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    """Pagination works correctly across merged results (10 total: 5 per vault)."""
    _daemon, client = daemon_with_two_vaults_many_jobs
    page1 = client.get("/api/jobs?limit=4&offset=0").json()["jobs"]
    page2 = client.get("/api/jobs?limit=4&offset=4").json()["jobs"]
    page3 = client.get("/api/jobs?limit=4&offset=8").json()["jobs"]
    assert len(page1) == 4, f"page1 expected 4 got {len(page1)}"
    assert len(page2) == 4, f"page2 expected 4 got {len(page2)}"
    assert len(page3) == 2, f"page3 expected 2 got {len(page3)}"
    # No overlap across pages
    all_ids = {j["id"] for j in page1 + page2 + page3}
    assert len(all_ids) == 10, f"expected 10 unique ids, got {len(all_ids)}"
