"""OpenRouter model presets for Berb.

This module provides pre-configured model presets optimized for different
research scenarios: max quality, budget, research, and EU sovereign.

Available Presets:
- berb-max-quality: Best models regardless of cost ($0.50-0.80/paper)
- berb-budget: Cheapest viable models ($0.15-0.25/paper)
- berb-research: Search-grounded models ($2.00-3.00/paper)
- berb-eu-sovereign: GDPR-compliant models ($0.80-1.20/paper)

Usage:
    from berb.llm.presets import get_preset
    
    config = get_preset("berb-research")
    # config contains base_url, api_key_env, models, fallback_models

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelConfig:
    """Configuration for a single model."""

    model_id: str
    provider: str
    price_input: float  # $/1M input tokens
    price_output: float  # $/1M output tokens
    context_window: int = 128000  # Default context window
    stages: list[str] = field(default_factory=list)  # Target pipeline stages
    capabilities: list[str] = field(default_factory=list)  # e.g., ["reasoning", "coding"]


@dataclass
class PresetConfig:
    """Configuration for a model preset."""

    name: str
    description: str
    base_url: str
    api_key_env: str
    primary_model: str
    fallback_models: list[str]
    cost_per_paper_estimate: tuple[float, float]  # (min, max) $/paper
    models: list[ModelConfig] = field(default_factory=list)
    features: list[str] = field(default_factory=list)


# Model definitions
MODELS = {
    # DeepSeek models
    "deepseek-v3.2": ModelConfig(
        model_id="deepseek/deepseek-chat-v3-0324:free",
        provider="deepseek",
        price_input=0.27,
        price_output=0.27,
        context_window=64000,
        stages=["8", "9", "13", "15"],
        capabilities=["reasoning", "coding", "math"],
    ),
    "deepseek-r1": ModelConfig(
        model_id="deepseek/deepseek-r1:free",
        provider="deepseek",
        price_input=0.50,
        price_output=0.50,
        context_window=64000,
        stages=["2", "8", "15"],
        capabilities=["reasoning", "chain-of-thought"],
    ),
    
    # Alibaba Qwen models
    "qwen3-max": ModelConfig(
        model_id="alibaba/qwen-max-2025-01-25",
        provider="alibaba",
        price_input=0.40,
        price_output=0.40,
        context_window=256000,
        stages=["5", "18"],
        capabilities=["long-context", "analysis"],
    ),
    "qwen3-turbo": ModelConfig(
        model_id="alibaba/qwen-turbo",
        provider="alibaba",
        price_input=0.03,
        price_output=0.03,
        context_window=32000,
        stages=["1", "11"],
        capabilities=["fast", "cheap"],
    ),
    
    # ZhipuAI GLM models
    "glm-4.5": ModelConfig(
        model_id="zhipuai/glm-4-0520",
        provider="zhipuai",
        price_input=0.30,
        price_output=0.30,
        context_window=128000,
        stages=["7", "20"],
        capabilities=["analysis", "synthesis"],
    ),
    
    # Anthropic Claude models
    "claude-sonnet-4.6": ModelConfig(
        model_id="anthropic/claude-sonnet-4-20250514",
        provider="anthropic",
        price_input=3.00,
        price_output=3.00,
        context_window=200000,
        stages=["14", "18"],
        capabilities=["writing", "analysis", "long-context"],
    ),
    
    # Google Gemini models
    "gemini-2.5-flash": ModelConfig(
        model_id="google/gemini-2.5-flash-001",
        provider="google",
        price_input=0.30,
        price_output=0.30,
        context_window=1000000,  # 1M context!
        stages=["4"],
        capabilities=["massive-context", "multimodal"],
    ),
    
    # Perplexity Sonar models
    "sonar-pro": ModelConfig(
        model_id="perplexity/sonar-pro",
        provider="perplexity",
        price_input=5.00,
        price_output=5.00,
        context_window=200000,
        stages=["5", "23"],
        capabilities=["search-grounded", "factual"],
    ),
    
    # Mistral models (EU sovereign)
    "mistral-large-3": ModelConfig(
        model_id="mistralai/mistral-large-2407",
        provider="mistral",
        price_input=4.00,
        price_output=4.00,
        context_window=128000,
        stages=["7", "18"],
        capabilities=["eu-sovereign", "gdpr"],
    ),
    
    # MiniMax models
    "minimax-m2.5": ModelConfig(
        model_id="minimax/minimax-01",
        provider="minimax",
        price_input=0.40,
        price_output=0.40,
        context_window=256000,
        stages=["8", "15"],
        capabilities=["diversity", "long-context"],
    ),
}


# Preset definitions
PRESETS = {
    "berb-max-quality": PresetConfig(
        name="berb-max-quality",
        description="Best models regardless of cost - maximum research quality",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        primary_model="anthropic/claude-sonnet-4-20250514",
        fallback_models=[
            "google/gemini-2.5-flash-001",
            "perplexity/sonar-pro",
            "alibaba/qwen-max-2025-01-25",
        ],
        cost_per_paper_estimate=(0.50, 0.80),
        models=[
            MODELS["claude-sonnet-4.6"],
            MODELS["gemini-2.5-flash"],
            MODELS["sonar-pro"],
            MODELS["qwen3-max"],
            MODELS["mistral-large-3"],
            MODELS["deepseek-r1"],
        ],
        features=[
            "Highest quality outputs",
            "Best for critical stages (review, decision)",
            "Long context support",
            "Multi-model ensemble",
        ],
    ),
    
    "berb-budget": PresetConfig(
        name="berb-budget",
        description="Cheapest viable models - maximum cost efficiency",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        primary_model="alibaba/qwen-turbo",
        fallback_models=[
            "deepseek/deepseek-chat-v3-0324:free",
            "zhipuai/glm-4-0520",
        ],
        cost_per_paper_estimate=(0.15, 0.25),
        models=[
            MODELS["qwen3-turbo"],
            MODELS["deepseek-v3.2"],
            MODELS["glm-4.5"],
            MODELS["minimax-m2.5"],
        ],
        features=[
            "Lowest cost per paper",
            "Fast inference",
            "Good for routine stages",
            "High-volume research optimized",
        ],
    ),
    
    "berb-research": PresetConfig(
        name="berb-research",
        description="Search-grounded models - best for literature review",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        primary_model="perplexity/sonar-pro",
        fallback_models=[
            "google/gemini-2.5-flash-001",
            "anthropic/claude-sonnet-4-20250514",
            "deepseek/deepseek-r1:free",
        ],
        cost_per_paper_estimate=(2.00, 3.00),
        models=[
            MODELS["sonar-pro"],
            MODELS["gemini-2.5-flash"],
            MODELS["claude-sonnet-4.6"],
            MODELS["deepseek-r1"],
            MODELS["qwen3-max"],
        ],
        features=[
            "Search-grounded responses",
            "Factual accuracy prioritized",
            "Best for literature stages",
            "Citation verification support",
        ],
    ),
    
    "berb-eu-sovereign": PresetConfig(
        name="berb-eu-sovereign",
        description="GDPR-compliant models - EU data sovereignty",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        primary_model="mistralai/mistral-large-2407",
        fallback_models=[
            "alibaba/qwen-max-2025-01-25",
            "zhipuai/glm-4-0520",
        ],
        cost_per_paper_estimate=(0.80, 1.20),
        models=[
            MODELS["mistral-large-3"],
            MODELS["qwen3-max"],
            MODELS["glm-4.5"],
            MODELS["minimax-m2.5"],
        ],
        features=[
            "GDPR compliant",
            "EU data sovereignty",
            "No US data transfer",
            "Suitable for sensitive research",
        ],
    ),
}


def get_preset(name: str) -> PresetConfig:
    """Get a preset configuration by name.
    
    Args:
        name: Preset name (e.g., "berb-research")
    
    Returns:
        PresetConfig with full configuration
    
    Raises:
        ValueError: If preset name not found
    """
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(
            f"Preset '{name}' not found. Available: {available}"
        )
    return PRESETS[name]


def list_presets() -> list[str]:
    """List all available preset names."""
    return list(PRESETS.keys())


def get_model(model_id: str) -> ModelConfig:
    """Get a model configuration by ID.
    
    Args:
        model_id: Model ID (e.g., "deepseek-v3.2")
    
    Returns:
        ModelConfig with full configuration
    
    Raises:
        ValueError: If model ID not found
    """
    if model_id not in MODELS:
        available = ", ".join(MODELS.keys())
        raise ValueError(
            f"Model '{model_id}' not found. Available: {available}"
        )
    return MODELS[model_id]


def list_models() -> list[str]:
    """List all available model IDs."""
    return list(MODELS.keys())


def get_models_for_stage(stage_id: str) -> list[ModelConfig]:
    """Get all models suitable for a specific pipeline stage.
    
    Args:
        stage_id: Pipeline stage ID (e.g., "8" for HYPOTHESIS_GEN)
    
    Returns:
        List of ModelConfig suitable for the stage
    """
    return [
        model for model in MODELS.values()
        if stage_id in model.stages
    ]


def to_llm_config(preset: PresetConfig) -> dict[str, Any]:
    """Convert preset to LLM client configuration dict.
    
    Args:
        preset: PresetConfig to convert
    
    Returns:
        Dictionary suitable for LLMConfig
    """
    return {
        "base_url": preset.base_url,
        "api_key_env": preset.api_key_env,
        "primary_model": preset.primary_model,
        "fallback_models": preset.fallback_models,
        "provider_name": "openrouter",
    }


# Convenience function for CLI
def print_preset_info(name: str | None = None) -> None:
    """Print preset information to stdout.
    
    Args:
        name: Specific preset name, or None for all
    """
    if name:
        preset = get_preset(name)
        print(f"\n{'='*60}")
        print(f"Preset: {preset.name}")
        print(f"{'='*60}")
        print(f"Description: {preset.description}")
        print(f"Base URL: {preset.base_url}")
        print(f"API Key Env: {preset.api_key_env}")
        print(f"Primary Model: {preset.primary_model}")
        print(f"Fallback Models: {', '.join(preset.fallback_models)}")
        print(f"Estimated Cost: ${preset.cost_per_paper_estimate[0]:.2f}-${preset.cost_per_paper_estimate[1]:.2f}/paper")
        print(f"\nFeatures:")
        for feature in preset.features:
            print(f"  ✓ {feature}")
        print(f"\nModels ({len(preset.models)}):")
        for model in preset.models:
            print(f"  • {model.model_id}")
            print(f"    Provider: {model.provider}")
            print(f"    Price: ${model.price_input:.2f}/${model.price_output:.2f} per 1M tokens")
            print(f"    Context: {model.context_window:,}")
            print(f"    Stages: {', '.join(model.stages)}")
            print(f"    Capabilities: {', '.join(model.capabilities)}")
    else:
        print("\nAvailable Presets:")
        print("="*60)
        for preset_name in PRESETS:
            preset = PRESETS[preset_name]
            print(f"\n{preset.name}")
            print(f"  {preset.description}")
            print(f"  Cost: ${preset.cost_per_paper_estimate[0]:.2f}-${preset.cost_per_paper_estimate[1]:.2f}/paper")
            print(f"  Primary: {preset.primary_model}")
        print(f"\nUse 'berb presets <name>' for detailed info")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print_preset_info(sys.argv[1])
    else:
        print_preset_info()
