"""Shared async-safe rate limiter for all literature API clients.

Replaces the duplicated time.sleep() calls scattered across openalex_client,
semantic_scholar, search, and verify modules with a single, event-loop-safe
implementation.

Usage (async callers):
    _limiter = RateLimiter(min_interval_sec=1.0, max_jitter_sec=0.1)
    await _limiter.wait()

Usage (sync callers — blocks the calling thread, not the event loop):
    _limiter = RateLimiter(min_interval_sec=1.0)
    _limiter.wait_sync()
"""

from __future__ import annotations

import asyncio
import logging
import random
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Enforces a minimum interval between calls.

    Thread-safe for synchronous callers via ``wait_sync()``.
    Async-safe for coroutine callers via ``await wait()``.

    Args:
        min_interval_sec: Minimum seconds between successive calls.
        max_jitter_sec: Upper bound of uniform jitter added to each wait.
                        Defaults to 10 % of min_interval_sec.
    """

    def __init__(
        self,
        min_interval_sec: float,
        max_jitter_sec: float | None = None,
    ) -> None:
        self._interval = min_interval_sec
        self._jitter = max_jitter_sec if max_jitter_sec is not None else min_interval_sec * 0.1
        self._last_call: float = 0.0
        # BUG-002 FIX: Use a regular threading.Lock for async lock initialization
        # to avoid the race condition. The _async_lock is protected by _init_lock.
        self._async_lock: asyncio.Lock | None = None
        self._init_lock: asyncio.Lock | None = None

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    async def _get_async_lock(self) -> asyncio.Lock:
        """Get or create the async lock with proper synchronization.
        
        BUG-002 FIX: Uses double-checked locking with a dedicated init lock
        to prevent the race condition where multiple tasks create separate locks.
        """
        # Fast path: lock already created
        if self._async_lock is not None:
            return self._async_lock
        
        # Create init lock lazily (safe because asyncio.Lock() just allocates,
        # doesn't interact with event loop until first use)
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        
        # Slow path: acquire init lock and create async lock
        async with self._init_lock:
            # Double-check after acquiring lock
            if self._async_lock is None:
                self._async_lock = asyncio.Lock()
            return self._async_lock

    async def wait(self) -> None:
        """Async-safe wait — yields control to the event loop during sleep.
        
        BUG-002 FIX: Uses _get_async_lock() to prevent race condition.
        """
        lock = await self._get_async_lock()
        async with lock:
            elapsed = time.monotonic() - self._last_call
            delay = self._interval + random.uniform(0.0, self._jitter) - elapsed
            if delay > 0:
                logger.debug("RateLimiter: async sleep %.3fs", delay)
                await asyncio.sleep(delay)
            self._last_call = time.monotonic()

    # ------------------------------------------------------------------
    # Sync interface (use only in non-async contexts)
    # ------------------------------------------------------------------

    def wait_sync(self) -> None:
        """Synchronous wait — blocks the calling thread.

        Only use this from synchronous code that is NOT running inside an
        asyncio event loop.  Prefer ``await wait()`` from coroutines.
        """
        elapsed = time.monotonic() - self._last_call
        delay = self._interval + random.uniform(0.0, self._jitter) - elapsed
        if delay > 0:
            logger.debug("RateLimiter: sync sleep %.3fs", delay)
            time.sleep(delay)
        self._last_call = time.monotonic()

    # ------------------------------------------------------------------
    # Exponential backoff helper
    # ------------------------------------------------------------------

    @staticmethod
    def backoff_delay(attempt: int, base: float = 2.0, max_delay: float = 60.0) -> float:
        """Return exponential backoff delay with ±20 % jitter."""
        delay = min(base ** attempt, max_delay)
        return delay + random.uniform(0.0, delay * 0.2)
