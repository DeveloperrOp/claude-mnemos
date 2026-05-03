"""Tests for claude_mnemos.core.ttl_cache."""

from __future__ import annotations

import asyncio

import pytest

from claude_mnemos.core.ttl_cache import TTLCache


@pytest.mark.asyncio
async def test_get_or_compute_caches_first_result() -> None:
    cache: TTLCache[int] = TTLCache(ttl_s=60.0)
    calls = 0

    async def compute() -> int:
        nonlocal calls
        calls += 1
        return 42

    assert await cache.get_or_compute(compute) == 42
    assert await cache.get_or_compute(compute) == 42
    assert calls == 1


@pytest.mark.asyncio
async def test_get_or_compute_recomputes_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    cache: TTLCache[int] = TTLCache(ttl_s=10.0)
    now = [0.0]
    monkeypatch.setattr(
        "claude_mnemos.core.ttl_cache.time.monotonic", lambda: now[0]
    )
    calls = 0

    async def compute() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_compute(compute) == 1
    now[0] = 5.0
    assert await cache.get_or_compute(compute) == 1
    now[0] = 11.0
    assert await cache.get_or_compute(compute) == 2


@pytest.mark.asyncio
async def test_invalidate_forces_recompute() -> None:
    cache: TTLCache[int] = TTLCache(ttl_s=60.0)
    calls = 0

    async def compute() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_compute(compute) == 1
    cache.invalidate()
    assert await cache.get_or_compute(compute) == 2


@pytest.mark.asyncio
async def test_concurrent_callers_share_inflight_future() -> None:
    """Three concurrent get_or_compute() calls must share ONE compute() invocation."""
    cache: TTLCache[int] = TTLCache(ttl_s=60.0)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def compute() -> int:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return 7

    task1 = asyncio.create_task(cache.get_or_compute(compute))
    await started.wait()
    task2 = asyncio.create_task(cache.get_or_compute(compute))
    task3 = asyncio.create_task(cache.get_or_compute(compute))
    release.set()
    results = await asyncio.gather(task1, task2, task3)
    assert results == [7, 7, 7]
    assert calls == 1
