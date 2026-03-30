"""Integration tests for cost optimization modules.

Tests the integration between:
- Token Tracker
- NadirClaw Router
- SmartLLMClient
- Mnemo Bridge
- Reasoner Bridge
- SearXNG Client

These tests verify that modules work together correctly.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from berb.utils.token_tracker import TokenTracker, TokenUsage
from berb.llm.nadirclaw_router import NadirClawRouter, ModelSelection
from berb.llm.smart_client import SmartLLMClient, SmartLLMResponse
from berb.mnemo_bridge import MnemoBridge, ContextChunk
from berb.reasoner_bridge import ReasonerBridge, HypothesisCandidate, PerspectiveType
from berb.literature.searxng_client import SearXNGClient, SearXNGConfig, SearXNGResult


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test_tracking.db"


@pytest.fixture
def token_tracker(tmp_db_path: Path) -> TokenTracker:
    """Create token tracker with temporary database."""
    tracker = TokenTracker(
        project_path=tmp_path / "test_project",
        db_path=tmp_db_path,
    )
    yield tracker
    tracker.close()


@pytest.fixture
def nadirclaw_router() -> NadirClawRouter:
    """Create NadirClaw router."""
    return NadirClawRouter(
        simple_model="gemini/gemini-2.5-flash",
        mid_model="openai/gpt-4o-mini",
        complex_model="anthropic/claude-sonnet-4-5-20250929",
        cache_enabled=True,
        cache_ttl=3600,
    )


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client for SmartLLMClient tests."""
    client = MagicMock()
    client.complete = AsyncMock(return_value=MagicMock(
        content="Test response",
        model="test-model",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    ))
    return client


@pytest.fixture
def smart_client(mock_llm_client, token_tracker) -> SmartLLMClient:
    """Create SmartLLMClient with mock dependencies."""
    from berb.llm.client import LLMConfig
    
    config = LLMConfig(
        base_url="https://test.api",
        api_key="test-key",
    )
    
    # Create client with tracking enabled
    client = SmartLLMClient.__new__(SmartLLMClient)
    client._base_client = mock_llm_client
    client.base_config = config
    client._tracker = token_tracker
    client._tracking_enabled = True
    client._nadirclaw_enabled = False
    client._router = None
    client._cost_rates = {"input": 5.0, "output": 15.0}
    
    yield client
    
    client.close()


# ─────────────────────────────────────────────────────────────────────────────
# Token Tracker Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenTrackerIntegration:
    """Integration tests for Token Tracker."""
    
    def test_track_and_retrieve(self, token_tracker: TokenTracker):
        """Test tracking and retrieving token usage."""
        # Track multiple commands
        token_tracker.track(
            command="llm_call",
            input_tokens=1000,
            output_tokens=200,
            execution_time_ms=150,
        )
        token_tracker.track(
            command="literature_search",
            input_tokens=500,
            output_tokens=100,
            execution_time_ms=100,
        )
        
        # Retrieve summary
        summary = token_tracker.get_summary()
        
        assert summary.total_commands == 2
        assert summary.total_input_tokens == 1500
        assert summary.total_output_tokens == 300
        assert summary.total_saved_tokens == 1200
    
    def test_cost_estimation(self, token_tracker: TokenTracker):
        """Test cost estimation from tracked usage."""
        token_tracker.track(
            command="llm_call",
            input_tokens=1_000_000,
            output_tokens=500_000,
        )
        
        costs = token_tracker.estimate_cost(
            input_rate=5.0,
            output_rate=15.0,
        )
        
        assert costs["input_cost"] == 5.0
        assert costs["output_cost"] == 7.5
        assert costs["total_cost"] == 12.5


# ─────────────────────────────────────────────────────────────────────────────
# NadirClaw Router Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNadirClawRouterIntegration:
    """Integration tests for NadirClaw Router."""
    
    def test_model_selection_caching(self, nadirclaw_router: NadirClawRouter):
        """Test that model selection is cached."""
        prompt = "What is 2+2?"
        
        # First call
        selection1 = nadirclaw_router.select_model(prompt)
        
        # Second call (should be cached)
        selection2 = nadirclaw_router.select_model(prompt)
        
        assert selection1.model == selection2.model
        assert nadirclaw_router._cache_enabled
    
    def test_context_optimization_pipeline(self, nadirclaw_router: NadirClawRouter):
        """Test context optimization pipeline."""
        messages = [
            {"role": "system", "content": "You are helpful" * 100},
            {"role": "user", "content": "Hello"},
        ]
        
        result = nadirclaw_router.optimize_context(messages, mode="safe")
        
        assert result.original_tokens > 0
        assert result.optimized_tokens <= result.original_tokens
        assert result.tokens_saved >= 0
    
    def test_router_with_tracking(self, nadirclaw_router: NadirClawRouter, token_tracker: TokenTracker):
        """Test router integrated with token tracking."""
        # Select model
        selection = nadirclaw_router.select_model("Test prompt")
        
        # Track usage
        token_tracker.track(
            command=f"llm_{selection.tier}",
            input_tokens=100,
            output_tokens=50,
        )
        
        # Verify tracking
        summary = token_tracker.get_summary()
        assert summary.total_commands == 1


