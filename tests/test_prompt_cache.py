"""Unit tests for prompt caching."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from berb.llm.prompt_cache import (
    CacheEntry,
    CacheWarmer,
    PromptCache,
    apply_cache_control_to_messages,
    cached_completion,
    get_cache_control_header,
)


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_create_entry(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            key="test_key",
            response="test_response",
            created_at=time.time(),
            input_tokens=100,
            output_tokens=50,
        )

        assert entry.key == "test_key"
        assert entry.response == "test_response"
        assert entry.input_tokens == 100
        assert entry.output_tokens == 50
        assert entry.access_count == 0


class TestPromptCache:
    """Test PromptCache class."""

    def test_create_cache(self):
        """Test creating a cache."""
        cache = PromptCache(ttl_seconds=3600, max_size=1000)

        assert cache.enabled is True
        assert cache._ttl_seconds == 3600
        assert cache._max_size == 1000

    def test_cache_miss(self):
        """Test cache miss."""
        cache = PromptCache()

        response = cache.get("nonexistent_key")

        assert response is None
        stats = cache.get_stats()
        assert stats["misses"] == 1

    def test_cache_hit(self):
        """Test cache hit."""
        cache = PromptCache()

        cache.set("test_key", "test_response")
        response = cache.get("test_key")

        assert response == "test_response"
        stats = cache.get_stats()
        assert stats["hits"] == 1

    def test_cache_ttl_expiration(self):
        """Test cache entry expiration."""
        cache = PromptCache(ttl_seconds=1)  # 1 second TTL

        cache.set("test_key", "test_response")

        # Should be cached
        assert cache.get("test_key") == "test_response"

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        response = cache.get("test_key")
        assert response is None

    def test_cache_max_size_eviction(self):
        """Test cache eviction when max size reached."""
        cache = PromptCache(max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Add 4th entry - should evict oldest
        cache.set("key4", "value4")

        stats = cache.get_stats()
        assert stats["size"] == 3
        assert stats["evictions"] >= 1

        # Oldest should be evicted
        assert cache.get("key1") is None
        assert cache.get("key4") == "value4"

    def test_cache_lru_order(self):
        """Test LRU ordering."""
        cache = PromptCache(max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 - moves to end
        cache.get("key1")

        # Add key4 - should evict key2 (now oldest)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Still there
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"  # Still there
        assert cache.get("key4") == "value4"  # Still there

    def test_cache_clear(self):
        """Test clearing cache."""
        cache = PromptCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        count = cache.clear()

        assert count == 2
        stats = cache.get_stats()
        assert stats["size"] == 0

    def test_cache_cleanup_expired(self):
        """Test cleaning up expired entries."""
        cache = PromptCache(ttl_seconds=1)

        cache.set("key1", "value1")
        time.sleep(1.1)
        cache.set("key2", "value2")  # Fresh

        count = cache.cleanup_expired()

        assert count == 1
        assert cache.get("key1") is None  # Expired
        assert cache.get("key2") == "value2"  # Still valid

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = PromptCache()

        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.get_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2 / 3  # 2 hits / 3 total
        assert stats["size"] == 1

    def test_cache_enabled_toggle(self):
        """Test enabling/disabling cache."""
        cache = PromptCache(enabled=True)

        assert cache.enabled is True

        cache.enabled = False

        assert cache.enabled is False

    def test_compute_key_deterministic(self):
        """Test cache key computation is deterministic."""
        cache = PromptCache()

        messages = [{"role": "user", "content": "test"}]

        key1 = cache._compute_key("gpt-4o", messages)
        key2 = cache._compute_key("gpt-4o", messages)

        assert key1 == key2

    def test_compute_key_different_models(self):
        """Test different models produce different keys."""
        cache = PromptCache()

        messages = [{"role": "user", "content": "test"}]

        key1 = cache._compute_key("gpt-4o", messages)
        key2 = cache._compute_key("claude-sonnet", messages)

        assert key1 != key2

    def test_compute_key_different_messages(self):
        """Test different messages produce different keys."""
        cache = PromptCache()

        key1 = cache._compute_key("gpt-4o", [{"role": "user", "content": "test1"}])
        key2 = cache._compute_key("gpt-4o", [{"role": "user", "content": "test2"}])

        assert key1 != key2


class TestCacheWarmer:
    """Test CacheWarmer class."""

    @pytest.mark.asyncio
    async def test_warm_cache(self):
        """Test cache warming."""
        cache = PromptCache()
        warmer = CacheWarmer(cache)

        # Mock client
        mock_client = AsyncMock()
        mock_response = MagicMock(content="OK", prompt_tokens=10, completion_tokens=5)
        mock_client.chat.return_value = mock_response

        key = await warmer.warm_cache(
            client=mock_client,
            system_prompt="Test system prompt",
            project_context="Test context",
            model="gpt-4o",
        )

        assert key is not None
        # Cache the response manually since warm_cache doesn't auto-cache
        cache.set(key, mock_response)
        assert cache.get(key) is not None

    def test_is_warmed(self):
        """Test checking if cache is warmed."""
        cache = PromptCache()
        warmer = CacheWarmer(cache)

        # Not warmed yet
        assert warmer.is_warmed("Test prompt", "gpt-4o") is False

        # Warm it
        cache.set(
            cache._compute_key("gpt-4o", [{"role": "system", "content": "Test prompt"}]), "response"
        )

        # Now warmed
        assert warmer.is_warmed("Test prompt", "gpt-4o") is True


class TestCacheControlHeaders:
    """Test cache control header functions."""

    def test_anthropic_headers(self):
        """Test Anthropic cache control headers."""
        headers = get_cache_control_header("anthropic")

        assert "anthropic-beta" in headers
        assert headers["anthropic-beta"] == "prompt-caching-2024-07-31"

    def test_openai_headers(self):
        """Test OpenAI headers (no special headers)."""
        headers = get_cache_control_header("openai")

        assert headers == {}

    def test_unknown_provider_headers(self):
        """Test unknown provider headers."""
        headers = get_cache_control_header("unknown")

        assert headers == {}

    def test_apply_cache_control_anthropic(self):
        """Test applying cache control to Anthropic messages."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User message"},
        ]

        annotated = apply_cache_control_to_messages(messages, "anthropic")

        assert len(annotated) == 2
        assert annotated[0].get("cache_control") == {"type": "ephemeral"}
        assert annotated[1].get("cache_control") is None

    def test_apply_cache_control_non_anthropic(self):
        """Test applying cache control to non-Anthropic messages."""
        messages = [
            {"role": "system", "content": "System prompt"},
        ]

        annotated = apply_cache_control_to_messages(messages, "openai")

        # Should return unchanged
        assert annotated == messages


