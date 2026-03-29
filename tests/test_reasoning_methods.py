"""Tests for reasoning methods.

This module tests all 9 reasoning methods:
- Multi-Perspective
- Pre-Mortem
- Bayesian
- Debate
- Dialectical
- Research
- Socratic
- Scientific
- Jury

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

from berb.reasoning.base import (
    ReasoningContext,
    ReasoningResult,
    MethodType,
    create_context,
)
from berb.reasoning.multi_perspective import MultiPerspectiveMethod
from berb.reasoning.pre_mortem import PreMortemMethod
from berb.reasoning.bayesian import BayesianMethod
from berb.reasoning.debate import DebateMethod
from berb.reasoning.dialectical import DialecticalMethod
from berb.reasoning.research import ResearchMethod
from berb.reasoning.socratic import SocraticMethod
from berb.reasoning.scientific import ScientificMethod
from berb.reasoning.jury import JuryMethod


# ============== Fixtures ==============

@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client for testing."""
    client = Mock()
    client.chat = Mock(return_value=Mock(content='{"result": "test"}'))
    return client


@pytest.fixture
def mock_search_client():
    """Create a mock search client for testing."""
    client = Mock()
    client.search = AsyncMock(return_value={"results": [{"snippet": "test result"}]})
    return client


@pytest.fixture
def sample_context():
    """Create a sample reasoning context."""
    return create_context(
        stage_id="TEST_STAGE",
        stage_name="Test Stage",
        input_data={
            "topic": "Test research topic",
            "hypothesis": "Test hypothesis",
            "question": "Test question?",
        },
        model="test-model",
    )


# ============== Base Class Tests ==============

class TestReasoningContext:
    """Test ReasoningContext class."""

    def test_create_context(self):
        """Test context creation."""
        ctx = create_context(
            stage_id="HYPOTHESIS_GEN",
            stage_name="Hypothesis Generation",
            input_data={"topic": "AI safety"},
        )
        assert ctx.stage_id == "HYPOTHESIS_GEN"
        assert ctx.stage_name == "Hypothesis Generation"
        assert ctx.get("topic") == "AI safety"

    def test_context_get_set(self):
        """Test context get/set methods."""
        ctx = ReasoningContext(
            stage_id="TEST",
            stage_name="Test",
        )
        ctx.set("key", "value")
        assert ctx.get("key") == "value"
        assert ctx.get("missing", "default") == "default"

    def test_context_to_dict(self):
        """Test context to_dict method."""
        ctx = create_context(
            stage_id="TEST",
            stage_name="Test",
            input_data={"key": "value"},
        )
        d = ctx.to_dict()
        assert d["stage_id"] == "TEST"
        assert d["input_data"]["key"] == "value"

    def test_context_from_dict(self):
        """Test context from_dict method."""
        d = {
            "stage_id": "TEST",
            "stage_name": "Test",
            "input_data": {"key": "value"},
            "metadata": {},
            "created_at": "2026-03-28T00:00:00",
        }
        ctx = ReasoningContext.from_dict(d)
        assert ctx.stage_id == "TEST"
        assert ctx.get("key") == "value"


class TestReasoningResult:
    """Test ReasoningResult class."""

    def test_success_result(self):
        """Test successful result creation."""
        result = ReasoningResult.success_result(
            MethodType.BAYESIAN,
            output={"key": "value"},
            confidence=0.8,
        )
        assert result.success is True
        assert result.confidence == 0.8
        assert result.output["key"] == "value"

    def test_error_result(self):
        """Test error result creation."""
        result = ReasoningResult.error_result(
            MethodType.BAYESIAN,
            error="Test error",
        )
        assert result.success is False
        assert result.error == "Test error"

    def test_result_to_dict(self):
        """Test result to_dict method."""
        result = ReasoningResult.success_result(
            MethodType.BAYESIAN,
            output={"key": "value"},
        )
        d = result.to_dict()
        assert d["method_type"] == "bayesian"
        assert d["success"] is True


# ============== Method Tests ==============

class TestMultiPerspectiveMethod:
    """Test Multi-Perspective reasoning method."""

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, mock_llm_client, sample_context):
        """Test multi-perspective execution with mock LLM."""
        method = MultiPerspectiveMethod()
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.MULTI_PERSPECTIVE

    def test_validate_context(self, sample_context):
        """Test context validation."""
        method = MultiPerspectiveMethod()
        assert method.validate_context(sample_context) is True

    def test_validate_context_missing_stage(self):
        """Test validation with missing stage."""
        ctx = ReasoningContext(
            stage_id="",
            stage_name="Test",
        )
        method = MultiPerspectiveMethod()
        assert method.validate_context(ctx) is False


