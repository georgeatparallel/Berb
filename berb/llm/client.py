"""Lightweight OpenAI-compatible LLM client — stdlib only.

Features:
  - Model fallback chain (gpt-5.2 → gpt-5.1 → gpt-4.1 → gpt-4o)
  - Auto-detect max_tokens vs max_completion_tokens per model
  - Cloudflare User-Agent bypass
  - Exponential backoff retry with jitter
  - JSON mode support
  - Streaming disabled (sync only)
  - Stage-based output token limits (15-25% cost reduction)
  - Circuit breaker for cascading failure prevention (P0 2026-04-02)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class LLMProvider(StrEnum):
    """LLM provider enumeration.

    Used for cross-model review and provider-specific routing.
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    MINIMAX = "minimax"
    QWEN = "qwen"
    GLM = "glm"
    XAI = "xai"
    KIMI = "kimi"
    PERPLEXITY = "perplexity"
    MIMO = "mimo"
    UNKNOWN = "unknown"


# OpenRouter uses different vendor slugs than our LLMProvider enum values
# for a few providers (e.g. "z-ai/glm-4.5", "x-ai/grok-4"). Map those
# OpenRouter-specific prefixes onto the corresponding LLMProvider.
_OPENROUTER_PREFIX_ALIASES: dict[str, LLMProvider] = {
    "z-ai": LLMProvider.GLM,
    "x-ai": LLMProvider.XAI,
    "moonshotai": LLMProvider.KIMI,
    "xiaomi": LLMProvider.MIMO,
}


def get_provider_from_model(model: str) -> LLMProvider:
    """Extract provider from model string.

    Args:
        model: Model identifier (e.g., 'qwen/qwen3.5-flash')

    Returns:
        LLMProvider enum value

    Example:
        >>> get_provider_from_model('qwen/qwen3.5-flash')
        <LLMProvider.QWEN: 'qwen'>
        >>> get_provider_from_model('z-ai/glm-4.5')
        <LLMProvider.GLM: 'glm'>
        >>> get_provider_from_model('unknown-model')
        <LLMProvider.UNKNOWN: 'unknown'>
    """
    if not model:
        return LLMProvider.UNKNOWN

    model_lower = model.lower().split("/")[0]  # Extract provider prefix

    if model_lower in _OPENROUTER_PREFIX_ALIASES:
        return _OPENROUTER_PREFIX_ALIASES[model_lower]

    for provider in LLMProvider:
        if provider.value != "unknown" and model_lower == provider.value:
            return provider
    return LLMProvider.UNKNOWN


def validate_model_for_provider(model: str, provider: LLMProvider) -> bool:
    """Validate that model string matches provider.

    Args:
        model: Model identifier
        provider: Expected provider

    Returns:
        True if model matches provider

    Example:
        >>> validate_model_for_provider('qwen/qwen3.5-flash', LLMProvider.QWEN)
        True
        >>> validate_model_for_provider('openai/gpt-4', LLMProvider.QWEN)
        False
    """
    if not model or provider == LLMProvider.UNKNOWN:
        return True  # Can't validate unknown provider
    extracted = get_provider_from_model(model)
    return extracted == provider


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
    cached_tokens: int = 0  # Prompt-cache reads (0.1x price) — see llm/prompt_cache.py


