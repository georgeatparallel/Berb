"""Integration tests for all 9 reasoning methods with ExtendedNadirClawRouter.

Tests verify:
- Router integration works correctly
- Cost tracking is functional
- Backward compatibility with llm_client
- End-to-end execution with mock providers

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from berb.reasoning.base import ReasoningContext, MethodType
from berb.reasoning.multi_perspective import MultiPerspectiveMethod
from berb.reasoning.pre_mortem import PreMortemMethod
from berb.reasoning.bayesian import BayesianMethod
from berb.reasoning.debate import DebateMethod
from berb.reasoning.dialectical import DialecticalMethod
from berb.reasoning.research import ResearchMethod
from berb.reasoning.socratic import SocraticMethod
from berb.reasoning.scientific import ScientificMethod
from berb.reasoning.jury import JuryMethod
from berb.llm.extended_router import ExtendedNadirClawRouter


# =============================================================================
# Mock Provider for Testing
# =============================================================================

class MockProvider:
    """Mock LLM provider for testing."""
    
    def __init__(self, model: str):
        self.model = model
        self.call_count = 0
    
    def is_healthy(self) -> bool:
        return True
    
    async def chat(self, messages: list[dict], **kwargs) -> any:
        """Mock chat that returns valid JSON."""
        return await self._mock_response(messages)
    
    async def complete(self, prompt: str, **kwargs) -> any:
        """Mock complete (for methods using this API)."""
        return await self._mock_response([{"role": "user", "content": prompt}])
    
    async def _mock_response(self, messages: list[dict]) -> any:
        """Generate mock response based on prompt content."""
        self.call_count += 1
        
        # Extract what type of response is needed from prompt
        prompt = messages[0]["content"].lower() if messages else ""
        
        # Return appropriate mock response based on context
        if "perspective" in prompt or "constructive" in prompt:
            response_content = '{"solution": "Test solution", "key_insights": ["insight1"]}'
        elif "failure" in prompt or "narrative" in prompt:
            response_content = '{"narratives": [{"scenario": "test"}]}'
        elif "prior" in prompt or "probability" in prompt:
            response_content = '{"priors": {"h1": 0.5}}'
        elif "argument" in prompt or "claim" in prompt:
            response_content = '{"arguments": [{"claim": "test claim", "evidence": "evidence"}]}'
        elif "thesis" in prompt or "antithesis" in prompt:
            response_content = '{"statement": "Test statement", "supporting_arguments": ["arg1"]}'
        elif "finding" in prompt or "synthesis" in prompt:
            response_content = '{"findings": ["finding1"], "synthesis": "test synthesis"}'
        elif "question" in prompt:
            response_content = '{"questions": [{"question": "Test?", "answer": "Answer"}]}'
        elif "hypothesis" in prompt:
            response_content = '{"statement": "Test hypothesis", "null_hypothesis": "Null"}'
        elif "juror" in prompt or "verdict" in prompt:
            response_content = '{"verdict": "approve", "reasoning": "Test reasoning"}'
        elif "winner" in prompt or "judge" in prompt:
            response_content = '{"winner": "pro", "reasoning": "Test", "conclusion": "Conclusion"}'
        else:
            response_content = '{"result": "mock result"}'
        
        from dataclasses import dataclass
        
        @dataclass
        class MockResponse:
            content: str = response_content
            model: str = self.model
            tokens: int = 100
            cost: float = 0.001
        
        return MockResponse()


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_router():
    """Create mock router with test configuration."""
    router = MagicMock(spec=ExtendedNadirClawRouter)
    router.role_models = {
        "constructive": "xiaomi/mimo-v2-pro",
        "destructive": "qwen/qwen3.5-397b-a17b",
        "narrative": "qwen/qwen3-max-thinking",
        "prior": "z-ai/glm-4.5",
        "pro": "qwen/qwen3.5-397b-a17b",
        "thesis": "z-ai/glm-5",
        "query": "perplexity/sonar-pro-search",
        "clarification": "z-ai/glm-4.5-air:free",
        "hypothesis": "qwen/qwen3-max-thinking",
        "juror": "x-ai/grok-4.20-multi-agent-beta",
    }
    router.mid_model = "qwen/qwen3.5-flash"
    router.complex_model = "xiaomi/mimo-v2-pro"
    router.simple_model = "minimax/minimax-m2.5:free"
    router.get_provider_for_role = lambda role: MockProvider(router.role_models.get(role, "test/model"))
    router.track_cost = MagicMock()
    return router


@pytest.fixture
def test_context():
    """Create test reasoning context."""
    return ReasoningContext(
        stage_id="TEST",
        stage_name="Test Stage",
        input_data={
            "problem": "Test problem for reasoning",
            "topic": "Test topic",
            "question": "What is the best approach?",
            "observation": "Test observation",
        },
        metadata={"test": True},
    )


# =============================================================================
# Multi-Perspective Integration Tests
# =============================================================================

class TestMultiPerspectiveIntegration:
    """Integration tests for Multi-Perspective method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Multi-Perspective with router."""
        method = MultiPerspectiveMethod(router=mock_router, top_k=2)
        result = await method.execute(test_context)
        
        assert result.success
        assert "perspectives" in result.output
        assert mock_router.track_cost.called
    
    @pytest.mark.asyncio
    async def test_with_llm_client_fallback(self, test_context):
        """Test Multi-Perspective with llm_client fallback."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            content='{"solution": "fallback", "key_insights": ["test"]}'
        ))
        
        method = MultiPerspectiveMethod(llm_client=mock_llm, top_k=2)
        result = await method.execute(test_context)
        
        assert result.success
        assert mock_llm.chat.called
    
    @pytest.mark.asyncio
    async def test_cost_tracking(self, mock_router, test_context):
        """Test cost tracking is called."""
        method = MultiPerspectiveMethod(router=mock_router)
        await method.execute(test_context)
        
        assert mock_router.track_cost.called
        call_args = mock_router.track_cost.call_args
        assert call_args[1]["method"] == "multi_perspective"


