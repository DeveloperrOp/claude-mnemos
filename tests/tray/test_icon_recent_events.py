"""Tests for read_recent_events — pure-function log parser, no pystray needed."""

from __future__ import annotations

from pathlib import Path

from claude_mnemos.tray.icon import read_recent_events


def test_returns_empty_when_log_missing(tmp_path: Path) -> None:
    assert read_recent_events(tmp_path / "no.log") == []


def test_parses_standard_log_lines(tmp_path: Path) -> None:
    log = tmp_path / "supervisor.log"
    log.write_text(
        "2026-04-30 14:30:01,123 [INFO] claude_mnemos.tray.supervisor: "
        "state Starting → Running\n"
        "2026-04-30 14:35:00,456 [WARNING] claude_mnemos.tray.supervisor: "
        "daemon crashed (exit=1), crash_count=1/5min\n",
        encoding="utf-8",
    )
    events = read_recent_events(log)
    assert len(events) == 2
    assert events[0].startswith("14:30:01")
    assert "Starting → Running" in events[0]
    assert events[1].startswith("14:35:00")
    assert "crash_count=1" in events[1]


def test_skips_unparseable_lines(tmp_path: Path) -> None:
    log = tmp_path / "supervisor.log"
    log.write_text(
        "garbage line without timestamp\n"
        "2026-04-30 12:00:00,000 [INFO] x.y: real event\n"
        "  another bad line\n",
        encoding="utf-8",
    )
    events = read_recent_events(log)
    assert len(events) == 1
    assert "real event" in events[0]


def test_returns_at_most_limit_entries(tmp_path: Path) -> None:
    log = tmp_path / "supervisor.log"
    lines = [
        f"2026-04-30 14:{i:02d}:00,000 [INFO] x.y: event {i}"
        for i in range(20)
    ]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    events = read_recent_events(log, limit=5)
    assert len(events) == 5
    # Oldest-first ordering of the *last 5* lines (events 15-19).
    assert "event 15" in events[0]
    assert "event 19" in events[-1]


def test_truncates_long_messages(tmp_path: Path) -> None:
    log = tmp_path / "supervisor.log"
    long_msg = "x" * 200
    log.write_text(
        f"2026-04-30 14:30:00,000 [INFO] x.y: {long_msg}\n",
        encoding="utf-8",
    )
    events = read_recent_events(log)
    assert len(events) == 1
    # 70-char cap with ellipsis
    assert events[0].endswith("…")
    assert len(events[0]) < 100
