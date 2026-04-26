from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout


class LockTimeoutError(TimeoutError):
    """Raised when pipeline lock cannot be acquired within timeout."""


@contextmanager
def pipeline_lock(lock_dir: Path, timeout: float = 60.0) -> Generator[Path, None, None]:
    """Acquire the per-vault pipeline lock; release on exit.

    Spec invariant (8.1): one FileLock for the whole ingest pipeline.
    """
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / ".pipeline.lock"
    lock = FileLock(lock_path, timeout=timeout)
    try:
        lock.acquire()
    except Timeout as exc:
        raise LockTimeoutError(
            f"pipeline lock at {lock_path} not acquired within {timeout}s"
        ) from exc
    try:
        yield lock_path
    finally:
        lock.release()