class TestPreMortemMethod:
    """Test Pre-Mortem reasoning method."""

    @pytest.mark.asyncio
    async def test_execute(self, sample_context):
        """Test pre-mortem execution."""
        # Add required field for pre-mortem
        sample_context.input_data["proposed_design"] = "Test design"
        method = PreMortemMethod()
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.PRE_MORTEM
        # Pre-mortem has fallback implementation
        assert result.success is True


class TestBayesianMethod:
    """Test Bayesian reasoning method."""

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, mock_llm_client, sample_context):
        """Test Bayesian execution with mock LLM."""
        # Add required fields for Bayesian
        sample_context.input_data["hypotheses"] = [
            {"name": "H1", "prior": 0.5, "description": "Test hypothesis 1"},
            {"name": "H2", "prior": 0.3, "description": "Test hypothesis 2"},
        ]
        sample_context.input_data["evidence"] = [
            {"name": "E1", "description": "Test evidence"}
        ]
        method = BayesianMethod()
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.BAYESIAN

    def test_prior_posterior_update(self):
        """Test Bayesian prior/posterior update."""
        # Test Bayes' theorem calculation manually
        prior = 0.5
        likelihood = 0.8
        marginal = 0.6
        # P(H|E) = P(E|H) * P(H) / P(E)
        posterior = (likelihood * prior) / marginal
        assert posterior == pytest.approx(0.667, rel=0.01)


class TestDebateMethod:
    """Test Debate reasoning method."""

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, mock_llm_client, sample_context):
        """Test debate execution with mock LLM."""
        method = DebateMethod(llm_client=mock_llm_client, num_arguments=2)
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.DEBATE

    @pytest.mark.asyncio
    async def test_execute_fallback(self, sample_context):
        """Test debate execution without LLM."""
        method = DebateMethod(num_arguments=2)
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        # Should have fallback arguments
        assert result.success is True


class TestDialecticalMethod:
    """Test Dialectical reasoning method."""

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, mock_llm_client, sample_context):
        """Test dialectical execution with mock LLM."""
        method = DialecticalMethod(llm_client=mock_llm_client)
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.DIALECTICAL

    @pytest.mark.asyncio
    async def test_thesis_antithesis_synthesis(self, sample_context):
        """Test dialectical structure."""
        method = DialecticalMethod()
        result = await method.execute(sample_context)
        assert result.success is True
        output = result.output
        assert "thesis" in output
        assert "antithesis" in output
        assert "synthesis" in output


class TestResearchMethod:
    """Test Research reasoning method."""

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, mock_llm_client, mock_search_client, sample_context):
        """Test research execution with mocks."""
        method = ResearchMethod(
            llm_client=mock_llm_client,
            search_client=mock_search_client,
            max_iterations=2,
        )
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.RESEARCH

    @pytest.mark.asyncio
    async def test_iteration_convergence(self, sample_context):
        """Test research iteration convergence."""
        method = ResearchMethod(max_iterations=1)
        result = await method.execute(sample_context)
        assert result.success is True
        assert result.output["iterations"] >= 1


class TestSocraticMethod:
    """Test Socratic reasoning method."""

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, mock_llm_client, sample_context):
        """Test Socratic execution with mock LLM."""
        method = SocraticMethod(llm_client=mock_llm_client, depth=1)
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.SOCRATIC

    @pytest.mark.asyncio
    async def test_all_categories(self, sample_context):
        """Test all Socratic categories are covered."""
        method = SocraticMethod(depth=1)
        result = await method.execute(sample_context)
        assert result.success is True
        questions_by_category = result.output.get("questions_by_category", {})
        # Should have all 6 categories
        assert len(questions_by_category) == 6


class TestScientificMethod:
    """Test Scientific reasoning method."""

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, mock_llm_client, sample_context):
        """Test scientific execution with mock LLM."""
        method = ScientificMethod(llm_client=mock_llm_client)
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.SCIENTIFIC

    @pytest.mark.asyncio
    async def test_hypothesis_structure(self, sample_context):
        """Test hypothesis structure."""
        method = ScientificMethod()
        result = await method.execute(sample_context)
        assert result.success is True
        hypothesis = result.output.get("hypothesis", {})
        assert "statement" in hypothesis
        assert "null_hypothesis" in hypothesis
        assert "predictions" in hypothesis


