from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon_with_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[MnemosDaemon, TestClient, Path], None, None]:
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
        yield daemon, client, tmp_path


def test_jobs_post_routes_by_project_name(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    daemon, client, tmp_path = daemon_with_two
    transcript_a = tmp_path / "a" / "t.jsonl"
    transcript_a.write_text("{}\n")
    transcript_b = tmp_path / "b" / "t.jsonl"
    transcript_b.write_text("{}\n")

    r = client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"project_name": "alpha", "transcript_path": str(transcript_a)},
        },
    )
    assert r.status_code == 201, r.text

    r = client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"project_name": "beta", "transcript_path": str(transcript_b)},
        },
    )
    assert r.status_code == 201, r.text

    a_count = daemon.runtimes["alpha"].job_store.count_by_status()
    b_count = daemon.runtimes["beta"].job_store.count_by_status()
    assert sum(a_count.values()) == 1
    assert sum(b_count.values()) == 1


def test_jobs_post_missing_project_name_returns_400(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    daemon, client, tmp_path = daemon_with_two
    t = tmp_path / "a" / "t.jsonl"
    t.write_text("{}\n")
    r = client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"transcript_path": str(t)},
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_project_name"


def test_jobs_post_unknown_project_returns_400(
    daemon_with_two: tuple[MnemosDaemon, TestClient, Path],
) -> None:
    daemon, client, tmp_path = daemon_with_two
    t = tmp_path / "a" / "t.jsonl"
    t.write_text("{}\n")
    r = client.post(
        "/jobs",
        json={
            "kind": "ingest",
            "payload": {"project_name": "ghost", "transcript_path": str(t)},
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "unknown_project"
