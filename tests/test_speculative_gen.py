"""Unit tests for speculative generation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from berb.llm.speculative_gen import (
    SpeculativeClient,
    SpeculativeConfig,
    get_speculative_config_for_stage,
)


class TestSpeculativeConfig:
    """Test SpeculativeConfig dataclass."""

    def test_create_config(self):
        """Test creating a speculative config."""
        config = SpeculativeConfig(
            cheap_model="gpt-4o-mini",
            premium_model="claude-sonnet",
            quality_threshold=0.85,
        )

        assert config.cheap_model == "gpt-4o-mini"
        assert config.premium_model == "claude-sonnet"
        assert config.quality_threshold == 0.85


class TestSpeculativeClient:
    """Test SpeculativeClient class."""

    @pytest.mark.asyncio
    async def test_cheap_used_on_good_quality(self):
        """Test cheap model used when quality is good."""
        mock_client = AsyncMock()

        # Cheap model returns good response
        cheap_response = MagicMock(
            content="A" * 500,  # Long content = good quality
            model="gpt-4o-mini",
            completion_tokens=500,
        )
        mock_client.chat.return_value = cheap_response

        config = SpeculativeConfig(
            cheap_model="gpt-4o-mini",
            premium_model="claude-sonnet",
            quality_threshold=0.85,
            enable_cancellation=True,
        )

        client = SpeculativeClient(mock_client, config)
        response = await client.chat([{"role": "user", "content": "test"}])

        # Should use cheap model
        assert response == cheap_response

        # Check statistics
        stats = client.get_stats()
        assert stats["cheap_used"] == 1
        assert stats["cheap_usage_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_premium_used_on_low_quality(self):
        """Test premium model used when cheap quality is low."""
        mock_client = AsyncMock()

        # Cheap model returns short response (low quality)
        cheap_response = MagicMock(
            content="x",  # Very short = low quality
            model="gpt-4o-mini",
        )

        # Premium model returns good response
        premium_response = MagicMock(
            content="A" * 500,
            model="claude-sonnet",
        )

        # First call is cheap, second is premium
        mock_client.chat.side_effect = [cheap_response, premium_response]

        config = SpeculativeConfig(
            cheap_model="gpt-4o-mini",
            premium_model="claude-sonnet",
            quality_threshold=0.85,
            premium_head_start=0.0,  # Start both immediately
        )

        client = SpeculativeClient(mock_client, config)
        response = await client.chat([{"role": "user", "content": "test"}])

        # Should use premium model
        assert response == premium_response

        # Check statistics
        stats = client.get_stats()
        assert stats["premium_used"] == 1

    @pytest.mark.asyncio
    async def test_cheap_timeout_fallback(self):
        """Test fallback to premium when cheap times out."""
        mock_client = AsyncMock()

        # Cheap model times out
        async def slow_chat(*args, **kwargs):
            await asyncio.sleep(10)  # Will timeout
            return MagicMock(content="response")

        # Premium model responds quickly
        premium_response = MagicMock(
            content="premium response",
            model="claude-sonnet",
        )

        async def fast_chat(*args, **kwargs):
            return premium_response

        # First call (cheap) is slow, second (premium) is fast
        call_count = [0]

        async def conditional_chat(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return await slow_chat(*args, **kwargs)
            else:
                return await fast_chat(*args, **kwargs)

        mock_client.chat = conditional_chat

        config = SpeculativeConfig(
            cheap_model="gpt-4o-mini",
            premium_model="claude-sonnet",
            cheap_timeout=0.1,  # 100ms timeout
        )

        client = SpeculativeClient(mock_client, config)
        response = await client.chat([{"role": "user", "content": "test"}])

        # Should use premium (cheap timed out)
        assert response == premium_response

    @pytest.mark.asyncio
    async def test_both_models_fail(self):
        """Test handling when both models fail."""
        mock_client = AsyncMock()
        mock_client.chat.side_effect = Exception("API error")

        config = SpeculativeConfig(
            cheap_model="gpt-4o-mini",
            premium_model="claude-sonnet",
        )

        client = SpeculativeClient(mock_client, config)
        response = await client.chat([{"role": "user", "content": "test"}])

        # Should return None response with error outcome
        assert response is None

    def test_default_evaluator(self):
        """Test default quality evaluator."""
        mock_client = AsyncMock()
        config = SpeculativeConfig()
        client = SpeculativeClient(mock_client, config)

        # Test short response (low quality)
        short_response = MagicMock(content="x")
        score = client._default_evaluator(short_response, [])
        assert score <= 0.7

        # Test refusal pattern (low quality)
        refusal_response = MagicMock(content="I cannot help with that")
        score = client._default_evaluator(refusal_response, [])
        assert score < 0.8

        # Test good response (high quality)
        good_response = MagicMock(content="A" * 500)
        score = client._default_evaluator(good_response, [])
        assert score > 0.7

        # Test JSON structure bonus
        json_messages = [{"content": "output json"}]
        json_response = MagicMock(content='{"key": "value"}')
        score = client._default_evaluator(json_response, json_messages)
        assert score >= 0.8

    def test_estimate_cost(self):
        """Test cost estimation."""
        mock_client = AsyncMock()
        config = SpeculativeConfig(
            cheap_model="gpt-4o-mini",
            premium_model="claude-sonnet",
        )
        client = SpeculativeClient(mock_client, config)

        response = MagicMock(completion_tokens=1000)

        saved = client._estimate_cost("claude-sonnet", response)

        # Should save money by using cheap instead of premium
        assert saved > 0

    def test_get_stats(self):
        """Test getting statistics."""
        mock_client = AsyncMock()
        config = SpeculativeConfig()
        client = SpeculativeClient(mock_client, config)

        # Simulate some requests
        client._total_requests = 10
        client._cheap_used = 7
        client._premium_used = 3
        client._total_saved = 0.05

        stats = client.get_stats()

        assert stats["total_requests"] == 10
        assert stats["cheap_used"] == 7
        assert stats["premium_used"] == 3
        assert stats["cheap_usage_rate"] == 0.7
        assert stats["total_saved"] == 0.05


class TestGetSpeculativeConfigForStage:
    """Test stage-specific configuration."""

    def test_critical_stages(self):
        """Test config for critical stages."""
        config = get_speculative_config_for_stage("PEER_REVIEW")

        # Should have higher threshold
        assert config.quality_threshold == 0.90
        assert config.premium_model.startswith("anthropic")

    def test_creative_stages(self):
        """Test config for creative stages."""
        config = get_speculative_config_for_stage("PAPER_DRAFT")

        # Should use cheaper models and lower threshold
        assert config.cheap_model == "gpt-4o-mini"
        assert config.quality_threshold == 0.80

    def test_default_stages(self):
        """Test config for default stages."""
        config = get_speculative_config_for_stage("UNKNOWN_STAGE")

        # Should use default configuration
        assert config.cheap_model == "gpt-4o-mini"
        assert config.quality_threshold == 0.85