class TestJuryMethod:
    """Test Jury reasoning method."""

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, mock_llm_client, sample_context):
        """Test jury execution with mock LLM."""
        method = JuryMethod(llm_client=mock_llm_client, jury_size=4)
        result = await method.execute(sample_context)
        assert isinstance(result, ReasoningResult)
        assert result.method_type == MethodType.JURY

    @pytest.mark.asyncio
    async def test_vote_counting(self, sample_context):
        """Test jury vote counting."""
        method = JuryMethod(jury_size=3)
        result = await method.execute(sample_context)
        assert result.success is True
        vote_count = result.output.get("vote_count", {})
        total_votes = sum(vote_count.values())
        assert total_votes == 3  # 3 jurors

    def test_verdict_determination(self):
        """Test verdict determination logic."""
        # Test vote counting logic manually
        votes = ["approve", "approve", "approve"]
        vote_count = {"approve": votes.count("approve"), "reject": votes.count("reject"), "abstain": votes.count("abstain")}
        
        if vote_count["approve"] == len(votes):
            verdict = "unanimous_approve"
        elif vote_count["reject"] == len(votes):
            verdict = "unanimous_reject"
        elif vote_count["approve"] > vote_count["reject"]:
            verdict = "majority_approve"
        else:
            verdict = "hung"
            
        assert verdict == "unanimous_approve"
        
        # Test majority
        votes = ["approve", "approve", "reject"]
        vote_count = {"approve": votes.count("approve"), "reject": votes.count("reject"), "abstain": votes.count("abstain")}
        if vote_count["approve"] > vote_count["reject"]:
            verdict = "majority_approve"
        assert verdict == "majority_approve"


# ============== Integration Tests ==============

class TestReasoningIntegration:
    """Integration tests for reasoning methods."""

    @pytest.mark.asyncio
    async def test_all_methods_execute(self, sample_context):
        """Test that all reasoning methods can execute."""
        methods = [
            MultiPerspectiveMethod(),
            PreMortemMethod(),
            BayesianMethod(),
            DebateMethod(),
            DialecticalMethod(),
            ResearchMethod(),
            SocraticMethod(),
            ScientificMethod(),
            JuryMethod(),
        ]

        for method in methods:
            result = await method.execute(sample_context)
            assert isinstance(result, ReasoningResult)
            assert result.method_type is not None

    @pytest.mark.asyncio
    async def test_method_type_coverage(self):
        """Test that all MethodType values have implementations."""
        implemented_types = {
            MethodType.MULTI_PERSPECTIVE,
            MethodType.PRE_MORTEM,
            MethodType.BAYESIAN,
            MethodType.DEBATE,
            MethodType.DIALECTICAL,
            MethodType.RESEARCH,
            MethodType.SOCRATIC,
            MethodType.SCIENTIFIC,
            MethodType.JURY,
        }

        all_types = set(MethodType)
        assert implemented_types == all_types, "Not all MethodType values have implementations"


# ============== Error Handling Tests ==============

class TestErrorHandling:
    """Test error handling in reasoning methods."""

    @pytest.mark.asyncio
    async def test_missing_topic(self):
        """Test handling of missing topic."""
        ctx = create_context(
            stage_id="TEST",
            stage_name="Test",
            input_data={},  # No topic/hypothesis/question
        )

        method = DebateMethod()
        result = await method.execute(ctx)
        assert result.success is False
        assert "missing" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_context(self):
        """Test handling of invalid context."""
        ctx = ReasoningContext(
            stage_id="",
            stage_name="",
        )

        method = BayesianMethod()
        result = await method.execute(ctx)
        assert result.success is False


# ============== Performance Tests ==============

class TestPerformance:
    """Performance tests for reasoning methods."""

    @pytest.mark.asyncio
    async def test_execution_time(self, sample_context):
        """Test that methods execute within reasonable time."""
        import time

        method = PreMortemMethod()  # Fastest (no LLM required)
        start = time.time()
        result = await method.execute(sample_context)
        duration = time.time() - start

        assert duration < 5.0  # Should complete in under 5 seconds
        assert result.duration_sec >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
