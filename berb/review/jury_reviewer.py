"""Enhanced cross-model review with Jury reasoning integration.

This module enhances the cross-model review system by integrating
the Jury reasoning method for multi-dimensional, consistent evaluation.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from berb.llm.client import LLMProvider
from berb.reasoning.jury import JuryMethod, Juror, JurorRole, JuryResult
from berb.review.cross_model_reviewer import (
    CrossModelReviewer,
    CrossModelReviewConfig,
    ReviewResult,
    ReviewVerdict,
    Weakness,
    WeaknessSeverity,
)

logger = logging.getLogger(__name__)


class JuryReviewConfig(BaseModel):
    """Configuration for jury-based review.

    Attributes:
        enabled: Whether to use jury reasoning
        jury_size: Number of jurors (3-6 recommended)
        require_unanimous: Whether unanimous verdict required
        jury_roles: Custom jury roles (None = default)
        deliberation_rounds: Number of deliberation rounds
    """

    enabled: bool = True
    jury_size: int = Field(default=5, ge=3, le=10)
    require_unanimous: bool = False
    jury_roles: list[str] | None = None
    deliberation_rounds: int = Field(default=2, ge=1, le=5)


class JuryCrossModelReviewer(CrossModelReviewer):
    """Cross-model reviewer enhanced with Jury reasoning.

    This reviewer uses a jury of specialized evaluators:
    1. Novelty Evaluator - Assesses contribution originality
    2. Methods Evaluator - Evaluates technical soundness
    3. Impact Evaluator - Assesses significance
    4. Clarity Evaluator - Evaluates presentation quality
    5. Meta Evaluator - Synthesizes verdict, resolves conflicts

    Usage::

        reviewer = JuryCrossModelReviewer(
            review_provider=openai_provider,
            config=CrossModelReviewConfig(
                generation_provider="anthropic",
                review_provider="openai",
            ),
            jury_config=JuryReviewConfig(
                jury_size=5,
                jury_roles=[
                    "novelty_evaluator",
                    "methods_evaluator",
                    "impact_evaluator",
                    "clarity_evaluator",
                    "meta_evaluator",
                ],
            ),
        )

        review = await reviewer.review(paper_text)

    Attributes:
        jury_config: Jury configuration
        jury_method: Jury reasoning method instance
    """

    # Mapping of jury roles to review dimensions
    ROLE_TO_DIMENSION = {
        "novelty_evaluator": "novelty",
        "methods_evaluator": "technical_quality",
        "impact_evaluator": "significance",
        "clarity_evaluator": "clarity",
        "meta_evaluator": "overall",
    }

    # Default jury roles for paper review
    DEFAULT_REVIEW_ROLES = [
        "novelty_evaluator",
        "methods_evaluator",
        "impact_evaluator",
        "clarity_evaluator",
        "meta_evaluator",
    ]

    def __init__(
        self,
        review_provider: LLMProvider,
        config: CrossModelReviewConfig,
        jury_config: JuryReviewConfig | None = None,
    ):
        """Initialize jury-based cross-model reviewer.

        Args:
            review_provider: LLM provider for generating reviews
            config: Cross-model review configuration
            jury_config: Jury configuration
        """
        super().__init__(review_provider, config)

        self.jury_config = jury_config or JuryReviewConfig()
        self.jury_roles = (
            self.jury_config.jury_roles or self.DEFAULT_REVIEW_ROLES
        )

        # Initialize jury method
        self.jury_method = JuryMethod(
            llm_client=review_provider,
            jury_size=len(self.jury_roles),
            require_unanimous=self.jury_config.require_unanimous,
        )

        # Map roles to JurorRole enums
        self._role_mapping = self._create_role_mapping()

    def _create_role_mapping(self) -> dict[str, JurorRole]:
        """Map review roles to JurorRole enums.

        Returns:
            Dictionary mapping role names to JurorRole
        """
        mapping = {
            "novelty_evaluator": JurorRole.INNOVATOR,
            "methods_evaluator": JurorRole.PRACTITIONER,
            "impact_evaluator": JurorRole.ECONOMIST,
            "clarity_evaluator": JurorRole.PRACTITIONER,
            "meta_evaluator": JurorRole.SKEPTIC,
        }

        # Override with custom roles if provided
        if self.jury_config.jury_roles:
            for i, role in enumerate(self.jury_config.jury_roles):
                if i < len(self.DEFAULT_REVIEW_ROLES):
                    mapping[role] = mapping.get(
                        self.DEFAULT_REVIEW_ROLES[i],
                        JurorRole.PRACTITIONER,
                    )

        return mapping

    async def review(
        self,
        paper_text: str,
        review_criteria: list[str] | None = None,
        venue: str = "default",
        prior_review: ReviewResult | None = None,
    ) -> ReviewResult:
        """Generate review using jury reasoning.

        Args:
            paper_text: Full paper text
            review_criteria: Optional custom criteria
            venue: Venue type for criteria
            prior_review: Optional prior review for comparison

        Returns:
            ReviewResult with jury-based evaluation
        """
        if not self.jury_config.enabled:
            # Fall back to standard review
            return await super().review(
                paper_text, review_criteria, venue, prior_review
            )

        logger.info(
            f"Starting jury-based review with {len(self.jury_roles)} evaluators..."
        )

        # Build case for jury
        case = self._build_jury_case(paper_text, review_criteria, venue)

        # Create jurors with specialized roles
        jurors = self._create_specialized_jurors()

        # Execute jury deliberation
        jury_result = await self.jury_method.deliberate(
            case=case,
            jurors=jurors,
            rounds=self.jury_config.deliberation_rounds,
        )

        # Convert jury result to review result
        review_result = self._jury_to_review(jury_result, paper_text)

        # Compare with prior review if provided
        if prior_review:
            delta = self.compare_with_prior(review_result, prior_review)
            logger.info(
                f"Jury review comparison: score change {delta.score_change:+.2f}"
            )

        logger.info(
            f"Jury review complete: score={review_result.overall_score:.1f}, "
            f"verdict={review_result.verdict.value}"
        )

        return review_result

    def _build_jury_case(
        self,
        paper_text: str,
        criteria: list[str] | None,
        venue: str,
    ) -> str:
        """Build case presentation for jury.

        Args:
            paper_text: Full paper text
            criteria: Review criteria
            venue: Venue type

        Returns:
            Formatted case string
        """
        criteria_text = "\n".join(f"- {c}" for c in (criteria or self.VENUE_CRITERIA.get(venue, self.VENUE_CRITERIA["default"])))

        case = f"""## Paper Review Case

