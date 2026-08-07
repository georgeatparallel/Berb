"""Prompt caching helpers for LLM calls.

Two independent mechanisms live here:

1. Provider-side caching (`model_needs_explicit_cache_control`,
   `build_cached_system_blocks`) — builds Anthropic-style `cache_control`
   breakpoints so a stable, reused prefix (e.g. a paper shared across a
   5-persona review round) is billed at ~0.1x on repeat reads instead of
   full input price. Wired into `LLMClient.chat(cached_prefix=...)` and
   `AnthropicAdapter.chat_completion(cached_prefix=...)`.
2. Local response cache (`PromptCache`, `CacheWarmer`, `cached_completion`)
   — an in-process LRU that memoizes exact-repeat calls (same model +
   messages) end to end. Separate from provider caching: it only helps on
   byte-identical repeats (e.g. retries), not on shared-prefix reuse. Not
   currently wired into any call site.

Usage:
    from berb.llm.prompt_cache import PromptCache, cached_completion

    cache = PromptCache(ttl_seconds=3600, max_size=1000)

    # Cache a completion
    response = await cached_completion(
        cache=cache,
        client=llm_client,
        messages=messages,
        model="claude-sonnet",
    )
"""

# Author: Georgios-Chrysovalantis Chatzivantsidis

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Represents a cached completion."""

    key: str
    response: Any
    created_at: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    input_tokens: int = 0
    output_tokens: int = 0


class PromptCache:
    """LRU cache for LLM completions with TTL support."""

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_size: int = 1000,
        enabled: bool = True,
    ):
        """Initialize prompt cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 1 hour)
            max_size: Maximum number of entries (default: 1000)
            enabled: Enable/disable cache (default: True)
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._enabled = enabled

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    @property
    def enabled(self) -> bool:
        """Check if cache is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable cache."""
        self._enabled = value

    def _compute_key(self, model: str, messages: list[dict], **kwargs) -> str:
        """Compute cache key from inputs.

        Args:
            model: Model name
            messages: List of message dicts
            **kwargs: Additional parameters

        Returns:
            SHA256 hash of inputs
        """
        # Create deterministic string representation
        key_parts = [
            f"model:{model}",
            f"messages:{str(messages)}",
        ]

        for key, value in sorted(kwargs.items()):
            key_parts.append(f"{key}:{value}")

        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Get cached response by key.

        Args:
            key: Cache key

        Returns:
            Cached response or None if not found/expired
        """
        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]

        # Check TTL
        if time.time() - entry.created_at > self._ttl_seconds:
            self._remove(key)
            self._misses += 1
            logger.debug(f"Cache entry expired: {key[:16]}")
            return None

        # Update access info
        entry.access_count += 1
        entry.last_accessed = time.time()

        # Move to end (most recently used)
        self._cache.move_to_end(key)

        self._hits += 1
        logger.debug(f"Cache hit: {key[:16]} (access #{entry.access_count})")
        return entry.response

    def set(
        self,
        key: str,
        response: Any,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Set cached response.

        Args:
            key: Cache key
            response: Response to cache
            input_tokens: Input token count
            output_tokens: Output token count
        """
        # Evict oldest if at capacity
        while len(self._cache) >= self._max_size:
            self._remove_oldest()

        entry = CacheEntry(
            key=key,
            response=response,
            created_at=time.time(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        self._cache[key] = entry
        logger.debug(f"Cache set: {key[:16]}")

    def _remove(self, key: str) -> None:
        """Remove entry by key."""
        if key in self._cache:
            del self._cache[key]
            self._evictions += 1

    def _remove_oldest(self) -> None:
        """Remove oldest (least recently used) entry."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            self._remove(oldest_key)
            logger.debug(f"Cache eviction: {oldest_key[:16]}")

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared: {count} entries removed")
        return count

    def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = []

        for key, entry in self._cache.items():
            if current_time - entry.created_at > self._ttl_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            self._remove(key)

        logger.debug(f"Cleanup: {len(expired_keys)} expired entries removed")
        return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        return {
            "enabled": self._enabled,
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "evictions": self._evictions,
            "total_tokens_saved": sum(e.input_tokens for e in self._cache.values()),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Cache Warming for Parallel Calls
# ─────────────────────────────────────────────────────────────────────────────


class CacheWarmer:
    """Warm cache before parallel LLM calls.

    This prevents cache miss storms when firing multiple parallel requests
    with the same system prompt.
    """

    def __init__(self, cache: PromptCache):
        self._cache = cache

    async def warm_cache(
        self,
        client: Any,
        system_prompt: str,
        project_context: str = "",
        model: str = "gpt-4o",
    ) -> str:
        """Warm cache with system prompt and context.

        Args:
            client: LLM client for making the warming call
            system_prompt: System prompt to cache
            project_context: Optional project context
            model: Model to use for warming

        Returns:
            Cache key for the warmed entry
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": project_context or "Acknowledge context."},
        ]

        # Make the call (will be cached)
        await client.chat(
            messages=messages,
            model=model,
            max_tokens=10,  # Minimal response for warming
        )

        logger.info(f"Cache warmed for system prompt (model={model})")
        return self._cache._compute_key(model, messages)

    def is_warmed(self, system_prompt: str, model: str) -> bool:
        """Check if cache is warmed for a system prompt.

        Args:
            system_prompt: System prompt to check
            model: Model name

        Returns:
            True if cache is warmed
        """
        messages = [{"role": "system", "content": system_prompt}]
        key = self._cache._compute_key(model, messages)
        return self._cache.get(key) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Provider-Specific Cache Control
#
# This targets Anthropic's Messages API `cache_control` mechanic (also
# honored by OpenRouter for Claude/Qwen, which route to Anthropic-shaped
# backends). It requires content as an array of blocks — a bare
# `cache_control` key alongside a string `content` field, which an earlier
# version of this module produced, is not part of any provider's wire
# format and would be silently ignored.
# ─────────────────────────────────────────────────────────────────────────────

# Per OpenRouter's prompt-caching docs: these need an explicit cache_control
# breakpoint to get provider-side caching. OpenAI, DeepSeek, Grok, Groq,
# Z.AI and Gemini 2.5 cache automatically and don't need (or use) the field.
_EXPLICIT_CACHE_MODEL_MARKERS = ("claude", "anthropic", "qwen")

_VALID_TTLS = ("5m", "1h")

# Below Sonnet's 1,024-token floor (Opus is 512, Haiku is 4,096) a cached
# block silently never caches. ~4 chars/token is a conservative estimate.
_DEFAULT_MIN_CACHEABLE_CHARS = 4000


def model_needs_explicit_cache_control(model: str) -> bool:
    """Whether `model` needs an explicit `cache_control` breakpoint to get
    provider-side prompt caching, vs. providers that cache automatically.
    """
    m = model.lower()
    return any(marker in m for marker in _EXPLICIT_CACHE_MODEL_MARKERS)


def build_cached_system_blocks(
    cached_prefix: str,
    system: str | None,
    *,
    ttl: str = "5m",
    min_chars: int = _DEFAULT_MIN_CACHEABLE_CHARS,
) -> list[dict[str, Any]] | None:
    """Build system content blocks with a cache breakpoint on `cached_prefix`.

    `cached_prefix` should be the STABLE part of the prompt (e.g. shared
    document text reused across several calls); it becomes the first block
    with a `cache_control` breakpoint. `system` (if given) is the volatile,
    call-specific part and is appended as a second, uncached block — it
    comes after the breakpoint so it never has to match for the cached
    prefix to hit.

    Returns None when `cached_prefix` is shorter than `min_chars` — too
    short to clear the provider's minimum-cacheable-tokens floor, so
    callers should fall back to plain string concatenation rather than pay
    the cache-write premium (1.25x for 5m, 2x for 1h) for a block that will
    never register a cache hit.
    """
    if ttl not in _VALID_TTLS:
        raise ValueError(f"cache ttl must be one of {_VALID_TTLS}, got {ttl!r}")
    if len(cached_prefix) < min_chars:
        return None

    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": cached_prefix,
            "cache_control": {"type": "ephemeral", "ttl": ttl},
        }
    ]
    if system:
        blocks.append({"type": "text", "text": system})
    return blocks


# ─────────────────────────────────────────────────────────────────────────────
# Decorator for Cached Completions
# ─────────────────────────────────────────────────────────────────────────────


async def cached_completion(
    cache: PromptCache,
    client: Any,
    messages: list[dict],
    model: str,
    **kwargs,
) -> Any:
    """Get completion from cache or make API call.

    Args:
        cache: PromptCache instance
        client: LLM client
        messages: List of message dicts
        model: Model name
        **kwargs: Additional parameters for client.chat

    Returns:
        LLM response
    """
    if not cache.enabled:
        return await client.chat(messages=messages, model=model, **kwargs)

    # Compute cache key
    key = cache._compute_key(model, messages, **kwargs)

    # Try cache first
    cached_response = cache.get(key)
    if cached_response is not None:
        logger.debug(f"Cache hit for {key[:16]}")
        return cached_response

    # Cache miss - make API call
    logger.debug(f"Cache miss for {key[:16]}, calling API")
    response = await client.chat(messages=messages, model=model, **kwargs)

    # Cache the response
    cache.set(
        key=key,
        response=response,
        input_tokens=getattr(response, "prompt_tokens", 0),
        output_tokens=getattr(response, "completion_tokens", 0),
    )

    return response
