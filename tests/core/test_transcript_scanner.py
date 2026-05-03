"""Tests for claude_mnemos.core.transcript_scanner."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.transcript_scanner import (
    TranscriptEntry,
    scan_transcripts,
)


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
