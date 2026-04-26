from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SNAPSHOTS_DIRNAME = ".backups"
META_FILENAME = ".meta.json"

_EXCLUDED_DIRS = {".staging", ".backups", ".trash"}
_EXCLUDED_FILES = {".pipeline.lock"}


class SnapshotError(RuntimeError):
    """Raised when snapshot creation fails or target path already exists."""


class SnapshotMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str  # ISO-8601 UTC
    operation_id: str
    operation_type: str
    page_count: int = Field(ge=0)
    vault_size_bytes: int = Field(ge=0)


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    vault_intact: bool
    vault_possibly_corrupted: bool = False
    error: str | None = None
    recovery_hint: str | None = None


def _timestamp() -> str:
    """Filename-safe timestamp (year-month-day-hour-minute-second)."""
    return datetime.now(UTC).strftime("%Y-%m-%d-%H-%M-%S")


def compute_snapshot_path(
    vault: Path,
    *,
    operation_id: str,
    operation_type: str,
) -> Path:
    """Compute the snapshot directory path for the current UTC moment.

    Single source of truth for the snapshot path format.
    Used by both create_snapshot (auto-compute) and StagingTransaction
    (lock-in before promote).
    """
    ts = _timestamp()
    snap_name = f"pre-op-{ts}-{operation_type}-{operation_id}"
    return vault / SNAPSHOTS_DIRNAME / snap_name


def _ignore_internal(directory: str, names: list[str]) -> set[str]:
    return {n for n in names if n in _EXCLUDED_DIRS or n in _EXCLUDED_FILES}


def _count_pages(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for p in root.rglob("*.md") if p.is_file())


def _vault_size(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def create_snapshot_at(
    vault: Path,
    snap_path: Path,
    *,
    operation_id: str,
    operation_type: str,
) -> Path:
    """Create a snapshot at the exact path provided.

    Same exclusion rules and meta.json behavior as create_snapshot, but the
    target path is dictated by the caller (used by StagingTransaction to lock
    in a snapshot path before promote, so activity entries can reference it).
    """
    if snap_path.exists():
        raise SnapshotError(f"snapshot already exists: {snap_path}")

    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.mkdir(parents=True)

    if vault.exists():
        for item in vault.iterdir():
            if item.name in _EXCLUDED_DIRS or item.name in _EXCLUDED_FILES:
                continue
            dest = snap_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, ignore=_ignore_internal)
            else:
                shutil.copy2(item, dest)

    page_count = _count_pages(snap_path)
    size_bytes = _vault_size(snap_path)

    meta = SnapshotMeta(
        timestamp=datetime.now(UTC).isoformat(),
        operation_id=operation_id,
        operation_type=operation_type,
        page_count=page_count,
        vault_size_bytes=size_bytes,
    )
    (snap_path / META_FILENAME).write_text(
        json.dumps(meta.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    return snap_path


def create_snapshot(
    vault: Path,
    *,
    operation_id: str,
    operation_type: str,
) -> Path:
    """Create a snapshot with auto-generated UTC timestamp in the path."""
    snap_path = compute_snapshot_path(
        vault, operation_id=operation_id, operation_type=operation_type
    )
    return create_snapshot_at(
        vault, snap_path, operation_id=operation_id, operation_type=operation_type
    )


def restore_from_snapshot(vault: Path, snapshot: Path) -> RestoreResult:
    """Atomic restore via copy-first / atomic-swap.

    1. Copy snapshot (minus .meta.json) to temp dir on same filesystem.
    2. Atomic rename: vault -> wiki.old.<ts>, temp -> vault.
    3. Cleanup wiki.old (best-effort).

    On step 1 failure -> vault not touched, success=False, vault_intact=True.
    On step 2 partial failure -> vault possibly corrupted, recovery_hint returned.
    NEVER recurses inside except (per spec section 7.4 invariant).
    """
    if not snapshot.exists():
        return RestoreResult(
            success=False,
            vault_intact=True,
            error=f"snapshot not found: {snapshot}",
        )

    temp_root = vault.parent / f".mnemos-restore-{int(time.time() * 1000)}"
    try:
        shutil.copytree(
            snapshot,
            temp_root,
            ignore=lambda d, names: {n for n in names if n == META_FILENAME},
        )
    except OSError as exc:
        if temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)
        return RestoreResult(
            success=False,
            vault_intact=True,
            error=f"cannot stage restore: {exc}",
        )

    old_vault: Path | None = None
    if vault.exists():
        old_vault = vault.parent / f".mnemos-old-{int(time.time() * 1000)}"
        try:
            vault.rename(old_vault)
        except OSError as exc:
            shutil.rmtree(temp_root, ignore_errors=True)
            return RestoreResult(
                success=False,
                vault_intact=True,
                error=f"cannot rename vault to old: {exc}",
            )

    try:
        temp_root.rename(vault)
    except OSError as exc:
        # Worst case: vault is gone, temp_root still has the staged copy.
        return RestoreResult(
            success=False,
            vault_intact=False,
            vault_possibly_corrupted=True,
            error=str(exc),
            recovery_hint=(
                f"Manual recovery: pre-restore state at {old_vault}, "
                f"snapshot copy at {temp_root}. Move one of them to {vault}."
            ),
        )

    if old_vault is not None:
        shutil.rmtree(old_vault, ignore_errors=True)

    return RestoreResult(success=True, vault_intact=False)
