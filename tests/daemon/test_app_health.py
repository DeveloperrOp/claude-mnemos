from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos import __version__
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.schemas import SchedulerJobInfo


@pytest.fixture
def app(tmp_path: Path):
    return create_app(tmp_path)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_returns_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


async def test_health_includes_version(tmp_path: Path):
    app = create_app(tmp_path)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/health")
    body = r.json()
    assert body["version"] == __version__
    assert "uptime_s" in body
    assert body["scheduler_jobs"] == []
    # vault field is gone; vaults dict is present and empty (no daemon attached)
    assert "vault" not in body
    assert body["vaults"] == {}


async def test_health_includes_scheduler_jobs_when_daemon_attached(tmp_path: Path):
    class FakeDaemon:
        started_at_monotonic = 0.0
        runtimes: dict = {}

        def __init__(self) -> None:
            pass

        def scheduler_jobs_info(self) -> list[SchedulerJobInfo]:
            return [
                SchedulerJobInfo(
                    id="daily_snapshot",
                    next_run_time=datetime(2026, 4, 27, 4, 0, tzinfo=UTC),
                    trigger="cron[hour=4]",
                )
            ]

    app = create_app(tmp_path, daemon=FakeDaemon())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/health")
    body = r.json()
    assert len(body["scheduler_jobs"]) == 1
    assert body["scheduler_jobs"][0]["id"] == "daily_snapshot"


async def test_version_endpoint(client):
    r = await client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == __version__
    assert body["python_version"]
    assert body["platform"]


async def test_unknown_endpoint_returns_404(client):
    r = await client.get("/does-not-exist")
    assert r.status_code == 404


async def test_health_default_empty_vaults(client):
    """No daemon attached → vaults dict is empty, alerts_count is 0."""
    r = await client.get("/health")
    body = r.json()
    assert body["vaults"] == {}
    assert body["alerts_count"] == 0


async def test_health_reports_running_observer(tmp_path: Path):
    from claude_mnemos.daemon.alerts import Alerts

    class FakeObserver:
        is_running = True

    class FakeRuntime:
        def __init__(self) -> None:
            self.observer = FakeObserver()
            self.job_store = None

    class FakeDaemon:
        started_at_monotonic = 0.0
        alerts = Alerts()

        def __init__(self) -> None:
            self.runtimes = {"alpha": FakeRuntime()}

        def scheduler_jobs_info(self) -> list[SchedulerJobInfo]:
            return []

    daemon = FakeDaemon()
    daemon.alerts.add(
        kind="parse_failed",
        path="/x.md",
        message="m",
        detected_at=datetime(2026, 4, 27, 14, 0, tzinfo=UTC),
    )

    app = create_app(tmp_path, daemon=daemon)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/health")
    body = r.json()
    assert body["vaults"]["alpha"]["watchdog_running"] is True
    assert body["alerts_count"] == 1


async def test_health_reports_observer_not_alive(tmp_path: Path):
    from claude_mnemos.daemon.alerts import Alerts

    class StoppedObserver:
        is_running = False

    class FakeRuntime:
        def __init__(self) -> None:
            self.observer = StoppedObserver()
            self.job_store = None

    class FakeDaemon:
        started_at_monotonic = 0.0
        alerts = Alerts()

        def __init__(self) -> None:
            self.runtimes = {"alpha": FakeRuntime()}

        def scheduler_jobs_info(self) -> list[SchedulerJobInfo]:
            return []

    app = create_app(tmp_path, daemon=FakeDaemon())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/health")
    body = r.json()
    assert body["vaults"]["alpha"]["watchdog_running"] is False


async def test_health_jobs_counts_default(client):
    """No daemon → vaults empty, jobs_alert false."""
    r = await client.get("/health")
    body = r.json()
    assert body["vaults"] == {}
    assert body["jobs_alert"] is False


async def test_health_jobs_alert_threshold(tmp_path: Path):
    from claude_mnemos.daemon.alerts import Alerts
    from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore

    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    # Create 11 dead_letter rows
    for i in range(11):
        job = store.create(kind="ingest", payload={"transcript_path": f"/p{i}"})
        store._conn.execute(
            "UPDATE jobs SET status='dead_letter' WHERE id=?", (job.id,)
        )

    class FakeRuntime:
        def __init__(self) -> None:
            self.observer = None
            self.job_store = store

    class FakeDaemon:
        started_at_monotonic = 0.0
        alerts = Alerts()

        def __init__(self) -> None:
            self.runtimes = {"alpha": FakeRuntime()}

        def scheduler_jobs_info(self) -> list:
            return []

    app = create_app(tmp_path, daemon=FakeDaemon())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/health")
    store.close()
    body = r.json()
    assert body["vaults"]["alpha"]["jobs_dead_letter"] == 11
    assert body["jobs_alert"] is True
