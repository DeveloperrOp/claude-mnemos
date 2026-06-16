from __future__ import annotations

from pathlib import Path

from watchdog.events import FileModifiedEvent

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler

_FM = """---
title: Foo
type: concept
status: draft
confidence: 0.7
flavor: []
sources: []
related: []
created: '2026-04-26'
updated: '2026-04-26'
agent_written: true
---
body text
"""


def _seed_page(vault: Path) -> Path:
    p = vault / "wiki" / "concepts" / "foo.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_FM, encoding="utf-8")
    return p


def _handler(vault: Path) -> VaultChangeHandler:
    return VaultChangeHandler(vault, OurWritesTracker(), Alerts())


def _agent_written(p: Path) -> bool:
    return "agent_written: false" not in p.read_text(encoding="utf-8")


def test_metadata_only_event_does_not_flip(tmp_path: Path) -> None:
    p = _seed_page(tmp_path)
    h = _handler(tmp_path)  # seeds foo.md signature at construction
    h.on_modified(FileModifiedEvent(str(p)))
    assert _agent_written(p) is True


def test_real_content_edit_flips(tmp_path: Path) -> None:
    p = _seed_page(tmp_path)
    h = _handler(tmp_path)
    p.write_text(_FM.replace("body text", "EDITED by a human"), encoding="utf-8")
    h.on_modified(FileModifiedEvent(str(p)))
    assert _agent_written(p) is False


def test_self_write_rebaselines_signature(tmp_path: Path) -> None:
    p = _seed_page(tmp_path)
    h = _handler(tmp_path)
    new = _FM.replace("body text", "ingested content")
    h.tracker.add(p)
    p.write_text(new, encoding="utf-8")
    h.on_modified(FileModifiedEvent(str(p)))  # self-write -> re-baseline, skip
    h.tracker.remove(p)
    h.on_modified(FileModifiedEvent(str(p)))  # metadata event on new content
    assert _agent_written(p) is True


def test_unseen_page_first_event_seeds_not_flips(tmp_path: Path) -> None:
    # A page created AFTER the handler was constructed (no baseline) must be
    # seeded on its first event, not flipped.
    h = _handler(tmp_path)  # constructed with empty vault -> nothing seeded
    p = _seed_page(tmp_path)
    h.on_modified(FileModifiedEvent(str(p)))  # first-ever event: seed, no flip
    assert _agent_written(p) is True
    p.write_text(_FM.replace("body text", "now edited"), encoding="utf-8")
    h.on_modified(FileModifiedEvent(str(p)))  # now a real change -> flip
    assert _agent_written(p) is False
