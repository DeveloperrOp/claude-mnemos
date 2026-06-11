"""7 semantic health detectors for the persistent ``AlertsStore``.

Each detector returns ``StoredAlert | None``. ``run_all_checks`` runs every
detector inside its own try/except so one bad detector cannot break the cron.

Detectors (final list):
    1. auto_dump_overdue       — last auto_dump_global cron run > 2h ago     (warning)
    2. ingest_failure_streak   — last 3 ingest jobs (in last 24h) all dead   (critical)
    3. runaway_job             — any job running, started_at > 30 min ago    (warning)
    4. hook_silence            — recent jsonl in ~/.claude/projects AND no
                                 successful ingest job in last 6h            (warning)
    5. disk_low                — vault disk free < 5%                         (critical)
    6. project_map_broken      — project-map.json failed to load              (critical)
    7. daemon_uptime_warning   — daemon uptime < 60s (auto-dismisses ~10 min) (info)
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_mnemos.core.clock import utcnow
from claude_mnemos.state.alerts_store import StoredAlert

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from claude_mnemos.daemon.process import MnemosDaemon
    from claude_mnemos.daemon.vault_runtime import VaultRuntime

logger = logging.getLogger(__name__)


def _make(
    *,
    id_: str,
    detector: str,
    severity: str,
    message: str,
    i18n_key: str,
    i18n_params: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> StoredAlert:
    n = now if now is not None else utcnow()
    return StoredAlert(
        id=id_,
        detector=detector,
        severity=severity,  # type: ignore[arg-type]
        message=message,
        i18n_key=i18n_key,
        i18n_params=i18n_params or {},
        context=context or {},
        first_seen=n,
        last_seen=n,
    )


# ─── 1. auto_dump_overdue ────────────────────────────────────────


def check_auto_dump_overdue(
    scheduler: AsyncIOScheduler,
    *,
    now: datetime | None = None,
) -> StoredAlert | None:
    """Warn if the ``auto_dump_global`` cron's next_run_time is in the past
    by more than 2h, OR the job is missing from the scheduler entirely.

    Cron is hourly (minute=0), so under healthy operation next_run_time is
    always ≤ 1h ahead. > 2h overdue ⇒ scheduler is wedged or job evicted.
    """
    n = now if now is not None else utcnow()
    job = scheduler.get_job("auto_dump_global")
    if job is None:
        return _make(
            id_="auto_dump_overdue",
            detector="auto_dump_overdue",
            severity="warning",
            message="Auto-dump cron job is not registered with the scheduler.",
            i18n_key="overview.health_alerts.detectors.auto_dump_overdue_missing",
            context={"job_id": "auto_dump_global"},
            now=n,
        )
    nrt = getattr(job, "next_run_time", None)
    if nrt is None:
        # Scheduler hasn't started or job is paused — not actionable.
        return None
    delta = (n - nrt).total_seconds()
    if delta > 2 * 3600:
        return _make(
            id_="auto_dump_overdue",
            detector="auto_dump_overdue",
            severity="warning",
            message=(
                f"Auto-dump is overdue by {int(delta / 60)} min "
                f"(next_run_time={nrt.isoformat()})."
            ),
            i18n_key="overview.health_alerts.detectors.auto_dump_overdue",
            i18n_params={"minutes": int(delta / 60)},
            context={"overdue_seconds": int(delta), "next_run_time": nrt.isoformat()},
            now=n,
        )
    return None


# ─── 2. ingest_failure_streak ────────────────────────────────────


def check_ingest_failure_streak(
    runtimes: dict[str, VaultRuntime],
    *,
    now: datetime | None = None,
) -> StoredAlert | None:
    """Critical when, across all vaults, the 3 most-recent ingest jobs in the
    last 24h are all in a failure terminal state (``failed`` / ``dead_letter``).

    Uses ``JobStore.list_by_status(None)`` to walk recent jobs; we sort in
    Python by ``finished_at`` descending so cross-vault ordering is correct.
    """
    n = now if now is not None else utcnow()
    cutoff = n - timedelta(hours=24)
    recent: list[tuple[datetime, str, str]] = []  # (finished_at, status, project)
    for project_name, rt in runtimes.items():
        store = getattr(rt, "job_store", None)
        if store is None:
            continue
        try:
            # 100 is enough to cover 3-of-most-recent in 24h for any sane vault.
            jobs = store.list_by_status(None, limit=100)
        except Exception:
            logger.exception("ingest_failure_streak: list_by_status failed for %s", project_name)
            continue
        for j in jobs:
            if j.kind != "ingest":
                continue
            finished = getattr(j, "finished_at", None)
            if finished is None or finished < cutoff:
                continue
            recent.append((finished, j.status, project_name))
    recent.sort(key=lambda x: x[0], reverse=True)
    last_three = recent[:3]
    if len(last_three) < 3:
        return None
    bad = {"failed", "dead_letter"}
    if all(status in bad for _, status, _ in last_three):
        return _make(
            id_="ingest_failure_streak",
            detector="ingest_failure_streak",
            severity="critical",
            message="Last 3 ingest jobs in the past 24h all failed.",
            i18n_key="overview.health_alerts.detectors.ingest_failure_streak",
            i18n_params={"count": len(last_three)},
            context={
                "projects": [p for _, _, p in last_three],
                "statuses": [s for _, s, _ in last_three],
            },
            now=n,
        )
    return None


# ─── 3. runaway_jobs ─────────────────────────────────────────────


def check_runaway_jobs(
    runtimes: dict[str, VaultRuntime],
    *,
    now: datetime | None = None,
) -> StoredAlert | None:
    """Warn when any running ingest job started more than 30 minutes ago."""
    n = now if now is not None else utcnow()
    cutoff = n - timedelta(minutes=30)
    runaways: list[dict[str, Any]] = []
    for project_name, rt in runtimes.items():
        store = getattr(rt, "job_store", None)
        if store is None:
            continue
        try:
            running = store.list_by_status("running", limit=100)
        except Exception:
            logger.exception("runaway_jobs: list_by_status failed for %s", project_name)
            continue
        for j in running:
            started = getattr(j, "started_at", None)
            if started is None:
                continue
            if started < cutoff:
                runaways.append(
                    {
                        "id": j.id,
                        "project": project_name,
                        "started_at": started.isoformat(),
                        "running_for_seconds": int((n - started).total_seconds()),
                    }
                )
    if not runaways:
        return None
    longest = max(runaways, key=lambda r: r["running_for_seconds"])
    return _make(
        id_="runaway_job",
        detector="runaway_job",
        severity="warning",
        message=(
            f"{len(runaways)} ingest job(s) running for more than 30 min "
            f"(longest: {max(r['running_for_seconds'] for r in runaways) // 60} min)."
        ),
        i18n_key="overview.health_alerts.detectors.runaway_job",
        i18n_params={
            "job_id": str(longest["id"]),
            "minutes": int(longest["running_for_seconds"] // 60),
        },
        context={"jobs": runaways},
        now=n,
    )


# ─── 4. hook_silence ─────────────────────────────────────────────


def _claude_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def check_hook_silence(
    runtimes: dict[str, VaultRuntime],
    *,
    now: datetime | None = None,
    projects_dir: Path | None = None,
) -> StoredAlert | None:
    """Warn when there are recent JSONL writes in ``~/.claude/projects/`` (last
    6h) but no successful **ingest** jobs in the same window.

    Heuristic interpretation: a successful SessionEnd/PreCompact hook always
    enqueues an ingest job. So a recent JSONL without any successful
    ``kind == "ingest"`` activity in 6h is a strong signal the hook isn't
    firing (most common cause: hooks not installed or installed but pointing
    at the wrong project). Other successful job kinds (e.g. ``lint``) are
    irrelevant — they don't prove hooks are firing.

    Heuristic limit: this assumes the operator runs at least one Claude Code
    session per 6h while working. A 6h+ idle gap with hooks healthy is
    indistinguishable from broken hooks; users who don't use CC every day
    can dismiss the alert.

    Edge case: if no JSONL files exist at all, return None (user may simply
    not be using Claude Code right now).
    """
    n = now if now is not None else utcnow()
    pd = projects_dir if projects_dir is not None else _claude_projects_dir()
    if not pd.exists() or not pd.is_dir():
        return None

    cutoff_ts = (n - timedelta(hours=6)).timestamp()
    recent_jsonls: list[Path] = []
    try:
        for sub in pd.iterdir():
            if not sub.is_dir():
                continue
            try:
                for f in sub.iterdir():
                    if f.suffix == ".jsonl" and f.is_file():
                        try:
                            if f.stat().st_mtime > cutoff_ts:
                                recent_jsonls.append(f)
                        except OSError:
                            continue
            except OSError:
                continue
    except OSError:
        return None
    if not recent_jsonls:
        return None

    # Look for any ingest job that succeeded in the last 6h. Limit raised to
    # 200 (was 20) so a busy queue can't bury the legitimate older success
    # behind 20+ recent non-ingest jobs. Filter explicitly by
    # kind == "ingest": a successful lint job does NOT prove hooks fire.
    cutoff = n - timedelta(hours=6)
    for rt in runtimes.values():
        store = getattr(rt, "job_store", None)
        if store is None:
            continue
        try:
            succeeded = store.list_by_status("succeeded", limit=200)
        except Exception:
            continue
        for j in succeeded:
            if j.kind != "ingest":
                continue
            finished = getattr(j, "finished_at", None)
            if finished is not None and finished >= cutoff:
                return None

    return _make(
        id_="hook_silence",
        detector="hook_silence",
        severity="warning",
        message=(
            f"{len(recent_jsonls)} recent Claude Code session(s) detected, but no "
            f"ingest job has succeeded in the last 6h. Check that hooks are installed."
        ),
        i18n_key="overview.health_alerts.detectors.hook_silence",
        i18n_params={"count": len(recent_jsonls)},
        context={"recent_jsonl_count": len(recent_jsonls)},
        now=n,
    )


# ─── 5. disk_low ─────────────────────────────────────────────────


async def check_disk_low(
    runtimes: dict[str, VaultRuntime],
    *,
    now: datetime | None = None,
    threshold: float = 0.05,
) -> StoredAlert | None:
    """Critical when any vault's filesystem has less than ``threshold`` (default 5%) free.

    ``shutil.disk_usage`` performs a blocking ``statvfs``/``GetDiskFreeSpaceExW``
    syscall that can stall on a slow/unresponsive volume; offload it to a
    thread so the event loop keeps serving requests during the cron tick.
    """
    n = now if now is not None else utcnow()
    low: list[dict[str, Any]] = []
    for project_name, rt in runtimes.items():
        vault_root = getattr(rt, "vault_root", None)
        if vault_root is None or not Path(vault_root).exists():
            continue
        try:
            usage = await asyncio.to_thread(shutil.disk_usage, str(vault_root))
        except OSError:
            continue
        if usage.total <= 0:
            continue
        free_ratio = usage.free / usage.total
        if free_ratio < threshold:
            low.append(
                {
                    "project": project_name,
                    "vault_root": str(vault_root),
                    "free_ratio": round(free_ratio, 4),
                    "free_bytes": int(usage.free),
                    "total_bytes": int(usage.total),
                }
            )
    if not low:
        return None
    worst = min(low, key=lambda v: v["free_ratio"])
    return _make(
        id_="disk_low",
        detector="disk_low",
        severity="critical",
        message=(
            f"{len(low)} vault filesystem(s) below {int(threshold * 100)}% free space."
        ),
        i18n_key="overview.health_alerts.detectors.disk_low",
        i18n_params={
            "vault": str(worst["project"]),
            "percent_free": int(worst["free_ratio"] * 100),
        },
        context={"vaults": low, "threshold": threshold},
        now=n,
    )


# ─── 6. project_map_broken ───────────────────────────────────────


def check_project_map_broken(*, now: datetime | None = None) -> StoredAlert | None:
    """Critical when ``project-map.json`` fails to load / parse."""
    n = now if now is not None else utcnow()
    try:
        from claude_mnemos.state.projects import ProjectStore

        ProjectStore().list_all()
    except Exception as exc:
        return _make(
            id_="project_map_broken",
            detector="project_map_broken",
            severity="critical",
            message=f"project-map.json failed to load: {type(exc).__name__}: {exc}",
            i18n_key="overview.health_alerts.detectors.project_map_broken",
            i18n_params={"detail": f"{type(exc).__name__}: {exc}"},
            context={"exception_type": type(exc).__name__},
            now=n,
        )
    return None


# ─── 7. daemon_uptime_warning ────────────────────────────────────


def check_daemon_uptime_warning(
    daemon: MnemosDaemon,
    *,
    now: datetime | None = None,
    threshold_seconds: float = 60.0,
) -> StoredAlert | None:
    """Info-level alert when the daemon has been up for less than
    ``threshold_seconds`` (default 60s).

    Self-clears: at the next cron tick (5 min later) uptime is well past the
    threshold so the alert is not re-emitted; the auto-dismiss-after-10-min
    UX is implemented client-side via the ``first_seen`` timestamp.
    """
    n = now if now is not None else utcnow()
    started = getattr(daemon, "started_at_monotonic", 0.0)
    if started <= 0.0:
        return None
    uptime = max(0.0, time.monotonic() - started)
    if uptime < threshold_seconds:
        return _make(
            id_="daemon_uptime_warning",
            detector="daemon_uptime_warning",
            severity="info",
            message=f"Daemon recently restarted ({int(uptime)}s ago).",
            i18n_key="overview.health_alerts.detectors.daemon_uptime_warning",
            i18n_params={"minutes": int(uptime / 60)},
            context={"uptime_seconds": int(uptime)},
            now=n,
        )
    return None


# ─── Orchestrator ────────────────────────────────────────────────


async def run_all_checks(
    *,
    daemon: MnemosDaemon,
    scheduler: AsyncIOScheduler,
    runtimes: dict[str, VaultRuntime],
    now: datetime | None = None,
) -> list[StoredAlert]:
    """Run all 7 detectors. Each is wrapped in try/except so one bad detector
    cannot kill the cron. Returns the list of currently-active alerts (None
    entries dropped).

    ``check_disk_low`` is async (so the blocking syscall stays off the event
    loop); other detectors are sync and called directly.
    """
    n = now if now is not None else utcnow()
    out: list[StoredAlert] = []

    sync_detectors: list[tuple[str, Any]] = [
        ("auto_dump_overdue", lambda: check_auto_dump_overdue(scheduler, now=n)),
        ("ingest_failure_streak", lambda: check_ingest_failure_streak(runtimes, now=n)),
        ("runaway_jobs", lambda: check_runaway_jobs(runtimes, now=n)),
        ("hook_silence", lambda: check_hook_silence(runtimes, now=n)),
        ("project_map_broken", lambda: check_project_map_broken(now=n)),
        ("daemon_uptime_warning", lambda: check_daemon_uptime_warning(daemon, now=n)),
    ]
    for name, fn in sync_detectors:
        try:
            alert = fn()
        except Exception:
            logger.exception("health detector %s raised", name)
            alert = None
        if alert is not None:
            out.append(alert)

    try:
        disk_alert = await check_disk_low(runtimes, now=n)
    except Exception:
        logger.exception("health detector disk_low raised")
        disk_alert = None
    if disk_alert is not None:
        out.append(disk_alert)

    return out