# =============================================================================
# Pre-Mortem Integration Tests
# =============================================================================

class TestPreMortemIntegration:
    """Integration tests for Pre-Mortem method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Pre-Mortem with router."""
        test_context.input_data["proposed_design"] = {"test": "design"}
        method = PreMortemMethod(router=mock_router, num_scenarios=2)
        result = await method.execute(test_context)
        
        assert result.success
        assert mock_router.track_cost.called


# =============================================================================
# Bayesian Integration Tests
# =============================================================================

class TestBayesianIntegration:
    """Integration tests for Bayesian method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Bayesian with router."""
        test_context.input_data["hypotheses"] = ["H1", "H2"]
        method = BayesianMethod(router=mock_router)
        result = await method.execute(test_context)
        
        assert result.success


# =============================================================================
# Debate Integration Tests
# =============================================================================

class TestDebateIntegration:
    """Integration tests for Debate method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Debate with router."""
        test_context.input_data["topic"] = "Test debate topic"
        method = DebateMethod(router=mock_router, num_arguments=2)
        result = await method.execute(test_context)
        
        assert result.success
        assert "winner" in result.output


# =============================================================================
# Dialectical Integration Tests
# =============================================================================

class TestDialecticalIntegration:
    """Integration tests for Dialectical method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Dialectical with router."""
        test_context.input_data["topic"] = "Test dialectic topic"
        method = DialecticalMethod(router=mock_router)
        result = await method.execute(test_context)
        
        assert result.success


# =============================================================================
# Research Integration Tests
# =============================================================================

class TestResearchIntegration:
    """Integration tests for Research method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Research with router."""
        test_context.input_data["topic"] = "Test research topic"
        mock_search = MagicMock()
        method = ResearchMethod(router=mock_router, search_client=mock_search, max_iterations=2)
        result = await method.execute(test_context)
        
        assert result.success


# =============================================================================
# Socratic Integration Tests
# =============================================================================

class TestSocraticIntegration:
    """Integration tests for Socratic method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Socratic with router."""
        test_context.input_data["question"] = "What is truth?"
        method = SocraticMethod(router=mock_router, depth=1)
        result = await method.execute(test_context)
        
        assert result.success
        assert "key_insights" in result.output


