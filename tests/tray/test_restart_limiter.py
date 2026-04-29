from __future__ import annotations

from claude_mnemos.tray.supervisor import RestartLimiter


def test_initial_state_allows_restart() -> None:
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    assert lim.crash_count() == 0
    assert lim.should_restart() is True


def test_records_crashes_and_blocks_after_threshold() -> None:
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    # Three crashes at the same monotonic time
    lim.record_crash(now=100.0)
    lim.record_crash(now=100.5)
    lim.record_crash(now=101.0)
    assert lim.crash_count(now=101.0) == 3
    assert lim.should_restart(now=101.0) is True  # exactly == max, still allow

    lim.record_crash(now=101.5)
    assert lim.crash_count(now=101.5) == 4
    assert lim.should_restart(now=101.5) is False


def test_old_crashes_outside_window_are_pruned() -> None:
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    lim.record_crash(now=0.0)
    lim.record_crash(now=10.0)
    lim.record_crash(now=20.0)
    lim.record_crash(now=30.0)
    # All 4 are within 5min — limiter blocks
    assert lim.should_restart(now=30.0) is False
    # Skip ahead 6 minutes — all 4 fall outside the 300s window
    assert lim.crash_count(now=400.0) == 0
    assert lim.should_restart(now=400.0) is True


def test_reset_clears_counter() -> None:
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    lim.record_crash(now=0.0)
    lim.record_crash(now=1.0)
    lim.record_crash(now=2.0)
    lim.record_crash(now=3.0)
    assert lim.should_restart(now=3.0) is False
    lim.reset()
    assert lim.crash_count() == 0
    assert lim.should_restart() is True


def test_backoff_seconds_progression() -> None:
    """1st crash → 1s, 2nd → 2s, 3rd → 4s, then capped at 4s."""
    lim = RestartLimiter(max_crashes=3, window_seconds=300.0)
    lim.record_crash(now=0.0)
    assert lim.next_backoff_seconds() == 1.0
    lim.record_crash(now=1.0)
    assert lim.next_backoff_seconds() == 2.0
    lim.record_crash(now=2.0)
    assert lim.next_backoff_seconds() == 4.0
    lim.record_crash(now=3.0)
    assert lim.next_backoff_seconds() == 4.0  # capped
