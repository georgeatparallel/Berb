"""Cross-model review system for unbiased paper evaluation.

This module implements the critical separation of generation and evaluation:
the model that writes the paper must NEVER be the model that evaluates it.

Features:
- Cross-provider review (Anthropic writes → OpenAI reviews)
- Structured review with scoring
- Anti-gaming measures (hide generation model, hide chain-of-thought)
- Comparison with prior reviews for improvement tracking

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from berb.llm.client import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class ReviewVerdict(str, Enum):
    """Review verdict for a paper.

    Attributes:
        ACCEPT: Accept for publication
        WEAK_ACCEPT: Weak accept with minor revisions
        BORDERLINE: Borderline accept/reject
        REJECT: Reject with major issues
    """

    ACCEPT = "accept"
    WEAK_ACCEPT = "weak_accept"
    BORDERLINE = "borderline"
    REJECT = "reject"


class WeaknessSeverity(str, Enum):
    """Severity of identified weaknesses.

    Attributes:
        CRITICAL: Must fix before publication
        MAJOR: Should fix before publication
        MINOR: Recommended to fix
        COSMETIC: Optional improvement
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    COSMETIC = "cosmetic"


class Weakness(BaseModel):
    """Identified weakness in the paper.

    Attributes:
        category: Weakness category (novelty/clarity/methods/etc.)
        description: Detailed description of the weakness
        severity: Severity level
        location: Where in the paper the weakness appears
        evidence: Evidence supporting the weakness identification
        actionable: Whether the weakness is actionable
    """

    category: str
    description: str
    severity: WeaknessSeverity
    location: str = Field(default="", description="Section/paragraph location")
    evidence: str = Field(default="", description="Supporting evidence")
    actionable: bool = Field(default=True, description="Whether this can be fixed")


class ReviewResult(BaseModel):
    """Complete review result for a paper.

    Attributes:
        overall_score: Overall score (1-10)
        verdict: Review verdict
        strengths: List of paper strengths
        weaknesses: List of identified weaknesses
        missing_experiments: Experiments that should be added
        writing_issues: Writing quality issues
        actionable_improvements: Specific actionable improvements
        confidence: Reviewer confidence in assessment
        review_text: Full review text
        model_used: Model that generated the review
    """

    overall_score: float = Field(ge=1.0, le=10.0)
    verdict: ReviewVerdict
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[Weakness] = Field(default_factory=list)
    missing_experiments: list[str] = Field(default_factory=list)
    writing_issues: list[str] = Field(default_factory=list)
    actionable_improvements: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    review_text: str = ""
    model_used: str = ""


class ImprovementDelta(BaseModel):
    """Comparison between current and prior review.

    Attributes:
        score_change: Change in overall score
        improvements_made: Improvements that were addressed
        regressions: Areas that got worse
        unchanged_weaknesses: Weaknesses that persist
        new_weaknesses: Newly identified weaknesses
        net_improvement: Whether paper improved overall
    """

    score_change: float
    improvements_made: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    unchanged_weaknesses: list[str] = Field(default_factory=list)
    new_weaknesses: list[str] = Field(default_factory=list)
    net_improvement: bool = True


