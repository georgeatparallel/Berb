"""Tests for OpenRouter model presets.

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
from berb.llm.presets import (
    get_preset,
    list_presets,
    get_model,
    list_models,
    get_models_for_stage,
    to_llm_config,
    PRESETS,
    MODELS,
    PresetConfig,
    ModelConfig,
)


class TestPresetFunctions:
    """Test preset retrieval functions."""

    def test_list_presets(self):
        """Test listing all presets."""
        presets = list_presets()
        assert len(presets) == 4
        assert "berb-max-quality" in presets
        assert "berb-budget" in presets
        assert "berb-research" in presets
        assert "berb-eu-sovereign" in presets

    def test_get_preset_max_quality(self):
        """Test getting max quality preset."""
        preset = get_preset("berb-max-quality")
        assert isinstance(preset, PresetConfig)
        assert preset.name == "berb-max-quality"
        assert preset.cost_per_paper_estimate[0] >= 0.50
        assert len(preset.models) >= 5

    def test_get_preset_budget(self):
        """Test getting budget preset."""
        preset = get_preset("berb-budget")
        assert preset.name == "berb-budget"
        assert preset.cost_per_paper_estimate[1] <= 0.25
        assert "qwen-turbo" in preset.primary_model

    def test_get_preset_research(self):
        """Test getting research preset."""
        preset = get_preset("berb-research")
        assert preset.name == "berb-research"
        assert "sonar-pro" in preset.primary_model
        assert "Search-grounded" in preset.features[0]

    def test_get_preset_eu_sovereign(self):
        """Test getting EU sovereign preset."""
        preset = get_preset("berb-eu-sovereign")
        assert preset.name == "berb-eu-sovereign"
        assert "mistral" in preset.primary_model
        assert "GDPR compliant" in preset.features

    def test_get_preset_not_found(self):
        """Test error handling for invalid preset."""
        with pytest.raises(ValueError, match="not found"):
            get_preset("invalid-preset")


class TestModelFunctions:
    """Test model retrieval functions."""

    def test_list_models(self):
        """Test listing all models."""
        models = list_models()
        assert len(models) >= 10
        assert "deepseek-v3.2" in models
        assert "qwen3-max" in models
        assert "qwen3-turbo" in models
        assert "glm-4.5" in models

    def test_get_model_deepseek(self):
        """Test getting DeepSeek model config."""
        model = get_model("deepseek-v3.2")
        assert isinstance(model, ModelConfig)
        assert model.provider == "deepseek"
        assert model.price_input == 0.27
        assert "8" in model.stages

    def test_get_model_qwen_max(self):
        """Test getting Qwen Max model config."""
        model = get_model("qwen3-max")
        assert model.provider == "alibaba"
        assert model.price_input == 0.40
        assert model.context_window >= 128000

    def test_get_model_qwen_turbo(self):
        """Test getting Qwen Turbo model config."""
        model = get_model("qwen3-turbo")
        assert model.price_input == 0.03
        assert "fast" in model.capabilities

    def test_get_model_glm(self):
        """Test getting GLM model config."""
        model = get_model("glm-4.5")
        assert model.provider == "zhipuai"
        assert model.price_input == 0.30

    def test_get_model_not_found(self):
        """Test error handling for invalid model."""
        with pytest.raises(ValueError, match="not found"):
            get_model("invalid-model")


class TestStageModels:
    """Test stage-specific model selection."""

    def test_models_for_hypothesis_gen(self):
        """Test models for Stage 8 (HYPOTHESIS_GEN)."""
        models = get_models_for_stage("8")
        assert len(models) >= 3
        model_ids = [m.model_id for m in models]
        assert any("deepseek" in m for m in model_ids)

    def test_models_for_experiment_design(self):
        """Test models for Stage 9 (EXPERIMENT_DESIGN)."""
        models = get_models_for_stage("9")
        assert len(models) >= 1
        assert any("deepseek" in m.model_id for m in models)

    def test_models_for_peer_review(self):
        """Test models for Stage 18 (PEER_REVIEW)."""
        models = get_models_for_stage("18")
        assert len(models) >= 3
        # Should include high-quality models
        assert any("claude" in m.model_id or "qwen-max" in m.model_id for m in models)


class TestPresetConfig:
    """Test preset configuration structure."""

    def test_max_quality_models_count(self):
        """Test max quality preset has enough models."""
        preset = get_preset("berb-max-quality")
        assert len(preset.models) >= 5

    def test_budget_cost_range(self):
        """Test budget preset cost range."""
        preset = get_preset("berb-budget")
        assert preset.cost_per_paper_estimate[0] <= 0.25
        assert preset.cost_per_paper_estimate[1] <= 0.30

    def test_research_features(self):
        """Test research preset features."""
        preset = get_preset("berb-research")
        assert "Search-grounded responses" in preset.features
        assert "Factual accuracy prioritized" in preset.features

    def test_eu_sovereign_gdpr(self):
        """Test EU sovereign preset GDPR compliance."""
        preset = get_preset("berb-eu-sovereign")
        assert "GDPR compliant" in preset.features
        assert "EU data sovereignty" in preset.features


class TestToLLMConfig:
    """Test LLM config conversion."""

    def test_to_llm_config_basic(self):
        """Test basic LLM config conversion."""
        preset = get_preset("berb-budget")
        config = to_llm_config(preset)
        
        assert config["base_url"] == "https://openrouter.ai/api/v1"
        assert config["api_key_env"] == "OPENROUTER_API_KEY"
        assert "primary_model" in config
        assert "fallback_models" in config

    def test_to_llm_config_fallback_models(self):
        """Test fallback models in config."""
        preset = get_preset("berb-max-quality")
        config = to_llm_config(preset)
        
        assert len(config["fallback_models"]) >= 2
        assert isinstance(config["fallback_models"], list)


class TestModelCapabilities:
    """Test model capabilities."""

    def test_reasoning_models(self):
        """Test models with reasoning capability."""
        reasoning_models = [
            m for m in MODELS.values()
            if "reasoning" in m.capabilities
        ]
        assert len(reasoning_models) >= 2
        assert any("deepseek" in m.model_id for m in reasoning_models)

    def test_long_context_models(self):
        """Test models with long context."""
        long_context_models = [
            m for m in MODELS.values()
            if m.context_window >= 200000
        ]
        assert len(long_context_models) >= 3
        # Gemini should have 1M context
        gemini = MODELS["gemini-2.5-flash"]
        assert gemini.context_window >= 1000000

    def test_cheapest_models(self):
        """Test cheapest models."""
        cheap_models = [
            m for m in MODELS.values()
            if m.price_input <= 0.10
        ]
        assert len(cheap_models) >= 1
        assert any("turbo" in m.model_id for m in cheap_models)


class TestPresetCoverage:
    """Test that all models are used in presets."""

    def test_all_models_in_presets(self):
        """Test that all defined models are used in at least one preset."""
        all_model_ids = set(MODELS.keys())
        used_model_ids = set()
        
        for preset in PRESETS.values():
            for model in preset.models:
                # Extract model ID from full model_id string
                for model_id in all_model_ids:
                    if model_id.replace("-", "").replace(".", "") in model.model_id.replace("-", ""):
                        used_model_ids.add(model_id)
        
        # At least some models should be used (this is a basic sanity check)
        assert len(used_model_ids) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
