import contextlib
import os
import time
import uuid
from pathlib import Path


class FileBusyError(OSError):
    """Raised when atomic_write cannot replace target after max_attempts."""


def atomic_write(
    target: Path,
    content: str,
    *,
    max_attempts: int = 5,
    retry_base_delay: float = 0.2,
    encoding: str = "utf-8",
) -> None:
    """Atomically write `content` to `target`.

    Writes to a sibling `.tmp` file and uses os.replace() for atomic rename.
    On Windows, retries up to `max_attempts` with exponential backoff when
    os.replace raises PermissionError (typical antivirus/indexer race).

    Spec: section 7.3 (Layer 3).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")

    try:
        tmp.write_text(content, encoding=encoding)
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                os.replace(tmp, target)
                return
            except PermissionError as exc:
                last_exc = exc
                time.sleep(retry_base_delay * (2 ** attempt))
        raise FileBusyError(
            f"could not replace {target} after {max_attempts} attempts"
        ) from last_exc
    finally:
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()
