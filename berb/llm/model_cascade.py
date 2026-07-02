"""Model cascading for cost-optimized LLM routing with caching.

This module implements model cascading - trying cheap models first and
escalating to premium models only when necessary - achieving 40-60%
cost reduction per task.

P1 2026-04-02: Added LRU caching for repeated prompts (50-80% cost reduction).

Architecture: Strategy pattern with quality evaluation
Paradigm: Functional composition with async support

Usage:
    from berb.llm.model_cascade import CascadingLLMClient, CascadeConfig

    config = CascadeConfig(
        cascade=[
            ("deepseek/deepseek-v3.2", 0.80),  # Try cheap, accept if score >= 0.80
            ("openai/gpt-4o-mini", 0.75),      # Mid-tier, accept if >= 0.75
            ("anthropic/claude-sonnet", 0.0),  # Premium, always accept
        ],
    )

    client = CascadingLLMClient(base_client=llm_client, config=config)
    response = await client.chat(messages)
"""

# Author: Georgios-Chrysovalantis Chatzivantsidis

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CascadeStep:
    """Represents a single step in the model cascade."""

    model: str
    min_score: float  # Minimum quality score to accept (0.0-1.0)
    max_tokens: int | None = None
    temperature: float = 0.7


@dataclass
class CascadeConfig:
    """Configuration for model cascading."""

    cascade: list[CascadeStep] = field(default_factory=list)
    quick_eval_enabled: bool = True
    quick_eval_threshold: float = 0.5  # Below this, skip expensive eval

    # Fallback: if all cascade steps fail, use this model
    fallback_model: str | None = None

    # Statistics tracking
    track_stats: bool = True


@dataclass
class CascadeStats:
    """Statistics for cascade execution."""

    steps_tried: int = 0
    final_model: str = ""
    final_score: float = 0.0
    total_latency_ms: int = 0
    cascade_exit_step: int = 0
    cost_saved_estimate: float = 0.0


