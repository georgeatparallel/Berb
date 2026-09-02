"""Unit tests for AnthropicAdapter's Message Batches API methods
(tasks/todo.md #5 — batch review ensemble as the first batch unit).

No network calls — patches httpx.Client.get/post to capture kwargs and
return canned responses.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from berb.llm.anthropic_adapter import AnthropicAdapter


def _mock_response(payload, text: str = ""):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    resp.text = text
    return resp


class TestSubmitBatch:
    def test_builds_one_request_per_item_with_custom_id(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        mock_post = MagicMock(return_value=_mock_response({"id": "batch_123"}))
        with patch("httpx.Client.post", mock_post):
            batch_id = adapter.submit_batch(
                [
                    {
                        "custom_id": "reviewer-1",
                        "model": "claude-sonnet-4-5",
                        "messages": [{"role": "user", "content": "review this"}],
                        "max_tokens": 100,
                        "temperature": 0.5,
                    },
                    {
                        "custom_id": "reviewer-2",
                        "model": "claude-sonnet-4-5",
                        "messages": [{"role": "user", "content": "review that"}],
                        "max_tokens": 100,
                        "temperature": 0.5,
                    },
                ]
            )

        assert batch_id == "batch_123"
        body = mock_post.call_args.kwargs["json"]
        assert [r["custom_id"] for r in body["requests"]] == [
            "reviewer-1",
            "reviewer-2",
        ]
        assert body["requests"][0]["params"]["model"] == "claude-sonnet-4-5"
        assert body["requests"][0]["params"]["messages"] == [
            {"role": "user", "content": "review this"}
        ]

    def test_applies_cached_prefix_per_request(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        mock_post = MagicMock(return_value=_mock_response({"id": "batch_456"}))
        with patch("httpx.Client.post", mock_post):
            adapter.submit_batch(
                [
                    {
                        "custom_id": "reviewer-1",
                        "model": "claude-sonnet-4-5",
                        "messages": [{"role": "user", "content": "review"}],
                        "max_tokens": 100,
                        "temperature": 0.5,
                        "cached_prefix": "x" * 5000,
                        "cache_ttl": "1h",
                    }
                ]
            )

        body = mock_post.call_args.kwargs["json"]
        system = body["requests"][0]["params"]["system"]
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    def test_raises_on_api_failure(self) -> None:
        import httpx

        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        error_resp = MagicMock()
        error_resp.status_code = 400
        error_resp.text = "bad request"
        error_resp.headers = {}
        mock_post = MagicMock(
            side_effect=httpx.HTTPStatusError("bad", request=MagicMock(), response=error_resp)
        )
        with (
            patch("httpx.Client.post", mock_post),
            pytest.raises(Exception),  # noqa: B017 - only asserting submit_batch propagates
        ):
            adapter.submit_batch(
                [
                    {
                        "custom_id": "reviewer-1",
                        "model": "claude-sonnet-4-5",
                        "messages": [{"role": "user", "content": "review"}],
                        "max_tokens": 100,
                        "temperature": 0.5,
                    }
                ]
            )


class TestGetBatchStatus:
    def test_returns_raw_status_payload(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        payload = {"id": "batch_123", "processing_status": "in_progress"}
        mock_get = MagicMock(return_value=_mock_response(payload))
        with patch("httpx.Client.get", mock_get):
            status = adapter.get_batch_status("batch_123")

        assert status["processing_status"] == "in_progress"
        assert mock_get.call_args.args[0] == (
            "https://api.anthropic.com/v1/messages/batches/batch_123"
        )


class TestFetchBatchResults:
    def test_parses_succeeded_entries_keyed_by_custom_id(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        jsonl = "\n".join(
            [
                (
                    '{"custom_id": "reviewer-1", "result": {"type": "succeeded", '
                    '"message": {"type": "message", "content": '
                    '[{"type": "text", "text": "review 1"}], "stop_reason": "end_turn", '
                    '"model": "claude-sonnet-4-5", "usage": {"input_tokens": 10, '
                    '"output_tokens": 5}}}}'
                ),
                (
                    '{"custom_id": "reviewer-2", "result": {"type": "succeeded", '
                    '"message": {"type": "message", "content": '
                    '[{"type": "text", "text": "review 2"}], "stop_reason": "end_turn", '
                    '"model": "claude-sonnet-4-5", "usage": {"input_tokens": 8, '
                    '"output_tokens": 4}}}}'
                ),
            ]
        )
        mock_get = MagicMock(return_value=_mock_response({}, text=jsonl))
        with patch("httpx.Client.get", mock_get):
            results = adapter.fetch_batch_results("https://api.anthropic.com/results/batch_123")

        assert set(results.keys()) == {"reviewer-1", "reviewer-2"}
        assert results["reviewer-1"]["choices"][0]["message"]["content"] == "review 1"
        assert results["reviewer-2"]["choices"][0]["message"]["content"] == "review 2"

    def test_skips_errored_entries(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        jsonl = (
            '{"custom_id": "reviewer-1", "result": {"type": "errored", '
            '"error": {"type": "invalid_request", "message": "bad"}}}\n'
            '{"custom_id": "reviewer-2", "result": {"type": "succeeded", '
            '"message": {"type": "message", "content": '
            '[{"type": "text", "text": "ok"}], "stop_reason": "end_turn", '
            '"model": "claude-sonnet-4-5", "usage": {"input_tokens": 1, "output_tokens": 1}}}}'
        )
        mock_get = MagicMock(return_value=_mock_response({}, text=jsonl))
        with patch("httpx.Client.get", mock_get):
            results = adapter.fetch_batch_results("https://api.anthropic.com/results/batch_123")

        assert set(results.keys()) == {"reviewer-2"}

    def test_empty_results_returns_empty_dict(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        mock_get = MagicMock(return_value=_mock_response({}, text=""))
        with patch("httpx.Client.get", mock_get):
            results = adapter.fetch_batch_results("https://api.anthropic.com/results/batch_123")

        assert results == {}


class TestChatCompletionUnchangedAfterRefactor:
    """The single-call path shares _build_message_body/_parse_message_response
    with the batch path now — verify chat_completion's behavior is unchanged."""

    def test_chat_completion_still_works(self) -> None:
        adapter = AnthropicAdapter(base_url="https://api.anthropic.com", api_key="k")
        payload = {
            "type": "message",
            "content": [{"type": "text", "text": "hello"}],
            "stop_reason": "end_turn",
            "model": "claude-sonnet-4-5",
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }
        mock_post = MagicMock(return_value=_mock_response(payload))
        with patch("httpx.Client.post", mock_post):
            result = adapter.chat_completion(
                "claude-sonnet-4-5",
                [{"role": "user", "content": "hi"}],
                max_tokens=50,
                temperature=0.3,
            )

        assert result["choices"][0]["message"]["content"] == "hello"
        assert result["usage"]["prompt_tokens"] == 3
