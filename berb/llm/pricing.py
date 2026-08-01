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
    "qwen/qwen3.7-flash": (0.03, 0.13),
    # XAI (Grok)
    "x-ai/grok-4.5": (2.00, 4.00),
    "x-ai/grok-4.3": (1.25, 2.50),
    # Xiaomi (MIMO)
    "xiaomi/mimo-v2.5": (0.14, 0.28),
    "xiaomi/mimo-v2.5-pro": (0.44, 0.87),
    # Perplexity
    "perplexity/sonar-pro": (5.00, 5.00),
    "perplexity/sonar-deep-research": (10.00, 10.00),
    # ai21
    "ai21/jamba-large-1.7": (2.0, 8.0),
    # aion-labs
    "aion-labs/aion-2.0": (0.8, 1.6),
    "aion-labs/aion-3.0": (3.0, 6.0),
    "aion-labs/aion-3.0-mini": (0.7, 1.4),
    "aion-labs/aion-rp-llama-3.1-8b": (0.8, 1.6),
    # allenai
    "allenai/olmo-3-32b-think": (0.15, 0.5),
    # amazon
    "amazon/nova-lite-v1": (0.06, 0.24),
    "amazon/nova-micro-v1": (0.035, 0.14),
    # anthracite-org
    "anthracite-org/magnum-v4-72b": (3.0, 5.0),
    # anthropic
    "anthropic/claude-3-haiku": (0.25, 1.25),
    "anthropic/claude-opus-4": (15.0, 75.0),
    "anthropic/claude-opus-5": (5.0, 25.0),
    "anthropic/claude-opus-5-fast": (10.0, 50.0),
    "anthropic/claude-sonnet-4": (3.0, 15.0),
    "anthropic/claude-sonnet-5": (2.0, 10.0),
    # arcee-ai
    "arcee-ai/trinity-large-thinking": (0.22, 0.85),
    "arcee-ai/virtuoso-large": (0.75, 1.2),
    # baidu
    "baidu/ernie-4.5-vl-424b-a47b": (0.42, 1.25),
    # bytedance
    "bytedance/ui-tars-1.5-7b": (0.1, 0.2),
    # bytedance-seed
    "bytedance-seed/seed-1.6": (0.25, 2.0),
    "bytedance-seed/seed-1.6-flash": (0.075, 0.3),
    "bytedance-seed/seed-2.0-lite": (0.25, 2.0),
    # cognitivecomputations
    "cognitivecomputations/dolphin-mistral-24b-venice-edition": (0.2, 0.9),
    # cohere
    "cohere/command-r-08-2024": (0.15, 0.6),
    "cohere/command-r-plus-08-2024": (2.5, 10.0),
    "cohere/command-r7b-12-2024": (0.0375, 0.15),
    "cohere/north-mini-code:free": (0.0, 0.0),
    # deepcogito
    "deepcogito/cogito-v2.1-671b": (1.25, 1.25),
    # deepseek
    "deepseek/deepseek-chat": (0.2574, 1.0287),
    "deepseek/deepseek-chat-v3-0324": (0.27, 1.12),
    "deepseek/deepseek-r1-0528": (0.5, 2.15),
    "deepseek/deepseek-r1-distill-llama-70b": (0.8, 0.8),
    "deepseek/deepseek-v3.1-terminus": (0.27, 1.0),
    "deepseek/deepseek-v3.2-exp": (0.27, 0.41),
    "deepseek/deepseek-v4-flash-0731": (0.14, 0.28),
    # google
    "google/gemini-2.5-flash-image": (0.3, 2.5),
    "google/gemini-2.5-pro-preview": (1.25, 10.0),
    "google/gemini-2.5-pro-preview-05-06": (1.25, 10.0),
    "google/gemini-3-pro-image": (2.0, 12.0),
    "google/gemini-3-pro-image-preview": (2.0, 12.0),
    "google/gemini-3.1-flash-image": (0.5, 3.0),
    "google/gemini-3.1-flash-image-preview": (0.5, 3.0),
    "google/gemini-3.1-flash-lite-image": (0.25, 1.5),
    "google/gemini-3.1-flash-lite-preview": (0.25, 1.5),
    "google/gemini-3.1-pro-preview": (2.0, 12.0),
    "google/gemini-3.1-pro-preview-customtools": (2.0, 12.0),
    "google/gemini-3.5-flash-lite": (0.3, 2.5),
    "google/gemini-3.6-flash": (1.5, 7.5),
    "google/gemma-2-27b-it": (0.65, 0.65),
    "google/gemma-3-12b-it": (0.05, 0.15),
    "google/gemma-3-27b-it": (0.08, 0.45),
    "google/gemma-3-4b-it": (0.05, 0.1),
    "google/gemma-3n-e4b-it": (0.06, 0.12),
    "google/gemma-4-26b-a4b-it:free": (0.0, 0.0),
    "google/gemma-4-31b-it:free": (0.0, 0.0),
    "google/lyria-3-clip-preview": (0.0, 0.0),
    "google/lyria-3-pro-preview": (0.0, 0.0),
    # gryphe
    "gryphe/mythomax-l2-13b": (0.06, 0.06),
    # ibm-granite
    "ibm-granite/granite-4.0-h-micro": (0.017, 0.112),
    "ibm-granite/granite-4.1-8b": (0.05, 0.1),
    # inception
    "inception/mercury-2": (0.25, 0.75),
    # inclusionai
    "inclusionai/ling-2.6-1t": (0.075, 0.625),
    "inclusionai/ling-2.6-flash": (0.01, 0.03),
    "inclusionai/ling-3.0-flash:free": (0.0, 0.0),
    "inclusionai/ring-2.6-1t": (0.075, 0.625),
    # kwaipilot
    "kwaipilot/kat-coder-air-v2.5": (0.15, 0.6),
    "kwaipilot/kat-coder-pro-v2": (0.3, 1.2),
    "kwaipilot/kat-coder-pro-v2.5": (0.74, 2.96),
    # mancer
    "mancer/weaver": (0.5, 0.75),
    # meituan
    "meituan/longcat-2.0": (0.3, 1.2),
    # meta
    "meta/muse-spark-1.1": (1.25, 4.25),
    # meta-llama
    "meta-llama/llama-3.1-70b-instruct": (0.4, 0.4),
    "meta-llama/llama-3.1-8b-instruct": (0.05, 0.08),
    "meta-llama/llama-3.2-1b-instruct": (0.027, 0.201),
    "meta-llama/llama-3.2-3b-instruct": (0.05, 0.33),
    "meta-llama/llama-3.3-70b-instruct": (0.13, 0.4),
    "meta-llama/llama-guard-4-12b": (0.18, 0.18),
    # microsoft
    "microsoft/phi-4": (0.07, 0.14),
    "microsoft/wizardlm-2-8x22b": (0.62, 0.62),
    # minimax
    "minimax/minimax-01": (0.2, 1.1),
    "minimax/minimax-m2": (0.255, 1.02),
    "minimax/minimax-m2-her": (0.3, 1.2),
    "minimax/minimax-m2.1": (0.3, 1.2),
    # mistralai
    "mistralai/codestral-2508": (0.3, 0.9),
    "mistralai/ministral-14b-2512": (0.2, 0.2),
    "mistralai/ministral-3b-2512": (0.1, 0.1),
    "mistralai/ministral-8b-2512": (0.15, 0.15),
    "mistralai/mistral-large-2407": (2.0, 6.0),
    "mistralai/mistral-large-2512": (0.5, 1.5),
    "mistralai/mistral-medium-3": (0.4, 2.0),
    "mistralai/mistral-medium-3.1": (0.4, 2.0),
    "mistralai/mistral-nemo": (0.019, 0.03),
    "mistralai/mistral-saba": (0.2, 0.6),
    "mistralai/mistral-small-24b-instruct-2501": (0.05, 0.08),
    "mistralai/mistral-small-2603": (0.15, 0.6),
    "mistralai/mistral-small-3.1-24b-instruct": (0.351, 0.555),
    "mistralai/mixtral-8x22b-instruct": (2.0, 6.0),
    "mistralai/voxtral-small-24b-2507": (0.1, 0.3),
    # moonshotai
    "moonshotai/kimi-k2-0905": (0.6, 2.5),
    "moonshotai/kimi-k2-thinking": (0.6, 2.5),
    "moonshotai/kimi-k3": (3.0, 15.0),
    # morph
    "morph/morph-v3-fast": (0.8, 1.2),
    "morph/morph-v3-large": (0.9, 1.9),
    # nex-agi
    "nex-agi/nex-n2-mini": (0.025, 0.1),
    "nex-agi/nex-n2-pro": (0.25, 1.0),
    # nousresearch
    "nousresearch/hermes-3-llama-3.1-405b": (1.0, 1.0),
    "nousresearch/hermes-3-llama-3.1-70b": (0.7, 0.7),
    "nousresearch/hermes-4-405b": (1.0, 3.0),
    "nousresearch/hermes-4-70b": (0.13, 0.4),
    # nvidia
    "nvidia/nemotron-3-nano-30b-a3b": (0.05, 0.2),
    "nvidia/nemotron-3-nano-30b-a3b:free": (0.0, 0.0),
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": (0.0, 0.0),
    "nvidia/nemotron-3-super-120b-a12b:free": (0.0, 0.0),
    "nvidia/nemotron-3-ultra-550b-a55b": (0.6, 3.6),
    "nvidia/nemotron-3-ultra-550b-a55b:free": (0.0, 0.0),
    "nvidia/nemotron-3.5-content-safety:free": (0.0, 0.0),
    "nvidia/nemotron-nano-12b-v2-vl:free": (0.0, 0.0),
    "nvidia/nemotron-nano-9b-v2:free": (0.0, 0.0),
    # openai
    "openai/gpt-3.5-turbo": (0.5, 1.5),
    "openai/gpt-3.5-turbo-0613": (1.0, 2.0),
    "openai/gpt-3.5-turbo-16k": (3.0, 4.0),
    "openai/gpt-3.5-turbo-instruct": (1.5, 2.0),
    "openai/gpt-4": (30.0, 60.0),
    "openai/gpt-4-turbo": (10.0, 30.0),
    "openai/gpt-4-turbo-preview": (10.0, 30.0),
    "openai/gpt-4o-2024-05-13": (5.0, 15.0),
    "openai/gpt-4o-2024-08-06": (2.5, 10.0),
    "openai/gpt-4o-2024-11-20": (2.5, 10.0),
    "openai/gpt-4o-mini-2024-07-18": (0.15, 0.6),
    "openai/gpt-5-image": (10.0, 10.0),
    "openai/gpt-5-image-mini": (2.5, 2.0),
    "openai/gpt-5-pro": (15.0, 120.0),
    "openai/gpt-5.1-codex": (1.25, 10.0),
    "openai/gpt-5.1-codex-max": (1.25, 10.0),
    "openai/gpt-5.1-codex-mini": (0.25, 2.0),
    "openai/gpt-5.2-chat": (1.75, 14.0),
    "openai/gpt-5.2-pro": (21.0, 168.0),
    "openai/gpt-5.3-chat": (1.75, 14.0),
    "openai/gpt-5.3-codex": (1.75, 14.0),
    "openai/gpt-5.4-image-2": (8.0, 15.0),
    "openai/gpt-5.6-luna": (0.1, 0.6),
    "openai/gpt-5.6-luna-pro": (0.1, 0.6),
    "openai/gpt-5.6-sol": (5.0, 30.0),
    "openai/gpt-5.6-sol-pro": (5.0, 30.0),
    "openai/gpt-5.6-terra": (1.0, 6.0),
    "openai/gpt-5.6-terra-pro": (1.0, 6.0),
    "openai/gpt-audio": (2.5, 10.0),
    "openai/gpt-audio-mini": (0.6, 2.4),
    "openai/gpt-chat-latest": (5.0, 30.0),
    "openai/gpt-oss-120b": (0.037, 0.17),
    "openai/gpt-oss-20b": (0.03, 0.13),
    "openai/gpt-oss-20b:free": (0.0, 0.0),
    "openai/gpt-oss-safeguard-20b": (0.075, 0.3),
    "openai/o1-pro": (150.0, 600.0),
    "openai/o3-mini-high": (1.1, 4.4),
    "openai/o4-mini-high": (1.1, 4.4),
    # openrouter
    "openrouter/auto": (-1000000.0, -1000000.0),
    "openrouter/auto-beta": (-1000000.0, -1000000.0),
    "openrouter/bodybuilder": (-1000000.0, -1000000.0),
    "openrouter/free": (0.0, 0.0),
    "openrouter/fusion": (-1000000.0, -1000000.0),
    "openrouter/pareto-code": (-1000000.0, -1000000.0),
    # perceptron
    "perceptron/perceptron-mk1": (0.15, 1.5),
    # poolside
    "poolside/laguna-s-2.1": (0.09, 0.18),
    "poolside/laguna-s-2.1:free": (0.0, 0.0),
    "poolside/laguna-xs-2.1": (0.06, 0.12),
    "poolside/laguna-xs-2.1:free": (0.0, 0.0),
    # qwen
    "qwen/qwen-2.5-72b-instruct": (0.36, 0.4),
    "qwen/qwen-2.5-7b-instruct": (0.1, 0.2),
    "qwen/qwen-2.5-coder-32b-instruct": (0.66, 1.0),
    "qwen/qwen-plus": (0.26, 0.78),
    "qwen/qwen-plus-2025-07-28": (0.26, 0.78),
    "qwen/qwen-plus-2025-07-28:thinking": (0.4, 1.2),
    "qwen/qwen2.5-vl-72b-instruct": (0.8, 1.0),
    "qwen/qwen3-14b": (0.2275, 0.91),
    "qwen/qwen3-235b-a22b": (0.455, 1.82),
    "qwen/qwen3-235b-a22b-2507": (0.09, 0.55),
    "qwen/qwen3-235b-a22b-thinking-2507": (0.23, 2.3),
    "qwen/qwen3-30b-a3b": (0.12, 0.5),
    "qwen/qwen3-30b-a3b-instruct-2507": (0.0481, 0.193),
    "qwen/qwen3-30b-a3b-thinking-2507": (0.2, 2.4),
    "qwen/qwen3-32b": (0.08, 0.28),
    "qwen/qwen3-8b": (0.117, 0.455),
    "qwen/qwen3-coder-30b-a3b-instruct": (0.07, 0.28),
    "qwen/qwen3-coder-next": (0.12, 0.8),
    "qwen/qwen3-next-80b-a3b-instruct": (0.1, 1.1),
    "qwen/qwen3-next-80b-a3b-thinking": (0.15, 1.2),
    "qwen/qwen3-vl-235b-a22b-instruct": (0.21, 1.9),
    "qwen/qwen3-vl-235b-a22b-thinking": (0.4, 4.0),
    "qwen/qwen3-vl-30b-a3b-instruct": (0.13, 0.52),
    "qwen/qwen3-vl-30b-a3b-thinking": (0.2, 2.4),
    "qwen/qwen3-vl-32b-instruct": (0.104, 0.416),
    "qwen/qwen3-vl-8b-instruct": (0.117, 0.455),
    "qwen/qwen3-vl-8b-thinking": (0.18, 2.1),
    "qwen/qwen3.5-plus-02-15": (0.26, 1.56),
    "qwen/qwen3.6-27b": (0.3, 2.0),
    "qwen/qwen3.6-35b-a3b": (0.14, 1.0),
    "qwen/qwen3.6-max-preview": (1.027, 6.162),
    # rekaai
    "rekaai/reka-edge": (0.1, 0.1),
    "rekaai/reka-flash-3": (0.1, 0.2),
    # relace
    "relace/relace-apply-3": (0.85, 1.25),
    "relace/relace-search": (1.0, 3.0),
    # sakana
    "sakana/fugu-ultra": (5.0, 30.0),
    # sao10k
    "sao10k/l3-lunaris-8b": (0.04, 0.05),
    "sao10k/l3.1-euryale-70b": (0.85, 0.85),
    "sao10k/l3.3-euryale-70b": (0.65, 0.75),
    # stepfun
    "stepfun/step-3.5-flash": (0.1, 0.3),
    "stepfun/step-3.7-flash": (0.2, 1.15),
    # tencent
    "tencent/hunyuan-a13b-instruct": (0.14, 0.57),
    "tencent/hy3": (0.132, 0.528),
    "tencent/hy3-preview": (0.063, 0.21),
    # thedrummer
    "thedrummer/cydonia-24b-v4.1": (0.3, 0.5),
    "thedrummer/rocinante-12b": (0.25, 0.5),
    "thedrummer/skyfall-36b-v2": (0.55, 0.8),
    "thedrummer/unslopnemo-12b": (0.4, 0.4),
    # thinkingmachines
    "thinkingmachines/inkling": (1.0, 4.05),
    "thinkingmachines/inkling-small": (0.5, 1.2),
    # undi95
    "undi95/remm-slerp-l2-13b": (0.45, 0.65),
    # upstage
    "upstage/solar-pro-3": (0.15, 0.6),
    # writer
    "writer/palmyra-x5": (0.6, 6.0),
    # x-ai
    "x-ai/grok-4.20": (1.25, 2.5),
    "x-ai/grok-4.20-multi-agent": (1.25, 2.5),
    "x-ai/grok-build-0.1": (1.0, 2.0),
    # z-ai
    "z-ai/glm-4.5v": (0.6, 1.8),
    "z-ai/glm-4.6": (0.5, 2.0),
    "z-ai/glm-4.6v": (0.3, 0.9),
    "z-ai/glm-5-turbo": (1.2, 4.0),
    "z-ai/glm-5v-turbo": (1.2, 4.0),
    # ~anthropic
    "~anthropic/claude-fable-latest": (10.0, 50.0),
    "~anthropic/claude-haiku-latest": (1.0, 5.0),
    "~anthropic/claude-opus-latest": (5.0, 25.0),
    "~anthropic/claude-sonnet-latest": (2.0, 10.0),
    # ~google
    "~google/gemini-flash-latest": (1.5, 7.5),
    "~google/gemini-pro-latest": (2.0, 12.0),
    # ~moonshotai
    "~moonshotai/kimi-latest": (2.9, 14.0),
    # ~openai
    "~openai/gpt-latest": (5.0, 30.0),
    "~openai/gpt-mini-latest": (0.75, 4.5),
    # ~x-ai
    "~x-ai/grok-latest": (2.0, 6.0),
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
        cost = (prompt_tokens / 1_000_000) * input_price + (
            completion_tokens / 1_000_000
        ) * output_price
        return cost
