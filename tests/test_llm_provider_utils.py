"""Tests for LLM provider utilities.

Tests for:
- get_provider_from_model()
- validate_model_for_provider()
- LLMProvider enum

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
from berb.llm.client import LLMProvider, get_provider_from_model, validate_model_for_provider


class TestLLMProviderEnum:
    """Test LLMProvider enum."""
    
    def test_all_providers_defined(self):
        """Test all 11 providers are defined."""
        expected_providers = [
            "openai", "anthropic", "google", "deepseek", "openrouter",
            "minimax", "qwen", "glm", "xai", "kimi", "perplexity", "mimo", "unknown"
        ]
        
        for provider_name in expected_providers:
            assert provider_name in [p.value for p in LLMProvider]
    
    def test_provider_values(self):
        """Test provider enum values."""
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.QWEN.value == "qwen"
        assert LLMProvider.UNKNOWN.value == "unknown"


class TestGetProviderFromModel:
    """Test get_provider_from_model() utility."""
    
    def test_standard_model_format(self):
        """Test provider extraction from standard model format."""
        assert get_provider_from_model("qwen/qwen3.5-flash") == LLMProvider.QWEN
        assert get_provider_from_model("openai/gpt-4") == LLMProvider.OPENAI
        assert get_provider_from_model("anthropic/claude-sonnet") == LLMProvider.ANTHROPIC
        assert get_provider_from_model("minimax/minimax-m2.5") == LLMProvider.MINIMAX
    
    def test_case_insensitive(self):
        """Test provider extraction is case-insensitive."""
        assert get_provider_from_model("QWEN/qwen3.5") == LLMProvider.QWEN
        assert get_provider_from_model("OpenAI/gpt-4") == LLMProvider.OPENAI
        assert get_provider_from_model("qWeN/qwen3.5") == LLMProvider.QWEN
    
    def test_unknown_model(self):
        """Test unknown model returns UNKNOWN."""
        assert get_provider_from_model("unknown-model") == LLMProvider.UNKNOWN
        assert get_provider_from_model("custom/model") == LLMProvider.UNKNOWN
    
    def test_empty_model(self):
        """Test empty model returns UNKNOWN."""
        assert get_provider_from_model("") == LLMProvider.UNKNOWN
        assert get_provider_from_model(None) == LLMProvider.UNKNOWN
    
    def test_all_providers(self):
        """Test provider extraction for all defined providers."""
        test_cases = [
            ("openai/gpt-4", LLMProvider.OPENAI),
            ("anthropic/claude-sonnet", LLMProvider.ANTHROPIC),
            ("google/gemini-3", LLMProvider.GOOGLE),
            ("deepseek/deepseek-chat", LLMProvider.DEEPSEEK),
            ("openrouter/auto", LLMProvider.OPENROUTER),
            ("minimax/minimax-m2.5", LLMProvider.MINIMAX),
            ("qwen/qwen3.5-flash", LLMProvider.QWEN),
            ("z-ai/glm-4.5", LLMProvider.GLM),
            ("x-ai/grok-4", LLMProvider.XAI),
            ("moonshotai/kimi-k2", LLMProvider.KIMI),
            ("perplexity/sonar-pro", LLMProvider.PERPLEXITY),
            ("xiaomi/mimo-v2", LLMProvider.MIMO),
        ]
        
        for model, expected_provider in test_cases:
            result = get_provider_from_model(model)
            assert result == expected_provider, f"Failed for {model}: expected {expected_provider}, got {result}"


class TestValidateModelForProvider:
    """Test validate_model_for_provider() utility."""
    
    def test_valid_model_provider(self):
        """Test valid model-provider pairs."""
        assert validate_model_for_provider("qwen/qwen3.5-flash", LLMProvider.QWEN) is True
        assert validate_model_for_provider("openai/gpt-4", LLMProvider.OPENAI) is True
        assert validate_model_for_provider("anthropic/claude", LLMProvider.ANTHROPIC) is True
    
    def test_invalid_model_provider(self):
        """Test invalid model-provider pairs."""
        assert validate_model_for_provider("qwen/qwen3.5-flash", LLMProvider.OPENAI) is False
        assert validate_model_for_provider("openai/gpt-4", LLMProvider.QWEN) is False
        assert validate_model_for_provider("anthropic/claude", LLMProvider.GOOGLE) is False
    
    def test_unknown_provider(self):
        """Test UNKNOWN provider always validates."""
        assert validate_model_for_provider("any-model", LLMProvider.UNKNOWN) is True
        assert validate_model_for_provider("qwen/qwen3.5", LLMProvider.UNKNOWN) is True
    
    def test_empty_model(self):
        """Test empty model validation."""
        assert validate_model_for_provider("", LLMProvider.QWEN) is True
        assert validate_model_for_provider(None, LLMProvider.QWEN) is True


class TestIntegration:
    """Integration tests for provider utilities."""
    
    def test_round_trip(self):
        """Test provider extraction and validation round-trip."""
        test_models = [
            "qwen/qwen3.5-flash",
            "openai/gpt-4",
            "anthropic/claude-sonnet",
            "minimax/minimax-m2.5",
        ]
        
        for model in test_models:
            provider = get_provider_from_model(model)
            assert provider != LLMProvider.UNKNOWN, f"Could not extract provider from {model}"
            assert validate_model_for_provider(model, provider), f"Validation failed for {model} with {provider}"
    
    def test_mismatch_detection(self):
        """Test detection of provider-model mismatch."""
        # qwen model with openai provider should fail
        model = "qwen/qwen3.5-flash"
        provider = get_provider_from_model(model)
        assert provider == LLMProvider.QWEN
        
        # Validate with wrong provider should fail
        assert validate_model_for_provider(model, LLMProvider.OPENAI) is False
