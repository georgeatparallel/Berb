"""Tests pinning PROVIDER_PRESETS shape and default model IDs.

Default model IDs must match models the provider endpoint actually
serves. Verified against live /models endpoints on 2026-07-06:
- DeepSeek retired "deepseek-chat"; serves deepseek-v4-flash / deepseek-v4-pro.
- xAI retired "grok-4"; grok-4.3 was the current general model, since
  superseded by grok-4.5 (migrated 2026-07-09; see docs.x.ai/developers/models/grok-4.5).
- Perplexity has no /models endpoint; "sonar-pro" confirmed via chat probe.
"""

from __future__ import annotations

from berb.llm import PROVIDER_PRESETS

EXPECTED_PROVIDERS = {
    "openai",
    "openrouter",
    "deepseek",
    "xai",
    "perplexity",
    "anthropic",
    "kimi-anthropic",
    "novita",
    "minimax",
    "openai-compatible",
}

EXPECTED_DEFAULT_MODELS = {
    "deepseek": "deepseek-v4-flash",
    "xai": "grok-4.5",
    "perplexity": "sonar-pro",
}


class TestProviderPresetShape:
    def test_all_expected_providers_registered(self):
        assert set(PROVIDER_PRESETS) == EXPECTED_PROVIDERS

    def test_every_preset_has_base_url_key(self):
        for name, preset in PROVIDER_PRESETS.items():
            assert "base_url" in preset, f"{name} missing base_url"

    def test_only_openai_compatible_has_null_base_url(self):
        for name, preset in PROVIDER_PRESETS.items():
            if name == "openai-compatible":
                assert preset["base_url"] is None
            else:
                assert isinstance(preset["base_url"], str)
                assert preset["base_url"].startswith("https://")

    def test_preset_keys_limited_to_known_fields(self):
        allowed = {"base_url", "default_model"}
        for name, preset in PROVIDER_PRESETS.items():
            extra = set(preset) - allowed
            assert not extra, f"{name} has unexpected keys: {extra}"


class TestDefaultModelIds:
    def test_default_models_pinned_to_live_ids(self):
        for provider, model in EXPECTED_DEFAULT_MODELS.items():
            assert PROVIDER_PRESETS[provider]["default_model"] == model

    def test_no_retired_deepseek_chat_anywhere(self):
        for name, preset in PROVIDER_PRESETS.items():
            assert preset.get("default_model") != "deepseek-chat", (
                f"{name} references retired DeepSeek model ID"
            )

    def test_cli_setup_deepseek_models_match_live_ids(self):
        from berb.cli import _PROVIDER_MODELS

        primary, alternates = _PROVIDER_MODELS["deepseek"]
        assert primary == "deepseek-v4-flash"
        assert alternates == ["deepseek-v4-pro"]
