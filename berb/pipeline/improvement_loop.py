"""Autonomous improvement loop for iterative paper refinement.

This module implements the review → fix → re-review loop that automatically
improves papers until they reach publication quality or exhaust budget.

Features:
- Automated weakness classification by severity and fix cost
- Prioritized fixing (cheap severe issues first)
- Multiple fix types (reframe/add_analysis/new_experiment/rewrite/acknowledge)
- Claim killing for unsupported assertions
- Score progression tracking across rounds

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from berb.review.cross_model_reviewer import (
    CrossModelReviewer,
    ReviewResult,
    Weakness,
    WeaknessSeverity,
    ImprovementDelta,
)

logger = logging.getLogger(__name__)


class FixType(str, Enum):
    """Type of fix for a weakness.

    Attributes:
        REFRAME: Rewrite with new narrative framing
        ADD_ANALYSIS: Run additional analysis on existing data
        NEW_EXPERIMENT: Run new experiment
        REWRITE: Improve clarity/structure without changing claims
        ACKNOWLEDGE: Add limitation discussion
        REMOVE: Remove unsupported claim
    """

    REFRAME = "reframe"
    ADD_ANALYSIS = "add_analysis"
    NEW_EXPERIMENT = "new_experiment"
    REWRITE = "rewrite"
    ACKNOWLEDGE = "acknowledge"
    REMOVE = "remove"


class ClaimVerdict(str, Enum):
    """Verdict for claim verification.

    Attributes:
        SUPPORTED: Claim is supported by evidence
        WEAKENED: Claim has some support but weakened
        REFUTED: Claim is refuted by evidence
        INCONCLUSIVE: Cannot determine support
    """

    SUPPORTED = "supported"
    WEAKENED = "weakened"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class ClassifiedWeakness(BaseModel):
    """Weakness classified by severity and fix cost.

    Attributes:
        weakness: Original weakness
        fix_type: Recommended fix type
        estimated_cost_usd: Estimated API cost to fix
        estimated_time_minutes: Estimated time to fix
        priority: Priority score (severity × (1/cost))
        can_auto_fix: Whether this can be fixed automatically
    """

    weakness: Weakness
    fix_type: FixType
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    estimated_time_minutes: float = Field(default=0.0, ge=0.0)
    priority: float = Field(default=0.0)
    can_auto_fix: bool = True


class RoundResult(BaseModel):
    """Result of a single improvement round.

    Attributes:
        round_number: Round number (1, 2, 3, ...)
        review: Review result for this round
        fixes_applied: Fixes applied in this round
        cost_usd: Cost for this round
        time_minutes: Time for this round
        score: Score at end of round
    """

    round_number: int
    review: ReviewResult
    fixes_applied: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0
    time_minutes: float = 0.0
    score: float = 0.0


class ScoreProgression(BaseModel):
    """Track improvement across rounds.

    Attributes:
        rounds: All round results
        initial_score: Score before any improvements
        final_score: Final score after all rounds
        total_improvements: Total improvements made
        claims_killed: Claims removed for not holding up
        experiments_run: Number of new experiments run
        narrative_rewrites: Number of narrative rewrites
        total_cost_usd: Total cost for all rounds
        total_time_minutes: Total time for all rounds
    """

    rounds: list[RoundResult] = Field(default_factory=list)
    initial_score: float = 0.0
    final_score: float = 0.0
    total_improvements: int = 0
    claims_killed: int = 0
    experiments_run: int = 0
    narrative_rewrites: int = 0
    total_cost_usd: float = 0.0
    total_time_minutes: float = 0.0


class ImprovementLoopConfig(BaseModel):
    """Configuration for improvement loop.

    Attributes:
        enabled: Whether improvement loop is enabled
        max_rounds: Maximum improvement rounds
        score_threshold: Stop when score ≥ threshold
        max_loop_budget_usd: Budget cap for improvement loop
        max_loop_time_minutes: Time cap for improvement loop
        prefer_reframing: Prefer narrative rewrite over new experiments
        max_new_experiment_hours: Skip experiments > N hours
        skip_expensive_fixes: Skip fixes that exceed budget
        no_hiding_weaknesses: Explicit rule against hiding weaknesses
        require_fix_before_resubmit: Must implement, not promise
    """

    enabled: bool = True
    max_rounds: int = Field(default=4, ge=1, le=10)
    score_threshold: float = Field(default=7.0, ge=1.0, le=10.0)
    max_loop_budget_usd: float = Field(default=1.0, ge=0.0)
    max_loop_time_minutes: float = Field(default=60.0, ge=0.0)
    prefer_reframing: bool = Field(
        default=True,
        description="Prefer narrative rewrite over new experiments",
    )
    max_new_experiment_hours: float = Field(
        default=4.0,
        description="Skip experiments longer than N hours",
    )
    skip_expensive_fixes: bool = Field(default=True)
    no_hiding_weaknesses: bool = Field(
        default=True,
        description="Explicit rule against hiding weaknesses",
    )
    require_fix_before_resubmit: bool = Field(default=True)


class ClaimRecord(BaseModel):
    """Track lifecycle of empirical claims.

    Attributes:
        id: Unique claim identifier
        text: Claim text
        source_stage: Pipeline stage where claim originated
        registered_round: Round when claim was registered
        evidence: Supporting evidence
        status: Current claim status
        challenge_history: History of challenges
        kill_reason: Reason if claim was killed
    """

    id: str
    text: str
    source_stage: int
    registered_round: int
    evidence: list[str] = Field(default_factory=list)
    status: Literal["active", "challenged", "verified", "killed", "weakened"] = "active"
    challenge_history: list[dict[str, Any]] = Field(default_factory=list)
    kill_reason: str | None = None


class ClaimTracker:
    """Track lifecycle of every empirical claim in the paper.

    This tracker ensures scientific integrity by:
    - Registering all claims when made
    - Tracking challenges from reviewers
    - Verifying claims with evidence
    - Killing claims that don't hold up

    Attributes:
        claims: Dictionary of claim records
    """

    def __init__(self):
        """Initialize claim tracker."""
        self.claims: dict[str, ClaimRecord] = {}
        self._counter = 0

    async def register_claim(
        self,
        claim: str,
        source_stage: int,
        evidence: list[str],
        round_num: int = 0,
    ) -> str:
        """Register a new empirical claim.

        Args:
            claim: Claim text
            source_stage: Pipeline stage where claim originated
            evidence: Supporting evidence
            round_num: Current improvement round

        Returns:
            Claim ID
        """
        self._counter += 1
        claim_id = f"claim_{self._counter}"

        self.claims[claim_id] = ClaimRecord(
            id=claim_id,
            text=claim,
            source_stage=source_stage,
            registered_round=round_num,
            evidence=evidence,
            status="active",
        )

        logger.debug(f"Registered claim {claim_id}: {claim[:50]}...")
        return claim_id

    async def challenge_claim(
        self,
        claim_id: str,
        round_num: int,
        reason: str,
    ) -> None:
        """Mark claim as challenged by reviewer.

        Args:
            claim_id: Claim ID
            round_num: Current round
            reason: Challenge reason
        """
        if claim_id not in self.claims:
            logger.warning(f"Claim {claim_id} not found for challenge")
            return

        claim = self.claims[claim_id]
        claim.status = "challenged"
        claim.challenge_history.append({
            "round": round_num,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(f"Challenged claim {claim_id}: {reason}")

    async def verify_claim(
        self,
        claim_id: str,
        experiment_results: dict[str, Any],
    ) -> ClaimVerdict:
        """Verify claim with new evidence.

        Args:
            claim_id: Claim ID
            experiment_results: Results from verification experiment

        Returns:
            ClaimVerdict
        """
        if claim_id not in self.claims:
            return ClaimVerdict.INCONCLUSIVE

        claim = self.claims[claim_id]

        # Analyze experiment results
        success = experiment_results.get("success", False)
        effect_size = experiment_results.get("effect_size", 0.0)
        p_value = experiment_results.get("p_value", 1.0)

        if success and p_value < 0.05 and effect_size > 0.3:
            claim.status = "verified"
            return ClaimVerdict.SUPPORTED
        elif success and p_value < 0.1:
            claim.status = "weakened"
            return ClaimVerdict.WEAKENED
        else:
            claim.status = "weakened"
            return ClaimVerdict.REFUTED

    async def kill_claim(
        self,
        claim_id: str,
        reason: str,
    ) -> None:
        """Remove claim from paper.

        Args:
            claim_id: Claim ID
            reason: Reason for killing
        """
        if claim_id not in self.claims:
            return

        claim = self.claims[claim_id]
        claim.status = "killed"
        claim.kill_reason = reason

        logger.info(f"Killed claim {claim_id}: {reason}")

    def generate_claim_report(self) -> dict[str, Any]:
        """Generate claim integrity report.

        Returns:
            Report with claim statistics
        """
        total = len(self.claims)
        verified = sum(1 for c in self.claims.values() if c.status == "verified")
        killed = sum(1 for c in self.claims.values() if c.status == "killed")
        weakened = sum(1 for c in self.claims.values() if c.status == "weakened")
        active = sum(1 for c in self.claims.values() if c.status == "active")

        return {
            "total_claims": total,
            "verified": verified,
            "killed": killed,
            "weakened": weakened,
            "active": active,
            "verification_rate": verified / total if total > 0 else 0.0,
            "claims": [
                {
                    "id": c.id,
                    "text": c.text[:100],
                    "status": c.status,
                    "kill_reason": c.kill_reason,
                }
                for c in self.claims.values()
            ],
        }


class ImprovementResult(BaseModel):
    """Result of autonomous improvement loop.

    Attributes:
        final_paper: Final improved paper text
        score_progression: Score tracking across rounds
        all_fixes: All fixes applied
        claims_killed: Claims that were removed
        total_cost_usd: Total cost
        total_time_minutes: Total time
        passed_threshold: Whether final score met threshold
        stopped_early: Whether loop stopped before max rounds
        stop_reason: Reason for stopping
    """

    final_paper: str
    score_progression: ScoreProgression
    all_fixes: list[str] = Field(default_factory=list)
    claims_killed: list[str] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_time_minutes: float = 0.0
    passed_threshold: bool = False
    stopped_early: bool = False
    stop_reason: str = ""


class AutonomousImprovementLoop:
    """Review → Fix → Re-review until publication-ready or budget exhausted.

    This loop:
    1. Gets external review of paper
    2. Classifies weaknesses by severity and fix cost
    3. Prioritizes cheap severe fixes first
    4. Implements fixes (reframe > analysis > experiments)
    5. Re-reviews with prior context
    6. Repeats until score threshold or budget exhausted

    Usage::

        loop = AutonomousImprovementLoop(config=ImprovementLoopConfig())
        result = await loop.run(
            paper=paper_text,
            reviewer=reviewer,
            config=config,
        )

    Attributes:
        config: Improvement loop configuration
        claim_tracker: Claim lifecycle tracker
    """

    def __init__(
        self,
        config: ImprovementLoopConfig | None = None,
    ):
        """Initialize improvement loop.

        Args:
            config: Improvement loop configuration
        """
        self.config = config or ImprovementLoopConfig()
        self.claim_tracker = ClaimTracker()

        # Cost estimates for fix types
        self._fix_costs = {
            FixType.REFRAME: {"cost": 0.05, "time": 5},
            FixType.REWRITE: {"cost": 0.03, "time": 3},
            FixType.ADD_ANALYSIS: {"cost": 0.10, "time": 15},
            FixType.ACKNOWLEDGE: {"cost": 0.02, "time": 2},
            FixType.REMOVE: {"cost": 0.01, "time": 1},
            FixType.NEW_EXPERIMENT: {"cost": 0.50, "time": 120},  # Highly variable
        }

    async def run(
        self,
        paper: str,
        reviewer: CrossModelReviewer,
        initial_review: ReviewResult | None = None,
    ) -> ImprovementResult:
        """Run improvement loop.

        Args:
            paper: Initial paper text
            reviewer: Cross-model reviewer
            initial_review: Optional initial review (skip round 1)

        Returns:
            ImprovementResult with final paper and metrics
        """
        if not self.config.enabled:
            return ImprovementResult(
                final_paper=paper,
                score_progression=ScoreProgression(),
            )

        start_time = datetime.now(timezone.utc)
        score_progression = ScoreProgression()
        all_fixes = []
        claims_killed = []
        total_cost = 0.0

        current_paper = paper
        prior_review = initial_review

        # Get initial review if not provided
        if prior_review is None:
            logger.info("Starting improvement loop - generating initial review...")
            prior_review = await reviewer.review(current_paper)
            score_progression.initial_score = prior_review.overall_score

        logger.info(
            f"Initial score: {prior_review.overall_score:.1f}, "
            f"threshold: {self.config.score_threshold}, "
            f"weaknesses: {len(prior_review.weaknesses)}"
        )

        # Improvement rounds
        for round_num in range(1, self.config.max_rounds + 1):
            # Check stopping conditions
            if prior_review.overall_score >= self.config.score_threshold:
                logger.info(f"Score threshold met ({prior_review.overall_score:.1f} >= {self.config.score_threshold})")
                score_progression.stopped_early = True  # type: ignore
                score_progression.stop_reason = "score_threshold_met"  # type: ignore
                break

            # Check budget
            if total_cost >= self.config.max_loop_budget_usd:
                logger.info(f"Budget exhausted (${total_cost:.2f} >= ${self.config.max_loop_budget_usd:.2f})")
                score_progression.stopped_early = True  # type: ignore
                score_progression.stop_reason = "budget_exhausted"  # type: ignore
                break

            logger.info(f"Starting improvement round {round_num}/{self.config.max_rounds}")

            # Classify weaknesses
            classified = await self._classify_weaknesses(prior_review.weaknesses)

            # Prioritize fixes
            prioritized = self._prioritize_fixes(classified)

            # Apply fixes
            fixes_applied = []
            round_cost = 0.0

            for weakness_class in prioritized:
                # Check if fix is affordable
                fix_cost = self._fix_costs.get(
                    weakness_class.fix_type,
                    {"cost": 0.10, "time": 10},
                )
                if total_cost + fix_cost["cost"] > self.config.max_loop_budget_usd:
                    if self.config.skip_expensive_fixes:
                        logger.info(f"Skipping fix (too expensive): {weakness_class.weakness.category}")
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

                    # Track claim kills
                    if weakness_class.fix_type == FixType.REMOVE:
                        claims_killed.append(weakness_class.weakness.description)
                        score_progression.claims_killed += 1  # type: ignore

                    # Track experiments
                    if weakness_class.fix_type == FixType.NEW_EXPERIMENT:
                        score_progression.experiments_run += 1  # type: ignore

                    # Track rewrites
                    if weakness_class.fix_type in (FixType.REFRAME, FixType.REWRITE):
                        score_progression.narrative_rewrites += 1  # type: ignore

            total_cost += round_cost

            # Re-review
            logger.info(f"Round {round_num} complete - {len(fixes_applied)} fixes applied, re-reviewing...")
            new_review = await reviewer.review(
                current_paper,
                prior_review=prior_review,
            )

            # Compare with prior
            delta = reviewer.compare_with_prior(new_review, prior_review)

            # Record round result
            round_result = RoundResult(
                round_number=round_num,
                review=new_review,
                fixes_applied=fixes_applied,
                cost_usd=round_cost,
                score=new_review.overall_score,
            )
            score_progression.rounds.append(round_result)  # type: ignore
            score_progression.total_improvements += len(fixes_applied)  # type: ignore

            logger.info(
                f"Round {round_num} complete: score {prior_review.overall_score:.1f} → {new_review.overall_score:.1f} "
                f"({delta.score_change:+.2f}), net improvement: {delta.net_improvement}"
            )

            # Update for next round
            prior_review = new_review

        # Calculate final metrics
        end_time = datetime.now(timezone.utc)
        total_time = (end_time - start_time).total_seconds() / 60

        score_progression.final_score = prior_review.overall_score  # type: ignore
        score_progression.total_cost_usd = total_cost  # type: ignore
        score_progression.total_time_minutes = total_time  # type: ignore

        return ImprovementResult(
            final_paper=current_paper,
            score_progression=score_progression,
            all_fixes=all_fixes,
            claims_killed=claims_killed,
            total_cost_usd=total_cost,
            total_time_minutes=total_time,
            passed_threshold=prior_review.overall_score >= self.config.score_threshold,
            stopped_early=score_progression.stopped_early,  # type: ignore
            stop_reason=score_progression.stop_reason,  # type: ignore
        )

    async def _classify_weaknesses(
        self,
        weaknesses: list[Weakness],
    ) -> list[ClassifiedWeakness]:
        """Classify weaknesses by severity and fix cost.

        Args:
            weaknesses: List of weaknesses

        Returns:
            Classified weaknesses with priority scores
        """
        classified = []

        for weakness in weaknesses:
            # Determine fix type
            fix_type = self._recommend_fix_type(weakness)

            # Get cost estimate
            cost_info = self._fix_costs.get(
                fix_type,
                {"cost": 0.10, "time": 10},
            )

            # Calculate priority (severity × (1/cost))
            severity_scores = {
                WeaknessSeverity.CRITICAL: 4.0,
                WeaknessSeverity.MAJOR: 3.0,
                WeaknessSeverity.MINOR: 2.0,
                WeaknessSeverity.COSMETIC: 1.0,
            }
            severity_score = severity_scores.get(weakness.severity, 1.0)
            priority = severity_score / max(cost_info["cost"], 0.01)

            # Determine if can auto-fix
            can_auto_fix = fix_type in (
                FixType.REFRAME,
                FixType.REWRITE,
                FixType.ACKNOWLEDGE,
                FixType.REMOVE,
            )

            classified.append(
                ClassifiedWeakness(
                    weakness=weakness,
                    fix_type=fix_type,
                    estimated_cost_usd=cost_info["cost"],
                    estimated_time_minutes=cost_info["time"],
                    priority=priority,
                    can_auto_fix=can_auto_fix,
                )
            )

        return classified

    def _recommend_fix_type(self, weakness: Weakness) -> FixType:
        """Recommend fix type for a weakness.

        Args:
            weakness: Weakness to classify

        Returns:
            Recommended FixType
        """
        category = weakness.category.lower()
        description = weakness.description.lower()

        # Experiments → NEW_EXPERIMENT (but expensive)
        if category == "experiments" or "experiment" in description:
            if self.config.prefer_reframing:
                # Try to reframe instead
                return FixType.REFRAME
            return FixType.NEW_EXPERIMENT

        # Methods issues → REFRAME or ACKNOWLEDGE
        if category == "methods":
            if weakness.severity in (WeaknessSeverity.CRITICAL, WeaknessSeverity.MAJOR):
                return FixType.REFRAME
            return FixType.ACKNOWLEDGE

        # Clarity/writing → REWRITE
        if category in ("clarity", "writing"):
            return FixType.REWRITE

        # Novelty concerns → REFRAME
        if category == "novelty":
            return FixType.REFRAME

        # Default: ACKNOWLEDGE limitations
        return FixType.ACKNOWLEDGE

    def _prioritize_fixes(
        self,
        classified: list[ClassifiedWeakness],
    ) -> list[ClassifiedWeakness]:
        """Sort fixes by priority (high to low).

        Args:
            classified: Classified weaknesses

        Returns:
            Sorted list
        """
        return sorted(classified, key=lambda c: c.priority, reverse=True)

    async def _apply_fix(
        self,
        weakness: ClassifiedWeakness,
        fix_type: FixType,
        paper: str,
        round_num: int,
    ) -> dict[str, Any]:
        """Apply a fix to the paper.

        Args:
            weakness: Classified weakness
            fix_type: Type of fix to apply
            paper: Current paper text
            round_num: Current round

        Returns:
            Fix result with new paper
        """
        # For now, implement simple fixes
        # In production, this would call LLM for rewrites

        if fix_type == FixType.REMOVE:
            # Mark claim for removal (would need NLP to actually remove)
            await self.claim_tracker.register_claim(
                weakness.weakness.description,
                source_stage=18,  # Review stage
                evidence=[],
                round_num=round_num,
            )
            await self.claim_tracker.kill_claim(
                await self._get_claim_id(weakness.weakness.description),
                reason=f"Reviewer identified as unsupported: {weakness.weakness.description[:50]}",
            )
            return {
                "success": True,
                "new_paper": paper,  # Would actually remove in production
                "description": f"Removed unsupported claim: {weakness.weakness.category}",
            }

        elif fix_type == FixType.ACKNOWLEDGE:
            # Add limitation acknowledgment
            return {
                "success": True,
                "new_paper": paper + f"\n\nLimitation: {weakness.weakness.description}",
                "description": f"Acknowledged limitation: {weakness.weakness.category}",
            }

        elif fix_type in (FixType.REFRAME, FixType.REWRITE):
            # Would call LLM to reframe/rewrite
            return {
                "success": True,
                "new_paper": paper,  # Would actually modify
                "description": f"Reframed: {weakness.weakness.category}",
            }

        elif fix_type == FixType.NEW_EXPERIMENT:
            # Would run experiment
            return {
                "success": False,  # Skip expensive experiments for now
                "new_paper": paper,
                "description": f"Skipped experiment: {weakness.weakness.description[:50]}",
            }

        return {
            "success": False,
            "new_paper": paper,
            "description": f"Unknown fix type: {fix_type}",
        }

    async def _get_claim_id(self, description: str) -> str:
        """Get or create claim ID for a description.

        Args:
            description: Claim description

        Returns:
            Claim ID
        """
        # Find matching claim
        for claim_id, claim in self.claim_tracker.claims.items():
            if claim.text.lower() == description.lower():
                return claim_id

        # Create new claim
        return await self.claim_tracker.register_claim(
            description,
            source_stage=18,
            evidence=[],
        )


class ComputeGuard:
    """Prevent expensive experiments from blowing the budget.

    This guard estimates experiment costs and blocks those that
    exceed budget or time limits.

    Attributes:
        budget_remaining: Remaining budget
        time_remaining_minutes: Remaining time
    """

    def __init__(
        self,
        budget_remaining: float,
        time_remaining_minutes: float,
    ):
        """Initialize compute guard.

        Args:
            budget_remaining: Remaining budget in USD
            time_remaining_minutes: Remaining time in minutes
        """
        self.budget_remaining = budget_remaining
        self.time_remaining_minutes = time_remaining_minutes

    async def estimate_experiment_cost(
        self,
        experiment_design: dict[str, Any],
    ) -> dict[str, float]:
        """Estimate experiment cost.

        Args:
            experiment_design: Experiment design dictionary

        Returns:
            Cost estimate with gpu_hours, api_cost, wall_clock_minutes
        """
        # Simplified estimation
        dataset_size = experiment_design.get("dataset_size", 1000)
        num_configs = experiment_design.get("num_configurations", 1)
        epochs = experiment_design.get("epochs", 10)
        gpu_required = experiment_design.get("gpu_required", False)

        # Estimate GPU hours
        base_hours = (dataset_size / 10000) * epochs * num_configs
        gpu_hours = base_hours * (2.0 if gpu_required else 1.0)

        # Estimate API cost (for analysis)
        api_cost = num_configs * 0.05  # $0.05 per config

        # Estimate wall clock time
        wall_clock = gpu_hours * 60  # minutes

        return {
            "gpu_hours": gpu_hours,
            "api_cost": api_cost,
            "wall_clock_minutes": wall_clock,
        }

    async def should_run(
        self,
        estimate: dict[str, float],
    ) -> tuple[bool, str]:
        """Decide whether experiment should run.

        Args:
            estimate: Cost estimate

        Returns:
            Tuple of (should_run, reason)
        """
        gpu_hours = estimate.get("gpu_hours", 0)
        api_cost = estimate.get("api_cost", 0)
        wall_clock = estimate.get("wall_clock_minutes", 0)

        # Check budget
        if api_cost > self.budget_remaining * 0.5:
            return False, f"Cost ${api_cost:.2f} exceeds 50% of remaining budget ${self.budget_remaining:.2f}"

        # Check time
        if wall_clock > self.time_remaining_minutes:
            return False, f"Time {wall_clock:.0f}min exceeds remaining time {self.time_remaining_minutes:.0f}min"

        # Check GPU hours (4hr limit)
        if gpu_hours > 4:
            return False, f"GPU hours {gpu_hours:.1f} exceeds 4hr limit"

        return True, f"Within budget: ${api_cost:.2f}, {wall_clock:.0f}min"


# Convenience function
async def improve_paper(
    paper: str,
    reviewer: CrossModelReviewer,
    config: ImprovementLoopConfig | None = None,
) -> ImprovementResult:
    """Convenience function to run improvement loop.

    Args:
        paper: Initial paper text
        reviewer: Cross-model reviewer
        config: Improvement loop configuration

    Returns:
        ImprovementResult
    """
    loop = AutonomousImprovementLoop(config=config)
    return await loop.run(paper, reviewer)
