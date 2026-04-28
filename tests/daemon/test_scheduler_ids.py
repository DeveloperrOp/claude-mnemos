from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_mnemos.daemon.scheduler import build_empty_scheduler


def test_build_empty_scheduler_returns_scheduler():
    sch = build_empty_scheduler()
    assert isinstance(sch, AsyncIOScheduler)
    assert sch.get_jobs() == []


def test_build_empty_scheduler_timezone():
    sch = build_empty_scheduler(timezone="Europe/Kyiv")
    assert str(sch.timezone) == "Europe/Kyiv"
