"""Regression tests for reasoning registry bug fixes.

Tests for:
- BUG-R001: Thread-safe singleton creation
- BUG-R002: Error handling in auto_register_all()
- BUG-R003: Timezone normalization in ReasoningContext.from_dict()
- BUG-NEW-001: Runtime warning for sync/async mixing
- BUG-NEW-002: Idempotency of auto_register_all()
- BUG-NEW-003: Fallback datetime format parsing

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import asyncio
import threading
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from berb.reasoning.base import ReasoningContext, MethodType
from berb.reasoning.registry import (
    ReasonerRegistry,
    get_reasoner,
    create_reasoner,
    auto_register_all,
)


# =============================================================================
# BUG-R001: Thread-safe Singleton Creation Tests
# =============================================================================

class TestSingletonThreadSafety:
    """Test BUG-R001 fix: Thread-safe singleton creation."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Clear singletons before and after each test."""
        ReasonerRegistry.clear_singletons()
        # Reset locks
        ReasonerRegistry._init_lock = None
        if hasattr(ReasonerRegistry, '_sync_init_lock'):
            ReasonerRegistry._sync_init_lock = None
        yield
        ReasonerRegistry.clear_singletons()

    def test_singleton_returns_same_instance_sync(self):
        """BUG-R001: Sync get() returns same instance on repeated calls."""
        # Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # Get singleton twice
        instance1 = get_reasoner("bayesian", llm_client=None)
        instance2 = get_reasoner("bayesian", llm_client=None)

        # Should be same instance
        assert instance1 is instance2

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance_async(self):
        """BUG-R001: Async get_async() returns same instance on repeated calls."""
        # Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # Get singleton twice via async
        instance1 = await ReasonerRegistry.get_async("bayesian", llm_client=None)
        instance2 = await ReasonerRegistry.get_async("bayesian", llm_client=None)

        # Should be same instance
        assert instance1 is instance2

    @pytest.mark.asyncio
    async def test_concurrent_async_access(self):
        """BUG-R001: Concurrent async calls return same instance."""
        # Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # Track created instances
        created_instances = []

        async def get_instance():
            instance = await ReasonerRegistry.get_async("bayesian", llm_client=None)
            created_instances.append(id(instance))
            return instance

        # Launch 10 concurrent tasks
        tasks = [asyncio.create_task(get_instance()) for _ in range(10)]
        await asyncio.gather(*tasks)

        # All should have same instance ID
        assert len(set(created_instances)) == 1, "Multiple instances created under concurrent access!"

    def test_concurrent_sync_access(self):
        """BUG-R001: Concurrent sync calls return same instance."""
        # Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # Track created instances
        created_instances = []
        lock = threading.Lock()

        def get_instance():
            instance = get_reasoner("bayesian", llm_client=None)
            with lock:
                created_instances.append(id(instance))

        # Launch 10 concurrent threads
        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should have same instance ID
        assert len(set(created_instances)) == 1, "Multiple instances created under concurrent access!"

    @pytest.mark.asyncio
    async def test_mixed_sync_async_access(self):
        """BUG-R001: Mixed sync and async access returns same instance."""
        # Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # Get via sync first
        instance_sync = get_reasoner("bayesian", llm_client=None)

        # Get via async
        instance_async = await ReasonerRegistry.get_async("bayesian", llm_client=None)

        # Get via sync again
        instance_sync2 = get_reasoner("bayesian", llm_client=None)

        # All should be same instance
        assert instance_sync is instance_async
        assert instance_async is instance_sync2

    def test_clear_singletons_works(self):
        """Verify clear_singletons() allows new instance creation."""
        # Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # Get singleton
        instance1 = get_reasoner("bayesian", llm_client=None)

        # Clear
        ReasonerRegistry.clear_singletons()

        # Get again - should be new instance
        instance2 = get_reasoner("bayesian", llm_client=None)

        # Should be different instances
        assert instance1 is not instance2

    @pytest.mark.asyncio
    async def test_initialize_creates_locks(self):
        """BUG-R001: initialize() pre-creates locks."""
        # Ensure locks are None
        ReasonerRegistry._init_lock = None
        if hasattr(ReasonerRegistry, '_sync_init_lock'):
            ReasonerRegistry._sync_init_lock = None

        # Initialize
        await ReasonerRegistry.initialize()

        # Locks should exist
        assert ReasonerRegistry._init_lock is not None
        assert hasattr(ReasonerRegistry, '_sync_init_lock')
        assert ReasonerRegistry._sync_init_lock is not None


