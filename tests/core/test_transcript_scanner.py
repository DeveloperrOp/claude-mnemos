"""Tests for claude_mnemos.core.transcript_scanner."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.transcript_scanner import (
    TranscriptEntry,
    scan_transcripts,
)


@pytest.fixture(autouse=True)
def _clear_transcripts_cache():
    from claude_mnemos.core.transcript_scanner import invalidate_transcripts_cache
    invalidate_transcripts_cache()
    yield
    invalidate_transcripts_cache()


def _write_jsonl(
    root: Path, name: str, payload: dict[str, object] | None = None
) -> tuple[Path, str]:
    content = json.dumps(payload or {"sid": name}).encode("utf-8")
    p = root / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p, hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_scan_empty_root_returns_empty(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    out = await scan_transcripts(transcripts_root=root)
    assert out == []


@pytest.mark.asyncio
async def test_scan_returns_one_entry_per_jsonl(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    _write_jsonl(root, "a")
    _write_jsonl(root, "b")
    out = await scan_transcripts(transcripts_root=root)
    assert {e.session_id for e in out} == {"a", "b"}
    for e in out:
        assert isinstance(e, TranscriptEntry)
        assert isinstance(e.mtime, datetime)
        assert e.mtime.tzinfo == UTC
        assert e.size_bytes > 0


@pytest.mark.asyncio
async def test_scan_extracts_cwd_from_first_event(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    _write_jsonl(root, "with-cwd", {"cwd": "D:\\code\\foo", "type": "user"})
    out = await scan_transcripts(transcripts_root=root)
    assert len(out) == 1
    assert out[0].cwd == "D:\\code\\foo"


@pytest.mark.asyncio
async def test_scan_skips_non_jsonl_files(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    (root / "ignore.txt").write_text("hi", encoding="utf-8")
    _write_jsonl(root, "real")
    out = await scan_transcripts(transcripts_root=root)
    assert {e.session_id for e in out} == {"real"}


@pytest.mark.asyncio
async def test_scan_recursive(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    nested = root / "project-1"
    nested.mkdir(parents=True)
    _write_jsonl(nested, "nested-sess")
    out = await scan_transcripts(transcripts_root=root)
    assert {e.session_id for e in out} == {"nested-sess"}


@pytest.mark.asyncio
async def test_scan_skips_subagent_transcripts(tmp_path: Path) -> None:
    """Subagent JSONLs live in `<session>/subagents/agent-*.jsonl` and must be
    excluded: their payload is already captured in the parent transcript via
    tool_use/tool_result, so re-ingesting them would double-count and pollute
    lost-sessions/active counters with sidechain runs.
    """
    root = tmp_path / "transcripts"
    proj = root / "project-1"
    proj.mkdir(parents=True)
    _write_jsonl(proj, "main-session")
    subagents = proj / "main-session" / "subagents"
    subagents.mkdir(parents=True)
    _write_jsonl(subagents, "agent-abc123")
    _write_jsonl(subagents, "agent-def456")

    out = await scan_transcripts(transcripts_root=root)
    assert {e.session_id for e in out} == {"main-session"}


@pytest.mark.asyncio
async def test_transcripts_cache_dedupes_concurrent(tmp_path: Path) -> None:
    """Two concurrent calls share one disk scan."""
    from claude_mnemos.core import transcript_scanner as ts

    root = tmp_path / "transcripts"
    root.mkdir()
    _write_jsonl(root, "x")

    ts.invalidate_transcripts_cache()

    # Hijack _scan_sync to count calls
    original = ts._scan_sync
    calls = 0
    def counting_scan(rt):
        nonlocal calls
        calls += 1
        return original(rt)
    ts._scan_sync = counting_scan
    try:
        results = await asyncio.gather(
            ts.scan_transcripts(transcripts_root=root),
            ts.scan_transcripts(transcripts_root=root),
            ts.scan_transcripts(transcripts_root=root),
        )
        assert all(len(r) == 1 for r in results)
        assert calls == 1
    finally:
        ts._scan_sync = original
        ts.invalidate_transcripts_cache()
