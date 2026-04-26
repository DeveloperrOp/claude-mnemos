import threading
from pathlib import Path

import pytest

from claude_mnemos.core.locks import LockTimeoutError, pipeline_lock


def test_lock_acquires_and_releases(tmp_path: Path):
    lock_dir = tmp_path
    with pipeline_lock(lock_dir, timeout=1.0):
        assert (lock_dir / ".pipeline.lock").exists()
    # после выхода — lock освобождён, второй вход проходит мгновенно
    with pipeline_lock(lock_dir, timeout=0.1):
        pass


def test_lock_timeout_raises(tmp_path: Path):
    lock_dir = tmp_path
    holder_started = threading.Event()
    holder_done = threading.Event()

    def hold_lock():
        with pipeline_lock(lock_dir, timeout=5.0):
            holder_started.set()
            holder_done.wait(timeout=2.0)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    assert holder_started.wait(timeout=1.0)

    try:
        with pytest.raises(LockTimeoutError):  # noqa: SIM117
            with pipeline_lock(lock_dir, timeout=0.2):
                pass
    finally:
        holder_done.set()
        thread.join(timeout=2.0)
