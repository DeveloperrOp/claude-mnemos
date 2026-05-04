# tests/core/test_cwd_detection.py
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.core.cwd_detection import (
    DetectedCwd,
    detect_cwds,
)


def _write_jsonl(p: Path, cwd: str, mtime: datetime) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"cwd": cwd, "type": "user", "message": {"role": "user", "content": "hi"}}) + "\n",
        encoding="utf-8",
    )
    ts = mtime.timestamp()
    import os
    os.utime(p, (ts, ts))


def test_detect_cwds_aggregates_by_directory(tmp_path: Path, monkeypatch) -> None:
    transcripts_root = tmp_path / "claude_projects"
    monkeypatch.setattr(
        "claude_mnemos.core.cwd_detection._transcripts_root",
        lambda: transcripts_root,
    )
    now = datetime.now(tz=UTC)

    _write_jsonl(transcripts_root / "p1" / "a.jsonl", "D:/code/app1", now - timedelta(days=1))
    _write_jsonl(transcripts_root / "p1" / "b.jsonl", "D:/code/app1", now - timedelta(days=2))
    _write_jsonl(transcripts_root / "p2" / "c.jsonl", "D:/code/app2", now - timedelta(days=3))

    result = detect_cwds(now=now)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].cwd == "D:/code/app1"
    assert result[0].session_count == 2
    assert result[1].cwd == "D:/code/app2"
    assert result[1].session_count == 1


def test_detect_cwds_filters_old_sessions(tmp_path: Path, monkeypatch) -> None:
    transcripts_root = tmp_path / "claude_projects"
    monkeypatch.setattr(
        "claude_mnemos.core.cwd_detection._transcripts_root",
        lambda: transcripts_root,
    )
    now = datetime.now(tz=UTC)
    _write_jsonl(transcripts_root / "p1" / "old.jsonl", "D:/old", now - timedelta(days=60))
    _write_jsonl(transcripts_root / "p1" / "fresh.jsonl", "D:/fresh", now - timedelta(days=1))

    result = detect_cwds(now=now)

    assert len(result) == 1
    assert result[0].cwd == "D:/fresh"


def test_detect_cwds_excludes_already_registered(tmp_path: Path, monkeypatch) -> None:
    transcripts_root = tmp_path / "claude_projects"
    monkeypatch.setattr(
        "claude_mnemos.core.cwd_detection._transcripts_root",
        lambda: transcripts_root,
    )
    now = datetime.now(tz=UTC)
    _write_jsonl(transcripts_root / "p1" / "a.jsonl", "D:/code/registered", now)
    _write_jsonl(transcripts_root / "p1" / "b.jsonl", "D:/code/new", now)

    result = detect_cwds(now=now, exclude_cwds={"D:/code/registered"})

    cwds = [r.cwd for r in result]
    assert "D:/code/registered" not in cwds
    assert "D:/code/new" in cwds


def test_detect_cwds_caps_at_ten(tmp_path: Path, monkeypatch) -> None:
    transcripts_root = tmp_path / "claude_projects"
    monkeypatch.setattr(
        "claude_mnemos.core.cwd_detection._transcripts_root",
        lambda: transcripts_root,
    )
    now = datetime.now(tz=UTC)
    for i in range(15):
        _write_jsonl(
            transcripts_root / "p1" / f"s{i}.jsonl",
            f"D:/code/app{i}",
            now - timedelta(hours=i),
        )

    result = detect_cwds(now=now)
    assert len(result) == 10
