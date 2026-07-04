"""OpenRouter API adapter for Berb.

OpenRouter provides unified access to 340+ LLM models from 60+ providers
with a single API key and competitive pricing.

Supported Providers (80+ notable models declared):
- Anthropic (Claude Sonnet/Opus/Haiku 4.5–4.8, Claude Fable 5)
- OpenAI (GPT-5.5/5.4/5.2/5.1/5/4o/4.1, o1/o3/o3-pro/o4-mini)
- Google (Gemini 2.5/3.0/3.5 Pro/Flash/Lite, Gemma 4)
- DeepSeek (V3.1/V3.2/V4-Pro/V4-Flash, R1)
- Qwen (Qwen3/3.5/3.6/3.7 Max/Plus/Flash, Qwen3-Coder)
- xAI (Grok 4.20, Grok 4.3)
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
from enum import Enum
from typing import Any

import httpx

# Use existing LLMResponse from client module
from berb.llm.client import LLMResponse

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Model Variants
# ─────────────────────────────────────────────────────────────────────────────


class ModelVariant(str, Enum):
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
    "x-ai/grok-4.20": OpenRouterModel(
        id="x-ai/grok-4.20",
        name="Grok 4.20",
        provider="xai",
        input_price=1.25,
        output_price=2.50,
        context_length=2_000_000,
        supports_vision=True,
        tier="mid",
    ),
    "x-ai/grok-4.20-multi-agent": OpenRouterModel(
        id="x-ai/grok-4.20-multi-agent",
        name="Grok 4.20 Multi-Agent",
        provider="xai",
        input_price=1.25,
        output_price=2.50,
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
    "microsoft/phi-4-mini-instruct": OpenRouterModel(
        id="microsoft/phi-4-mini-instruct",
        name="Phi-4 Mini",
        provider="microsoft",
        input_price=0.08,
        output_price=0.35,
        context_length=131_072,
        supports_vision=True,
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
