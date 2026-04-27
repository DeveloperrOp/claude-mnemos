"""In-process integration: real VaultObserver + handler over a tmp vault."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest

from claude_mnemos.core.snapshots import create_snapshot, restore_from_snapshot
from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler
from claude_mnemos.daemon.watchdog_observer import VaultObserver
from claude_mnemos.state.activity import ActivityLog

pytestmark = pytest.mark.slow


def _seed_page(vault: Path, rel: str) -> Path:
    full = vault / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(
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
    return full


def _wait_for(
    predicate: Callable[[], bool],
    *,
    timeout: float = 3.0,
    interval: float = 0.05,
) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


@pytest.fixture
def harness(vault: Path):
    tracker = OurWritesTracker(ttl_s=60.0)
    alerts = Alerts()
    handler = VaultChangeHandler(vault, tracker, alerts)
    observer = VaultObserver(vault, handler)
    observer.start()
    try:
        yield observer, tracker, alerts
    finally:
        observer.stop()


def test_external_modify_marks_page(vault: Path, harness):
    _, _, _ = harness
    page = _seed_page(vault, "wiki/entities/foo.md")

    # External modify (preserve frontmatter, change body).
    text = page.read_text(encoding="utf-8")
    page.write_text(text + "\nfresh edit\n", encoding="utf-8")

    def marked() -> bool:
        return "agent_written: false" in page.read_text(encoding="utf-8")

    assert _wait_for(marked, timeout=4.0)

    log = ActivityLog.load(vault)
    assert any(e.operation_type == "human_edit_detected" for e in log.entries)


def test_self_write_via_tracker_not_marked(vault: Path, harness):
    _, tracker, _ = harness
    page = _seed_page(vault, "wiki/entities/foo.md")
    text = page.read_text(encoding="utf-8")

    # add() with default TTL keeps the path in the tracker until it expires —
    # any delayed watchdog event arrives while the path is still recognized
    # as a self-write. This mirrors the handler's own atomic_write surround.
    tracker.add(page)
    page.write_text(text + "\nself write\n", encoding="utf-8")
    # Sleep less than TTL so the event has time to be processed and matched.
    time.sleep(1.0)
    assert "agent_written: true" in page.read_text(encoding="utf-8")


def test_dotfile_change_ignored(vault: Path, harness):
    _, _, alerts = harness
    staging_page = vault / ".staging/foo.md"
    staging_page.parent.mkdir(parents=True, exist_ok=True)
    staging_page.write_text("anything", encoding="utf-8")
    time.sleep(0.5)
    # No alerts, no activity entries.
    assert ActivityLog.load(vault).entries == []
    assert alerts.list() == []


def test_paused_tracker_blocks_marking(vault: Path, harness):
    _, tracker, _ = harness
    page = _seed_page(vault, "wiki/entities/foo.md")

    with tracker.paused():
        text = page.read_text(encoding="utf-8")
        page.write_text(text + "\npaused edit\n", encoding="utf-8")
        time.sleep(0.5)

    # Inside paused() the modification was ignored — page still agent_written.
    assert "agent_written: true" in page.read_text(encoding="utf-8")

    # After resuming, a new modify should be picked up.
    text = page.read_text(encoding="utf-8")
    page.write_text(text + "\nafter pause\n", encoding="utf-8")

    def marked() -> bool:
        return "agent_written: false" in page.read_text(encoding="utf-8")

    assert _wait_for(marked, timeout=4.0)


def test_restore_under_pause_no_new_marks(vault: Path, harness):
    """Restore must not generate human_edit_detected entries from its own swap."""
    _, tracker, _ = harness
    _seed_page(vault, "wiki/entities/foo.md")
    snap = create_snapshot(vault, operation_id="op-int-1", operation_type="ingest")

    # Drain any handler reactions caused by snapshot creation.
    time.sleep(1.0)

    result = restore_from_snapshot(vault, snap, tracker=tracker)
    assert result.success is True

    # Wait long enough for any straggling events to arrive after restore.
    time.sleep(1.5)

    log = ActivityLog.load(vault)
    # The restored vault came from before we'd written any human_edit_detected
    # entries, so the activity log should be empty (or still empty if it was).
    assert all(e.operation_type != "human_edit_detected" for e in log.entries)
