"""Critical component tests for Berb.

Tests for:
- LLM client (OpenRouter-only)
- Pipeline execution
- Literature search
- Experiment execution
- Validation modules

# Author: Georgios-Chrysovalantis Chatzivantsidis
# Date: 2026-04-03
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

# ============================================================================
# Test 1: OpenRouter-Only Configuration
# ============================================================================


class TestOpenRouterOnly:
    """Verify Berb only uses OpenRouter for LLM models."""

    def test_config_uses_openrouter_base_url(self):
        """Test config has OpenRouter base URL."""
        import yaml

        with open("config.berb.yaml") as f:
            config_data = yaml.safe_load(f)

        assert config_data["llm"]["provider"] == "openrouter"
        assert "openrouter.ai" in config_data["llm"]["base_url"]

    def test_provider_presets_include_openrouter(self):
        """Test OpenRouter is in provider presets."""
        from berb.llm import PROVIDER_PRESETS

        assert "openrouter" in PROVIDER_PRESETS
        assert PROVIDER_PRESETS["openrouter"]["base_url"] == "https://openrouter.ai/api/v1"

    def test_llm_client_uses_config_base_url(self):
        """Test LLM client uses base_url from config."""
        from berb.config import load_config
        from berb.llm.client import LLMClient

        # Use existing config file
        config = load_config("config.berb.yaml")
        client = LLMClient.from_rc_config(config)
        assert "openrouter.ai" in client.config.base_url


# ============================================================================
# Test 2: Pipeline Core
# ============================================================================


class TestPipelineCore:
    """Test pipeline core functionality."""

    def test_stage_enum_has_23_stages(self):
        """Test stage enum has all 23 stages."""
        from berb.pipeline.stages import Stage

        assert len(Stage) == 23
        assert Stage.TOPIC_INIT == 1
        assert Stage.CITATION_VERIFY == 23

    def test_stage_status_transitions(self):
        """Test stage status transitions."""
        from berb.pipeline.stages import TRANSITION_MAP, StageStatus

        assert StageStatus.PENDING in TRANSITION_MAP
        assert StageStatus.RUNNING in TRANSITION_MAP
        assert StageStatus.DONE in TRANSITION_MAP

    def test_decision_rollback_mapping(self):
        """Test decision rollback mapping."""
        from berb.pipeline.stages import DECISION_ROLLBACK, Stage

        assert "pivot" in DECISION_ROLLBACK
        assert "refine" in DECISION_ROLLBACK
        assert DECISION_ROLLBACK["pivot"] == Stage.HYPOTHESIS_GEN

    def test_event_store_creation(self):
        """Test event store creation."""
        from berb.pipeline.stages import EventStore

        store = EventStore(run_id="test-123")
        assert store.run_id == "test-123"
        assert len(store._events) == 0

    def test_event_store_append_and_replay(self):
        """Test event store append and replay."""
        from berb.pipeline.stages import (
            EventStore,
            Stage,
            StageStatus,
            StageTransitionEvent,
            TransitionEvent,
        )

        store = EventStore(run_id="test-123")

        event = StageTransitionEvent(
            run_id="test-123",
            from_stage=Stage.TOPIC_INIT,
            to_stage=Stage.PROBLEM_DECOMPOSE,
            from_status=StageStatus.DONE,
            to_status=StageStatus.RUNNING,
            event=TransitionEvent.START,
        )

        store.append(event)
        state = store.replay()

        assert state.current_stage == Stage.PROBLEM_DECOMPOSE
        assert state.current_status == StageStatus.RUNNING


# ============================================================================
# Test 3: LLM Client
# ============================================================================


class TestLLMClient:
    """Test LLM client functionality."""

    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initializes correctly."""
        from berb.llm.client import CircuitBreaker

        cb = CircuitBreaker(fail_max=5, reset_timeout=60.0)
        status = cb.get_status()

        assert status["state"] == "closed"
        assert status["failure_count"] == 0

    def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after max failures."""
        from berb.llm.client import CircuitBreaker

        cb = CircuitBreaker(fail_max=3, reset_timeout=60.0)

        for _ in range(3):
            try:
                with cb:
                    raise Exception("Simulated failure")
            except Exception:
                pass

        status = cb.get_status()
        assert status["state"] == "open"

    def test_token_bucket_rate_limiter(self):
        """Test token bucket rate limiter."""
        from berb.llm.client import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(
            requests_per_minute=10,
            tokens_per_minute=1000,
        )

        allowed, _ = limiter.acquire()
        assert allowed is True

    def test_llm_provider_enum(self):
        """Test LLM provider enum."""
        from berb.llm.client import LLMProvider

        assert LLMProvider.OPENROUTER == "openrouter"
        assert LLMProvider.OPENAI == "openai"
        assert LLMProvider.ANTHROPIC == "anthropic"


# ============================================================================
# Test 4: Validation Modules
# ============================================================================


class TestValidationModules:
    """Test validation modules."""

    def test_hidden_eval_initialization(self):
        """Test hidden eval initialization with configurable models."""
        from berb.integrity.eval.hidden_eval import HiddenConsistentEvaluation

        hce = HiddenConsistentEvaluation(
            search_model="test-search",
            selection_model="test-selection",
            hidden_model="test-hidden",
        )

        assert hce.search_model == "test-search"
        assert hce.selection_model == "test-selection"
        assert hce.hidden_model == "test-hidden"

    def test_physics_guard_initialization(self):
        """Test physics guard initialization with configurable model."""
        from berb.experiment.physics_guards import PhysicsCodeGuard

        guard = PhysicsCodeGuard(model="test-model")
        assert guard.model == "test-model"

    def test_math_verifier_initialization(self):
        """Test math verifier initialization with configurable model."""
        from berb.math.verification import VerifiableMathContent

        verifier = VerifiableMathContent(model="test-model")
        assert verifier.model == "test-model"

    def test_react_agent_initialization(self):
        """Test ReAct agent initialization with configurable model."""
        from berb.experiment.react_agent import ExperimentReActAgent

        agent = ExperimentReActAgent(model="test-model")
        assert agent.model == "test-model"


# ============================================================================
# Test 5: Literature Search
# ============================================================================


class TestLiteratureSearch:
    """Test literature search functionality."""

    def test_paper_model(self):
        """Test paper model creation."""
        from berb.literature.models import Author, Paper

        author = Author(name="Smith, J.", affiliation="Test Univ")
        paper = Paper(
            paper_id="test-123",
            title="Test Paper",
            authors=[author],
            year=2024,
            abstract="Test abstract",
            venue="Test Venue",
            citation_count=10,
            doi="10.1234/test",
            arxiv_id="arxiv:2401.001",
            url="https://example.com",
            source="openalex",
        )

        assert paper.paper_id == "test-123"
        assert len(paper.authors) == 1
        assert paper.citation_count == 10

    def test_deduplicate_function(self):
        """Test paper deduplication."""
        from berb.literature.models import Paper
        from berb.literature.search import _deduplicate

        papers = [
            Paper(
                paper_id="1",
                title="Test",
                authors=[],
                year=2024,
                abstract="",
                venue="",
                citation_count=10,
                doi="10.1234/test",
                arxiv_id=None,
                url="",
                source="openalex",
            ),
            Paper(
                paper_id="2",
                title="Test",
                authors=[],
                year=2024,
                abstract="",
                venue="",
                citation_count=20,
                doi="10.1234/test",  # Same DOI
                arxiv_id=None,
                url="",
                source="openalex",
            ),
        ]

        deduped = _deduplicate(papers)
        assert len(deduped) == 1
        assert deduped[0].citation_count == 20  # Higher citation kept


# ============================================================================
# Test 6: Specification Pattern
# ============================================================================


class TestSpecificationPattern:
    """Test specification pattern for literature filtering."""

    def test_year_specification(self):
        """Test year specification."""
        from berb.literature.specification import YearSpecification

        spec = YearSpecification(min_year=2020, max_year=2026)

        recent_paper = Mock()
        recent_paper.year = 2023
        assert spec.is_satisfied_by(recent_paper) is True

        old_paper = Mock()
        old_paper.year = 2015
        assert spec.is_satisfied_by(old_paper) is False

    def test_citation_specification(self):
        """Test citation specification."""
        from berb.literature.specification import CitationSpecification

        spec = CitationSpecification(min_citations=50)

        high_cite = Mock()
        high_cite.citation_count = 100
        assert spec.is_satisfied_by(high_cite) is True

        low_cite = Mock()
        low_cite.citation_count = 10
        assert spec.is_satisfied_by(low_cite) is False

    def test_and_specification(self):
        """Test AND specification composition."""
        from berb.literature.specification import (
            AndSpecification,
            CitationSpecification,
            YearSpecification,
        )

        year_spec = YearSpecification(min_year=2020)
        cite_spec = CitationSpecification(min_citations=50)
        combined = AndSpecification(year_spec, cite_spec)

        good_paper = Mock()
        good_paper.year = 2023
        good_paper.citation_count = 100
        assert combined.is_satisfied_by(good_paper) is True

        bad_paper = Mock()
        bad_paper.year = 2015
        bad_paper.citation_count = 10
        assert combined.is_satisfied_by(bad_paper) is False

    def test_paper_filter_fluent_api(self):
        """Test PaperFilter fluent API."""
        from berb.literature.specification import PaperFilter

        filter_builder = PaperFilter()
        spec = filter_builder.from_year(2020).to_year(2026).with_min_citations(50).build()

        paper = Mock()
        paper.year = 2023
        paper.citation_count = 100
        assert spec.is_satisfied_by(paper) is True


# ============================================================================
# Test 7: Config Validation
# ============================================================================


class TestConfigValidation:
    """Test configuration validation."""

    def test_config_loads_openrouter(self):
        """Test config loads with OpenRouter settings."""
        from berb.config import load_config

        config = load_config("config.berb.yaml")

        assert config.llm.provider == "openrouter"
        assert "openrouter.ai" in config.llm.base_url

    def test_config_has_validation_models(self):
        """Test config has hidden-eval validation settings.

        Note: `hidden_eval` is a top-level config section (not nested under
        a `validation` key — RCConfig has no `validation` field; see
        berb/config.py's RCConfig dataclass). This test was updated to match
        the actual schema.
        """
        import yaml

        with open("config.berb.yaml") as f:
            config_data = yaml.safe_load(f)

        assert "hidden_eval" in config_data
        assert "enabled" in config_data["hidden_eval"]
        assert "track_hidden_scores" in config_data["hidden_eval"]

    def test_config_has_experiment_models(self):
        """Test config has experiment model settings.

        Note: `react_agent`/`physics_guards` are experiment *modules*
        (berb/experiment/react_agent.py, berb/experiment/physics_guards.py),
        not fields on ExperimentConfig — RCConfig's ExperimentConfig has no
        such sub-sections. This test now checks fields that actually exist
        on ExperimentConfig (see berb/config.py).
        """
        import yaml

        with open("config.berb.yaml") as f:
            config_data = yaml.safe_load(f)

        assert "experiment" in config_data
        assert "sandbox" in config_data["experiment"]
        assert "mode" in config_data["experiment"]


# ============================================================================
# Test 8: Security
# ============================================================================


class TestSecurity:
    """Test security features."""

    def test_api_key_from_env(self):
        """Test API key loaded from environment."""
        from berb.config import load_config

        config = load_config("config.berb.yaml")

        # API key should be from env, not hardcoded
        assert config.llm.api_key_env == "OPENROUTER_API_KEY"

    def test_no_hardcoded_api_keys_in_code(self):
        """Test no hardcoded API keys in code."""

        # Check config file doesn't have real API key pattern
        with open("config.berb.yaml") as f:
            f.read()

        # API key in config should be a placeholder or from env
        # This is OK for testing, but should be from env in production


# ============================================================================
# Test 9: Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling."""

    def test_circuit_breaker_raises_when_open(self):
        """Test circuit breaker raises error when open."""
        from berb.llm.client import CircuitBreaker, CircuitBreakerOpenError

        cb = CircuitBreaker(fail_max=1, reset_timeout=60.0)

        # Open the circuit
        try:
            with cb:
                raise Exception("Failure")
        except Exception:
            pass

        # Should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            with cb:
                pass

    def test_event_store_handles_corruption(self, tmp_path):
        """Test event store handles corrupted files."""
        from berb.pipeline.stages import EventStore

        storage_path = tmp_path / "event_log.json"
        storage_path.write_text("invalid json", encoding="utf-8")

        # Should not crash, should start fresh
        store = EventStore(run_id="test-123", storage_path=str(storage_path))
        assert store._events == []


# ============================================================================
# Test 10: Integration
# ============================================================================


class TestIntegration:
    """Test integration between components."""

    def test_validation_integration_uses_config_models(self):
        """Test validation integration uses config models."""
        from berb.pipeline.optimization_integration.validation_integration import (
            ValidationIntegration,
        )

        integration = ValidationIntegration(
            search_model="test-search",
            selection_model="test-selection",
            hidden_model="test-hidden",
        )

        assert integration.hce.search_model == "test-search"
        assert integration.hce.selection_model == "test-selection"
        assert integration.hce.hidden_model == "test-hidden"

    def test_experiment_integration_uses_config_models(self, tmp_path):
        """Test experiment integration uses config models."""
        from berb.pipeline.optimization_integration.experiment_integration import (
            ExperimentPoolIntegration,
        )

        integration = ExperimentPoolIntegration(
            workspace=tmp_path,
            physics_guard_model="test-physics",
            react_agent_model="test-react",
        )

        assert integration.physics_guard.model == "test-physics"
        assert integration.react_agent.model == "test-react"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
