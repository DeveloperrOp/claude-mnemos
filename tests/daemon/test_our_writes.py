from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from claude_mnemos.daemon.our_writes import OurWritesTracker


def test_add_then_contains(tmp_path: Path):
    tracker = OurWritesTracker()
    p = tmp_path / "foo.md"
    p.write_text("hi", encoding="utf-8")
    tracker.add(p)
    assert tracker.contains(p)


def test_remove_makes_contains_false(tmp_path: Path):
    tracker = OurWritesTracker()
    p = tmp_path / "foo.md"
    p.write_text("hi", encoding="utf-8")
    tracker.add(p)
    tracker.remove(p)
    assert not tracker.contains(p)


def test_ttl_expiration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_now = [1000.0]

    def fake_monotonic() -> float:
        return fake_now[0]

    monkeypatch.setattr("claude_mnemos.daemon.our_writes.time.monotonic", fake_monotonic)

    tracker = OurWritesTracker(ttl_s=5.0)
    p = tmp_path / "foo.md"
    p.write_text("hi", encoding="utf-8")
    tracker.add(p)
    fake_now[0] = 1004.99
    assert tracker.contains(p)
    fake_now[0] = 1005.01
    assert not tracker.contains(p)


def test_writing_context_keeps_path_via_ttl(tmp_path: Path):
    # writing() adds each path with the TTL and does NOT explicitly remove on
    # exit: a delayed self-write event after the block must still match
    # contains() within the TTL window (the TTL's documented purpose — the OS
    # can emit our own write's MODIFIED event late). The path expires via TTL.
    tracker = OurWritesTracker(ttl_s=60.0)
    p1 = tmp_path / "a.md"
    p2 = tmp_path / "b.md"

    with tracker.writing([p1, p2]):
        assert tracker.contains(p1)
        assert tracker.contains(p2)
    # Still ours within the TTL window (delayed-event grace), not removed.
    assert tracker.contains(p1)
    assert tracker.contains(p2)


def test_writing_context_keeps_path_on_exception(tmp_path: Path):
    # An exception inside writing() leaves the path tracked (TTL) rather than
    # explicitly removed, so a partial write's delayed events stay suppressed.
    tracker = OurWritesTracker(ttl_s=60.0)
    p = tmp_path / "foo.md"
    with pytest.raises(RuntimeError), tracker.writing([p]):
        assert tracker.contains(p)
        raise RuntimeError("boom")
    assert tracker.contains(p)


def test_writing_context_path_expires_after_ttl(tmp_path: Path):
    # A negative TTL deadline is already in the past, so the path is GC'd out on
    # the next contains() — proves writing() relies on TTL expiry, not remove().
    tracker = OurWritesTracker(ttl_s=-1.0)
    p = tmp_path / "a.md"
    with tracker.writing([p]):
        pass
    assert not tracker.contains(p)


def test_paused_context_disables_membership(tmp_path: Path):
    tracker = OurWritesTracker(pause_cooldown_s=0.0)
    p = tmp_path / "foo.md"
    p.write_text("hi", encoding="utf-8")
    tracker.add(p)
    assert tracker.contains(p)

    with tracker.paused():
        assert tracker.is_paused
    assert not tracker.is_paused
    assert tracker.contains(p)  # still in set, but flag was off after exit


def test_paused_context_restores_on_exception():
    tracker = OurWritesTracker(pause_cooldown_s=0.0)
    with pytest.raises(RuntimeError), tracker.paused():
        assert tracker.is_paused
        raise RuntimeError("boom")
    assert not tracker.is_paused


def test_paused_cooldown_keeps_paused_after_exit(monkeypatch: pytest.MonkeyPatch):
    fake_now = [1000.0]

    def fake_monotonic() -> float:
        return fake_now[0]

    monkeypatch.setattr(
        "claude_mnemos.daemon.our_writes.time.monotonic", fake_monotonic
    )

    tracker = OurWritesTracker(pause_cooldown_s=2.0)
    with tracker.paused():
        assert tracker.is_paused
    # Just after exit, cooldown is still active.
    fake_now[0] = 1000.5
    assert tracker.is_paused
    # After cooldown expires, is_paused flips to False.
    fake_now[0] = 1003.0
    assert not tracker.is_paused


def test_thread_safety_smoke(tmp_path: Path):
    tracker = OurWritesTracker(ttl_s=60.0)
    p = tmp_path / "foo.md"
    p.write_text("hi", encoding="utf-8")
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(500):
                tracker.add(p)
                tracker.contains(p)
                tracker.remove(p)
        except BaseException as exc:  # pragma: no cover - thread aborts only on real bug
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors


def test_normalizes_path_via_resolve(tmp_path: Path):
    tracker = OurWritesTracker()
    p = tmp_path / "foo.md"
    p.write_text("hi", encoding="utf-8")
    tracker.add(p)
    # absolute, but constructed differently — should still resolve to same canonical path
    same_path = Path(str(p))
    assert tracker.contains(same_path)


def test_paused_concurrent_with_add(tmp_path: Path):
    """Pause and add can race; pause flag flip is independent of set membership."""
    tracker = OurWritesTracker()
    p = tmp_path / "foo.md"
    p.write_text("hi", encoding="utf-8")

    started = threading.Event()
    finished = threading.Event()

    def adder() -> None:
        started.wait()
        for _ in range(200):
            tracker.add(p)
            tracker.remove(p)
        finished.set()

    th = threading.Thread(target=adder)
    th.start()
    started.set()
    while not finished.is_set():
        with tracker.paused():
            time.sleep(0.001)
    th.join()
