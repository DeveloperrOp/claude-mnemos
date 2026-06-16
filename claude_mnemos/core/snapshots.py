from __future__ import annotations

import hashlib
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
TRASH_PREFIX = "_trash-"  # delete_snapshot() renames here (soft-delete)

# .chunk-cache holds transient per-chunk extraction payloads for rate-limit
# resume — it must never ride into a backup.
_EXCLUDED_DIRS = {".staging", ".backups", ".trash", ".chunk-cache"}
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
_MANUAL_RE = re.compile(r"^manual-(?P<ts>\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})(?:-(?P<label>.+))?$")
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
    return create_snapshot_at(vault, snap_path, operation_id=op_id, operation_type="manual")


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
        # Skip soft-deleted snapshots silently (renamed by delete_snapshot()
        # to `_trash-<original>`). They surface separately via list_trash().
        if entry.name.startswith(TRASH_PREFIX):
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

    # v0.0.37: soft-delete — rename with `_trash-` prefix instead of
    # rmtree. list_snapshots() skips _trash-* entries; list_trash() surfaces
    # them so the user can restore or permanently purge. prune_old_backups()
    # also reclaims trashed entries once they age past the retention window.
    trash_target = target.parent / f"{TRASH_PREFIX}{target.name}"
    # If a previous soft-delete already renamed something to this path
    # (e.g. multiple deletes of the same snapshot would be impossible
    # because of the prefix, but tests can stage this scenario), fall
    # back to a hard remove of the orphan first.
    if trash_target.exists():
        shutil.rmtree(trash_target)
    target.rename(trash_target)


def _resolve_trash_target(vault: Path, name: str) -> Path:
    """Validate *name* (an original snapshot name) and return the absolute
    path to its `.backups/_trash-<name>` directory. Path-traversal-safe.

    Raises ValueError for malformed/escaping names (same rules as
    delete_snapshot, applied to the un-prefixed original name).
    """
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"snapshot name contains path separators: {name!r}")
    if Path(name).is_absolute():
        raise ValueError(f"snapshot name must be relative: {name!r}")
    if parse_snapshot_name(name) is None:
        raise ValueError(f"not a snapshot name: {name!r}")

    backups_root = (vault / SNAPSHOTS_DIRNAME).resolve()
    target = (vault / SNAPSHOTS_DIRNAME / f"{TRASH_PREFIX}{name}").resolve()
    if backups_root not in target.parents:
        raise ValueError(f"trash path escapes .backups/: {name!r}")
    return target