# =============================================================================
# BUG-R002: Error Handling in auto_register_all() Tests
# =============================================================================

class TestAutoRegisterErrorHandling:
    """Test BUG-R002 fix: Error handling in auto_register_all()."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Clear registry before and after each test."""
        ReasonerRegistry._registry.clear()
        ReasonerRegistry.clear_singletons()
        yield
        ReasonerRegistry._registry.clear()

    def test_auto_register_handles_import_errors(self, caplog):
        """BUG-R002: auto_register_all() handles import errors gracefully."""
        # Mock one module to fail
        with patch.dict('sys.modules', {'berb.reasoning.bayesian': None}):
            with patch('builtins.__import__', side_effect=ImportError("Simulated import error")):
                # Should not raise
                auto_register_all()

        # Should have logged error
        assert "Failed to register reasoning method" in caplog.text
        assert "Simulated import error" in caplog.text

    def test_auto_register_logs_failed_modules(self, caplog):
        """BUG-R002: Failed modules are logged with names."""
        import builtins

        # Create a mock module that raises on import
        class FailingModule:
            def __getattr__(self, name):
                raise ImportError("Module load error")

        # Patch import for one module
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "berb.reasoning.bayesian":
                raise ImportError("Bayesian module unavailable")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, '__import__', side_effect=mock_import):
            auto_register_all()

        # Should log which module failed
        assert "bayesian" in caplog.text
        assert "Failed to register" in caplog.text

    def test_auto_register_partial_success(self, caplog):
        """BUG-R002: Partial registration succeeds with warning."""
        # Clear registry
        ReasonerRegistry._registry.clear()

        # Mock all imports to fail except one
        call_count = [0]

        def selective_import(name, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First import succeeds
                return __import__(name, *args, **kwargs)
            else:
                raise ImportError(f"Import failed for {name}")

        import builtins
        with patch.object(builtins, '__import__', side_effect=selective_import):
            auto_register_all()

        # Should have warning about partial failure
        assert "complete with errors" in caplog.text.lower() or "registered" in caplog.text.lower()


# =============================================================================
# BUG-R003: Timezone Normalization Tests
# =============================================================================

class TestTimezoneNormalization:
    """Test BUG-R003 fix: Timezone normalization in ReasoningContext.from_dict()."""

    def test_from_dict_with_timezone_aware_datetime(self):
        """BUG-R003: Preserves timezone-aware datetime."""
        data = {
            "stage_id": "TEST",
            "stage_name": "Test Stage",
            "created_at": "2026-03-29T12:00:00+00:00",
        }

        ctx = ReasoningContext.from_dict(data)

        assert ctx.created_at.tzinfo is not None
        assert ctx.created_at.utcoffset().total_seconds() == 0  # UTC

    def test_from_dict_with_naive_datetime(self):
        """BUG-R003: Converts naive datetime to UTC."""
        data = {
            "stage_id": "TEST",
            "stage_name": "Test Stage",
            "created_at": "2026-03-29T12:00:00",  # No timezone
        }

        ctx = ReasoningContext.from_dict(data)

        assert ctx.created_at.tzinfo is not None
        assert ctx.created_at.tzinfo == timezone.utc
        assert ctx.created_at.hour == 12  # Preserves time

    def test_from_dict_with_different_timezone(self):
        """BUG-R003: Converts non-UTC timezone to UTC."""
        data = {
            "stage_id": "TEST",
            "stage_name": "Test Stage",
            "created_at": "2026-03-29T14:00:00+02:00",  # UTC+2
        }

        ctx = ReasoningContext.from_dict(data)

        assert ctx.created_at.tzinfo is not None
        assert ctx.created_at.utcoffset().total_seconds() == 0  # Converted to UTC
        assert ctx.created_at.hour == 12  # 14:00 UTC+2 = 12:00 UTC

    def test_from_dict_with_none_created_at(self):
        """BUG-R003: Uses current time when created_at is None."""
        data = {
            "stage_id": "TEST",
            "stage_name": "Test Stage",
            "created_at": None,
        }

        ctx = ReasoningContext.from_dict(data)

        assert ctx.created_at.tzinfo is not None
        assert ctx.created_at.tzinfo == timezone.utc

    def test_from_dict_with_missing_created_at(self):
        """BUG-R003: Uses current time when created_at is missing."""
        data = {
            "stage_id": "TEST",
            "stage_name": "Test Stage",
        }

        ctx = ReasoningContext.from_dict(data)

        assert ctx.created_at.tzinfo is not None
        assert ctx.created_at.tzinfo == timezone.utc

    def test_from_dict_with_invalid_format(self, caplog):
        """BUG-R003: Handles invalid datetime format gracefully."""
        data = {
            "stage_id": "TEST",
            "stage_name": "Test Stage",
            "created_at": "not-a-date",
        }

        ctx = ReasoningContext.from_dict(data)

        # Should use current time as fallback
        assert ctx.created_at.tzinfo is not None
        assert "Invalid datetime format" in caplog.text

    def test_from_dict_with_malformed_iso_string(self, caplog):
        """BUG-R003: Handles malformed ISO string."""
        data = {
            "stage_id": "TEST",
            "stage_name": "Test Stage",
            "created_at": "2026-13-45T99:99:99",  # Invalid date/time
        }

        ctx = ReasoningContext.from_dict(data)

        # Should use current time as fallback
        assert ctx.created_at.tzinfo is not None
        assert "Invalid datetime format" in caplog.text

    def test_parse_datetime_static_method(self):
        """Test _parse_datetime helper directly."""
        # Test with None
        dt = ReasoningContext._parse_datetime(None)
        assert dt.tzinfo == timezone.utc

        # Test with naive datetime string
        dt = ReasoningContext._parse_datetime("2026-03-29T12:00:00")
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 12

        # Test with timezone-aware string
        dt = ReasoningContext._parse_datetime("2026-03-29T12:00:00+05:00")
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 7  # Converted from UTC+5 to UTC


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for all bug fixes."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Clear state before and after each test."""
        ReasonerRegistry._registry.clear()
        ReasonerRegistry.clear_singletons()
        ReasonerRegistry._init_lock = None
        if hasattr(ReasonerRegistry, '_sync_init_lock'):
            ReasonerRegistry._sync_init_lock = None
        yield
        ReasonerRegistry._registry.clear()

    @pytest.mark.asyncio
    async def test_full_workflow_with_fixes(self):
        """Integration test: Full workflow with all fixes applied."""
        # 1. Initialize registry (BUG-R001)
        await ReasonerRegistry.initialize()

        # 2. Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

            async def execute(self, context):
                return {"result": "success"}

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # 3. Get singleton (BUG-R001)
        reasoner1 = await ReasonerRegistry.get_async("bayesian", llm_client=None)
        reasoner2 = await ReasonerRegistry.get_async("bayesian", llm_client=None)
        assert reasoner1 is reasoner2

        # 4. Create context with timezone (BUG-R003)
        ctx = ReasoningContext(
            stage_id="TEST",
            stage_name="Test",
            input_data={"key": "value"},
        )
        assert ctx.created_at.tzinfo == timezone.utc

        # 5. Serialize and deserialize context (BUG-R003)
        ctx_dict = ctx.to_dict()
        ctx_restored = ReasoningContext.from_dict(ctx_dict)
        assert ctx_restored.created_at.tzinfo == timezone.utc

    def test_error_recovery_workflow(self):
        """Integration test: Error recovery with BUG-R002 fix."""
        # Clear registry
        ReasonerRegistry._registry.clear()

        # Manually register one method
        class MockReasoner:
            pass

        ReasonerRegistry.register(MethodType.MULTI_PERSPECTIVE, MockReasoner)

        # Verify it's registered
        assert ReasonerRegistry.is_registered("multi_perspective")
        assert not ReasonerRegistry.is_registered("unknown_method")


# =============================================================================
# BUG-NEW-001: Sync/Async Mixing Warning Tests
# =============================================================================

class TestSyncAsyncMixingWarning:
    """Test BUG-NEW-001 fix: Runtime warning for sync/async mixing."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Clear singletons before and after each test."""
        ReasonerRegistry.clear_singletons()
        ReasonerRegistry._init_lock = None
        if hasattr(ReasonerRegistry, '_sync_init_lock'):
            ReasonerRegistry._sync_init_lock = None
        yield
        ReasonerRegistry.clear_singletons()

    @pytest.mark.asyncio
    async def test_warning_when_sync_call_from_async_context(self, caplog):
        """BUG-NEW-001: Warning logged when get() called from async context."""
        # Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # Call sync get() from async context - should warn
        import logging
        with caplog.at_level(logging.WARNING):
            result = get_reasoner("bayesian", llm_client=None)

        # Should have warning about async context
        assert "async context" in caplog.text.lower() or "get_async" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_no_warning_for_async_call(self, caplog):
        """BUG-NEW-001: No warning when get_async() called from async context."""
        # Register a mock reasoner
        class MockReasoner:
            def __init__(self, **kwargs):
                pass

        ReasonerRegistry.register(MethodType.BAYESIAN, MockReasoner)

        # Call async get_async() - should NOT warn
        import logging
        with caplog.at_level(logging.WARNING):
            result = await ReasonerRegistry.get_async("bayesian", llm_client=None)

        # Should NOT have warning
        assert "async context" not in caplog.text.lower()


# =============================================================================
# BUG-NEW-002: Idempotency Tests
# =============================================================================

class TestAutoRegisterIdempotency:
    """Test BUG-NEW-002 fix: Idempotency of auto_register_all()."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Clear state before and after each test."""
        ReasonerRegistry._registry.clear()
        ReasonerRegistry.clear_singletons()
        # Remove idempotency flag if exists
        if hasattr(auto_register_all, '_called'):
            delattr(auto_register_all, '_called')
        yield
        ReasonerRegistry._registry.clear()
        if hasattr(auto_register_all, '_called'):
            delattr(auto_register_all, '_called')

    def test_auto_register_idempotent(self, caplog):
        """BUG-NEW-002: Second call to auto_register_all() is skipped."""
        import logging

        # First call - should register
        with caplog.at_level(logging.DEBUG):
            auto_register_all()

        # Second call - should skip with debug message
        with caplog.at_level(logging.DEBUG):
            auto_register_all()

        # Should have idempotency message
        assert "already called" in caplog.text.lower() or "skipping" in caplog.text.lower()

    def test_auto_register_after_clear(self, caplog):
        """BUG-NEW-002: Can re-register after clear_singletons()."""
        import logging

        # First registration
        auto_register_all()
        count_after_first = len(ReasonerRegistry.list_available())

        # Clear (should reset flag)
        ReasonerRegistry.clear_singletons()

        # Clear registry manually
        ReasonerRegistry._registry.clear()

        # Second registration - should work because flag was reset
        auto_register_all()
        count_after_second = len(ReasonerRegistry.list_available())

        # Should have re-registered
        assert count_after_second > 0


# =============================================================================
# BUG-NEW-003: Fallback Datetime Parsing Tests
# =============================================================================

class TestFallbackDatetimeParsing:
    """Test BUG-NEW-003 fix: Fallback datetime format parsing."""

    def test_parse_space_separator_naive(self):
        """BUG-NEW-003: Parses '2026-03-29 12:00:00' format."""
        dt = ReasoningContext._parse_datetime("2026-03-29 12:00:00")

        assert dt.tzinfo == timezone.utc
        assert dt.hour == 12
        assert dt.minute == 0

    def test_parse_space_separator_with_tz(self):
        """BUG-NEW-003: Parses '2026-03-29 12:00:00+05:30' format."""
        dt = ReasoningContext._parse_datetime("2026-03-29 12:00:00+05:30")

        assert dt.tzinfo == timezone.utc
        # 12:00 UTC+5:30 = 06:30 UTC
        assert dt.hour == 6
        assert dt.minute == 30

    def test_parse_iso_with_tz(self):
        """BUG-NEW-003: Still parses standard ISO format correctly."""
        dt = ReasoningContext._parse_datetime("2026-03-29T12:00:00+00:00")

        assert dt.tzinfo == timezone.utc
        assert dt.hour == 12

    def test_parse_invalid_format(self, caplog):
        """BUG-NEW-003: Invalid format falls back to current time with warning."""
        import logging

        with caplog.at_level(logging.WARNING):
            dt = ReasoningContext._parse_datetime("not-a-date-at-all")

        # Should return current time (within reason)
        assert dt.tzinfo == timezone.utc
        assert "unable to parse" in caplog.text.lower() or "invalid" in caplog.text.lower()

    def test_from_dict_with_space_separator(self):
        """BUG-NEW-003: from_dict handles space-separated datetime."""
        data = {
            "stage_id": "TEST",
            "stage_name": "Test Stage",
            "created_at": "2026-03-29 12:00:00",
        }

        ctx = ReasoningContext.from_dict(data)

        assert ctx.created_at.tzinfo == timezone.utc
        assert ctx.created_at.hour == 12