# ─────────────────────────────────────────────────────────────────────────────
# SmartLLMClient Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSmartLLMClientIntegration:
    """Integration tests for SmartLLMClient."""
    
    @pytest.mark.asyncio
    async def test_complete_with_tracking(self, smart_client: SmartLLMClient):
        """Test completion with token tracking."""
        messages = [{"role": "user", "content": "Test"}]
        
        response = await smart_client.complete(messages)
        
        assert isinstance(response, SmartLLMResponse)
        assert response.response.prompt_tokens == 100
        assert response.response.completion_tokens == 50
        
        # Verify tracking
        summary = smart_client.get_tracking_summary()
        assert summary is not None
        assert summary["total_commands"] == 1
    
    @pytest.mark.asyncio
    async def test_cost_estimation(self, smart_client: SmartLLMClient):
        """Test cost estimation in response."""
        messages = [{"role": "user", "content": "Test"}]
        
        response = await smart_client.complete(messages)
        
        # Cost = (100 * 5.0 + 50 * 15.0) / 1_000_000
        expected_cost = (100 * 5.0 + 50 * 15.0) / 1_000_000
        assert response.estimated_cost == expected_cost
    
    @pytest.mark.asyncio
    async def test_cache_clearing(self, smart_client: SmartLLMClient):
        """Test cache clearing."""
        cleared = smart_client.clear_cache()
        assert cleared == 0  # No cache entries yet