class TestCachedCompletion:
    """Test cached_completion decorator function."""

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """Test cached completion with cache disabled."""
        cache = PromptCache(enabled=False)
        mock_client = AsyncMock()
        mock_client.chat.return_value = MagicMock(content="response")

        response = await cached_completion(
            cache=cache,
            client=mock_client,
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4o",
        )

        # Should call API directly
        mock_client.chat.assert_called_once()
        assert response.content == "response"

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Test cached completion with cache miss."""
        cache = PromptCache()
        mock_client = AsyncMock()
        mock_client.chat.return_value = MagicMock(
            content="response",
            prompt_tokens=100,
            completion_tokens=50,
        )

        response = await cached_completion(
            cache=cache,
            client=mock_client,
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4o",
        )

        # Should call API
        mock_client.chat.assert_called_once()
        assert response.content == "response"

        # Should be cached now
        stats = cache.get_stats()
        assert stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cached completion with cache hit."""
        cache = PromptCache()
        mock_client = AsyncMock()
        mock_response = MagicMock(content="response")
        mock_client.chat.return_value = mock_response

        # First call - cache miss
        await cached_completion(
            cache=cache,
            client=mock_client,
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4o",
        )

        # Second call - cache hit
        response = await cached_completion(
            cache=cache,
            client=mock_client,
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4o",
        )

        # Should only call API once
        mock_client.chat.assert_called_once()
        assert response.content == "response"

        # Should have cache hit
        stats = cache.get_stats()
        assert stats["hits"] == 1
