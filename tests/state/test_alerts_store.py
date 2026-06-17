from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_mnemos.state.alerts_store import AlertsStore, StoredAlert


def test_stored_alert_accepts_i18n_fields():
    """v0.0.12: StoredAlert may carry i18n_key + i18n_params alongside the
    legacy message field. Both serialize round-trip cleanly."""
    a = StoredAlert(
        id="x",
        detector="hook_silence",
        severity="warning",
        message="4 recent Claude Code session(s) detected, but no ingest job has succeeded in the last 6h. Check that hooks are installed.",
        i18n_key="overview.health_alerts.detectors.hook_silence",
        i18n_params={"count": 4},
        first_seen=datetime(2026, 5, 8, tzinfo=UTC),
        last_seen=datetime(2026, 5, 8, tzinfo=UTC),
    )
    dumped = a.model_dump(mode="json")
    assert dumped["i18n_key"] == "overview.health_alerts.detectors.hook_silence"
    assert dumped["i18n_params"] == {"count": 4}

    # Round-trip
    reloaded = StoredAlert.model_validate(dumped)
    assert reloaded.i18n_key == "overview.health_alerts.detectors.hook_silence"
    assert reloaded.i18n_params == {"count": 4}


def test_stored_alert_omits_i18n_fields_for_legacy_payload():
    """v0.0.11- alerts on disk have neither i18n_key nor i18n_params.
    Forward-compat: the model loads them with both fields = None / {}."""
    a = StoredAlert.model_validate({
        "id": "x",
        "detector": "hook_silence",
        "severity": "warning",
        "message": "legacy",
        "first_seen": "2026-05-08T00:00:00+00:00",
        "last_seen": "2026-05-08T00:00:00+00:00",
    })
    assert a.i18n_key is None
    assert a.i18n_params == {}


def test_upsert_refreshes_i18n_fields_on_redetection():
    """v0.0.12: when a detector re-fires with updated i18n_params (e.g.
    the count changed), upsert() must overwrite the stored params, not
    keep the stale first-seen value. Regression for the silent-drop bug
    found by code-quality review of 69eae38."""
    from datetime import UTC, datetime
    from claude_mnemos.state.alerts_store import AlertsStore, StoredAlert

    store = AlertsStore()
    first = StoredAlert(
        id="hook_silence",
        detector="hook_silence",
        severity="warning",
        message="4 sessions, no ingest",
        i18n_key="overview.health_alerts.detectors.hook_silence",
        i18n_params={"count": 4},
        first_seen=datetime(2026, 5, 8, 10, tzinfo=UTC),
        last_seen=datetime(2026, 5, 8, 10, tzinfo=UTC),
    )
    store.upsert(first)
    assert store.alerts[0].i18n_params == {"count": 4}

    # Re-detection with a higher count and a new message
    second = first.model_copy(update={
        "message": "7 sessions, no ingest",
        "i18n_params": {"count": 7},
        "last_seen": datetime(2026, 5, 8, 12, tzinfo=UTC),
    })
    store.upsert(second)
    assert len(store.alerts) == 1
    assert store.alerts[0].i18n_params == {"count": 7}
    assert store.alerts[0].message == "7 sessions, no ingest"


def _alert(id_: str, *, dismissed: bool = False) -> StoredAlert:
    return StoredAlert(
        id=id_,
        detector=id_,
        severity="critical",
        message=id_,
        first_seen=datetime(2026, 6, 10, tzinfo=UTC),
        last_seen=datetime(2026, 6, 10, tzinfo=UTC),
        dismissed=dismissed,
    )


def test_reconcile_drops_cleared_alerts():
    """An alert whose condition has cleared (not in the active set) must be
    removed, not lingered forever. Regression: project_map_broken stuck for a
    week after a transient corruption because the cron only ever upserted."""
    store = AlertsStore()
    store.upsert(_alert("project_map_broken"))
    store.upsert(_alert("hook_silence"))
    assert len(store.alerts) == 2

    # Next tick: only hook_silence still fires.
    store.reconcile([_alert("hook_silence")])

    ids = {a.id for a in store.alerts}
    assert ids == {"hook_silence"}


def test_reconcile_preserves_first_seen_and_dismissed_on_survivors():
    store = AlertsStore()
    original = StoredAlert(
        id="hook_silence",
        detector="hook_silence",
        severity="warning",
        message="old",
        first_seen=datetime(2026, 6, 1, tzinfo=UTC),
        last_seen=datetime(2026, 6, 1, tzinfo=UTC),
        dismissed=True,
    )
    store.upsert(original)

    # Re-detected this tick with a fresh last_seen/message.
    redetected = original.model_copy(
        update={
            "message": "new",
            "last_seen": datetime(2026, 6, 17, tzinfo=UTC),
        }
    )
    store.reconcile([redetected])

    assert len(store.alerts) == 1
    survivor = store.alerts[0]
    assert survivor.first_seen == datetime(2026, 6, 1, tzinfo=UTC)  # preserved
    assert survivor.dismissed is True  # user state preserved
    assert survivor.message == "new"  # detector data refreshed


