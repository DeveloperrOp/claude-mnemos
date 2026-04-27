"""Unit tests for VaultChangeHandler — direct event dispatch, no real Observer."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler


def _frozen_now() -> datetime:
    return datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC)


def _seed_page(
    vault: Path,
    rel: str,
    *,
    title: str = "Foo",
    page_type: str = "entity",
    extras: dict[str, Any] | None = None,
    agent_written: bool = True,
) -> Path:
    full = vault / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    extras_block = ""
    if extras:
        for k, v in extras.items():
            extras_block += f"{k}: {v}\n"
    full.write_text(
        f"""---
title: {title}
type: {page_type}
created: 2026-04-26
updated: 2026-04-26
agent_written: {'true' if agent_written else 'false'}
{extras_block}---
body
""",
        encoding="utf-8",
    )
    return full


def _make_handler(
    vault: Path,
    *,
    tracker: OurWritesTracker | None = None,
    alerts: Alerts | None = None,
    clock=_frozen_now,
) -> tuple[VaultChangeHandler, OurWritesTracker, Alerts]:
    t = tracker or OurWritesTracker(ttl_s=60.0)
    a = alerts or Alerts()
    h = VaultChangeHandler(vault, t, a, clock=clock, lock_timeout_s=2.0)
    return h, t, a


def _make_old(path: Path) -> None:
    """Backdate mtime so test reads are deterministic (no real-time dependency)."""
    old = time.time() - 60.0
    os.utime(path, (old, old))


def test_skip_directory_event(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    h, _, alerts = _make_handler(vault)
    h.on_modified(DirModifiedEvent(str(vault / "wiki")))
    assert alerts.list() == []


def test_skip_dotfile_path(tmp_path: Path):
    vault = tmp_path / "vault"
    p = _seed_page(vault, ".staging/foo.md")
    _make_old(p)
    h, _, alerts = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(p)))
    # Page must remain agent_written=True; nothing logged.
    assert "agent_written: true" in p.read_text(encoding="utf-8")
    assert alerts.list() == []


def test_skip_outside_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    other = tmp_path / "other.md"
    other.write_text("hi", encoding="utf-8")
    h, _, alerts = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(other)))
    assert alerts.list() == []


def test_skip_non_wiki(tmp_path: Path):
    vault = tmp_path / "vault"
    p = _seed_page(vault, "raw/chats/foo.md")
    _make_old(p)
    h, _, alerts = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(p)))
    assert "agent_written: true" in p.read_text(encoding="utf-8")
    assert alerts.list() == []


def test_skip_non_md(tmp_path: Path):
    vault = tmp_path / "vault"
    txt = vault / "wiki/entities/note.txt"
    txt.parent.mkdir(parents=True, exist_ok=True)
    txt.write_text("not markdown", encoding="utf-8")
    h, _, alerts = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(txt)))
    assert alerts.list() == []


def test_skip_when_tracker_contains(tmp_path: Path):
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md")
    _make_old(p)
    tracker = OurWritesTracker(ttl_s=60.0)
    tracker.add(p)
    h, _, _ = _make_handler(vault, tracker=tracker)
    h.on_modified(FileModifiedEvent(str(p)))
    assert "agent_written: true" in p.read_text(encoding="utf-8")


def test_skip_when_tracker_paused(tmp_path: Path):
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md")
    _make_old(p)
    tracker = OurWritesTracker(ttl_s=60.0)
    h, _, _ = _make_handler(vault, tracker=tracker)
    with tracker.paused():
        h.on_modified(FileModifiedEvent(str(p)))
    assert "agent_written: true" in p.read_text(encoding="utf-8")


def test_modified_marks_human_edited(tmp_path: Path):
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md")
    _make_old(p)
    h, _, alerts = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(p)))
    text = p.read_text(encoding="utf-8")
    assert "agent_written: false" in text
    assert "last_human_edit:" in text
    assert alerts.list() == []


def test_modified_preserves_obsidian_extras(tmp_path: Path):
    vault = tmp_path / "vault"
    p = _seed_page(
        vault,
        "wiki/entities/foo.md",
        extras={"cssclass": "my-class", "obsidianUIMode": "preview"},
    )
    _make_old(p)
    h, _, _ = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(p)))
    text = p.read_text(encoding="utf-8")
    assert "cssclass: my-class" in text
    assert "obsidianUIMode: preview" in text
    assert "agent_written: false" in text


def test_modified_writes_activity_entry(tmp_path: Path):
    from claude_mnemos.state.activity import ActivityLog

    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md")
    _make_old(p)
    h, _, _ = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(p)))
    log = ActivityLog.load(vault)
    assert len(log.entries) == 1
    e = log.entries[0]
    assert e.operation_type == "human_edit_detected"
    assert e.can_undo is False
    assert e.snapshot_path is None
    assert e.affected_pages == ["wiki/entities/foo.md"]


def test_already_human_edited_page_still_marked(tmp_path: Path):
    """If page already has agent_written=False, handler still bumps last_human_edit."""
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md", agent_written=False)
    _make_old(p)
    h, _, _ = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(p)))
    text = p.read_text(encoding="utf-8")
    assert "agent_written: false" in text


def test_modified_invalid_yaml_alerts_no_mutation(tmp_path: Path):
    vault = tmp_path / "vault"
    p = vault / "wiki/entities/broken.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not a markdown page at all", encoding="utf-8")
    _make_old(p)
    h, _, alerts = _make_handler(vault)
    h.on_modified(FileModifiedEvent(str(p)))
    assert p.read_text(encoding="utf-8") == "not a markdown page at all"
    items = alerts.list()
    assert len(items) == 1
    assert items[0].kind == "parse_failed"


def test_modified_pipeline_lock_timeout_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md")
    _make_old(p)
    h, _, alerts = _make_handler(vault)

    # Hold the pipeline lock so the handler timeout fires.
    with pipeline_lock(vault, timeout=2.0):
        # Within the with-block the lock is held, handler timeout=2.0 will fire fast.
        # We need the handler to actually try and timeout — set short timeout via
        # constructor (already 2.0) and a holder process. Same-process FileLock
        # is reentrant, so use monkeypatch to force a timeout.
        def boom_acquire(self: Any) -> None:
            from filelock import Timeout

            raise Timeout("forced")

        monkeypatch.setattr("filelock.FileLock.acquire", boom_acquire)
        h.on_modified(FileModifiedEvent(str(p)))

    items = alerts.list()
    assert any(a.kind == "lock_timeout" for a in items)
    # Page should not have been mutated.
    assert "agent_written: true" in p.read_text(encoding="utf-8")


def test_created_alerts_no_mutation(tmp_path: Path):
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/new.md")
    h, _, alerts = _make_handler(vault)
    h.on_created(FileCreatedEvent(str(p)))
    items = alerts.list()
    assert len(items) == 1
    assert items[0].kind == "external_create"
    # No mutation.
    assert "agent_written: true" in p.read_text(encoding="utf-8")


def test_created_dir_skipped(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    h, _, alerts = _make_handler(vault)
    h.on_created(DirCreatedEvent(str(vault / "wiki" / "entities")))
    assert alerts.list() == []


def test_moved_alerts(tmp_path: Path):
    vault = tmp_path / "vault"
    p_old = _seed_page(vault, "wiki/entities/old.md")
    p_new = vault / "wiki/entities/new.md"
    h, _, alerts = _make_handler(vault)
    h.on_moved(FileMovedEvent(str(p_old), str(p_new)))
    items = alerts.list()
    assert len(items) == 1
    assert items[0].kind == "external_rename"


def test_handler_exception_inside_mark_logs_alert_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md")
    _make_old(p)
    h, _, alerts = _make_handler(vault)

    def boom(_path: Path):  # noqa: ANN202
        raise RuntimeError("unexpected")

    monkeypatch.setattr("claude_mnemos.daemon.watchdog_handler.read_page", boom)

    # Must not raise out of the handler.
    h.on_modified(FileModifiedEvent(str(p)))

    items = alerts.list()
    assert any(a.kind == "handler_error" for a in items)


def test_self_write_loop_prevention(tmp_path: Path):
    """During the handler's own write-back, the path must be in the tracker."""
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md")
    _make_old(p)
    tracker = OurWritesTracker(ttl_s=60.0)
    seen_during_write: list[bool] = []

    from claude_mnemos.daemon import watchdog_handler as wh

    real_atomic_write = wh.atomic_write

    def spy_atomic_write(target: Path, content: str, **kwargs: Any) -> None:
        seen_during_write.append(tracker.contains(target))
        real_atomic_write(target, content, **kwargs)

    wh.atomic_write = spy_atomic_write  # type: ignore[assignment]
    try:
        h, _, _ = _make_handler(vault, tracker=tracker)
        h.on_modified(FileModifiedEvent(str(p)))
    finally:
        wh.atomic_write = real_atomic_write  # type: ignore[assignment]

    # atomic_write was called twice (page + activity log); the page write must
    # have seen the tracker registration.
    assert any(seen_during_write)
    # After exit, path must be removed from tracker.
    assert not tracker.contains(p)


def test_clock_is_used_for_last_human_edit(tmp_path: Path):
    vault = tmp_path / "vault"
    p = _seed_page(vault, "wiki/entities/foo.md")
    _make_old(p)

    fixed = datetime(2030, 6, 7, 8, 9, 10, tzinfo=UTC)
    h = VaultChangeHandler(
        vault, OurWritesTracker(ttl_s=60.0), Alerts(), clock=lambda: fixed
    )
    h.on_modified(FileModifiedEvent(str(p)))
    text = p.read_text(encoding="utf-8")
    assert "2030-06-07T08:09:10" in text


