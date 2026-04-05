"""Unit tests for Berb cross-model review and improvement loop.

Tests for:
- CrossModelReviewer (M1)
- AutonomousImprovementLoop (M2)
- ClaimTracker (M2)
- ComputeGuard (M2)

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from berb.review.cross_model_reviewer import (
    CrossModelReviewer,
    CrossModelReviewConfig,
    CrossModelReviewConfigPreset,
    ReviewVerdict,
    WeaknessSeverity,
    Weakness,
    ReviewResult,
    ImprovementDelta,
    get_review_config_for_generation,
)

from berb.pipeline.improvement_loop import (
    AutonomousImprovementLoop,
    ImprovementLoopConfig,
    ImprovementResult,
    ScoreProgression,
    RoundResult,
    ClaimTracker,
    ClaimRecord,
    ClaimVerdict,
    FixType,
    ClassifiedWeakness,
    ComputeGuard,
)


class TestCrossModelReviewConfig:
    """Test CrossModelReviewConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = CrossModelReviewConfig(
            generation_provider="anthropic",
            review_provider="openai",
        )
        assert config.review_model == "gpt-4o"
        assert config.review_temperature == 0.3
        assert config.hide_generation_model is True
        assert config.allow_same_provider is False

    def test_validate_provider_separation(self):
        """Test provider separation validation."""
        # Different providers - valid
        config = CrossModelReviewConfig(
            generation_provider="anthropic",
            review_provider="openai",
        )
        is_valid, error = config.validate_provider_separation()
        assert is_valid is True
        assert error == ""

        # Same providers - invalid
        config = CrossModelReviewConfig(
            generation_provider="anthropic",
            review_provider="anthropic",
        )
        is_valid, error = config.validate_provider_separation()
        assert is_valid is False
        assert "cannot be the same" in error

        # Same providers but allow_same_provider=True
        config = CrossModelReviewConfig(
            generation_provider="anthropic",
            review_provider="anthropic",
            allow_same_provider=True,
        )
        is_valid, error = config.validate_provider_separation()
        assert is_valid is True

    def test_presets(self):
        """Test configuration presets."""
        assert CrossModelReviewConfigPreset.CLAUDE_TO_GPT.generation_provider == "anthropic"
        assert CrossModelReviewConfigPreset.CLAUDE_TO_GPT.review_provider == "openai"

        assert CrossModelReviewConfigPreset.GPT_TO_CLAUDE.generation_provider == "openai"
        assert CrossModelReviewConfigPreset.GPT_TO_CLAUDE.review_provider == "anthropic"


class TestReviewVerdict:
    """Test ReviewVerdict enum."""

    def test_verdict_values(self):
        """Test verdict enum values."""
        assert ReviewVerdict.ACCEPT.value == "accept"
        assert ReviewVerdict.WEAK_ACCEPT.value == "weak_accept"
        assert ReviewVerdict.BORDERLINE.value == "borderline"
        assert ReviewVerdict.REJECT.value == "reject"


class TestWeakness:
    """Test Weakness model."""

    def test_create_weakness(self):
        """Test creating weakness."""
        weakness = Weakness(
            category="methods",
            description="Sample size too small",
            severity=WeaknessSeverity.MAJOR,
            location="Section 4.2",
        )
        assert weakness.category == "methods"
        assert weakness.severity == WeaknessSeverity.MAJOR
        assert weakness.actionable is True


class TestReviewResult:
    """Test ReviewResult model."""

    def test_create_review_result(self):
        """Test creating review result."""
        review = ReviewResult(
            overall_score=7.5,
            verdict=ReviewVerdict.WEAK_ACCEPT,
            strengths=["Novel contribution", "Well-written"],
            weaknesses=[
                Weakness(
                    category="experiments",
                    description="Needs more baselines",
                    severity=WeaknessSeverity.MINOR,
                )
            ],
            confidence=0.8,
        )
        assert review.overall_score == 7.5
        assert len(review.strengths) == 2
        assert len(review.weaknesses) == 1


class TestImprovementDelta:
    """Test ImprovementDelta model."""

    def test_create_delta(self):
        """Test creating improvement delta."""
        delta = ImprovementDelta(
            score_change=1.5,
            improvements_made=["Fixed clarity", "Added analysis"],
            net_improvement=True,
        )
        assert delta.score_change == 1.5
        assert len(delta.improvements_made) == 2
        assert delta.net_improvement is True


