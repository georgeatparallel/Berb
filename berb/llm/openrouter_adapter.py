"""OpenRouter API adapter for Berb.

OpenRouter provides unified access to 340+ LLM models from 60+ providers
with a single API key and competitive pricing.

Supported Providers (80+ notable models declared):
- Anthropic (Claude Sonnet/Opus/Haiku 4.5–4.8, Claude Fable 5)
- OpenAI (GPT-5.5/5.4/5.2/5.1/5/4o/4.1, o1/o3/o3-pro/o4-mini)
- Google (Gemini 2.5/3.0/3.5 Pro/Flash/Lite, Gemma 4)
- DeepSeek (V3.1/V3.2/V4-Pro/V4-Flash, R1)
- Qwen (Qwen3/3.5/3.6/3.7 Max/Plus/Flash, Qwen3-Coder)
- xAI (Grok 4.5, Grok 4.3)
- Xiaomi (MIMO v2.5/v2.5-Pro)
- MoonshotAI (Kimi K2/K2.5/K2.6/K2.7)
- MiniMax (MiniMax M2.5/M2.7/M3)
- Z-AI (GLM 4.5/4.7/5/5.1/5.2)
- Perplexity (Sonar, Sonar Pro, Sonar Deep Research)
- Meta (Llama 4 Maverick/Scout)
- Amazon (Nova Lite/Pro/Premier)
- Mistral (Mistral Large, Mistral Medium/Small)
- And more: NVIDIA, Microsoft, Cohere, ByteDance Seed

Model Variants (appended as suffixes to model IDs):
- :extended  — Extended context window variant
- :nitro     — High-throughput / low-latency provider routing
- :thinking  — Extended chain-of-thought reasoning variant
- :exacto    — Exact provider pinning, disables auto-routing fallbacks

Features:
- Unified API across all providers
- Model variant routing (:extended, :nitro, :thinking, :exacto)
- Provider routing hints (order, fallback control)
- Automatic fallback chains
- Cost tracking and optimization
- Model ranking based on performance

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.llm.openrouter_adapter import OpenRouterProvider, ModelVariant

    provider = OpenRouterProvider(
        api_key="sk-or-...",
        model="anthropic/claude-sonnet-4.6",
    )

    # Use a model variant
    response = await provider.complete(
        [{"role": "user", "content": "Hello!"}],
        variant=ModelVariant.THINKING,
    )

    # Or construct variant model IDs directly
    thinking_model = ModelVariant.THINKING.apply("anthropic/claude-sonnet-4.6")
    # -> "anthropic/claude-sonnet-4.6:thinking"
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

# Use existing LLMResponse from client module
from berb.llm.client import LLMResponse
from berb.llm.openrouter_models_data import OPENROUTER_MODELS, OpenRouterModel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Model Variants
# ─────────────────────────────────────────────────────────────────────────────


class ModelVariant(StrEnum):
    """OpenRouter model variant suffixes.

    Appended to a model ID to select a routing variant:
      - EXTENDED : Extended context window version (e.g. 200K → 1M tokens)
      - NITRO    : Fast, high-throughput provider routing
      - THINKING : Extended chain-of-thought reasoning
      - EXACTO   : Pin to exact model/provider, disable auto-routing fallbacks

    Example:
        >>> ModelVariant.THINKING.apply("anthropic/claude-3.5-sonnet")
        'anthropic/claude-3.5-sonnet:thinking'
    """

    EXTENDED = "extended"
    NITRO = "nitro"
    THINKING = "thinking"
    EXACTO = "exacto"

    def apply(self, model_id: str) -> str:
        """Return model ID with this variant suffix.

        Idempotent: if the model already has this variant suffix, returns as-is.
        Replaces any existing variant suffix with this one.
        """
        base = strip_variant(model_id)
        return f"{base}:{self.value}"

    @classmethod
    def from_model_id(cls, model_id: str) -> ModelVariant | None:
        """Extract variant from a model ID, or None if no variant present."""
        if ":" in model_id:
            suffix = model_id.rsplit(":", 1)[-1]
            try:
                return cls(suffix)
            except ValueError:
                return None
        return None


def strip_variant(model_id: str) -> str:
    """Return model ID with any variant suffix removed."""
    if ":" in model_id:
        base, suffix = model_id.rsplit(":", 1)
        # Only strip recognized variant suffixes; keep provider-prefixed colons
        try:
            ModelVariant(suffix)
            return base
        except ValueError:
            pass
    return model_id


# ─────────────────────────────────────────────────────────────────────────────
# Provider Routing Hints
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ProviderRouting:
    """OpenRouter provider routing hints.

    Controls how OpenRouter selects the underlying provider for a request.

    Attributes:
        order: Preferred provider order (e.g. ["Anthropic", "AWS Bedrock"])
        allow_fallbacks: Whether to fall back to other providers if preferred
            are unavailable. Set False when combined with EXACTO variant.
        require_parameters: Only use providers that support all requested
            parameters (e.g. ["tools", "stream"]).
        data_collection: "allow" or "deny" — whether to permit providers
            that use requests for model training.
    """

    order: list[str] = field(default_factory=list)
    allow_fallbacks: bool = True
    require_parameters: list[str] = field(default_factory=list)
    data_collection: str = "allow"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to OpenRouter API format."""
        d: dict[str, Any] = {}
        if self.order:
            d["order"] = self.order
        if not self.allow_fallbacks:
            d["allow_fallbacks"] = False
        if self.require_parameters:
            d["require_parameters"] = self.require_parameters
        if self.data_collection != "allow":
            d["data_collection"] = self.data_collection
        return d


