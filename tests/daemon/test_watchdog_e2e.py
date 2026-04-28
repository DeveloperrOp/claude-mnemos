"""Slow E2E for Plan #9: real subprocess daemon, real watchdog,
real filesystem write -> human_edit_detected appears in /activity.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Plan #13b-β1 Task 12 stubbed MnemosDaemon.run() as NotImplementedError "
        "until Task 16 wires _bootstrap_runtimes + uvicorn. Re-enable this "
        "subprocess e2e once Task 16 lands."
    )
)


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

    proc = subprocess.Popen(
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
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        health = _wait_for_health(f"http://127.0.0.1:{port}/health")
        assert health is not None, (
            f"daemon did not respond. "
            f"stderr: {proc.stderr.read().decode() if proc.stderr else ''}"
        )
        assert health.get("watchdog_running") is True, (
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

        # Wait for the daemon to potentially detect the seed write — give it a
        # full second to settle, then we'll do a deliberate external modify.
        time.sleep(1.0)

        # External modify simulating an editor save.
        existing = page.read_text(encoding="utf-8")
        page.write_text(existing + "\nedited externally\n", encoding="utf-8")

        def has_human_edit() -> bool:
            try:
                r = httpx.get(
                    f"http://127.0.0.1:{port}/activity?limit=20", timeout=2.0
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
        # path. The daemon adds an informational handler_error when its vault
        # isn't registered in project-map (Plan #13b-α Task 7); that one is
        # expected here since this E2E uses an ad-hoc tmp vault.
        r = httpx.get(f"http://127.0.0.1:{port}/alerts", timeout=2.0)
        assert r.status_code == 200
        # external_create alerts may exist (initial write was external from
        # daemon's perspective) — they're informational, not errors.
        unexpected = [
            a
            for a in r.json()
            if a["kind"] == "handler_error"
            and "not registered in project-map" not in a["message"]
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
