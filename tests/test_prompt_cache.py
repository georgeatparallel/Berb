"""Unit tests for provider-side prompt caching."""

import pytest

from berb.llm.prompt_cache import (
    build_cached_system_blocks,
    model_needs_explicit_cache_control,
)


class TestModelNeedsExplicitCacheControl:
    """Test provider-caching model gating."""

    @pytest.mark.parametrize(
        "model",
        ["anthropic/claude-sonnet-4.5", "claude-3-7-sonnet", "qwen/qwen-2.5-72b"],
    )
    def test_explicit_cache_models(self, model):
        assert model_needs_explicit_cache_control(model) is True

    @pytest.mark.parametrize(
        "model",
        [
            "openai/gpt-4o",
            "deepseek/deepseek-v3",
            "x-ai/grok-4",
            "google/gemini-2.5-pro",
        ],
    )
    def test_automatic_cache_models(self, model):
        assert model_needs_explicit_cache_control(model) is False


class TestBuildCachedSystemBlocks:
    """Test provider cache_control block construction."""

    def test_builds_breakpoint_on_prefix_and_appends_system(self):
        prefix = "x" * 5000
        blocks = build_cached_system_blocks(prefix, "You are a reviewer.")

        assert blocks is not None
        assert blocks[0]["text"] == prefix
        assert blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
        assert blocks[1] == {"type": "text", "text": "You are a reviewer."}

    def test_omits_system_block_when_none(self):
        blocks = build_cached_system_blocks("x" * 5000, None)

        assert blocks is not None
        assert len(blocks) == 1

    def test_returns_none_below_min_chars(self):
        blocks = build_cached_system_blocks("short", "system", min_chars=4000)

        assert blocks is None

    def test_custom_ttl(self):
        blocks = build_cached_system_blocks("x" * 5000, None, ttl="1h")

        assert blocks[0]["cache_control"]["ttl"] == "1h"

    def test_rejects_invalid_ttl(self):
        with pytest.raises(ValueError):
            build_cached_system_blocks("x" * 5000, None, ttl="1d")