@dataclass
class LLMConfig:
    """Configuration for the LLM client."""

    base_url: str
    api_key: str
    wire_api: str = "chat_completions"
    primary_model: str = "gpt-4o"
    fallback_models: list[str] = field(default_factory=lambda: ["gpt-4.1", "gpt-4o-mini"])
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
    # OpenRouter-only: pins the upstream provider instead of OpenRouter's
    # default cross-provider load balancing. Shape matches OpenRouter's
    # `provider` request field: {"order": [...], "allow_fallbacks": bool}.
    # None (default) omits the field entirely — unchanged behavior.
    provider_routing: dict[str, Any] | None = None


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

        # BUG-004 FIX: Lock must be created eagerly here, not lazily on first
        # use. Lazy init had a TOCTOU window — two threads could both see
        # self._lock is None and each create a separate Lock, so one thread
        # would end up operating without mutual exclusion.
        import threading

        self._lock = threading.Lock()

    def _get_lock(self):
        """Return the lock created eagerly in __init__ (BUG-004)."""
        return self._lock

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update

        # Refill at steady rate
        self._request_tokens = min(
            self.requests_per_minute,
            self._request_tokens + elapsed * (self.requests_per_minute / 60.0),
        )
        self._token_tokens = min(
            self.tokens_per_minute, self._token_tokens + elapsed * (self.tokens_per_minute / 60.0)
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


@dataclass
class CircuitBreakerState:
    """State for circuit breaker pattern."""

    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    state: str = "closed"  # closed, open, half_open


class CircuitBreaker:
    """Circuit breaker for preventing cascading failures.

    P0 Implementation (2026-04-02): Prevents system-wide failures during LLM outages.

    States:
    - closed: Normal operation, requests pass through
    - open: Circuit tripped, requests fail immediately
    - half_open: Testing if service recovered

    Args:
        fail_max: Number of failures before opening circuit
        reset_timeout: Seconds to wait before trying again
        success_threshold: Successes needed in half_open to close
    """

    def __init__(
        self,
        fail_max: int = 5,
        reset_timeout: float = 60.0,
        success_threshold: int = 3,
    ):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.success_threshold = success_threshold
        self._state = CircuitBreakerState()
        self._lock = threading.Lock()

    def __enter__(self) -> CircuitBreaker:
        """Enter circuit breaker context."""
        if not self._can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit breaker open. Retry after {self.reset_timeout}s"
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit circuit breaker context, recording success or failure.

        NOTE: _on_success()/_on_failure() each acquire self._lock
        themselves — don't also acquire it here, self._lock is a plain
        (non-reentrant) threading.Lock and double-acquiring it from the
        same thread deadlocks forever.
        """
        if exc_type is None:
            self._on_success()
        else:
            self._on_failure()

    def _can_execute(self) -> bool:
        """Check if request can proceed."""
        with self._lock:
            state = self._state

            if state.state == "closed":
                return True

            if state.state == "open":
                # Check if reset timeout has passed
                if time.monotonic() - state.last_failure_time >= self.reset_timeout:
                    state.state = "half_open"
                    state.success_count = 0
                    return True
                return False

            # half_open state
            return True

    def _on_success(self) -> None:
        """Record successful request."""
        with self._lock:
            state = self._state

            if state.state == "half_open":
                state.success_count += 1
                if state.success_count >= self.success_threshold:
                    state.state = "closed"
                    state.failure_count = 0
                    state.success_count = 0
            elif state.state == "closed":
                state.failure_count = 0

    def _on_failure(self) -> None:
        """Record failed request."""
        with self._lock:
            state = self._state
            state.failure_count += 1
            state.last_failure_time = time.monotonic()

            if state.state == "half_open":
                # Immediately back to open on failure in half_open
                state.state = "open"
                state.success_count = 0
            elif state.state == "closed" and state.failure_count >= self.fail_max:
                state.state = "open"

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status."""
        with self._lock:
            state = self._state
            return {
                "state": state.state,
                "failure_count": state.failure_count,
                "success_count": state.success_count,
                "last_failure_time": state.last_failure_time,
            }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


class LLMClient:
    """Stateless OpenAI-compatible chat completion client.

    SECURITY FIX #6: Includes rate limiting to prevent quota exhaustion.
    """

    def __init__(
        self,
        config: LLMConfig,
        circuit_breaker_enabled: bool = True,
    ) -> None:
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

        # P0 2026-04-02: Initialize circuit breaker for cascading failure prevention
        self._circuit_breaker: CircuitBreaker | None = None
        if circuit_breaker_enabled:
            self._circuit_breaker = CircuitBreaker(
                fail_max=5,  # Open after 5 failures
                reset_timeout=60.0,  # Try again after 60 seconds
                success_threshold=3,  # Need 3 successes to close
            )

    def get_rate_limiter_status(self) -> dict[str, Any] | None:
        """Get current rate limiter status (for monitoring)."""
        if self._rate_limiter:
            return self._rate_limiter.get_status()
        return None

    def get_circuit_breaker_status(self) -> dict[str, Any] | None:
        """Get current circuit breaker status (for monitoring)."""
        if self._circuit_breaker:
            return self._circuit_breaker.get_status()
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
    def from_rc_config(cls, rc_config: Any, circuit_breaker_enabled: bool = True) -> LLMClient:
        from berb.llm import PROVIDER_PRESETS

        provider = getattr(rc_config.llm, "provider", "openai")
        preset = PROVIDER_PRESETS.get(provider, {})
        preset_base_url = preset.get("base_url")

        api_key = str(rc_config.llm.api_key or os.environ.get(rc_config.llm.api_key_env, "") or "")

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

        # fallback_models is a same-provider model chain (e.g. MiniMax's
        # "MiniMax-M2.5-highspeed" as a fallback for "MiniMax-M2.5", or
        # OpenRouter's "qwen/qwen3.5-flash" slugs). It is the operator's
        # responsibility to configure IDs that resolve against the selected
        # provider — wire it through unconditionally rather than guessing
        # by provider name.
        model_chain_fallbacks = list(rc_config.llm.fallback_models or [])

        # Provider pinning only means something on OpenRouter — other
        # providers don't have a cross-provider load balancer to pin.
        provider_routing: dict[str, Any] | None = None
        if provider == "openrouter":
            routing_order = list(getattr(rc_config.llm, "provider_routing_order", ()) or ())
            if routing_order:
                provider_routing = {
                    "order": routing_order,
                    "allow_fallbacks": bool(
                        getattr(rc_config.llm, "provider_routing_allow_fallbacks", True)
                    ),
                }

        config = LLMConfig(
            base_url=base_url,
            api_key=api_key,
            wire_api=getattr(rc_config.llm, "wire_api", "chat_completions"),
            primary_model=rc_config.llm.primary_model or "gpt-4o",
            fallback_models=model_chain_fallbacks,
            fallback_url=fallback_url,
            fallback_api_key=fallback_api_key,
            max_retries=getattr(rc_config.llm, "max_retries", 3),
            rate_limit_enabled=False,  # Disable rate limiter for faster response
            provider_routing=provider_routing,
        )
        client = cls(config, circuit_breaker_enabled=circuit_breaker_enabled)

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
        cached_prefix: str | None = None,
        cache_ttl: str = "5m",
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
            cached_prefix: Stable, reused text (e.g. shared document
                content across several calls) to mark with a provider-side
                cache_control breakpoint on models that need one
                explicitly (Claude, Qwen — see
                berb.llm.prompt_cache.model_needs_explicit_cache_control).
                Sent as the FIRST system block so `system` — the volatile,
                call-specific part — never needs to match across calls for
                the cached prefix to hit. Below ~4,000 chars this is a
                no-op (falls back to plain concatenation): too short to
                clear the provider's minimum-cacheable-tokens floor.
            cache_ttl: "5m" (1.25x write cost, default) or "1h" (2x write
                cost) — use "1h" when reuse spans longer than a few
                minutes (e.g. a multi-call review round).
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
            # Estimate tokens from message content (rough estimate)
            estimated_tokens = sum(
                len(m.get("content", "")) // 4  # ~4 chars per token
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
                # Wait and retry
                logger.warning("Rate limit hit. Waiting %.1f seconds before retry.", wait_time)
                time.sleep(wait_time)
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
                resp = self._call_with_retry(
                    m, messages, max_tok, temp, json_mode, cached_prefix, cache_ttl
                )
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

        raise RuntimeError(f"All models failed. Last error: {last_error}") from last_error

    def preflight(self) -> tuple[bool, str]:
        """Quick connectivity check - one minimal chat call.

        Returns (success, message).
        Distinguishes: 401 (bad key), 403 (model forbidden),
                       404 (bad endpoint), 429 (rate limited), timeout.
        """
        is_reasoning = any(self.config.primary_model.startswith(p) for p in _NEW_PARAM_MODELS)
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
        cached_prefix: str | None = None,
        cache_ttl: str = "5m",
    ) -> LLMResponse:
        """Call with exponential backoff retry and circuit breaker.

        P0 2026-04-02: Added circuit breaker for cascading failure prevention.
        P0 2026-04-06: Added IncompleteRead retry for network stability.
        """
        import http.client

        for attempt in range(self.config.max_retries):
            try:
                # P0 2026-04-02: Wrap call with circuit breaker
                if self._circuit_breaker:
                    with self._circuit_breaker:
                        return self._raw_call(
                            model, messages, max_tokens, temperature, json_mode,
                            cached_prefix, cache_ttl,
                        )
                else:
                    return self._raw_call(
                        model, messages, max_tokens, temperature, json_mode,
                        cached_prefix, cache_ttl,
                    )
            except http.client.IncompleteRead as e:
                # P0 2026-04-06: Retry on IncompleteRead (streaming truncation)
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_base_delay * (2**attempt)
                    logger.warning(
                        "IncompleteRead from %s (attempt %d/%d), retrying in %.1fs: %s",
                        model,
                        attempt + 1,
                        self.config.max_retries,
                        delay,
                        e,
                    )
                    time.sleep(delay)
                    continue
                raise
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
        cached_prefix: str | None = None,
        cache_ttl: str = "5m",
    ) -> LLMResponse:
        """Make a single API call."""

        # Use Anthropic adapter if configured
        if self._anthropic:
            data = self._anthropic.chat_completion(
                model,
                messages,
                max_tokens,
                temperature,
                json_mode,
                cached_prefix=cached_prefix,
                cache_ttl=cache_ttl,
            )
        else:
            # Original OpenAI logic
            # Copy messages to avoid mutating the caller's list (important for
            # retries and model-fallback — each attempt must start from the
            # original, un-modified messages).
            msgs = [dict(m) for m in messages]

            # Provider-side prompt caching: mark the stable cached_prefix
            # with a cache_control breakpoint (Claude/Qwen) or plainly
            # prepend it (other providers cache automatically). Skipped for
            # the "responses" wire API — _messages_to_responses_input
            # stringifies content and would mangle a block list.
            if cached_prefix and self._normalize_wire_api(self.config.wire_api) != "responses":
                msgs = self._apply_cached_prefix(msgs, model, cached_prefix, cache_ttl)

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

                if self.config.provider_routing:
                    body["provider"] = self.config.provider_routing

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
                    # Prepend to existing system message or add as new one.
                    # System content may be a plain string or a block list
                    # (when cached_prefix applied a cache_control breakpoint
                    # — see _apply_cached_prefix) — a hint block is
                    # prepended rather than string-concatenated so an
                    # existing cache_control breakpoint stays intact.
                    if msgs and msgs[0]["role"] == "system":
                        existing = msgs[0]["content"]
                        if isinstance(existing, list):
                            msgs[0]["content"] = [
                                {"type": "text", "text": _json_hint},
                                *existing,
                            ]
                        else:
                            msgs[0]["content"] = _json_hint + "\n\n" + existing
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
                with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
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
            resp = self._parse_responses_response(data, model)
        else:
            resp = self._parse_chat_completions_response(data, model)
        self._record_llm_cost(resp)
        return resp

    def _record_llm_cost(self, resp: LLMResponse) -> None:
        """P0-05: record every LLM call for cost/budget accounting.

        Single choke point _raw_call funnels every chat() call, retry, and
        model-fallback attempt through exactly once.
        CostTracker.record_from_llm_response previously had zero production
        callers, so nothing was ever recorded despite the tracker existing.
        """
        try:
            from .cost_tracker import get_cost_tracker

            get_cost_tracker().record_from_llm_response(
                resp.model, resp.prompt_tokens, resp.completion_tokens
            )
        except Exception:  # noqa: BLE001
            logger.debug("Cost tracking failed", exc_info=True)

    def _apply_cached_prefix(
        self,
        msgs: list[dict[str, Any]],
        model: str,
        cached_prefix: str,
        cache_ttl: str,
    ) -> list[dict[str, Any]]:
        """Fold `cached_prefix` into `msgs`'s system message.

        `msgs` must already be a fresh copy (callers own it, safe to mutate
        in place here). See `LLMClient.chat`'s `cached_prefix` docs for the
        ordering rationale.
        """
        from .prompt_cache import build_cached_system_blocks, model_needs_explicit_cache_control

        existing_system = ""
        rest = msgs
        if msgs and msgs[0].get("role") == "system" and isinstance(msgs[0].get("content"), str):
            existing_system = msgs[0]["content"]
            rest = msgs[1:]

        if not model_needs_explicit_cache_control(model):
            # Automatic-caching providers: no cache_control field needed —
            # just make the stable text part of the (auto-cached) prefix.
            merged = cached_prefix + ("\n\n" + existing_system if existing_system else "")
            return [{"role": "system", "content": merged}] + rest

        blocks = build_cached_system_blocks(cached_prefix, existing_system or None, ttl=cache_ttl)
        if blocks is None:
            merged = cached_prefix + ("\n\n" + existing_system if existing_system else "")
            return [{"role": "system", "content": merged}] + rest
        return [{"role": "system", "content": blocks}] + rest

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

    def _messages_to_responses_input(self, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
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

    def _parse_chat_completions_response(self, data: dict[str, Any], model: str) -> LLMResponse:
        if "choices" not in data or not data["choices"]:
            raise ValueError(f"Malformed API response: missing choices. Got: {data}")

        choice = data["choices"][0]
        usage = data.get("usage", {})

        message = choice.get("message", {})
        content = message.get("content") or ""

        # Cached-token reads, normalized across shapes: OpenAI/OpenRouter
        # nest it under prompt_tokens_details; AnthropicAdapter (direct
        # Anthropic path) puts a pre-normalized "cached_tokens" at the top
        # of usage — see anthropic_adapter.py.
        prompt_details = usage.get("prompt_tokens_details")
        if isinstance(prompt_details, dict):
            cached_tokens = int(prompt_details.get("cached_tokens", 0) or 0)
        else:
            cached_tokens = int(usage.get("cached_tokens", 0) or 0)

        return LLMResponse(
            content=content,
            model=data.get("model", model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", ""),
            truncated=(choice.get("finish_reason", "") == "length"),
            raw=data,
            cached_tokens=cached_tokens,
        )

    def _parse_responses_response(self, data: dict[str, Any], model: str) -> LLMResponse:
        output_items = data.get("output")
        if not isinstance(output_items, list) or not output_items:
            raise ValueError(f"Malformed responses API payload: missing output. Got: {data}")

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
            total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)

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
            fallback_models=llm_section.get("fallback_models", ["gpt-4.1", "gpt-4o-mini"]),
            max_retries=int(llm_section.get("max_retries", 3)),
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

    @property
    def config(self) -> LLMConfig:
        """Primary provider's config (for callers that inspect .config)."""
        return self._primary.config

    @classmethod
    def from_rc_config(cls, rc_config: Any) -> MultiProviderLLMClient:
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

        # Model IDs are not portable across providers (e.g. "deepseek-chat"
        # vs OpenRouter-style "deepseek/deepseek-v3.2"). Resolve per-provider.
        model_overrides = dict(getattr(rc_config.llm, "fallback_provider_models", ()) or ())

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

            fallback_model = (
                model_overrides.get(fallback_provider)
                or preset.get("default_model")
                or rc_config.llm.primary_model
                or "gpt-4o"
            )
            # OpenRouter-style fallback_models (e.g. "qwen/qwen3.5-flash") only
            # resolve against OpenRouter's own model catalog — reusing them
            # against a direct provider API (DeepSeek, xAI, ...) would 404.
            chain_models = (
                list(rc_config.llm.fallback_models or [])
                if fallback_provider == "openrouter"
                else []
            )

            # Create fallback client config
            fallback_config = LLMConfig(
                base_url=preset_base_url,
                api_key=api_key,
                wire_api="chat_completions",
                primary_model=fallback_model,
                fallback_models=chain_models,
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
        cached_prefix: str | None = None,
        cache_ttl: str = "5m",
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
                    cached_prefix=cached_prefix,
                    cache_ttl=cache_ttl,
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
