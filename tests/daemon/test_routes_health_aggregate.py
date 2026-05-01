"""Per-vault dict shape tests for /health endpoint (Task 14, Plan #13b-β2).

Exercises the new `vaults` dict field and confirms top-level `vault`,
`watchdog_running`, `jobs_queued`, `jobs_running`, `jobs_dead_letter` are gone.
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def daemon_with_two_vaults_health(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[MnemosDaemon, TestClient], None, None]:
    """Real MnemosDaemon with alpha + beta mounted."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()

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
# Tests
# ---------------------------------------------------------------------------


def test_health_lists_per_vault(
    daemon_with_two_vaults_health: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_health
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["vaults"].keys()) == {"alpha", "beta"}
    for name in ("alpha", "beta"):
        v = body["vaults"][name]
        assert "watchdog_running" in v
        assert "jobs_queued" in v
        assert "jobs_running" in v
        assert "jobs_dead_letter" in v


def test_health_vault_values_are_typed(
    daemon_with_two_vaults_health: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_health
    r = client.get("/api/health")
    body = r.json()
    for name in ("alpha", "beta"):
        v = body["vaults"][name]
        assert isinstance(v["watchdog_running"], bool)
        assert isinstance(v["jobs_queued"], int)
        assert isinstance(v["jobs_running"], int)
        assert isinstance(v["jobs_dead_letter"], int)


def test_health_empty_runtimes(
    empty_daemon: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = empty_daemon
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vaults"] == {}
    assert body["status"] == "ok"


def test_health_no_top_level_vault_field(
    daemon_with_two_vaults_health: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_health
    body = client.get("/api/health").json()
    assert "vault" not in body
    assert "watchdog_running" not in body
    assert "jobs_queued" not in body
    assert "jobs_running" not in body
    assert "jobs_dead_letter" not in body


def test_health_jobs_alert_false_when_no_dead_letter(
    daemon_with_two_vaults_health: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_health
    body = client.get("/api/health").json()
    # Fresh vaults have no dead-letter jobs
    assert body["jobs_alert"] is False


def test_health_watchdog_running_in_vault_entry(
    daemon_with_two_vaults_health: tuple[MnemosDaemon, TestClient],
) -> None:
    _daemon, client = daemon_with_two_vaults_health
    body = client.get("/api/health").json()
    # With a real mounted vault the watchdog should be running
    assert body["vaults"]["alpha"]["watchdog_running"] is True
    assert body["vaults"]["beta"]["watchdog_running"] is True


def test_health_status_ok_when_all_healthy(
    daemon_with_two_vaults_health: tuple[MnemosDaemon, TestClient],
) -> None:
    """Status is 'ok' when all watchdogs are up and dead-letter count is low."""
    _daemon, client = daemon_with_two_vaults_health
    body = client.get("/api/health").json()
    assert body["status"] == "ok"


def test_health_status_degraded_when_watchdog_down(
    daemon_with_two_vaults_health: tuple[MnemosDaemon, TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status becomes 'degraded' when any vault's watchdog is not running."""
    daemon, client = daemon_with_two_vaults_health
    observer = daemon.runtimes["alpha"].observer
    assert observer is not None, "expected a running observer on alpha"
    # Patch _observer to None so is_running returns False
    monkeypatch.setattr(observer, "_observer", None)
    body = client.get("/api/health").json()
    assert body["status"] == "degraded", f"expected degraded, got {body['status']}"
