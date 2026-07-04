"""LLM client wrapper with NadirClaw routing and token tracking.

This module wraps the base LLMClient with:
- NadirClaw intelligent model routing
- Token consumption tracking
- Context optimization
- Cost estimation

Architecture: Decorator + Proxy patterns
Paradigm: Functional + Async

Example:
    >>> config = LLMConfig(base_url="...", api_key="...")
    >>> router = SmartLLMClient(config, nadirclaw_enabled=True, tracking_enabled=True)
    >>> response = await router.complete(messages)
    >>> print(f"Model: {response.model}, Cost: ${response.estimated_cost:.4f}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from berb.llm.client import LLMClient, LLMConfig, LLMResponse
from berb.llm.nadirclaw_router import NadirClawRouter
from berb.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


@dataclass
class SmartLLMResponse:
    """Extended LLM response with routing and cost info."""

    response: LLMResponse
    selected_model: str
    selected_tier: str
    routing_confidence: float
    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    estimated_cost: float
    routing_latency_ms: int


class SmartLLMClient:
    """LLM client with intelligent routing and cost tracking.

    Wraps LLMClient with:
    - NadirClaw model routing (40-70% cost savings)
    - Token tracking and analytics
    - Context optimization (30-70% input token reduction)
    - Cost estimation per request

    Example:
        >>> client = SmartLLMClient(config)
        >>> response = await client.complete(messages)
        >>> print(f"Saved {response.tokens_saved} tokens")
    """

    def __init__(
        self,
        config: LLMConfig,
        nadirclaw_config: Any | None = None,
        tracking_config: Any | None = None,
        project_path: str | None = None,
    ):
        """Initialize smart LLM client.

        Args:
            config: Base LLM configuration
            nadirclaw_config: NadirClaw configuration (optional)
            tracking_config: Token tracking configuration (optional)
            project_path: Project path for tracking (optional)
        """
        self.base_config = config
        self._base_client = LLMClient(config)

        # Initialize NadirClaw router if enabled
        if nadirclaw_config and nadirclaw_config.enabled:
            self._router = NadirClawRouter(
                simple_model=nadirclaw_config.simple_model,
                mid_model=nadirclaw_config.mid_model,
                complex_model=nadirclaw_config.complex_model,
                tier_thresholds=nadirclaw_config.tier_thresholds,
                cache_enabled=nadirclaw_config.cache_enabled,
                cache_ttl=nadirclaw_config.cache_ttl,
                cache_max_size=nadirclaw_config.cache_max_size,
                context_optimize_mode=nadirclaw_config.context_optimize_mode,
            )
            self._nadirclaw_enabled = True
        else:
            self._router = None
            self._nadirclaw_enabled = False

        # Initialize token tracker if enabled
        if tracking_config and tracking_config.enabled:
            from pathlib import Path

            self._tracker = TokenTracker(
                project_path=Path(project_path) if project_path else None,
                db_path=Path(tracking_config.db_path) if tracking_config.db_path else None,
            )
            self._tracking_enabled = True
        else:
            self._tracker = None
            self._tracking_enabled = False

        # Cost rates (USD per 1M tokens)
        self._cost_rates = {
            "input": 0.000005,  # Default GPT-4 rate
            "output": 0.000015,
        }

        logger.info(
            f"SmartLLMClient initialized: "
            f"NadirClaw={self._nadirclaw_enabled}, "
            f"Tracking={self._tracking_enabled}"
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs,
    ) -> SmartLLMResponse:
        """Complete a chat conversation with intelligent routing.

        Args:
            messages: List of message dicts
            max_tokens: Max completion tokens
            temperature: Sampling temperature
            **kwargs: Additional args for LLMClient

        Returns:
            SmartLLMResponse with routing and cost info
        """
        start_time = time.time()

        # Extract prompt for classification
        prompt = self._extract_prompt(messages)

        # Select optimal model via NadirClaw
        if self._nadirclaw_enabled and self._router:
            selection = self._router.select_model(prompt)
            model = selection.model
            tier = selection.tier
            confidence = selection.confidence

            logger.info(f"NadirClaw routing: {tier} tier → {model} (confidence={confidence:.2f})")
        else:
            # Use default model
            selection = None
            model = self.base_config.primary_model
            tier = "default"
            confidence = 1.0

        # Optimize context if enabled
        if self._nadirclaw_enabled and self._router:
            opt_result = self._router.optimize_context(messages)
            optimized_messages = opt_result.messages
            original_tokens = opt_result.original_tokens
            optimized_tokens = opt_result.optimized_tokens
            tokens_saved = opt_result.tokens_saved

            if tokens_saved > 0:
                logger.info(
                    f"Context optimization: {original_tokens}→{optimized_tokens} tokens "
                    f"(saved {tokens_saved}, {opt_result.savings_pct:.1f}%)"
                )
        else:
            optimized_messages = messages
            original_tokens = 0
            optimized_tokens = 0
            tokens_saved = 0

        # Execute LLM call
        llm_start = time.time()
        response = await self._base_client.complete(
            messages=optimized_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            model=model,  # Use selected model
            **kwargs,
        )
        llm_duration_ms = int((time.time() - llm_start) * 1000)

        # Track token usage
        if self._tracking_enabled and self._tracker:
            self._tracker.track(
                command="llm_call",
                input_tokens=response.prompt_tokens,
                output_tokens=response.completion_tokens,
                execution_time_ms=llm_duration_ms,
            )

        # Estimate cost
        estimated_cost = self._estimate_cost(
            response.prompt_tokens,
            response.completion_tokens,
        )

        total_latency_ms = int((time.time() - start_time) * 1000)

        result = SmartLLMResponse(
            response=response,
            selected_model=model,
            selected_tier=tier,
            routing_confidence=confidence,
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=tokens_saved,
            estimated_cost=estimated_cost,
            routing_latency_ms=total_latency_ms,
        )

        logger.info(
            f"LLM call complete: {model} ({tier}), "
            f"cost=${estimated_cost:.4f}, "
            f"latency={total_latency_ms}ms"
        )

        return result

    def _extract_prompt(self, messages: list[dict[str, Any]]) -> str:
        """Extract user prompt from messages for classification."""
        # Find last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # Handle multi-part messages
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            return part.get("text", "")
        return ""

    def _estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate API cost.

        Args:
            input_tokens: Input token count
            output_tokens: Output token count

        Returns:
            Estimated cost in USD
        """
        input_cost = input_tokens * self._cost_rates["input"] / 1_000_000
        output_cost = output_tokens * self._cost_rates["output"] / 1_000_000
        return input_cost + output_cost

    def get_tracking_summary(self) -> dict[str, Any] | None:
        """Get token tracking summary.

        Returns:
            Summary dict or None if tracking disabled
        """
        if not self._tracking_enabled or not self._tracker:
            return None

        summary = self._tracker.get_summary()
        costs = self._tracker.estimate_cost(
            input_rate=self._cost_rates["input"],
            output_rate=self._cost_rates["output"],
        )

        return {
            "total_commands": summary.total_commands,
            "total_tokens": summary.total_input_tokens + summary.total_output_tokens,
            "total_cost": costs["total_cost"],
            "avg_cost_per_command": costs["avg_cost_per_command"],
        }

    def clear_cache(self) -> int:
        """Clear NadirClaw cache.

        Returns:
            Number of entries cleared
        """
        if self._nadirclaw_enabled and self._router:
            return self._router.clear_cache()
        return 0

    def close(self) -> None:
        """Close client and release resources."""
        if self._tracking_enabled and self._tracker:
            self._tracker.close()
        logger.info("SmartLLMClient closed")