def list_trash(vault: Path) -> list[SnapshotInfo]:
    """List soft-deleted snapshots (the `_trash-<original>` dirs), newest-first.

    Each entry's ``name`` is the *original* (un-prefixed) snapshot name so the
    restore/purge endpoints can address it the same way as a live snapshot;
    ``path`` points at the actual on-disk trash directory.
    """
    backups_root = vault / SNAPSHOTS_DIRNAME
    if not backups_root.is_dir():
        return []

    items: list[SnapshotInfo] = []
    for entry in backups_root.iterdir():
        if not entry.is_dir() or not entry.name.startswith(TRASH_PREFIX):
            continue
        original = entry.name[len(TRASH_PREFIX) :]
        parsed = parse_snapshot_name(original)
        if parsed is None:
            # Trash of something that no longer parses — leave it (only
            # purge_trash/prune can remove it), don't crash the listing.
            logger.warning("skipping unparseable trash entry: %s", entry.name)
            continue
        items.append(
            SnapshotInfo(
                name=original,
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


def restore_from_trash(vault: Path, name: str) -> None:
    """Move a soft-deleted snapshot back into the live set.

    Renames `.backups/_trash-<name>` → `.backups/<name>`. Path-traversal-safe.

    Raises:
        ValueError: malformed name.
        FileNotFoundError: no such trash entry.
        FileExistsError: a live snapshot of the same name already exists.
    """
    trash_target = _resolve_trash_target(vault, name)
    if not trash_target.exists():
        raise FileNotFoundError(f"trashed snapshot not found: {name}")
    live_target = vault / SNAPSHOTS_DIRNAME / name
    if live_target.exists():
        raise FileExistsError(
            f"a snapshot named {name!r} already exists; cannot restore from trash"
        )
    trash_target.rename(live_target)


def purge_trash(vault: Path, name: str) -> None:
    """Permanently delete a soft-deleted snapshot (real rmtree). Irreversible.

    Raises:
        ValueError: malformed name.
        FileNotFoundError: no such trash entry.
    """
    trash_target = _resolve_trash_target(vault, name)
    if not trash_target.exists():
        raise FileNotFoundError(f"trashed snapshot not found: {name}")
    shutil.rmtree(trash_target)


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
        name = entry.name
        # Soft-deleted snapshots also age out: parse the original name behind
        # the `_trash-` prefix so the trash doesn't accumulate forever (the
        # only other way to reclaim it is a manual purge from the UI).
        is_trash = name.startswith(TRASH_PREFIX)
        parse_name = name[len(TRASH_PREFIX) :] if is_trash else name
        parsed = parse_snapshot_name(parse_name)
        if parsed is None:
            # Junk: not ours, leave it alone
            continue
        if parsed.timestamp.date() < cutoff:
            try:
                shutil.rmtree(entry)
                pruned.append(name)
            except OSError as exc:
                errors.append((name, str(exc)))
        elif not is_trash:
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
        # Idempotent reuse: if the existing snapshot was created for the
        # exact same (operation_id, operation_type) — i.e. this is a retry
        # of the same logical operation hitting the same-second timestamp —
        # treat it as the snapshot we'd be creating anyway and return it.
        # The previous behaviour (always raise SnapshotError) dead-lettered
        # legitimate retries when the worker re-ran a failed ingest within
        # one second of the first attempt.
        meta_file = snap_path / META_FILENAME
        if meta_file.is_file():
            try:
                existing_meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if (
                    existing_meta.get("operation_id") == operation_id
                    and existing_meta.get("operation_type") == operation_type
                ):
                    return snap_path
            except (json.JSONDecodeError, OSError):
                pass  # corrupt meta — fall through to raise below
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


_ASIDE_PREFIX = "restore-aside-"
_ASIDE_SWEEP_AGE_S = 24 * 3600.0


def _sweep_stale_aside_dirs(vault: Path) -> None:
    """Best-effort removal of restore-aside-* debris older than 24h.

    A crashed fallback strands a full vault-content copy under .staging/ —
    without a sweep it is permanent disk bloat AND gets copytree'd into
    temp_root by the preserve-internal-dirs block on every later restore.
    The age guard keeps a fresh crash's debris available for manual recovery.
    """
    staging = vault / ".staging"
    if not staging.is_dir():
        return
    now = time.time()
    for entry in staging.iterdir():
        if not entry.name.startswith(_ASIDE_PREFIX):
            continue
        try:
            ts_ms = int(entry.name[len(_ASIDE_PREFIX) :])
        except ValueError:
            continue
        if now - ts_ms / 1000.0 > _ASIDE_SWEEP_AGE_S:
            shutil.rmtree(entry, ignore_errors=True)


def _restore_content_swap(vault: Path, temp_root: Path) -> RestoreResult:
    """Per-entry fallback for when the whole-vault rename is blocked.

    On Windows an open handle on ANY file under the vault blocks renaming the
    vault directory itself. Inside the daemon that is the normal state —
    ``<vault>/.jobs.db`` is always open, and undo / the staging rollback run
    inside the worker where the store cannot be closed around the swap. So:
    swap every non-excluded TOP-LEVEL entry instead (live entries move aside
    into ``.staging/restore-aside-<ts>/``, staged entries move in, both plain
    same-filesystem renames). The vault root and the excluded entries
    (.jobs.db family, .staging/.backups/.trash) are never renamed, so open
    daemon handles — and the watchdog observer — survive. (The pipeline lock
    file lives OUTSIDE the vault, ``<parent>/.{name}.pipeline.lock`` — it is
    unaffected by either swap strategy.)

    Not crash-atomic like the rename swap (a hard crash mid-loop can leave a
    mixed state), but the in-daemon alternative on Windows is failing
    outright. ANY mid-swap abort — including KeyboardInterrupt in the CLI
    undo path — rolls the moves back before propagating; in every failure
    branch nothing is deleted, so vault∪aside = the full pre-restore set and
    vault∪temp = the full snapshot set, and reassembly is always possible.
    """
    skip = _EXCLUDED_DIRS | _EXCLUDED_FILES | {META_FILENAME}
    _sweep_stale_aside_dirs(vault)
    aside_root = vault / ".staging" / f"{_ASIDE_PREFIX}{int(time.time() * 1000)}"

    try:
        live_entries = [p for p in vault.iterdir() if p.name not in skip]
        staged_entries = [p for p in temp_root.iterdir() if p.name not in skip]
        aside_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        return RestoreResult(
            success=False,
            vault_intact=True,
            error=f"content-swap setup failed: {exc}",
        )

    # Forensic breadcrumb BEFORE any move: a hard crash mid-swap leaves a
    # gutted-looking vault — this line is the only pointer to the pieces.
    logger.warning(
        "restore: whole-vault rename blocked, using content-swap fallback; "
        "pre-restore entries -> %s, snapshot copy at %s",
        aside_root,
        temp_root,
    )

    def _rollback_aside(moved: list[tuple[Path, Path]]) -> bool:
        ok = True
        for orig, target in reversed(moved):
            try:
                target.rename(orig)
            except OSError:
                ok = False
        return ok

    # Phase A: move live entries aside.
    moved_aside: list[tuple[Path, Path]] = []
    try:
        for entry in live_entries:
            target = aside_root / entry.name
            entry.rename(target)
            moved_aside.append((entry, target))
    except BaseException as exc:
        rolled_back = _rollback_aside(moved_aside)
        if not isinstance(exc, OSError):
            logger.exception(
                "restore: content-swap aborted mid-Phase-A (%s); rollback %s",
                type(exc).__name__,
                "complete" if rolled_back else f"INCOMPLETE — see {aside_root}",
            )
            raise
        shutil.rmtree(temp_root, ignore_errors=True)
        if not rolled_back:
            return RestoreResult(
                success=False,
                vault_intact=False,
                vault_possibly_corrupted=True,
                error=f"content-swap aside failed and rollback incomplete: {exc}",
                recovery_hint=(
                    f"Entries stranded in {aside_root} — move them back into "
                    f"{vault}. The source snapshot in .backups/ is untouched; "
                    f"re-running the restore is safe."
                ),
            )
        shutil.rmtree(aside_root, ignore_errors=True)
        return RestoreResult(
            success=False,
            vault_intact=True,
            error=f"cannot swap vault contents (open file inside?): {exc}",
        )

    def _rollback_move_in(moved: list[Path]) -> bool:
        ok = True
        for target in reversed(moved):
            try:
                target.rename(temp_root / target.name)
            except OSError:
                ok = False
        return ok

    # Phase B: move staged entries in.
    moved_in: list[Path] = []
    try:
        for entry in staged_entries:
            target = vault / entry.name
            entry.rename(target)
            moved_in.append(target)
    except BaseException as exc:
        # Per-item best-effort, both directions independently.
        rolled_in = _rollback_move_in(moved_in)
        rolled_aside = _rollback_aside(moved_aside)
        if not isinstance(exc, OSError):
            logger.exception(
                "restore: content-swap aborted mid-Phase-B (%s); rollback %s",
                type(exc).__name__,
                "complete"
                if (rolled_in and rolled_aside)
                else f"INCOMPLETE — pre-restore at {aside_root}, snapshot at {temp_root}",
            )
            raise
        if not (rolled_in and rolled_aside):
            return RestoreResult(
                success=False,
                vault_intact=False,
                vault_possibly_corrupted=True,
                error=f"content-swap move-in failed and rollback incomplete: {exc}",
                recovery_hint=(
                    f"Invariants: {vault} + {aside_root} = the full pre-restore "
                    f"set; {vault} + {temp_root} = the full snapshot set; "
                    f"nothing was deleted. The source snapshot in .backups/ is "
                    f"untouched and re-running the restore is safe."
                ),
            )
        shutil.rmtree(temp_root, ignore_errors=True)
        shutil.rmtree(aside_root, ignore_errors=True)
        return RestoreResult(
            success=False,
            vault_intact=True,
            error=f"cannot move restored contents in: {exc}",
        )

    # Phase C: cleanup. The live excluded entries never moved, so temp_root's
    # preserved copies of them are now redundant — drop everything.
    shutil.rmtree(aside_root, ignore_errors=True)
    shutil.rmtree(temp_root, ignore_errors=True)
    if aside_root.exists():
        logger.warning(
            "restore: content-swap succeeded but aside cleanup left debris "
            "at %s (will be swept after 24h)",
            aside_root,
        )
    return RestoreResult(success=True, vault_intact=False)


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
                # Windows refuses to rename a directory while ANY handle is
                # open on it or its contents. Inside the daemon that is the
                # normal state: <vault>/.jobs.db is open (and undo / the
                # staging rollback run inside the worker, where the store
                # cannot be closed around the swap). Fall back to a per-entry
                # content swap that never renames the vault root — the open
                # excluded files (.jobs.db family) stay untouched in place.
                logger.warning(
                    "restore: vault rename blocked (%s) — falling back to content swap",
                    exc,
                )
                return _restore_content_swap(vault, temp_root)

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


# ---------------------------------------------------------------------------
# Restore preview
# ---------------------------------------------------------------------------


class RestorePreview(BaseModel):
    snapshot_name: str
    snapshot_timestamp: str
    snapshot_kind: str
    snapshot_file_count: int
    vault_file_count: int
    will_create: list[str]
    will_delete: list[str]
    will_overwrite: list[str]
    unchanged_count: int
    sample_limit: int
    truncated: bool


def _file_sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _iter_vault_files(vault: Path) -> list[tuple[str, Path]]:
    """Return (vault-relative-posix, abs_path) for every non-excluded file."""
    results: list[tuple[str, Path]] = []
    for p in vault.rglob("*"):
        if not p.is_file():
            continue
        parts = p.relative_to(vault).parts
        if parts[0] in _EXCLUDED_DIRS or parts[0] in _EXCLUDED_FILES:
            continue
        results.append((p.relative_to(vault).as_posix(), p))
    return results


def compute_restore_preview(
    vault: Path,
    snapshot_name: str,
    *,
    sample_limit: int = 20,
) -> RestorePreview:
    snap_path = vault / SNAPSHOTS_DIRNAME / snapshot_name
    if not snap_path.is_dir():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_name}")

    # Walk snapshot files (exclude .meta.json)
    snap_files: dict[str, Path] = {}
    for p in snap_path.rglob("*"):
        if not p.is_file():
            continue
        if p.name == META_FILENAME:
            continue
        snap_files[p.relative_to(snap_path).as_posix()] = p

    # Walk vault files
    vault_files: dict[str, Path] = dict(_iter_vault_files(vault))

    snap_keys = set(snap_files.keys())
    vault_keys = set(vault_files.keys())

    will_create_all = sorted(snap_keys - vault_keys)
    will_delete_all = sorted(vault_keys - snap_keys)

    will_overwrite_all: list[str] = []
    unchanged_count = 0
    for key in sorted(snap_keys & vault_keys):
        snap_sha = _file_sha256(snap_files[key])
        vault_sha = _file_sha256(vault_files[key])
        if snap_sha != vault_sha:
            will_overwrite_all.append(key)
        else:
            unchanged_count += 1

    total_changes = len(will_create_all) + len(will_delete_all) + len(will_overwrite_all)
    truncated = total_changes > sample_limit

    will_create = will_create_all[:sample_limit]
    remaining = sample_limit - len(will_create)
    will_overwrite = will_overwrite_all[: max(0, remaining)]
    remaining -= len(will_overwrite)
    will_delete = will_delete_all[: max(0, remaining)]

    parsed = parse_snapshot_name(snapshot_name)
    snap_kind = parsed.kind if parsed is not None else "manual"
    snap_ts = parsed.timestamp.isoformat() if parsed is not None else snapshot_name

    return RestorePreview(
        snapshot_name=snapshot_name,
        snapshot_timestamp=snap_ts,
        snapshot_kind=snap_kind,
        snapshot_file_count=len(snap_keys),
        vault_file_count=len(vault_keys),
        will_create=will_create,
        will_delete=will_delete,
        will_overwrite=will_overwrite,
        unchanged_count=unchanged_count,
        sample_limit=sample_limit,
        truncated=truncated,
    )
