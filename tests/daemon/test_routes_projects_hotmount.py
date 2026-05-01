"""Tests: /projects POST/DELETE/PATCH hot-mount/unmount/remount wiring."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Yield (daemon, TestClient) with a single persistent event-loop portal.

    TestClient used as a context manager keeps one anyio BlockingPortal alive
    for all requests, which is required when routes spawn asyncio Tasks (e.g.
    JobWorker) that must be awaited across request boundaries.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app, raise_server_exceptions=True) as client:
        yield daemon, client
    # Portal is closed; remaining runtimes were already unmounted by the test
    # or will be cleaned up here via the portal's shutdown (unmount is best-effort
    # in teardown — jobs SQLite is closed by VaultRuntime.unmount).


def test_post_projects_hot_mounts(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    vault = tmp_path / "alpha"
    vault.mkdir()
    r = client.post("/api/projects", json={
        "name": "alpha",
        "vault_root": str(vault),
        "cwd_patterns": [],
    })
    assert r.status_code == 201, r.text
    assert "alpha" in daemon.runtimes
    assert daemon.runtimes["alpha"].is_mounted


def test_post_projects_mount_failure_rolls_back_map(
    live: tuple[MnemosDaemon, TestClient],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon, client = live
    vault = tmp_path / "rb"
    vault.mkdir()

    from claude_mnemos.daemon import vault_runtime as vr

    class _Boom:
        def __init__(self, *a: Any, **k: Any) -> None: pass
        def start(self) -> None: raise RuntimeError("simulated")
        def stop(self) -> None: pass

    monkeypatch.setattr(vr, "VaultObserver", _Boom)

    r = client.post("/api/projects", json={
        "name": "rb",
        "vault_root": str(vault),
        "cwd_patterns": [],
    })
    assert r.status_code == 500
    list_r = client.get("/api/projects")
    assert all(e["name"] != "rb" for e in list_r.json())


def test_delete_projects_busy_returns_409(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    vault = tmp_path / "busy"
    vault.mkdir()
    client.post("/api/projects", json={"name": "busy", "vault_root": str(vault), "cwd_patterns": []})

    daemon.runtimes["busy"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )
    r = client.delete("/api/projects/busy")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "vault_busy"


def test_delete_projects_force_drains(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    vault = tmp_path / "drain"
    vault.mkdir()
    client.post("/api/projects", json={"name": "drain", "vault_root": str(vault), "cwd_patterns": []})
    daemon.runtimes["drain"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )
    r = client.delete("/api/projects/drain?force=true")
    assert r.status_code == 204
    assert "drain" not in daemon.runtimes


def test_patch_vault_root_remounts(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    old_vault = tmp_path / "old"
    old_vault.mkdir()
    new_vault = tmp_path / "new"
    new_vault.mkdir()
    client.post("/api/projects", json={"name": "rm", "vault_root": str(old_vault), "cwd_patterns": []})
    r = client.patch("/api/projects/rm", json={"vault_root": str(new_vault)})
    assert r.status_code == 200
    assert daemon.runtimes["rm"].vault_root == new_vault


def test_patch_vault_root_busy_returns_409_without_changing_map(
    live: tuple[MnemosDaemon, TestClient], tmp_path: Path
) -> None:
    daemon, client = live
    old_vault = tmp_path / "old2"
    old_vault.mkdir()
    new_vault = tmp_path / "new2"
    new_vault.mkdir()
    client.post("/api/projects", json={"name": "rm2", "vault_root": str(old_vault), "cwd_patterns": []})
    daemon.runtimes["rm2"].job_store.create(
        kind="ingest", payload={"transcript_path": "x"}
    )
    r = client.patch("/api/projects/rm2", json={"vault_root": str(new_vault)})
    assert r.status_code == 409
    show = client.get("/api/projects/rm2").json()
    assert show["vault_root"] == str(old_vault)  # map untouched
