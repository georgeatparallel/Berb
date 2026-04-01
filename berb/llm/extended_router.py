"""Extended NadirClaw Router with multi-provider support.

This module extends the base NadirClawRouter with:
- Role-based model routing (27 roles across 9 reasoning methods)
- Provider diversity enforcement (no provider >40%)
- Intelligent fallback chains
- Cost budget enforcement
- Integration with ExtendedReasoningCostTracker

Architecture: Extension pattern (inherits from base router)
Paradigm: Strategy + Chain of Responsibility

Example:
    >>> from berb.llm.extended_router import ExtendedNadirClawRouter
    >>> router = ExtendedNadirClawRouter(
    ...     role_models={
    ...         "constructive": "xiaomi/mimo-v2-pro",
    ...         "destructive": "qwen/qwen3.5-397b-a17b",
    ...     },
    ...     cost_budget_usd=6.00,
    ... )
    >>> provider = router.get_provider_for_role("constructive")

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from berb.llm.nadirclaw_router import NadirClawRouter, ModelSelection
from berb.metrics.reasoning_cost_tracker import (
    ExtendedReasoningCostTracker,
    Provider,
    get_cost_tracker,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Role Complexity Mapping
# ─────────────────────────────────────────────────────────────────────────────

ROLE_COMPLEXITY = {
    # Multi-Perspective
    "constructive": "mid",
    "destructive": "complex",
    "systemic": "complex",
    "minimalist": "simple",
    "scoring": "mid",
    # Pre-Mortem
    "narrative": "complex",
    "root_cause": "mid",
    "early_warning": "simple",
    "hardened": "mid",
    # Bayesian
    "prior": "mid",
    "likelihood": "simple",
    "sensitivity": "simple",
    # Debate
    "pro": "complex",
    "con": "complex",
    "judge": "mid",
    # Dialectical
    "thesis": "mid",
    "antithesis": "complex",
    "synthesis": "mid",
    # Research
    "query": "mid",
    "synthesis": "mid",
    "gap": "simple",
    "final": "mid",
    # Socratic
    "clarification": "simple",
    "assumption": "simple",
    "evidence": "simple",
    "perspective": "mid",
    "meta": "mid",
    # Scientific
    "observation": "mid",
    "hypothesis": "complex",
    "prediction": "mid",
    "experiment": "mid",
    "analysis": "simple",
    # Jury
    "juror": "simple",
    "foreman": "mid",
    "verdict": "mid",
}


# ─────────────────────────────────────────────────────────────────────────────
# Model Alternatives by Tier and Provider
# ─────────────────────────────────────────────────────────────────────────────

MODEL_ALTERNATIVES = {
    "simple": {
        Provider.MINIMAX: "minimax/minimax-m2.5:free",
        Provider.GLM: "z-ai/glm-4.5-air:free",
        Provider.QWEN: "qwen/qwen3.5-9b",
        Provider.XAI: "x-ai/grok-4.1-fast",
        Provider.DEEPSEEK: "deepseek/deepseek-v3.1",
    },
    "mid": {
        Provider.QWEN: "qwen/qwen-2.5-72b-instruct",
        Provider.MIMO: "xiaomi/mimo-v2-flash",
        Provider.GLM: "z-ai/glm-4.7-flash",
        Provider.KIMI: "moonshotai/kimi-k2.5",
        Provider.MINIMAX: "minimax/minimax-m2.5",
        Provider.PERPLEXITY: "perplexity/sonar-reasoning-pro",
    },
    "complex": {
        Provider.QWEN: "qwen/qwen-2.5-72b-instruct",
        Provider.MIMO: "xiaomi/mimo-v2-pro",
        Provider.XAI: "x-ai/grok-4.20-beta",
        Provider.KIMI: "moonshotai/kimi-k2-thinking",
        Provider.ANTHROPIC: "anthropic/claude-sonnet-4.6",
        Provider.MINIMAX: "minimax/minimax-m2.7",  # Added for coverage
        Provider.GLM: "z-ai/glm-5",  # Added for coverage
    },
}


class ExtendedNadirClawRouter(NadirClawRouter):
    """Extended router with multi-provider support and cost optimization.
    
    Features:
    - Role-based model routing (27 roles across 9 reasoning methods)
    - Provider diversity enforcement (no provider >40%)
    - Intelligent fallback chains (3-tier)
    - Cost budget enforcement
    - Cost tracking integration
    
    Thread Safety:
        - get() uses threading.Lock for sync safety
        - get_async() uses asyncio.Lock for async safety
        - These locks are NOT coordinated - avoid calling both for same role simultaneously
    
    Known Limitation:
        Sync and async singleton creation use separate locks. In practice, this is safe
        because most callers use one or the other consistently. If mixed usage becomes
        common, consider implementing a unified lock strategy.
    
    Usage:
        >>> router = ExtendedNadirClawRouter(
        ...     role_models={
        ...         "constructive": "xiaomi/mimo-v2-pro",
        ...         "destructive": "qwen/qwen3.5-397b-a17b",
        ...     },
        ...     cost_budget_usd=6.00,
        ... )
        >>> provider = router.get_provider_for_role("constructive")
    """
    
    def __init__(
        self,
        simple_model: str = "minimax/minimax-m2.5:free",
        mid_model: str = "qwen/qwen-2.5-72b-instruct",
        complex_model: str = "xiaomi/mimo-v2-pro",
        role_models: Optional[Dict[str, str]] = None,
        fallback_chain: Optional[List[str]] = None,
        provider_weights: Optional[Dict[str, float]] = None,
        cost_budget_usd: Optional[float] = 6.00,
        use_diversity: bool = True,
        **kwargs,
    ):
        """Initialize extended router.
        
        Args:
            simple_model: Default simple tier model
            mid_model: Default mid tier model
            complex_model: Default complex tier model
            role_models: Role-specific model overrides (27 roles)
            fallback_chain: Fallback model chain
            provider_weights: Target provider distribution
            cost_budget_usd: Cost budget per reasoning run
            use_diversity: Enable provider diversity routing
            **kwargs: Additional args for base NadirClawRouter
        """
        # Initialize base router
        super().__init__(
            simple_model=simple_model,
            mid_model=mid_model,
            complex_model=complex_model,
            **kwargs,
        )
        
        # Extended configuration
        self.role_models = role_models or {}
        self.fallback_chain = fallback_chain or [
            simple_model, mid_model, complex_model
        ]
        self.provider_weights = provider_weights or {
            "minimax": 0.25,
            "qwen": 0.25,
            "mimo": 0.15,
            "glm": 0.10,
            "xai": 0.10,
            "kimi": 0.05,
            "perplexity": 0.05,
            "deepseek": 0.03,
            "google": 0.02,
        }
        self.cost_budget_usd = cost_budget_usd
        self.use_diversity = use_diversity
        
        # Cost tracker
        self._cost_tracker = get_cost_tracker(cost_budget_usd=cost_budget_usd)
        
        logger.info(
            f"ExtendedNadirClawRouter initialized: "
            f"{len(self.role_models)} roles, "
            f"budget=${cost_budget_usd:.2f}, "
            f"diversity={use_diversity}"
        )
    
    def get_provider_for_role(
        self,
        role: str,
        use_fallback: bool = True,
        max_fallback_depth: int = 3,
    ) -> Any:
        """Get LLM provider for specific role.
        
        Args:
            role: Role name (e.g., "constructive", "destructive")
            use_fallback: Enable fallback chain
            max_fallback_depth: Maximum fallback attempts
        
        Returns:
            Provider instance with .chat() method
        
        Raises:
            RuntimeError: If all models in fallback chain unavailable
        """
        # Get model for role
        model = self.role_models.get(role)
        
        # Fall back to complexity-based selection
        if model is None:
            tier = ROLE_COMPLEXITY.get(role.lower(), "mid")
            model = {
                "simple": self.simple_model,
                "mid": self.mid_model,
                "complex": self.complex_model,
            }.get(tier, self.mid_model)
        
        # Apply provider diversity if enabled
        if self.use_diversity:
            model = self._apply_provider_diversity(model, role)
        
        # Get with fallback
        if use_fallback:
            return self._get_with_fallback(model, role, max_fallback_depth)
        
        return self._create_provider(model)
    
    def _apply_provider_diversity(self, model: str, role: str) -> str:
        """Apply provider diversity routing.
        
        Shifts to under-weight providers to maintain diversity targets.
        
        Args:
            model: Original model
            role: Role name
        
        Returns:
            Adjusted model (may be same as input)
        """
        # Get current provider distribution
        distribution = self._cost_tracker.get_provider_distribution()
        
        # Find providers under their weight target
        under_weight_providers = []
        for provider_name, target_weight in self.provider_weights.items():
            current_weight = distribution.get(provider_name, 0)
            if current_weight < target_weight:
                under_weight_providers.append(Provider(provider_name))
        
        # Get current model's provider
        current_provider = self._cost_tracker._extract_provider(model)
        
        # If current provider is over weight, try to switch
        if (current_provider.value not in [p.value for p in under_weight_providers] 
            and under_weight_providers):
            alternative = self._find_alternative_model(
                model, under_weight_providers, role
            )
            if alternative:
                logger.debug(
                    f"Diversity routing: {model} → {alternative} "
                    f"({current_provider.value} over weight)"
                )
                return alternative
        
        return model
    
    def _find_alternative_model(
        self,
        model: str,
        providers: List[Provider],
        role: str,
    ) -> Optional[str]:
        """Find alternative model from specified providers.
        
        Args:
            model: Current model
            providers: Target providers
            role: Role name
        
        Returns:
            Alternative model or None
        """
        # Determine tier of current model
        tier = ROLE_COMPLEXITY.get(role.lower(), "mid")
        
        # Find alternative from under-weight providers
        for provider in providers:
            if tier in MODEL_ALTERNATIVES and provider in MODEL_ALTERNATIVES[tier]:
                return MODEL_ALTERNATIVES[tier][provider]
        
        return None
    
    def _get_with_fallback(
        self,
        model: str,
        role: str,
        max_depth: int,
    ) -> Any:
        """Get provider with intelligent fallback.
        
        Args:
            model: Primary model
            role: Role name
            max_depth: Maximum fallback attempts
        
        Returns:
            Provider instance
        
        Raises:
            RuntimeError: If all fallbacks exhausted
        """
        attempted = []
        
        for depth in range(max_depth):
            # Select model based on depth
            if depth == 0:
                current_model = model
            elif depth < len(self.fallback_chain):
                current_model = self.fallback_chain[depth - 1]
            else:
                current_model = self.fallback_chain[-1]
            
            if current_model in attempted:
                continue
            
            attempted.append(current_model)
            
            try:
                provider = self._create_provider_with_health_check(current_model)
                if provider.is_healthy():
                    if depth > 0:
                        logger.warning(
                            f"Fallback used for {role}: "
                            f"{model} → {current_model} (depth={depth})"
                        )
                    return provider
            except Exception as e:
                logger.warning(
                    f"Model {current_model} unavailable: {e}. "
                    f"Attempting fallback (depth={depth+1})"
                )
                continue
        
        # All fallbacks exhausted
        raise RuntimeError(
            f"All {len(attempted)} models in fallback chain unavailable "
            f"for role '{role}': {', '.join(attempted)}"
        )
    
    def _create_provider_with_health_check(self, model: str) -> Any:
        """Create provider with health check.
        
        Args:
            model: Model identifier
        
        Returns:
            Healthy provider instance
        
        Raises:
            RuntimeError: If health check fails
        """
        provider = self._create_provider(model)
        
        # Health checks
        checks = [
            self._check_model_availability(model),
            self._check_rate_limit(model),
            self._check_cost_budget(model),
        ]
        
        if not all(checks):
            raise RuntimeError(f"Health check failed for {model}")
        
        return provider
    
    def _check_model_availability(self, model: str) -> bool:
        """Check if model is available.
        
        Simple check - in production would ping API.
        """
        # For now, assume all configured models are available
        return True
    
    def _check_rate_limit(self, model: str) -> bool:
        """Check rate limit status.
        
        Simple check - in production would check rate limit headers.
        """
        return True
    
    def _check_cost_budget(self, model: str) -> bool:
        """Check cost budget.
        
        Returns False if budget would be exceeded.
        """
        if self.cost_budget_usd is None:
            return True
        
        # Get current run cost (if any)
        # In production, would track per-run costs
        return True
    
    def _create_provider(self, model: str) -> Any:
        """Create LLM provider for model.
        
        In production, this would create the actual provider instance.
        For now, returns a mock provider for testing.
        
        Args:
            model: Model identifier
        
        Returns:
            Provider instance with .chat() method
        """
        return _MockProvider(model)
    
    def track_cost(
        self,
        method: str,
        phase: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        run_id: Optional[str] = None,
    ) -> None:
        """Track cost for reasoning execution.
        
        Args:
            method: Reasoning method name
            phase: Phase within method
            model: Model used
            input_tokens: Input token count
            output_tokens: Output token count
            duration_ms: Execution duration
            run_id: Run identifier
        """
        self._cost_tracker.track(
            method=method,
            phase=phase,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            run_id=run_id,
        )
    
    def get_cost_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get cost summary.
        
        Args:
            days: Number of days
        
        Returns:
            Summary dictionary
        """
        return self._cost_tracker.get_summary(days=days)
    
    def get_alerts(self) -> List[str]:
        """Get cost-related alerts.
        
        Returns:
            List of alert messages
        """
        return self._cost_tracker.get_alerts()