# =============================================================================
# Scientific Integration Tests
# =============================================================================

class TestScientificIntegration:
    """Integration tests for Scientific method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Scientific with router."""
        test_context.input_data["observation"] = "Test observation"
        method = ScientificMethod(router=mock_router)
        result = await method.execute(test_context)
        
        assert result.success
        assert "hypothesis" in result.output


# =============================================================================
# Jury Integration Tests
# =============================================================================

class TestJuryIntegration:
    """Integration tests for Jury method."""
    
    @pytest.mark.asyncio
    async def test_with_router(self, mock_router, test_context):
        """Test Jury with router."""
        test_context.input_data["case"] = "Test case for evaluation"
        method = JuryMethod(router=mock_router, jury_size=3)
        result = await method.execute(test_context)
        
        assert result.success
        assert "verdict" in result.output


# =============================================================================
# Cross-Method Integration Tests
# =============================================================================

class TestAllReasonersIntegration:
    """Integration tests for all 9 reasoning methods together."""
    
    @pytest.mark.asyncio
    async def test_all_methods_with_router(self, mock_router, test_context):
        """Test all 9 methods work with router."""
        methods = [
            ("multi_perspective", MultiPerspectiveMethod(router=mock_router, top_k=2)),
            ("pre_mortem", PreMortemMethod(router=mock_router, num_scenarios=2)),
            ("bayesian", BayesianMethod(router=mock_router)),
            ("debate", DebateMethod(router=mock_router, num_arguments=2)),
            ("dialectical", DialecticalMethod(router=mock_router)),
            ("research", ResearchMethod(router=mock_router, search_client=MagicMock(), max_iterations=2)),
            ("socratic", SocraticMethod(router=mock_router, depth=1)),
            ("scientific", ScientificMethod(router=mock_router)),
            ("jury", JuryMethod(router=mock_router, jury_size=3)),
        ]
        
        # Prepare context for each method
        test_context.input_data.update({
            "problem": "Test problem",
            "proposed_design": {"test": "design"},
            "hypotheses": ["H1"],
            "topic": "Test topic",
            "question": "Test question?",
            "observation": "Test observation",
            "case": "Test case",
        })
        
        results = {}
        for name, method in methods:
            try:
                result = await method.execute(test_context)
                results[name] = {
                    "success": result.success,
                    "tracked_cost": mock_router.track_cost.called,
                }
                mock_router.track_cost.reset_mock()
            except Exception as e:
                results[name] = {"success": False, "error": str(e)}
        
        # Verify all methods succeeded
        for name, result in results.items():
            assert result.get("success"), f"{name} failed: {result.get('error', 'unknown')}"


# =============================================================================
# Backward Compatibility Tests
# =============================================================================

class TestBackwardCompatibility:
    """Test backward compatibility with llm_client."""
    
    @pytest.mark.asyncio
    async def test_all_methods_with_llm_client(self, test_context):
        """Test all 9 methods work with llm_client fallback."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            content='{"result": "mock"}'
        ))
        
        methods = [
            MultiPerspectiveMethod(llm_client=mock_llm, top_k=2),
            PreMortemMethod(llm_client=mock_llm, num_scenarios=2),
            BayesianMethod(llm_client=mock_llm),
            DebateMethod(llm_client=mock_llm, num_arguments=2),
            DialecticalMethod(llm_client=mock_llm),
            ResearchMethod(llm_client=mock_llm, search_client=MagicMock(), max_iterations=2),
            SocraticMethod(llm_client=mock_llm, depth=1),
            ScientificMethod(llm_client=mock_llm),
            JuryMethod(llm_client=mock_llm, jury_size=3),
        ]
        
        test_context.input_data.update({
            "problem": "Test",
            "proposed_design": {},
            "hypotheses": [],
            "topic": "Test",
            "question": "Test?",
            "observation": "Test",
            "case": "Test",
        })
        
        for i, method in enumerate(methods):
            result = await method.execute(test_context)
            # Should succeed with fallback
            assert result is not None