class CrossModelReviewConfig(BaseModel):
    """Configuration for cross-model review.

    Attributes:
        generation_provider: Provider that generated the paper
        review_provider: Provider for review (MUST be different)
        allow_same_provider: Safety flag (default False)
        review_model: Specific model for reviews
        review_reasoning_level: Reasoning level for review
        review_temperature: Temperature for review generation
        hide_generation_model: Don't tell reviewer which model wrote it
        hide_intermediate_reasoning: Reviewer sees output only
    """

    generation_provider: str = Field(
        description="Provider that generated the paper (anthropic/openai/etc.)",
    )
    review_provider: str = Field(
        description="Provider for review (MUST be different from generation)",
    )
    allow_same_provider: bool = Field(
        default=False,
        description="Safety: default False to prevent self-grading",
    )
    review_model: str = Field(
        default="gpt-4o",
        description="Specific model for reviews",
    )
    review_reasoning_level: Literal["standard", "high", "xhigh"] = Field(
        default="xhigh",
        description="Reasoning level for review",
    )
    review_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Lower temperature for consistent scoring",
    )
    hide_generation_model: bool = Field(
        default=True,
        description="Don't tell reviewer which model wrote the paper",
    )
    hide_intermediate_reasoning: bool = Field(
        default=True,
        description="Reviewer sees output only, not chain-of-thought",
    )

    def validate_provider_separation(self) -> tuple[bool, str]:
        """Validate that generation and review providers are different.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.allow_same_provider:
            return True, ""

        if self.generation_provider.lower() == self.review_provider.lower():
            return False, (
                f"Generation provider ({self.generation_provider}) cannot be the same "
                f"as review provider ({self.review_provider}). This would create "
                f"self-grading bias. Set allow_same_provider=True to override (not recommended)."
            )

        return True, ""


class CrossModelReviewer:
    """External model reviews paper without seeing generation process.

    This reviewer ensures unbiased evaluation by:
    1. Using a different model family than the generator
    2. Hiding generation metadata from the reviewer
    3. Using structured review prompts for consistency
    4. Tracking improvement across review rounds

    Usage::

        reviewer = CrossModelReviewer(
            review_provider=openai_provider,
            config=CrossModelReviewConfig(
                generation_provider="anthropic",
                review_provider="openai",
            ),
        )

        review = await reviewer.review(
            paper_text=paper_text,
            review_criteria=["novelty", "significance", "clarity"],
        )

    Attributes:
        review_provider: LLM provider for generating reviews
        config: Review configuration
    """

    # Review prompt template
    REVIEW_PROMPT = """You are a senior reviewer for {venue}. Your task is to provide a ruthlessly honest, constructive review of the following paper.

## Important Instructions
- Be as critical as a real reviewer would be
- Do NOT hide weaknesses to produce a positive score
- Identify specific, actionable improvements
- Score objectively based on the criteria below

## Paper Text
{paper_text}

## Review Criteria
{criteria}

## Output Format
Respond with JSON in this exact format:
{{
    "overall_score": 1-10,
    "verdict": "accept|weak_accept|borderline|reject",
    "strengths": ["strength 1", "strength 2", ...],
    "weaknesses": [
        {{
            "category": "novelty|clarity|methods|experiments|writing|other",
            "description": "Detailed description",
            "severity": "critical|major|minor|cosmetic",
            "location": "Section/paragraph where it appears",
            "evidence": "Supporting evidence from the paper",
            "actionable": true/false
        }},
        ...
    ],
    "missing_experiments": ["experiment 1", ...],
    "writing_issues": ["issue 1", ...],
    "actionable_improvements": ["improvement 1", ...],
    "confidence": 0.0-1.0,
    "review_text": "Full review text (2-3 paragraphs)"
}}

## Scoring Guidelines
- 9-10: Outstanding, accept immediately
- 7-8: Strong paper, minor revisions needed
- 5-6: Borderline, major revisions needed
- 3-4: Weak, significant issues
- 1-2: Reject, fundamental flaws