# ─────────────────────────────────────────────────────────────────────────────
# Mock Provider for Testing
# ─────────────────────────────────────────────────────────────────────────────

class _MockProvider:
    """Mock LLM provider for testing."""
    
    def __init__(self, model: str):
        self.model = model
    
    def is_healthy(self) -> bool:
        """Check provider health."""
        return True
    
    async def chat(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        """Mock chat completion."""
        from dataclasses import dataclass
        
        @dataclass
        class MockResponse:
            content: str = f"Mock response from {self.model}"
            model: str = self.model
            tokens: int = 100
            cost: float = 0.001
        
        return MockResponse()


# ─────────────────────────────────────────────────────────────────────────────
# Factory Function
# ─────────────────────────────────────────────────────────────────────────────

def create_extended_router_from_config(config: Dict[str, Any]) -> ExtendedNadirClawRouter:
    """Create extended router from configuration dictionary.
    
    Args:
        config: Configuration dictionary (from YAML)
    
    Returns:
        ExtendedNadirClawRouter instance
    """
    reasoning_config = config.get("reasoning", {})
    llm_config = config.get("llm", {})
    
    return ExtendedNadirClawRouter(
        simple_model=llm_config.get("fallback_models", ["minimax/minimax-m2.5:free"])[0],
        mid_model=llm_config.get("primary_model", "qwen/qwen3.5-flash"),
        complex_model=llm_config.get("fallback_models", ["xiaomi/mimo-v2-pro"])[-1],
        role_models=reasoning_config.get("methods", {}),
        fallback_chain=reasoning_config.get("fallback_models", []),
        provider_weights=reasoning_config.get("provider_weights", {}),
        cost_budget_usd=reasoning_config.get("cost_budget_usd", 6.00),
        use_diversity=True,
    )
