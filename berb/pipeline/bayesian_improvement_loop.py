"""Enhanced improvement loop with Iterative and Bayesian reasoning integration.

This module enhances the autonomous improvement loop by integrating:
1. Iterative (Research) reasoning for structured fix planning
2. Bayesian reasoning for quality belief updates and stop decisions

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from berb.llm.client import LLMProvider
from berb.reasoning.bayesian import BayesianMethod, BayesianResult, Hypothesis, Evidence
from berb.reasoning.research import ResearchMethod, ResearchResult
from berb.review.cross_model_reviewer import CrossModelReviewer, ReviewResult, Weakness
from berb.pipeline.improvement_loop import (
    AutonomousImprovementLoop,
    ImprovementLoopConfig,
    ImprovementResult,
    ScoreProgression,
    RoundResult,
    ClassifiedWeakness,
    FixType,
)

logger = logging.getLogger(__name__)


class BayesianImprovementConfig(ImprovementLoopConfig):
    """Enhanced improvement loop configuration with Bayesian reasoning.

    Attributes:
        use_bayesian_decision: Whether to use Bayesian decision making
        prior_quality_mean: Prior belief about paper quality (0-1)
        prior_quality_variance: Uncertainty in prior belief
        evidence_weight: How much to weight new evidence
        min_confidence_threshold: Minimum confidence to continue
        use_iterative_planning: Whether to use iterative fix planning
    """

    use_bayesian_decision: bool = True
    prior_quality_mean: float = Field(default=0.5, ge=0.0, le=1.0)
    prior_quality_variance: float = Field(default=0.3, ge=0.01)
    evidence_weight: float = Field(default=1.0, ge=0.1, le=5.0)
    min_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    use_iterative_planning: bool = True


@dataclass
class QualityBelief:
    """Belief distribution about paper quality.

    Attributes:
        mean: Mean quality estimate (0-1)
        variance: Uncertainty in estimate
        confidence: Confidence in estimate (1/variance)
        evidence_count: Number of evidence items observed
    """

    mean: float = 0.5
    variance: float = 0.3
    confidence: float = 0.0
    evidence_count: int = 0

    def update(
        self,
        new_evidence: float,
        evidence_confidence: float,
        weight: float = 1.0,
    ) -> "QualityBelief":
        """Update belief with new evidence using Bayesian update.

        Args:
            new_evidence: New quality evidence (0-1)
            evidence_confidence: Confidence in new evidence
            weight: Weight for new evidence

        Returns:
            Updated QualityBelief
        """
        # Precision (inverse variance)
        prior_precision = 1.0 / max(self.variance, 0.01)
        evidence_precision = evidence_confidence * weight

        # Weighted update
        total_precision = prior_precision + evidence_precision
        new_mean = (
            prior_precision * self.mean + evidence_precision * new_evidence
        ) / total_precision

        # New variance is inverse of total precision
        new_variance = 1.0 / total_precision

        return QualityBelief(
            mean=new_mean,
            variance=new_variance,
            confidence=total_precision,
            evidence_count=self.evidence_count + 1,
        )


class BayesianImprovementLoop(AutonomousImprovementLoop):
    """Improvement loop enhanced with Bayesian and Iterative reasoning.

    This loop uses:
    1. Bayesian reasoning for quality belief updates and stop decisions
    2. Iterative reasoning for structured fix planning and execution

    Usage::

        loop = BayesianImprovementLoop(
            config=BayesianImprovementConfig(
                max_rounds=4,
                score_threshold=7.0,
                use_bayesian_decision=True,
                use_iterative_planning=True,
            ),
        )

        result = await loop.run(paper, reviewer)

    Attributes:
        bayesian_method: Bayesian reasoning method
        iterative_method: Iterative reasoning method
        quality_belief: Current belief about paper quality
    """

    def __init__(
        self,
        config: BayesianImprovementConfig | None = None,
        llm_provider: LLMProvider | None = None,
    ):
        """Initialize Bayesian improvement loop.

        Args:
            config: Improvement loop configuration
            llm_provider: LLM provider for reasoning methods
        """
        super().__init__(config or BayesianImprovementConfig())

        self.config = config or BayesianImprovementConfig()
        self.llm_provider = llm_provider

        # Initialize reasoning methods
        self.bayesian_method = BayesianMethod(llm_provider) if llm_provider else None
        self.iterative_method = ResearchMethod(llm_provider) if llm_provider else None

        # Bayesian state
        self.quality_belief = QualityBelief(
            mean=self.config.prior_quality_mean,
            variance=self.config.prior_quality_variance,
        )

    async def run(
        self,
        paper: str,
        reviewer: CrossModelReviewer,
        initial_review: ReviewResult | None = None,
    ) -> ImprovementResult:
        """Run improvement loop with Bayesian decision making.

        Args:
            paper: Initial paper text
            reviewer: Cross-model reviewer
            initial_review: Optional initial review

        Returns:
            ImprovementResult with final paper and metrics
        """
        if not self.config.enabled:
            return ImprovementResult(
                final_paper=paper,
                score_progression=ScoreProgression(),
            )

        import time
        from datetime import datetime, timezone

        start_time = datetime.now(timezone.utc)
        score_progression = ScoreProgression()
        all_fixes = []
        claims_killed = []
        total_cost = 0.0

        current_paper = paper
        prior_review = initial_review

        # Reset quality belief
        self.quality_belief = QualityBelief(
            mean=self.config.prior_quality_mean,
            variance=self.config.prior_quality_variance,
        )

        # Get initial review if not provided
        if prior_review is None:
            logger.info("Generating initial review...")
            prior_review = await reviewer.review(current_paper)
            score_progression.initial_score = prior_review.overall_score

            # Update belief with initial review
            self.quality_belief = self.quality_belief.update(
                new_evidence=prior_review.overall_score / 10.0,
                evidence_confidence=prior_review.confidence,
                weight=self.config.evidence_weight,
            )

        logger.info(
            f"Initial score: {prior_review.overall_score:.1f}, "
            f"threshold: {self.config.score_threshold}, "
            f"quality belief: {self.quality_belief.mean:.2f} ± {math.sqrt(self.quality_belief.variance):.2f}"
        )

        # Improvement rounds
        for round_num in range(1, self.config.max_rounds + 1):
            round_start = time.time()

            # Bayesian decision: continue or stop?
            should_continue = self._bayesian_decision(round_num)
            if not should_continue:
                logger.info(
                    f"Bayesian decision: stopping at round {round_num} "
                    f"(quality={self.quality_belief.mean:.2f}, confidence={self.quality_belief.confidence:.2f})"
                )
                score_progression.stopped_early = True
                score_progression.stop_reason = "bayesian_decision"
                break

            # Check score threshold
            if prior_review.overall_score >= self.config.score_threshold:
                logger.info(f"Score threshold met")
                score_progression.stopped_early = True
                score_progression.stop_reason = "score_threshold_met"
                break

            logger.info(f"Starting improvement round {round_num}/{self.config.max_rounds}")

            # Classify weaknesses
            classified = await self._classify_weaknesses(prior_review.weaknesses)

            # Use iterative reasoning for fix planning
            if self.config.use_iterative_planning and self.iterative_method:
                fix_plan = await self._iterative_fix_planning(
                    weaknesses=classified,
                    remaining_rounds=self.config.max_rounds - round_num,
                )
                prioritized = fix_plan
            else:
                # Use default prioritization
                prioritized = self._prioritize_fixes(classified)

            # Apply fixes
            fixes_applied = []
            round_cost = 0.0

            for weakness_class in prioritized[:5]:  # Top 5 fixes
                # Check if fix is affordable
                fix_cost = self._fix_costs.get(
                    weakness_class.fix_type,
                    {"cost": 0.10, "time": 10},
                )

                if total_cost + fix_cost["cost"] > self.config.max_loop_budget_usd:
                    if self.config.skip_expensive_fixes:
                        continue

                # Apply fix
                fix_result = await self._apply_fix(
                    weakness=weakness_class.weakness,
                    fix_type=weakness_class.fix_type,
                    paper=current_paper,
                    round_num=round_num,
                )

                if fix_result["success"]:
                    current_paper = fix_result["new_paper"]
                    fixes_applied.append(fix_result["description"])
                    all_fixes.append(fix_result["description"])
                    round_cost += fix_cost["cost"]

                    if weakness_class.fix_type == FixType.REMOVE:
                        claims_killed.append(weakness_class.weakness.description)
                        score_progression.claims_killed += 1

            round_time = (time.time() - round_start) / 60  # minutes
            total_cost += round_cost

            # Re-review
            logger.info(f"Round {round_num} complete - {len(fixes_applied)} fixes applied")
            new_review = await reviewer.review(
                current_paper,
                prior_review=prior_review,
            )

            # Bayesian update with new evidence
            self.quality_belief = self.quality_belief.update(
                new_evidence=new_review.overall_score / 10.0,
                evidence_confidence=new_review.confidence,
                weight=self.config.evidence_weight,
            )

            # Compare with prior
            delta = reviewer.compare_with_prior(new_review, prior_review)

            # Record round result
            round_result = RoundResult(
                round_number=round_num,
                review=new_review,
                fixes_applied=fixes_applied,
                cost_usd=round_cost,
                time_minutes=round_time,
                score=new_review.overall_score,
            )
            score_progression.rounds.append(round_result)
            score_progression.total_improvements += len(fixes_applied)

            logger.info(
                f"Round {round_num}: score {prior_review.overall_score:.1f} → {new_review.overall_score:.1f} "
                f"({delta.score_change:+.2f}), quality belief: {self.quality_belief.mean:.2f}"
            )

            # Update for next round
            prior_review = new_review

        # Calculate final metrics
        end_time = datetime.now(timezone.utc)
        total_time = (end_time - start_time).total_seconds() / 60

        score_progression.final_score = prior_review.overall_score
        score_progression.total_cost_usd = total_cost
        score_progression.total_time_minutes = total_time

        return ImprovementResult(
            final_paper=current_paper,
            score_progression=score_progression,
            all_fixes=all_fixes,
            claims_killed=claims_killed,
            total_cost_usd=total_cost,
            total_time_minutes=total_time,
            passed_threshold=prior_review.overall_score >= self.config.score_threshold,
            stopped_early=getattr(score_progression, "stopped_early", False),
            stop_reason=getattr(score_progression, "stop_reason", ""),
        )

    def _bayesian_decision(self, round_num: int) -> bool:
        """Make Bayesian decision about whether to continue.

        Args:
            round_num: Current round number

        Returns:
            True if should continue
        """
        if not self.config.use_bayesian_decision:
            return True

        # Calculate probability that quality >= threshold
        threshold_normalized = self.config.score_threshold / 10.0

        # Z-score for threshold
        z = (threshold_normalized - self.quality_belief.mean) / math.sqrt(
            max(self.quality_belief.variance, 0.001)
        )

        # Probability that quality >= threshold (using normal CDF approximation)
        prob_above_threshold = 1.0 - self._normal_cdf(z)

        # Decision rule: continue if P(quality >= threshold) < min_confidence
        should_continue = (
            prob_above_threshold < self.config.min_confidence_threshold
            and round_num < self.config.max_rounds
        )

        logger.debug(
            f"Bayesian decision: P(quality>={threshold_normalized:.1f})={prob_above_threshold:.2f}, "
            f"continue={should_continue}"
        )

        return should_continue

    def _normal_cdf(self, x: float) -> float:
        """Approximate normal CDF.

        Args:
            x: Z-score

        Returns:
            CDF value
        """
        # Approximation using error function
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    async def _iterative_fix_planning(
        self,
        weaknesses: list[ClassifiedWeakness],
        remaining_rounds: int,
    ) -> list[ClassifiedWeakness]:
        """Use iterative reasoning to plan fixes.

        Args:
            weaknesses: Classified weaknesses
            remaining_rounds: Remaining improvement rounds

        Returns:
            Prioritized list of fixes
        """
        if not self.iterative_method:
            return self._prioritize_fixes(weaknesses)

        # Build problem statement
        problem = f"""Plan fixes for {len(weaknesses)} weaknesses over {remaining_rounds} rounds.

