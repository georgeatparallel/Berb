"""Pricing table for LLM model cost computation.

Provides model-to-pricing lookups used by CostTracker.
Pricing data is stored in pricing.yaml (versioned) with
Python-native fallback pricing for common models.

Usage:
    table = PricingTable()
    cost = table.compute_cost("openai/gpt-4o-mini", prompt_tokens=500, completion_tokens=200)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Fallback pricing (per 1M tokens) for models not in pricing.yaml
# Format: {model: (input_price_per_1M, output_price_per_1M)}
FALLBACK_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "anthropic/claude-opus-4.6": (5.00, 25.00),
    "anthropic/claude-opus-4.7": (5.00, 25.00),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "anthropic/claude-fable-5": (0.01, 0.05),
    # OpenAI
    "openai/gpt-5.5": (5.00, 30.00),
    "openai/gpt-5.5-pro": (30.00, 180.00),
    "openai/gpt-5.4": (2.50, 15.00),
    "openai/gpt-5.4-mini": (0.75, 4.50),
    "openai/gpt-5.4-nano": (0.20, 1.25),
    "openai/gpt-4o": (2.50, 10.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/o3-mini": (1.10, 4.40),
    "openai/o4-mini": (1.10, 4.40),
    "openai/o1": (15.00, 60.00),
    # Google
    "google/gemini-2.5-pro": (1.25, 10.00),
    "google/gemini-2.5-flash": (0.30, 2.50),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
    # DeepSeek
    "deepseek/deepseek-v3.2": (0.23, 0.34),
    "deepseek/deepseek-chat-v3.1": (0.21, 0.79),
    "deepseek/deepseek-r1": (0.70, 2.50),
    # Qwen
    "qwen/qwen3-max": (0.78, 3.90),
    "qwen/qwen3.5-plus-20260420": (0.30, 1.80),
    "qwen/qwen3.5-flash-02-23": (0.065, 0.26),
    # XAI (Grok)
    "x-ai/grok-4.5": (2.00, 4.00),
    "x-ai/grok-4.3": (1.25, 2.50),
    # Xiaomi (MIMO)
    "xiaomi/mimo-v2.5": (0.14, 0.28),
    "xiaomi/mimo-v2.5-pro": (0.44, 0.87),
    # Perplexity
    "perplexity/sonar-pro": (5.00, 5.00),
    "perplexity/sonar-deep-research": (10.00, 10.00),
}


class PricingTable:
    """Versioned pricing table for LLM model cost computation.

    Looks up model pricing from pricing.yaml first, falling back to
    the built-in FALLBACK_PRICING dict, then returning None for truly
    unknown models.
    """

    version: str = "1.0"

    def __init__(self, pricing_path: Path | str | None = None) -> None:
        """Initialize pricing table.

        Args:
            pricing_path: Path to a pricing.yaml file. If None, uses
                only the built-in fallback pricing.
        """
        self._yaml_pricing: dict[str, tuple[float, float]] = {}
        self._load_yaml(pricing_path)

    def _load_yaml(self, path: Path | str | None) -> None:
        """Try to load pricing from a YAML file."""
        if path is None:
            # Look for default pricing.yaml relative to this file
            default = Path(__file__).resolve().parent / "pricing.yaml"
            if default.exists():
                path = default
            else:
                return

        path = Path(path)
        if not path.exists():
            logger.debug("Pricing file %s not found, using fallback pricing", path)
            return

        try:
            import yaml  # type: ignore[import-untyped]

            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                logger.warning("Invalid pricing.yaml format: expected dict, got %s", type(data))
                return

            self.version = data.get("version", self.version)
            models = data.get("models", {})
            for model_id, prices in models.items():
                if isinstance(prices, dict):
                    self._yaml_pricing[model_id] = (
                        prices.get("input", 0.0),
                        prices.get("output", 0.0),
                    )
                elif isinstance(prices, list) and len(prices) >= 2:
                    self._yaml_pricing[model_id] = (float(prices[0]), float(prices[1]))

            logger.debug("Loaded %d models from %s", len(self._yaml_pricing), path)

        except Exception as e:
            logger.warning("Failed to load pricing.yaml: %s", e)

    def get_price(self, model: str) -> tuple[float, float] | None:
        """Get (input_price_per_1M, output_price_per_1M) for a model.

        Checks YAML pricing first, then fallback dict.

        Args:
            model: Full model identifier.

        Returns:
            (input_price, output_price) tuple, or None if unknown.
        """
        # Check YAML pricing first
        if model in self._yaml_pricing:
            return self._yaml_pricing[model]

        # Check fallback dict
        if model in FALLBACK_PRICING:
            return FALLBACK_PRICING[model]

        # Try suffix matching for OpenRouter-style model paths
        for key, prices in {**self._yaml_pricing, **FALLBACK_PRICING}.items():
            if model.endswith(key) or key.endswith(model):
                return prices

        return None

    def compute_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float | None:
        """Compute cost in USD for a given model and token usage.

        Args:
            model: Full model identifier.
            prompt_tokens: Input token count.
            completion_tokens: Output token count.

        Returns:
            Cost in USD, or None if the model is unknown.
        """
        prices = self.get_price(model)
        if prices is None:
            return None

        input_price, output_price = prices
        cost = (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price
        return cost
