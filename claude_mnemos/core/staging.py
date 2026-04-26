from __future__ import annotations

import contextlib
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal

from claude_mnemos.core.atomic import atomic_write  # noqa: F401  (kept for tests)
from claude_mnemos.core.snapshots import (
    compute_snapshot_path,
    create_snapshot,
    create_snapshot_at,
    restore_from_snapshot,
)

STAGING_DIRNAME = ".staging"
TRASH_DIRNAME = ".trash"


class StagingPromoteError(RuntimeError):
    """Raised when promote_to_vault fails (snapshot fail or partial-write rollback)."""


@dataclass(frozen=True)
class PromoteResult:
    success: bool
    snapshot: Path | None
    error: str | None = None
    recovery_hint: str | None = None


class StagingTransaction:
    """Context-managed staging area for atomic vault writes.

    Usage:
        with StagingTransaction(vault, "abc-123") as txn:
            txn.write(Path("wiki/entities/foo.md"), "...")
            txn.write(Path(".manifest.json"), "...")
            txn.promote_to_vault()

    On exit without explicit promote (clean OR exception) — staging is rejected:
    moved to `.trash/rejected-<op_id>-<ts>/` for inspection. Vault is never touched
    until promote_to_vault is called and succeeds.
    """

    def __init__(
        self,
        vault: Path,
        operation_id: str,
        operation_type: str = "ingest",
    ) -> None:
        self.vault = vault
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.staging_dir = vault / STAGING_DIRNAME / operation_id
        self._promoted = False
        self._rejected = False
        self._locked_snapshot_path: Path | None = None

    def __enter__(self) -> StagingTransaction:
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if not self._promoted and not self._rejected:
            reason = (
                f"exited with exception {exc_type.__name__}: {exc}"
                if exc_type is not None
                else "exited without promote_to_vault()"
            )
            # Best-effort cleanup; never mask original exception.
            with contextlib.suppress(OSError):
                self.reject(reason)
        return False  # never swallow

    def pre_promote_snapshot_path(self) -> Path:
        """Lock in and return the snapshot path that promote_to_vault will use.

        First call computes the path; subsequent calls return the same path.
        After finalize (promoted or rejected), raises RuntimeError.
        """
        if self._promoted or self._rejected:
            raise RuntimeError(
                "StagingTransaction is finalized; cannot lock snapshot path"
            )
        if self._locked_snapshot_path is None:
            self._locked_snapshot_path = compute_snapshot_path(
                self.vault,
                operation_id=self.operation_id,
                operation_type=self.operation_type,
            )
        return self._locked_snapshot_path

    def write(self, relative_path: Path, content: str) -> None:
        """Write content to staging area at `relative_path`. NOT to vault."""
        if self._promoted or self._rejected:
            raise RuntimeError("StagingTransaction is finalized; cannot write")
        target = self.staging_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def promote_to_vault(self) -> PromoteResult:
        """Snapshot vault, then atomically move staging files into vault.

        On any failure during the move loop, restore vault from snapshot and raise
        StagingPromoteError. On snapshot creation failure, vault is untouched and
        StagingPromoteError still fires (no restore needed).
        """
        if self._promoted:
            raise RuntimeError("StagingTransaction already promoted")
        if self._rejected:
            raise RuntimeError("StagingTransaction already rejected; cannot promote")

        # 1. Snapshot vault BEFORE moving anything. Use precomputed path if
        # caller invoked pre_promote_snapshot_path() — guarantees activity
        # entries written into staging reference the correct snapshot.
        try:
            if self._locked_snapshot_path is not None:
                snapshot = create_snapshot_at(
                    self.vault,
                    self._locked_snapshot_path,
                    operation_id=self.operation_id,
                    operation_type=self.operation_type,
                )
            else:
                snapshot = create_snapshot(
                    self.vault,
                    operation_id=self.operation_id,
                    operation_type=self.operation_type,
                )
        except Exception as exc:
            raise StagingPromoteError(
                f"snapshot creation failed: {exc}"
            ) from exc

        # 2. Move staged files into vault, one at a time, via shutil.move
        # (atomic rename on same filesystem; binary-safe; faster than read+write).
        try:
            for staged in self.staging_dir.rglob("*"):
                if not staged.is_file():
                    continue
                relative = staged.relative_to(self.staging_dir)
                target = self.vault / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                # shutil.move is atomic on same FS (uses os.rename) and is binary-safe.
                # Pipeline guarantees no collisions: already-existing pages are excluded
                # via skipped_collisions BEFORE writing to staging.
                shutil.move(str(staged), str(target))
        except Exception as exc:
            restore = restore_from_snapshot(self.vault, snapshot)
            self._promoted = True  # mark finalized so __exit__ doesn't reject
            # Restore preserves .staging/ across the swap (so other concurrent
            # transactions survive); clean up our own partial staging dir here.
            shutil.rmtree(self.staging_dir, ignore_errors=True)
            if restore.success:
                raise StagingPromoteError(
                    f"promote failed mid-move; vault restored from snapshot. cause: {exc}"
                ) from exc
            raise StagingPromoteError(
                f"promote failed mid-move; restore ALSO failed: {restore.error}. "
                f"recovery hint: {restore.recovery_hint}. original cause: {exc}"
            ) from exc

        # 3. Cleanup staging.
        shutil.rmtree(self.staging_dir, ignore_errors=True)
        self._promoted = True

        return PromoteResult(success=True, snapshot=snapshot)

    def reject(self, reason: str) -> None:
        """Move staging dir into .trash/rejected-<op_id>-<ts>/ with a .reason.txt."""
        if self._promoted:
            raise RuntimeError("StagingTransaction already promoted; cannot reject")
        if self._rejected:
            return  # idempotent
        ts = int(time.time() * 1000)
        trash_root = self.vault / TRASH_DIRNAME
        trash_root.mkdir(parents=True, exist_ok=True)
        trash_dir = trash_root / f"rejected-{self.operation_id}-{ts}"
        if self.staging_dir.exists():
            shutil.move(str(self.staging_dir), str(trash_dir))
        else:
            trash_dir.mkdir(parents=True, exist_ok=True)
        (trash_dir / ".reason.txt").write_text(reason, encoding="utf-8")
        self._rejected = True
