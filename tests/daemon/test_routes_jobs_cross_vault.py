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
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app) as client:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        client.post(
            "/projects",
            json={"name": "alpha", "vault_root": str(a), "cwd_patterns": []},
        )
        client.post(
            "/projects",
            json={"name": "beta", "vault_root": str(b), "cwd_patterns": []},
        )
        # Enqueue one job in each
        for name, vault in (("alpha", a), ("beta", b)):
            t = vault / f"{name}.jsonl"
            t.write_text("{}\n")
            r = client.post(
                "/jobs",
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


def test_list_jobs_cross_vault(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs")
    assert r.status_code == 200, r.text
    body = r.json()
    project_names = {j["project_name"] for j in body["jobs"]}
    assert project_names == {"alpha", "beta"}


def test_list_jobs_filtered_by_project(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs?project=alpha")
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert len(jobs) >= 1
    assert all(j["project_name"] == "alpha" for j in jobs)


def test_list_jobs_unknown_project_returns_404(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs?project=ghost")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


def test_get_job_searches_across_runtimes(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    list_r = client.get("/jobs?project=beta")
    assert list_r.status_code == 200, list_r.text
    jobs = list_r.json()["jobs"]
    assert jobs, "expected at least one job in beta"
    job_id = jobs[0]["id"]
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["project_name"] == "beta"


def test_get_job_unknown_returns_404(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_cancel_job_finds_correct_runtime(
    daemon_with_two_vaults_jobs: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs?project=alpha&status=queued")
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert jobs, "expected a queued job in alpha"
    job_id = jobs[0]["id"]
    r = client.delete(f"/jobs/{job_id}")
    assert r.status_code == 204
