from __future__ import annotations

import json
import logging
import re
import shutil
import time
from contextlib import nullcontext, suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker

SNAPSHOTS_DIRNAME = ".backups"
META_FILENAME = ".meta.json"

_EXCLUDED_DIRS = {".staging", ".backups", ".trash"}
_EXCLUDED_FILES = {
    ".pipeline.lock",
    ".jobs.db",
    ".jobs.db-wal",
    ".jobs.db-shm",
    ".jobs.db-journal",
}

logger = logging.getLogger(__name__)

SnapshotKind = Literal["pre-op", "daily", "manual"]

_PRE_OP_RE = re.compile(
    r"^pre-op-"
    r"(?P<ts>\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})-"
    r"(?P<op_type>[A-Za-z0-9_]+)-"
    r"(?P<op_id>.+)$"
)
_DAILY_RE = re.compile(r"^daily-(?P<date>\d{4}-\d{2}-\d{2})$")
_MANUAL_RE = re.compile(
    r"^manual-(?P<ts>\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})(?:-(?P<label>.+))?$"
)
_LABEL_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


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


@dataclass(frozen=True)
class ParsedSnapshot:
    """Parsed components of a snapshot directory name."""

    kind: SnapshotKind
    timestamp: datetime  # UTC
    op_id: str | None = None
    op_type: str | None = None
    label: str | None = None


class SnapshotInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: SnapshotKind
    timestamp: datetime
    op_id: str | None = None
    op_type: str | None = None
    label: str | None = None
    size_bytes: int = 0
    path: str  # relative to vault root, posix-style


