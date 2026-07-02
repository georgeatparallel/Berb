"""Unit tests for adaptive temperature."""

import pytest
from unittest.mock import AsyncMock

from berb.llm.adaptive_temp import (
    AdaptiveTemperatureClient,
    TemperatureStrategy,
    RetryStage,
    TASK_STRATEGIES,
    DEFAULT_STRATEGY,
    get_temperature_for_stage,
)


class TestTemperatureStrategy:
    """Test TemperatureStrategy dataclass."""

    def test_create_strategy(self):
        """Test creating a temperature strategy."""
        strategy = TemperatureStrategy(
            initial=0.0,
            retry_1=0.2,
            retry_2=0.4,
        )

        assert strategy.initial == 0.0
        assert strategy.retry_1 == 0.2
        assert strategy.retry_2 == 0.4

    def test_get_temperature(self):
        """Test getting temperature for retry count."""
        strategy = TemperatureStrategy(
            initial=0.0,
            retry_1=0.2,
            retry_2=0.4,
            retry_3=0.7,
        )

        assert strategy.get_temperature(0) == 0.0
        assert strategy.get_temperature(1) == 0.2
        assert strategy.get_temperature(2) == 0.4
        assert strategy.get_temperature(3) == 0.7
        assert strategy.get_temperature(4) == 0.7  # Max retry


class TestPredefinedStrategies:
    """Test predefined task strategies."""

    def test_decomposition_strategy(self):
        """Test decomposition strategy (deterministic)."""
        strategy = TASK_STRATEGIES["decomposition"]

        assert strategy.initial == 0.0  # Start deterministic
        assert strategy.retry_1 == 0.2
        assert strategy.retry_2 == 0.4

    def test_hypothesis_gen_strategy(self):
        """Test hypothesis generation strategy (creative)."""
        strategy = TASK_STRATEGIES["hypothesis_gen"]

        assert strategy.initial == 0.3  # Start moderate
        assert strategy.retry_1 == 0.5
        assert strategy.retry_2 == 0.7

    def test_peer_review_strategy(self):
        """Test peer review strategy (critical, stay deterministic)."""
        strategy = TASK_STRATEGIES["peer_review"]

        assert strategy.initial == 0.0
        assert strategy.retry_1 == 0.1  # Minimal increase
        assert strategy.retry_2 == 0.2


class TestAdaptiveTemperatureClient:
    """Test AdaptiveTemperatureClient class."""

    @pytest.mark.asyncio
    async def test_initial_call_zero_temperature(self):
        """Test initial call uses zero temperature."""
        mock_client = AsyncMock()
        mock_client.chat.return_value = "response"

        client = AdaptiveTemperatureClient(mock_client)
        await client.chat([{"role": "user", "content": "test"}])

        # Verify temperature=0.0 was used
        mock_client.chat.assert_called_once()
        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_retry_increases_temperature(self):
        """Test retries use higher temperature."""
        mock_client = AsyncMock()

        # First two calls fail, third succeeds
        mock_client.chat.side_effect = [
            Exception("Fail 1"),
            Exception("Fail 2"),
            "success",
        ]

        client = AdaptiveTemperatureClient(mock_client, max_retries=3)
        response = await client.chat([{"role": "user", "content": "test"}])

        assert response == "success"
        assert mock_client.chat.call_count == 3

        # Verify temperatures increased
        calls = mock_client.chat.call_args_list
        assert calls[0][1]["temperature"] == 0.0  # Initial
        assert calls[1][1]["temperature"] == 0.2  # Retry 1
        assert calls[2][1]["temperature"] == 0.4  # Retry 2

    @pytest.mark.asyncio
    async def test_stage_specific_strategy(self):
        """Test stage-specific temperature strategy."""
        mock_client = AsyncMock()
        mock_client.chat.return_value = "response"

        client = AdaptiveTemperatureClient(mock_client)

        # Hypothesis generation should use creative strategy
        await client.chat(
            [{"role": "user", "content": "test"}],
            stage="HYPOTHESIS_GEN",
        )

        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["temperature"] == 0.3  # hypothesis_gen initial

    @pytest.mark.asyncio
    async def test_temperature_override(self):
        """Test manual temperature override."""
        mock_client = AsyncMock()
        mock_client.chat.return_value = "response"

        client = AdaptiveTemperatureClient(mock_client)

        await client.chat(
            [{"role": "user", "content": "test"}],
            temperature=0.9,  # Override
        )

        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_all_retries_fail(self):
        """Test handling when all retries fail."""
        mock_client = AsyncMock()
        mock_client.chat.side_effect = Exception("Always fail")

        client = AdaptiveTemperatureClient(mock_client, max_retries=2)

        with pytest.raises(RuntimeError, match="All retries failed"):
            await client.chat([{"role": "user", "content": "test"}])

        # Should have tried 3 times (initial + 2 retries)
        assert mock_client.chat.call_count == 3

    def test_get_stats(self):
        """Test getting statistics."""
        mock_client = AsyncMock()
        mock_client.chat.return_value = "response"

        client = AdaptiveTemperatureClient(mock_client)

        # Simulate some requests with different retry counts
        client._total_requests = 10
        client._retry_counts = {0: 7, 1: 2, 2: 1}

        stats = client.get_stats()

        assert stats["total_requests"] == 10
        assert stats["retry_distribution"] == {0: 7, 1: 2, 2: 1}
        assert stats["zero_retry_rate"] == 0.7  # 7/10 succeeded on first try


class TestGetTemperatureForStage:
    """Test get_temperature_for_stage function."""

    def test_decomposition_stage(self):
        """Test temperature for decomposition stage."""
        temp = get_temperature_for_stage("PROBLEM_DECOMPOSE", retry_count=0)

        assert temp == 0.0  # Deterministic

    def test_hypothesis_stage(self):
        """Test temperature for hypothesis stage."""
        temp = get_temperature_for_stage("HYPOTHESIS_GEN", retry_count=0)

        assert temp == 0.3  # Creative

    def test_unknown_stage(self):
        """Test temperature for unknown stage."""
        temp = get_temperature_for_stage("UNKNOWN_STAGE", retry_count=0)

        assert temp == DEFAULT_STRATEGY.initial