# Convenience preset: disable all fallbacks (pair with EXACTO variant)
ROUTING_EXACT = ProviderRouting(allow_fallbacks=False)
# Convenience preset: prefer speed-optimized providers
ROUTING_NITRO = ProviderRouting(order=["Together", "Fireworks", "Lepton"])
# Convenience preset: Anthropic-direct for Claude models
ROUTING_ANTHROPIC_DIRECT = ProviderRouting(order=["Anthropic"], allow_fallbacks=True)


class OpenRouterProvider:
    """OpenRouter API provider.

    Provides unified access to 100+ LLM models with competitive pricing
    and automatic fallback support.

    Attributes:
        api_key: OpenRouter API key
        model: Model ID to use
        base_url: OpenRouter API base URL
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "anthropic/claude-sonnet-4.6",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: int = 120,
        max_retries: int = 3,
    ):
        """
        Initialize OpenRouter provider.

        Args:
            api_key: OpenRouter API key (or OPENROUTER_API_KEY env var)
            model: Model ID to use
            base_url: OpenRouter API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not provided. "
                "Set OPENROUTER_API_KEY environment variable or pass api_key parameter."
            )

        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/georgehadji/Berb",
                "X-Title": "Berb",
            },
        )

        # Get model info
        self.model_info = OPENROUTER_MODELS.get(model)
        if not self.model_info:
            logger.warning("Model %s not in pre-configured list, using defaults", model)
            self.model_info = OpenRouterModel(
                id=model,
                name=model,
                provider="unknown",
            )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        variant: ModelVariant | None = None,
        provider_routing: ProviderRouting | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Complete a chat conversation.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            variant: Optional model variant suffix to apply (:extended,
                :nitro, :thinking, :exacto). Overrides any suffix already
                present in self.model.
            provider_routing: Optional provider routing hints. When variant
                is EXACTO, automatically sets allow_fallbacks=False unless
                provider_routing is explicitly provided.
            **kwargs: Additional OpenRouter API parameters

        Returns:
            LLMResponse with completion
        """
        import time

        time.monotonic()

        # Resolve model ID (apply variant suffix if requested)
        model_id = variant.apply(self.model) if variant else self.model

        # Auto-configure provider routing for EXACTO variant
        if variant is ModelVariant.EXACTO and provider_routing is None:
            provider_routing = ROUTING_EXACT

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }

        if provider_routing:
            routing_dict = provider_routing.to_dict()
            if routing_dict:
                payload["provider"] = routing_dict

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = await self._client.post(
                    "/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Parse response
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                # FIX-001a: Match LLMResponse dataclass fields exactly
                # LLMResponse only has: content, model, prompt_tokens, completion_tokens, total_tokens, finish_reason, truncated, raw
                # Cost and duration tracking deferred to future PR
                return LLMResponse(
                    content=content,
                    model=data.get("model", self.model),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    finish_reason=data.get("choices", [{}])[0].get("finish_reason", ""),
                    truncated=data.get("choices", [{}])[0].get("finish_reason")
                    == "length",
                    raw=data,
                )

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    "OpenRouter API error (attempt %d/%d): %s - %s",
                    attempt + 1,
                    self.max_retries,
                    e.response.status_code,
                    e.response.text,
                )

                if e.response.status_code in (400, 401, 403):
                    # Don't retry client errors
                    break

                await asyncio.sleep(2**attempt)

            except Exception as e:
                last_error = e
                logger.warning(
                    "OpenRouter request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                await asyncio.sleep(2**attempt)

        # All retries exhausted
        raise type(last_error)(
            f"OpenRouter API failed after {self.max_retries} retries: {last_error}"
        ) from last_error

    def _calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calculate cost based on token usage."""
        if not self.model_info:
            return 0.0

        input_cost = (prompt_tokens / 1_000_000) * self.model_info.input_price
        output_cost = (completion_tokens / 1_000_000) * self.model_info.output_price

        return input_cost + output_cost

    def get_model_info(self) -> OpenRouterModel:
        """Get current model information."""
        return self.model_info

    @classmethod
    def get_available_models(
        cls,
        tier: str | None = None,
        provider: str | None = None,
        min_context: int | None = None,
    ) -> list[OpenRouterModel]:
        """
        Get available models filtered by criteria.

        Args:
            tier: Filter by tier (budget, mid, premium)
            provider: Filter by provider name
            min_context: Minimum context length

        Returns:
            List of matching models
        """
        models = list(OPENROUTER_MODELS.values())

        if tier:
            models = [m for m in models if m.tier == tier]

        if provider:
            models = [m for m in models if m.provider == provider]

        if min_context:
            models = [m for m in models if m.context_length >= min_context]

        return sorted(models, key=lambda m: m.input_price)

    def with_variant(self, variant: ModelVariant) -> OpenRouterProvider:
        """Return a new provider instance using the given model variant.

        Convenience method for one-off variant calls without mutating self.

        Example:
            thinking = provider.with_variant(ModelVariant.THINKING)
            response = await thinking.complete(messages)
        """
        return OpenRouterProvider(
            api_key=self.api_key,
            model=variant.apply(self.model),
            base_url=str(self._client.base_url),
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> OpenRouterProvider:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Import asyncio at module level for retry logic
