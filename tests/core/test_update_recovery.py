"""Resume-on-boot reconciliation for an interrupted Windows in-app swap.

All tests redirect ``update_apply.updates_dir`` at a tmp dir so reconciliation
reads/writes the marker, result.txt and last_apply.json under pytest's control.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_mnemos.core import update_apply, update_recovery


@pytest.fixture
def updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``update_apply.updates_dir`` at a tmp dir; return it."""
    d = tmp_path / "updates"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(update_apply, "updates_dir", lambda: d)
    return d


def _write_marker(updates: Path, *, version: str, old_dir: Path) -> None:
    update_apply.pending_marker_path().write_text(
        json.dumps(
            {
                "version": version,
                "install_dir": str(updates / "install"),
                "old_dir": str(old_dir),
                "started_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


# ── reconcile_pending ───────────────────────────────────────────────────


def test_no_marker_returns_none_and_writes_nothing(updates: Path) -> None:
    assert update_recovery.reconcile_pending("0.0.1") is None
    assert not update_recovery.last_apply_path().exists()


def test_matching_version_ok_cleans_marker_and_old_dir(updates: Path) -> None:
    old_dir = updates / "install.old"
    old_dir.mkdir()
    (old_dir / "stale.txt").write_text("x", encoding="utf-8")
    _write_marker(updates, version="0.9.0", old_dir=old_dir)

    result = update_recovery.reconcile_pending("0.9.0")

    assert result is not None
    assert result["version"] == "0.9.0"
    assert result["status"] == "ok"
    assert result["error"] is None
    assert "at" in result
    # marker + old backup both gone
    assert not update_apply.pending_marker_path().exists()
    assert not old_dir.exists()
    # last_apply persisted
    persisted = json.loads(update_recovery.last_apply_path().read_text("utf-8"))
    assert persisted["status"] == "ok"
    assert persisted["version"] == "0.9.0"


def test_non_matching_version_failed_keeps_backup_reads_result(updates: Path) -> None:
    old_dir = updates / "install.old"
    old_dir.mkdir()
    target_dir = updates / "0.9.0"
    target_dir.mkdir()
    (target_dir / "result.txt").write_text("FAILED: boom", encoding="utf-8")
    _write_marker(updates, version="0.9.0", old_dir=old_dir)

    result = update_recovery.reconcile_pending("0.0.1")

    assert result is not None
    assert result["status"] == "failed"
    assert result["error"] == "boom"
    assert result["version"] == "0.9.0"
    # marker cleared so it does not re-fire
    assert not update_apply.pending_marker_path().exists()
    # backup KEPT
    assert old_dir.exists()
    persisted = json.loads(update_recovery.last_apply_path().read_text("utf-8"))
    assert persisted["status"] == "failed"
    assert persisted["error"] == "boom"


def test_non_matching_version_failed_no_result_default_error(updates: Path) -> None:
    old_dir = updates / "install.old"
    old_dir.mkdir()
    _write_marker(updates, version="0.9.0", old_dir=old_dir)

    result = update_recovery.reconcile_pending("0.0.1")

    assert result is not None
    assert result["status"] == "failed"
    assert result["error"] == "update did not complete"
    assert not update_apply.pending_marker_path().exists()
    assert old_dir.exists()


def test_corrupt_marker_returns_none_no_raise(updates: Path) -> None:
    update_apply.pending_marker_path().write_text('"{bad', encoding="utf-8")
    # Must not raise.
    assert update_recovery.reconcile_pending("0.0.1") is None
    assert not update_recovery.last_apply_path().exists()


# ── reconcile_on_startup ────────────────────────────────────────────────


def test_reconcile_on_startup_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(running_version: str = "x") -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(update_recovery, "reconcile_pending", _boom)
    # Must swallow, not raise.
    update_recovery.reconcile_on_startup()


# ── read_last_apply ─────────────────────────────────────────────────────


def test_read_last_apply_missing_returns_none(updates: Path) -> None:
    assert update_recovery.read_last_apply() is None


def test_read_last_apply_round_trips(updates: Path) -> None:
    payload = {"version": "0.9.0", "status": "ok", "error": None, "at": "now"}
    update_recovery.last_apply_path().write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert update_recovery.read_last_apply() == payload


def test_read_last_apply_corrupt_returns_none(updates: Path) -> None:
    update_recovery.last_apply_path().write_text('"{bad', encoding="utf-8")
    assert update_recovery.read_last_apply() is None
