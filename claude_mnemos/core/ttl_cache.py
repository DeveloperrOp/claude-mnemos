"""TTL-based cache with asyncio anti-stampede support."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")
_MISSING: Any = object()


class TTLCache(Generic[T]):
    """Thread-safe TTL cache with asyncio anti-stampede via inflight futures.

    When multiple concurrent callers invoke get_or_compute() while a compute
    is in flight, they all await the same future instead of spawning duplicate
    compute invocations.
    """

    def __init__(self, ttl_s: float) -> None:
        """Initialize cache with TTL in seconds.

        Args:
            ttl_s: Time-to-live in seconds. After this duration from the last
                   successful compute, the cache is considered stale.
        """
        self.ttl_s = ttl_s
        self._value: Any = _MISSING
        self._expires_at: float | None = None
        self._lock = asyncio.Lock()
        self._inflight: asyncio.Future[T] | None = None

    async def get_or_compute(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Get cached value or compute it if expired/missing.

        Multiple concurrent callers during compute share the same in-flight
        future, ensuring fn() is only invoked once.

        Args:
            fn: Async callable that computes the value.

        Returns:
            Cached or newly computed value.

        Raises:
            Any exception raised by fn() is propagated to all waiters.
        """
        should_compute = False

        async with self._lock:
            # Check if we have a valid cached value
            if self._value is not _MISSING and self._expires_at is not None:
                if time.monotonic() < self._expires_at:
                    return self._value

            # Check if compute is already in flight
            if self._inflight is None:
                # Spawn new compute
                self._inflight = asyncio.Future()
                should_compute = True

            # Capture the inflight future (will either be newly created or existing)
            inflight = self._inflight

        # If we're the one who should compute, do it
        if should_compute:
            try:
                result = await fn()
                async with self._lock:
                    # Only commit the result to the cache if our inflight
                    # future is still the active one. invalidate() may have
                    # cleared self._inflight while we were computing — in
                    # that case we still resolve waiters with our result
                    # (they're already awaiting `inflight`), but we do NOT
                    # repopulate self._value, so the next caller will
                    # trigger a fresh compute as the operator requested.
                    if self._inflight is inflight:
                        self._value = result
                        self._expires_at = time.monotonic() + self.ttl_s
                        self._inflight = None
                    inflight.set_result(result)
                return result
            except BaseException as e:
                async with self._lock:
                    if self._inflight is inflight:
                        self._inflight = None
                    inflight.set_exception(e)
                raise
        else:
            # We're not computing; await the inflight future
            return await inflight

    def invalidate(self) -> None:
        """Invalidate cached value, forcing recompute on next call.

        Safe to call concurrently with an in-flight ``get_or_compute``: the
        in-flight future will still resolve its existing waiters with the
        computed value, but the cache will not be repopulated, so the next
        caller after invalidation will trigger a fresh compute.
        """
        self._value = _MISSING
        self._expires_at = None
        self._inflight = None