class TestGetReviewConfig:
    """Test get_review_config_for_generation."""

    def test_claude_generation(self):
        """Test config for Claude generation."""
        config = get_review_config_for_generation("anthropic")
        assert config.review_provider == "openai"

    def test_gpt_generation(self):
        """Test config for GPT generation."""
        config = get_review_config_for_generation("openai")
        assert config.review_provider == "anthropic"

    def test_unknown_generation(self):
        """Test config for unknown generation provider."""
        config = get_review_config_for_generation("unknown")
        assert config.review_provider == "openai"  # Default


class TestCrossModelReviewer:
    """Test CrossModelReviewer."""

    def test_create_reviewer(self):
        """Test creating reviewer."""
        config = CrossModelReviewConfig(
            generation_provider="anthropic",
            review_provider="openai",
        )
        mock_provider = MagicMock()
        reviewer = CrossModelReviewer(mock_provider, config)
        assert reviewer.config == config

    def test_create_reviewer_same_provider_fails(self):
        """Test that same provider raises error."""
        config = CrossModelReviewConfig(
            generation_provider="anthropic",
            review_provider="anthropic",
        )
        mock_provider = MagicMock()
        with pytest.raises(ValueError) as exc_info:
            CrossModelReviewer(mock_provider, config)
        assert "cannot be the same" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_review_generation(self):
        """Test review generation."""
        config = CrossModelReviewConfig(
            generation_provider="anthropic",
            review_provider="openai",
        )
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = '''
        {
            "overall_score": 7.5,
            "verdict": "weak_accept",
            "strengths": ["Novel idea"],
            "weaknesses": [
                {
                    "category": "experiments",
                    "description": "Needs more baselines",
                    "severity": "minor",
                    "location": "",
                    "evidence": "",
                    "actionable": true
                }
            ],
            "missing_experiments": [],
            "writing_issues": [],
            "actionable_improvements": ["Add baselines"],
            "confidence": 0.8,
            "review_text": "Good paper overall"
        }
        '''
        
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)
        
        reviewer = CrossModelReviewer(mock_provider, config)
        
        review = await reviewer.review(
            paper_text="Test paper content" * 100,
            venue="neurips",
        )
        
        assert review.overall_score == 7.5
        assert review.verdict == ReviewVerdict.WEAK_ACCEPT
        assert len(review.weaknesses) == 1

    def test_compare_with_prior(self):
        """Test review comparison."""
        config = CrossModelReviewConfig(
            generation_provider="anthropic",
            review_provider="openai",
        )
        mock_provider = MagicMock()
        reviewer = CrossModelReviewer(mock_provider, config)
        
        prior = ReviewResult(
            overall_score=6.0,
            verdict=ReviewVerdict.BORDERLINE,
            weaknesses=[
                Weakness(
                    category="clarity",
                    description="Unclear methods",
                    severity=WeaknessSeverity.MAJOR,
                )
            ],
        )
        
        current = ReviewResult(
            overall_score=7.5,
            verdict=ReviewVerdict.WEAK_ACCEPT,
            weaknesses=[
                Weakness(
                    category="experiments",
                    description="Needs more baselines",
                    severity=WeaknessSeverity.MINOR,
                )
            ],
        )
        
        delta = reviewer.compare_with_prior(current, prior)
        
        assert delta.score_change == 1.5
        assert len(delta.improvements_made) == 1
        assert "Unclear methods" in delta.improvements_made[0]


