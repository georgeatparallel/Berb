"""Unit tests for P0/P1 implementations.

P0 Critical Fixes:
- Circuit Breaker for LLMClient
- Thread Safety for SharedResearchMemory
- Event Sourcing for Pipeline

P1 High Priority:
- Caching for CascadingLLMClient
- Bulkhead Isolation for AsyncExperimentPool
- Pure Functions from Pipeline

# Author: Georgios-Chrysovalantis Chatzivantsidis
# Date: 2026-04-02
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from berb.llm.client import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    LLMClient,
)
from berb.llm.model_cascade import CascadeConfig, CascadeStep, CascadingLLMClient
from berb.memory.shared_memory import SharedResearchMemory
from berb.pipeline.runner import (
    _create_pivot_event,
    _get_rollback_target,
    _should_pivot,
)
from berb.pipeline.stages import (
    EventStore,
    PipelineState,
    Stage,
    StageStatus,
    StageTransitionEvent,
    TransitionEvent,
)

# ============================================================================
# P0-1: Circuit Breaker Tests
# ============================================================================


class TestCircuitBreakerState:
    """Test CircuitBreakerState dataclass."""

    def test_default_state(self):
        """Test default state values."""
        state = CircuitBreakerState()
        assert state.failure_count == 0
        assert state.success_count == 0
        assert state.last_failure_time == 0.0
        assert state.state == "closed"

    def test_custom_state(self):
        """Test custom state values."""
        state = CircuitBreakerState(
            failure_count=5,
            success_count=3,
            last_failure_time=1234567890.0,
            state="open",
        )
        assert state.failure_count == 5
        assert state.success_count == 3
        assert state.last_failure_time == 1234567890.0
        assert state.state == "open"


class TestCircuitBreaker:
    """Test CircuitBreaker pattern implementation."""

    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker()
        status = cb.get_status()
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["success_count"] == 0

    def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after max failures."""
        cb = CircuitBreaker(fail_max=3, reset_timeout=60.0)

        # Simulate 3 failures
        for _ in range(3):
            try:
                with cb:
                    raise Exception("Simulated failure")
            except Exception:
                pass

        status = cb.get_status()
        assert status["state"] == "open"
        assert status["failure_count"] == 3

    def test_circuit_breaker_raises_when_open(self):
        """Test circuit breaker raises error when open."""
        cb = CircuitBreaker(fail_max=1, reset_timeout=60.0)

        # Open the circuit
        try:
            with cb:
                raise Exception("Failure")
        except Exception:
            pass

        # Should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            with cb:
                pass  # Should not reach here

    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit breaker transitions to half_open after timeout."""
        cb = CircuitBreaker(fail_max=1, reset_timeout=0.1, success_threshold=1)

        # Open the circuit
        try:
            with cb:
                raise Exception("Failure")
        except Exception:
            pass

        assert cb.get_status()["state"] == "open"

        # Wait for timeout
        time.sleep(0.15)

        # Should transition to half_open on next attempt
        assert cb._can_execute()
        assert cb._state.state == "half_open"

    def test_circuit_breaker_closes_after_successes(self):
        """Test circuit breaker closes after success threshold."""
        cb = CircuitBreaker(fail_max=1, reset_timeout=0.1, success_threshold=2)

        # Open the circuit
        try:
            with cb:
                raise Exception("Failure")
        except Exception:
            pass

        # Wait for timeout
        time.sleep(0.15)

        # Simulate 2 successes
        with cb:
            pass  # Success 1
        with cb:
            pass  # Success 2

        status = cb.get_status()
        assert status["state"] == "closed"
        assert status["failure_count"] == 0

    def test_circuit_breaker_reopens_on_half_open_failure(self):
        """Test circuit breaker reopens on failure in half_open state."""
        cb = CircuitBreaker(fail_max=1, reset_timeout=0.1, success_threshold=2)

        # Open the circuit
        try:
            with cb:
                raise Exception("Failure")
        except Exception:
            pass

        # Wait for timeout
        time.sleep(0.15)

        # Fail in half_open state
        try:
            with cb:
                raise Exception("Failure in half_open")
        except Exception:
            pass

        status = cb.get_status()
        assert status["state"] == "open"

    def test_circuit_breaker_thread_safety(self):
        """Test circuit breaker is thread-safe."""
        cb = CircuitBreaker(fail_max=100, reset_timeout=60.0)
        success_count = [0]
        failure_count = [0]

        def worker(success: bool):
            try:
                with cb:
                    if success:
                        success_count[0] += 1
                    else:
                        raise Exception("Failure")
            except Exception:
                failure_count[0] += 1

        # Run concurrent operations. This test exercises thread-safety of the
        # synchronous CircuitBreaker, so plain ThreadPoolExecutor is enough —
        # wrapping futures in asyncio.gather() only added a fragile dependency
        # on ambient event-loop state (asyncio.get_event_loop() behavior
        # differs across Python versions when no loop is set).
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(worker, success=(i % 2 == 0)) for i in range(50)
            ]
            for future in futures:
                future.result()

        # Should not have crashed
        assert success_count[0] + failure_count[0] == 50

    def test_circuit_breaker_custom_config(self):
        """Test circuit breaker with custom configuration."""
        cb = CircuitBreaker(
            fail_max=10,
            reset_timeout=120.0,
            success_threshold=5,
        )
        assert cb.fail_max == 10
        assert cb.reset_timeout == 120.0
        assert cb.success_threshold == 5


def _minimal_rc_config_dict(tmp_path: Path | None = None) -> dict[str, Any]:
    """Build a minimal but fully-valid RCConfig dict for LLMClient tests.

    RCConfig.from_dict enforces REQUIRED_FIELDS (project.name, research.topic,
    runtime.timezone, notifications.channel, knowledge_base.root, llm.base_url,
    llm.api_key_env) — all sections must be present or validation raises.
    """
    kb_root = str(tmp_path / "kb") if tmp_path is not None else "./kb"
    return {
        "project": {"name": "test"},
        "research": {"topic": "test-topic"},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "local"},
        "knowledge_base": {"backend": "markdown", "root": kb_root},
        "llm": {
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
            "primary_model": "gpt-4o",
        },
    }


class TestLLMClientWithCircuitBreaker:
    """Test LLMClient integration with circuit breaker."""

    def test_llm_client_circuit_breaker_enabled(self, tmp_path):
        """Test LLMClient initializes with circuit breaker."""
        from berb.config import RCConfig

        config = RCConfig.from_dict(_minimal_rc_config_dict(tmp_path))

        client = LLMClient.from_rc_config(config)
        # Circuit breaker is enabled by default
        assert client._circuit_breaker is not None

    def test_llm_client_circuit_breaker_disabled(self, tmp_path):
        """Test LLMClient can disable circuit breaker."""
        from berb.config import RCConfig

        config = RCConfig.from_dict(_minimal_rc_config_dict(tmp_path))

        client = LLMClient.from_rc_config(config, circuit_breaker_enabled=False)
        assert client._circuit_breaker is None

    def test_llm_client_circuit_breaker_status(self, tmp_path):
        """Test LLMClient circuit breaker status method."""
        from berb.config import RCConfig

        config = RCConfig.from_dict(_minimal_rc_config_dict(tmp_path))

        client = LLMClient.from_rc_config(config)
        status = client.get_circuit_breaker_status()

        assert status is not None
        assert "state" in status
        assert "failure_count" in status
        assert "success_count" in status


# ============================================================================
# P0-2: Thread Safety Tests
# ============================================================================


class TestSharedResearchMemoryThreadSafety:
    """Test SharedResearchMemory thread safety fixes."""

    def test_sync_lock_initialized(self):
        """Test _sync_lock is properly initialized."""
        memory = SharedResearchMemory(project_id="test")
        assert hasattr(memory, "_sync_lock")
        assert isinstance(memory._sync_lock, type(threading.RLock()))

    def test_async_lock_lazy_initialization(self):
        """Test _async_lock is lazily initialized."""
        memory = SharedResearchMemory(project_id="test")
        assert memory._async_lock is None

        # Should create lock when accessed
        lock = memory._get_async_lock()
        assert lock is not None
        assert isinstance(lock, asyncio.Lock)

    def test_async_lock_reuse(self):
        """Test _async_lock is reused after creation."""
        memory = SharedResearchMemory(project_id="test")
        lock1 = memory._get_async_lock()
        lock2 = memory._get_async_lock()
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_concurrent_store_operations(self):
        """Test concurrent store operations don't corrupt data."""
        memory = SharedResearchMemory(project_id="test")

        async def store_value(key: str, value: Any):
            memory.store(key, value, agent_id=f"agent-{key}")

        # Run concurrent stores
        tasks = [store_value(f"key-{i}", f"value-{i}") for i in range(10)]
        await asyncio.gather(*tasks)

        # Verify all values stored correctly
        for i in range(10):
            value = memory.get(f"key-{i}")
            assert value == f"value-{i}"

    def test_thread_safe_store_from_threads(self):
        """Test store operations from multiple threads."""
        memory = SharedResearchMemory(project_id="test")
        results = []

        def store_from_thread(thread_id: int):
            try:
                memory.store(f"thread-{thread_id}", f"value-{thread_id}")
                results.append(("success", thread_id))
            except Exception as e:
                results.append(("error", thread_id, str(e)))

        # Run concurrent stores from threads
        threads = [threading.Thread(target=store_from_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert len(results) == 10
        assert all(r[0] == "success" for r in results)


# ============================================================================
# P0-3: Event Sourcing Tests
# ============================================================================


class TestStageTransitionEvent:
    """Test StageTransitionEvent dataclass."""

    def test_event_creation(self):
        """Test event creation with all fields."""
        event = StageTransitionEvent(
            run_id="test-123",
            from_stage=Stage.TOPIC_INIT,
            to_stage=Stage.PROBLEM_DECOMPOSE,
            from_status=StageStatus.DONE,
            to_status=StageStatus.RUNNING,
            event=TransitionEvent.START,
            metadata={"model": "gpt-4o"},
        )

        assert event.run_id == "test-123"
        assert event.from_stage == Stage.TOPIC_INIT
        assert event.to_stage == Stage.PROBLEM_DECOMPOSE
        assert event.from_status == StageStatus.DONE
        assert event.to_status == StageStatus.RUNNING
        assert event.event == TransitionEvent.START
        assert event.metadata == {"model": "gpt-4o"}

    def test_event_to_dict(self):
        """Test event serialization to dict."""
        event = StageTransitionEvent(
            run_id="test-123",
            from_stage=Stage.TOPIC_INIT,
            to_stage=Stage.PROBLEM_DECOMPOSE,
            from_status=StageStatus.DONE,
            to_status=StageStatus.RUNNING,
            event=TransitionEvent.START,
        )

        data = event.to_dict()

        assert data["run_id"] == "test-123"
        assert data["from_stage"] == 1
        assert data["from_stage_name"] == "TOPIC_INIT"
        assert data["to_stage"] == 2
        assert data["to_stage_name"] == "PROBLEM_DECOMPOSE"
        assert "timestamp" in data

    def test_event_from_dict(self):
        """Test event deserialization from dict."""
        data = {
            "run_id": "test-123",
            "from_stage": 1,
            "from_stage_name": "TOPIC_INIT",
            "to_stage": 2,
            "to_stage_name": "PROBLEM_DECOMPOSE",
            "from_status": "done",
            "to_status": "running",
            "event": "start",
            "timestamp": "2026-04-02T12:00:00+00:00",
            "metadata": {"model": "gpt-4o"},
        }

        event = StageTransitionEvent.from_dict(data)

        assert event.run_id == "test-123"
        assert event.from_stage == Stage.TOPIC_INIT
        assert event.to_stage == Stage.PROBLEM_DECOMPOSE
        assert event.metadata == {"model": "gpt-4o"}


class TestPipelineState:
    """Test PipelineState dataclass."""

    def test_default_state(self):
        """Test default pipeline state."""
        state = PipelineState()
        assert state.current_stage == Stage.TOPIC_INIT
        assert state.current_status == StageStatus.PENDING
        assert state.pivot_count == 0
        assert state.retry_count == 0
        assert state.last_error is None

    def test_apply_event(self):
        """Test applying event updates state."""
        state = PipelineState()
        event = StageTransitionEvent(
            run_id="test",
            from_stage=Stage.TOPIC_INIT,
            to_stage=Stage.PROBLEM_DECOMPOSE,
            from_status=StageStatus.DONE,
            to_status=StageStatus.RUNNING,
            event=TransitionEvent.SUCCEED,
            metadata={"decision": "pivot"},
        )

        state.apply(event)

        assert state.current_stage == Stage.PROBLEM_DECOMPOSE
        assert state.current_status == StageStatus.RUNNING
        assert state.pivot_count == 1

    def test_apply_multiple_events(self):
        """Test applying multiple events."""
        state = PipelineState()

        events = [
            StageTransitionEvent(
                run_id="test",
                from_stage=Stage(i),
                to_stage=Stage(i + 1),
                from_status=StageStatus.DONE,
                to_status=StageStatus.RUNNING,
                event=TransitionEvent.SUCCEED,
                metadata={"decision": "pivot" if i % 2 == 0 else "continue"},
            )
            for i in range(1, 5)
        ]

        for event in events:
            state.apply(event)

        assert state.current_stage == Stage(5)
        assert state.pivot_count == 2  # Events 1 and 3


class TestEventStore:
    """Test EventStore implementation."""

    def test_event_store_creation(self, tmp_path: Path):
        """Test event store creation."""
        store = EventStore(run_id="test-123")
        assert store.run_id == "test-123"
        assert store._events == []

    def test_event_store_append(self):
        """Test appending events to store."""
        store = EventStore(run_id="test-123")
        event = StageTransitionEvent(
            run_id="test-123",
            from_stage=Stage.TOPIC_INIT,
            to_stage=Stage.PROBLEM_DECOMPOSE,
            from_status=StageStatus.PENDING,
            to_status=StageStatus.RUNNING,
            event=TransitionEvent.START,
        )

        store.append(event)

        assert len(store._events) == 1
        assert store._events[0] == event

    def test_event_store_replay(self):
        """Test replaying events to reconstruct state."""
        store = EventStore(run_id="test-123")

        events = [
            StageTransitionEvent(
                run_id="test-123",
                from_stage=Stage(i),
                to_stage=Stage(i + 1),
                from_status=StageStatus.DONE,
                to_status=StageStatus.RUNNING,
                event=TransitionEvent.SUCCEED,
                metadata={},
            )
            for i in range(1, 5)
        ]

        for event in events:
            store.append(event)

        state = store.replay()

        assert state.current_stage == Stage(5)
        assert state.pivot_count == 0

    def test_event_store_get_events(self):
        """Test querying events."""
        store = EventStore(run_id="test-123")

        events = [
            StageTransitionEvent(
                run_id="test-123",
                from_stage=Stage.TOPIC_INIT,
                to_stage=Stage.PROBLEM_DECOMPOSE,
                from_status=StageStatus.PENDING,
                to_status=StageStatus.RUNNING,
                event=TransitionEvent.START,
                metadata={},
            ),
            StageTransitionEvent(
                run_id="test-123",
                from_stage=Stage.PROBLEM_DECOMPOSE,
                to_stage=Stage.SEARCH_STRATEGY,
                from_status=StageStatus.DONE,
                to_status=StageStatus.RUNNING,
                event=TransitionEvent.SUCCEED,
                metadata={},
            ),
        ]

        for event in events:
            store.append(event)

        # Filter by from_stage
        filtered = store.get_events(from_stage=Stage.TOPIC_INIT)
        assert len(filtered) == 1
        assert filtered[0].from_stage == Stage.TOPIC_INIT

    def test_event_store_get_last_n(self):
        """Test getting last N events."""
        store = EventStore(run_id="test-123")

        for i in range(1, 11):  # Stage 1-10
            store.append(
                StageTransitionEvent(
                    run_id="test-123",
                    from_stage=Stage(i),
                    to_stage=Stage(i + 1),
                    from_status=StageStatus.DONE,
                    to_status=StageStatus.RUNNING,
                    event=TransitionEvent.SUCCEED,
                    metadata={},
                )
            )

        last_3 = store.get_last_n_events(3)
        assert len(last_3) == 3
        assert last_3[0].from_stage == Stage(8)

    def test_event_store_persistence(self, tmp_path: Path):
        """Test event store persistence to disk."""
        storage_path = tmp_path / "event_log.json"
        store = EventStore(run_id="test-123", storage_path=str(storage_path))

        event = StageTransitionEvent(
            run_id="test-123",
            from_stage=Stage.TOPIC_INIT,
            to_stage=Stage.PROBLEM_DECOMPOSE,
            from_status=StageStatus.PENDING,
            to_status=StageStatus.RUNNING,
            event=TransitionEvent.START,
            metadata={"test": "value"},
        )
        store.append(event)

        # Create new store and load from disk
        store2 = EventStore(run_id="test-123", storage_path=str(storage_path))
        assert len(store2._events) == 1
        assert store2._events[0].metadata == {"test": "value"}

    def test_event_store_corruption_handling(self, tmp_path: Path):
        """Test event store handles corrupted files."""
        storage_path = tmp_path / "event_log.json"
        storage_path.write_text("invalid json", encoding="utf-8")

        # Should not crash, should start fresh
        store = EventStore(run_id="test-123", storage_path=str(storage_path))
        assert store._events == []


# ============================================================================
# P1-1: Caching Tests
# ============================================================================


class TestCascadingLLMClientCaching:
    """Test CascadingLLMClient caching implementation."""

    def test_cache_initialization(self):
        """Test cache is properly initialized."""
        base_client = Mock()
        config = CascadeConfig()

        client = CascadingLLMClient(
            base_client,
            config,
            cache_enabled=True,
            cache_max_size=100,
        )

        assert client._cache_enabled is True
        assert client._cache_max_size == 100
        assert client._cache == {}
        assert client._cache_stats["hits"] == 0
        assert client._cache_stats["misses"] == 0

    def test_cache_key_generation(self):
        """Test cache key generation is deterministic."""
        base_client = Mock()
        config = CascadeConfig()
        client = CascadingLLMClient(base_client, config)

        messages = [{"role": "user", "content": "test"}]
        key1 = client._generate_cache_key(messages, temperature=0.7)
        key2 = client._generate_cache_key(messages, temperature=0.7)
        key3 = client._generate_cache_key(messages, temperature=0.8)

        assert key1 == key2  # Same input = same key
        assert key1 != key3  # Different input = different key
        assert len(key1) == 32  # SHA-256 hex truncated

    def test_cache_hit(self):
        """Test cache hit returns cached value."""
        base_client = Mock()
        config = CascadeConfig()
        client = CascadingLLMClient(base_client, config, cache_enabled=True)

        messages = [{"role": "user", "content": "test"}]
        cached_response = Mock()

        # Manually cache a response
        key = client._generate_cache_key(messages)
        client._cache[key] = cached_response

        # Should return cached value
        result = client._get_from_cache(key)
        assert result is cached_response
        assert client._cache_stats["hits"] == 1

    def test_cache_miss(self):
        """Test cache miss returns None."""
        base_client = Mock()
        config = CascadeConfig()
        client = CascadingLLMClient(base_client, config, cache_enabled=True)

        result = client._get_from_cache("nonexistent-key")
        assert result is None
        assert client._cache_stats["misses"] == 1

    def test_cache_lru_eviction(self):
        """Test LRU cache eviction."""
        base_client = Mock()
        config = CascadeConfig()
        client = CascadingLLMClient(
            base_client,
            config,
            cache_enabled=True,
            cache_max_size=3,
        )

        # Fill cache
        for i in range(3):
            client._set_cache(f"key-{i}", f"value-{i}")

        assert len(client._cache) == 3

        # Add one more - should evict oldest
        client._set_cache("key-new", "value-new")

        assert len(client._cache) == 3
        assert "key-0" not in client._cache  # Oldest evicted
        assert client._cache_stats["evictions"] == 1

    def test_cache_stats(self):
        """Test cache statistics."""
        base_client = Mock()
        config = CascadeConfig()
        client = CascadingLLMClient(base_client, config, cache_enabled=True)

        # Simulate hits and misses
        client._cache_stats["hits"] = 80
        client._cache_stats["misses"] = 20

        stats = client.get_cache_stats()

        assert stats["hit_rate"] == 0.8
        assert stats["enabled"] is True
        assert "size" in stats
        assert "max_size" in stats

    def test_cache_clear(self):
        """Test cache clearing."""
        base_client = Mock()
        config = CascadeConfig()
        client = CascadingLLMClient(base_client, config, cache_enabled=True)

        # Add some data
        client._cache["key"] = "value"
        client._cache_stats["hits"] = 10

        client.clear_cache()

        assert len(client._cache) == 0
        assert client._cache_stats["hits"] == 0


# ============================================================================
# P1-2: Bulkhead Isolation Tests
# ============================================================================


class TestAsyncExperimentPoolBulkhead:
    """Test AsyncExperimentPool bulkhead isolation."""

    def test_bulkhead_semaphores_initialized(self):
        """Test bulkhead semaphores are properly initialized."""
        from berb.experiment.async_pool import AsyncExperimentPool, PoolConfig

        config = PoolConfig(max_workers=4)
        pool = AsyncExperimentPool(config, bulkhead_enabled=True)

        assert len(pool._worker_semaphores) == 4
        assert all(isinstance(s, asyncio.Semaphore) for s in pool._worker_semaphores)

    def test_bulkhead_disabled(self):
        """Test bulkhead can be disabled."""
        from berb.experiment.async_pool import AsyncExperimentPool, PoolConfig

        config = PoolConfig(max_workers=4)
        pool = AsyncExperimentPool(config, bulkhead_enabled=False)

        assert pool._worker_semaphores == []

    def test_bulkhead_default_enabled(self):
        """Test bulkhead is enabled by default."""
        from berb.experiment.async_pool import AsyncExperimentPool, PoolConfig

        config = PoolConfig(max_workers=4)
        pool = AsyncExperimentPool(config)

        assert pool._bulkhead_enabled is True
        assert len(pool._worker_semaphores) == 4


# ============================================================================
# P1-3: Pure Function Tests
# ============================================================================


class TestPureFunctions:
    """Test pure functions extracted from pipeline runner."""

    def test_should_pivot_true(self):
        """Test _should_pivot returns True when conditions met."""
        result = MagicMock()
        result.decision = "pivot"

        assert _should_pivot(result, 0) is True
        assert _should_pivot(result, 1) is True

    def test_should_pivot_false_max_depth(self):
        """Test _should_pivot returns False at max depth."""
        result = MagicMock()
        result.decision = "pivot"

        from berb.pipeline.stages import MAX_DECISION_PIVOTS

        assert _should_pivot(result, MAX_DECISION_PIVOTS) is False

    def test_should_pivot_false_invalid_decision(self):
        """Test _should_pivot returns False for invalid decision."""
        result = MagicMock()
        result.decision = "proceed"

        assert _should_pivot(result, 0) is False

    def test_get_rollback_target_pivot(self):
        """Test _get_rollback_target for pivot decision."""
        target = _get_rollback_target(Stage.RESEARCH_DECISION, "pivot")
        assert target == Stage.HYPOTHESIS_GEN

    def test_get_rollback_target_refine(self):
        """Test _get_rollback_target for refine decision."""
        target = _get_rollback_target(Stage.RESEARCH_DECISION, "refine")
        assert target == Stage.ITERATIVE_REFINE

    def test_create_pivot_event(self):
        """Test _create_pivot_event creates correct event."""
        event = _create_pivot_event(
            run_id="test-123",
            stage=Stage.RESEARCH_DECISION,
            rollback_target=Stage.HYPOTHESIS_GEN,
            pivot_count=2,
        )

        assert event.run_id == "test-123"
        assert event.from_stage == Stage.RESEARCH_DECISION
        assert event.to_stage == Stage.HYPOTHESIS_GEN
        assert event.metadata["decision"] == "pivot"
        assert event.metadata["pivot_count"] == 2


# ============================================================================
# Integration Tests
# ============================================================================


class TestP0P1Integration:
    """Integration tests for P0/P1 implementations."""

    def test_circuit_breaker_with_llm_client(self, tmp_path):
        """Test circuit breaker integrates properly with LLM client."""
        from berb.config import RCConfig

        config = RCConfig.from_dict(_minimal_rc_config_dict(tmp_path))

        client = LLMClient.from_rc_config(config)

        # Verify circuit breaker is accessible
        assert client._circuit_breaker is not None
        assert client.get_circuit_breaker_status() is not None

    def test_event_store_with_pipeline_state(self):
        """Test event store properly reconstructs pipeline state."""
        store = EventStore(run_id="test-123")

        # Simulate full pipeline run
        for i in range(1, 24):
            event = StageTransitionEvent(
                run_id="test-123",
                from_stage=Stage(i),
                to_stage=Stage(i + 1) if i < 23 else Stage(23),
                from_status=StageStatus.DONE,
                to_status=StageStatus.RUNNING if i < 23 else StageStatus.DONE,
                event=TransitionEvent.SUCCEED,
                metadata={},
            )
            store.append(event)

        state = store.replay()
        assert state.current_stage == Stage(23)
        assert state.current_status == StageStatus.DONE

    def test_cache_with_cascading_client(self):
        """Test caching integrates properly with cascading client."""
        base_client = AsyncMock()
        base_client.chat.return_value = Mock(content="response")

        config = CascadeConfig(
            cascade=[
                CascadeStep(model="test-model", min_score=0.0),
            ]
        )

        client = CascadingLLMClient(
            base_client,
            config,
            cache_enabled=True,
            cache_max_size=100,
        )

        # First call - cache miss
        # Note: Full integration test would require async test setup

        # Verify cache methods are accessible
        assert client._cache_enabled is True
        assert client.get_cache_stats() is not None


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance tests for P0/P1 implementations."""

    def test_circuit_breaker_overhead(self):
        """Test circuit breaker has minimal overhead."""
        cb = CircuitBreaker()

        start = time.perf_counter()
        for _ in range(1000):
            with cb:
                pass
        elapsed = time.perf_counter() - start

        # Should complete 1000 iterations in < 0.1 seconds
        assert elapsed < 0.1

    def test_cache_performance(self):
        """Test cache operations are fast."""
        base_client = Mock()
        config = CascadeConfig()
        client = CascadingLLMClient(base_client, config, cache_enabled=True)

        # Test cache set performance
        start = time.perf_counter()
        for i in range(1000):
            client._set_cache(f"key-{i}", f"value-{i}")
        elapsed_set = time.perf_counter() - start

        # Test cache get performance
        start = time.perf_counter()
        for i in range(1000):
            client._get_from_cache(f"key-{i}")
        elapsed_get = time.perf_counter() - start

        # Both should be fast
        assert elapsed_set < 0.1
        assert elapsed_get < 0.1

    def test_event_store_append_performance(self):
        """Test event store append is fast.

        The pipeline only defines Stage values 1..len(Stage) (23 stages as of
        this writing), so Stage(100) etc. would raise ValueError. Cycle
        through the valid stage range to still exercise 100 appends.
        """
        store = EventStore(run_id="test-123")
        n_stages = len(list(Stage))

        start = time.perf_counter()
        for i in range(1, 101):  # 100 event appends
            from_stage_val = ((i - 1) % n_stages) + 1
            to_stage_val = (i % n_stages) + 1
            store.append(
                StageTransitionEvent(
                    run_id="test-123",
                    from_stage=Stage(from_stage_val),
                    to_stage=Stage(to_stage_val),
                    from_status=StageStatus.DONE,
                    to_status=StageStatus.RUNNING,
                    event=TransitionEvent.SUCCEED,
                    metadata={},
                )
            )
        elapsed = time.perf_counter() - start

        # Should append 100 events in < 0.1 seconds
        assert elapsed < 0.1
