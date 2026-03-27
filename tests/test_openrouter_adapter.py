"""Tests for OpenRouter adapter."""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from berb.llm.openrouter_adapter import (
    OpenRouterProvider,
    OpenRouterModel,
    OPENROUTER_MODELS,
)
from berb.llm.client import LLMResponse


class TestOpenRouterModel:
    """Test OpenRouterModel dataclass."""
    
    def test_model_creation(self):
        """Test creating model configuration."""
        model = OpenRouterModel(
            id="test/model",
            name="Test Model",
            provider="test",
            input_price=0.50,
            output_price=1.50,
            context_length=128000,
        )
        
        assert model.id == "test/model"
        assert model.name == "Test Model"
        assert model.provider == "test"
        assert model.input_price == 0.50
        assert model.output_price == 1.50
        assert model.context_length == 128000
        assert model.tier == "mid"
    
    def test_preconfigured_models(self):
        """Test pre-configured models exist."""
        assert len(OPENROUTER_MODELS) > 0
        
        # Check key models exist
        assert "deepseek/deepseek-chat-v3-0324" in OPENROUTER_MODELS
        assert "anthropic/claude-3.5-sonnet" in OPENROUTER_MODELS
        assert "openai/gpt-4o" in OPENROUTER_MODELS


class TestOpenRouterProvider:
    """Test OpenRouterProvider class."""
    
    def test_init_with_api_key(self):
        """Test initialization with API key."""
        provider = OpenRouterProvider(
            api_key="sk-or-test-key",
            model="anthropic/claude-3.5-sonnet",
        )
        
        assert provider.api_key == "sk-or-test-key"
        assert provider.model == "anthropic/claude-3.5-sonnet"
        assert provider.model_info is not None
        assert provider.model_info.name == "Claude 3.5 Sonnet"
    
    def test_init_without_api_key(self):
        """Test initialization without API key raises error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API key not provided"):
                OpenRouterProvider()
    
    def test_init_with_env_var(self):
        """Test initialization with environment variable."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-env-key"}):
            provider = OpenRouterProvider()
            assert provider.api_key == "sk-or-env-key"
    
    def test_get_model_info(self):
        """Test getting model information."""
        provider = OpenRouterProvider(
            api_key="sk-or-test-key",
            model="deepseek/deepseek-chat-v3-0324",
        )
        
        info = provider.get_model_info()
        assert info.name == "DeepSeek V3"
        assert info.tier == "budget"
        assert info.input_price == 0.27
    
    def test_calculate_cost(self):
        """Test cost calculation."""
        provider = OpenRouterProvider(
            api_key="sk-or-test-key",
            model="deepseek/deepseek-chat-v3-0324",
        )
        
        # 1000 input tokens, 500 output tokens
        cost = provider._calculate_cost(1000, 500)
        
        # DeepSeek V3: $0.27/1M input, $1.10/1M output
        expected = (1000 / 1_000_000) * 0.27 + (500 / 1_000_000) * 1.10
        assert abs(cost - expected) < 0.0001
    
    def test_get_available_models(self):
        """Test filtering available models."""
        # Filter by tier
        budget_models = OpenRouterProvider.get_available_models(tier="budget")
        assert len(budget_models) > 0
        assert all(m.tier == "budget" for m in budget_models)
        
        # Filter by provider
        anthropic_models = OpenRouterProvider.get_available_models(provider="anthropic")
        assert len(anthropic_models) > 0
        assert all(m.provider == "anthropic" for m in anthropic_models)
        
        # Filter by context length
        long_context = OpenRouterProvider.get_available_models(min_context=500000)
        assert len(long_context) > 0
        assert all(m.context_length >= 500000 for m in long_context)
    
    @pytest.mark.asyncio
    async def test_complete_success(self):
        """Test successful completion."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Test response"}
            }],
            "model": "anthropic/claude-3.5-sonnet",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        mock_response.raise_for_status.return_value = None
        
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            provider = OpenRouterProvider(api_key="sk-or-test-key")
            response = await provider.complete([
                {"role": "user", "content": "Hello"}
            ])
            
            assert isinstance(response, LLMResponse)
            assert response.content == "Test response"
            assert response.model == "anthropic/claude-3.5-sonnet"
            assert response.prompt_tokens == 10
            assert response.completion_tokens == 5
    
    @pytest.mark.asyncio
    async def test_complete_with_retry(self):
        """Test completion with retry on failure."""
        # First call fails, second succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.raise_for_status.side_effect = Exception("Rate limit")
        
        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Success"}}],
            "usage": {},
        }
        mock_response_success.raise_for_status.return_value = None
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = [mock_response_fail, mock_response_success]
            
            provider = OpenRouterProvider(
                api_key="sk-or-test-key",
                max_retries=2,
            )
            response = await provider.complete([
                {"role": "user", "content": "Hello"}
            ])
            
            assert response.content == "Success"
            assert mock_post.call_count == 2
    
    @pytest.mark.asyncio
    async def test_complete_max_retries_exceeded(self):
        """Test completion fails after max retries."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API error")
        
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            provider = OpenRouterProvider(
                api_key="sk-or-test-key",
                max_retries=3,
            )
            
            with pytest.raises(Exception, match="failed after 3 retries"):
                await provider.complete([
                    {"role": "user", "content": "Hello"}
                ])
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        with patch("httpx.AsyncClient"):
            async with OpenRouterProvider(api_key="sk-or-test-key") as provider:
                assert provider is not None
    
    def test_model_tiers(self):
        """Test model tier classification."""
        budget = OpenRouterProvider.get_available_models(tier="budget")
        mid = OpenRouterProvider.get_available_models(tier="mid")
        premium = OpenRouterProvider.get_available_models(tier="premium")
        
        # Check budget models are cheaper
        assert all(m.input_price < 0.50 for m in budget)
        assert all(m.input_price >= 0.50 and m.input_price < 5.00 for m in mid)
        assert all(m.input_price >= 5.00 for m in premium)
    
    def test_vision_support(self):
        """Test vision support detection."""
        vision_models = [m for m in OPENROUTER_MODELS.values() if m.supports_vision]
        non_vision_models = [m for m in OPENROUTER_MODELS.values() if not m.supports_vision]
        
        assert len(vision_models) > 0
        assert len(non_vision_models) > 0
        
        # Check specific models
        assert OPENROUTER_MODELS["openai/gpt-4o"].supports_vision is True
        assert OPENROUTER_MODELS["openai/o1"].supports_vision is False
