from __future__ import annotations

import threading
from datetime import UTC, datetime

from claude_mnemos.daemon.alerts import Alerts


def _ts(s: int = 0) -> datetime:
    return datetime(2026, 4, 27, 14, 0, s, tzinfo=UTC)


def test_add_returns_alert_with_id():
    alerts = Alerts()
    a = alerts.add(kind="external_create", path="/x.md", message="m", detected_at=_ts(0))
    assert a.id
    assert a.kind == "external_create"
    assert a.path == "/x.md"
    assert a.message == "m"
    assert a.detected_at == _ts(0)


def test_list_newest_first():
    alerts = Alerts()
    a1 = alerts.add(kind="parse_failed", path="/a.md", message="1", detected_at=_ts(0))
    a2 = alerts.add(kind="parse_failed", path="/b.md", message="2", detected_at=_ts(1))
    a3 = alerts.add(kind="parse_failed", path="/c.md", message="3", detected_at=_ts(2))
    out = alerts.list()
    assert [a.id for a in out] == [a3.id, a2.id, a1.id]


def test_ring_buffer_caps_at_max():
    alerts = Alerts()
    for i in range(Alerts.MAX + 50):
        alerts.add(kind="handler_error", path=f"/p{i}.md", message="m", detected_at=_ts(0))
    out = alerts.list()
    assert len(out) == Alerts.MAX


def test_clear_existing_returns_true():
    alerts = Alerts()
    a = alerts.add(kind="lock_timeout", path="/x.md", message="m", detected_at=_ts(0))
    assert alerts.clear(a.id) is True
    assert all(x.id != a.id for x in alerts.list())


def test_clear_missing_returns_false():
    alerts = Alerts()
    alerts.add(kind="lock_timeout", path="/x.md", message="m", detected_at=_ts(0))
    assert alerts.clear("nonexistent") is False


def test_thread_safety_smoke():
    alerts = Alerts()
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for i in range(100):
                alerts.add(
                    kind="handler_error",
                    path=f"/p{i}.md",
                    message="m",
                    detected_at=_ts(0),
                )
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(alerts.list()) <= Alerts.MAX
