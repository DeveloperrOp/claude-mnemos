"""Shared fixtures for daemon integration tests.

``daemon_subprocess`` boots a real daemon process against an isolated HOME
and tears it down on exit.  Mirror the pattern in test_e2e_subprocess.py and
test_pages_e2e.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from typing import NamedTuple

import httpx
import pytest


class DaemonHandle(NamedTuple):
    proc: subprocess.Popen[bytes]
    base_url: str
    home: Path


def _wait_for_health(base_url: str, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=0.5)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    return False


@pytest.fixture
def daemon_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[DaemonHandle, None, None]:
    """Parametrised factory fixture — returns a callable.

    Usage inside a test::

        def test_something(daemon_subprocess):
            handle = daemon_subprocess(port=5760)
            # handle.base_url, handle.proc, handle.home
    """

    def _factory(
        port: int,
        projects: list[dict[str, object]] | None = None,
    ) -> DaemonHandle:
        home = tmp_path / f"home_{port}"
        home.mkdir(exist_ok=True)

        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))

        if projects:
            cfg_dir = home / ".claude-mnemos"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            (cfg_dir / "project-map.json").write_text(
                json.dumps({"version": 1, "projects": projects}),
                encoding="utf-8",
            )

        env = {
            **os.environ,
            "HOME": str(home),
            "USERPROFILE": str(home),
        }
        env.pop("MNEMOS_VAULT_ROOT", None)

        pid_file = home / "d.pid"
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "claude_mnemos.daemon",
                "run",
                "--port",
                str(port),
                "--pid-file",
                str(pid_file),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

        base_url = f"http://127.0.0.1:{port}"
        if not _wait_for_health(base_url):
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5.0)
            pytest.fail(f"daemon on :{port} did not respond within timeout")

        return DaemonHandle(proc=proc, base_url=base_url, home=home)

    handles: list[DaemonHandle] = []
    _real_factory = _factory

    def _tracked_factory(
        port: int,
        projects: list[dict[str, object]] | None = None,
    ) -> DaemonHandle:
        h = _real_factory(port, projects)
        handles.append(h)
        return h

    yield _tracked_factory  # type: ignore[misc]

    for h in handles:
        h.proc.terminate()
        try:
            h.proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            h.proc.kill()
            h.proc.wait(timeout=5.0)
