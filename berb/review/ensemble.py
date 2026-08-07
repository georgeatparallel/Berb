"""Automated Reviewer Ensemble for Berb.

Implements 5-reviewer system + Area Chair meta-review based on AI Scientist (Nature 2026).

Each reviewer has distinct focus:
1. Novelty & Significance
2. Technical Correctness
3. Experimental Rigor
4. Clarity & Presentation
5. Reproducibility

Area Chair aggregates reviews and provides acceptance recommendation.

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.review import AutomatedReviewerEnsemble

    ensemble = AutomatedReviewerEnsemble()
    reviews = await ensemble.review_paper(paper_path="paper.pdf")
    meta_review = ensemble.area_chair_decision(reviews)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _safe_json_loads(text: str, default: Any) -> Any:
    """Parse JSON from an LLM response, tolerating markdown code fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return default


class ReviewDimension(StrEnum):
    """Review dimensions based on NeurIPS guidelines."""

    NOVELTY = "novelty"  # 1-10
    SIGNIFICANCE = "significance"  # 1-10
    TECHNICAL_QUALITY = "technical_quality"  # 1-10
    EXPERIMENTAL_RIGOR = "experimental_rigor"  # 1-10
    CLARITY = "clarity"  # 1-10
    REPRODUCIBILITY = "reproducibility"  # 1-10


class Decision(StrEnum):
    """Paper decisions."""

    STRONG_ACCEPT = "strong_accept"  # 9-10
    ACCEPT = "accept"  # 7-8
    WEAK_ACCEPT = "weak_accept"  # 6
    WEAK_REJECT = "weak_reject"  # 5
    REJECT = "reject"  # 3-4
    STRONG_REJECT = "strong_reject"  # 1-2


@dataclass
class ReviewerPersona:
    """Defines a reviewer's focus and evaluation criteria."""

    id: str
    name: str
    focus_areas: list[ReviewDimension]
    system_prompt: str
    weight: float = 1.0  # Weight in meta-review


@dataclass
class Review:
    """Single reviewer's evaluation."""

    reviewer_id: str
    reviewer_name: str
    scores: dict[ReviewDimension, int]
    overall_score: float  # Weighted average
    decision: Decision
    strengths: list[str]
    weaknesses: list[str]
    questions_for_authors: list[str]
    confidence: int  # 1-5 (5=very confident)
    detailed_feedback: str


@dataclass
class MetaReview:
    """Area Chair meta-review aggregating all reviews."""

    reviews: list[Review]
    average_score: float
    score_std: float
    max_score: float
    min_score: float
    score_distribution: dict[str, int]
    consensus_decision: Decision
    confidence: float  # 0-1 (agreement level)
    meta_review_text: str
    acceptance_recommendation: str
    reviewer_conflicts: list[str]  # Areas where reviewers disagreed