class TestClaimTracker:
    """Test ClaimTracker."""

    @pytest.mark.asyncio
    async def test_register_claim(self):
        """Test claim registration."""
        tracker = ClaimTracker()
        
        claim_id = await tracker.register_claim(
            claim="Method X improves accuracy by 15%",
            source_stage=8,
            evidence=["experiment_1_results"],
            round_num=1,
        )
        
        assert claim_id == "claim_1"
        assert claim_id in tracker.claims
        assert tracker.claims[claim_id].status == "active"

    @pytest.mark.asyncio
    async def test_challenge_claim(self):
        """Test claim challenging."""
        tracker = ClaimTracker()
        
        claim_id = await tracker.register_claim(
            claim="Test claim",
            source_stage=8,
            evidence=[],
        )
        
        await tracker.challenge_claim(
            claim_id=claim_id,
            round_num=2,
            reason="Unsupported by evidence",
        )
        
        assert tracker.claims[claim_id].status == "challenged"
        assert len(tracker.claims[claim_id].challenge_history) == 1

    @pytest.mark.asyncio
    async def test_verify_claim_supported(self):
        """Test claim verification - supported."""
        tracker = ClaimTracker()
        
        claim_id = await tracker.register_claim(
            claim="Test claim",
            source_stage=8,
            evidence=[],
        )
        
        verdict = await tracker.verify_claim(
            claim_id=claim_id,
            experiment_results={
                "success": True,
                "effect_size": 0.5,
                "p_value": 0.01,
            },
        )
        
        assert verdict == ClaimVerdict.SUPPORTED
        assert tracker.claims[claim_id].status == "verified"

    @pytest.mark.asyncio
    async def test_verify_claim_refuted(self):
        """Test claim verification - refuted."""
        tracker = ClaimTracker()
        
        claim_id = await tracker.register_claim(
            claim="Test claim",
            source_stage=8,
            evidence=[],
        )
        
        verdict = await tracker.verify_claim(
            claim_id=claim_id,
            experiment_results={
                "success": False,
                "effect_size": 0.1,
                "p_value": 0.5,
            },
        )
        
        assert verdict == ClaimVerdict.REFUTED

    @pytest.mark.asyncio
    async def test_kill_claim(self):
        """Test claim killing."""
        tracker = ClaimTracker()
        
        claim_id = await tracker.register_claim(
            claim="Test claim",
            source_stage=8,
            evidence=[],
        )
        
        await tracker.kill_claim(
            claim_id=claim_id,
            reason="Evidence does not support claim",
        )
        
        assert tracker.claims[claim_id].status == "killed"
        assert tracker.claims[claim_id].kill_reason == "Evidence does not support claim"

    @pytest.mark.asyncio
    async def test_generate_report(self):
        """Test claim report generation."""
        tracker = ClaimTracker()
        
        await tracker.register_claim("Claim 1", source_stage=8, evidence=[])
        await tracker.register_claim("Claim 2", source_stage=8, evidence=[])
        
        report = tracker.generate_claim_report()
        
        assert report["total_claims"] == 2
        assert report["verification_rate"] == 0.0


class TestClassifiedWeakness:
    """Test ClassifiedWeakness model."""

    def test_create_classified_weakness(self):
        """Test creating classified weakness."""
        weakness = Weakness(
            category="experiments",
            description="Needs more baselines",
            severity=WeaknessSeverity.MINOR,
        )
        
        classified = ClassifiedWeakness(
            weakness=weakness,
            fix_type=FixType.NEW_EXPERIMENT,
            priority=5.0,
        )
        
        assert classified.fix_type == FixType.NEW_EXPERIMENT
        assert classified.priority == 5.0