@dataclass(frozen=True)
class PruneResult:
    pruned: list[str] = field(default_factory=list)
    kept: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def parse_snapshot_name(name: str) -> ParsedSnapshot | None:
    """Parse a `.backups/<name>` directory name into structured components.

    Returns None for unknown / malformed names.
    """
    if not name:
        return None

    m = _PRE_OP_RE.match(name)
    if m is not None:
        try:
            ts = datetime.strptime(m.group("ts"), "%Y-%m-%d-%H-%M-%S").replace(tzinfo=UTC)
        except ValueError:
            return None
        return ParsedSnapshot(
            kind="pre-op",
            timestamp=ts,
            op_type=m.group("op_type"),
            op_id=m.group("op_id"),
        )

    m = _DAILY_RE.match(name)
    if m is not None:
        try:
            d = datetime.strptime(m.group("date"), "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return None
        return ParsedSnapshot(kind="daily", timestamp=d)

    m = _MANUAL_RE.match(name)
    if m is not None:
        try:
            ts = datetime.strptime(m.group("ts"), "%Y-%m-%d-%H-%M-%S").replace(tzinfo=UTC)
        except ValueError:
            return None
        return ParsedSnapshot(
            kind="manual",
            timestamp=ts,
            label=m.group("label"),
        )

    return None


def _sanitize_label(label: str) -> str:
    """Replace anything outside [A-Za-z0-9._-] with `-`, collapse repeats, strip."""
    cleaned = _LABEL_SANITIZE_RE.sub("-", label).strip("-")
    cleaned = re.sub(r"-+", "-", cleaned)
    return cleaned


def compute_daily_snapshot_path(vault: Path, today: date) -> Path:
    """Return <vault>/.backups/daily-<YYYY-MM-DD>/ — deterministic per-day path."""
    return vault / SNAPSHOTS_DIRNAME / f"daily-{today.isoformat()}"


def compute_manual_snapshot_path(
    vault: Path,
    *,
    label: str | None,
    now: datetime,
) -> Path:
    """Return <vault>/.backups/manual-<utc-ts>[-<sanitized-label>]/."""
    ts = now.astimezone(UTC).strftime("%Y-%m-%d-%H-%M-%S")
    if label is None:
        return vault / SNAPSHOTS_DIRNAME / f"manual-{ts}"
    sanitized = _sanitize_label(label)
    if not sanitized:
        raise ValueError(f"manual snapshot label is empty after sanitization: {label!r}")
    return vault / SNAPSHOTS_DIRNAME / f"manual-{ts}-{sanitized}"


def create_daily_snapshot(vault: Path, today: date) -> Path:
    """Create daily snapshot if not exists; return path. Idempotent.

    Operation type recorded in meta.json is `daily`.
    """
    snap_path = compute_daily_snapshot_path(vault, today)
    if snap_path.exists():
        return snap_path
    return create_snapshot_at(
        vault, snap_path, operation_id=today.isoformat(), operation_type="daily"
    )


def create_manual_snapshot(vault: Path, *, label: str | None = None) -> Path:
    """Create a manual snapshot under unique timestamp, op_type='manual'."""
    snap_path = compute_manual_snapshot_path(vault, label=label, now=datetime.now(UTC))
    op_id = label if label else "manual"
    return create_snapshot_at(
        vault, snap_path, operation_id=op_id, operation_type="manual"
    )


def _snapshot_size(snap_dir: Path) -> int:
    total = 0
    if not snap_dir.exists():
        return 0
    for p in snap_dir.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def list_snapshots(vault: Path) -> list[SnapshotInfo]:
    """List snapshots in <vault>/.backups/, sorted newest-first.

    Skips directories that don't match known prefixes (logs warning).
    Best-effort size computation; errors → size_bytes=0.
    """
    backups_root = vault / SNAPSHOTS_DIRNAME
    if not backups_root.is_dir():
        return []

    items: list[SnapshotInfo] = []
    for entry in backups_root.iterdir():
        if not entry.is_dir():
            continue
        parsed = parse_snapshot_name(entry.name)
        if parsed is None:
            logger.warning("skipping unrecognized backup entry: %s", entry.name)
            continue
        items.append(
            SnapshotInfo(
                name=entry.name,
                kind=parsed.kind,
                timestamp=parsed.timestamp,
                op_id=parsed.op_id,
                op_type=parsed.op_type,
                label=parsed.label,
                size_bytes=_snapshot_size(entry),
                path=f".backups/{entry.name}",
            )
        )

    items.sort(key=lambda s: s.timestamp, reverse=True)
    return items


def _iter_snapshot_files(root: Path) -> "list[tuple[str, Path]]":
    """Walk vault/snapshot, yield (posix-relpath, abs-path) for content files.

    Skips ``.backups/``, ``.staging/``, ``.trash/`` subtrees and meta/lock files.
    """
    out: list[tuple[str, Path]] = []
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        parts = rel.parts
        if parts and parts[0] in _EXCLUDED_DIRS:
            continue
        if p.name in _EXCLUDED_FILES or p.name == META_FILENAME:
            continue
        out.append((rel.as_posix(), p))
    return out


def _file_sha(path: Path) -> str | None:
    import hashlib

    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


class RestorePreview(BaseModel):
    """Diff between a snapshot and the current vault — what restore would do."""

    model_config = ConfigDict(extra="forbid")

    snapshot_name: str
    snapshot_timestamp: datetime
    snapshot_kind: SnapshotKind
    snapshot_file_count: int
    vault_file_count: int
    will_create: list[str]  # in snapshot, missing from vault — restore writes them
    will_delete: list[str]  # in vault, missing from snapshot — restore removes them
    will_overwrite: list[str]  # in both, sha differs — restore overwrites
    unchanged_count: int
    sample_limit: int  # cap on each will_* list
    truncated: bool  # True if any will_* list was truncated


def compute_restore_preview(
    vault: Path,
    snapshot_name: str,
    *,
    sample_limit: int = 20,
) -> RestorePreview:
    """Diff snapshot vs current vault to preview a restore.

    Walks both trees, classifies every file by sha. Cheap when most files
    match by size (sha is only computed when sizes are equal).
    Lists are sorted alphabetically; truncated at ``sample_limit`` entries
    each — ``truncated=True`` signals that more changes exist.
    """
    parsed = parse_snapshot_name(snapshot_name)
    if parsed is None:
        raise ValueError(f"not a snapshot name: {snapshot_name!r}")
    snap_dir = vault / SNAPSHOTS_DIRNAME / snapshot_name
    if not snap_dir.is_dir():
        raise FileNotFoundError(f"snapshot not found: {snapshot_name}")

    snap_files = {rel: p for rel, p in _iter_snapshot_files(snap_dir)}
    vault_files = {rel: p for rel, p in _iter_snapshot_files(vault)}

    create: list[str] = []
    delete: list[str] = []
    overwrite: list[str] = []
    unchanged = 0

    for rel, snap_p in snap_files.items():
        v_p = vault_files.get(rel)
        if v_p is None:
            create.append(rel)
            continue
        try:
            same_size = snap_p.stat().st_size == v_p.stat().st_size
        except OSError:
            same_size = False
        if same_size and _file_sha(snap_p) == _file_sha(v_p):
            unchanged += 1
        else:
            overwrite.append(rel)

    for rel in vault_files:
        if rel not in snap_files:
            delete.append(rel)

    create.sort()
    delete.sort()
    overwrite.sort()

    truncated = (
        len(create) > sample_limit
        or len(delete) > sample_limit
        or len(overwrite) > sample_limit
    )

    return RestorePreview(
        snapshot_name=snapshot_name,
        snapshot_timestamp=parsed.timestamp,
        snapshot_kind=parsed.kind,
        snapshot_file_count=len(snap_files),
        vault_file_count=len(vault_files),
        will_create=create[:sample_limit],
        will_delete=delete[:sample_limit],
        will_overwrite=overwrite[:sample_limit],
        unchanged_count=unchanged,
        sample_limit=sample_limit,
        truncated=truncated,
    )


def delete_snapshot(vault: Path, name: str) -> None:
    """Delete a snapshot directory by name. Path-traversal-safe.

    Rejects:
    - names containing path separators or `..`
    - absolute paths
    - names that don't match a known snapshot prefix
    """
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"snapshot name contains path separators: {name!r}")
    if Path(name).is_absolute():
        raise ValueError(f"snapshot name must be relative: {name!r}")
    if parse_snapshot_name(name) is None:
        raise ValueError(f"not a snapshot name: {name!r}")

    backups_root = (vault / SNAPSHOTS_DIRNAME).resolve()
    target = (vault / SNAPSHOTS_DIRNAME / name).resolve()

    # Double-check resolved path is inside .backups/
    if backups_root not in target.parents and target != backups_root:
        raise ValueError(f"snapshot path escapes .backups/: {name!r}")
    if target == backups_root:
        raise ValueError("cannot delete .backups/ itself")

    if not target.exists():
        raise FileNotFoundError(f"snapshot not found: {name}")

    shutil.rmtree(target)


