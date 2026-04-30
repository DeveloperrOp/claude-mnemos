"""Tests for DELETE /projects/{slug}: 204, 404, settings-file cleanup, 409, force."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Yield (daemon, TestClient) using the same persistent-portal pattern as
    test_routes_projects_hotmount.py — required because DELETE awaits async
    unmount_vault on jobs spawned by VaultRuntime.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app, raise_server_exceptions=True) as client:
        yield daemon, client


def _add_project(
    client: TestClient, vault: Path, name: str = "p1"
) -> None:
    body = {"name": name, "vault_root": str(vault), "cwd_patterns": []}
    resp = client.post("/projects", json=body)
    assert resp.status_code in (200, 201), resp.text


def test_delete_project_returns_204_on_success(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    vault = tmp_path / "v1"
    vault.mkdir()
    _add_project(client, vault, name="p1")
    resp = client.delete("/projects/p1")
    assert resp.status_code == 204
    # Project gone from registry
    assert client.get("/projects/p1").status_code == 404
    assert "p1" not in daemon.runtimes


def test_delete_project_returns_404_when_missing(
    live: tuple[MnemosDaemon, TestClient]
) -> None:
    _daemon, client = live
    resp = client.delete("/projects/does-not-exist")
    assert resp.status_code == 404


def test_delete_project_removes_settings_file(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    vault = tmp_path / "v2"
    vault.mkdir()
    _add_project(client, vault, name="p2")
    # Force a settings PATCH so the file exists.
    r = client.patch("/settings/p2", json={"telemetry": {"opt_in": True}})
    assert r.status_code == 200, r.text
    settings_path = daemon.settings_store.settings_dir / "p2.json"
    assert settings_path.exists()
    resp = client.delete("/projects/p2")
    assert resp.status_code == 204
    assert not settings_path.exists()


def test_delete_project_blocks_when_jobs_running(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    vault = tmp_path / "v3"
    vault.mkdir()
    _add_project(client, vault, name="p3")
    # Inject an in-flight job so unmount_vault sees queued > 0.
    daemon.runtimes["p3"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )
    resp = client.delete("/projects/p3")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "vault_busy"
    assert detail["queued"] + detail["running"] >= 1


def test_delete_project_force_overrides_jobs_running(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    vault = tmp_path / "v4"
    vault.mkdir()
    _add_project(client, vault, name="p4")
    daemon.runtimes["p4"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )
    resp = client.delete("/projects/p4?force=true")
    assert resp.status_code == 204
    assert "p4" not in daemon.runtimes
