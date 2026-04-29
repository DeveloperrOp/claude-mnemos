from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / JOBS_DB_FILENAME)


def test_new_store_paused_until_is_none(store: JobStore) -> None:
    assert store.paused_until() is None


def test_pause_queue_sets_paused_until(store: JobStore) -> None:
    when = datetime.now(UTC) + timedelta(hours=5)
    store.pause_queue(until=when)
    paused = store.paused_until()
    assert paused is not None
    # Allow second-level slop
    assert abs((paused - when).total_seconds()) < 2


def test_pause_queue_overwrites_earlier_pause(store: JobStore) -> None:
    early = datetime.now(UTC) + timedelta(hours=1)
    later = datetime.now(UTC) + timedelta(hours=10)
    store.pause_queue(until=early)
    store.pause_queue(until=later)
    paused = store.paused_until()
    assert paused is not None
    assert abs((paused - later).total_seconds()) < 2


def test_resume_queue_clears_paused_until(store: JobStore) -> None:
    store.pause_queue(until=datetime.now(UTC) + timedelta(hours=5))
    store.resume_queue()
    assert store.paused_until() is None


def test_paused_until_persists_across_jobstore_instances(tmp_path: Path) -> None:
    db_path = tmp_path / JOBS_DB_FILENAME
    when = datetime.now(UTC) + timedelta(hours=5)
    with JobStore(db_path) as store:
        store.pause_queue(until=when)
    # Re-open same db
    with JobStore(db_path) as fresh:
        paused = fresh.paused_until()
    assert paused is not None
    assert abs((paused - when).total_seconds()) < 2


def test_is_paused_returns_true_while_in_window(store: JobStore) -> None:
    store.pause_queue(until=datetime.now(UTC) + timedelta(hours=1))
    assert store.is_paused() is True


def test_is_paused_returns_false_after_window(store: JobStore) -> None:
    store.pause_queue(until=datetime.now(UTC) - timedelta(seconds=1))
    assert store.is_paused() is False