Weaknesses:
"""
        for i, w in enumerate(weaknesses[:10]):
            problem += f"{i+1}. [{w.weakness.severity.value}] {w.weakness.category}: {w.weakness.description[:100]}\n"

        problem += """
Prioritize by:
1. Severity (critical > major > minor > cosmetic)
2. Fix cost (cheap first)
3. Impact on overall quality
4. Dependencies between fixes

Output a prioritized list with reasoning."""

        # Execute iterative reasoning
        from berb.reasoning.base import ReasoningContext

        context = ReasoningContext(
            stage_id="IMPROVEMENT_PLANNING",
            stage_name="Improvement Planning",
            input_data={"problem": problem},
        )

        try:
            result = await self.iterative_method.execute(context)

            # Parse result to adjust priorities
            # For now, use default prioritization
            logger.debug("Iterative fix planning complete")

        except Exception as e:
            logger.warning(f"Iterative fix planning failed: {e}")

        # Fall back to default prioritization
        return self._prioritize_fixes(weaknesses)

    async def _bayesian_quality_assessment(
        self,
        paper: str,
        review: ReviewResult,
    ) -> QualityBelief:
        """Use Bayesian reasoning to assess paper quality.

        Args:
            paper: Paper text
            review: Review result

        Returns:
            Updated QualityBelief
        """
        if not self.bayesian_method:
            # Use simple update
            return self.quality_belief.update(
                new_evidence=review.overall_score / 10.0,
                evidence_confidence=review.confidence,
            )

        # Define hypotheses about paper quality
        hypotheses = [
            Hypothesis(
                name="high_quality",
                prior=0.3,
                description="Paper is high quality (score >= 8)",
            ),
            Hypothesis(
                name="medium_quality",
                prior=0.5,
                description="Paper is medium quality (6 <= score < 8)",
            ),
            Hypothesis(
                name="low_quality",
                prior=0.2,
                description="Paper is low quality (score < 6)",
            ),
        ]

        # Define evidence from review
        evidence = Evidence(
            name="review_score",
            description=f"Review score: {review.overall_score}/10",
            likelihood_given_h={
                "high_quality": 0.9 if review.overall_score >= 8 else 0.3,
                "medium_quality": 0.7 if 6 <= review.overall_score < 8 else 0.2,
                "low_quality": 0.8 if review.overall_score < 6 else 0.1,
            },
        )

        # Execute Bayesian reasoning
        from berb.reasoning.base import ReasoningContext

        context = ReasoningContext(
            stage_id="QUALITY_ASSESSMENT",
            stage_name="Quality Assessment",
            input_data={
                "hypotheses": hypotheses,
                "evidence": [evidence],
            },
        )

        try:
            result = await self.bayesian_method.execute(context)

            # Extract posteriors
            if isinstance(result.output, dict) and "posteriors" in result.output:
                posteriors = result.output["posteriors"]
                # Update belief based on posterior probabilities
                # (Simplified - would use full posterior distribution)

        except Exception as e:
            logger.warning(f"Bayesian quality assessment failed: {e}")

        # Fall back to simple update
        return self.quality_belief.update(
            new_evidence=review.overall_score / 10.0,
            evidence_confidence=review.confidence,
        )


class IterativeFixPlanner:
    """Specialized planner for iterative improvement.

    This planner uses the Iterative reasoning method to:
    1. Analyze weaknesses
    2. Plan fix sequence
    3. Identify dependencies
    4. Estimate cumulative impact

    Attributes:
        iterative_method: Iterative reasoning method
    """

    def __init__(self, llm_provider: LLMProvider):
        """Initialize fix planner.

        Args:
            llm_provider: LLM provider
        """
        self.iterative_method = ResearchMethod(llm_provider)

    async def plan(
        self,
        weaknesses: list[Weakness],
        remaining_rounds: int,
        budget_remaining: float,
    ) -> list[ClassifiedWeakness]:
        """Plan fix sequence.

        Args:
            weaknesses: List of weaknesses
            remaining_rounds: Remaining improvement rounds
            budget_remaining: Remaining budget

        Returns:
            Prioritized list of classified weaknesses
        """
        # Build planning problem
        problem = self._build_planning_problem(
            weaknesses, remaining_rounds, budget_remaining
        )

        # Execute iterative reasoning
        from berb.reasoning.base import ReasoningContext

        context = ReasoningContext(
            stage_id="FIX_PLANNING",
            stage_name="Fix Planning",
            input_data={"problem": problem},
        )

        result = await self.iterative_method.execute(context)

        # Parse result into prioritized list
        return self._parse_plan(result, weaknesses)

    def _build_planning_problem(
        self,
        weaknesses: list[Weakness],
        rounds: int,
        budget: float,
    ) -> str:
        """Build planning problem statement.

        Args:
            weaknesses: List of weaknesses
            rounds: Remaining rounds
            budget: Remaining budget

        Returns:
            Problem statement
        """
        problem = f"""Plan an improvement strategy for this paper.