def prune_old_backups(
    vault: Path,
    retention_days: int,
    today: date,
) -> PruneResult:
    """Delete snapshots older than (today - retention_days). Junk dirs untouched.

    Returns (pruned: list[str], kept: int, errors: list[(name, message)]).
    """
    backups_root = vault / SNAPSHOTS_DIRNAME
    if not backups_root.is_dir():
        return PruneResult()

    cutoff = today - timedelta(days=retention_days)
    pruned: list[str] = []
    errors: list[tuple[str, str]] = []
    kept = 0

    for entry in backups_root.iterdir():
        if not entry.is_dir():
            continue
        parsed = parse_snapshot_name(entry.name)
        if parsed is None:
            # Junk: not ours, leave it alone
            continue
        if parsed.timestamp.date() < cutoff:
            try:
                shutil.rmtree(entry)
                pruned.append(entry.name)
            except OSError as exc:
                errors.append((entry.name, str(exc)))
        else:
            kept += 1

    return PruneResult(pruned=pruned, kept=kept, errors=errors)


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


def restore_from_snapshot(
    vault: Path,
    snapshot: Path,
    *,
    tracker: OurWritesTracker | None = None,
) -> RestoreResult:
    """Atomic restore via copy-first / atomic-swap.

    1. Copy snapshot (minus .meta.json) to temp dir on same filesystem.
    2. Atomic rename: vault -> wiki.old.<ts>, temp -> vault.
    3. Cleanup wiki.old (best-effort).

    On step 1 failure -> vault not touched, success=False, vault_intact=True.
    On step 2 partial failure -> vault possibly corrupted, recovery_hint returned.
    NEVER recurses inside except (per spec section 7.4 invariant).

    If `tracker` is provided, the restore runs inside `tracker.paused()` so a
    parallel watchdog handler ignores the dozens of CREATE events the swap
    produces (Plan #9).
    """
    if not snapshot.exists():
        return RestoreResult(
            success=False,
            vault_intact=True,
            error=f"snapshot not found: {snapshot}",
        )

    pause_cm = tracker.paused() if tracker is not None else nullcontext()
    with pause_cm:
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

        # Preserve current vault's internal dirs into temp_root before swap.
        # The snapshot deliberately excludes .backups/.trash/.staging so it doesn't
        # recurse on itself. But after the atomic swap, those internal dirs would
        # disappear — losing all earlier snapshots, breaking chain undo. Copy them
        # over before the swap so they survive.
        if vault.exists():
            for preserved in (".backups", ".trash", ".staging"):
                src = vault / preserved
                if src.is_dir():
                    dst = temp_root / preserved
                    if dst.exists():
                        # Snapshot included this dir somehow (shouldn't happen) — replace
                        shutil.rmtree(dst)
                    try:
                        shutil.copytree(src, dst)
                    except OSError as exc:
                        # Couldn't preserve internal dir — abort restore.
                        # Vault is still intact since we haven't swapped yet.
                        shutil.rmtree(temp_root, ignore_errors=True)
                        return RestoreResult(
                            success=False,
                            vault_intact=True,
                            error=f"cannot preserve internal dir {preserved}: {exc}",
                        )

            # Preserve jobs DB and its WAL/SHM/journal companions across the swap.
            # The snapshot excludes them (Plan #11), so without this they would be
            # wiped on every restore — silently losing permanent dead_letter rows
            # that spec §8.9 promises will never auto-clean.
            for preserved_file in (
                ".jobs.db",
                ".jobs.db-wal",
                ".jobs.db-shm",
                ".jobs.db-journal",
            ):
                src = vault / preserved_file
                if src.is_file():
                    dst = temp_root / preserved_file
                    if dst.exists():
                        # Snapshot included this file somehow (shouldn't happen) — replace
                        with suppress(OSError):
                            dst.unlink()
                    try:
                        shutil.copy2(src, dst)
                    except OSError as exc:
                        # Couldn't preserve internal file — abort restore.
                        # Vault is still intact since we haven't swapped yet.
                        shutil.rmtree(temp_root, ignore_errors=True)
                        return RestoreResult(
                            success=False,
                            vault_intact=True,
                            error=f"cannot preserve internal file {preserved_file}: {exc}",
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
