"""Lightweight OpenAI-compatible LLM client — stdlib only.

Features:
  - Model fallback chain (gpt-5.2 → gpt-5.1 → gpt-4.1 → gpt-4o)
  - Auto-detect max_tokens vs max_completion_tokens per model
  - Cloudflare User-Agent bypass
  - Exponential backoff retry with jitter
  - JSON mode support
  - Streaming disabled (sync only)
  - Stage-based output token limits (15-25% cost reduction)
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Models that require max_completion_tokens instead of max_tokens
_NEW_PARAM_MODELS = frozenset(
    {
        "o3",
        "o3-mini",
        "o4-mini",
        "gpt-5",
        "gpt-5.1",
        "gpt-5.2",
        "gpt-5.4",
    }
)

_NO_TEMPERATURE_MODELS = frozenset(
    {
        "o3",
        "o3-mini",
        "o4-mini",
    }
)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class LLMResponse:
    """Parsed response from the LLM API."""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""
    truncated: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    cost: float = 0.0  # BUG-001 FIX: Added cost field for OpenRouter compatibility


@dataclass
class LLMConfig:
    """Configuration for the LLM client."""

    base_url: str
    api_key: str
    wire_api: str = "chat_completions"
    primary_model: str = "gpt-4o"
    fallback_models: list[str] = field(
        default_factory=lambda: ["gpt-4.1", "gpt-4o-mini"]
    )
    max_tokens: int = 4096
    temperature: float = 0.7
    max_retries: int = 3
    retry_base_delay: float = 2.0
    timeout_sec: int = 300
    user_agent: str = _DEFAULT_USER_AGENT
    # MetaClaw bridge: extra headers for proxy requests
    extra_headers: dict[str, str] = field(default_factory=dict)
    # MetaClaw bridge: fallback URL if primary (proxy) is unreachable
    fallback_url: str = ""
    fallback_api_key: str = ""
    # SECURITY FIX #6: Rate limiting configuration
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 60  # Default: 60 requests/min
    rate_limit_tokens_per_minute: int = 90000  # Default: 90k tokens/min
    # P1 FIX: Multi-provider failover configuration
    provider_name: str = ""  # Current provider name (for logging)
    fallback_providers: list[str] = field(default_factory=list)  # Provider names for failover


class TokenBucketRateLimiter:
    """Token bucket rate limiter for LLM API calls.

    SECURITY FIX #6: Prevents quota exhaustion from runaway pipelines.

    Uses two buckets:
    - Request bucket: Limits number of API calls
    - Token bucket: Limits total tokens consumed
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        tokens_per_minute: int = 90000,
    ):
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute

        # Token bucket state
        self._request_tokens = float(requests_per_minute)
        self._token_tokens = float(tokens_per_minute)
        self._last_update = time.monotonic()

        # BUG-004 fix: initialize the lock eagerly in __init__ so there is no
        # TOCTOU window between the `self._lock is None` check and the
        # assignment.  Two threads racing on the first call to acquire() would
        # each create their own Lock and one would silently be discarded,
        # leaving the other thread to use an unprotected bucket.
        import threading
        self._lock = threading.Lock()

    def _get_lock(self):
        """Return the thread-safety lock (pre-initialised in __init__)."""
        return self._lock

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update

        # Refill at steady rate
        self._request_tokens = min(
            self.requests_per_minute,
            self._request_tokens + elapsed * (self.requests_per_minute / 60.0)
        )
        self._token_tokens = min(
            self.tokens_per_minute,
            self._token_tokens + elapsed * (self.tokens_per_minute / 60.0)
        )

        self._last_update = now

    def acquire(self, tokens: int = 0) -> tuple[bool, float]:
        """Attempt to acquire rate limit tokens.

        Args:
            tokens: Number of tokens to consume (0 = just check request limit)

        Returns:
            Tuple of (allowed, wait_time_seconds).
            If allowed is False, wait_time indicates how long to wait.
        """
        with self._get_lock():
            self._refill()

            # Check if we have enough tokens
            if self._request_tokens < 1.0:
                wait_time = (1.0 - self._request_tokens) * 60.0 / self.requests_per_minute
                return (False, wait_time)

            if tokens > 0 and self._token_tokens < tokens:
                wait_time = (tokens - self._token_tokens) * 60.0 / self.tokens_per_minute
                return (False, wait_time)

            # Consume tokens
            self._request_tokens -= 1.0
            if tokens > 0:
                self._token_tokens -= tokens

            return (True, 0.0)

    def get_status(self) -> dict[str, Any]:
        """Get current rate limiter status."""
        with self._get_lock():
            self._refill()
            return {
                "request_tokens_available": self._request_tokens,
                "token_tokens_available": self._token_tokens,
                "requests_per_minute": self.requests_per_minute,
                "tokens_per_minute": self.tokens_per_minute,
            }


