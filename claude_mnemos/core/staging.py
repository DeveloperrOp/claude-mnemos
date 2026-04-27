from __future__ import annotations

import contextlib
import shutil
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Literal

from claude_mnemos.core.atomic import atomic_write  # noqa: F401  (kept for tests)
from claude_mnemos.core.snapshots import (
    compute_snapshot_path,
    create_snapshot,
    create_snapshot_at,
    restore_from_snapshot,
)

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker

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
        # Plan #8 ontology extensions: queued vault mutations applied during promote
        # AFTER staged files are moved into vault. Snapshot taken before promote
        # captures pre-mutation state, so any failure rolls back via restore.
        self._to_move: list[tuple[str, str]] = []
        self._to_remove: list[tuple[str, bool]] = []

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

    def move(self, src_relpath: str, dst_relpath: str) -> None:
        """Queue a vault file move. Applied during promote AFTER staged writes.

        `src_relpath` must exist in the vault at promote time; otherwise the move
        fails the whole promote and rolls back via snapshot restore.
        """
        if self._promoted or self._rejected:
            raise RuntimeError("StagingTransaction is finalized; cannot move")
        if not src_relpath or not dst_relpath:
            raise ValueError("src/dst relpath must be non-empty")
        if src_relpath == dst_relpath:
            raise ValueError("src and dst are equal — move is a no-op")
        self._to_move.append((src_relpath, dst_relpath))

    def delete(self, relpath: str, *, to_trash: bool = True) -> None:
        """Queue a vault file delete. Applied during promote AFTER staged writes.

        With `to_trash=True` (default): file moves to
        `<vault>/.trash/deleted-<slug>-<utc-ts>/<basename>` with a
        `.reason.txt` recording the operation id/type.
        With `to_trash=False`: hard delete (used for staged-only artefacts).
        """
        if self._promoted or self._rejected:
            raise RuntimeError("StagingTransaction is finalized; cannot delete")
        if not relpath:
            raise ValueError("relpath must be non-empty")
        self._to_remove.append((relpath, to_trash))

    def _apply_moves(self) -> None:
        for src_rel, dst_rel in self._to_move:
            src = self.vault / src_rel
            dst = self.vault / dst_rel
            if not src.exists():
                raise FileNotFoundError(f"move source missing: {src_rel}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    def _apply_deletes(self) -> None:
        for rel, to_trash in self._to_remove:
            src = self.vault / rel
            if not src.exists():
                # Already gone (e.g. moved by an earlier op in same txn) — ok.
                continue
            if not to_trash:
                src.unlink()
                continue
            slug = Path(rel).stem or "page"
            ts = datetime.now(UTC).strftime("%Y-%m-%d-%H-%M-%S")
            trash_dir = (
                self.vault / TRASH_DIRNAME / f"deleted-{slug}-{ts}-{self.operation_id[:8]}"
            )
            trash_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(trash_dir / src.name))
            (trash_dir / ".reason.txt").write_text(
                f"deleted via {self.operation_type} operation {self.operation_id}",
                encoding="utf-8",
            )

    def promote_to_vault(
        self, *, tracker: OurWritesTracker | None = None
    ) -> PromoteResult:
        """Snapshot vault, then atomically move staging files into vault.

        On any failure during the move loop, restore vault from snapshot and raise
        StagingPromoteError. On snapshot creation failure, vault is untouched and
        StagingPromoteError still fires (no restore needed).

        If `tracker` is provided, every vault path that this promote touches —
        staged-file destinations, ontology move sources/destinations, and delete
        sources — is registered with the tracker for the duration of the move
        loop, so a parallel watchdog handler can suppress its own self-write
        events.
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

        # 2. Materialize the list of staged files BEFORE the move loop — pathlib
        # rglob is lazy and the tree mutates under our feet during shutil.move.
        staged_files = [p for p in self.staging_dir.rglob("*") if p.is_file()]
        target_paths = self._collect_target_paths(staged_files)
        cm = tracker.writing(target_paths) if tracker is not None else nullcontext()

        # 3. Move staged files into vault, one at a time, via shutil.move
        # (atomic rename on same filesystem; binary-safe; faster than read+write).
        # Then apply queued moves and deletes (Plan #8 ontology operations) under
        # the same try/restore umbrella.
        try:
            with cm:
                for staged in staged_files:
                    relative = staged.relative_to(self.staging_dir)
                    target = self.vault / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # shutil.move is atomic on same FS (uses os.rename) and is binary-safe.
                    # Pipeline guarantees no collisions: already-existing pages are excluded
                    # via skipped_collisions BEFORE writing to staging.
                    shutil.move(str(staged), str(target))
                self._apply_moves()
                self._apply_deletes()
        except Exception as exc:
            restore = restore_from_snapshot(self.vault, snapshot, tracker=tracker)
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

        # 4. Cleanup staging.
        shutil.rmtree(self.staging_dir, ignore_errors=True)
        self._promoted = True

        return PromoteResult(success=True, snapshot=snapshot)

    def _collect_target_paths(self, staged_files: list[Path]) -> list[Path]:
        """All vault paths the promote will touch — for OurWritesTracker registration."""
        targets: list[Path] = [
            self.vault / staged.relative_to(self.staging_dir) for staged in staged_files
        ]
        for src, dst in self._to_move:
            targets.append(self.vault / src)
            targets.append(self.vault / dst)
        for rel, _ in self._to_remove:
            targets.append(self.vault / rel)
        return targets

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
