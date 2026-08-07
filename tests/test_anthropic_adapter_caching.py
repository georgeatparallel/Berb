"""Unit tests for AnthropicAdapter's cached_prefix wiring (tasks/todo.md #2).

No network calls — inspects the request body AnthropicAdapter would send,
by patching httpx.Client.post to capture kwargs and return a canned
response.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from berb.llm.anthropic_adapter import AnthropicAdapter

_CANNED_RESPONSE = {
    "type": "message",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "model": "claude-sonnet-4-5",
    "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 7},
}


def _mock_post():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = _CANNED_RESPONSE
    return MagicMock(return_value=resp)


class TestAnthropicAdapterCaching:
    def test_cached_prefix_builds_system_blocks(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        mock_post = _mock_post()
        with patch("httpx.Client.post", mock_post):
            adapter.chat_completion(
                "claude-sonnet-4-5",
                [{"role": "user", "content": "review"}],
                max_tokens=100,
                temperature=0.5,
                cached_prefix="x" * 5000,
                cache_ttl="1h",
            )

        body = mock_post.call_args.kwargs["json"]
        assert isinstance(body["system"], list)
        assert body["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    def test_cached_prefix_below_min_falls_back_to_string(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        mock_post = _mock_post()
        with patch("httpx.Client.post", mock_post):
            adapter.chat_completion(
                "claude-sonnet-4-5",
                [{"role": "user", "content": "review"}],
                max_tokens=100,
                temperature=0.5,
                cached_prefix="short",
            )

        body = mock_post.call_args.kwargs["json"]
        assert isinstance(body["system"], str)
        assert body["system"] == "short"

    def test_no_cached_prefix_leaves_system_untouched(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        mock_post = _mock_post()
        with patch("httpx.Client.post", mock_post):
            adapter.chat_completion(
                "claude-sonnet-4-5",
                [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "hi"},
                ],
                max_tokens=100,
                temperature=0.5,
            )

        body = mock_post.call_args.kwargs["json"]
        assert body["system"] == "You are helpful."

    def test_response_normalizes_cache_read_tokens(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        mock_post = _mock_post()
        with patch("httpx.Client.post", mock_post):
            result = adapter.chat_completion(
                "claude-sonnet-4-5",
                [{"role": "user", "content": "review"}],
                max_tokens=100,
                temperature=0.5,
                cached_prefix="x" * 5000,
            )

        assert result["usage"]["cached_tokens"] == 7