**Venue:** {venue.upper()}

**Review Criteria:**
{criteria_text}

**Paper Text:**
{paper_text[:50000]}  # Truncate if too long

## Instructions for Jury

You are serving on a jury to evaluate this academic paper. Each juror should:
1. Evaluate the paper from their specialized perspective
2. Provide specific evidence for their assessment
3. Identify concrete weaknesses and strengths
4. Assign a confidence score to their verdict

The foreman will synthesize all perspectives into a final review."""

        return case

    def _create_specialized_jurors(self) -> list[Juror]:
        """Create jurors with specialized review roles.

        Returns:
            List of specialized jurors
        """
        jurors = []

        for role_name in self.jury_roles:
            juror_role = self._role_mapping.get(
                role_name, JurorRole.PRACTITIONER
            )

            # Create juror with role-specific perspective
            perspective = self._get_role_perspective(role_name)
            jurors.append(
                Juror(
                    role=juror_role,
                    name=role_name.replace("_", " ").title(),
                    perspective=perspective,
                )
            )

        return jurors

    def _get_role_perspective(self, role_name: str) -> str:
        """Get perspective description for a role.

        Args:
            role_name: Role name

        Returns:
            Perspective description
        """
        perspectives = {
            "novelty_evaluator": (
                "You evaluate the originality and novelty of contributions. "
                "Look for: new methods, new insights, new applications, new theory. "
                "Question: Has this been done before? What's genuinely new here?"
            ),
            "methods_evaluator": (
                "You evaluate technical soundness and methodological rigor. "
                "Look for: appropriate methods, proper controls, statistical validity, "
                "reproducibility. Question: Would this hold up to expert scrutiny?"
            ),
            "impact_evaluator": (
                "You evaluate significance and potential impact. "
                "Look for: broad applicability, important problem, practical relevance. "
                "Question: Will this matter to the field in 5 years?"
            ),
            "clarity_evaluator": (
                "You evaluate presentation quality and accessibility. "
                "Look for: clear writing, logical flow, understandable figures, "
                "complete explanations. Question: Can readers understand and build on this?"
            ),
            "meta_evaluator": (
                "You synthesize all perspectives and resolve conflicts. "
                "Look for: overall contribution, balance of strengths/weaknesses. "
                "Question: Taking all factors into account, should this be accepted?"
            ),
        }

        return perspectives.get(
            role_name,
            "You evaluate this paper from a specialized perspective.",
        )

    def _jury_to_review(
        self,
        jury_result: JuryResult,
        paper_text: str,
    ) -> ReviewResult:
        """Convert jury result to review result.

        Args:
            jury_result: Result from jury deliberation
            paper_text: Original paper text

        Returns:
            ReviewResult for the paper
        """
        # Parse jury verdict
        verdict = self._parse_jury_verdict(jury_result.verdict)

        # Calculate overall score from jury confidence
        overall_score = jury_result.confidence * 10.0

        # Extract weaknesses from juror concerns
        weaknesses = []
        for juror in jury_result.jurors:
            for concern in juror.concerns:
                weaknesses.append(
                    Weakness(
                        category=self._get_category_for_role(juror.role.value),
                        description=concern,
                        severity=self._estimate_severity(concern),
                        location="",
                        evidence=juror.reasoning[:200],
                        actionable=True,
                    )
                )

        # Extract strengths from positive reasoning
        strengths = []
        for juror in jury_result.jurors:
            if juror.verdict == "approve":
                strengths.append(
                    f"{juror.name}: {juror.reasoning[:100]}"
                )

        # Extract actionable improvements from conditions
        actionable_improvements = []
        for juror in jury_result.jurors:
            actionable_improvements.extend(juror.conditions)

        return ReviewResult(
            overall_score=overall_score,
            verdict=verdict,
            strengths=strengths[:5],  # Top 5 strengths
            weaknesses=weaknesses[:10],  # Top 10 weaknesses
            missing_experiments=[],  # Would extract from jury result
            writing_issues=[],  # Would extract from clarity evaluator
            actionable_improvements=actionable_improvements[:5],
            confidence=jury_result.confidence,
            review_text=jury_result.foreman_synthesis,
            model_used=self.config.review_model,
        )

    def _parse_jury_verdict(self, jury_verdict: str) -> ReviewVerdict:
        """Parse jury verdict to review verdict.

        Args:
            jury_verdict: Jury verdict string

        Returns:
            ReviewVerdict
        """
        verdict_mapping = {
            "unanimous_approve": ReviewVerdict.ACCEPT,
            "majority_approve": ReviewVerdict.WEAK_ACCEPT,
            "hung": ReviewVerdict.BORDERLINE,
            "majority_reject": ReviewVerdict.BORDERLINE,
            "unanimous_reject": ReviewVerdict.REJECT,
        }

        return verdict_mapping.get(
            jury_verdict.lower(),
            ReviewVerdict.BORDERLINE,
        )

    def _get_category_for_role(self, role: str) -> str:
        """Map jury role to weakness category.

        Args:
            role: Jury role

        Returns:
            Weakness category
        """
        category_mapping = {
            "innovator": "novelty",
            "practitioner": "methods",
            "economist": "significance",
            "skeptic": "clarity",
            "optimist": "other",
            "ethicist": "other",
        }

        return category_mapping.get(role, "other")

    def _estimate_severity(self, concern: str) -> WeaknessSeverity:
        """Estimate severity from concern text.

        Args:
            concern: Concern text

        Returns:
            WeaknessSeverity
        """
        concern_lower = concern.lower()

        # Critical keywords
        critical_keywords = [
            "fundamental flaw", "incorrect", "invalid", "doesn't work",
            "no evidence", "contradicts", "impossible",
        ]

        # Major keywords
        major_keywords = [
            "insufficient", "incomplete", "unclear", "missing",
            "weak", "limited", "questionable",
        ]

        for keyword in critical_keywords:
            if keyword in concern_lower:
                return WeaknessSeverity.CRITICAL

        for keyword in major_keywords:
            if keyword in concern_lower:
                return WeaknessSeverity.MAJOR

        # Default to minor
        return WeaknessSeverity.MINOR


class MultiJuryReviewConfig(BaseModel):
    """Configuration for multi-jury review (ensemble of juries).

    Attributes:
        num_juries: Number of independent juries
        aggregation_method: How to aggregate jury scores
    """

    num_juries: int = Field(default=3, ge=1, le=5)
    aggregation_method: str = "mean"  # mean, median, weighted


class MultiJuryReviewer:
    """Ensemble of multiple independent juries for robust review.

    This reviewer runs multiple juries in parallel and aggregates
    their results for more robust evaluation.

    Usage::

        reviewer = MultiJuryReviewer(
            review_provider=openai_provider,
            config=CrossModelReviewConfig(...),
            multi_jury_config=MultiJuryReviewConfig(num_juries=3),
        )

        review = await reviewer.review(paper_text)

    Attributes:
        jury_reviewer: Base jury reviewer
        num_juries: Number of independent juries
    """

    def __init__(
        self,
        review_provider: LLMProvider,
        config: CrossModelReviewConfig,
        multi_jury_config: MultiJuryReviewConfig | None = None,
    ):
        """Initialize multi-jury reviewer.

        Args:
            review_provider: LLM provider for reviews
            config: Cross-model review configuration
            multi_jury_config: Multi-jury configuration
        """
        self.multi_jury_config = multi_jury_config or MultiJuryReviewConfig()

        self.jury_reviewer = JuryCrossModelReviewer(
            review_provider=review_provider,
            config=config,
        )

    async def review(
        self,
        paper_text: str,
        **kwargs: Any,
    ) -> ReviewResult:
        """Generate review using ensemble of juries.

        Args:
            paper_text: Full paper text
            **kwargs: Additional arguments for jury review

        Returns:
            Aggregated ReviewResult
        """
        import asyncio

        # Run multiple juries in parallel
        jury_tasks = [
            self.jury_reviewer.review(paper_text, **kwargs)
            for _ in range(self.multi_jury_config.num_juries)
        ]

        jury_results = await asyncio.gather(*jury_tasks)

        # Aggregate results
        aggregated = self._aggregate_reviews(jury_results)

        logger.info(
            f"Multi-jury review complete: {self.multi_jury_config.num_juries} juries, "
            f"aggregated score={aggregated.overall_score:.1f}"
        )

        return aggregated

    def _aggregate_reviews(
        self,
        reviews: list[ReviewResult],
    ) -> ReviewResult:
        """Aggregate multiple jury reviews.

        Args:
            reviews: List of jury review results

        Returns:
            Aggregated review result
        """
        if not reviews:
            raise ValueError("No reviews to aggregate")

        if len(reviews) == 1:
            return reviews[0]

        # Calculate aggregated score
        scores = [r.overall_score for r in reviews]

        if self.multi_jury_config.aggregation_method == "mean":
            aggregated_score = sum(scores) / len(scores)
        elif self.multi_jury_config.aggregation_method == "median":
            sorted_scores = sorted(scores)
            mid = len(sorted_scores) // 2
            aggregated_score = sorted_scores[mid]
        else:  # weighted by confidence
            total_confidence = sum(r.confidence for r in reviews)
            if total_confidence > 0:
                aggregated_score = sum(
                    r.overall_score * r.confidence for r in reviews
                ) / total_confidence
            else:
                aggregated_score = sum(scores) / len(scores)

        # Aggregate verdicts (majority vote)
        verdict_votes = {}
        for r in reviews:
            verdict = r.verdict.value
            verdict_votes[verdict] = verdict_votes.get(verdict, 0) + 1

        majority_verdict = max(verdict_votes, key=verdict_votes.get)

        # Combine weaknesses (union, deduplicated)
        all_weaknesses = []
        seen = set()
        for r in reviews:
            for w in r.weaknesses:
                key = w.description[:50]
                if key not in seen:
                    all_weaknesses.append(w)
                    seen.add(key)

        # Combine strengths
        all_strengths = []
        for r in reviews:
            all_strengths.extend(r.strengths)

        return ReviewResult(
            overall_score=aggregated_score,
            verdict=ReviewVerdict(majority_verdict),
            strengths=all_strengths[:10],
            weaknesses=all_weaknesses[:20],
            missing_experiments=[],
            writing_issues=[],
            actionable_improvements=[],
            confidence=sum(r.confidence for r in reviews) / len(reviews),
            review_text=f"Aggregated from {len(reviews)} independent juries.",
            model_used=self.jury_reviewer.config.review_model,
        )