# Reviewer personas based on NeurIPS reviewer guidelines
REVIEWER_PERSONAS = [
    ReviewerPersona(
        id="reviewer_1",
        name="Novelty & Significance Expert",
        focus_areas=[ReviewDimension.NOVELTY, ReviewDimension.SIGNIFICANCE],
        weight=1.2,  # Slightly higher weight for novelty
        system_prompt="""You are a senior ML researcher reviewing for a top-tier conference (NeurIPS/ICML/ICLR).
Your expertise is in identifying novel contributions and assessing their significance.

Evaluation Criteria:
- NOVELTY: Does this paper present a genuinely new idea? Or is it incremental?
- SIGNIFICANCE: If the claims are true, would this impact the field?

Be critical but fair. Distinguish between:
- Truly novel ideas (rare, score 8-10)
- Solid incremental improvements (common, score 5-7)
- Obvious variations (score 3-4)
- Already published ideas (score 1-2)

Provide specific examples from the paper to justify your scores.""",
    ),
    ReviewerPersona(
        id="reviewer_2",
        name="Technical Correctness Expert",
        focus_areas=[ReviewDimension.TECHNICAL_QUALITY],
        weight=1.1,
        system_prompt="""You are a rigorous technical reviewer with expertise in mathematical proofs, algorithm design, and theoretical foundations.

Evaluation Criteria:
- TECHNICAL_QUALITY: Are the claims mathematically sound? Are proofs correct? Are algorithms well-defined?

Check for:
- Mathematical errors or gaps in proofs
- Undefined notation or ambiguous definitions
- Incorrect assumptions
- Flawed logic or reasoning
- Missing baselines or unfair comparisons

Be meticulous. A single critical error should significantly lower your score.""",
    ),
    ReviewerPersona(
        id="reviewer_3",
        name="Experimental Rigor Expert",
        focus_areas=[ReviewDimension.EXPERIMENTAL_RIGOR],
        weight=1.1,
        system_prompt="""You are an experienced experimentalist who has reviewed hundreds of ML papers.

Evaluation Criteria:
- EXPERIMENTAL_RIGOR: Are experiments well-designed? Are baselines appropriate? Are statistical tests used?

Check for:
- Adequate number of runs / seeds
- Proper train/val/test splits
- Appropriate baselines (SOTA, not weak)
- Statistical significance testing
- Ablation studies
- Hyperparameter sensitivity
- Compute budget reporting
- Potential data leakage

Be skeptical of claims without proper experimental support.""",
    ),
    ReviewerPersona(
        id="reviewer_4",
        name="Clarity & Presentation Expert",
        focus_areas=[ReviewDimension.CLARITY],
        weight=0.9,
        system_prompt="""You focus on paper clarity, organization, and presentation quality.

Evaluation Criteria:
- CLARITY: Is the paper well-written and easy to understand?

Check for:
- Clear problem statement
- Logical flow and organization
- Readable figures and tables
- Proper citations
- Grammar and spelling
- Appropriate length (no padding)

A well-written paper should be accessible to a knowledgeable ML researcher who is not an expert in this specific subfield.""",
    ),
    ReviewerPersona(
        id="reviewer_5",
        name="Reproducibility Expert",
        focus_areas=[ReviewDimension.REPRODUCIBILITY],
        weight=1.0,
        system_prompt="""You are dedicated to ensuring research reproducibility.

Evaluation Criteria:
- REPRODUCIBILITY: Could another researcher reproduce these results?

Check for:
- Code availability (URL, anonymized if double-blind)
- Detailed hyperparameters
- Dataset availability and preprocessing
- Training details (optimizer, LR schedule, etc.)
- Compute requirements
- Random seeds
- Environment specifications (Docker, conda, etc.)

A paper with code and detailed instructions should score 8-10.
A paper with no code and vague details should score 3-5.""",
    ),
]


