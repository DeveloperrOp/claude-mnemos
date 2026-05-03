"""Tests for claude_mnemos.core.auto_dump."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.core.auto_dump import auto_dump_stale
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore


@pytest.fixture(autouse=True)
def _clear_transcripts_cache():
    from claude_mnemos.core.transcript_scanner import invalidate_transcripts_cache
    invalidate_transcripts_cache()
    yield
    invalidate_transcripts_cache()


class _FakeRuntime:
    def __init__(self, name: str, vault: Path) -> None:
        self.name = name
        self.vault_root = vault
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.job_worker = None


def _stale_jsonl(root: Path, name: str, cwd: str, hours_ago: float) -> Path:
    p = root / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(json.dumps({"cwd": cwd, "sid": name}).encode("utf-8"))
    ts = (datetime.now(tz=UTC) - timedelta(hours=hours_ago)).timestamp()
    os.utime(p, (ts, ts))
    return p


@pytest.fixture
def projects_with_alpha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """Register project 'alpha' with cwd_patterns matching tmp_path/work."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    work = tmp_path / "work"
    work.mkdir()
    vault = tmp_path / "vault-alpha"
    vault.mkdir()
    map_path = home / ".claude-mnemos" / "project-map.json"
    store = ProjectStore(map_path=map_path)
    store.add(ProjectMapEntry(
        name="alpha",
        vault_root=vault,
        cwd_patterns=[str(work)],
    ))
    return vault, str(work)


@pytest.mark.asyncio
async def test_auto_dump_stale_assigned_session_enqueues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    # Create a cooling session (>30min old, <24h old)
    _stale_jsonl(transcripts, "sess-stale", cwd, hours_ago=2)

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale({"alpha": runtime})

    assert queued == 1
    counts = runtime.job_store.count_by_status()
    assert sum(counts.values()) == 1
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_skips_unassigned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    vault, _cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    # Create a cooling session with unassigned cwd
    _stale_jsonl(transcripts, "orphan", "D:\\nowhere", hours_ago=2)

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale({"alpha": runtime})

    assert queued == 0
    counts = runtime.job_store.count_by_status()
    assert sum(counts.values()) == 0
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_skips_recent_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """Sessions within COOLING_THRESHOLD_HOURS (24h) but with status=hot should NOT be enqueued.

    A fresh hot session (5 min ago) has status=hot and should be skipped.
    """
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "fresh", cwd, hours_ago=0.05)  # 3 min ago — hot

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale({"alpha": runtime})

    assert queued == 0
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_caps_at_max_per_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    for i in range(5):
        _stale_jsonl(transcripts, f"s{i}", cwd, hours_ago=2 + i)  # cooling, all assigned

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale({"alpha": runtime}, max_per_run=2)

    assert queued == 2
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_payload_extract_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """Auto-dump must always enqueue with extract=False (no LLM stage)."""
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "auto", cwd, hours_ago=2)

    runtime = _FakeRuntime("alpha", vault)
    await auto_dump_stale({"alpha": runtime})

    rows = runtime.job_store.list_by_status("queued")
    assert len(rows) == 1
    assert rows[0].payload["extract"] is False
    assert rows[0].payload["transcript_path"].endswith("auto.jsonl")
    runtime.job_store.close()
