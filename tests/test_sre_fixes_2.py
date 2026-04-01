"""Regression tests for SRE Run-2 fixes (2026-04-01).

BUG-A: RateLimiter.wait_sync() — _last_call read+write without mutex
BUG-B: put_cache() — non-atomic path.write_text() → corrupt JSON under concurrency
BUG-C: CascadingLLMClient.get_stats() — dict iteration without lock
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# BUG-A — RateLimiter.wait_sync() race on _last_call
# ---------------------------------------------------------------------------

class TestRateLimiterWaitSyncThreadSafety:
    """BUG-A: concurrent wait_sync() callers must each honour min_interval_sec."""

    def test_wait_sync_serialises_concurrent_callers(self):
        """N threads calling wait_sync() must collectively span ≥ (N-1)*interval seconds."""
        from berb.literature._rate_limiter import RateLimiter

        interval = 0.05  # 50 ms — fast enough for a unit test
        limiter = RateLimiter(min_interval_sec=interval, max_jitter_sec=0.0)
        N = 5
        barrier = threading.Barrier(N)
        call_times: list[float] = []

        def _worker():
            barrier.wait()
            limiter.wait_sync()
            call_times.append(time.monotonic())

        threads = [threading.Thread(target=_worker) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        call_times.sort()
        # The spread from first to last call must be at least (N-1) * interval.
        # A race (all reads before any write) would produce a spread close to 0.
        total_span = call_times[-1] - call_times[0]
        assert total_span >= (N - 1) * interval * 0.8, (
            f"BUG-A regression: spread={total_span:.3f}s, expected ≥ {(N-1)*interval:.3f}s — "
            "concurrent callers are under-sleeping"
        )

    def test_wait_sync_single_thread_still_works(self):
        """Non-regression: single-threaded sequential calls still enforce interval."""
        from berb.literature._rate_limiter import RateLimiter

        interval = 0.05
        limiter = RateLimiter(min_interval_sec=interval, max_jitter_sec=0.0)
        t0 = time.monotonic()
        limiter.wait_sync()
        limiter.wait_sync()
        elapsed = time.monotonic() - t0
        assert elapsed >= interval * 0.9, (
            f"Single-threaded wait_sync broken: elapsed={elapsed:.3f}s"
        )

    def test_sync_lock_attribute_exists(self):
        """BUG-A fix: _sync_lock must be present on RateLimiter instances."""
        from berb.literature._rate_limiter import RateLimiter
        import threading as _threading

        limiter = RateLimiter(min_interval_sec=1.0)
        assert hasattr(limiter, "_sync_lock"), "BUG-A: _sync_lock not added to RateLimiter"
        assert isinstance(limiter._sync_lock, type(_threading.Lock())), (
            "_sync_lock must be a threading.Lock"
        )


# ---------------------------------------------------------------------------
# BUG-B — put_cache() non-atomic write
# ---------------------------------------------------------------------------

class TestPutCacheAtomicWrite:
    """BUG-B: concurrent put_cache() writes must not corrupt the JSON file."""

    def test_concurrent_writes_produce_valid_json(self, tmp_path: Path):
        """N threads writing to the same cache key must always leave valid JSON."""
        from berb.literature.cache import put_cache, get_cached

        query, source, limit = "concurrent test", "arxiv", 10
        N = 20

        def _writer(i: int):
            papers = [{"title": f"paper-{i}-{j}", "id": f"{i}-{j}"} for j in range(5)]
            put_cache(query, source, limit, papers, cache_base=tmp_path)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # File must be readable and valid JSON after all concurrent writes
        result = get_cached(query, source, limit, cache_base=tmp_path)
        assert result is not None, (
            "BUG-B regression: get_cached returned None — JSON likely corrupted by concurrent writes"
        )
        assert isinstance(result, list), "BUG-B: cached papers must be a list"

    def test_single_writer_still_works(self, tmp_path: Path):
        """Non-regression: single-threaded put/get round-trip."""
        from berb.literature.cache import put_cache, get_cached

        papers = [{"title": "single", "id": "001"}]
        put_cache("q", "semantic_scholar", 5, papers, cache_base=tmp_path)
        result = get_cached("q", "semantic_scholar", 5, cache_base=tmp_path)
        assert result is not None
        assert result[0]["title"] == "single"

    def test_put_cache_writes_to_cache_dir(self, tmp_path: Path):
        """put_cache must create the cache directory and write a .json file."""
        from berb.literature.cache import put_cache, cache_key

        key = cache_key("my query", "openalex", 20)
        put_cache("my query", "openalex", 20, [], cache_base=tmp_path)
        assert (tmp_path / f"{key}.json").exists(), "Cache file was not created"

    def test_no_tmp_files_left_behind(self, tmp_path: Path):
        """After successful write, no .tmp files should remain in the cache dir."""
        from berb.literature.cache import put_cache

        N = 10

        def _writer(i: int):
            put_cache(f"query-{i}", "arxiv", 5, [{"id": str(i)}], cache_base=tmp_path)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        leftover_tmp = list(tmp_path.glob("*.tmp"))
        assert leftover_tmp == [], (
            f"BUG-B: {len(leftover_tmp)} .tmp files left behind: {leftover_tmp}"
        )


# ---------------------------------------------------------------------------
# BUG-C — CascadingLLMClient.get_stats() dict iteration race
# ---------------------------------------------------------------------------

class TestGetStatsThreadSafety:
    """BUG-C: get_stats() must not raise RuntimeError when dict is concurrently modified."""

    def _make_client(self) -> "CascadingLLMClient":  # noqa: F821
        from berb.llm.model_cascade import CascadingLLMClient, CascadeConfig, CascadeStep

        config = CascadeConfig(
            cascade=[
                CascadeStep("model-cheap", min_score=0.5),
                CascadeStep("model-premium", min_score=0.0),
            ]
        )
        base = MagicMock()
        return CascadingLLMClient(base_client=base, config=config)

    def test_get_stats_returns_dict(self):
        """Non-regression: get_stats() must return a dict with expected keys."""
        client = self._make_client()
        stats = client.get_stats()
        assert isinstance(stats, dict)
        assert "total_requests" in stats
        assert "cascade_exits" in stats
        assert "average_exit_step" in stats

    def test_get_stats_no_runtime_error_under_concurrent_mutation(self):
        """BUG-C regression: get_stats() must not raise RuntimeError under concurrent _record_cascade_exit calls."""
        client = self._make_client()
        errors: list[Exception] = []
        barrier = threading.Barrier(20)

        def _mutate():
            """Simulate what _record_cascade_exit does inside chat()."""
            barrier.wait()
            for i in range(50):
                # Direct mutation simulating concurrent chat() calls
                client._cascade_exits[i % 3] = client._cascade_exits.get(i % 3, 0) + 1

        def _reader():
            barrier.wait()
            for _ in range(50):
                try:
                    client.get_stats()
                except RuntimeError as exc:
                    errors.append(exc)

        threads = (
            [threading.Thread(target=_mutate) for _ in range(10)]
            + [threading.Thread(target=_reader) for _ in range(10)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], (
            f"BUG-C regression: get_stats() raised RuntimeError {len(errors)} time(s): {errors[0]}"
        )

    def test_get_stats_snapshot_not_live_reference(self):
        """BUG-C fix: cascade_exits in the returned dict must be a copy, not a live reference."""
        from berb.llm.model_cascade import CascadingLLMClient, CascadeConfig, CascadeStep

        config = CascadeConfig(cascade=[CascadeStep("m", min_score=0.0)])
        client = CascadingLLMClient(base_client=MagicMock(), config=config)
        client._cascade_exits[0] = 5

        stats = client.get_stats()
        # Mutate the internal dict AFTER calling get_stats
        client._cascade_exits[0] = 999

        # The returned snapshot should still reflect the value at call time
        assert stats["cascade_exits"].get(0) == 5, (
            "BUG-C: cascade_exits is a live reference — mutating internal dict changes returned stats"
        )