# ─────────────────────────────────────────────────────────────────────────────
# Mnemo Bridge Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMnemoBridgeIntegration:
    """Integration tests for Mnemo Bridge."""
    
    @pytest.mark.asyncio
    async def test_context_formatting(self):
        """Test context formatting for prompts."""
        chunks = [
            ContextChunk(
                content="Test content 1",
                source="session",
                relevance=0.9,
                cache_tier="L2",
            ),
            ContextChunk(
                content="Test content 2",
                source="knowledge",
                relevance=0.7,
                cache_tier="L1",
            ),
        ]
        
        formatted = MnemoBridge.format_context_for_prompt(chunks, "Test Context")
        
        assert "Test Context" in formatted
        assert "Test content 1" in formatted
        assert "Test content 2" in formatted
        assert "0.90" in formatted
        assert "0.70" in formatted
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check failure handling."""
        bridge = MnemoBridge(server_url="http://invalid-url")
        
        result = await bridge.health_check()
        
        assert result["status"] == "unhealthy"
        await bridge.close()


# ─────────────────────────────────────────────────────────────────────────────
# Reasoner Bridge Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReasonerBridgeIntegration:
    """Integration tests for Reasoner Bridge."""
    
    @pytest.mark.asyncio
    async def test_hypothesis_generation_flow(self):
        """Test hypothesis generation flow."""
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=MagicMock(
            content='{"hypothesis": "Test hypothesis", "key_insights": ["insight1"], "confidence": 0.8}',
            model="test-model",
        ))
        
        bridge = ReasonerBridge(mock_llm)
        
        hypotheses = await bridge.generate_hypotheses("Test research gap")
        
        # Should generate 4 hypotheses (one per perspective)
        assert len(hypotheses) == 4
    
    @pytest.mark.asyncio
    async def test_stress_test_flow(self):
        """Test stress testing flow."""
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=MagicMock(
            content='{"survival_rate": 0.8, "failure_mode": "None", "recovery_path": "N/A", "severity": "low"}',
            model="test-model",
        ))
        
        bridge = ReasonerBridge(mock_llm)
        
        experiment_design = {"method": "test", "samples": 100}
        results = await bridge.stress_test(experiment_design, "Test hypothesis")
        
        # Should run 3 scenarios
        assert len(results) == 3
    
    @pytest.mark.asyncio
    async def test_context_vetting_flow(self):
        """Test context vetting flow."""
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=MagicMock(
            content='{"cot_leakage": false, "severity": "low"}',
            model="test-model",
        ))
        
        bridge = ReasonerBridge(mock_llm)
        
        result = await bridge.vet_context("Test abstract", "Test topic")
        
        assert "severity" in result


# ─────────────────────────────────────────────────────────────────────────────
# SearXNG Client Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSearXNGClientIntegration:
    """Integration tests for SearXNG Client."""
    
    @pytest.mark.asyncio
    async def test_result_parsing(self):
        """Test result parsing from SearXNG response."""
        config = SearXNGConfig(base_url="http://test")
        client = SearXNGClient(config)
        
        mock_data = {
            "results": [
                {
                    "title": "Test Paper",
                    "url": "https://example.com/paper",
                    "content": "J Smith, A Johnson - Journal, 2023",
                    "engine": "google scholar",
                    "score": 0.9,
                }
            ]
        }
        
        results = client._parse_results(mock_data)
        
        assert len(results) == 1
        assert results[0].title == "Test Paper"
        assert results[0].engine == "google scholar"
        assert len(results[0].authors) == 2
    
    @pytest.mark.asyncio
    async def test_doi_deduplication(self):
        """Test DOI-based deduplication."""
        config = SearXNGConfig(base_url="http://test")
        client = SearXNGClient(config)
        
        results = [
            SearXNGResult(
                title="Paper 1",
                url="https://example.com/1",
                content="",
                engine="engine1",
                score=0.8,
                doi="10.1234/test",
            ),
            SearXNGResult(
                title="Paper 1 (duplicate)",
                url="https://example.com/2",
                content="",
                engine="engine2",
                score=0.9,  # Higher score
                doi="10.1234/test",  # Same DOI
            ),
        ]
        
        deduplicated = client._deduplicate_by_doi(results)
        
        # Should keep only one (higher score)
        assert len(deduplicated) == 1
        assert deduplicated[0].score == 0.9
    
    @pytest.mark.asyncio
    async def test_cache_flow(self):
        """Test caching flow."""
        config = SearXNGConfig(base_url="http://test", cache_enabled=True, cache_ttl=3600)
        client = SearXNGClient(config)
        
        # Set cache
        results = [SearXNGResult("Title", "URL", "Content", "engine", 0.9)]
        cache_key = client._get_cache_key("query", None, None, 1)
        client._cache_set(cache_key, results)
        
        # Get cache
        cached = client._cache_get(cache_key)
        
        assert cached is not None
        assert len(cached) == 1
        
        # Clear cache
        cleared = client.clear_cache()
        assert cleared == 1


# ─────────────────────────────────────────────────────────────────────────────
# Cross-Module Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossModuleIntegration:
    """Integration tests across multiple modules."""
    
    @pytest.mark.asyncio
    async def test_full_cost_optimization_pipeline(self, tmp_path: Path):
        """Test full cost optimization pipeline."""
        # Create tracker
        tracker = TokenTracker(
            project_path=tmp_path / "test",
            db_path=tmp_path / "tracking.db",
        )
        
        # Create router
        router = NadirClawRouter(
            simple_model="gemini/gemini-2.5-flash",
            cache_enabled=True,
        )
        
        # Simulate workflow with padded whitespace so optimization saves tokens
        prompt = "What is machine learning?"

        # 1. Select model
        selection = router.select_model(prompt)

        # 2. Optimize context — extra spaces get compacted, saving tokens
        padded_prompt = "What   is   machine   learning?   " + "   " * 20
        messages = [{"role": "user", "content": padded_prompt}]
        opt_result = router.optimize_context(messages)

        # 3. Track usage: record original→optimized tokens to capture savings
        tracker.track(
            command=f"llm_{selection.tier}",
            input_tokens=opt_result.original_tokens,
            output_tokens=opt_result.optimized_tokens,
        )

        # 4. Get summary
        summary = tracker.get_summary()

        assert summary.total_commands == 1
        assert summary.total_saved_tokens > 0
        
        tracker.close()
    
    @pytest.mark.asyncio
    async def test_multi_bridge_coordination(self):
        """Test coordination between multiple bridges."""
        # Create mock LLM client
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=MagicMock(
            content='{"hypothesis": "Test", "key_insights": [], "confidence": 0.5}',
            model="test",
        ))
        
        # Create bridges
        reasoner = ReasonerBridge(mock_llm)
        
        # Generate hypotheses
        hypotheses = await reasoner.generate_hypotheses("Test gap")
        
        # Vet context
        vet_result = await reasoner.vet_context("Abstract", "Topic")
        
        # Verify both operations completed
        assert len(hypotheses) > 0
        assert "severity" in vet_result
