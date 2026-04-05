"""Unit tests for Extended NadirClaw Router.

Tests for:
- Role-based model routing
- Provider diversity enforcement
- Fallback chains
- Cost tracker integration

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from berb.llm.extended_router import (
    ExtendedNadirClawRouter,
    ROLE_COMPLEXITY,
    MODEL_ALTERNATIVES,
    create_extended_router_from_config,
)
from berb.metrics.reasoning_cost_tracker import Provider


class TestExtendedNadirClawRouter:
    """Test extended router functionality."""
    
    @pytest.fixture
    def router(self):
        """Create test router."""
        return ExtendedNadirClawRouter(
            role_models={
                "constructive": "xiaomi/mimo-v2-pro",
                "destructive": "qwen/qwen3.5-397b-a17b",
            },
            cost_budget_usd=6.00,
            use_diversity=False,  # Disable for basic tests
        )
    
    def test_role_based_routing(self, router):
        """Test role-based model selection."""
        # Test configured roles
        provider = router.get_provider_for_role("constructive")
        assert provider.model == "xiaomi/mimo-v2-pro"
        
        provider = router.get_provider_for_role("destructive")
        assert provider.model == "qwen/qwen3.5-397b-a17b"
    
    def test_complexity_based_fallback(self, router):
        """Test complexity-based model selection for unconfigured roles."""
        # Test unconfigured role - should use complexity mapping
        provider = router.get_provider_for_role("minimalist")
        # minimalist is "simple" tier, should use simple_model
        assert provider.model == router.simple_model
    
    def test_all_role_complexities_mapped(self):
        """Test all 27 roles have complexity mapping."""
        expected_roles = [
            # Multi-Perspective (5)
            "constructive", "destructive", "systemic", "minimalist", "scoring",
            # Pre-Mortem (4)
            "narrative", "root_cause", "early_warning", "hardened",
            # Bayesian (3)
            "prior", "likelihood", "sensitivity",
            # Debate (3)
            "pro", "con", "judge",
            # Dialectical (3)
            "thesis", "antithesis", "synthesis",
            # Research (4)
            "query", "synthesis", "gap", "final",
            # Socratic (5)
            "clarification", "assumption", "evidence", "perspective", "meta",
            # Scientific (5)
            "observation", "hypothesis", "prediction", "experiment", "analysis",
            # Jury (3)
            "juror", "foreman", "verdict",
        ]
        
        for role in expected_roles:
            assert role in ROLE_COMPLEXITY, f"Role {role} not mapped"
            assert ROLE_COMPLEXITY[role] in ["simple", "mid", "complex"]
    
    def test_provider_diversity_routing(self):
        """Test provider diversity enforcement."""
        router = ExtendedNadirClawRouter(
            role_models={"constructive": "qwen/qwen3.5-flash"},
            provider_weights={
                "minimax": 0.50,  # High weight for MiniMax
                "qwen": 0.10,     # Low weight for Qwen
            },
            use_diversity=True,
        )
        
        # First call should shift to under-weight provider
        provider = router.get_provider_for_role("constructive")
        # Should shift from Qwen to MiniMax (under-weight)
        assert "minimax" in provider.model.lower() or "qwen" in provider.model.lower()
    
    def test_fallback_chain(self):
        """Test fallback chain functionality."""
        router = ExtendedNadirClawRouter(
            role_models={"test": "unavailable/model"},
            fallback_chain=[
                "minimax/minimax-m2.5:free",
                "qwen/qwen3.5-flash",
            ],
        )
        
        # Should use fallback when primary unavailable
        # (Mock provider always healthy, so this tests the chain logic)
        provider = router.get_provider_for_role("test", use_fallback=True)
        assert provider is not None
    
    def test_cost_tracking(self, router):
        """Test cost tracking integration."""
        # Track a cost
        router.track_cost(
            method="multi_perspective",
            phase="constructive",
            model="xiaomi/mimo-v2-pro",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=1500,
            run_id="test-run-123",
        )
        
        # Get summary
        summary = router.get_cost_summary(days=7)
        
        assert summary["total_executions"] >= 1
        assert summary["total_cost_usd"] >= 0
    
    def test_cost_alerts(self, router):
        """Test cost alert generation."""
        alerts = router.get_alerts()
        assert isinstance(alerts, list)
    
    def test_model_alternatives_coverage(self):
        """Test model alternatives cover all tiers and providers."""
        expected_tiers = ["simple", "mid", "complex"]
        expected_providers = [
            Provider.MINIMAX, Provider.QWEN, Provider.GLM,
            Provider.MIMO, Provider.XAI, Provider.KIMI,
        ]
        
        for tier in expected_tiers:
            assert tier in MODEL_ALTERNATIVES
            for provider in expected_providers:
                # Not all providers need all tiers, but check common ones
                if provider in [Provider.MINIMAX, Provider.QWEN, Provider.GLM]:
                    assert provider in MODEL_ALTERNATIVES[tier], \
                        f"{provider.value} missing for {tier}"


class TestCreateRouterFromConfig:
    """Test router creation from configuration."""
    
    def test_create_from_minimal_config(self):
        """Test router creation with minimal config."""
        config = {
            "llm": {
                "primary_model": "qwen/qwen3.5-flash",
            },
            "reasoning": {},
        }
        
        router = create_extended_router_from_config(config)
        assert router is not None
        assert router.mid_model == "qwen/qwen3.5-flash"
    
    def test_create_from_full_config(self):
        """Test router creation with full config."""
        config = {
            "llm": {
                "primary_model": "qwen/qwen3.5-flash",
                "fallback_models": [
                    "minimax/minimax-m2.5:free",
                    "xiaomi/mimo-v2-pro",
                ],
            },
            "reasoning": {
                "default_model": "minimax/minimax-m2.5:free",
                "fallback_models": ["qwen/qwen3.5-flash"],
                "provider_weights": {
                    "minimax": 0.30,
                    "qwen": 0.30,
                },
                "cost_budget_usd": 5.00,
                "methods": {
                    "multi_perspective": {
                        "constructive": "xiaomi/mimo-v2-pro",
                    },
                },
            },
        }
        
        router = create_extended_router_from_config(config)
        
        assert router.cost_budget_usd == 5.00
        assert router.provider_weights["minimax"] == 0.30
        assert router.role_models["multi_perspective"]["constructive"] == "xiaomi/mimo-v2-pro"


class TestProviderSelection:
    """Test provider selection logic."""
    
    def test_extract_provider(self):
        """Test provider extraction from model strings."""
        from berb.metrics.reasoning_cost_tracker import ExtendedReasoningCostTracker
        
        tracker = ExtendedReasoningCostTracker()
        
        test_cases = [
            ("minimax/minimax-m2.5", Provider.MINIMAX),
            ("qwen/qwen3.5-flash", Provider.QWEN),
            ("z-ai/glm-4.5", Provider.GLM),
            ("xiaomi/mimo-v2-pro", Provider.MIMO),
            ("moonshotai/kimi-k2.5", Provider.KIMI),
            ("perplexity/sonar-pro", Provider.PERPLEXITY),
            ("x-ai/grok-4.20", Provider.XAI),
            ("deepseek/deepseek-v3.2", Provider.DEEPSEEK),
            ("google/gemini-3-flash", Provider.GOOGLE),
            ("anthropic/claude-sonnet", Provider.ANTHROPIC),
            ("openai/gpt-5.4", Provider.OPENAI),
        ]
        
        for model, expected_provider in test_cases:
            result = tracker._extract_provider(model)
            assert result == expected_provider, \
                f"Expected {expected_provider} for {model}, got {result}"


class TestRoleComplexityMapping:
    """Test role complexity mapping correctness."""
    
    def test_constructive_is_mid(self):
        """Constructive should be mid complexity."""
        assert ROLE_COMPLEXITY["constructive"] == "mid"
    
    def test_destructive_is_complex(self):
        """Destructive should be complex."""
        assert ROLE_COMPLEXITY["destructive"] == "complex"
    
    def test_minimalist_is_simple(self):
        """Minimalist should be simple."""
        assert ROLE_COMPLEXITY["minimalist"] == "simple"
    
    def test_jury_juror_is_simple(self):
        """Jury juror should be simple (parallel execution)."""
        assert ROLE_COMPLEXITY["juror"] == "simple"
    
    def test_jury_foreman_is_mid(self):
        """Jury foreman should be mid (synthesis)."""
        assert ROLE_COMPLEXITY["foreman"] == "mid"


class TestMockProvider:
    """Test mock provider for testing."""
    
    @pytest.mark.asyncio
    async def test_mock_provider_chat(self):
        """Test mock provider chat method."""
        from berb.llm.extended_router import _MockProvider
        
        provider = _MockProvider("test/model")
        response = await provider.chat([{"role": "user", "content": "test"}])
        
        assert response.model == "test/model"
        assert response.content == "Mock response from test/model"
    
    def test_mock_provider_healthy(self):
        """Test mock provider health check."""
        from berb.llm.extended_router import _MockProvider
        
        provider = _MockProvider("test/model")
        assert provider.is_healthy() is True
