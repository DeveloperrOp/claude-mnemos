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


@pytest.mark.asyncio
async def test_invalidate_during_inflight_does_not_corrupt_state() -> None:
    """If invalidate() runs while compute is still in flight, the cache
    must end in a clean state — t1's existing waiters get their result,
    but the cache is NOT repopulated, so the next caller after invalidate
    triggers a fresh compute."""
    cache: TTLCache[int] = TTLCache(ttl_s=60.0)
    n_calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_compute() -> int:
        nonlocal n_calls
        n_calls += 1
        started.set()
        await release.wait()
        return n_calls

    # Start the first compute
    t1 = asyncio.create_task(cache.get_or_compute(slow_compute))
    await started.wait()

    # Invalidate while compute is still running
    cache.invalidate()

    # Release the in-flight compute — t1 should complete cleanly
    release.set()
    result1 = await t1
    assert result1 == 1

    # Next call after invalidate must trigger fresh compute
    started.clear()
    release.clear()
    t2 = asyncio.create_task(cache.get_or_compute(slow_compute))
    await started.wait()
    release.set()
    result2 = await t2
    assert result2 == 2
    assert n_calls == 2


@pytest.mark.asyncio
async def test_exception_propagates_and_cache_self_heals() -> None:
    """Exception propagates to all waiters, cache self-heals on next call."""
    cache: TTLCache[int] = TTLCache(ttl_s=60.0)
    call_count = 0

    async def fn_that_raises() -> int:
        nonlocal call_count
        call_count += 1
        raise ValueError("test error")

    async def fn_that_succeeds() -> int:
        nonlocal call_count
        call_count += 1
        return 42

    # First call: fn_that_raises should raise
    with pytest.raises(ValueError, match="test error"):
        await cache.get_or_compute(fn_that_raises)

    assert call_count == 1

    # Second call: fn_that_succeeds should be called (not cached exception)
    result = await cache.get_or_compute(fn_that_succeeds)
    assert result == 42
    assert call_count == 2
