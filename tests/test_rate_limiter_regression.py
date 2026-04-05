"""Regression tests for BUG-002 (RateLimiter race condition fix).

Test that concurrent async calls to RateLimiter.wait() properly serialize
access and don't create multiple locks.
"""

import asyncio
import time
import pytest
from berb.literature._rate_limiter import RateLimiter


class TestRateLimiterConcurrency:
    """Test RateLimiter under concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_wait_serializes(self):
        """BUG-002 REGRESSION: Multiple concurrent wait() calls should serialize.
        
        Without the fix, multiple tasks could create separate locks and bypass
        rate limiting. This test verifies proper serialization.
        """
        limiter = RateLimiter(min_interval_sec=0.1, max_jitter_sec=0.0)
        
        # Track execution order
        execution_times = []
        
        async def worker(worker_id: int):
            await limiter.wait()
            execution_times.append((worker_id, time.monotonic()))
        
        # Launch 5 concurrent tasks
        tasks = [asyncio.create_task(worker(i)) for i in range(5)]
        await asyncio.gather(*tasks)
        
        # Verify serialization: each call should be at least 0.1s apart
        execution_times.sort(key=lambda x: x[0])  # Sort by worker_id for consistency
        times = [t[1] for t in execution_times]
        
        for i in range(1, len(times)):
            elapsed = times[i] - times[i - 1]
            # Should be at least min_interval_sec (0.1s) apart
            # Allow 10% tolerance for timing variations
            assert elapsed >= 0.09, f"Tasks not serialized: gap={elapsed}s"

    @pytest.mark.asyncio
    async def test_lock_created_once(self):
        """BUG-002 REGRESSION: Verify only one async_lock is created.
        
        The fix uses double-checked locking to ensure exactly one lock
        is created even under concurrent initialization.
        """
        limiter = RateLimiter(min_interval_sec=0.01)
        
        # Access lock from multiple concurrent tasks
        async def get_lock():
            return await limiter._get_async_lock()
        
        tasks = [asyncio.create_task(get_lock()) for _ in range(10)]
        locks = await asyncio.gather(*tasks)
        
        # All tasks should get the SAME lock instance
        assert all(lock is locks[0] for lock in locks), "Multiple locks created!"
        assert limiter._async_lock is locks[0]

    @pytest.mark.asyncio
    async def test_init_lock_created_on_demand(self):
        """Verify _init_lock is created lazily but safely."""
        limiter = RateLimiter(min_interval_sec=0.01)
        
        # Before first use, both locks should be None
        assert limiter._async_lock is None
        assert limiter._init_lock is None
        
        # After first use, both should exist
        await limiter.wait()
        assert limiter._async_lock is not None
        assert limiter._init_lock is not None

    @pytest.mark.asyncio
    async def test_rate_limiting_with_jitter(self):
        """Test that jitter is properly applied to rate limiting."""
        limiter = RateLimiter(min_interval_sec=0.05, max_jitter_sec=0.02)
        
        times = []
        for _ in range(5):
            await limiter.wait()
            times.append(time.monotonic())
        
        # Check intervals are in expected range
        for i in range(1, len(times)):
            elapsed = times[i] - times[i - 1]
            # Min interval + jitter should be 0.05-0.07s
            assert elapsed >= 0.04, f"Interval too short: {elapsed}s"
            assert elapsed <= 0.15, f"Interval too long: {elapsed}s"  # Generous upper bound

    @pytest.mark.asyncio
    async def test_sync_wait_thread_safety(self):
        """Test that wait_sync() is thread-safe."""
        import threading
        
        limiter = RateLimiter(min_interval_sec=0.05, max_jitter_sec=0.0)
        
        execution_times = []
        lock = threading.Lock()
        
        def worker():
            limiter.wait_sync()
            with lock:
                execution_times.append(time.monotonic())
        
        # Launch threads concurrently
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify serialization
        execution_times.sort()
        for i in range(1, len(execution_times)):
            elapsed = execution_times[i] - execution_times[i - 1]
            assert elapsed >= 0.04, f"Sync wait not serialized: gap={elapsed}s"


class TestRateLimiterEdgeCases:
    """Test RateLimiter edge cases."""

    @pytest.mark.asyncio
    async def test_zero_interval(self):
        """Test with zero min_interval_sec."""
        limiter = RateLimiter(min_interval_sec=0.0, max_jitter_sec=0.0)
        
        # Should not raise or block
        await limiter.wait()
        await limiter.wait()

    @pytest.mark.asyncio
    async def test_very_large_interval(self):
        """Test with very large min_interval_sec."""
        limiter = RateLimiter(min_interval_sec=3600.0)  # 1 hour
        
        start = time.monotonic()
        await limiter.wait()  # First call should not wait
        elapsed = time.monotonic() - start
        
        # First call should return immediately
        assert elapsed < 0.01

    def test_backoff_delay(self):
        """Test exponential backoff helper."""
        # Base case
        delay = RateLimiter.backoff_delay(0, base=2.0)
        assert 0.0 <= delay <= 60.0
        
        # Exponential growth
        delays = [RateLimiter.backoff_delay(i, base=2.0, max_delay=60.0) for i in range(10)]
        # Generally increasing (with jitter)
        assert delays[-1] >= delays[0]
        
        # Max delay cap
        for _ in range(100):
            delay = RateLimiter.backoff_delay(100, base=2.0, max_delay=1.0)
            assert delay <= 1.2  # max + 20% jitter
