"""Integration tests for hooks/session_start.py — subprocess-driven."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.state.inject_metrics import InjectMetricsLog
from claude_mnemos.state.manifest import IngestRecord, Manifest

HOOK_PATH = Path(__file__).resolve().parent.parent / "hooks" / "session_start.py"


def _write_full_page(vault: Path, slug: str, body: str = "") -> None:
    page_path = vault / "wiki" / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        "---\n"
        f"title: {slug}\n"
        "type: concept\n"
        "status: draft\n"
        "confidence: 0.7\n"
        "flavor: []\n"
        "sources: []\n"
        "related: []\n"
        "created: 2026-04-29\n"
        "updated: 2026-04-29\n"
        "agent_written: true\n"
        "---\n"
    )
    page_path.write_text(fm + body, encoding="utf-8")


def _seed_manifest(vault: Path, *, pages: list[str]) -> None:
    rec = IngestRecord(
        session_id="s1",
        ingested_at=datetime.now(UTC),
        raw_path="raw/s1.md",
        source_path=None,
        created_pages=pages,
        skipped_collisions=[],
        model=None,
        input_tokens=None,
        output_tokens=None,
    )
    manifest = Manifest(ingested={"s1": rec})
    atomic_write(vault / ".manifest.json", manifest.serialize_to_string())


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run the hook as a subprocess; return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_hook_emits_context_on_cwd_match(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a", body="alpha context body")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "session_id": "test", "source": "startup"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout, f"expected non-empty stdout; got {stdout!r}"
    out = json.loads(stdout)
    hsi = out["hookSpecificOutput"]
    assert hsi["hookEventName"] == "SessionStart"
    assert "additionalContext" in hsi
    assert "concepts/a" in hsi["additionalContext"]


def test_hook_silent_skip_on_resume(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "source": "resume"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout == ""


def test_hook_silent_skip_when_recursion_flag_set(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "source": "startup"}
    rc, stdout, _ = _run_hook(payload, env_extra={"MNEMOS_INJECT_RUNNING": "1"})
    assert rc == 0
    assert stdout == ""


def test_hook_silent_skip_on_unmatched_cwd(tmp_path: Path) -> None:
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    payload = {"cwd": str(cwd), "source": "startup"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout == ""


def test_hook_silent_skip_on_invalid_stdin(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input="not json",
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=15,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_hook_writes_inject_event(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a", body="alpha context body")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "session_id": "test-sess-1", "source": "startup"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout

    log = InjectMetricsLog.load(vault)
    assert len(log.events) == 1
    evt = log.events[0]
    assert evt.session_id == "test-sess-1"
    assert evt.operation == "session_start"
    assert evt.mode in ("full", "trimmed")
    assert evt.tokens_actual > 0
    assert evt.tokens_full >= evt.tokens_actual


def test_hook_does_not_write_event_on_skip(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "source": "resume"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout == ""

    log = InjectMetricsLog.load(vault)
    assert log.events == []
