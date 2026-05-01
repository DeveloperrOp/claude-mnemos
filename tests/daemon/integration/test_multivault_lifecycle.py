"""Integration test: two-vault bootstrap.

Boots a real daemon with two projects pre-registered, then asserts:
- both vault .jobs.db files are created
- GET /projects lists both vaults
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

PORT = 5760


@pytest.mark.slow
def test_two_vault_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    vault_a = tmp_path / "alpha"
    vault_b = tmp_path / "beta"
    vault_a.mkdir()
    vault_b.mkdir()

    # Pre-register both projects by writing project-map.json into the isolated home.
    cfg_dir = home / ".claude-mnemos"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "project-map.json").write_text(
        json.dumps(
            {
                "version": 1,
                "projects": [
                    {
                        "name": "alpha",
                        "vault_root": str(vault_a),
                        "cwd_patterns": [],
                    },
                    {
                        "name": "beta",
                        "vault_root": str(vault_b),
                        "cwd_patterns": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    pid_file = home / "d.pid"
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
    }
    env.pop("MNEMOS_VAULT_ROOT", None)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "claude_mnemos.daemon",
            "run",
            "--port",
            str(PORT),
            "--pid-file",
            str(pid_file),
            "--all",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{PORT}/api/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            pytest.fail(f"daemon on :{PORT} did not respond within timeout")

        # Both vaults' .jobs.db should be created on mount.
        assert (vault_a / ".jobs.db").is_file(), "alpha .jobs.db not created"
        assert (vault_b / ".jobs.db").is_file(), "beta .jobs.db not created"

        # GET /projects returns a list; both names should be present.
        r = httpx.get(f"http://127.0.0.1:{PORT}/api/projects", timeout=5.0)
        assert r.status_code == 200, r.text
        projects = r.json()
        assert isinstance(projects, list)
        names = {p["name"] for p in projects}
        assert names == {"alpha", "beta"}, f"unexpected names: {names}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