class AutomatedReviewerEnsemble:
    """5-reviewer ensemble + Area Chair meta-review."""

    def __init__(self, llm_client: Any | None = None) -> None:
        """Initialize reviewer ensemble.

        Args:
            llm_client: LLM client for generating reviews (optional, uses default if None)
        """
        self._personas = REVIEWER_PERSONAS
        self._llm_client = llm_client

    async def review_paper(
        self,
        paper_path: str | Path,
        paper_text: str | None = None,
        *,
        use_batch: bool = False,
    ) -> list[Review]:
        """Generate 5 independent reviews.

        Args:
            paper_path: Path to paper (PDF or LaTeX)
            paper_text: Optional pre-extracted paper text
            use_batch: Try Anthropic's Message Batches API first (50%
                discount, stacks with prompt caching — tasks/todo.md #5).
                Only takes effect when the configured LLM client talks to
                Anthropic directly (OpenRouter has no verified native
                batch endpoint, so this is a no-op there). Bounded by a
                short poll timeout — on timeout or any failure this falls
                back to the normal per-persona calls below, so worst-case
                behavior matches use_batch=False.

        Returns:
            List of 5 reviews
        """
        paper_path = Path(paper_path)

        # Extract paper text if not provided
        if paper_text is None:
            paper_text = self._extract_paper_text(paper_path)

        if use_batch:
            batch_reviews = await self._review_paper_batch(paper_text)
            if batch_reviews is not None:
                logger.info(
                    f"Generated {len(batch_reviews)} reviews via batch for {paper_path.name}"
                )
                return batch_reviews
            logger.info("Batch review unavailable or timed out — falling back to per-call reviews")

        # Generate reviews in parallel
        import asyncio

        review_tasks = [self._generate_review(persona, paper_text) for persona in self._personas]

        reviews = await asyncio.gather(*review_tasks)

        logger.info(f"Generated {len(reviews)} reviews for {paper_path.name}")
        return list(reviews)

    async def _review_paper_batch(
        self,
        paper_text: str,
        *,
        poll_interval_sec: float = 5.0,
        max_wait_sec: float = 600.0,
    ) -> list[Review] | None:
        """Submit all 5 persona reviews as one Anthropic Message Batch.

        Returns None (never raises) if batch mode isn't available, the
        submission fails, or the batch doesn't finish within
        max_wait_sec — every failure mode is a signal for the caller to
        fall back to the synchronous per-persona path, not an error to
        propagate. Bounding the wait (rather than trusting the API's 24h
        SLA) keeps `berb run` from stalling for hours on a slow batch —
        for a 5-request batch, actual turnaround is normally minutes.
        """
        anthropic = getattr(self._llm_client, "_anthropic", None)
        if anthropic is None:
            return None

        model = getattr(getattr(self._llm_client, "config", None), "primary_model", None)
        if not model:
            return None
        client_config = self._llm_client.config
        max_tokens = getattr(client_config, "max_tokens", 4096)
        temperature = getattr(client_config, "temperature", 0.7)

        if len(paper_text) > 50000:
            paper_text = paper_text[:50000] + "\n\n[... truncated ...]"
        cached_prefix = f"PAPER TEXT:\n{paper_text}"

        requests = [
            {
                "custom_id": persona.id,
                "model": model,
                "messages": [
                    {"role": "system", "content": persona.system_prompt},
                    {"role": "user", "content": self._build_review_prompt(persona)},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "cached_prefix": cached_prefix,
                "cache_ttl": "1h",
            }
            for persona in self._personas
        ]

        import asyncio

        try:
            batch_id = await asyncio.to_thread(anthropic.submit_batch, requests)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Batch submission failed: %s", exc)
            return None

        elapsed = 0.0
        results_url: str | None = None
        while elapsed < max_wait_sec:
            await asyncio.sleep(poll_interval_sec)
            elapsed += poll_interval_sec
            try:
                status = await asyncio.to_thread(anthropic.get_batch_status, batch_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Batch status poll failed: %s", exc)
                return None
            if status.get("processing_status") == "ended":
                results_url = status.get("results_url")
                break
        else:
            logger.warning(
                "Batch %s did not finish within %ss — falling back", batch_id, max_wait_sec
            )
            return None

        if not results_url:
            return None

        try:
            raw_results = await asyncio.to_thread(anthropic.fetch_batch_results, results_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Batch result fetch failed: %s", exc)
            return None

        reviews: list[Review] = []
        for persona in self._personas:
            entry = raw_results.get(persona.id)
            content = entry["choices"][0]["message"]["content"] if entry else ""
            reviews.append(self._parse_review_content(persona, content))
        return reviews

    @staticmethod
    def _build_review_prompt(persona: ReviewerPersona) -> str:
        """The persona-specific user turn — identical between the sync
        per-call path and the batch path, so results are comparable."""
        return f"""OUTPUT FORMAT (JSON):
{{
    "scores": {{
        "novelty": <1-10>,
        "significance": <1-10>,
        "technical_quality": <1-10>,
        "experimental_rigor": <1-10>,
        "clarity": <1-10>,
        "reproducibility": <1-10>
    }},
    "overall_score": <float 1-10>,
    "decision": "<strong_accept|accept|weak_accept|weak_reject|reject|strong_reject>",
    "strengths": ["strength 1", "strength 2", ...],
    "weaknesses": ["weakness 1", "weakness 2", ...],
    "questions_for_authors": ["question 1", ...],
    "confidence": <1-5>,
    "detailed_feedback": "<2-3 paragraphs of detailed review>"
}}

Focus on your assigned areas: {", ".join(d.value for d in persona.focus_areas)}
Return ONLY the JSON object, no other text.
"""

    def _parse_review_content(self, persona: ReviewerPersona, content: str) -> Review:
        """Parse an LLM response's text content into a Review, falling back
        to the honestly-marked "unavailable" placeholder on empty/malformed
        content. Shared by the sync per-call path and the batch path."""
        parsed = _safe_json_loads(content, None) if content else None
        review_data = parsed if isinstance(parsed, dict) and "scores" in parsed else None

        if review_data is None:
            review_data = self._generate_unavailable_review(persona)

        try:
            scores = {ReviewDimension(k): int(v) for k, v in review_data["scores"].items()}
            decision = Decision(review_data["decision"])
        except (KeyError, ValueError):
            logger.warning("Reviewer '%s' returned malformed review data", persona.name)
            review_data = self._generate_unavailable_review(persona)
            scores = {ReviewDimension(k): int(v) for k, v in review_data["scores"].items()}
            decision = Decision(review_data["decision"])

        return Review(
            reviewer_id=persona.id,
            reviewer_name=persona.name,
            scores=scores,
            overall_score=float(review_data["overall_score"]),
            decision=decision,
            strengths=review_data["strengths"],
            weaknesses=review_data["weaknesses"],
            questions_for_authors=review_data["questions_for_authors"],
            confidence=int(review_data["confidence"]),
            detailed_feedback=review_data["detailed_feedback"],
        )

    def _extract_paper_text(self, paper_path: Path) -> str:
        """Extract text from paper (PDF or LaTeX)."""
        if paper_path.suffix == ".pdf":
            # Use existing PDF extractor
            from berb.web.pdf_extractor import PDFExtractor

            extractor = PDFExtractor()
            return extractor.extract_text(str(paper_path))

        elif paper_path.suffix in (".tex", ".md"):
            return paper_path.read_text(encoding="utf-8")

        else:
            raise ValueError(f"Unsupported paper format: {paper_path.suffix}")

    async def _generate_review(
        self,
        persona: ReviewerPersona,
        paper_text: str,
    ) -> Review:
        """Generate single review from persona via a real LLM call.

        Falls back to an honestly-marked "review unavailable" result (not a
        fabricated score) if no LLM client is configured or the call fails —
        this ensemble previously simulated plausible-looking scores with
        random.uniform(), which is worse than no score at all.
        """
        # Truncate paper if too long (LLM context limit)
        max_length = 50000  # Adjust based on model
        if len(paper_text) > max_length:
            paper_text = paper_text[:max_length] + "\n\n[... truncated ...]"

        # PAPER TEXT is passed via `cached_prefix` below rather than
        # embedded here — all 5 personas review the same paper, so keeping
        # it out of the (persona-varying) user turn lets it sit in a
        # provider-cached, shared system prefix instead of being resent in
        # full 5x per round (tasks/todo.md #2).
        prompt = self._build_review_prompt(persona)

        content = ""
        if self._llm_client is not None:
            try:
                response = self._llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system=persona.system_prompt,
                    cached_prefix=f"PAPER TEXT:\n{paper_text}",
                    cache_ttl="1h",
                )
                content = response.content if hasattr(response, "content") else str(response)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reviewer '%s' LLM call failed: %s", persona.name, exc)

        return self._parse_review_content(persona, content)

    def _generate_unavailable_review(self, persona: ReviewerPersona) -> dict[str, Any]:
        """Honest fallback when no real review could be obtained.

        Returns a conservative, clearly-marked placeholder rather than a
        fabricated plausible-looking score — this feeds into a report that
        a human/downstream LLM may act on, so it must not look like a real
        review.
        """
        scores = {dim.value: 5 for dim in ReviewDimension}
        return {
            "scores": scores,
            "overall_score": 5.0,
            "decision": "weak_reject",
            "strengths": [],
            "weaknesses": ["Review unavailable — no LLM client configured or call failed."],
            "questions_for_authors": [],
            "confidence": 1,
            "detailed_feedback": (
                f"[{persona.name}] Review could not be generated. This is a placeholder, "
                "not an actual assessment — do not treat these scores as real signal."
            ),
        }

    def area_chair_decision(self, reviews: list[Review]) -> MetaReview:
        """Area Chair meta-review aggregating all reviews.

        Args:
            reviews: List of 5 reviews

        Returns:
            MetaReview with aggregated decision
        """
        if len(reviews) != 5:
            logger.warning(f"Expected 5 reviews, got {len(reviews)}")

        # Calculate score statistics
        overall_scores = [r.overall_score for r in reviews]

        # Weighted average drives the actual decision — some reviewers
        # (e.g. Novelty & Significance) carry more weight than others.
        # Fall back to matching reviews by reviewer_id rather than assuming
        # `reviews` is in the same order as self._personas.
        persona_by_id = {p.id: p for p in self._personas}
        weighted_scores = [
            r.overall_score * persona_by_id[r.reviewer_id].weight
            for r in reviews
            if r.reviewer_id in persona_by_id
        ]
        total_weight = sum(
            persona_by_id[r.reviewer_id].weight for r in reviews if r.reviewer_id in persona_by_id
        )
        avg_score = (
            sum(weighted_scores) / total_weight
            if total_weight > 0
            else sum(overall_scores) / len(overall_scores)
        )

        # Score distribution
        score_distribution = {}
        for decision in Decision:
            count = sum(1 for r in reviews if r.decision == decision)
            if count > 0:
                score_distribution[decision.value] = count

        # Determine consensus decision
        if avg_score >= 8.5:
            consensus = Decision.STRONG_ACCEPT
        elif avg_score >= 6.5:
            consensus = Decision.ACCEPT
        elif avg_score >= 5.5:
            consensus = Decision.WEAK_ACCEPT
        elif avg_score >= 4.5:
            consensus = Decision.WEAK_REJECT
        elif avg_score >= 2.5:
            consensus = Decision.REJECT
        else:
            consensus = Decision.STRONG_REJECT

        # Calculate confidence (inverse of score std dev)
        import statistics

        score_std = statistics.stdev(overall_scores) if len(overall_scores) > 1 else 0
        confidence = max(0, 1 - (score_std / 5))  # Normalize to 0-1

        # Identify conflicts (high disagreement)
        conflicts = []
        max_diff = max(overall_scores) - min(overall_scores)
        if max_diff > 3:
            conflicts.append(f"High score variance: {max_diff:.1f} point spread")

        # Check for specific dimension disagreements
        for dim in ReviewDimension:
            dim_scores = [r.scores.get(dim, 5) for r in reviews]
            if max(dim_scores) - min(dim_scores) > 4:
                conflicts.append(f"Disagreement on {dim.value}")

        # Acceptance recommendation
        if consensus in (Decision.STRONG_ACCEPT, Decision.ACCEPT):
            recommendation = "ACCEPT"
        elif consensus == Decision.WEAK_ACCEPT:
            recommendation = "BORDERLINE - Discuss at AC meeting"
        elif consensus == Decision.WEAK_REJECT:
            recommendation = "BORDERLINE REJECT - Discuss at AC meeting"
        else:
            recommendation = "REJECT"

        # Generate meta-review text (recommendation passed in, not
        # recomputed via a recursive area_chair_decision() call — the
        # original recursive call here caused unbounded recursion)
        meta_review_text = self._generate_meta_review_text(
            reviews, avg_score, consensus, conflicts, recommendation
        )

        return MetaReview(
            reviews=reviews,
            average_score=round(avg_score, 2),
            score_std=round(score_std, 2),
            max_score=max(overall_scores),
            min_score=min(overall_scores),
            score_distribution=score_distribution,
            consensus_decision=consensus,
            confidence=round(confidence, 2),
            meta_review_text=meta_review_text,
            acceptance_recommendation=recommendation,
            reviewer_conflicts=conflicts,
        )

    def _generate_meta_review_text(
        self,
        reviews: list[Review],
        avg_score: float,
        consensus: Decision,
        conflicts: list[str],
        recommendation: str,
    ) -> str:
        """Generate Area Chair meta-review text."""
        lines = [
            "## Meta-Review",
            "",
            f"**Average Score:** {avg_score:.2f}/10",
            f"**Decision:** {consensus.value.replace('_', ' ').title()}",
            "",
            "## Review Summary",
            "",
        ]

        for i, review in enumerate(reviews, 1):
            lines.append(
                f"**Reviewer {i} ({review.reviewer_name}):** {review.overall_score:.1f}/10 - {review.decision.value.replace('_', ' ').title()}"
            )

        if conflicts:
            lines.extend(
                [
                    "",
                    "## Areas of Disagreement",
                    "",
                ]
            )
            for conflict in conflicts:
                lines.append(f"- {conflict}")

        lines.extend(
            [
                "",
                "## Area Chair Recommendation",
                "",
                f"This paper receives an average score of {avg_score:.2f}/10 from 5 reviewers. ",
                f"The reviews show {'strong agreement' if len(conflicts) == 0 else 'notable disagreement'}.",
                "",
                "**Recommendation:** " + recommendation,
            ]
        )

        return "\n".join(lines)

    def generate_review_report(
        self,
        reviews: list[Review],
        meta_review: MetaReview,
        output_path: str | Path | None = None,
    ) -> str:
        """Generate comprehensive review report.

        Args:
            reviews: List of reviews
            meta_review: Meta-review
            output_path: Optional path to save report

        Returns:
            Report text
        """
        lines = [
            "# Automated Peer Review Report",
            "",
            f"**Generated:** {__import__('datetime').datetime.now().isoformat()}",
            "",
            "## Meta-Review Summary",
            "",
            meta_review.meta_review_text,
            "",
            "## Individual Reviews",
            "",
        ]

        for i, review in enumerate(reviews, 1):
            lines.extend(
                [
                    f"### Review {i}: {review.reviewer_name}",
                    "",
                    f"**Overall Score:** {review.overall_score:.2f}/10",
                    f"**Decision:** {review.decision.value.replace('_', ' ').title()}",
                    f"**Confidence:** {review.confidence}/5",
                    "",
                    "**Scores by Dimension:**",
                ]
            )

            for dim, score in review.scores.items():
                lines.append(f"- {dim.value.replace('_', ' ').title()}: {score}/10")

            lines.extend(
                [
                    "",
                    "**Strengths:**",
                ]
            )
            for strength in review.strengths:
                lines.append(f"- {strength}")

            lines.extend(
                [
                    "",
                    "**Weaknesses:**",
                ]
            )
            for weakness in review.weaknesses:
                lines.append(f"- {weakness}")

            lines.extend(
                [
                    "",
                    "**Questions for Authors:**",
                ]
            )
            for question in review.questions_for_authors:
                lines.append(f"- {question}")

            lines.extend(
                [
                    "",
                    "**Detailed Feedback:**",
                    "",
                    review.detailed_feedback,
                    "",
                    "---",
                    "",
                ]
            )

        report = "\n".join(lines)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"Review report saved to {output_path}")

        return report


# Convenience function
async def review_paper(paper_path: str | Path) -> tuple[list[Review], MetaReview]:
    """Quick function to review a paper.

    Args:
        paper_path: Path to paper

    Returns:
        Tuple of (reviews, meta_review)
    """
    ensemble = AutomatedReviewerEnsemble()
    reviews = await ensemble.review_paper(paper_path)
    meta_review = ensemble.area_chair_decision(reviews)
    return reviews, meta_review
