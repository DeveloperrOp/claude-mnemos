"""Slow E2E for Plan #13b-α: subprocess daemon + project-map + settings."""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest

pytestmark = pytest.mark.slow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_ready(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=0.5)
            if r.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_exc = exc
        time.sleep(0.2)
    raise RuntimeError(
        f"daemon at {url} did not become ready within {timeout}s; last exc: {last_exc}"
    )


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(psutil.NoSuchProcess):
        psutil.Process(proc.pid).terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _spawn_daemon(
    vault: Path, port: int, env: dict[str, str], pid_file: Path,
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "claude_mnemos.daemon",
            "run",
            "--vault",
            str(vault),
            "--port",
            str(port),
            "--pid-file",
            str(pid_file),
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("MNEMOS_VAULT_ROOT", raising=False)
    return tmp_path


def _child_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.pop("MNEMOS_VAULT_ROOT", None)
    return env


def test_e2e_register_project_then_patch_settings(isolated_home: Path) -> None:
    home = isolated_home
    vault = home / "v"
    vault.mkdir()
    port = _free_port()
    env = _child_env(home)
    pid_file = home / "daemon.pid"
    proc = _spawn_daemon(vault, port, env, pid_file)
    try:
        url = f"http://127.0.0.1:{port}"
        _wait_until_ready(url)

        r = httpx.post(
            f"{url}/projects",
            json={
                "name": "myvault",
                "vault_root": str(vault),
                "cwd_patterns": [str(home / "code" / "*")],
            },
            timeout=2.0,
        )
        assert r.status_code == 201, r.text

        r = httpx.patch(
            f"{url}/settings/myvault",
            json={"snapshots": {"retention_days": 7, "daily_enabled": False}},
            timeout=2.0,
        )
        assert r.status_code == 200
        assert r.json()["snapshots"]["retention_days"] == 7

        sf = home / ".claude-mnemos" / "settings" / "myvault.json"
        data = json.loads(sf.read_text(encoding="utf-8"))
        assert data["snapshots"]["retention_days"] == 7

        # Combined project view via GET /projects/{name}
        r = httpx.get(f"{url}/projects/myvault", timeout=2.0)
        assert r.status_code == 200
        view = r.json()
        assert view["name"] == "myvault"
        assert view["settings"]["snapshots"]["retention_days"] == 7
    finally:
        _terminate(proc)


def test_e2e_cli_offline_add_then_resolve(isolated_home: Path) -> None:
    home = isolated_home
    vault = home / "v"
    vault.mkdir()
    cwd = home / "code" / "myproj"
    cwd.mkdir(parents=True)
    env = _child_env(home)

    # Offline add (no daemon running)
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "claude_mnemos",
            "project",
            "add",
            "--name",
            "myproj",
            "--vault",
            str(vault),
            "--cwd-pattern",
            str(cwd),
        ],
        env=env,
        capture_output=True,
        timeout=15,
    )
    assert r.returncode == 0, r.stderr.decode()

    # Resolve from cwd
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "claude_mnemos",
            "project",
            "resolve",
            "--cwd",
            str(cwd),
            "--json",
        ],
        env=env,
        capture_output=True,
        timeout=15,
    )
    assert r.returncode == 0, r.stderr.decode()
    data = json.loads(r.stdout.decode())
    assert data["name"] == "myproj"


def test_e2e_settings_persist_across_daemon_restart(isolated_home: Path) -> None:
    home = isolated_home
    vault = home / "v"
    vault.mkdir()
    env = _child_env(home)

    # Pre-register project + patch settings file directly.
    # Path.home() in this pytest process resolves to ``home`` thanks to
    # the monkeypatched USERPROFILE/HOME, so writes land under
    # ``home / .claude-mnemos / ...``.
    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    from claude_mnemos.state.settings import SettingsStore

    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    SettingsStore().patch_project("x", {"snapshots": {"retention_days": 11}})

    port = _free_port()
    pid_file = home / "daemon.pid"
    proc = _spawn_daemon(vault, port, env, pid_file)
    try:
        url = f"http://127.0.0.1:{port}"
        _wait_until_ready(url)
        r = httpx.get(f"{url}/settings/x", timeout=2.0)
        assert r.status_code == 200
        assert r.json()["snapshots"]["retention_days"] == 11
    finally:
        _terminate(proc)
