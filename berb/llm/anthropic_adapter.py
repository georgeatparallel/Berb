"""Anthropic Messages API adapter for Berb."""

from __future__ import annotations

import logging
import urllib.error
from typing import Any

from berb.llm.vision import content_to_text, to_anthropic_content

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)

_JSON_MODE_INSTRUCTION = (
    "You MUST respond with valid JSON only. Do not include any text outside the JSON object."
)

# Map Anthropic stop_reason → OpenAI finish_reason
_STOP_REASON_MAP = {
    "end_turn": "stop",
    "max_tokens": "length",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
}


def _as_blocks(content: Any) -> list[dict[str, Any]]:
    """Coerce message content to a list of Anthropic content blocks."""
    if isinstance(content, list):
        return list(content)
    return [{"type": "text", "text": str(content)}]


def _merge_content(first: Any, second: Any) -> Any:
    """Join two same-role message contents, preserving any image blocks."""
    if isinstance(first, str) and isinstance(second, str):
        return first + "\n\n" + second
    return _as_blocks(first) + _as_blocks(second)


class AnthropicAdapter:
    """Adapter to call Anthropic Messages API and return OpenAI-compatible response."""

    def __init__(self, base_url: str, api_key: str, timeout_sec: int = 300):
        if not HAS_HTTPX:
            raise ImportError("httpx is required for Anthropic adapter. Install: pip install httpx")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self._client: httpx.Client | None = None

    def close(self) -> None:
        """BUG-DA8-09: Close the httpx connection pool to prevent fd leaks."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    @staticmethod
    def _build_message_body(
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
        json_mode: bool = False,
        *,
        cached_prefix: str | None = None,
        cache_ttl: str = "5m",
    ) -> dict[str, Any]:
        """Build an Anthropic Messages API request body.

        Pure/no I/O — shared by the single-call path (`chat_completion`)
        and batch submission (`submit_batch`), so both apply identical
        message-merging, cache_control, and json_mode semantics.
        """
        # Extract and concatenate all system messages. Anthropic's `system`
        # is text-only, so an image in a system message is dropped by
        # content_to_text rather than silently corrupting the body.
        system_parts: list[str] = []
        user_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(content_to_text(msg["content"]))
            else:
                user_messages.append({**msg, "content": to_anthropic_content(msg["content"])})

        system_msg = "\n\n".join(system_parts) if system_parts else None

        # Merge consecutive messages with the same role (Anthropic
        # requires strict user/assistant alternation). Block lists concatenate
        # as lists; a string joined to a block list is promoted to a text block
        # so an image is never flattened away by the merge.
        merged: list[dict[str, Any]] = []
        for msg in user_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1] = {
                    "role": msg["role"],
                    "content": _merge_content(merged[-1]["content"], msg["content"]),
                }
            else:
                merged.append(dict(msg))
        user_messages = merged

        # Ensure at least one user message and that it starts with "user"
        if not user_messages:
            user_messages = [{"role": "user", "content": "Hello."}]
        elif user_messages[0]["role"] != "user":
            user_messages.insert(0, {"role": "user", "content": "Continue."})

        # Prepend JSON instruction when json_mode is requested
        if json_mode:
            system_msg = (
                f"{_JSON_MODE_INSTRUCTION}\n\n{system_msg}"
                if system_msg
                else _JSON_MODE_INSTRUCTION
            )

        # BUG-DA8-05: Thinking-enabled Claude models require temperature=1.0
        # and do not accept other temperature values.
        _THINKING_MODELS = ("claude-3-7", "claude-4")
        _is_thinking = any(model.startswith(p) for p in _THINKING_MODELS)
        if _is_thinking:
            temperature = 1.0

        # Build Anthropic request
        body: dict[str, Any] = {
            "model": model,
            "messages": user_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if cached_prefix:
            from berb.llm.prompt_cache import build_cached_system_blocks

            blocks = build_cached_system_blocks(cached_prefix, system_msg, ttl=cache_ttl)
            body["system"] = (
                blocks
                if blocks is not None
                else cached_prefix + ("\n\n" + system_msg if system_msg else "")
            )
        elif system_msg:
            body["system"] = system_msg

        return body

    @staticmethod
    def _parse_message_response(data: dict[str, Any], model: str, url: str = "") -> dict[str, Any]:
        """Convert a raw Anthropic Messages API response into the
        OpenAI-compatible shape the rest of Berb expects.

        Pure/no I/O — shared by the single-call path and batch result
        fetching. Raises urllib.error.HTTPError on an API-level error
        response so callers can handle it the same way as a transport error.
        """
        if data.get("type") == "error" or "error" in data:
            error_info = data.get("error", {})
            raise urllib.error.HTTPError(
                url,
                500,
                f"{error_info.get('type', 'api_error')}: {error_info.get('message', str(data))}",
                {},
                None,
            )

        # Extract ALL text content blocks (not just the first)
        content = ""
        if "content" in data and data["content"]:
            text_parts = [
                block.get("text", "") for block in data["content"] if block.get("type") == "text"
            ]
            content = "\n".join(text_parts)

        # Map Anthropic stop_reason to OpenAI finish_reason
        raw_stop_reason = data.get("stop_reason", "end_turn")
        finish_reason = _STOP_REASON_MAP.get(raw_stop_reason, "stop")

        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (
                    data.get("usage", {}).get("input_tokens", 0)
                    + data.get("usage", {}).get("output_tokens", 0)
                ),
                # Pre-normalized (Anthropic uses cache_read_input_tokens, not
                # OpenAI's prompt_tokens_details.cached_tokens) — see
                # LLMClient._parse_chat_completions_response.
                "cached_tokens": data.get("usage", {}).get("cache_read_input_tokens", 0),
            },
            "model": data.get("model", model),
        }

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout_sec)
        return self._client

    def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
        json_mode: bool = False,
        *,
        cached_prefix: str | None = None,
        cache_ttl: str = "5m",
    ) -> dict[str, Any]:
        """Call Anthropic Messages API and return OpenAI-compatible response.

        Raises urllib.error.HTTPError on API errors so the upstream retry
        logic in LLMClient._call_with_retry works unchanged.
        """
        body = self._build_message_body(
            model,
            messages,
            max_tokens,
            temperature,
            json_mode,
            cached_prefix=cached_prefix,
            cache_ttl=cache_ttl,
        )
        url = f"{self.base_url}/v1/messages"

        try:
            response = self._ensure_client().post(url, headers=self._headers(), json=body)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            # Convert to urllib.error.HTTPError for upstream retry logic.
            # Include Anthropic's error body so upstream logs show the
            # actual reason (e.g. "Prefilling not supported").
            detail = ""
            try:
                detail = exc.response.text[:500]
            except Exception:  # noqa: BLE001
                pass
            msg = f"{exc}: {detail}" if detail else str(exc)
            raise urllib.error.HTTPError(
                url,
                exc.response.status_code,
                msg,
                dict(exc.response.headers),
                None,
            ) from exc
        except httpx.HTTPError as exc:
            # Catch all transport errors (ConnectError, TimeoutException,
            # ReadError, RemoteProtocolError, PoolTimeout, etc.)
            raise urllib.error.URLError(str(exc)) from exc

        return self._parse_message_response(data, model, url)

    def submit_batch(self, requests: list[dict[str, Any]]) -> str:
        """Submit a Message Batch (50% discount, <=24h SLA, typically <1h
        for small batches). Each request dict needs: custom_id, model,
        messages, max_tokens, temperature, and optionally json_mode,
        cached_prefix, cache_ttl — same shape as chat_completion's params.

        Returns the batch id. Raises urllib.error.HTTPError/URLError on
        failure, same conventions as chat_completion.
        """
        batch_requests = [
            {
                "custom_id": req["custom_id"],
                "params": self._build_message_body(
                    req["model"],
                    req["messages"],
                    req["max_tokens"],
                    req["temperature"],
                    req.get("json_mode", False),
                    cached_prefix=req.get("cached_prefix"),
                    cache_ttl=req.get("cache_ttl", "5m"),
                ),
            }
            for req in requests
        ]
        url = f"{self.base_url}/v1/messages/batches"
        try:
            response = self._ensure_client().post(
                url, headers=self._headers(), json={"requests": batch_requests}
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:500]
            except Exception:  # noqa: BLE001
                pass
            raise urllib.error.HTTPError(
                url,
                exc.response.status_code,
                f"{exc}: {detail}" if detail else str(exc),
                dict(exc.response.headers),
                None,
            ) from exc
        except httpx.HTTPError as exc:
            raise urllib.error.URLError(str(exc)) from exc
        return data["id"]

    def get_batch_status(self, batch_id: str) -> dict[str, Any]:
        """GET the current status of a Message Batch.

        Returns the raw Anthropic batch object — notably
        `processing_status` ("in_progress" | "canceling" | "ended") and,
        once ended, `results_url`.
        """
        url = f"{self.base_url}/v1/messages/batches/{batch_id}"
        try:
            response = self._ensure_client().get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:500]
            except Exception:  # noqa: BLE001
                pass
            raise urllib.error.HTTPError(
                url,
                exc.response.status_code,
                f"{exc}: {detail}" if detail else str(exc),
                dict(exc.response.headers),
                None,
            ) from exc
        except httpx.HTTPError as exc:
            raise urllib.error.URLError(str(exc)) from exc

    def fetch_batch_results(self, results_url: str) -> dict[str, dict[str, Any]]:
        """Fetch and parse a Message Batch's JSONL results.

        Returns {custom_id: <OpenAI-compatible response dict>} for
        succeeded entries. Entries that errored or expired are logged and
        omitted — callers should treat a missing custom_id as "unavailable"
        (same convention chat_completion's callers already use for a
        failed single call).
        """
        import json as _json

        try:
            response = self._ensure_client().get(results_url, headers=self._headers())
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:500]
            except Exception:  # noqa: BLE001
                pass
            raise urllib.error.HTTPError(
                results_url,
                exc.response.status_code,
                f"{exc}: {detail}" if detail else str(exc),
                dict(exc.response.headers),
                None,
            ) from exc
        except httpx.HTTPError as exc:
            raise urllib.error.URLError(str(exc)) from exc

        results: dict[str, dict[str, Any]] = {}
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            entry = _json.loads(line)
            custom_id = entry.get("custom_id", "")
            result = entry.get("result", {})
            if result.get("type") != "succeeded":
                logger.warning("Batch entry %s did not succeed: %s", custom_id, result.get("type"))
                continue
            message = result.get("message", {})
            try:
                results[custom_id] = self._parse_message_response(message, message.get("model", ""))
            except urllib.error.HTTPError as exc:
                logger.warning("Batch entry %s returned an error payload: %s", custom_id, exc)
        return results