class LLMClient:
    """Stateless OpenAI-compatible chat completion client.

    SECURITY FIX #6: Includes rate limiting to prevent quota exhaustion.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._model_chain = [config.primary_model] + list(config.fallback_models)
        self._anthropic = None  # Will be set by from_rc_config if needed

        # SECURITY FIX #6: Initialize rate limiter
        self._rate_limiter: TokenBucketRateLimiter | None = None
        if config.rate_limit_enabled:
            self._rate_limiter = TokenBucketRateLimiter(
                requests_per_minute=config.rate_limit_requests_per_minute,
                tokens_per_minute=config.rate_limit_tokens_per_minute,
            )

    def get_rate_limiter_status(self) -> dict[str, Any] | None:
        """Get current rate limiter status (for monitoring)."""
        if self._rate_limiter:
            return self._rate_limiter.get_status()
        return None

    @staticmethod
    def _normalize_wire_api(wire_api: str) -> str:
        normalized = (wire_api or "").strip().lower().replace("-", "_")
        if normalized in ("", "chat/completions", "chat_completions"):
            return "chat_completions"
        if normalized == "responses":
            return "responses"
        return normalized

    def _endpoint_path(self) -> str:
        if self._normalize_wire_api(self.config.wire_api) == "responses":
            return "/responses"
        return "/chat/completions"

    def _endpoint_url(self, base_url: str) -> str:
        return f"{base_url.rstrip('/')}{self._endpoint_path()}"

    @staticmethod
    def _supports_temperature(model: str) -> bool:
        return not any(model.startswith(prefix) for prefix in _NO_TEMPERATURE_MODELS)

    @classmethod
    def from_rc_config(cls, rc_config: Any) -> LLMClient:
        from berb.llm import PROVIDER_PRESETS

        provider = getattr(rc_config.llm, "provider", "openai")
        preset = PROVIDER_PRESETS.get(provider, {})
        preset_base_url = preset.get("base_url")

        api_key = str(
            rc_config.llm.api_key or os.environ.get(rc_config.llm.api_key_env, "") or ""
        )

        # Use preset base_url if available and config doesn't override
        base_url = rc_config.llm.base_url or preset_base_url or ""

        # Preserve original URL/key before MetaClaw bridge override
        # (needed for Anthropic adapter which should always talk directly
        # to the Anthropic API, not through the OpenAI-compatible proxy).
        original_base_url = base_url
        original_api_key = api_key

        # MetaClaw bridge: if enabled, point to proxy and set up fallback
        bridge = getattr(rc_config, "metaclaw_bridge", None)
        fallback_url = ""
        fallback_api_key = ""

        if bridge and getattr(bridge, "enabled", False):
            fallback_url = base_url
            fallback_api_key = api_key
            base_url = bridge.proxy_url
            if bridge.fallback_url:
                fallback_url = bridge.fallback_url
            if bridge.fallback_api_key:
                fallback_api_key = bridge.fallback_api_key

        config = LLMConfig(
            base_url=base_url,
            api_key=api_key,
            wire_api=getattr(rc_config.llm, "wire_api", "chat_completions"),
            primary_model=rc_config.llm.primary_model or "gpt-4o",
            fallback_models=list(rc_config.llm.fallback_models or []),
            fallback_url=fallback_url,
            fallback_api_key=fallback_api_key,
        )
        client = cls(config)

        # Detect Anthropic or Kimi-Anthropic provider — use original URL/key (not the
        # MetaClaw proxy URL which is OpenAI-compatible only).
        if provider in ("anthropic", "kimi-anthropic"):
            from .anthropic_adapter import AnthropicAdapter

            client._anthropic = AnthropicAdapter(
                original_base_url, original_api_key, config.timeout_sec
            )
        return client

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        system: str | None = None,
        strip_thinking: bool = False,
        stage: Any | None = None,  # Optional pipeline stage for token limits
    ) -> LLMResponse:
        """Send a chat completion request with retry and fallback.

        SECURITY FIX #6: Includes rate limiting to prevent quota exhaustion.

        Args:
            messages: List of {role, content} dicts.
            model: Override model (skips fallback chain).
            max_tokens: Override max token count.
            temperature: Override temperature.
            json_mode: Request JSON response format.
            system: Prepend a system message.
            strip_thinking: If True, strip <think>…</think> reasoning
                tags from the response content.  Use this when the
                output will be written to paper/script artifacts but
                NOT for general chat calls (to avoid corrupting
                legitimate content).
            stage: Optional pipeline stage for automatic token limiting.
                If provided, max_tokens defaults to stage limit.

        Returns:
            LLMResponse with content and metadata.

        Raises:
            RuntimeError: If rate limit exceeded and wait would exceed timeout.
        """
        # SECURITY FIX #6: Apply rate limiting
        if self._rate_limiter:
            # Estimate tokens from message content.
            # Use ceil(chars/3) as a conservative upper-bound — real tokenisers
            # average ~3.5 chars/token for English prose and less for code, so
            # dividing by 3 avoids systematically undercharging the bucket.
            estimated_tokens = sum(
                (len(m.get("content", "")) + 2) // 3
                for m in messages
            )
            estimated_tokens += max_tokens or self.config.max_tokens

            allowed, wait_time = self._rate_limiter.acquire(estimated_tokens)
            if not allowed:
                # Check if wait time is acceptable
                if wait_time > self.config.timeout_sec:
                    raise RuntimeError(
                        f"Rate limit exceeded. Would need to wait {wait_time:.1f}s "
                        f"(exceeds timeout of {self.config.timeout_sec}s). "
                        f"Consider reducing request frequency or increasing limits."
                    )
                # Cap sleep to 60 s so a single call can never block indefinitely
                # even when timeout_sec is set to a very large value.
                capped_wait = min(wait_time, 60.0)
                logger.warning(
                    "Rate limit hit. Waiting %.1f seconds before retry.",
                    capped_wait,
                )
                time.sleep(capped_wait)
                # Try again after waiting
                allowed, _ = self._rate_limiter.acquire(estimated_tokens)
                if not allowed:
                    raise RuntimeError("Rate limit still exceeded after waiting.")

        # Apply stage-based token limit if stage provided and max_tokens not set
        if stage is not None and max_tokens is None:
            from .output_limits import get_stage_token_limit
            max_tokens = get_stage_token_limit(stage)
            logger.debug(f"Stage {stage}: auto-set max_tokens={max_tokens}")

        if system:
            messages = [{"role": "system", "content": system}] + messages

        models = [model] if model else self._model_chain
        max_tok = max_tokens or self.config.max_tokens
        temp = temperature if temperature is not None else self.config.temperature

        last_error: Exception | None = None

        for m in models:
            try:
                resp = self._call_with_retry(m, messages, max_tok, temp, json_mode)
                if strip_thinking:
                    from berb.utils.thinking_tags import strip_thinking_tags

                    resp = LLMResponse(
                        content=strip_thinking_tags(resp.content),
                        model=resp.model,
                        prompt_tokens=resp.prompt_tokens,
                        completion_tokens=resp.completion_tokens,
                        total_tokens=resp.total_tokens,
                        finish_reason=resp.finish_reason,
                        truncated=resp.truncated,
                        raw=resp.raw,
                    )
                return resp
            except Exception as exc:  # noqa: BLE001
                logger.warning("Model %s failed: %s. Trying next.", m, exc)
                last_error = exc

        raise RuntimeError(
            f"All models failed. Last error: {last_error}"
        ) from last_error

    def preflight(self) -> tuple[bool, str]:
        """Quick connectivity check - one minimal chat call.

        Returns (success, message).
        Distinguishes: 401 (bad key), 403 (model forbidden),
                       404 (bad endpoint), 429 (rate limited), timeout.
        """
        is_reasoning = any(
            self.config.primary_model.startswith(p) for p in _NEW_PARAM_MODELS
        )
        min_tokens = 64 if is_reasoning else 1
        try:
            _ = self.chat(
                [{"role": "user", "content": "ping"}],
                max_tokens=min_tokens,
                temperature=0,
            )
            return True, f"OK - model {self.config.primary_model} responding"
        except urllib.error.HTTPError as e:
            status_map = {
                401: "Invalid API key",
                403: f"Model {self.config.primary_model} not allowed for this key",
                404: f"Endpoint not found: {self._endpoint_url(self.config.base_url)}",
                429: "Rate limited - try again in a moment",
            }
            msg = status_map.get(e.code, f"HTTP {e.code}")
            return False, msg
        except (urllib.error.URLError, OSError) as e:
            return False, f"Connection failed: {e}"
        except RuntimeError as e:
            # chat() wraps errors in RuntimeError; extract original HTTPError
            cause = e.__cause__
            if isinstance(cause, urllib.error.HTTPError):
                status_map = {
                    401: "Invalid API key",
                    403: f"Model {self.config.primary_model} not allowed for this key",
                    404: f"Endpoint not found: {self._endpoint_url(self.config.base_url)}",
                    429: "Rate limited - try again in a moment",
                }
                msg = status_map.get(cause.code, f"HTTP {cause.code}")
                return False, msg
            return False, f"All models failed: {e}"

    def _call_with_retry(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> LLMResponse:
        """Call with exponential backoff retry."""
        for attempt in range(self.config.max_retries):
            try:
                return self._raw_call(
                    model, messages, max_tokens, temperature, json_mode
                )
            except urllib.error.HTTPError as e:
                status = e.code
                body = ""
                try:
                    body = e.read().decode()[:500]
                except Exception:  # noqa: BLE001
                    pass

                # Non-retryable errors
                if status == 403 and "not allowed to use model" in body:
                    raise  # Model not available — let fallback handle

                # 400 is normally non-retryable, but some providers
                # (Azure OpenAI) return 400 during overload / rate-limit.
                # Retry if the body hints at a transient issue.
                if status == 400:
                    _transient_400 = any(
                        kw in body.lower()
                        for kw in (
                            "rate limit",
                            "ratelimit",
                            "overloaded",
                            "temporarily",
                            "capacity",
                            "throttl",
                            "too many",
                            "retry",
                        )
                    )
                    if not _transient_400:
                        raise  # Genuine bad request — don't retry

                # Retryable: 429 (rate limit), transient 400, 500, 502, 503, 504,
                # 529 (Anthropic overloaded)
                if status in (400, 429, 500, 502, 503, 504, 529):
                    delay = self.config.retry_base_delay * (2**attempt)
                    # Add jitter
                    import random

                    delay += random.uniform(0, delay * 0.3)
                    logger.info(
                        "Retry %d/%d for %s (HTTP %d). Waiting %.1fs.",
                        attempt + 1,
                        self.config.max_retries,
                        model,
                        status,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                raise  # Other HTTP errors
            except urllib.error.URLError:
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_base_delay * (2**attempt)
                    time.sleep(delay)
                    continue
                raise

        # All retries exhausted
        raise RuntimeError(
            f"LLM call failed after {self.config.max_retries} retries for model {model}"
        )

    def _raw_call(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> LLMResponse:
        """Make a single API call."""

        # Use Anthropic adapter if configured
        if self._anthropic:
            data = self._anthropic.chat_completion(
                model, messages, max_tokens, temperature, json_mode
            )
        else:
            # Original OpenAI logic
            # Copy messages to avoid mutating the caller's list (important for
            # retries and model-fallback — each attempt must start from the
            # original, un-modified messages).
            msgs = [dict(m) for m in messages]

            # MiniMax API requires temperature in [0, 1.0]
            _temp = temperature
            if "api.minimax.io" in self.config.base_url:
                _temp = max(0.0, min(_temp, 1.0))

            if self._normalize_wire_api(self.config.wire_api) == "responses":
                body = self._build_responses_body(model, msgs, max_tokens, _temp)
            else:
                body = {
                    "model": model,
                    "messages": msgs,
                }
                if self._supports_temperature(model):
                    body["temperature"] = _temp

                # Use correct token parameter based on model
                if any(model.startswith(prefix) for prefix in _NEW_PARAM_MODELS):
                    reasoning_min = 32768
                    body["max_completion_tokens"] = max(max_tokens, reasoning_min)
                else:
                    body["max_tokens"] = max_tokens

            if json_mode:
                # Many OpenAI-compatible proxies serving Claude models don't
                # support the response_format parameter and return HTTP 400.
                # Fall back to a system-prompt injection for non-OpenAI models.
                if (
                    model.startswith("claude")
                    or self._normalize_wire_api(self.config.wire_api) == "responses"
                ):
                    _json_hint = (
                        "You MUST respond with valid JSON only. "
                        "Do not include any text outside the JSON object."
                    )
                    # Prepend to existing system message or add as new one
                    if msgs and msgs[0]["role"] == "system":
                        msgs[0]["content"] = _json_hint + "\n\n" + msgs[0]["content"]
                    else:
                        msgs.insert(0, {"role": "system", "content": _json_hint})
                else:
                    body["response_format"] = {"type": "json_object"}

            payload = json.dumps(body).encode("utf-8")
            url = self._endpoint_url(self.config.base_url)

            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": self.config.user_agent,
            }
            # MetaClaw bridge: inject extra headers (session ID, stage info, etc.)
            headers.update(self.config.extra_headers)

            req = urllib.request.Request(url, data=payload, headers=headers)

            try:
                with urllib.request.urlopen(
                    req, timeout=self.config.timeout_sec
                ) as resp:
                    data = json.loads(resp.read())
            except (urllib.error.URLError, OSError) as exc:
                # MetaClaw bridge: fallback to direct LLM if proxy unreachable
                if self.config.fallback_url:
                    logger.warning(
                        "Primary endpoint unreachable, falling back to %s: %s",
                        self.config.fallback_url,
                        exc,
                    )
                    fallback_url = self._endpoint_url(self.config.fallback_url)
                    fallback_key = self.config.fallback_api_key or self.config.api_key
                    fallback_headers = {
                        "Authorization": f"Bearer {fallback_key}",
                        "Content-Type": "application/json",
                        "User-Agent": self.config.user_agent,
                    }
                    fallback_req = urllib.request.Request(
                        fallback_url, data=payload, headers=fallback_headers
                    )
                    with urllib.request.urlopen(
                        fallback_req, timeout=self.config.timeout_sec
                    ) as resp:
                        data = json.loads(resp.read())
                else:
                    raise

        if not isinstance(data, dict):
            raise ValueError(
                f"Malformed API response: expected JSON object, got {type(data).__name__}: {data}"
            )

        # Handle API error responses
        if "error" in data and data["error"] is not None:
            error_info = data["error"]
            if isinstance(error_info, dict):
                error_msg = str(error_info.get("message", str(error_info)))
                error_type = str(error_info.get("type", "api_error"))
            else:
                error_msg = str(error_info)
                error_type = "api_error"
            import io

            raise urllib.error.HTTPError(
                "",
                500,
                f"{error_type}: {error_msg}",
                None,
                io.BytesIO(error_msg.encode()),
            )

        if self._normalize_wire_api(self.config.wire_api) == "responses":
            return self._parse_responses_response(data, model)
        return self._parse_chat_completions_response(data, model)

    def _build_responses_body(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "input": self._messages_to_responses_input(messages),
        }
        if self._supports_temperature(model):
            body["temperature"] = temperature
        body["max_output_tokens"] = max_tokens
        return body

    def _messages_to_responses_input(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", "user") or "user")
            content = str(message.get("content", "") or "")
            items.append(
                {
                    "role": role,
                    "content": [{"type": "input_text", "text": content}],
                }
            )
        return items

    def _parse_chat_completions_response(
        self, data: dict[str, Any], model: str
    ) -> LLMResponse:
        if "choices" not in data or not data["choices"]:
            raise ValueError(f"Malformed API response: missing choices. Got: {data}")

        choice = data["choices"][0]
        usage = data.get("usage", {})

        message = choice.get("message", {})
        content = message.get("content") or ""

        return LLMResponse(
            content=content,
            model=data.get("model", model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", ""),
            truncated=(choice.get("finish_reason", "") == "length"),
            raw=data,
        )

    def _parse_responses_response(
        self, data: dict[str, Any], model: str
    ) -> LLMResponse:
        output_items = data.get("output")
        if not isinstance(output_items, list) or not output_items:
            raise ValueError(
                f"Malformed responses API payload: missing output. Got: {data}"
            )

        chunks: list[str] = []
        finish_reason = str(data.get("status", "") or "")
        truncated = False

        for item in output_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                if not isinstance(content_item, dict):
                    continue
                if content_item.get("type") == "output_text":
                    text = content_item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)

        incomplete_details = data.get("incomplete_details")
        if isinstance(incomplete_details, dict):
            reason = incomplete_details.get("reason")
            if isinstance(reason, str) and reason:
                finish_reason = reason
                truncated = reason in ("max_output_tokens", "content_filter")

        usage = data.get("usage", {})
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("input_tokens", 0) or 0)
            completion_tokens = int(usage.get("output_tokens", 0) or 0)
            total_tokens = int(
                usage.get("total_tokens", prompt_tokens + completion_tokens) or 0
            )

        return LLMResponse(
            content="".join(chunks),
            model=data.get("model", model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            finish_reason=finish_reason,
            truncated=truncated,
            raw=data,
        )


def create_client_from_yaml(yaml_path: str | None = None) -> LLMClient:
    """Create an LLMClient from the ARC config file.

    Reads base_url and api_key from config.arc.yaml's llm section.
    """
    import yaml as _yaml

    if yaml_path is None:
        yaml_path = "config.yaml"

    with open(yaml_path, encoding="utf-8") as f:
        raw = _yaml.safe_load(f)

    llm_section = raw.get("llm", {})
    api_key = str(
        os.environ.get(
            llm_section.get("api_key_env", "OPENAI_API_KEY"),
            llm_section.get("api_key", ""),
        )
        or ""
    )

    return LLMClient(
        LLMConfig(
            base_url=llm_section.get("base_url", "https://api.openai.com/v1"),
            api_key=api_key,
            wire_api=llm_section.get("wire_api", "chat_completions"),
            primary_model=llm_section.get("primary_model", "gpt-4o"),
            fallback_models=llm_section.get(
                "fallback_models", ["gpt-4.1", "gpt-4o-mini"]
            ),
        )
    )


class MultiProviderLLMClient:
    """P1 FIX: Multi-provider LLM client with automatic failover.

    Wraps multiple LLMClient instances and tries them in order when
    the primary provider fails. This addresses the SPOF issue where
    all 23 pipeline stages depend on a single LLM provider.

    Example usage:
        client = MultiProviderLLMClient.from_rc_config(rc_config)
        response = client.chat(messages)  # Auto-fails to backup providers
    """

    def __init__(self, clients: list[LLMClient], provider_names: list[str]) -> None:
        """Initialize with a list of LLMClient instances.

        Args:
            clients: List of LLMClient instances (primary first, then fallbacks)
            provider_names: List of provider names for logging
        """
        if not clients:
            raise ValueError("At least one LLMClient is required")
        self._clients = clients
        self._provider_names = provider_names
        self._primary = clients[0]
        self._current_provider_idx = 0

    @classmethod
    def from_rc_config(cls, rc_config: Any) -> "MultiProviderLLMClient":
        """Create a multi-provider client from RCConfig.

        Reads fallback_providers from config and creates clients for each.
        """
        from berb.llm import PROVIDER_PRESETS

        # Create primary client
        primary_client = LLMClient.from_rc_config(rc_config)
        provider_names = [rc_config.llm.provider]

        # Get fallback providers from config
        fallback_providers = list(rc_config.llm.fallback_providers or [])
        clients = [primary_client]

        for fallback_provider in fallback_providers:
            if fallback_provider == rc_config.llm.provider:
                continue  # Skip if same as primary

            preset = PROVIDER_PRESETS.get(fallback_provider, {})
            preset_base_url = preset.get("base_url")

            if not preset_base_url:
                logger.warning(
                    "Fallback provider '%s' has no preset base_url, skipping",
                    fallback_provider,
                )
                continue

            # Try to get API key for fallback provider
            # Convention: FALLBACK_PROVIDER_API_KEY (e.g., DEEPSEEK_API_KEY)
            env_var = f"{fallback_provider.upper()}_API_KEY"
            api_key = os.environ.get(env_var, "")

            if not api_key:
                logger.warning(
                    "Fallback provider '%s' has no API key (env var '%s' not set), skipping",
                    fallback_provider,
                    env_var,
                )
                continue

            # Create fallback client config
            fallback_config = LLMConfig(
                base_url=preset_base_url,
                api_key=api_key,
                wire_api="chat_completions",
                primary_model=rc_config.llm.primary_model or "gpt-4o",
                fallback_models=list(rc_config.llm.fallback_models or []),
                provider_name=fallback_provider,
            )
            clients.append(LLMClient(fallback_config))
            provider_names.append(fallback_provider)
            logger.info(
                "Multi-provider failover: added '%s' as fallback (env var: %s)",
                fallback_provider,
                env_var,
            )

        return cls(clients, provider_names)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        system: str | None = None,
        strip_thinking: bool = False,
        stage: Any | None = None,
    ) -> LLMResponse:
        """Send a chat request with multi-provider failover.

        Tries providers in order: primary → fallback_1 → fallback_2 → ...
        """
        last_error: Exception | None = None

        for idx, client in enumerate(self._clients):
            provider_name = self._provider_names[idx]
            try:
                logger.debug(
                    "Trying provider '%s' (index %d/%d)",
                    provider_name,
                    idx + 1,
                    len(self._clients),
                )
                response = client.chat(
                    messages,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    json_mode=json_mode,
                    system=system,
                    strip_thinking=strip_thinking,
                    stage=stage,
                )
                if idx > 0:
                    logger.info(
                        "Multi-provider failover: succeeded on fallback provider '%s'",
                        provider_name,
                    )
                return response
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Provider '%s' failed: %s. Trying next provider.",
                    provider_name,
                    exc,
                )
                last_error = exc

        raise RuntimeError(
            f"All providers failed. Tried: {self._provider_names}. Last error: {last_error}"
        ) from last_error

    def preflight(self) -> tuple[bool, str]:
        """Check connectivity for primary provider."""
        return self._primary.preflight()

    def get_rate_limiter_status(self) -> dict[str, Any] | None:
        """Get rate limiter status from primary client."""
        return self._primary.get_rate_limiter_status()

    def get_provider_status(self) -> dict[str, Any]:
        """Get status of all providers."""
        return {
            "providers": self._provider_names,
            "current_provider": self._provider_names[self._current_provider_idx],
            "total_providers": len(self._clients),
        }
