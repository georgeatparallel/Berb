"""LLM integration — OpenAI-compatible and ACP agent clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export LLMProvider enum and utilities for cross-model review
from berb.llm.client import (
    LLMProvider,
    get_provider_from_model,
    validate_model_for_provider,
)

__all__ = [
    "LLMProvider",
    "get_provider_from_model",
    "validate_model_for_provider",
    "PROVIDER_PRESETS",
    # OpenRouter adapter
    "ModelVariant",
    "ProviderRouting",
    "OpenRouterProvider",
    "strip_variant",
    "ROUTING_EXACT",
    "ROUTING_NITRO",
    "ROUTING_ANTHROPIC_DIRECT",
    # Preset exports
    "MODELS",
    "PRESETS",
    "ModelConfig",
    "PresetConfig",
    "get_model",
    "get_models_for_stage",
    "get_preset",
    "list_models",
    "list_presets",
    "print_preset_info",
    "to_llm_config",
]

if TYPE_CHECKING:
    from berb.config import RCConfig
    from berb.llm.acp_client import ACPClient
    from berb.llm.client import LLMClient, MultiProviderLLMClient
    from berb.llm.presets import ModelConfig, PresetConfig
    from berb.llm.smart_client import SmartLLMClient

# Provider presets for common LLM services
PROVIDER_PRESETS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-v4-flash",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-4.3",
    },
    "perplexity": {
        "base_url": "https://api.perplexity.ai",
        "default_model": "sonar-pro",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
    },
    "kimi-anthropic": {
        "base_url": "https://api.kimi.com/coding/",
    },
    "novita": {
        "base_url": "https://api.novita.ai/openai",
    },
    "minimax": {
        "base_url": "https://api.minimax.io/v1",
    },
    "openai-compatible": {
        "base_url": None,  # Use user-provided base_url
    },
}

# Re-export OpenRouter variant routing API
from berb.llm.openrouter_adapter import (  # noqa: E402
    ModelVariant,
    OpenRouterProvider,
    ProviderRouting,
    ROUTING_ANTHROPIC_DIRECT,
    ROUTING_EXACT,
    ROUTING_NITRO,
    strip_variant,
)

# Re-export preset functions for convenience
from berb.llm.presets import (  # noqa: E402
    MODELS,
    PRESETS,
    ModelConfig,
    PresetConfig,
    get_model,
    get_models_for_stage,
    get_preset,
    list_models,
    list_presets,
    print_preset_info,
    to_llm_config,
)


def create_llm_client(
    config: RCConfig,
) -> LLMClient | ACPClient | SmartLLMClient | MultiProviderLLMClient:
    """Factory: return the right LLM client based on ``config.llm.provider``.

    - ``"acp"`` → :class:`ACPClient` (spawns an ACP-compatible agent)
    - ``"anthropic"`` → :class:`LLMClient` with Anthropic Messages API adapter
    - ``"kimi-anthropic"`` → :class:`LLMClient` with Kimi Coding Anthropic adapter
    - ``"openrouter"`` → :class:`LLMClient` with OpenRouter base URL
    - ``"openai"`` → :class:`LLMClient` with OpenAI base URL
    - ``"deepseek"`` → :class:`LLMClient` with DeepSeek base URL
    - ``"novita"`` → :class:`LLMClient` with Novita AI base URL
    - ``"minimax"`` → :class:`LLMClient` with MiniMax base URL
    - ``"openai-compatible"`` (default) → :class:`LLMClient` with custom base_url

    If config.nadirclaw.enabled or config.token_tracking.enabled, wraps
    the base client with SmartLLMClient for intelligent routing and tracking.
    """
    if config.llm.provider == "acp":
        from berb.llm.acp_client import ACPClient as _ACP  # noqa: N814

        base_client = _ACP.from_rc_config(config)
    elif config.llm.fallback_providers:
        from berb.llm.client import MultiProviderLLMClient as _MPC  # noqa: N814

        base_client = _MPC.from_rc_config(config)
    else:
        from berb.llm.client import LLMClient as _LLM  # noqa: N814

        base_client = _LLM.from_rc_config(config)

    # Wrap with SmartLLMClient if NadirClaw or tracking is enabled
    if (hasattr(config, "nadirclaw") and config.nadirclaw.enabled) or (
        hasattr(config, "token_tracking") and config.token_tracking.enabled
    ):
        from berb.llm.smart_client import SmartLLMClient

        return SmartLLMClient(
            config=base_client.config,
            nadirclaw_config=getattr(config, "nadirclaw", None),
            tracking_config=getattr(config, "token_tracking", None),
            project_path=config.project.name if hasattr(config, "project") else None,
        )

    return base_client