class TestImprovementLoopConfig:
    """Test ImprovementLoopConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = ImprovementLoopConfig()
        assert config.max_rounds == 4
        assert config.score_threshold == 7.0
        assert config.max_loop_budget_usd == 1.0
        assert config.prefer_reframing is True


class TestAutonomousImprovementLoop:
    """Test AutonomousImprovementLoop."""

    def test_create_loop(self):
        """Test creating improvement loop."""
        loop = AutonomousImprovementLoop()
        assert loop.config.max_rounds == 4

    @pytest.mark.asyncio
    async def test_run_loop_disabled(self):
        """Test loop with disabled config."""
        config = ImprovementLoopConfig(enabled=False)
        loop = AutonomousImprovementLoop(config=config)
        
        result = await loop.run(
            paper="Test paper",
            reviewer=MagicMock(),
        )
        
        assert result.final_paper == "Test paper"
        assert len(result.score_progression.rounds) == 0

    @pytest.mark.asyncio
    async def test_classify_weaknesses(self):
        """Test weakness classification."""
        loop = AutonomousImprovementLoop()
        
        weaknesses = [
            Weakness(
                category="experiments",
                description="Needs more experiments",
                severity=WeaknessSeverity.MAJOR,
            ),
            Weakness(
                category="clarity",
                description="Unclear writing",
                severity=WeaknessSeverity.MINOR,
            ),
        ]
        
        classified = await loop._classify_weaknesses(weaknesses)
        
        assert len(classified) == 2
        assert all(c.priority > 0 for c in classified)

    def test_prioritize_fixes(self):
        """Test fix prioritization."""
        loop = AutonomousImprovementLoop()
        
        classified = [
            ClassifiedWeakness(
                weakness=Weakness(
                    category="clarity",
                    description="Minor issue",
                    severity=WeaknessSeverity.COSMETIC,
                ),
                fix_type=FixType.REWRITE,
                priority=1.0,
            ),
            ClassifiedWeakness(
                weakness=Weakness(
                    category="methods",
                    description="Critical flaw",
                    severity=WeaknessSeverity.CRITICAL,
                ),
                fix_type=FixType.REFRAME,
                priority=10.0,
            ),
        ]
        
        prioritized = loop._prioritize_fixes(classified)
        
        # Higher priority first
        assert prioritized[0].priority == 10.0
        assert prioritized[1].priority == 1.0


class TestComputeGuard:
    """Test ComputeGuard."""

    @pytest.mark.asyncio
    async def test_estimate_cost(self):
        """Test cost estimation."""
        guard = ComputeGuard(
            budget_remaining=10.0,
            time_remaining_minutes=120,
        )
        
        estimate = await guard.estimate_experiment_cost({
            "dataset_size": 10000,
            "num_configurations": 5,
            "epochs": 20,
            "gpu_required": True,
        })
        
        assert "gpu_hours" in estimate
        assert "api_cost" in estimate
        assert "wall_clock_minutes" in estimate

    @pytest.mark.asyncio
    async def test_should_run_within_budget(self):
        """Test should_run - within budget."""
        guard = ComputeGuard(
            budget_remaining=10.0,
            time_remaining_minutes=120,
        )
        
        should_run, reason = await guard.should_run({
            "gpu_hours": 2.0,
            "api_cost": 0.25,
            "wall_clock_minutes": 60,
        })
        
        assert should_run is True

    @pytest.mark.asyncio
    async def test_should_run_exceeds_budget(self):
        """Test should_run - exceeds budget."""
        guard = ComputeGuard(
            budget_remaining=1.0,
            time_remaining_minutes=120,
        )
        
        should_run, reason = await guard.should_run({
            "gpu_hours": 2.0,
            "api_cost": 1.0,
            "wall_clock_minutes": 60,
        })
        
        assert should_run is False
        assert "budget" in reason.lower()

    @pytest.mark.asyncio
    async def test_should_run_exceeds_time(self):
        """Test should_run - exceeds time."""
        guard = ComputeGuard(
            budget_remaining=10.0,
            time_remaining_minutes=30,
        )
        
        should_run, reason = await guard.should_run({
            "gpu_hours": 2.0,
            "api_cost": 0.25,
            "wall_clock_minutes": 120,
        })
        
        assert should_run is False
        assert "time" in reason.lower()

    @pytest.mark.asyncio
    async def test_should_run_exceeds_gpu_limit(self):
        """Test should_run - exceeds GPU limit."""
        guard = ComputeGuard(
            budget_remaining=10.0,
            time_remaining_minutes=300,
        )
        
        should_run, reason = await guard.should_run({
            "gpu_hours": 5.0,  # > 4hr limit
            "api_cost": 0.25,
            "wall_clock_minutes": 60,
        })
        
        assert should_run is False
        assert "GPU hours" in reason
        assert "4hr limit" in reason


class TestFixType:
    """Test FixType enum."""

    def test_fix_type_values(self):
        """Test fix type values."""
        assert FixType.REFRAME.value == "reframe"
        assert FixType.ADD_ANALYSIS.value == "add_analysis"
        assert FixType.NEW_EXPERIMENT.value == "new_experiment"
        assert FixType.REWRITE.value == "rewrite"
        assert FixType.ACKNOWLEDGE.value == "acknowledge"
        assert FixType.REMOVE.value == "remove"


class TestClaimVerdict:
    """Test ClaimVerdict enum."""

    def test_verdict_values(self):
        """Test verdict values."""
        assert ClaimVerdict.SUPPORTED.value == "supported"
        assert ClaimVerdict.WEAKENED.value == "weakened"
        assert ClaimVerdict.REFUTED.value == "refuted"
        assert ClaimVerdict.INCONCLUSIVE.value == "inconclusive"
