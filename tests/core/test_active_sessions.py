"""Tests for claude_mnemos.core.active_sessions."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.core.active_sessions import (
    ActiveSession,
    scan_active_sessions,
)
from claude_mnemos.state.manifest import IngestRecord, Manifest


def _write_jsonl_with_mtime(root: Path, name: str, mtime_ago: timedelta, cwd: str | None = None) -> Path:
    """Write a jsonl and set its mtime to `now - mtime_ago`."""
    payload: dict[str, object] = {"sid": name}
    if cwd is not None:
        payload["cwd"] = cwd
    content = json.dumps(payload).encode("utf-8")
    p = root / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    target = datetime.now(tz=UTC) - mtime_ago
    ts = target.timestamp()
    os.utime(p, (ts, ts))
    return p


class _FakeRuntime:
    """Minimal VaultRuntime stand-in for active_sessions tests."""

    def __init__(self, name: str, vault: Path) -> None:
        self.name = name
        self.vault_root = vault


def _ingest(sid: str, sha: str, vault: Path) -> None:
    manifest = Manifest.load(vault)
    manifest.ingested[sha] = IngestRecord(
        session_id=sid,
        ingested_at=datetime.now(tz=UTC),
        raw_path=f"raw/chats/{sid}.md",
        source_path=None,
        model=None,
        input_tokens=None,
        output_tokens=None,
    )
    manifest.save(vault)


@pytest.mark.asyncio
async def test_scan_returns_empty_for_no_jsonls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    out = await scan_active_sessions([])
    assert out == []


@pytest.mark.asyncio
async def test_scan_filters_by_24h_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    _write_jsonl_with_mtime(root, "fresh", timedelta(minutes=15))
    _write_jsonl_with_mtime(root, "old", timedelta(hours=30))
    out = await scan_active_sessions([])
    assert {s.session_id for s in out} == {"fresh"}


@pytest.mark.asyncio
async def test_scan_classifies_hot_vs_cooling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    _write_jsonl_with_mtime(root, "hot", timedelta(minutes=10))
    _write_jsonl_with_mtime(root, "cool", timedelta(hours=3))
    out = await scan_active_sessions([])
    by_id = {s.session_id: s for s in out}
    assert by_id["hot"].status == "hot"
    assert by_id["cool"].status == "cooling"


@pytest.mark.asyncio
async def test_scan_excludes_globally_ingested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    p = _write_jsonl_with_mtime(root, "ingested", timedelta(minutes=10))
    import hashlib
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    vault = tmp_path / "vault"
    vault.mkdir()
    _ingest("ingested", sha, vault)
    runtime = _FakeRuntime("alpha", vault)
    out = await scan_active_sessions([runtime])
    assert out == []


@pytest.mark.asyncio
async def test_scan_attributes_via_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without registered project — sessions are __unassigned__."""
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    _write_jsonl_with_mtime(root, "no-cwd", timedelta(minutes=10))
    out = await scan_active_sessions([])
    assert all(s.project_name == "__unassigned__" for s in out)


@pytest.mark.asyncio
async def test_auto_dump_at_set_for_assigned_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """auto_dump_at = mtime+24h for assigned, None for unassigned."""
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    _write_jsonl_with_mtime(root, "u", timedelta(hours=2))
    out = await scan_active_sessions([])
    assert len(out) == 1
    assert out[0].project_name == "__unassigned__"
    assert out[0].auto_dump_at is None


@pytest.mark.asyncio
async def test_scan_attributes_assigned_session_to_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sessions with cwd matching registered project are assigned with correct status."""
    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore

    # Setup: tmp home for ProjectStore
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    # Register project with cwd pattern
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    store = ProjectStore(map_path=home / ".claude-mnemos" / "project-map.json")
    store.add(
        ProjectMapEntry(
            name="alpha",
            vault_root=vault,
            cwd_patterns=[str(work_dir)],
        )
    )

    # Setup transcripts
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))

    # Test 1: Recent session (15 min ago) with matching cwd → hot + assigned
    _write_jsonl_with_mtime(root, "hot-assigned", timedelta(minutes=15), cwd=str(work_dir))
    out = await scan_active_sessions([])
    assert len(out) == 1
    assert out[0].session_id == "hot-assigned"
    assert out[0].project_name == "alpha"
    assert out[0].status == "hot"
    assert out[0].auto_dump_at is not None

    # Clean up for next test
    (root / "hot-assigned.jsonl").unlink()

    # Test 2: Older session (3 hours ago) with matching cwd → cooling + assigned
    _write_jsonl_with_mtime(root, "cool-assigned", timedelta(hours=3), cwd=str(work_dir))
    out = await scan_active_sessions([])
    assert len(out) == 1
    assert out[0].session_id == "cool-assigned"
    assert out[0].project_name == "alpha"
    assert out[0].status == "cooling"
    assert out[0].auto_dump_at is not None
