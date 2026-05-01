"""Slow E2E for Plan #9: real subprocess daemon, real watchdog,
real filesystem write -> human_edit_detected appears in /activity.
"""

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

pytestmark = [
    pytest.mark.slow,
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(predicate, *, timeout: float = 10.0, interval: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _wait_for_health(url: str, timeout: float = 15.0) -> dict | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    return None


@pytest.mark.slow
def test_watchdog_e2e_external_modify_detected(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    pid_file = tmp_path / "daemon.pid"
    port = _free_port()

    # Pre-register project so the daemon mounts the vault at startup;
    # and vault-root-dependent routes (/activity, /alerts) work.
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    child_env = os.environ.copy()
    child_env["HOME"] = str(isolated_home)
    child_env["USERPROFILE"] = str(isolated_home)
    child_env.pop("MNEMOS_VAULT_ROOT", None)
    (isolated_home / ".claude-mnemos").mkdir(parents=True, exist_ok=True)
    (isolated_home / ".claude-mnemos" / "project-map.json").write_text(
        json.dumps({"projects": [{"name": "main", "vault_root": str(vault), "cwd_patterns": []}]}),
        encoding="utf-8",
    )

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
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        health = _wait_for_health(f"http://127.0.0.1:{port}/api/health")
        assert health is not None, (
            f"daemon did not respond. "
            f"stderr: {proc.stderr.read().decode() if proc.stderr else ''}"
        )
        # Per-vault dict shape: watchdog state lives under vaults["main"]
        vaults = health.get("vaults", {})
        assert vaults.get("main", {}).get("watchdog_running") is True, (
            f"watchdog not running. health={health}"
        )

        # Seed a page through normal filesystem write before any external edit.
        page = vault / "wiki/entities/foo.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            """---
title: Foo
type: entity
created: 2026-04-26
updated: 2026-04-26
agent_written: true
---
body
""",
            encoding="utf-8",
        )

        # Wait for the daemon to fully process the seed write before doing the
        # external modify. The seed (a fresh file under wiki/) shows up as an
        # `external_create` alert from the watchdog's perspective; once that
        # alert is visible, the watchdog has drained the seed event and the
        # follow-up modify is unambiguous.
        def seed_was_observed() -> bool:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/api/alerts", timeout=2.0)
                if r.status_code != 200:
                    return False
                return any(
                    a.get("kind") == "external_create"
                    and a.get("path", "").endswith("foo.md")
                    for a in r.json()
                )
            except httpx.HTTPError:
                return False

        assert _wait_for(seed_was_observed, timeout=5.0), (
            "daemon never observed seed write (no external_create alert)"
        )

        # External modify simulating an editor save.
        existing = page.read_text(encoding="utf-8")
        page.write_text(existing + "\nedited externally\n", encoding="utf-8")

        def has_human_edit() -> bool:
            try:
                r = httpx.get(
                    f"http://127.0.0.1:{port}/api/activity/main?limit=200",
                    timeout=2.0,
                )
                if r.status_code != 200:
                    return False
                entries = r.json().get("entries", [])
                return any(
                    e.get("operation_type") == "human_edit_detected"
                    for e in entries
                )
            except httpx.HTTPError:
                return False

        assert _wait_for(has_human_edit, timeout=10.0), (
            "human_edit_detected entry never appeared"
        )

        # Page mutation should be reflected.
        assert "agent_written: false" in page.read_text(encoding="utf-8")

        # /alerts should not contain unexpected handler errors for the normal
        # path. The project is pre-registered so no "not in project-map" alert
        # is expected; external_create alerts may exist (initial write was
        # external from daemon's perspective) — they're informational, not errors.
        r = httpx.get(f"http://127.0.0.1:{port}/api/alerts", timeout=2.0)
        assert r.status_code == 200
        unexpected = [
            a
            for a in r.json()
            if a["kind"] == "handler_error"
        ]
        assert not unexpected, f"unexpected handler_error alerts: {unexpected}"

    finally:
        with contextlib.suppress(psutil.NoSuchProcess):
            psutil.Process(proc.pid).terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    if pid_file.exists():
        pid_file.unlink()
