"""Tests: /settings PATCH triggers daemon.reload_project_settings /
reload_global_settings (Task 19, Plan #13b-β1).
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon_with_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Yield (daemon, TestClient).

    The scheduler is NOT started here — APScheduler's in-memory job registry
    is readable (get_job / get_jobs) without a running event loop.  Only the
    trigger-dispatch thread needs start(); our tests only inspect job presence.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    with TestClient(daemon.app, raise_server_exceptions=True) as client:
        yield daemon, client


def test_patch_project_settings_reloads_runtime(
    daemon_with_app: tuple[MnemosDaemon, TestClient],
    tmp_path: Path,
) -> None:
    """PATCH /settings/{name} must remove the daily_snapshot job when
    snapshots.daily_enabled is flipped to False on a mounted runtime."""
    daemon, client = daemon_with_app
    vault = tmp_path / "alpha"
    vault.mkdir()
    client.post(
        "/projects",
        json={"name": "alpha", "vault_root": str(vault), "cwd_patterns": []},
    )

    # After mount the daily_snapshot job must be present.
    assert daemon.scheduler.get_job("daily_snapshot:alpha") is not None

    r = client.patch("/settings/alpha", json={"snapshots": {"daily_enabled": False}})
    assert r.status_code == 200, r.text

    # reload_project_settings must have removed the job.
    assert daemon.scheduler.get_job("daily_snapshot:alpha") is None


def test_patch_global_settings_repicks_primary(
    daemon_with_app: tuple[MnemosDaemon, TestClient],
    tmp_path: Path,
) -> None:
    """PATCH /settings/global with primary_project=beta must switch the
    daemon's primary_runtime to beta and update app.state.vault_root."""
    daemon, client = daemon_with_app
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
    # Alphabetically "alpha" is primary before explicit pinning.
    assert daemon.primary_runtime is not None
    assert daemon.primary_runtime.name == "alpha"

    r = client.patch("/settings/global", json={"primary_project": "beta"})
    assert r.status_code == 200, r.text

    assert daemon.primary_runtime is not None
    assert daemon.primary_runtime.name == "beta"
    assert daemon.app.state.vault_root == b