Constraints:
- Rounds remaining: {rounds}
- Budget remaining: ${budget:.2f}

Weaknesses to address:
"""
        for i, w in enumerate(weaknesses[:15]):
            problem += f"{i+1}. [{w.severity.value}] {w.category}: {w.description[:80]}\n"

        problem += """
Output a prioritized plan with:
1. Which weaknesses to address first
2. Estimated cost per fix
3. Expected quality improvement
4. Dependencies between fixes
"""
        return problem

    def _parse_plan(
        self,
        result: ResearchResult,
        weaknesses: list[Weakness],
    ) -> list[ClassifiedWeakness]:
        """Parse planning result into prioritized list.

        Args:
            result: Research result from iterative reasoning
            weaknesses: Original weaknesses

        Returns:
            Prioritized ClassifiedWeaknesses
        """
        # For now, return default classification
        # In production, would parse LLM output
        classified = []

        for w in weaknesses:
            classified.append(
                ClassifiedWeakness(
                    weakness=w,
                    fix_type=self._recommend_fix(w),
                    priority=1.0,  # Would calculate from plan
                )
            )

        return classified

    def _recommend_fix(self, weakness: Weakness) -> FixType:
        """Recommend fix type for weakness.

        Args:
            weakness: Weakness

        Returns:
            Recommended FixType
        """
        # Same logic as parent class
        if weakness.category == "experiments":
            return FixType.REFRAME
        elif weakness.category == "clarity":
            return FixType.REWRITE
        else:
            return FixType.ACKNOWLEDGE