Be conservative with high scores. Most papers score 5-7."""

    # Criteria for different venues
    VENUE_CRITERIA = {
        "neurips": [
            "Novelty: Does this paper present novel contributions?",
            "Technical Quality: Are the methods sound and rigorous?",
            "Significance: Will this impact the field?",
            "Clarity: Is the paper well-written and understandable?",
            "Experiments: Are experiments thorough and convincing?",
        ],
        "nature": [
            "Novelty: Does this present a significant advance?",
            "Evidence: Is the evidence compelling and robust?",
            "Impact: Will this interest a broad scientific audience?",
            "Clarity: Is the paper accessible to non-specialists?",
            "Methods: Are methods appropriate and rigorous?",
        ],
        "default": [
            "Novelty: Does this paper present novel contributions?",
            "Technical Quality: Are the methods sound?",
            "Significance: Is this important for the field?",
            "Clarity: Is the paper well-written?",
            "Experiments: Are experiments adequate?",
        ],
    }

    def __init__(
        self,
        review_provider: LLMProvider,
        config: CrossModelReviewConfig,
    ):
        """Initialize cross-model reviewer.

        Args:
            review_provider: LLM provider for generating reviews
            config: Review configuration
        """
        self.review_provider = review_provider
        self.config = config

        # Validate configuration
        is_valid, error = config.validate_provider_separation()
        if not is_valid:
            raise ValueError(error)

        # Review cache
        self._review_cache: dict[str, ReviewResult] = {}

    async def review(
        self,
        paper_text: str,
        review_criteria: list[str] | None = None,
        venue: str = "default",
        prior_review: ReviewResult | None = None,
    ) -> ReviewResult:
        """Generate review for a paper.

        Args:
            paper_text: Full paper text
            review_criteria: Optional custom criteria
            venue: Venue type for criteria (neurips/nature/default)
            prior_review: Optional prior review for comparison

        Returns:
            ReviewResult with scores and feedback
        """
        # Check cache
        cache_key = f"{hash(paper_text)}:{venue}"
        if cache_key in self._review_cache:
            return self._review_cache[cache_key]

        # Get criteria
        criteria = review_criteria or self.VENUE_CRITERIA.get(
            venue, self.VENUE_CRITERIA["default"]
        )
        criteria_text = "\n".join(f"- {c}" for c in criteria)

        # Build prompt
        prompt = self.REVIEW_PROMPT.format(
            venue=venue.upper(),
            paper_text=paper_text[:50000],  # Truncate if too long
            criteria=criteria_text,
        )

        # Add anti-gaming instruction
        if self.config.hide_generation_model:
            prompt += "\n\nNote: You are reviewing this paper blind - do not speculate about how it was generated."

        try:
            # Call LLM
            response = await self.review_provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self.config.review_model,
                temperature=self.config.review_temperature,
            )

            # Parse response
            result = self._parse_response(response)
            result.model_used = self.config.review_model

            # Compare with prior review if provided
            if prior_review:
                delta = self.compare_with_prior(result, prior_review)
                logger.info(
                    f"Review comparison: score change {delta.score_change:+.2f}, "
                    f"net improvement: {delta.net_improvement}"
                )

            # Cache result
            self._review_cache[cache_key] = result

            logger.info(
                f"Generated review: score={result.overall_score:.1f}, "
                f"verdict={result.verdict.value}, "
                f"weaknesses={len(result.weaknesses)}"
            )

            return result

        except Exception as e:
            logger.error(f"Review generation failed: {e}")
            # Return conservative fallback review
            return ReviewResult(
                overall_score=5.0,
                verdict=ReviewVerdict.BORDERLINE,
                strengths=["Paper appears complete"],
                weaknesses=[
                    Weakness(
                        category="other",
                        description="Review generation failed - manual review recommended",
                        severity=WeaknessSeverity.MAJOR,
                        actionable=False,
                    )
                ],
                confidence=0.3,
                review_text=f"Review generation failed: {e}",
                model_used=self.config.review_model,
            )

    def _parse_response(self, response: LLMResponse) -> ReviewResult:
        """Parse LLM response into ReviewResult.

        Args:
            response: LLM response

        Returns:
            Parsed ReviewResult
        """
        import re

        text = response.content.strip()

        # Try to extract JSON from response
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return ReviewResult(
                    overall_score=float(data.get("overall_score", 5.0)),
                    verdict=ReviewVerdict(data.get("verdict", "borderline")),
                    strengths=data.get("strengths", []),
                    weaknesses=[
                        Weakness(**w) for w in data.get("weaknesses", [])
                    ],
                    missing_experiments=data.get("missing_experiments", []),
                    writing_issues=data.get("writing_issues", []),
                    actionable_improvements=data.get("actionable_improvements", []),
                    confidence=float(data.get("confidence", 0.5)),
                    review_text=data.get("review_text", ""),
                    model_used=self.config.review_model,
                )
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse JSON response: {e}")

        # Fallback: return minimal review
        return ReviewResult(
            overall_score=5.0,
            verdict=ReviewVerdict.BORDERLINE,
            strengths=[],
            weaknesses=[
                Weakness(
                    category="other",
                    description="Could not parse review - response format error",
                    severity=WeaknessSeverity.MINOR,
                    actionable=False,
                )
            ],
            confidence=0.3,
            review_text=text[:500],
            model_used=self.config.review_model,
        )

    def compare_with_prior(
        self,
        current_review: ReviewResult,
        prior_review: ReviewResult,
    ) -> ImprovementDelta:
        """Compare current review with prior review.

        Args:
            current_review: Current review result
            prior_review: Prior review result

        Returns:
            ImprovementDelta with comparison
        """
        score_change = current_review.overall_score - prior_review.overall_score

        # Identify improvements made
        prior_weaknesses = {w.description.lower(): w for w in prior_review.weaknesses}
        current_weaknesses = {w.description.lower(): w for w in current_review.weaknesses}

        improvements_made = []
        unchanged_weaknesses = []
        new_weaknesses = []

        for desc, weakness in prior_weaknesses.items():
            if desc in current_weaknesses:
                unchanged_weaknesses.append(desc)
            else:
                improvements_made.append(f"Fixed: {weakness.category} - {desc[:50]}")

        for desc, weakness in current_weaknesses.items():
            if desc not in prior_weaknesses:
                new_weaknesses.append(f"New: {weakness.category} - {desc[:50]}")

        # Identify regressions (new critical/major weaknesses)
        regressions = [
            w for w in new_weaknesses
            if any(sev in w.lower() for sev in ["critical", "major"])
        ]

        net_improvement = score_change > 0 and len(improvements_made) >= len(new_weaknesses)

        return ImprovementDelta(
            score_change=score_change,
            improvements_made=improvements_made,
            regressions=regressions,
            unchanged_weaknesses=unchanged_weaknesses,
            new_weaknesses=new_weaknesses,
            net_improvement=net_improvement,
        )


class CrossModelReviewConfigPreset:
    """Presets for common cross-model review configurations."""

    # Claude writes → GPT reviews
    CLAUDE_TO_GPT = CrossModelReviewConfig(
        generation_provider="anthropic",
        review_provider="openai",
        review_model="gpt-4o",
    )

    # GPT writes → Claude reviews
    GPT_TO_CLAUDE = CrossModelReviewConfig(
        generation_provider="openai",
        review_provider="anthropic",
        review_model="claude-sonnet-4-6",
    )

    # DeepSeek writes → Claude reviews
    DEEPSEEK_TO_CLAUDE = CrossModelReviewConfig(
        generation_provider="deepseek",
        review_provider="anthropic",
        review_model="claude-sonnet-4-6",
    )

    # Gemini writes → GPT reviews
    GEMINI_TO_GPT = CrossModelReviewConfig(
        generation_provider="google",
        review_provider="openai",
        review_model="gpt-4o",
    )


def get_review_config_for_generation(generation_provider: str) -> CrossModelReviewConfig:
    """Get appropriate review config for a generation provider.

    Args:
        generation_provider: Provider that generated the paper

    Returns:
        Appropriate CrossModelReviewConfig
    """
    presets = {
        "anthropic": CrossModelReviewConfigPreset.CLAUDE_TO_GPT,
        "openai": CrossModelReviewConfigPreset.GPT_TO_CLAUDE,
        "deepseek": CrossModelReviewConfigPreset.DEEPSEEK_TO_CLAUDE,
        "google": CrossModelReviewConfigPreset.GEMINI_TO_GPT,
    }

    return presets.get(
        generation_provider.lower(),
        CrossModelReviewConfigPreset.CLAUDE_TO_GPT,
    )
