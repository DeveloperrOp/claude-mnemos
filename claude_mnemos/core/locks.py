from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout


class LockTimeoutError(TimeoutError):
    """Raised when pipeline lock cannot be acquired within timeout."""


def build_pipeline_lock(lock_dir: Path, timeout: float = 60.0) -> FileLock:
    """Construct (but do not acquire) the per-vault pipeline FileLock.

    Exposed so async callers can offload the blocking ``acquire()`` to a
    worker thread (a 60s blocking acquire on the event loop freezes the whole
    daemon). The FileLock is not thread-affine — acquire and release may run
    on different threads.
    """
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir.parent / f".{lock_dir.name}.pipeline.lock"
    return FileLock(lock_path, timeout=timeout)


@contextmanager
def pipeline_lock(lock_dir: Path, timeout: float = 60.0) -> Generator[Path, None, None]:
    """Acquire the per-vault pipeline lock; release on exit.

    Spec invariant (8.1): one FileLock for the whole ingest pipeline.
    Blocking — only safe in sync code (FastAPI runs sync handlers in a
    threadpool). Async handlers must offload via ``build_pipeline_lock`` +
    ``asyncio.to_thread``.
    """
    lock = build_pipeline_lock(lock_dir, timeout)
    try:
        lock.acquire()
    except Timeout as exc:
        raise LockTimeoutError(
            f"pipeline lock at {lock.lock_file} not acquired within {timeout}s"
        ) from exc
    try:
        yield Path(lock.lock_file)
    finally:
        lock.release()