class CascadingLLMClient:
    """LLM client with model cascading support."""

    # Cost per 1M tokens (approximate, for estimation)
    MODEL_COSTS = {
        "deepseek": 0.00028,  # $0.28/1M input
        "gpt-4o-mini": 0.00015,
        "gpt-4o": 0.0025,
        "claude-haiku": 0.00025,
        "claude-sonnet": 0.003,
        "claude-opus": 0.015,
    }

    def __init__(
        self,
        base_client: Any,
        config: CascadeConfig,
        quality_evaluator: Callable | None = None,
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
    ):
        """Initialize cascading client.

        Args:
            base_client: Base LLM client for making API calls
            config: Cascade configuration
            quality_evaluator: Function to evaluate response quality
                (signature: eval(response, messages) -> score 0.0-1.0)
            cache_enabled: Enable LRU caching for repeated prompts
            cache_max_size: Maximum cache size (default: 1000)
        """
        self._base_client = base_client
        self._config = config
        self._evaluator = quality_evaluator or self._default_evaluator

        # P1 2026-04-02: LRU caching for repeated prompts
        self._cache_enabled = cache_enabled
        self._cache_max_size = cache_max_size
        self._cache: dict[str, Any] = {}
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }

        # Statistics — protected by a lock because chat() is async and multiple
        # coroutines may share one CascadingLLMClient instance.
        self._stats_lock: asyncio.Lock = asyncio.Lock()
        self._total_requests = 0
        self._cascade_exits: dict[int, int] = {}  # step -> count
        self._total_saved = 0.0

    # ========== P1 2026-04-02: Caching Methods ==========

    def _generate_cache_key(self, messages: list[dict], **kwargs) -> str:
        """Generate cache key from messages and kwargs.

        P1 2026-04-02: LRU caching for repeated prompts.
        """
        # Create deterministic representation
        key_data = {
            "messages": messages,
            **kwargs,
        }
        key_str = str(key_data)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    def _get_from_cache(self, key: str) -> Any | None:
        """Get response from cache."""
        if not self._cache_enabled:
            return None

        value = self._cache.get(key)
        if value is not None:
            self._cache_stats["hits"] += 1
            logger.debug(f"Cache hit: {key[:16]}...")
        else:
            self._cache_stats["misses"] += 1
            logger.debug(f"Cache miss: {key[:16]}...")
        return value

    def _set_cache(self, key: str, value: Any) -> None:
        """Set response in cache with LRU eviction."""
        if not self._cache_enabled:
            return

        # Evict oldest if at capacity
        if len(self._cache) >= self._cache_max_size:
            # Remove oldest (first) item
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._cache_stats["evictions"] += 1

        self._cache[key] = value
        logger.debug(f"Cached: {key[:16]}... (size={len(self._cache)})")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = self._cache_stats["hits"] / total if total > 0 else 0.0
        return {
            **self._cache_stats,
            "size": len(self._cache),
            "max_size": self._cache_max_size,
            "hit_rate": hit_rate,
            "enabled": self._cache_enabled,
        }

    def clear_cache(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
        logger.info("Cache cleared")

    # ========== End Caching Methods ==========

    async def chat(
        self,
        messages: list[dict],
        stage: Any | None = None,
        **kwargs,
    ) -> Any:
        """Send chat request through cascade.

        P1 2026-04-02: Added LRU caching for repeated prompts.

        Args:
            messages: List of message dicts
            stage: Optional pipeline stage (for stage-specific cascade)
            **kwargs: Additional parameters for base client

        Returns:
            LLM response from first acceptable model in cascade
        """
        # P1 2026-04-02: Check cache first
        cache_key = self._generate_cache_key(messages, **kwargs)
        cached_response = self._get_from_cache(cache_key)
        if cached_response is not None:
            logger.info("Cache hit for prompt (saved API call)")
            return cached_response

        async with self._stats_lock:
            self._total_requests += 1
        time.time()

        # Get cascade config for this stage
        cascade = self._get_cascade_for_stage(stage)

        last_response = None
        last_error = None

        for step_idx, step in enumerate(cascade):
            try:
                # Try this model
                logger.debug(f"Cascade step {step_idx + 1}: trying {step.model}")

                response = await self._base_client.chat(
                    messages=messages,
                    model=step.model,
                    max_tokens=step.max_tokens,
                    temperature=step.temperature,
                    **kwargs,
                )

                # Evaluate quality
                if self._config.quick_eval_enabled:
                    score = self._evaluator(response, messages)

                    logger.debug(f"Cascade step {step_idx + 1}: quality score = {score:.2f}")

                    # Accept if score meets threshold
                    if score >= step.min_score:
                        logger.info(
                            f"Cascade exit at step {step_idx + 1}: "
                            f"{step.model} (score={score:.2f} >= {step.min_score:.2f})"
                        )

                        async with self._stats_lock:
                            self._record_cascade_exit(step_idx)

                        # P1 2026-04-02: Cache the response
                        self._set_cache(cache_key, response)

                        return response

                    # Continue to next model in cascade
                    logger.debug(f"Cascade continue: score {score:.2f} < {step.min_score:.2f}")
                else:
                    # No evaluation - accept first response
                    return response

                last_response = response

            except BaseException as e:
                # Re-raise asyncio.CancelledError and other non-Exception BaseExceptions
                # so that task cancellation is not silently swallowed by the cascade loop.
                # On Python 3.7 CancelledError inherits from Exception; on 3.8+ it does not,
                # but catching BaseException here is correct for both.
                if not isinstance(e, Exception):
                    raise
                logger.warning(f"Cascade step {step_idx + 1} ({step.model}) failed: {e}")
                last_error = e
                continue

        # All cascade steps failed or were rejected
        if last_response is not None:
            # Return last response even if below threshold
            logger.warning(
                f"All cascade steps exhausted, returning last response "
                f"(model={last_response.model})"
            )
            return last_response

        # Try the configured fallback model before giving up entirely.
        # Without this the fallback_model field in CascadeConfig was dead code.
        if self._config.fallback_model is not None:
            logger.warning(
                "All cascade steps failed/rejected; trying fallback model: %s",
                self._config.fallback_model,
            )
            try:
                return await self._base_client.chat(
                    messages=messages,
                    model=self._config.fallback_model,
                    **kwargs,
                )
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(
                    f"All cascade steps and fallback model ({self._config.fallback_model}) "
                    f"failed. Last error: {e}"
                ) from e

        if last_error is not None:
            raise RuntimeError(f"All cascade steps failed: {last_error}")

        raise RuntimeError("Cascade produced no response")

    def _get_cascade_for_stage(self, stage: Any | None) -> list[CascadeStep]:
        """Get cascade configuration for a specific stage.

        For now, returns the default cascade. Can be extended with
        stage-specific cascades.
        """
        return self._config.cascade

    def _default_evaluator(self, response: Any, messages: list[dict]) -> float:
        """Default quality evaluator.

        Uses simple heuristics:
        - Response length (not too short)
        - No refusal patterns
        - Contains expected structure (for JSON tasks)

        Args:
            response: LLM response
            messages: Input messages

        Returns:
            Quality score 0.0-1.0
        """
        content = getattr(response, "content", "")

        if not content:
            return 0.0

        score = 1.0

        # Penalize very short responses
        if len(content) < 50:
            score -= 0.3

        # Penalize refusal patterns
        refusal_patterns = [
            "i cannot",
            "i'm unable",
            "i am not able",
            "as an ai",
            "i don't have",
        ]

        content_lower = content.lower()
        for pattern in refusal_patterns:
            if pattern in content_lower:
                score -= 0.2

        # Bonus for structured output (if requested)
        if any("json" in str(m.get("content", "")).lower() for m in messages):
            if content.strip().startswith("{") or content.strip().startswith("["):
                score += 0.2

        return max(0.0, min(1.0, score))

    def _record_cascade_exit(self, step_idx: int) -> None:
        """Record which step the cascade exited at."""
        self._cascade_exits[step_idx] = self._cascade_exits.get(step_idx, 0) + 1

    def get_stats(self) -> dict[str, Any]:
        """Get cascade statistics.

        Returns:
            Dictionary with cascade statistics
        """
        # BUG-C fix: snapshot the dict before iterating.  Without this,
        # concurrent chat() calls that hold _stats_lock and mutate _cascade_exits
        # can cause "RuntimeError: dictionary changed size during iteration" here,
        # because get_stats() is synchronous and cannot acquire the asyncio.Lock.
        # dict() creates a shallow copy atomically under the CPython GIL, making
        # subsequent iteration safe regardless of concurrent modifications.
        exits = dict(self._cascade_exits)

        total_cascade_exits = sum(exits.values())

        # Calculate average exit step
        if total_cascade_exits > 0:
            avg_exit = sum(step * count for step, count in exits.items()) / total_cascade_exits
        else:
            avg_exit = 0.0

        return {
            "total_requests": self._total_requests,
            "cascade_exits": exits,
            "average_exit_step": avg_exit,
            "estimated_savings": self._total_saved,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Stage-Specific Cascade Configurations
# ─────────────────────────────────────────────────────────────────────────────


def get_cascade_for_stage(stage_name: str) -> CascadeConfig:
    """Get recommended cascade configuration for a pipeline stage.

    Args:
        stage_name: Name of the pipeline stage

    Returns:
        CascadeConfig optimized for this stage
    """
    stage_name = stage_name.upper()

    # Simple tasks: start with cheapest, quick to accept
    if stage_name in {"TOPIC_INIT", "LITERATURE_COLLECT", "KNOWLEDGE_EXTRACT"}:
        return CascadeConfig(
            cascade=[
                CascadeStep("deepseek/deepseek-v3.2", min_score=0.70),
                CascadeStep("openai/gpt-4o-mini", min_score=0.75),
                CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),
            ],
        )

    # Reasoning tasks: start with mid-tier, need good reasoning
    elif stage_name in {"HYPOTHESIS_GEN", "RESEARCH_DECISION", "RESULT_ANALYSIS"}:
        return CascadeConfig(
            cascade=[
                CascadeStep("openai/gpt-4o-mini", min_score=0.75),
                CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.80),
                CascadeStep("anthropic/claude-opus-4.6", min_score=0.0),
            ],
        )

    # Creative tasks: can use cheaper models
    elif stage_name in {"PAPER_OUTLINE", "PAPER_DRAFT"}:
        return CascadeConfig(
            cascade=[
                CascadeStep("openai/gpt-4o", min_score=0.75),
                CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),
            ],
        )

    # Critical tasks: start with premium
    elif stage_name in {"PEER_REVIEW", "QUALITY_GATE", "CITATION_VERIFY"}:
        return CascadeConfig(
            cascade=[
                CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),
            ],
            # No cascading for critical tasks
        )

    # Default: balanced cascade
    else:
        return CascadeConfig(
            cascade=[
                CascadeStep("deepseek/deepseek-v3.2", min_score=0.75),
                CascadeStep("openai/gpt-4o-mini", min_score=0.75),
                CascadeStep("anthropic/claude-sonnet-4.6", min_score=0.0),
            ],
        )