def test_reconcile_with_empty_active_clears_all():
    store = AlertsStore()
    store.upsert(_alert("project_map_broken"))
    store.upsert(_alert("runaway_jobs"))
    store.reconcile([])
    assert store.alerts == []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make(id_: str = "x", **overrides) -> StoredAlert:
    base = dict(
        id=id_,
        detector="test",
        severity="warning",
        message="m",
        context={"k": "v"},
        first_seen=_now(),
        last_seen=_now(),
    )
    base.update(overrides)
    return StoredAlert(**base)


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "alerts.json"


def test_load_missing_returns_empty(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    assert s.alerts == []
    assert s.version == 1


def test_save_and_reload_roundtrip(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    s.upsert(_make("a"))
    s.save()
    assert store_path.exists()
    s2 = AlertsStore.load(store_path)
    assert len(s2.alerts) == 1
    assert s2.alerts[0].id == "a"


def test_upsert_inserts_then_updates(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    a1 = _make("dup", message="first")
    s.upsert(a1)
    later = _now() + timedelta(minutes=5)
    a2 = _make("dup", message="second", last_seen=later)
    s.upsert(a2)
    assert len(s.alerts) == 1
    assert s.alerts[0].message == "second"
    # first_seen preserved across upsert
    assert s.alerts[0].first_seen == a1.first_seen
    # last_seen refreshed
    assert s.alerts[0].last_seen == later


def test_upsert_preserves_silenced_until_and_dismissed(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    s.upsert(_make("dup"))
    s.silence("dup", timedelta(hours=1))
    s.dismiss("dup")
    silenced_until = s.alerts[0].silenced_until
    s.upsert(_make("dup", message="changed"))
    assert s.alerts[0].silenced_until == silenced_until
    assert s.alerts[0].dismissed is True
    assert s.alerts[0].message == "changed"


def test_silence_returns_none_for_missing(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    assert s.silence("nope", timedelta(hours=1)) is None


def test_dismiss_returns_none_for_missing(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    assert s.dismiss("nope") is None


def test_active_alerts_filters_dismissed_and_silenced(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    s.upsert(_make("a"))
    s.upsert(_make("b"))
    s.upsert(_make("c"))
    s.dismiss("a")
    s.silence("b", timedelta(hours=1))
    active = s.active_alerts()
    ids = {a.id for a in active}
    assert ids == {"c"}


def test_active_alerts_returns_silenced_after_expiry(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    s.upsert(_make("b"))
    s.silence("b", timedelta(seconds=1))
    future = _now() + timedelta(minutes=10)
    assert any(a.id == "b" for a in s.active_alerts(now=future))


def test_silenced_alerts_excludes_dismissed(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    s.upsert(_make("a"))
    s.upsert(_make("b"))
    s.silence("a", timedelta(hours=1))
    s.silence("b", timedelta(hours=1))
    s.dismiss("b")
    silenced = s.silenced_alerts()
    assert {a.id for a in silenced} == {"a"}


def test_load_corrupt_json_returns_empty(store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text("not json{{{", encoding="utf-8")
    s = AlertsStore.load(store_path)
    assert s.alerts == []


def test_save_uses_atomic_write(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    s.upsert(_make("a"))
    s.save()
    # Verify it's valid JSON and properly written
    import json
    data = json.loads(store_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["alerts"]) == 1


def test_purge_old_drops_dismissed_past_retention(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    old = _now() - timedelta(days=45)
    fresh = _now() - timedelta(days=5)
    # Old + dismissed → purged
    s.alerts.append(_make("old_dismissed", first_seen=old, last_seen=old, dismissed=True))
    # Old + not dismissed → kept (operator may want to see lingering active alerts)
    s.alerts.append(_make("old_active", first_seen=old, last_seen=old))
    # Fresh + dismissed → kept (still within retention)
    s.alerts.append(_make("fresh_dismissed", first_seen=fresh, last_seen=fresh, dismissed=True))
    removed = s.purge_old(retention_days=30)
    assert removed == 1
    ids = {a.id for a in s.alerts}
    assert ids == {"old_active", "fresh_dismissed"}


def test_load_from_disk_purges_at_load(store_path: Path) -> None:
    s = AlertsStore.load(store_path)
    old = _now() - timedelta(days=60)
    s.alerts.append(_make("ancient", first_seen=old, last_seen=old, dismissed=True))
    s.save()
    s2 = AlertsStore.load_from_disk(store_path)
    assert all(a.id != "ancient" for a in s2.alerts)


def test_lock_is_per_instance(store_path: Path) -> None:
    s1 = AlertsStore.load(store_path)
    s2 = AlertsStore.load(store_path)
    assert s1._lock is not s2._lock
