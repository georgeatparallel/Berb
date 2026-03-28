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

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReviewDimension(str, Enum):
    """Review dimensions based on NeurIPS guidelines."""
    NOVELTY = "novelty"  # 1-10
    SIGNIFICANCE = "significance"  # 1-10
    TECHNICAL_QUALITY = "technical_quality"  # 1-10
    EXPERIMENTAL_RIGOR = "experimental_rigor"  # 1-10
    CLARITY = "clarity"  # 1-10
    REPRODUCIBILITY = "reproducibility"  # 1-10


class Decision(str, Enum):
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

Provide specific examples from the paper to justify your scores."""
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

Be meticulous. A single critical error should significantly lower your score."""
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

Be skeptical of claims without proper experimental support."""
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

A well-written paper should be accessible to a knowledgeable ML researcher who is not an expert in this specific subfield."""
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
A paper with no code and vague details should score 3-5."""
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
    ) -> list[Review]:
        """Generate 5 independent reviews.
        
        Args:
            paper_path: Path to paper (PDF or LaTeX)
            paper_text: Optional pre-extracted paper text
            
        Returns:
            List of 5 reviews
        """
        paper_path = Path(paper_path)
        
        # Extract paper text if not provided
        if paper_text is None:
            paper_text = self._extract_paper_text(paper_path)
        
        # Generate reviews in parallel
        import asyncio
        review_tasks = [
            self._generate_review(persona, paper_text)
            for persona in self._personas
        ]
        
        reviews = await asyncio.gather(*review_tasks)
        
        logger.info(f"Generated {len(reviews)} reviews for {paper_path.name}")
        return list(reviews)
    
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
        """Generate single review from persona."""
        # Truncate paper if too long (LLM context limit)
        max_length = 50000  # Adjust based on model
        if len(paper_text) > max_length:
            paper_text = paper_text[:max_length] + "\n\n[... truncated ...]"
        
        # Build review prompt
        prompt = f"""{persona.system_prompt}

PAPER TEXT:
{paper_text}

OUTPUT FORMAT (JSON):
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

Focus on your assigned areas: {', '.join(persona.focus_areas)}
"""
        
        # Call LLM (placeholder - integrate with actual LLM client)
        # In production:
        # response = await self._llm_client.chat(
        #     messages=[{"role": "user", "content": prompt}],
        #     json_mode=True
        # )
        # review_data = json.loads(response.content)
        
        # Placeholder for now
        review_data = self._generate_placeholder_review(persona)
        
        return Review(
            reviewer_id=persona.id,
            reviewer_name=persona.name,
            scores={ReviewDimension(k): v for k, v in review_data["scores"].items()},
            overall_score=review_data["overall_score"],
            decision=Decision(review_data["decision"]),
            strengths=review_data["strengths"],
            weaknesses=review_data["weaknesses"],
            questions_for_authors=review_data["questions_for_authors"],
            confidence=review_data["confidence"],
            detailed_feedback=review_data["detailed_feedback"],
        )
    
    def _generate_placeholder_review(self, persona: ReviewerPersona) -> dict:
        """Generate placeholder review (replace with actual LLM call)."""
        import random
        
        # Simulate reviewer scores based on persona focus
        base_score = random.uniform(5.5, 7.5)
        
        scores = {}
        for dim in ReviewDimension:
            if dim in persona.focus_areas:
                # Higher variance in focus areas
                scores[dim.value] = int(random.uniform(4, 9))
            else:
                # Lower variance in non-focus areas
                scores[dim.value] = int(random.uniform(5, 7))
        
        overall = sum(scores.values()) / len(scores)
        
        if overall >= 9:
            decision = "strong_accept"
        elif overall >= 7:
            decision = "accept"
        elif overall >= 6:
            decision = "weak_accept"
        elif overall >= 5:
            decision = "weak_reject"
        elif overall >= 3:
            decision = "reject"
        else:
            decision = "strong_reject"
        
        return {
            "scores": scores,
            "overall_score": round(overall, 2),
            "decision": decision,
            "strengths": [
                f"Strong {persona.focus_areas[0].value} contribution",
                "Well-motivated problem",
            ],
            "weaknesses": [
                "Could benefit from additional baselines",
                "Some claims need stronger evidence",
            ],
            "questions_for_authors": [
                "How does this compare to [recent related work]?",
                "What is the computational cost?",
            ],
            "confidence": random.randint(3, 5),
            "detailed_feedback": f"As a {persona.name}, I find this paper ... [detailed review]",
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
        avg_score = sum(overall_scores) / len(overall_scores)
        
        # Weighted average (some reviewers have higher weight)
        weighted_scores = [
            r.overall_score * self._personas[i].weight
            for i, r in enumerate(reviews)
        ]
        weighted_avg = sum(weighted_scores) / sum(p.weight for p in self._personas)
        
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
        
        # Generate meta-review text
        meta_review_text = self._generate_meta_review_text(
            reviews, avg_score, consensus, conflicts
        )
        
        # Acceptance recommendation
        if consensus in (Decision.STRONG_ACCEPT, Decision.ACCEPT):
            recommendation = "ACCEPT"
        elif consensus == Decision.WEAK_ACCEPT:
            recommendation = "BORDERLINE - Discuss at AC meeting"
        elif consensus == Decision.WEAK_REJECT:
            recommendation = "BORDERLINE REJECT - Discuss at AC meeting"
        else:
            recommendation = "REJECT"
        
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
            lines.append(f"**Reviewer {i} ({review.reviewer_name}):** {review.overall_score:.1f}/10 - {review.decision.value.replace('_', ' ').title()}")
        
        if conflicts:
            lines.extend([
                "",
                "## Areas of Disagreement",
                "",
            ])
            for conflict in conflicts:
                lines.append(f"- {conflict}")
        
        lines.extend([
            "",
            "## Area Chair Recommendation",
            "",
            f"This paper receives an average score of {avg_score:.2f}/10 from 5 reviewers. ",
            f"The reviews show {'strong agreement' if len(conflicts) == 0 else 'notable disagreement'}.",
            "",
            "**Recommendation:** " + self.area_chair_decision(reviews).acceptance_recommendation,
        ])
        
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
            lines.extend([
                f"### Review {i}: {review.reviewer_name}",
                "",
                f"**Overall Score:** {review.overall_score:.2f}/10",
                f"**Decision:** {review.decision.value.replace('_', ' ').title()}",
                f"**Confidence:** {review.confidence}/5",
                "",
                "**Scores by Dimension:**",
            ])
            
            for dim, score in review.scores.items():
                lines.append(f"- {dim.value.replace('_', ' ').title()}: {score}/10")
            
            lines.extend([
                "",
                "**Strengths:**",
            ])
            for strength in review.strengths:
                lines.append(f"- {strength}")
            
            lines.extend([
                "",
                "**Weaknesses:**",
            ])
            for weakness in review.weaknesses:
                lines.append(f"- {weakness}")
            
            lines.extend([
                "",
                "**Questions for Authors:**",
            ])
            for question in review.questions_for_authors:
                lines.append(f"- {question}")
            
            lines.extend([
                "",
                "**Detailed Feedback:**",
                "",
                review.detailed_feedback,
                "",
                "---",
                "",
            ])
        
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
