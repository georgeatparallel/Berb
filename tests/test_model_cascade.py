"""Unit tests for model cascading."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from berb.llm.model_cascade import (
    CascadeStep,
    CascadeConfig,
    CascadeStats,
    CascadingLLMClient,
    get_cascade_for_stage,
)


class TestCascadeStep:
    """Test CascadeStep dataclass."""

    def test_create_step(self):
        """Test creating a cascade step."""
        step = CascadeStep(
            model="gpt-4o",
            min_score=0.75,
            max_tokens=2000,
            temperature=0.7,
        )

        assert step.model == "gpt-4o"
        assert step.min_score == 0.75
        assert step.max_tokens == 2000
        assert step.temperature == 0.7


class TestCascadeConfig:
    """Test CascadeConfig dataclass."""

    def test_create_config(self):
        """Test creating a cascade config."""
        config = CascadeConfig(
            cascade=[
                CascadeStep("deepseek", 0.70),
                CascadeStep("gpt-4o", 0.0),
            ],
            quick_eval_enabled=True,
        )

        assert len(config.cascade) == 2
        assert config.quick_eval_enabled is True


class TestCascadingLLMClient:
    """Test CascadingLLMClient class."""

    @pytest.mark.asyncio
    async def test_single_step_accept(self):
        """Test cascade with single step accepts response."""
        mock_client = AsyncMock()
        mock_response = MagicMock(content="response", model="gpt-4o")
        mock_client.chat.return_value = mock_response

        config = CascadeConfig(
            cascade=[CascadeStep("gpt-4o", min_score=0.0)],
            quick_eval_enabled=False,
        )

        client = CascadingLLMClient(mock_client, config)
        response = await client.chat([{"role": "user", "content": "test"}])

        assert response == mock_response
        mock_client.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_cascade_exit_early(self):
        """Test cascade exits early when quality met."""
        mock_client = AsyncMock()
        mock_response = MagicMock(
            content="good response",
            model="deepseek",
        )
        mock_client.chat.return_value = mock_response

        config = CascadeConfig(
            cascade=[
                CascadeStep("deepseek", min_score=0.70),
                CascadeStep("gpt-4o", min_score=0.0),
            ],
        )

        client = CascadingLLMClient(mock_client, config)
        response = await client.chat([{"role": "user", "content": "test"}])

        # Should only call first model (quality met)
        assert mock_client.chat.call_count == 1
        assert response.model == "deepseek"

    @pytest.mark.asyncio
    async def test_cascade_continue_on_low_quality(self):
        """Test cascade continues when quality not met."""
        mock_client = AsyncMock()

        # First call returns low quality, second returns good quality
        low_quality = MagicMock(content="bad", model="deepseek")
        good_quality = MagicMock(content="good", model="gpt-4o")
        mock_client.chat.side_effect = [low_quality, good_quality]

        config = CascadeConfig(
            cascade=[
                CascadeStep("deepseek", min_score=0.90),  # High threshold
                CascadeStep("gpt-4o", min_score=0.0),
            ],
        )

        client = CascadingLLMClient(mock_client, config)
        response = await client.chat([{"role": "user", "content": "test"}])

        # Should call both models
        assert mock_client.chat.call_count == 2
        assert response.model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_cascade_all_fail(self):
        """Test cascade when all steps fail."""
        mock_client = AsyncMock()
        mock_client.chat.side_effect = Exception("API error")

        config = CascadeConfig(
            cascade=[
                CascadeStep("deepseek", min_score=0.0),
                CascadeStep("gpt-4o", min_score=0.0),
            ],
        )

        client = CascadingLLMClient(mock_client, config)

        with pytest.raises(RuntimeError, match="All cascade steps failed"):
            await client.chat([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_default_evaluator(self):
        """Test default quality evaluator."""
        mock_client = AsyncMock()
        config = CascadeConfig(cascade=[CascadeStep("gpt-4o", min_score=0.0)])

        client = CascadingLLMClient(mock_client, config)

        # Test short response
        short_response = MagicMock(content="x")
        score = client._default_evaluator(short_response, [])
        assert score <= 0.7

        # Test refusal pattern
        refusal_response = MagicMock(content="I cannot help with that")
        score = client._default_evaluator(refusal_response, [])
        assert score < 0.8

        # Test good response
        good_response = MagicMock(content="A" * 200)
        score = client._default_evaluator(good_response, [])
        assert score > 0.7

        # Test JSON structure bonus
        json_messages = [{"content": "output json"}]
        json_response = MagicMock(content='{"key": "value"}')
        score = client._default_evaluator(json_response, json_messages)
        assert score >= 0.89  # Should be ~0.9 with JSON bonus (floating point)

    def test_get_stats(self):
        """Test getting cascade statistics."""
        mock_client = AsyncMock()
        config = CascadeConfig(
            cascade=[
                CascadeStep("deepseek", min_score=0.70),
                CascadeStep("gpt-4o", min_score=0.0),
            ],
        )

        client = CascadingLLMClient(mock_client, config)

        # Simulate some requests
        client._total_requests = 10
        client._cascade_exits = {0: 7, 1: 3}  # 7 exited at step 0, 3 at step 1

        stats = client.get_stats()

        assert stats["total_requests"] == 10
        assert 0 in stats["cascade_exits"]
        assert stats["average_exit_step"] > 0

    @pytest.mark.asyncio
    async def test_stage_specific_cascade(self):
        """Test stage-specific cascade configuration."""
        mock_client = AsyncMock()
        mock_response = MagicMock(content="response")
        mock_client.chat.return_value = mock_response

        # Get cascade for literature collection (should start cheap)
        config = get_cascade_for_stage("LITERATURE_COLLECT")

        client = CascadingLLMClient(mock_client, config)
        await client.chat([{"role": "user", "content": "test"}])

        # Should try deepseek first (cheapest)
        first_call_model = mock_client.chat.call_args_list[0][1]["model"]
        assert "deepseek" in first_call_model.lower()


class TestGetCascadeForStage:
    """Test get_cascade_for_stage function."""

    def test_simple_tasks(self):
        """Test cascade for simple tasks."""
        config = get_cascade_for_stage("TOPIC_INIT")

        # Should start with cheapest model
        assert config.cascade[0].model.lower().startswith("deepseek")
        assert config.cascade[0].min_score == 0.70

    def test_reasoning_tasks(self):
        """Test cascade for reasoning tasks."""
        config = get_cascade_for_stage("HYPOTHESIS_GEN")

        # Should start with mid-tier
        assert config.cascade[0].model.lower().startswith("openai")
        assert config.cascade[0].min_score == 0.75

    def test_critical_tasks(self):
        """Test cascade for critical tasks."""
        config = get_cascade_for_stage("PEER_REVIEW")

        # Should use premium model directly (no cascading)
        assert len(config.cascade) == 1
        assert "claude-sonnet" in config.cascade[0].model.lower()

    def test_default_cascade(self):
        """Test default cascade for unknown stage."""
        config = get_cascade_for_stage("UNKNOWN_STAGE")

        # Should have balanced cascade
        assert len(config.cascade) == 3
        assert config.cascade[0].min_score == 0.75
