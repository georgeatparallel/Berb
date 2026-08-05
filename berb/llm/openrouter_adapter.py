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


@dataclass
class OpenRouterModel:
    """OpenRouter model configuration."""

    id: str
    """Model ID (e.g., 'anthropic/claude-3.5-sonnet')"""

    name: str
    """Human-readable name"""

    provider: str
    """Provider name (anthropic, openai, google, etc.)"""

    input_price: float = 0.0
    """Price per 1M input tokens (USD)"""

    output_price: float = 0.0
    """Price per 1M output tokens (USD)"""

    context_length: int = 128000
    """Maximum context length"""

    supports_vision: bool = False
    """Whether model supports vision input"""

    supports_json: bool = True
    """Whether model supports JSON output"""

    tier: str = "mid"
    """Model tier: budget, mid, premium"""


# Pre-configured models from OpenRouter (sourced June 2026).
# Prices are per 1M tokens in USD. Free models have 0 pricing.
# See https://openrouter.ai/docs/guides/routing/model-variants for variant suffixes.
OPENROUTER_MODELS: dict[str, OpenRouterModel] = {
    # =========================================================================
    # ANTHROPIC
    # =========================================================================
    "anthropic/claude-sonnet-4.6": OpenRouterModel(
        id="anthropic/claude-sonnet-4.6",
        name="Claude Sonnet 4.6",
        provider="anthropic",
        input_price=3.00,
        output_price=15.00,
        context_length=1_000_000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-opus-4.6": OpenRouterModel(
        id="anthropic/claude-opus-4.6",
        name="Claude Opus 4.6",
        provider="anthropic",
        input_price=5.00,
        output_price=25.00,
        context_length=1_000_000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-opus-4.7": OpenRouterModel(
        id="anthropic/claude-opus-4.7",
        name="Claude Opus 4.7",
        provider="anthropic",
        input_price=5.00,
        output_price=25.00,
        context_length=1_000_000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-opus-4.7-fast": OpenRouterModel(
        id="anthropic/claude-opus-4.7-fast",
        name="Claude Opus 4.7 Fast",
        provider="anthropic",
        input_price=30.00,
        output_price=150.00,
        context_length=1_000_000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-opus-4.8": OpenRouterModel(
        id="anthropic/claude-opus-4.8",
        name="Claude Opus 4.8",
        provider="anthropic",
        input_price=5.00,
        output_price=25.00,
        context_length=1_000_000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-opus-4.8-fast": OpenRouterModel(
        id="anthropic/claude-opus-4.8-fast",
        name="Claude Opus 4.8 Fast",
        provider="anthropic",
        input_price=10.00,
        output_price=50.00,
        context_length=1_000_000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-haiku-4.5": OpenRouterModel(
        id="anthropic/claude-haiku-4.5",
        name="Claude Haiku 4.5",
        provider="anthropic",
        input_price=1.00,
        output_price=5.00,
        context_length=200_000,
        supports_vision=True,
        tier="mid",
    ),
    "anthropic/claude-sonnet-4.5": OpenRouterModel(
        id="anthropic/claude-sonnet-4.5",
        name="Claude Sonnet 4.5",
        provider="anthropic",
        input_price=3.00,
        output_price=15.00,
        context_length=1_000_000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-fable-5": OpenRouterModel(
        id="anthropic/claude-fable-5",
        name="Claude Fable 5",
        provider="anthropic",
        input_price=0.01,
        output_price=0.05,
        context_length=1_000_000,
        supports_vision=True,
        tier="budget",
    ),
    "anthropic/claude-opus-4.5": OpenRouterModel(
        id="anthropic/claude-opus-4.5",
        name="Claude Opus 4.5",
        provider="anthropic",
        input_price=5.00,
        output_price=25.00,
        context_length=200_000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-opus-4.1": OpenRouterModel(
        id="anthropic/claude-opus-4.1",
        name="Claude Opus 4.1",
        provider="anthropic",
        input_price=15.00,
        output_price=75.00,
        context_length=200_000,
        supports_vision=True,
        tier="premium",
    ),
    # =========================================================================
    # OPENAI
    # =========================================================================
    "openai/gpt-5.5": OpenRouterModel(
        id="openai/gpt-5.5",
        name="GPT-5.5",
        provider="openai",
        input_price=5.00,
        output_price=30.00,
        context_length=1_050_000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.5-pro": OpenRouterModel(
        id="openai/gpt-5.5-pro",
        name="GPT-5.5 Pro",
        provider="openai",
        input_price=30.00,
        output_price=180.00,
        context_length=1_050_000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.4": OpenRouterModel(
        id="openai/gpt-5.4",
        name="GPT-5.4",
        provider="openai",
        input_price=2.50,
        output_price=15.00,
        context_length=1_050_000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.4-pro": OpenRouterModel(
        id="openai/gpt-5.4-pro",
        name="GPT-5.4 Pro",
        provider="openai",
        input_price=30.00,
        output_price=180.00,
        context_length=1_050_000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.4-mini": OpenRouterModel(
        id="openai/gpt-5.4-mini",
        name="GPT-5.4 Mini",
        provider="openai",
        input_price=0.75,
        output_price=4.50,
        context_length=400_000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5.2": OpenRouterModel(
        id="openai/gpt-5.2",
        name="GPT-5.2",
        provider="openai",
        input_price=1.75,
        output_price=14.00,
        context_length=400_000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5.2-codex": OpenRouterModel(
        id="openai/gpt-5.2-codex",
        name="GPT-5.2 Codex",
        provider="openai",
        input_price=1.75,
        output_price=14.00,
        context_length=400_000,
        supports_vision=False,
        tier="mid",
    ),
    "openai/gpt-5.1": OpenRouterModel(
        id="openai/gpt-5.1",
        name="GPT-5.1",
        provider="openai",
        input_price=1.25,
        output_price=10.00,
        context_length=400_000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5": OpenRouterModel(
        id="openai/gpt-5",
        name="GPT-5",
        provider="openai",
        input_price=1.25,
        output_price=10.00,
        context_length=400_000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5-mini": OpenRouterModel(
        id="openai/gpt-5-mini",
        name="GPT-5 Mini",
        provider="openai",
        input_price=0.25,
        output_price=2.00,
        context_length=400_000,
        supports_vision=True,
        tier="budget",
    ),
    "openai/gpt-5-nano": OpenRouterModel(
        id="openai/gpt-5-nano",
        name="GPT-5 Nano",
        provider="openai",
        input_price=0.05,
        output_price=0.40,
        context_length=400_000,
        supports_vision=True,
        tier="budget",
    ),
    "openai/gpt-4o": OpenRouterModel(
        id="openai/gpt-4o",
        name="GPT-4o",
        provider="openai",
        input_price=2.50,
        output_price=10.00,
        context_length=128_000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-4o-mini": OpenRouterModel(
        id="openai/gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        input_price=0.15,
        output_price=0.60,
        context_length=128_000,
        supports_vision=True,
        tier="budget",
    ),
    "openai/gpt-4.1": OpenRouterModel(
        id="openai/gpt-4.1",
        name="GPT-4.1",
        provider="openai",
        input_price=2.00,
        output_price=8.00,
        context_length=1_047_576,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-4.1-mini": OpenRouterModel(
        id="openai/gpt-4.1-mini",
        name="GPT-4.1 Mini",
        provider="openai",
        input_price=0.40,
        output_price=1.60,
        context_length=1_047_576,
        supports_vision=True,
        tier="budget",
    ),
    "openai/gpt-4.1-nano": OpenRouterModel(
        id="openai/gpt-4.1-nano",
        name="GPT-4.1 Nano",
        provider="openai",
        input_price=0.10,
        output_price=0.40,
        context_length=1_047_576,
        supports_vision=True,
        tier="budget",
    ),
    "openai/o3-pro": OpenRouterModel(
        id="openai/o3-pro",
        name="o3 Pro",
        provider="openai",
        input_price=20.00,
        output_price=80.00,
        context_length=200_000,
        supports_vision=False,
        tier="premium",
    ),
    "openai/o3": OpenRouterModel(
        id="openai/o3",
        name="o3",
        provider="openai",
        input_price=2.00,
        output_price=8.00,
        context_length=200_000,
        supports_vision=False,
        tier="premium",
    ),
    "openai/o3-mini": OpenRouterModel(
        id="openai/o3-mini",
        name="o3 Mini",
        provider="openai",
        input_price=1.10,
        output_price=4.40,
        context_length=200_000,
        supports_vision=False,
        tier="mid",
    ),
    "openai/o4-mini": OpenRouterModel(
        id="openai/o4-mini",
        name="o4 Mini",
        provider="openai",
        input_price=1.10,
        output_price=4.40,
        context_length=200_000,
        supports_vision=False,
        tier="mid",
    ),
    "openai/o1": OpenRouterModel(
        id="openai/o1",
        name="o1",
        provider="openai",
        input_price=15.00,
        output_price=60.00,
        context_length=200_000,
        supports_vision=False,
        tier="premium",
    ),
    # =========================================================================
    # GOOGLE
    # =========================================================================
    "google/gemini-2.5-pro": OpenRouterModel(
        id="google/gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider="google",
        input_price=1.25,
        output_price=10.00,
        context_length=1_048_576,
        supports_vision=True,
        tier="premium",
    ),
    "google/gemini-2.5-flash": OpenRouterModel(
        id="google/gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        provider="google",
        input_price=0.30,
        output_price=2.50,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemini-2.5-flash-lite": OpenRouterModel(
        id="google/gemini-2.5-flash-lite",
        name="Gemini 2.5 Flash Lite",
        provider="google",
        input_price=0.10,
        output_price=0.40,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemini-3-flash-preview": OpenRouterModel(
        id="google/gemini-3-flash-preview",
        name="Gemini 3 Flash",
        provider="google",
        input_price=0.50,
        output_price=3.00,
        context_length=1_048_576,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3.5-flash": OpenRouterModel(
        id="google/gemini-3.5-flash",
        name="Gemini 3.5 Flash",
        provider="google",
        input_price=1.50,
        output_price=9.00,
        context_length=1_048_576,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3.1-flash-lite": OpenRouterModel(
        id="google/gemini-3.1-flash-lite",
        name="Gemini 3.1 Flash Lite",
        provider="google",
        input_price=0.25,
        output_price=1.50,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemma-4-26b-a4b-it": OpenRouterModel(
        id="google/gemma-4-26b-a4b-it",
        name="Gemma 4 26B",
        provider="google",
        input_price=0.06,
        output_price=0.33,
        context_length=262_144,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemma-4-31b-it": OpenRouterModel(
        id="google/gemma-4-31b-it",
        name="Gemma 4 31B",
        provider="google",
        input_price=0.12,
        output_price=0.35,
        context_length=262_144,
        supports_vision=True,
        tier="budget",
    ),
    # =========================================================================
    # DEEPSEEK
    # =========================================================================
    "deepseek/deepseek-v3.2": OpenRouterModel(
        id="deepseek/deepseek-v3.2",
        name="DeepSeek V3.2",
        provider="deepseek",
        input_price=0.23,
        output_price=0.34,
        context_length=131_072,
        supports_vision=True,
        tier="budget",
    ),
    "deepseek/deepseek-chat-v3.1": OpenRouterModel(
        id="deepseek/deepseek-chat-v3.1",
        name="DeepSeek V3.1",
        provider="deepseek",
        input_price=0.21,
        output_price=0.79,
        context_length=163_840,
        supports_vision=False,
        tier="budget",
    ),
    "deepseek/deepseek-v4-pro": OpenRouterModel(
        id="deepseek/deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        provider="deepseek",
        input_price=0.44,
        output_price=0.87,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    "deepseek/deepseek-v4-flash": OpenRouterModel(
        id="deepseek/deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        provider="deepseek",
        input_price=0.09,
        output_price=0.18,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    "deepseek/deepseek-r1": OpenRouterModel(
        id="deepseek/deepseek-r1",
        name="DeepSeek R1",
        provider="deepseek",
        input_price=0.70,
        output_price=2.50,
        context_length=163_840,
        supports_vision=False,
        tier="mid",
    ),
    # =========================================================================
    # QWEN (Alibaba Cloud)
    # =========================================================================
    "qwen/qwen3-max": OpenRouterModel(
        id="qwen/qwen3-max",
        name="Qwen3 Max",
        provider="qwen",
        input_price=0.78,
        output_price=3.90,
        context_length=262_144,
        supports_vision=True,
        tier="mid",
    ),
    "qwen/qwen3-max-thinking": OpenRouterModel(
        id="qwen/qwen3-max-thinking",
        name="Qwen3 Max Thinking",
        provider="qwen",
        input_price=0.78,
        output_price=3.90,
        context_length=262_144,
        supports_vision=True,
        tier="mid",
    ),
    "qwen/qwen3.5-plus-20260420": OpenRouterModel(
        id="qwen/qwen3.5-plus-20260420",
        name="Qwen3.5 Plus",
        provider="qwen",
        input_price=0.30,
        output_price=1.80,
        context_length=1_000_000,
        supports_vision=True,
        tier="mid",
    ),
    "qwen/qwen3.5-flash-02-23": OpenRouterModel(
        id="qwen/qwen3.5-flash-02-23",
        name="Qwen3.5 Flash",
        provider="qwen",
        input_price=0.065,
        output_price=0.26,
        context_length=1_000_000,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3.5-9b": OpenRouterModel(
        id="qwen/qwen3.5-9b",
        name="Qwen3.5 9B",
        provider="qwen",
        input_price=0.10,
        output_price=0.15,
        context_length=262_144,
        supports_vision=False,
        tier="budget",
    ),
    "qwen/qwen3.5-27b": OpenRouterModel(
        id="qwen/qwen3.5-27b",
        name="Qwen3.5 27B",
        provider="qwen",
        input_price=0.20,
        output_price=1.56,
        context_length=262_144,
        supports_vision=False,
        tier="budget",
    ),
    "qwen/qwen3.5-35b-a3b": OpenRouterModel(
        id="qwen/qwen3.5-35b-a3b",
        name="Qwen3.5 35B-A3B MoE",
        provider="qwen",
        input_price=0.14,
        output_price=1.00,
        context_length=262_144,
        supports_vision=False,
        tier="budget",
    ),
    "qwen/qwen3.5-122b-a10b": OpenRouterModel(
        id="qwen/qwen3.5-122b-a10b",
        name="Qwen3.5 122B-A10B MoE",
        provider="qwen",
        input_price=0.26,
        output_price=2.08,
        context_length=262_144,
        supports_vision=False,
        tier="mid",
    ),
    "qwen/qwen3.5-397b-a17b": OpenRouterModel(
        id="qwen/qwen3.5-397b-a17b",
        name="Qwen3.5 397B-A17B MoE",
        provider="qwen",
        input_price=0.39,
        output_price=2.45,
        context_length=256_000,
        supports_vision=False,
        tier="mid",
    ),
    "qwen/qwen3.6-plus": OpenRouterModel(
        id="qwen/qwen3.6-plus",
        name="Qwen3.6 Plus",
        provider="qwen",
        input_price=0.33,
        output_price=1.95,
        context_length=1_000_000,
        supports_vision=True,
        tier="mid",
    ),
    "qwen/qwen3.6-flash": OpenRouterModel(
        id="qwen/qwen3.6-flash",
        name="Qwen3.6 Flash",
        provider="qwen",
        input_price=0.19,
        output_price=1.13,
        context_length=1_000_000,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3.7-plus": OpenRouterModel(
        id="qwen/qwen3.7-plus",
        name="Qwen3.7 Plus",
        provider="qwen",
        input_price=0.32,
        output_price=1.28,
        context_length=1_000_000,
        supports_vision=True,
        tier="mid",
    ),
    "qwen/qwen3.7-max": OpenRouterModel(
        id="qwen/qwen3.7-max",
        name="Qwen3.7 Max",
        provider="qwen",
        input_price=1.25,
        output_price=3.75,
        context_length=1_000_000,
        supports_vision=True,
        tier="mid",
    ),
    "qwen/qwen3.7-flash": OpenRouterModel(
        id="qwen/qwen3.7-flash",
        name="Qwen3.7 Flash",
        provider="qwen",
        input_price=0.03,
        output_price=0.13,
        context_length=1_000_000,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3-coder": OpenRouterModel(
        id="qwen/qwen3-coder",
        name="Qwen3 Coder",
        provider="qwen",
        input_price=0.22,
        output_price=1.80,
        context_length=1_048_576,
        supports_vision=False,
        tier="budget",
    ),
    "qwen/qwen3-coder-plus": OpenRouterModel(
        id="qwen/qwen3-coder-plus",
        name="Qwen3 Coder Plus",
        provider="qwen",
        input_price=0.65,
        output_price=3.25,
        context_length=1_000_000,
        supports_vision=False,
        tier="mid",
    ),
    "qwen/qwen3-coder-flash": OpenRouterModel(
        id="qwen/qwen3-coder-flash",
        name="Qwen3 Coder Flash",
        provider="qwen",
        input_price=0.20,
        output_price=0.98,
        context_length=1_000_000,
        supports_vision=False,
        tier="budget",
    ),
    # =========================================================================
    # XAI (Grok)
    # =========================================================================
    "x-ai/grok-4.5": OpenRouterModel(
        id="x-ai/grok-4.5",
        name="Grok 4.5",
        provider="xai",
        input_price=2.00,
        output_price=4.00,
        context_length=2_000_000,
        supports_vision=True,
        tier="mid",
    ),
    "x-ai/grok-4.3": OpenRouterModel(
        id="x-ai/grok-4.3",
        name="Grok 4.3",
        provider="xai",
        input_price=1.25,
        output_price=2.50,
        context_length=1_000_000,
        supports_vision=True,
        tier="mid",
    ),
    # =========================================================================
    # XIAOMI (MIMO)
    # =========================================================================
    "xiaomi/mimo-v2.5": OpenRouterModel(
        id="xiaomi/mimo-v2.5",
        name="MIMO v2.5",
        provider="xiaomi",
        input_price=0.14,
        output_price=0.28,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    "xiaomi/mimo-v2.5-pro": OpenRouterModel(
        id="xiaomi/mimo-v2.5-pro",
        name="MIMO v2.5 Pro",
        provider="xiaomi",
        input_price=0.44,
        output_price=0.87,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    # =========================================================================
    # MOONSHOTAI (KIMI)
    # =========================================================================
    "moonshotai/kimi-k2": OpenRouterModel(
        id="moonshotai/kimi-k2",
        name="Kimi K2",
        provider="moonshotai",
        input_price=0.57,
        output_price=2.30,
        context_length=131_072,
        supports_vision=False,
        tier="mid",
    ),
    "moonshotai/kimi-k2.5": OpenRouterModel(
        id="moonshotai/kimi-k2.5",
        name="Kimi K2.5",
        provider="moonshotai",
        input_price=0.38,
        output_price=2.03,
        context_length=262_144,
        supports_vision=False,
        tier="mid",
    ),
    "moonshotai/kimi-k2.6": OpenRouterModel(
        id="moonshotai/kimi-k2.6",
        name="Kimi K2.6",
        provider="moonshotai",
        input_price=0.66,
        output_price=3.41,
        context_length=262_144,
        supports_vision=False,
        tier="mid",
    ),
    "moonshotai/kimi-k2.7-code": OpenRouterModel(
        id="moonshotai/kimi-k2.7-code",
        name="Kimi K2.7 Code",
        provider="moonshotai",
        input_price=0.61,
        output_price=3.07,
        context_length=262_144,
        supports_vision=False,
        tier="mid",
    ),
    # =========================================================================
    # MINIMAX
    # =========================================================================
    "minimax/minimax-m2.5": OpenRouterModel(
        id="minimax/minimax-m2.5",
        name="MiniMax M2.5",
        provider="minimax",
        input_price=0.15,
        output_price=0.90,
        context_length=204_800,
        supports_vision=True,
        tier="budget",
    ),
    "minimax/minimax-m2.7": OpenRouterModel(
        id="minimax/minimax-m2.7",
        name="MiniMax M2.7",
        provider="minimax",
        input_price=0.25,
        output_price=1.00,
        context_length=204_800,
        supports_vision=True,
        tier="budget",
    ),
    "minimax/minimax-m3": OpenRouterModel(
        id="minimax/minimax-m3",
        name="MiniMax M3",
        provider="minimax",
        input_price=0.30,
        output_price=1.20,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    "minimax/minimax-m1": OpenRouterModel(
        id="minimax/minimax-m1",
        name="MiniMax M1",
        provider="minimax",
        input_price=0.20,
        output_price=1.10,
        context_length=1_000_000,
        supports_vision=True,
        tier="budget",
    ),
    # =========================================================================
    # Z-AI (GLM)
    # =========================================================================
    "z-ai/glm-4.5": OpenRouterModel(
        id="z-ai/glm-4.5",
        name="GLM-4.5",
        provider="z-ai",
        input_price=0.60,
        output_price=2.20,
        context_length=131_072,
        supports_vision=True,
        tier="mid",
    ),
    "z-ai/glm-4.5-air": OpenRouterModel(
        id="z-ai/glm-4.5-air",
        name="GLM-4.5 Air",
        provider="z-ai",
        input_price=0.13,
        output_price=0.85,
        context_length=131_072,
        supports_vision=False,
        tier="budget",
    ),
    "z-ai/glm-4.7": OpenRouterModel(
        id="z-ai/glm-4.7",
        name="GLM-4.7",
        provider="z-ai",
        input_price=0.40,
        output_price=1.75,
        context_length=202_752,
        supports_vision=False,
        tier="mid",
    ),
    "z-ai/glm-4.7-flash": OpenRouterModel(
        id="z-ai/glm-4.7-flash",
        name="GLM-4.7 Flash",
        provider="z-ai",
        input_price=0.06,
        output_price=0.40,
        context_length=202_752,
        supports_vision=False,
        tier="budget",
    ),
    "z-ai/glm-5": OpenRouterModel(
        id="z-ai/glm-5",
        name="GLM-5",
        provider="z-ai",
        input_price=0.60,
        output_price=1.92,
        context_length=202_752,
        supports_vision=False,
        tier="mid",
    ),
    "z-ai/glm-5.1": OpenRouterModel(
        id="z-ai/glm-5.1",
        name="GLM-5.1",
        provider="z-ai",
        input_price=0.98,
        output_price=3.08,
        context_length=202_752,
        supports_vision=False,
        tier="mid",
    ),
    "z-ai/glm-5.2": OpenRouterModel(
        id="z-ai/glm-5.2",
        name="GLM-5.2",
        provider="z-ai",
        input_price=0.98,
        output_price=3.08,
        context_length=1_048_576,
        supports_vision=False,
        tier="mid",
    ),
    # =========================================================================
    # PERPLEXITY
    # =========================================================================
    "perplexity/sonar": OpenRouterModel(
        id="perplexity/sonar",
        name="Sonar",
        provider="perplexity",
        input_price=1.00,
        output_price=1.00,
        context_length=127_072,
        supports_vision=False,
        tier="mid",
    ),
    "perplexity/sonar-pro": OpenRouterModel(
        id="perplexity/sonar-pro",
        name="Sonar Pro",
        provider="perplexity",
        input_price=3.00,
        output_price=15.00,
        context_length=200_000,
        supports_vision=False,
        tier="premium",
    ),
    "perplexity/sonar-pro-search": OpenRouterModel(
        id="perplexity/sonar-pro-search",
        name="Sonar Pro Search",
        provider="perplexity",
        input_price=3.00,
        output_price=15.00,
        context_length=200_000,
        supports_vision=False,
        tier="premium",
    ),
    "perplexity/sonar-reasoning-pro": OpenRouterModel(
        id="perplexity/sonar-reasoning-pro",
        name="Sonar Reasoning Pro",
        provider="perplexity",
        input_price=2.00,
        output_price=8.00,
        context_length=128_000,
        supports_vision=False,
        tier="mid",
    ),
    "perplexity/sonar-deep-research": OpenRouterModel(
        id="perplexity/sonar-deep-research",
        name="Sonar Deep Research",
        provider="perplexity",
        input_price=2.00,
        output_price=8.00,
        context_length=128_000,
        supports_vision=False,
        tier="mid",
    ),
    # =========================================================================
    # META (Llama)
    # =========================================================================
    "meta-llama/llama-4-maverick": OpenRouterModel(
        id="meta-llama/llama-4-maverick",
        name="Llama 4 Maverick",
        provider="meta-llama",
        input_price=0.15,
        output_price=0.60,
        context_length=1_048_576,
        supports_vision=True,
        tier="budget",
    ),
    "meta-llama/llama-4-scout": OpenRouterModel(
        id="meta-llama/llama-4-scout",
        name="Llama 4 Scout",
        provider="meta-llama",
        input_price=0.10,
        output_price=0.30,
        context_length=10_000_000,
        supports_vision=True,
        tier="budget",
    ),
    # =========================================================================
    # AMAZON (Nova)
    # =========================================================================
    "amazon/nova-2-lite-v1": OpenRouterModel(
        id="amazon/nova-2-lite-v1",
        name="Nova 2 Lite",
        provider="amazon",
        input_price=0.30,
        output_price=2.50,
        context_length=1_000_000,
        supports_vision=True,
        tier="budget",
    ),
    "amazon/nova-pro-v1": OpenRouterModel(
        id="amazon/nova-pro-v1",
        name="Nova Pro",
        provider="amazon",
        input_price=0.80,
        output_price=3.20,
        context_length=300_000,
        supports_vision=True,
        tier="mid",
    ),
    "amazon/nova-premier-v1": OpenRouterModel(
        id="amazon/nova-premier-v1",
        name="Nova Premier",
        provider="amazon",
        input_price=2.50,
        output_price=12.50,
        context_length=1_000_000,
        supports_vision=True,
        tier="premium",
    ),
    # =========================================================================
    # MISTRAL
    # =========================================================================
    "mistralai/mistral-large": OpenRouterModel(
        id="mistralai/mistral-large",
        name="Mistral Large",
        provider="mistralai",
        input_price=2.00,
        output_price=6.00,
        context_length=128_000,
        supports_vision=True,
        tier="premium",
    ),
    "mistralai/mistral-medium-3-5": OpenRouterModel(
        id="mistralai/mistral-medium-3-5",
        name="Mistral Medium 3.5",
        provider="mistralai",
        input_price=1.50,
        output_price=7.50,
        context_length=262_144,
        supports_vision=True,
        tier="mid",
    ),
    "mistralai/mistral-small-3.2-24b-instruct": OpenRouterModel(
        id="mistralai/mistral-small-3.2-24b-instruct",
        name="Mistral Small 3.2 24B",
        provider="mistralai",
        input_price=0.08,
        output_price=0.20,
        context_length=128_000,
        supports_vision=True,
        tier="budget",
    ),
    # =========================================================================
    # OTHER NOTABLE PROVIDERS
    # =========================================================================
    "nvidia/nemotron-3-super-120b-a12b": OpenRouterModel(
        id="nvidia/nemotron-3-super-120b-a12b",
        name="Nemotron 3 Super 120B",
        provider="nvidia",
        input_price=0.09,
        output_price=0.45,
        context_length=1_000_000,
        supports_vision=False,
        tier="budget",
    ),
    "cohere/command-a": OpenRouterModel(
        id="cohere/command-a",
        name="Command A",
        provider="cohere",
        input_price=2.50,
        output_price=10.00,
        context_length=256_000,
        supports_vision=False,
        tier="premium",
    ),
    "bytedance-seed/seed-2.0-mini": OpenRouterModel(
        id="bytedance-seed/seed-2.0-mini",
        name="Seed 2.0 Mini",
        provider="bytedance-seed",
        input_price=0.10,
        output_price=0.40,
        context_length=262_144,
        supports_vision=False,
        tier="budget",
    ),
    # ===========================================================================
    # AI21
    # ===========================================================================
    "ai21/jamba-large-1.7": OpenRouterModel(
        id="ai21/jamba-large-1.7",
        name="Jamba Large 1.7",
        provider="ai21",
        input_price=2.0,
        output_price=8.0,
        context_length=256000,
        tier="mid",
    ),
    # ===========================================================================
    # AION LABS
    # ===========================================================================
    "aion-labs/aion-2.0": OpenRouterModel(
        id="aion-labs/aion-2.0",
        name="Aion-2.0",
        provider="aion-labs",
        input_price=0.8,
        output_price=1.6,
        context_length=131072,
        tier="mid",
    ),
    "aion-labs/aion-3.0": OpenRouterModel(
        id="aion-labs/aion-3.0",
        name="Aion-3.0",
        provider="aion-labs",
        input_price=3.0,
        output_price=6.0,
        context_length=131072,
        tier="premium",
    ),
    "aion-labs/aion-3.0-mini": OpenRouterModel(
        id="aion-labs/aion-3.0-mini",
        name="Aion-3.0-Mini",
        provider="aion-labs",
        input_price=0.7,
        output_price=1.4,
        context_length=131072,
        tier="mid",
    ),
    "aion-labs/aion-rp-llama-3.1-8b": OpenRouterModel(
        id="aion-labs/aion-rp-llama-3.1-8b",
        name="Aion-RP 1.0 (8B)",
        provider="aion-labs",
        input_price=0.8,
        output_price=1.6,
        context_length=32768,
        supports_json=False,
        tier="mid",
    ),
    # ===========================================================================
    # ALLENAI
    # ===========================================================================
    "allenai/olmo-3-32b-think": OpenRouterModel(
        id="allenai/olmo-3-32b-think",
        name="Olmo 3 32B Think",
        provider="allenai",
        input_price=0.15,
        output_price=0.5,
        context_length=65536,
        tier="budget",
    ),
    # ===========================================================================
    # AMAZON
    # ===========================================================================
    "amazon/nova-lite-v1": OpenRouterModel(
        id="amazon/nova-lite-v1",
        name="Nova Lite 1.0",
        provider="amazon",
        input_price=0.06,
        output_price=0.24,
        context_length=300000,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    "amazon/nova-micro-v1": OpenRouterModel(
        id="amazon/nova-micro-v1",
        name="Nova Micro 1.0",
        provider="amazon",
        input_price=0.035,
        output_price=0.14,
        context_length=128000,
        supports_json=False,
        tier="budget",
    ),
    # ===========================================================================
    # ANTHRACITE ORG
    # ===========================================================================
    "anthracite-org/magnum-v4-72b": OpenRouterModel(
        id="anthracite-org/magnum-v4-72b",
        name="Magnum v4 72B",
        provider="anthracite-org",
        input_price=3.0,
        output_price=5.0,
        context_length=16384,
        tier="premium",
    ),
    # ===========================================================================
    # ANTHROPIC
    # ===========================================================================
    "anthropic/claude-3-haiku": OpenRouterModel(
        id="anthropic/claude-3-haiku",
        name="Claude 3 Haiku",
        provider="anthropic",
        input_price=0.25,
        output_price=1.25,
        context_length=200000,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    "anthropic/claude-opus-4": OpenRouterModel(
        id="anthropic/claude-opus-4",
        name="Claude Opus 4",
        provider="anthropic",
        input_price=15.0,
        output_price=75.0,
        context_length=200000,
        supports_vision=True,
        supports_json=False,
        tier="premium",
    ),
    "anthropic/claude-opus-5": OpenRouterModel(
        id="anthropic/claude-opus-5",
        name="Claude Opus 5",
        provider="anthropic",
        input_price=5.0,
        output_price=25.0,
        context_length=1000000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-opus-5-fast": OpenRouterModel(
        id="anthropic/claude-opus-5-fast",
        name="Claude Opus 5 (Fast)",
        provider="anthropic",
        input_price=10.0,
        output_price=50.0,
        context_length=1000000,
        supports_vision=True,
        tier="premium",
    ),
    "anthropic/claude-sonnet-4": OpenRouterModel(
        id="anthropic/claude-sonnet-4",
        name="Claude Sonnet 4",
        provider="anthropic",
        input_price=3.0,
        output_price=15.0,
        context_length=1000000,
        supports_vision=True,
        supports_json=False,
        tier="premium",
    ),
    "anthropic/claude-sonnet-5": OpenRouterModel(
        id="anthropic/claude-sonnet-5",
        name="Claude Sonnet 5",
        provider="anthropic",
        input_price=2.0,
        output_price=10.0,
        context_length=1000000,
        supports_vision=True,
        tier="mid",
    ),
    # ===========================================================================
    # ARCEE AI
    # ===========================================================================
    "arcee-ai/trinity-large-thinking": OpenRouterModel(
        id="arcee-ai/trinity-large-thinking",
        name="Trinity Large Thinking",
        provider="arcee-ai",
        input_price=0.22,
        output_price=0.85,
        context_length=262144,
        tier="budget",
    ),
    "arcee-ai/virtuoso-large": OpenRouterModel(
        id="arcee-ai/virtuoso-large",
        name="Virtuoso Large",
        provider="arcee-ai",
        input_price=0.75,
        output_price=1.2,
        context_length=131072,
        supports_json=False,
        tier="mid",
    ),
    # ===========================================================================
    # BAIDU
    # ===========================================================================
    "baidu/ernie-4.5-vl-424b-a47b": OpenRouterModel(
        id="baidu/ernie-4.5-vl-424b-a47b",
        name="ERNIE 4.5 VL 424B A47B ",
        provider="baidu",
        input_price=0.42,
        output_price=1.25,
        context_length=123000,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    # ===========================================================================
    # BYTEDANCE
    # ===========================================================================
    "bytedance/ui-tars-1.5-7b": OpenRouterModel(
        id="bytedance/ui-tars-1.5-7b",
        name="UI-TARS 7B ",
        provider="bytedance",
        input_price=0.1,
        output_price=0.2,
        context_length=128000,
        supports_vision=True,
        tier="budget",
    ),
    # ===========================================================================
    # BYTEDANCE SEED
    # ===========================================================================
    "bytedance-seed/seed-1.6": OpenRouterModel(
        id="bytedance-seed/seed-1.6",
        name="Seed 1.6",
        provider="bytedance-seed",
        input_price=0.25,
        output_price=2.0,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "bytedance-seed/seed-1.6-flash": OpenRouterModel(
        id="bytedance-seed/seed-1.6-flash",
        name="Seed 1.6 Flash",
        provider="bytedance-seed",
        input_price=0.075,
        output_price=0.3,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "bytedance-seed/seed-2.0-lite": OpenRouterModel(
        id="bytedance-seed/seed-2.0-lite",
        name="Seed-2.0-Lite",
        provider="bytedance-seed",
        input_price=0.25,
        output_price=2.0,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    # ===========================================================================
    # COGNITIVECOMPUTATIONS
    # ===========================================================================
    "cognitivecomputations/dolphin-mistral-24b-venice-edition": OpenRouterModel(
        id="cognitivecomputations/dolphin-mistral-24b-venice-edition",
        name="Uncensored",
        provider="cognitivecomputations",
        input_price=0.2,
        output_price=0.9,
        context_length=128000,
        tier="budget",
    ),
    # ===========================================================================
    # COHERE
    # ===========================================================================
    "cohere/command-r-08-2024": OpenRouterModel(
        id="cohere/command-r-08-2024",
        name="Command R (08-2024)",
        provider="cohere",
        input_price=0.15,
        output_price=0.6,
        context_length=128000,
        tier="budget",
    ),
    "cohere/command-r-plus-08-2024": OpenRouterModel(
        id="cohere/command-r-plus-08-2024",
        name="Command R+ (08-2024)",
        provider="cohere",
        input_price=2.5,
        output_price=10.0,
        context_length=128000,
        tier="premium",
    ),
    "cohere/command-r7b-12-2024": OpenRouterModel(
        id="cohere/command-r7b-12-2024",
        name="Command R7B (12-2024)",
        provider="cohere",
        input_price=0.0375,
        output_price=0.15,
        context_length=128000,
        tier="budget",
    ),
    "cohere/north-mini-code:free": OpenRouterModel(
        id="cohere/north-mini-code:free",
        name="North Mini Code (free)",
        provider="cohere",
        input_price=0.0,
        output_price=0.0,
        context_length=256000,
        supports_json=False,
        tier="budget",
    ),
    # ===========================================================================
    # DEEPCOGITO
    # ===========================================================================
    "deepcogito/cogito-v2.1-671b": OpenRouterModel(
        id="deepcogito/cogito-v2.1-671b",
        name="Cogito v2.1 671B",
        provider="deepcogito",
        input_price=1.25,
        output_price=1.25,
        context_length=128000,
        tier="mid",
    ),
    # ===========================================================================
    # DEEPSEEK
    # ===========================================================================
    "deepseek/deepseek-chat": OpenRouterModel(
        id="deepseek/deepseek-chat",
        name="DeepSeek V3",
        provider="deepseek",
        input_price=0.2574,
        output_price=1.0287,
        context_length=163840,
        tier="budget",
    ),
    "deepseek/deepseek-chat-v3-0324": OpenRouterModel(
        id="deepseek/deepseek-chat-v3-0324",
        name="DeepSeek V3 0324",
        provider="deepseek",
        input_price=0.27,
        output_price=1.12,
        context_length=163840,
        tier="budget",
    ),
    "deepseek/deepseek-r1-0528": OpenRouterModel(
        id="deepseek/deepseek-r1-0528",
        name="R1 0528",
        provider="deepseek",
        input_price=0.5,
        output_price=2.15,
        context_length=163840,
        tier="mid",
    ),
    "deepseek/deepseek-r1-distill-llama-70b": OpenRouterModel(
        id="deepseek/deepseek-r1-distill-llama-70b",
        name="R1 Distill Llama 70B",
        provider="deepseek",
        input_price=0.8,
        output_price=0.8,
        context_length=8192,
        supports_json=False,
        tier="mid",
    ),
    "deepseek/deepseek-v3.1-terminus": OpenRouterModel(
        id="deepseek/deepseek-v3.1-terminus",
        name="DeepSeek V3.1 Terminus",
        provider="deepseek",
        input_price=0.27,
        output_price=1.0,
        context_length=163840,
        tier="budget",
    ),
    "deepseek/deepseek-v3.2-exp": OpenRouterModel(
        id="deepseek/deepseek-v3.2-exp",
        name="DeepSeek V3.2 Exp",
        provider="deepseek",
        input_price=0.27,
        output_price=0.41,
        context_length=163840,
        tier="budget",
    ),
    "deepseek/deepseek-v4-flash-0731": OpenRouterModel(
        id="deepseek/deepseek-v4-flash-0731",
        name="DeepSeek V4 Flash 0731",
        provider="deepseek",
        input_price=0.14,
        output_price=0.28,
        context_length=1048576,
        tier="budget",
    ),
    # ===========================================================================
    # GOOGLE
    # ===========================================================================
    "google/gemini-2.5-flash-image": OpenRouterModel(
        id="google/gemini-2.5-flash-image",
        name="Nano Banana (Gemini 2.5 Flash Image)",
        provider="google",
        input_price=0.3,
        output_price=2.5,
        context_length=32768,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemini-2.5-pro-preview": OpenRouterModel(
        id="google/gemini-2.5-pro-preview",
        name="Gemini 2.5 Pro Preview 06-05",
        provider="google",
        input_price=1.25,
        output_price=10.0,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-2.5-pro-preview-05-06": OpenRouterModel(
        id="google/gemini-2.5-pro-preview-05-06",
        name="Gemini 2.5 Pro Preview 05-06",
        provider="google",
        input_price=1.25,
        output_price=10.0,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3-pro-image": OpenRouterModel(
        id="google/gemini-3-pro-image",
        name="Nano Banana Pro (Gemini 3 Pro Image)",
        provider="google",
        input_price=2.0,
        output_price=12.0,
        context_length=131072,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3-pro-image-preview": OpenRouterModel(
        id="google/gemini-3-pro-image-preview",
        name="Nano Banana Pro (Gemini 3 Pro Image Preview)",
        provider="google",
        input_price=2.0,
        output_price=12.0,
        context_length=65536,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3.1-flash-image": OpenRouterModel(
        id="google/gemini-3.1-flash-image",
        name="Nano Banana 2 (Gemini 3.1 Flash Image)",
        provider="google",
        input_price=0.5,
        output_price=3.0,
        context_length=131072,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3.1-flash-image-preview": OpenRouterModel(
        id="google/gemini-3.1-flash-image-preview",
        name="Nano Banana 2 (Gemini 3.1 Flash Image Preview)",
        provider="google",
        input_price=0.5,
        output_price=3.0,
        context_length=65536,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3.1-flash-lite-image": OpenRouterModel(
        id="google/gemini-3.1-flash-lite-image",
        name="Nano Banana 2 Lite (Gemini 3.1 Flash Lite Image)",
        provider="google",
        input_price=0.25,
        output_price=1.5,
        context_length=65536,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemini-3.1-flash-lite-preview": OpenRouterModel(
        id="google/gemini-3.1-flash-lite-preview",
        name="Gemini 3.1 Flash Lite Preview",
        provider="google",
        input_price=0.25,
        output_price=1.5,
        context_length=1048576,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemini-3.1-pro-preview": OpenRouterModel(
        id="google/gemini-3.1-pro-preview",
        name="Gemini 3.1 Pro Preview",
        provider="google",
        input_price=2.0,
        output_price=12.0,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3.1-pro-preview-customtools": OpenRouterModel(
        id="google/gemini-3.1-pro-preview-customtools",
        name="Gemini 3.1 Pro Preview Custom Tools",
        provider="google",
        input_price=2.0,
        output_price=12.0,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemini-3.5-flash-lite": OpenRouterModel(
        id="google/gemini-3.5-flash-lite",
        name="Gemini 3.5 Flash Lite",
        provider="google",
        input_price=0.3,
        output_price=2.5,
        context_length=1048576,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemini-3.6-flash": OpenRouterModel(
        id="google/gemini-3.6-flash",
        name="Gemini 3.6 Flash",
        provider="google",
        input_price=1.5,
        output_price=7.5,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    "google/gemma-2-27b-it": OpenRouterModel(
        id="google/gemma-2-27b-it",
        name="Gemma 2 27B",
        provider="google",
        input_price=0.65,
        output_price=0.65,
        context_length=8192,
        tier="mid",
    ),
    "google/gemma-3-12b-it": OpenRouterModel(
        id="google/gemma-3-12b-it",
        name="Gemma 3 12B",
        provider="google",
        input_price=0.05,
        output_price=0.15,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemma-3-27b-it": OpenRouterModel(
        id="google/gemma-3-27b-it",
        name="Gemma 3 27B",
        provider="google",
        input_price=0.08,
        output_price=0.45,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemma-3-4b-it": OpenRouterModel(
        id="google/gemma-3-4b-it",
        name="Gemma 3 4B",
        provider="google",
        input_price=0.05,
        output_price=0.1,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemma-3n-e4b-it": OpenRouterModel(
        id="google/gemma-3n-e4b-it",
        name="Gemma 3n 4B",
        provider="google",
        input_price=0.06,
        output_price=0.12,
        context_length=32768,
        tier="budget",
    ),
    "google/gemma-4-26b-a4b-it:free": OpenRouterModel(
        id="google/gemma-4-26b-a4b-it:free",
        name="Gemma 4 26B A4B  (free)",
        provider="google",
        input_price=0.0,
        output_price=0.0,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "google/gemma-4-31b-it:free": OpenRouterModel(
        id="google/gemma-4-31b-it:free",
        name="Gemma 4 31B (free)",
        provider="google",
        input_price=0.0,
        output_price=0.0,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "google/lyria-3-clip-preview": OpenRouterModel(
        id="google/lyria-3-clip-preview",
        name="Lyria 3 Clip Preview",
        provider="google",
        input_price=0.0,
        output_price=0.0,
        context_length=1048576,
        supports_vision=True,
        tier="budget",
    ),
    "google/lyria-3-pro-preview": OpenRouterModel(
        id="google/lyria-3-pro-preview",
        name="Lyria 3 Pro Preview",
        provider="google",
        input_price=0.0,
        output_price=0.0,
        context_length=1048576,
        supports_vision=True,
        tier="budget",
    ),
    # ===========================================================================
    # GRYPHE
    # ===========================================================================
    "gryphe/mythomax-l2-13b": OpenRouterModel(
        id="gryphe/mythomax-l2-13b",
        name="MythoMax 13B",
        provider="gryphe",
        input_price=0.06,
        output_price=0.06,
        context_length=8192,
        tier="budget",
    ),
    # ===========================================================================
    # IBM GRANITE
    # ===========================================================================
    "ibm-granite/granite-4.0-h-micro": OpenRouterModel(
        id="ibm-granite/granite-4.0-h-micro",
        name="Granite 4.0 Micro",
        provider="ibm-granite",
        input_price=0.017,
        output_price=0.112,
        context_length=131000,
        tier="budget",
    ),
    "ibm-granite/granite-4.1-8b": OpenRouterModel(
        id="ibm-granite/granite-4.1-8b",
        name="Granite 4.1 8B",
        provider="ibm-granite",
        input_price=0.05,
        output_price=0.1,
        context_length=131072,
        tier="budget",
    ),
    # ===========================================================================
    # INCEPTION
    # ===========================================================================
    "inception/mercury-2": OpenRouterModel(
        id="inception/mercury-2",
        name="Mercury 2",
        provider="inception",
        input_price=0.25,
        output_price=0.75,
        context_length=128000,
        tier="budget",
    ),
    # ===========================================================================
    # INCLUSIONAI
    # ===========================================================================
    "inclusionai/ling-2.6-1t": OpenRouterModel(
        id="inclusionai/ling-2.6-1t",
        name="Ling-2.6-1T",
        provider="inclusionai",
        input_price=0.075,
        output_price=0.625,
        context_length=262144,
        tier="budget",
    ),
    "inclusionai/ling-2.6-flash": OpenRouterModel(
        id="inclusionai/ling-2.6-flash",
        name="Ling-2.6-flash",
        provider="inclusionai",
        input_price=0.01,
        output_price=0.03,
        context_length=262144,
        tier="budget",
    ),
    "inclusionai/ling-3.0-flash:free": OpenRouterModel(
        id="inclusionai/ling-3.0-flash:free",
        name="Ling-3.0-flash (free)",
        provider="inclusionai",
        input_price=0.0,
        output_price=0.0,
        context_length=262144,
        supports_json=False,
        tier="budget",
    ),
    "inclusionai/ring-2.6-1t": OpenRouterModel(
        id="inclusionai/ring-2.6-1t",
        name="Ring-2.6-1T",
        provider="inclusionai",
        input_price=0.075,
        output_price=0.625,
        context_length=262144,
        tier="budget",
    ),
    # ===========================================================================
    # KWAIPILOT
    # ===========================================================================
    "kwaipilot/kat-coder-air-v2.5": OpenRouterModel(
        id="kwaipilot/kat-coder-air-v2.5",
        name="KAT-Coder-Air V2.5",
        provider="kwaipilot",
        input_price=0.15,
        output_price=0.6,
        context_length=256000,
        tier="budget",
    ),
    "kwaipilot/kat-coder-pro-v2": OpenRouterModel(
        id="kwaipilot/kat-coder-pro-v2",
        name="KAT-Coder-Pro V2",
        provider="kwaipilot",
        input_price=0.3,
        output_price=1.2,
        context_length=262144,
        tier="budget",
    ),
    "kwaipilot/kat-coder-pro-v2.5": OpenRouterModel(
        id="kwaipilot/kat-coder-pro-v2.5",
        name="KAT-Coder-Pro V2.5",
        provider="kwaipilot",
        input_price=0.74,
        output_price=2.96,
        context_length=256000,
        tier="mid",
    ),
    # ===========================================================================
    # MANCER
    # ===========================================================================
    "mancer/weaver": OpenRouterModel(
        id="mancer/weaver",
        name="Weaver (alpha)",
        provider="mancer",
        input_price=0.5,
        output_price=0.75,
        context_length=8000,
        tier="mid",
    ),
    # ===========================================================================
    # MEITUAN
    # ===========================================================================
    "meituan/longcat-2.0": OpenRouterModel(
        id="meituan/longcat-2.0",
        name="LongCat 2.0",
        provider="meituan",
        input_price=0.3,
        output_price=1.2,
        context_length=1048756,
        supports_json=False,
        tier="budget",
    ),
    # ===========================================================================
    # META
    # ===========================================================================
    "meta/muse-spark-1.1": OpenRouterModel(
        id="meta/muse-spark-1.1",
        name="Muse Spark 1.1",
        provider="meta",
        input_price=1.25,
        output_price=4.25,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    # ===========================================================================
    # META LLAMA
    # ===========================================================================
    "meta-llama/llama-3.1-70b-instruct": OpenRouterModel(
        id="meta-llama/llama-3.1-70b-instruct",
        name="Llama 3.1 70B Instruct",
        provider="meta-llama",
        input_price=0.4,
        output_price=0.4,
        context_length=131072,
        tier="budget",
    ),
    "meta-llama/llama-3.1-8b-instruct": OpenRouterModel(
        id="meta-llama/llama-3.1-8b-instruct",
        name="Llama 3.1 8B Instruct",
        provider="meta-llama",
        input_price=0.05,
        output_price=0.08,
        context_length=131072,
        tier="budget",
    ),
    "meta-llama/llama-3.2-1b-instruct": OpenRouterModel(
        id="meta-llama/llama-3.2-1b-instruct",
        name="Llama 3.2 1B Instruct",
        provider="meta-llama",
        input_price=0.027,
        output_price=0.201,
        context_length=60000,
        supports_json=False,
        tier="budget",
    ),
    "meta-llama/llama-3.2-3b-instruct": OpenRouterModel(
        id="meta-llama/llama-3.2-3b-instruct",
        name="Llama 3.2 3B Instruct",
        provider="meta-llama",
        input_price=0.05,
        output_price=0.33,
        context_length=131072,
        tier="budget",
    ),
    "meta-llama/llama-3.3-70b-instruct": OpenRouterModel(
        id="meta-llama/llama-3.3-70b-instruct",
        name="Llama 3.3 70B Instruct",
        provider="meta-llama",
        input_price=0.13,
        output_price=0.4,
        context_length=131072,
        tier="budget",
    ),
    "meta-llama/llama-guard-4-12b": OpenRouterModel(
        id="meta-llama/llama-guard-4-12b",
        name="Llama Guard 4 12B",
        provider="meta-llama",
        input_price=0.18,
        output_price=0.18,
        context_length=1048576,
        supports_vision=True,
        tier="budget",
    ),
    # ===========================================================================
    # MICROSOFT
    # ===========================================================================
    "microsoft/phi-4": OpenRouterModel(
        id="microsoft/phi-4",
        name="Phi 4",
        provider="microsoft",
        input_price=0.07,
        output_price=0.14,
        context_length=16384,
        tier="budget",
    ),
    "microsoft/wizardlm-2-8x22b": OpenRouterModel(
        id="microsoft/wizardlm-2-8x22b",
        name="WizardLM-2 8x22B",
        provider="microsoft",
        input_price=0.62,
        output_price=0.62,
        context_length=65535,
        tier="mid",
    ),
    # ===========================================================================
    # MINIMAX
    # ===========================================================================
    "minimax/minimax-01": OpenRouterModel(
        id="minimax/minimax-01",
        name="MiniMax-01",
        provider="minimax",
        input_price=0.2,
        output_price=1.1,
        context_length=1000192,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    "minimax/minimax-m2": OpenRouterModel(
        id="minimax/minimax-m2",
        name="MiniMax M2",
        provider="minimax",
        input_price=0.255,
        output_price=1.02,
        context_length=204800,
        tier="budget",
    ),
    "minimax/minimax-m2-her": OpenRouterModel(
        id="minimax/minimax-m2-her",
        name="MiniMax M2-her",
        provider="minimax",
        input_price=0.3,
        output_price=1.2,
        context_length=65536,
        supports_json=False,
        tier="budget",
    ),
    "minimax/minimax-m2.1": OpenRouterModel(
        id="minimax/minimax-m2.1",
        name="MiniMax M2.1",
        provider="minimax",
        input_price=0.3,
        output_price=1.2,
        context_length=204800,
        tier="budget",
    ),
    # ===========================================================================
    # MISTRALAI
    # ===========================================================================
    "mistralai/codestral-2508": OpenRouterModel(
        id="mistralai/codestral-2508",
        name="Codestral 2508",
        provider="mistralai",
        input_price=0.3,
        output_price=0.9,
        context_length=256000,
        tier="budget",
    ),
    "mistralai/ministral-14b-2512": OpenRouterModel(
        id="mistralai/ministral-14b-2512",
        name="Ministral 3 14B 2512",
        provider="mistralai",
        input_price=0.2,
        output_price=0.2,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "mistralai/ministral-3b-2512": OpenRouterModel(
        id="mistralai/ministral-3b-2512",
        name="Ministral 3 3B 2512",
        provider="mistralai",
        input_price=0.1,
        output_price=0.1,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "mistralai/ministral-8b-2512": OpenRouterModel(
        id="mistralai/ministral-8b-2512",
        name="Ministral 3 8B 2512",
        provider="mistralai",
        input_price=0.15,
        output_price=0.15,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "mistralai/mistral-large-2407": OpenRouterModel(
        id="mistralai/mistral-large-2407",
        name="Mistral Large 2407",
        provider="mistralai",
        input_price=2.0,
        output_price=6.0,
        context_length=131072,
        tier="mid",
    ),
    "mistralai/mistral-large-2512": OpenRouterModel(
        id="mistralai/mistral-large-2512",
        name="Mistral Large 3 2512",
        provider="mistralai",
        input_price=0.5,
        output_price=1.5,
        context_length=262144,
        supports_vision=True,
        tier="mid",
    ),
    "mistralai/mistral-medium-3": OpenRouterModel(
        id="mistralai/mistral-medium-3",
        name="Mistral Medium 3",
        provider="mistralai",
        input_price=0.4,
        output_price=2.0,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "mistralai/mistral-medium-3.1": OpenRouterModel(
        id="mistralai/mistral-medium-3.1",
        name="Mistral Medium 3.1",
        provider="mistralai",
        input_price=0.4,
        output_price=2.0,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "mistralai/mistral-nemo": OpenRouterModel(
        id="mistralai/mistral-nemo",
        name="Mistral Nemo",
        provider="mistralai",
        input_price=0.019,
        output_price=0.03,
        context_length=131072,
        tier="budget",
    ),
    "mistralai/mistral-saba": OpenRouterModel(
        id="mistralai/mistral-saba",
        name="Saba",
        provider="mistralai",
        input_price=0.2,
        output_price=0.6,
        context_length=32768,
        tier="budget",
    ),
    "mistralai/mistral-small-24b-instruct-2501": OpenRouterModel(
        id="mistralai/mistral-small-24b-instruct-2501",
        name="Mistral Small 3",
        provider="mistralai",
        input_price=0.05,
        output_price=0.08,
        context_length=32768,
        tier="budget",
    ),
    "mistralai/mistral-small-2603": OpenRouterModel(
        id="mistralai/mistral-small-2603",
        name="Mistral Small 4",
        provider="mistralai",
        input_price=0.15,
        output_price=0.6,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "mistralai/mistral-small-3.1-24b-instruct": OpenRouterModel(
        id="mistralai/mistral-small-3.1-24b-instruct",
        name="Mistral Small 3.1 24B",
        provider="mistralai",
        input_price=0.351,
        output_price=0.555,
        context_length=128000,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    "mistralai/mixtral-8x22b-instruct": OpenRouterModel(
        id="mistralai/mixtral-8x22b-instruct",
        name="Mixtral 8x22B Instruct",
        provider="mistralai",
        input_price=2.0,
        output_price=6.0,
        context_length=65536,
        tier="mid",
    ),
    "mistralai/voxtral-small-24b-2507": OpenRouterModel(
        id="mistralai/voxtral-small-24b-2507",
        name="Voxtral Small 24B 2507",
        provider="mistralai",
        input_price=0.1,
        output_price=0.3,
        context_length=32000,
        tier="budget",
    ),
    # ===========================================================================
    # MOONSHOTAI
    # ===========================================================================
    "moonshotai/kimi-k2-0905": OpenRouterModel(
        id="moonshotai/kimi-k2-0905",
        name="Kimi K2 0905",
        provider="moonshotai",
        input_price=0.6,
        output_price=2.5,
        context_length=262144,
        tier="mid",
    ),
    "moonshotai/kimi-k2-thinking": OpenRouterModel(
        id="moonshotai/kimi-k2-thinking",
        name="Kimi K2 Thinking",
        provider="moonshotai",
        input_price=0.6,
        output_price=2.5,
        context_length=262144,
        tier="mid",
    ),
    "moonshotai/kimi-k3": OpenRouterModel(
        id="moonshotai/kimi-k3",
        name="Kimi K3",
        provider="moonshotai",
        input_price=3.0,
        output_price=15.0,
        context_length=1048576,
        supports_vision=True,
        tier="premium",
    ),
    # ===========================================================================
    # MORPH
    # ===========================================================================
    "morph/morph-v3-fast": OpenRouterModel(
        id="morph/morph-v3-fast",
        name="Morph V3 Fast",
        provider="morph",
        input_price=0.8,
        output_price=1.2,
        context_length=81920,
        supports_json=False,
        tier="mid",
    ),
    "morph/morph-v3-large": OpenRouterModel(
        id="morph/morph-v3-large",
        name="Morph V3 Large",
        provider="morph",
        input_price=0.9,
        output_price=1.9,
        context_length=262144,
        tier="mid",
    ),
    # ===========================================================================
    # NEX AGI
    # ===========================================================================
    "nex-agi/nex-n2-mini": OpenRouterModel(
        id="nex-agi/nex-n2-mini",
        name="Nex-N2-Mini",
        provider="nex-agi",
        input_price=0.025,
        output_price=0.1,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "nex-agi/nex-n2-pro": OpenRouterModel(
        id="nex-agi/nex-n2-pro",
        name="Nex-N2-Pro",
        provider="nex-agi",
        input_price=0.25,
        output_price=1.0,
        context_length=262144,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    # ===========================================================================
    # NOUSRESEARCH
    # ===========================================================================
    "nousresearch/hermes-3-llama-3.1-405b": OpenRouterModel(
        id="nousresearch/hermes-3-llama-3.1-405b",
        name="Hermes 3 405B Instruct",
        provider="nousresearch",
        input_price=1.0,
        output_price=1.0,
        context_length=131072,
        tier="mid",
    ),
    "nousresearch/hermes-3-llama-3.1-70b": OpenRouterModel(
        id="nousresearch/hermes-3-llama-3.1-70b",
        name="Hermes 3 70B Instruct",
        provider="nousresearch",
        input_price=0.7,
        output_price=0.7,
        context_length=131072,
        tier="mid",
    ),
    "nousresearch/hermes-4-405b": OpenRouterModel(
        id="nousresearch/hermes-4-405b",
        name="Hermes 4 405B",
        provider="nousresearch",
        input_price=1.0,
        output_price=3.0,
        context_length=131072,
        tier="mid",
    ),
    "nousresearch/hermes-4-70b": OpenRouterModel(
        id="nousresearch/hermes-4-70b",
        name="Hermes 4 70B",
        provider="nousresearch",
        input_price=0.13,
        output_price=0.4,
        context_length=131072,
        tier="budget",
    ),
    # ===========================================================================
    # NVIDIA
    # ===========================================================================
    "nvidia/nemotron-3-nano-30b-a3b": OpenRouterModel(
        id="nvidia/nemotron-3-nano-30b-a3b",
        name="Nemotron 3 Nano 30B A3B",
        provider="nvidia",
        input_price=0.05,
        output_price=0.2,
        context_length=262144,
        tier="budget",
    ),
    "nvidia/nemotron-3-nano-30b-a3b:free": OpenRouterModel(
        id="nvidia/nemotron-3-nano-30b-a3b:free",
        name="Nemotron 3 Nano 30B A3B (free)",
        provider="nvidia",
        input_price=0.0,
        output_price=0.0,
        context_length=256000,
        supports_json=False,
        tier="budget",
    ),
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": OpenRouterModel(
        id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        name="Nemotron 3 Nano Omni (free)",
        provider="nvidia",
        input_price=0.0,
        output_price=0.0,
        context_length=256000,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    "nvidia/nemotron-3-super-120b-a12b:free": OpenRouterModel(
        id="nvidia/nemotron-3-super-120b-a12b:free",
        name="Nemotron 3 Super (free)",
        provider="nvidia",
        input_price=0.0,
        output_price=0.0,
        context_length=262144,
        tier="budget",
    ),
    "nvidia/nemotron-3-ultra-550b-a55b": OpenRouterModel(
        id="nvidia/nemotron-3-ultra-550b-a55b",
        name="Nemotron 3 Ultra",
        provider="nvidia",
        input_price=0.6,
        output_price=3.6,
        context_length=512288,
        tier="mid",
    ),
    "nvidia/nemotron-3-ultra-550b-a55b:free": OpenRouterModel(
        id="nvidia/nemotron-3-ultra-550b-a55b:free",
        name="Nemotron 3 Ultra (free)",
        provider="nvidia",
        input_price=0.0,
        output_price=0.0,
        context_length=1000000,
        supports_json=False,
        tier="budget",
    ),
    "nvidia/nemotron-3.5-content-safety:free": OpenRouterModel(
        id="nvidia/nemotron-3.5-content-safety:free",
        name="Nemotron 3.5 Content Safety (free)",
        provider="nvidia",
        input_price=0.0,
        output_price=0.0,
        context_length=128000,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    "nvidia/nemotron-nano-12b-v2-vl:free": OpenRouterModel(
        id="nvidia/nemotron-nano-12b-v2-vl:free",
        name="Nemotron Nano 12B 2 VL (free)",
        provider="nvidia",
        input_price=0.0,
        output_price=0.0,
        context_length=128000,
        supports_vision=True,
        supports_json=False,
        tier="budget",
    ),
    "nvidia/nemotron-nano-9b-v2:free": OpenRouterModel(
        id="nvidia/nemotron-nano-9b-v2:free",
        name="Nemotron Nano 9B V2 (free)",
        provider="nvidia",
        input_price=0.0,
        output_price=0.0,
        context_length=128000,
        tier="budget",
    ),
    # ===========================================================================
    # OPENAI
    # ===========================================================================
    "openai/gpt-3.5-turbo": OpenRouterModel(
        id="openai/gpt-3.5-turbo",
        name="GPT-3.5 Turbo",
        provider="openai",
        input_price=0.5,
        output_price=1.5,
        context_length=16385,
        tier="mid",
    ),
    "openai/gpt-3.5-turbo-0613": OpenRouterModel(
        id="openai/gpt-3.5-turbo-0613",
        name="GPT-3.5 Turbo (older v0613)",
        provider="openai",
        input_price=1.0,
        output_price=2.0,
        context_length=4095,
        tier="mid",
    ),
    "openai/gpt-3.5-turbo-16k": OpenRouterModel(
        id="openai/gpt-3.5-turbo-16k",
        name="GPT-3.5 Turbo 16k",
        provider="openai",
        input_price=3.0,
        output_price=4.0,
        context_length=16385,
        tier="premium",
    ),
    "openai/gpt-3.5-turbo-instruct": OpenRouterModel(
        id="openai/gpt-3.5-turbo-instruct",
        name="GPT-3.5 Turbo Instruct",
        provider="openai",
        input_price=1.5,
        output_price=2.0,
        context_length=4095,
        tier="mid",
    ),
    "openai/gpt-4": OpenRouterModel(
        id="openai/gpt-4",
        name="GPT-4",
        provider="openai",
        input_price=30.0,
        output_price=60.0,
        context_length=8191,
        tier="premium",
    ),
    "openai/gpt-4-turbo": OpenRouterModel(
        id="openai/gpt-4-turbo",
        name="GPT-4 Turbo",
        provider="openai",
        input_price=10.0,
        output_price=30.0,
        context_length=128000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-4-turbo-preview": OpenRouterModel(
        id="openai/gpt-4-turbo-preview",
        name="GPT-4 Turbo Preview",
        provider="openai",
        input_price=10.0,
        output_price=30.0,
        context_length=128000,
        tier="premium",
    ),
    "openai/gpt-4o-2024-05-13": OpenRouterModel(
        id="openai/gpt-4o-2024-05-13",
        name="GPT-4o (2024-05-13)",
        provider="openai",
        input_price=5.0,
        output_price=15.0,
        context_length=128000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-4o-2024-08-06": OpenRouterModel(
        id="openai/gpt-4o-2024-08-06",
        name="GPT-4o (2024-08-06)",
        provider="openai",
        input_price=2.5,
        output_price=10.0,
        context_length=128000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-4o-2024-11-20": OpenRouterModel(
        id="openai/gpt-4o-2024-11-20",
        name="GPT-4o (2024-11-20)",
        provider="openai",
        input_price=2.5,
        output_price=10.0,
        context_length=128000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-4o-mini-2024-07-18": OpenRouterModel(
        id="openai/gpt-4o-mini-2024-07-18",
        name="GPT-4o-mini (2024-07-18)",
        provider="openai",
        input_price=0.15,
        output_price=0.6,
        context_length=128000,
        supports_vision=True,
        tier="budget",
    ),
    "openai/gpt-5-image": OpenRouterModel(
        id="openai/gpt-5-image",
        name="GPT-5 Image",
        provider="openai",
        input_price=10.0,
        output_price=10.0,
        context_length=400000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5-image-mini": OpenRouterModel(
        id="openai/gpt-5-image-mini",
        name="GPT-5 Image Mini",
        provider="openai",
        input_price=2.5,
        output_price=2.0,
        context_length=400000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5-pro": OpenRouterModel(
        id="openai/gpt-5-pro",
        name="GPT-5 Pro",
        provider="openai",
        input_price=15.0,
        output_price=120.0,
        context_length=400000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.1-codex": OpenRouterModel(
        id="openai/gpt-5.1-codex",
        name="GPT-5.1-Codex",
        provider="openai",
        input_price=1.25,
        output_price=10.0,
        context_length=400000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5.1-codex-max": OpenRouterModel(
        id="openai/gpt-5.1-codex-max",
        name="GPT-5.1-Codex-Max",
        provider="openai",
        input_price=1.25,
        output_price=10.0,
        context_length=400000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5.1-codex-mini": OpenRouterModel(
        id="openai/gpt-5.1-codex-mini",
        name="GPT-5.1-Codex-Mini",
        provider="openai",
        input_price=0.25,
        output_price=2.0,
        context_length=400000,
        supports_vision=True,
        tier="budget",
    ),
    "openai/gpt-5.2-chat": OpenRouterModel(
        id="openai/gpt-5.2-chat",
        name="GPT-5.2 Chat",
        provider="openai",
        input_price=1.75,
        output_price=14.0,
        context_length=128000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5.2-pro": OpenRouterModel(
        id="openai/gpt-5.2-pro",
        name="GPT-5.2 Pro",
        provider="openai",
        input_price=21.0,
        output_price=168.0,
        context_length=400000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.3-chat": OpenRouterModel(
        id="openai/gpt-5.3-chat",
        name="GPT-5.3 Chat",
        provider="openai",
        input_price=1.75,
        output_price=14.0,
        context_length=128000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5.3-codex": OpenRouterModel(
        id="openai/gpt-5.3-codex",
        name="GPT-5.3-Codex",
        provider="openai",
        input_price=1.75,
        output_price=14.0,
        context_length=400000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5.4-image-2": OpenRouterModel(
        id="openai/gpt-5.4-image-2",
        name="GPT-5.4 Image 2",
        provider="openai",
        input_price=8.0,
        output_price=15.0,
        context_length=272000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.6-luna": OpenRouterModel(
        id="openai/gpt-5.6-luna",
        name="GPT-5.6 Luna",
        provider="openai",
        input_price=0.1,
        output_price=0.6,
        context_length=1050000,
        supports_vision=True,
        tier="budget",
    ),
    "openai/gpt-5.6-luna-pro": OpenRouterModel(
        id="openai/gpt-5.6-luna-pro",
        name="GPT-5.6 Luna Pro",
        provider="openai",
        input_price=0.1,
        output_price=0.6,
        context_length=1050000,
        supports_vision=True,
        tier="budget",
    ),
    "openai/gpt-5.6-sol": OpenRouterModel(
        id="openai/gpt-5.6-sol",
        name="GPT-5.6 Sol",
        provider="openai",
        input_price=5.0,
        output_price=30.0,
        context_length=1050000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.6-sol-pro": OpenRouterModel(
        id="openai/gpt-5.6-sol-pro",
        name="GPT-5.6 Sol Pro",
        provider="openai",
        input_price=5.0,
        output_price=30.0,
        context_length=1050000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-5.6-terra": OpenRouterModel(
        id="openai/gpt-5.6-terra",
        name="GPT-5.6 Terra",
        provider="openai",
        input_price=1.0,
        output_price=6.0,
        context_length=1050000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-5.6-terra-pro": OpenRouterModel(
        id="openai/gpt-5.6-terra-pro",
        name="GPT-5.6 Terra Pro",
        provider="openai",
        input_price=1.0,
        output_price=6.0,
        context_length=1050000,
        supports_vision=True,
        tier="mid",
    ),
    "openai/gpt-audio": OpenRouterModel(
        id="openai/gpt-audio",
        name="GPT Audio",
        provider="openai",
        input_price=2.5,
        output_price=10.0,
        context_length=128000,
        tier="premium",
    ),
    "openai/gpt-audio-mini": OpenRouterModel(
        id="openai/gpt-audio-mini",
        name="GPT Audio Mini",
        provider="openai",
        input_price=0.6,
        output_price=2.4,
        context_length=128000,
        tier="mid",
    ),
    "openai/gpt-chat-latest": OpenRouterModel(
        id="openai/gpt-chat-latest",
        name="GPT Chat Latest",
        provider="openai",
        input_price=5.0,
        output_price=30.0,
        context_length=400000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/gpt-oss-120b": OpenRouterModel(
        id="openai/gpt-oss-120b",
        name="gpt-oss-120b",
        provider="openai",
        input_price=0.037,
        output_price=0.17,
        context_length=131072,
        tier="budget",
    ),
    "openai/gpt-oss-20b": OpenRouterModel(
        id="openai/gpt-oss-20b",
        name="gpt-oss-20b",
        provider="openai",
        input_price=0.03,
        output_price=0.13,
        context_length=131072,
        tier="budget",
    ),
    "openai/gpt-oss-20b:free": OpenRouterModel(
        id="openai/gpt-oss-20b:free",
        name="gpt-oss-20b (free)",
        provider="openai",
        input_price=0.0,
        output_price=0.0,
        context_length=131072,
        tier="budget",
    ),
    "openai/gpt-oss-safeguard-20b": OpenRouterModel(
        id="openai/gpt-oss-safeguard-20b",
        name="gpt-oss-safeguard-20b",
        provider="openai",
        input_price=0.075,
        output_price=0.3,
        context_length=131072,
        tier="budget",
    ),
    "openai/o1-pro": OpenRouterModel(
        id="openai/o1-pro",
        name="o1-pro",
        provider="openai",
        input_price=150.0,
        output_price=600.0,
        context_length=200000,
        supports_vision=True,
        tier="premium",
    ),
    "openai/o3-mini-high": OpenRouterModel(
        id="openai/o3-mini-high",
        name="o3 Mini High",
        provider="openai",
        input_price=1.1,
        output_price=4.4,
        context_length=200000,
        tier="mid",
    ),
    "openai/o4-mini-high": OpenRouterModel(
        id="openai/o4-mini-high",
        name="o4 Mini High",
        provider="openai",
        input_price=1.1,
        output_price=4.4,
        context_length=200000,
        supports_vision=True,
        tier="mid",
    ),
    # ===========================================================================
    # OPENROUTER
    # ===========================================================================
    "openrouter/auto": OpenRouterModel(
        id="openrouter/auto",
        name="Auto Router",
        provider="openrouter",
        # Dynamic router with no fixed underlying price; 0.0 avoids a negative
        # cost since OpenRouterModel.input_price/output_price is a plain float.
        input_price=0.0,
        output_price=0.0,
        context_length=2000000,
        supports_vision=True,
        tier="budget",
    ),
    "openrouter/auto-beta": OpenRouterModel(
        id="openrouter/auto-beta",
        name="Auto Router (Beta)",
        provider="openrouter",
        # Dynamic router with no fixed underlying price; 0.0 avoids a negative
        # cost since OpenRouterModel.input_price/output_price is a plain float.
        input_price=0.0,
        output_price=0.0,
        context_length=2000000,
        supports_vision=True,
        tier="budget",
    ),
    "openrouter/bodybuilder": OpenRouterModel(
        id="openrouter/bodybuilder",
        name="Body Builder (beta)",
        provider="openrouter",
        # Dynamic router with no fixed underlying price; 0.0 avoids a negative
        # cost since OpenRouterModel.input_price/output_price is a plain float.
        input_price=0.0,
        output_price=0.0,
        context_length=128000,
        supports_json=False,
        tier="budget",
    ),
    "openrouter/free": OpenRouterModel(
        id="openrouter/free",
        name="Free Models Router",
        provider="openrouter",
        input_price=0.0,
        output_price=0.0,
        context_length=200000,
        supports_vision=True,
        tier="budget",
    ),
    "openrouter/fusion": OpenRouterModel(
        id="openrouter/fusion",
        name="Fusion",
        provider="openrouter",
        # Dynamic router with no fixed underlying price; 0.0 avoids a negative
        # cost since OpenRouterModel.input_price/output_price is a plain float.
        input_price=0.0,
        output_price=0.0,
        context_length=1000000,
        supports_json=False,
        tier="budget",
    ),
    "openrouter/pareto-code": OpenRouterModel(
        id="openrouter/pareto-code",
        name="Pareto Code Router",
        provider="openrouter",
        # Dynamic router with no fixed underlying price; 0.0 avoids a negative
        # cost since OpenRouterModel.input_price/output_price is a plain float.
        input_price=0.0,
        output_price=0.0,
        context_length=2000000,
        supports_json=False,
        tier="budget",
    ),
    # ===========================================================================
    # PERCEPTRON
    # ===========================================================================
    "perceptron/perceptron-mk1": OpenRouterModel(
        id="perceptron/perceptron-mk1",
        name="Perceptron Mk1",
        provider="perceptron",
        input_price=0.15,
        output_price=1.5,
        context_length=32768,
        supports_vision=True,
        tier="budget",
    ),
    # ===========================================================================
    # POOLSIDE
    # ===========================================================================
    "poolside/laguna-s-2.1": OpenRouterModel(
        id="poolside/laguna-s-2.1",
        name="Laguna S 2.1",
        provider="poolside",
        input_price=0.09,
        output_price=0.18,
        context_length=1048576,
        supports_json=False,
        tier="budget",
    ),
    "poolside/laguna-s-2.1:free": OpenRouterModel(
        id="poolside/laguna-s-2.1:free",
        name="Laguna S 2.1 (free)",
        provider="poolside",
        input_price=0.0,
        output_price=0.0,
        context_length=262144,
        supports_json=False,
        tier="budget",
    ),
    "poolside/laguna-xs-2.1": OpenRouterModel(
        id="poolside/laguna-xs-2.1",
        name="Laguna XS 2.1",
        provider="poolside",
        input_price=0.06,
        output_price=0.12,
        context_length=262144,
        supports_json=False,
        tier="budget",
    ),
    "poolside/laguna-xs-2.1:free": OpenRouterModel(
        id="poolside/laguna-xs-2.1:free",
        name="Laguna XS 2.1 (free)",
        provider="poolside",
        input_price=0.0,
        output_price=0.0,
        context_length=262144,
        supports_json=False,
        tier="budget",
    ),
    # ===========================================================================
    # QWEN
    # ===========================================================================
    "qwen/qwen-2.5-72b-instruct": OpenRouterModel(
        id="qwen/qwen-2.5-72b-instruct",
        name="Qwen2.5 72B Instruct",
        provider="qwen",
        input_price=0.36,
        output_price=0.4,
        context_length=32768,
        tier="budget",
    ),
    "qwen/qwen-2.5-7b-instruct": OpenRouterModel(
        id="qwen/qwen-2.5-7b-instruct",
        name="Qwen2.5 7B Instruct",
        provider="qwen",
        input_price=0.1,
        output_price=0.2,
        context_length=32768,
        tier="budget",
    ),
    "qwen/qwen-2.5-coder-32b-instruct": OpenRouterModel(
        id="qwen/qwen-2.5-coder-32b-instruct",
        name="Qwen2.5 Coder 32B Instruct",
        provider="qwen",
        input_price=0.66,
        output_price=1.0,
        context_length=32768,
        supports_json=False,
        tier="mid",
    ),
    "qwen/qwen-plus": OpenRouterModel(
        id="qwen/qwen-plus",
        name="Qwen-Plus",
        provider="qwen",
        input_price=0.26,
        output_price=0.78,
        context_length=1000000,
        tier="budget",
    ),
    "qwen/qwen-plus-2025-07-28": OpenRouterModel(
        id="qwen/qwen-plus-2025-07-28",
        name="Qwen Plus 0728",
        provider="qwen",
        input_price=0.26,
        output_price=0.78,
        context_length=1000000,
        tier="budget",
    ),
    "qwen/qwen-plus-2025-07-28:thinking": OpenRouterModel(
        id="qwen/qwen-plus-2025-07-28:thinking",
        name="Qwen Plus 0728 (thinking)",
        provider="qwen",
        input_price=0.4,
        output_price=1.2,
        context_length=1000000,
        tier="budget",
    ),
    "qwen/qwen2.5-vl-72b-instruct": OpenRouterModel(
        id="qwen/qwen2.5-vl-72b-instruct",
        name="Qwen2.5 VL 72B Instruct",
        provider="qwen",
        input_price=0.8,
        output_price=1.0,
        context_length=128000,
        supports_vision=True,
        tier="mid",
    ),
    "qwen/qwen3-14b": OpenRouterModel(
        id="qwen/qwen3-14b",
        name="Qwen3 14B",
        provider="qwen",
        input_price=0.2275,
        output_price=0.91,
        context_length=131072,
        tier="budget",
    ),
    "qwen/qwen3-235b-a22b": OpenRouterModel(
        id="qwen/qwen3-235b-a22b",
        name="Qwen3 235B A22B",
        provider="qwen",
        input_price=0.455,
        output_price=1.82,
        context_length=131072,
        tier="budget",
    ),
    "qwen/qwen3-235b-a22b-2507": OpenRouterModel(
        id="qwen/qwen3-235b-a22b-2507",
        name="Qwen3 235B A22B Instruct 2507",
        provider="qwen",
        input_price=0.09,
        output_price=0.55,
        context_length=262144,
        tier="budget",
    ),
    "qwen/qwen3-235b-a22b-thinking-2507": OpenRouterModel(
        id="qwen/qwen3-235b-a22b-thinking-2507",
        name="Qwen3 235B A22B Thinking 2507",
        provider="qwen",
        input_price=0.23,
        output_price=2.3,
        context_length=262144,
        tier="budget",
    ),
    "qwen/qwen3-30b-a3b": OpenRouterModel(
        id="qwen/qwen3-30b-a3b",
        name="Qwen3 30B A3B",
        provider="qwen",
        input_price=0.12,
        output_price=0.5,
        context_length=131072,
        tier="budget",
    ),
    "qwen/qwen3-30b-a3b-instruct-2507": OpenRouterModel(
        id="qwen/qwen3-30b-a3b-instruct-2507",
        name="Qwen3 30B A3B Instruct 2507",
        provider="qwen",
        input_price=0.0481,
        output_price=0.193,
        context_length=262144,
        tier="budget",
    ),
    "qwen/qwen3-30b-a3b-thinking-2507": OpenRouterModel(
        id="qwen/qwen3-30b-a3b-thinking-2507",
        name="Qwen3 30B A3B Thinking 2507",
        provider="qwen",
        input_price=0.2,
        output_price=2.4,
        context_length=81920,
        tier="budget",
    ),
    "qwen/qwen3-32b": OpenRouterModel(
        id="qwen/qwen3-32b",
        name="Qwen3 32B",
        provider="qwen",
        input_price=0.08,
        output_price=0.28,
        context_length=131072,
        tier="budget",
    ),
    "qwen/qwen3-8b": OpenRouterModel(
        id="qwen/qwen3-8b",
        name="Qwen3 8B",
        provider="qwen",
        input_price=0.117,
        output_price=0.455,
        context_length=131072,
        tier="budget",
    ),
    "qwen/qwen3-coder-30b-a3b-instruct": OpenRouterModel(
        id="qwen/qwen3-coder-30b-a3b-instruct",
        name="Qwen3 Coder 30B A3B Instruct",
        provider="qwen",
        input_price=0.07,
        output_price=0.28,
        context_length=262144,
        tier="budget",
    ),
    "qwen/qwen3-coder-next": OpenRouterModel(
        id="qwen/qwen3-coder-next",
        name="Qwen3 Coder Next",
        provider="qwen",
        input_price=0.12,
        output_price=0.8,
        context_length=262144,
        tier="budget",
    ),
    "qwen/qwen3-next-80b-a3b-instruct": OpenRouterModel(
        id="qwen/qwen3-next-80b-a3b-instruct",
        name="Qwen3 Next 80B A3B Instruct",
        provider="qwen",
        input_price=0.1,
        output_price=1.1,
        context_length=262144,
        tier="budget",
    ),
    "qwen/qwen3-next-80b-a3b-thinking": OpenRouterModel(
        id="qwen/qwen3-next-80b-a3b-thinking",
        name="Qwen3 Next 80B A3B Thinking",
        provider="qwen",
        input_price=0.15,
        output_price=1.2,
        context_length=262144,
        tier="budget",
    ),
    "qwen/qwen3-vl-235b-a22b-instruct": OpenRouterModel(
        id="qwen/qwen3-vl-235b-a22b-instruct",
        name="Qwen3 VL 235B A22B Instruct",
        provider="qwen",
        input_price=0.21,
        output_price=1.9,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3-vl-235b-a22b-thinking": OpenRouterModel(
        id="qwen/qwen3-vl-235b-a22b-thinking",
        name="Qwen3 VL 235B A22B Thinking",
        provider="qwen",
        input_price=0.4,
        output_price=4.0,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3-vl-30b-a3b-instruct": OpenRouterModel(
        id="qwen/qwen3-vl-30b-a3b-instruct",
        name="Qwen3 VL 30B A3B Instruct",
        provider="qwen",
        input_price=0.13,
        output_price=0.52,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3-vl-30b-a3b-thinking": OpenRouterModel(
        id="qwen/qwen3-vl-30b-a3b-thinking",
        name="Qwen3 VL 30B A3B Thinking",
        provider="qwen",
        input_price=0.2,
        output_price=2.4,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3-vl-32b-instruct": OpenRouterModel(
        id="qwen/qwen3-vl-32b-instruct",
        name="Qwen3 VL 32B Instruct",
        provider="qwen",
        input_price=0.104,
        output_price=0.416,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3-vl-8b-instruct": OpenRouterModel(
        id="qwen/qwen3-vl-8b-instruct",
        name="Qwen3 VL 8B Instruct",
        provider="qwen",
        input_price=0.117,
        output_price=0.455,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3-vl-8b-thinking": OpenRouterModel(
        id="qwen/qwen3-vl-8b-thinking",
        name="Qwen3 VL 8B Thinking",
        provider="qwen",
        input_price=0.18,
        output_price=2.1,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3.5-plus-02-15": OpenRouterModel(
        id="qwen/qwen3.5-plus-02-15",
        name="Qwen3.5 Plus 2026-02-15",
        provider="qwen",
        input_price=0.26,
        output_price=1.56,
        context_length=1000000,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3.6-27b": OpenRouterModel(
        id="qwen/qwen3.6-27b",
        name="Qwen3.6 27B",
        provider="qwen",
        input_price=0.3,
        output_price=2.0,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3.6-35b-a3b": OpenRouterModel(
        id="qwen/qwen3.6-35b-a3b",
        name="Qwen3.6 35B A3B",
        provider="qwen",
        input_price=0.14,
        output_price=1.0,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    "qwen/qwen3.6-max-preview": OpenRouterModel(
        id="qwen/qwen3.6-max-preview",
        name="Qwen3.6 Max Preview",
        provider="qwen",
        input_price=1.027,
        output_price=6.162,
        context_length=262144,
        tier="mid",
    ),
    # ===========================================================================
    # REKAAI
    # ===========================================================================
    "rekaai/reka-edge": OpenRouterModel(
        id="rekaai/reka-edge",
        name="Reka Edge",
        provider="rekaai",
        input_price=0.1,
        output_price=0.1,
        context_length=16384,
        supports_vision=True,
        tier="budget",
    ),
    "rekaai/reka-flash-3": OpenRouterModel(
        id="rekaai/reka-flash-3",
        name="Reka Flash 3",
        provider="rekaai",
        input_price=0.1,
        output_price=0.2,
        context_length=65536,
        tier="budget",
    ),
    # ===========================================================================
    # RELACE
    # ===========================================================================
    "relace/relace-apply-3": OpenRouterModel(
        id="relace/relace-apply-3",
        name="Relace Apply 3",
        provider="relace",
        input_price=0.85,
        output_price=1.25,
        context_length=256000,
        supports_json=False,
        tier="mid",
    ),
    "relace/relace-search": OpenRouterModel(
        id="relace/relace-search",
        name="Relace Search",
        provider="relace",
        input_price=1.0,
        output_price=3.0,
        context_length=256000,
        tier="mid",
    ),
    # ===========================================================================
    # SAKANA
    # ===========================================================================
    "sakana/fugu-ultra": OpenRouterModel(
        id="sakana/fugu-ultra",
        name="Fugu Ultra",
        provider="sakana",
        input_price=5.0,
        output_price=30.0,
        context_length=1000000,
        supports_vision=True,
        tier="premium",
    ),
    # ===========================================================================
    # SAO10K
    # ===========================================================================
    "sao10k/l3-lunaris-8b": OpenRouterModel(
        id="sao10k/l3-lunaris-8b",
        name="Llama 3 8B Lunaris",
        provider="sao10k",
        input_price=0.04,
        output_price=0.05,
        context_length=8192,
        tier="budget",
    ),
    "sao10k/l3.1-euryale-70b": OpenRouterModel(
        id="sao10k/l3.1-euryale-70b",
        name="Llama 3.1 Euryale 70B v2.2",
        provider="sao10k",
        input_price=0.85,
        output_price=0.85,
        context_length=131072,
        tier="mid",
    ),
    "sao10k/l3.3-euryale-70b": OpenRouterModel(
        id="sao10k/l3.3-euryale-70b",
        name="Llama 3.3 Euryale 70B",
        provider="sao10k",
        input_price=0.65,
        output_price=0.75,
        context_length=131072,
        tier="mid",
    ),
    # ===========================================================================
    # STEPFUN
    # ===========================================================================
    "stepfun/step-3.5-flash": OpenRouterModel(
        id="stepfun/step-3.5-flash",
        name="Step 3.5 Flash",
        provider="stepfun",
        input_price=0.1,
        output_price=0.3,
        context_length=262144,
        supports_json=False,
        tier="budget",
    ),
    "stepfun/step-3.7-flash": OpenRouterModel(
        id="stepfun/step-3.7-flash",
        name="Step 3.7 Flash",
        provider="stepfun",
        input_price=0.2,
        output_price=1.15,
        context_length=262144,
        supports_vision=True,
        tier="budget",
    ),
    # ===========================================================================
    # TENCENT
    # ===========================================================================
    "tencent/hunyuan-a13b-instruct": OpenRouterModel(
        id="tencent/hunyuan-a13b-instruct",
        name="Hunyuan A13B Instruct",
        provider="tencent",
        input_price=0.14,
        output_price=0.57,
        context_length=131072,
        tier="budget",
    ),
    "tencent/hy3": OpenRouterModel(
        id="tencent/hy3",
        name="Hy3",
        provider="tencent",
        input_price=0.132,
        output_price=0.528,
        context_length=262144,
        tier="budget",
    ),
    "tencent/hy3-preview": OpenRouterModel(
        id="tencent/hy3-preview",
        name="Hy3 preview",
        provider="tencent",
        input_price=0.063,
        output_price=0.21,
        context_length=262144,
        supports_json=False,
        tier="budget",
    ),
    # ===========================================================================
    # THEDRUMMER
    # ===========================================================================
    "thedrummer/cydonia-24b-v4.1": OpenRouterModel(
        id="thedrummer/cydonia-24b-v4.1",
        name="Cydonia 24B V4.1",
        provider="thedrummer",
        input_price=0.3,
        output_price=0.5,
        context_length=131072,
        tier="budget",
    ),
    "thedrummer/rocinante-12b": OpenRouterModel(
        id="thedrummer/rocinante-12b",
        name="Rocinante 12B",
        provider="thedrummer",
        input_price=0.25,
        output_price=0.5,
        context_length=65536,
        tier="budget",
    ),
    "thedrummer/skyfall-36b-v2": OpenRouterModel(
        id="thedrummer/skyfall-36b-v2",
        name="Skyfall 36B V2",
        provider="thedrummer",
        input_price=0.55,
        output_price=0.8,
        context_length=32768,
        tier="mid",
    ),
    "thedrummer/unslopnemo-12b": OpenRouterModel(
        id="thedrummer/unslopnemo-12b",
        name="UnslopNemo 12B",
        provider="thedrummer",
        input_price=0.4,
        output_price=0.4,
        context_length=1024000,
        tier="budget",
    ),
    # ===========================================================================
    # THINKINGMACHINES
    # ===========================================================================
    "thinkingmachines/inkling": OpenRouterModel(
        id="thinkingmachines/inkling",
        name="Inkling",
        provider="thinkingmachines",
        input_price=1.0,
        output_price=4.05,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    "thinkingmachines/inkling-small": OpenRouterModel(
        id="thinkingmachines/inkling-small",
        name="Inkling Small",
        provider="thinkingmachines",
        input_price=0.5,
        output_price=1.2,
        context_length=524288,
        supports_vision=True,
        supports_json=False,
        tier="mid",
    ),
    # ===========================================================================
    # UNDI95
    # ===========================================================================
    "undi95/remm-slerp-l2-13b": OpenRouterModel(
        id="undi95/remm-slerp-l2-13b",
        name="ReMM SLERP 13B",
        provider="undi95",
        input_price=0.45,
        output_price=0.65,
        context_length=6144,
        tier="budget",
    ),
    # ===========================================================================
    # UPSTAGE
    # ===========================================================================
    "upstage/solar-pro-3": OpenRouterModel(
        id="upstage/solar-pro-3",
        name="Solar Pro 3",
        provider="upstage",
        input_price=0.15,
        output_price=0.6,
        context_length=128000,
        tier="budget",
    ),
    # ===========================================================================
    # WRITER
    # ===========================================================================
    "writer/palmyra-x5": OpenRouterModel(
        id="writer/palmyra-x5",
        name="Palmyra X5",
        provider="writer",
        input_price=0.6,
        output_price=6.0,
        context_length=1040000,
        supports_json=False,
        tier="mid",
    ),
    # ===========================================================================
    # X AI
    # ===========================================================================
    "x-ai/grok-4.20": OpenRouterModel(
        id="x-ai/grok-4.20",
        name="Grok 4.20",
        provider="x-ai",
        input_price=1.25,
        output_price=2.5,
        context_length=2000000,
        supports_vision=True,
        tier="mid",
    ),
    "x-ai/grok-4.20-multi-agent": OpenRouterModel(
        id="x-ai/grok-4.20-multi-agent",
        name="Grok 4.20 Multi-Agent",
        provider="x-ai",
        input_price=1.25,
        output_price=2.5,
        context_length=2000000,
        supports_vision=True,
        tier="mid",
    ),
    "x-ai/grok-build-0.1": OpenRouterModel(
        id="x-ai/grok-build-0.1",
        name="Grok Build 0.1",
        provider="x-ai",
        input_price=1.0,
        output_price=2.0,
        context_length=256000,
        supports_vision=True,
        tier="mid",
    ),
    # ===========================================================================
    # Z AI
    # ===========================================================================
    "z-ai/glm-4.5v": OpenRouterModel(
        id="z-ai/glm-4.5v",
        name="GLM 4.5V",
        provider="z-ai",
        input_price=0.6,
        output_price=1.8,
        context_length=65536,
        supports_vision=True,
        tier="mid",
    ),
    "z-ai/glm-4.6": OpenRouterModel(
        id="z-ai/glm-4.6",
        name="GLM 4.6",
        provider="z-ai",
        input_price=0.5,
        output_price=2.0,
        context_length=204800,
        tier="mid",
    ),
    "z-ai/glm-4.6v": OpenRouterModel(
        id="z-ai/glm-4.6v",
        name="GLM 4.6V",
        provider="z-ai",
        input_price=0.3,
        output_price=0.9,
        context_length=131072,
        supports_vision=True,
        tier="budget",
    ),
    "z-ai/glm-5-turbo": OpenRouterModel(
        id="z-ai/glm-5-turbo",
        name="GLM 5 Turbo",
        provider="z-ai",
        input_price=1.2,
        output_price=4.0,
        context_length=202752,
        tier="mid",
    ),
    "z-ai/glm-5v-turbo": OpenRouterModel(
        id="z-ai/glm-5v-turbo",
        name="GLM 5V Turbo",
        provider="z-ai",
        input_price=1.2,
        output_price=4.0,
        context_length=202752,
        supports_vision=True,
        tier="mid",
    ),
    # ===========================================================================
    # ~ANTHROPIC
    # ===========================================================================
    "~anthropic/claude-fable-latest": OpenRouterModel(
        id="~anthropic/claude-fable-latest",
        name="Claude Fable Latest",
        provider="~anthropic",
        input_price=10.0,
        output_price=50.0,
        context_length=1000000,
        supports_vision=True,
        tier="premium",
    ),
    "~anthropic/claude-haiku-latest": OpenRouterModel(
        id="~anthropic/claude-haiku-latest",
        name="Anthropic Claude Haiku Latest",
        provider="~anthropic",
        input_price=1.0,
        output_price=5.0,
        context_length=200000,
        supports_vision=True,
        tier="mid",
    ),
    "~anthropic/claude-opus-latest": OpenRouterModel(
        id="~anthropic/claude-opus-latest",
        name="Claude Opus Latest",
        provider="~anthropic",
        input_price=5.0,
        output_price=25.0,
        context_length=1000000,
        supports_vision=True,
        tier="premium",
    ),
    "~anthropic/claude-sonnet-latest": OpenRouterModel(
        id="~anthropic/claude-sonnet-latest",
        name="Anthropic Claude Sonnet Latest",
        provider="~anthropic",
        input_price=2.0,
        output_price=10.0,
        context_length=1000000,
        supports_vision=True,
        tier="mid",
    ),
    # ===========================================================================
    # ~GOOGLE
    # ===========================================================================
    "~google/gemini-flash-latest": OpenRouterModel(
        id="~google/gemini-flash-latest",
        name="Google Gemini Flash Latest",
        provider="~google",
        input_price=1.5,
        output_price=7.5,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    "~google/gemini-pro-latest": OpenRouterModel(
        id="~google/gemini-pro-latest",
        name="Google Gemini Pro Latest",
        provider="~google",
        input_price=2.0,
        output_price=12.0,
        context_length=1048576,
        supports_vision=True,
        tier="mid",
    ),
    # ===========================================================================
    # ~MOONSHOTAI
    # ===========================================================================
    "~moonshotai/kimi-latest": OpenRouterModel(
        id="~moonshotai/kimi-latest",
        name="MoonshotAI Kimi Latest",
        provider="~moonshotai",
        input_price=2.9,
        output_price=14.0,
        context_length=1048576,
        supports_vision=True,
        tier="premium",
    ),
    # ===========================================================================
    # ~OPENAI
    # ===========================================================================
    "~openai/gpt-latest": OpenRouterModel(
        id="~openai/gpt-latest",
        name="OpenAI GPT Latest",
        provider="~openai",
        input_price=5.0,
        output_price=30.0,
        context_length=1050000,
        supports_vision=True,
        tier="premium",
    ),
    "~openai/gpt-mini-latest": OpenRouterModel(
        id="~openai/gpt-mini-latest",
        name="OpenAI GPT Mini Latest",
        provider="~openai",
        input_price=0.75,
        output_price=4.5,
        context_length=400000,
        supports_vision=True,
        tier="mid",
    ),
    # ===========================================================================
    # ~X AI
    # ===========================================================================
    "~x-ai/grok-latest": OpenRouterModel(
        id="~x-ai/grok-latest",
        name="Grok Latest",
        provider="~x-ai",
        input_price=2.0,
        output_price=6.0,
        context_length=500000,
        supports_vision=True,
        tier="mid",
    ),
}


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
                    truncated=data.get("choices", [{}])[0].get("finish_reason") == "length",
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
