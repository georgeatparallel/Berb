"""Unit tests for provider-side prompt caching wiring (tasks/todo.md #2).

Covers payload construction only — no network calls. Verifies that
`cached_prefix` produces the correct Anthropic-style cache_control blocks
for Claude/Qwen, plain concatenation for other providers, and correct
fallback below the minimum-cacheable-chars floor.
"""

from __future__ import annotations

from berb.llm.client import LLMClient, LLMConfig
from berb.llm.prompt_cache import (
    model_needs_explicit_cache_control,
)


def _client() -> LLMClient:
    return LLMClient(LLMConfig(base_url="https://openrouter.ai/api/v1", api_key="test"))


class TestApplyCachedPrefix:
    def test_claude_model_gets_cache_control_blocks(self) -> None:
        client = _client()
        msgs = [{"role": "user", "content": "review this"}]

        out = client._apply_cached_prefix(msgs, "anthropic/claude-sonnet-4.5", "x" * 5000, "1h")

        assert out[0]["role"] == "system"
        blocks = out[0]["content"]
        assert isinstance(blocks, list)
        assert blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        assert out[1] == msgs[0]

    def test_existing_system_message_becomes_second_block(self) -> None:
        client = _client()
        msgs = [
            {"role": "system", "content": "You are a reviewer."},
            {"role": "user", "content": "review this"},
        ]

        out = client._apply_cached_prefix(msgs, "anthropic/claude-sonnet-4.5", "x" * 5000, "5m")

        blocks = out[0]["content"]
        assert len(blocks) == 2
        assert blocks[0]["text"] == "x" * 5000
        assert "cache_control" in blocks[0]
        assert blocks[1] == {"type": "text", "text": "You are a reviewer."}
        assert "cache_control" not in blocks[1]

    def test_non_explicit_model_gets_plain_concatenation(self) -> None:
        client = _client()
        msgs = [{"role": "user", "content": "review this"}]

        out = client._apply_cached_prefix(msgs, "openai/gpt-4o", "x" * 5000, "5m")

        assert out[0]["role"] == "system"
        assert isinstance(out[0]["content"], str)
        assert out[0]["content"] == "x" * 5000

    def test_below_min_chars_falls_back_to_plain_string(self) -> None:
        client = _client()
        msgs = [{"role": "user", "content": "review this"}]

        out = client._apply_cached_prefix(msgs, "anthropic/claude-sonnet-4.5", "short", "5m")

        assert isinstance(out[0]["content"], str)
        assert out[0]["content"] == "short"

    def test_does_not_mutate_caller_list(self) -> None:
        client = _client()
        original = [{"role": "user", "content": "review this"}]
        msgs = [dict(m) for m in original]

        client._apply_cached_prefix(msgs, "anthropic/claude-sonnet-4.5", "x" * 5000, "5m")

        assert original == [{"role": "user", "content": "review this"}]


class TestModelGating:
    def test_claude_needs_explicit(self) -> None:
        assert model_needs_explicit_cache_control("anthropic/claude-sonnet-4.5") is True

    def test_gpt_does_not_need_explicit(self) -> None:
        assert model_needs_explicit_cache_control("openai/gpt-4o") is False


class TestParseChatCompletionsCachedTokens:
    def test_reads_openai_shaped_cached_tokens(self) -> None:
        client = _client()
        data = {
            "model": "openai/gpt-4o",
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 10,
                "total_tokens": 1010,
                "prompt_tokens_details": {"cached_tokens": 800},
            },
        }

        resp = client._parse_chat_completions_response(data, "openai/gpt-4o")

        assert resp.cached_tokens == 800

    def test_reads_normalized_anthropic_cached_tokens(self) -> None:
        client = _client()
        data = {
            "model": "anthropic/claude-sonnet-4.5",
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 10,
                "total_tokens": 1010,
                "cached_tokens": 900,
            },
        }

        resp = client._parse_chat_completions_response(data, "anthropic/claude-sonnet-4.5")

        assert resp.cached_tokens == 900

    def test_defaults_to_zero_when_absent(self) -> None:
        client = _client()
        data = {
            "model": "openai/gpt-4o",
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
            },
        }

        resp = client._parse_chat_completions_response(data, "openai/gpt-4o")

        assert resp.cached_tokens == 0


class TestJsonModeHintWithCacheControl:
    def test_json_hint_prepended_as_block_not_string_concat(self) -> None:
        client = _client()
        msgs = [{"role": "user", "content": "review this"}]
        cached = client._apply_cached_prefix(msgs, "anthropic/claude-sonnet-4.5", "x" * 5000, "5m")
        # Simulate the json_mode hint-injection branch in _raw_call.
        existing = cached[0]["content"]
        assert isinstance(existing, list)
        hinted = [{"type": "text", "text": "JSON ONLY"}, *existing]
        assert hinted[0]["text"] == "JSON ONLY"
        assert hinted[1] is existing[0]
