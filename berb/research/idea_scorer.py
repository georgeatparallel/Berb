"""Idea Quality Scoring and Ranking for Berb.

Based on AI Scientist (Nature 2026) - Section 3.1

Scores research ideas on 5 dimensions:
1. Novelty (vs existing literature)
2. Feasibility (computational resources, time)
3. Impact (potential citations, significance)
4. Clarity (well-defined problem)
5. Testability (can be empirically validated)

Ranks ideas and pursues top-k, tracking score vs actual outcome for learning.

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.research.idea_scorer import IdeaQualityScorer
    
    scorer = IdeaQualityScorer()
    scored_ideas = await scorer.score_ideas(ideas)
    top_ideas = scorer.get_top_k(scored_ideas, k=3)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class NoveltyLevel(str, Enum):
    """Novelty classification."""
    GROUNDBREAKING = "groundbreaking"  # 9-10: Paradigm shift
    HIGHLY_NOVEL = "highly_novel"  # 7-8: Significant advance
    MODERATELY_NOVEL = "moderately_novel"  # 5-6: Solid improvement
    INCREMENTAL = "incremental"  # 3-4: Minor variation
    DERIVATIVE = "derivative"  # 1-2: Already published


@dataclass
class ResearchIdea:
    """A research idea to be scored."""
    
    id: str
    title: str
    description: str
    domain: str
    keywords: list[str] = field(default_factory=list)
    related_work: list[str] = field(default_factory=list)
    proposed_method: str = ""
    expected_contributions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredIdea:
    """Research idea with quality scores."""
    
    idea: ResearchIdea
    novelty_score: float = 0.0  # 1-10
    feasibility_score: float = 0.0  # 1-10
    impact_score: float = 0.0  # 1-10
    clarity_score: float = 0.0  # 1-10
    testability_score: float = 0.0  # 1-10
    overall_score: float = 0.0  # Weighted average
    novelty_level: NoveltyLevel = NoveltyLevel.INCREMENTAL
    confidence: float = 0.0  # 0-1 confidence in scores
    ranking: int = 0  # Rank among peer ideas
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0
    estimated_duration_hours: float = 0.0
    actual_outcome_score: float | None = None  # Filled in post-completion
    score_accuracy: float | None = None  # predicted vs actual
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.idea.id,
            "title": self.idea.title,
            "novelty_score": self.novelty_score,
            "feasibility_score": self.feasibility_score,
            "impact_score": self.impact_score,
            "clarity_score": self.clarity_score,
            "testability_score": self.testability_score,
            "overall_score": self.overall_score,
            "novelty_level": self.novelty_level.value,
            "confidence": self.confidence,
            "ranking": self.ranking,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "risks": self.risks,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_duration_hours": self.estimated_duration_hours,
            "actual_outcome_score": self.actual_outcome_score,
            "score_accuracy": self.score_accuracy,
        }


@dataclass
class ScoringConfig:
    """Configuration for idea scoring."""
    
    weights: dict[str, float] = field(default_factory=lambda: {
        "novelty": 0.25,
        "feasibility": 0.20,
        "impact": 0.25,
        "clarity": 0.15,
        "testability": 0.15,
    })
    min_overall_score: float = 5.0  # Minimum to pursue
    top_k: int = 3  # Number of top ideas to pursue
    calibrate_from_history: bool = True  # Use historical data for calibration


class IdeaQualityScorer:
    """Score and rank research ideas."""
    
    def __init__(
        self,
        config: ScoringConfig | None = None,
        llm_client: Any | None = None,
    ) -> None:
        """Initialize idea scorer.
        
        Args:
            config: Scoring configuration
            llm_client: LLM client for scoring
        """
        self._config = config or ScoringConfig()
        self._llm_client = llm_client
        self._scoring_history: list[ScoredIdea] = []
        self._calibration_data: list[dict] = []
    
    async def score_ideas(
        self,
        ideas: list[ResearchIdea],
        domain_context: str = "",
    ) -> list[ScoredIdea]:
        """Score a list of research ideas.
        
        Args:
            ideas: Ideas to score
            domain_context: Optional domain context for scoring
            
        Returns:
            List of scored ideas, ranked by overall score
        """
        logger.info(f"Scoring {len(ideas)} research ideas")
        
        scored_ideas = []
        
        for idea in ideas:
            scored = await self._score_single_idea(idea, domain_context)
            scored_ideas.append(scored)
        
        # Rank by overall score
        scored_ideas.sort(key=lambda x: x.overall_score, reverse=True)
        
        # Assign rankings
        for i, scored in enumerate(scored_ideas, 1):
            scored.ranking = i
        
        # Store in history
        self._scoring_history.extend(scored_ideas)
        
        logger.info(
            f"Scoring complete. Top idea: {scored_ideas[0].idea.title} "
            f"(score: {scored_ideas[0].overall_score:.2f})"
        )
        
        return scored_ideas
    
    async def _score_single_idea(
        self,
        idea: ResearchIdea,
        domain_context: str,
    ) -> ScoredIdea:
        """Score a single research idea."""
        scored = ScoredIdea(idea=idea)
        
        # Build scoring prompt
        prompt = self._build_scoring_prompt(idea, domain_context)
        
        # Call LLM for scoring (placeholder)
        # In production:
        # response = await self._llm_client.chat(
        #     messages=[{"role": "user", "content": prompt}],
        #     json_mode=True
        # )
        # scores_data = json.loads(response.content)
        
        # Placeholder: generate synthetic scores
        scores_data = self._generate_placeholder_scores(idea)
        
        # Extract scores
        scored.novelty_score = scores_data.get("novelty_score", 5.0)
        scored.feasibility_score = scores_data.get("feasibility_score", 5.0)
        scored.impact_score = scores_data.get("impact_score", 5.0)
        scored.clarity_score = scores_data.get("clarity_score", 5.0)
        scored.testability_score = scores_data.get("testability_score", 5.0)
        scored.confidence = scores_data.get("confidence", 0.7)
        
        # Calculate weighted overall score
        weights = self._config.weights
        scored.overall_score = (
            scored.novelty_score * weights["novelty"] +
            scored.feasibility_score * weights["feasibility"] +
            scored.impact_score * weights["impact"] +
            scored.clarity_score * weights["clarity"] +
            scored.testability_score * weights["testability"]
        )
        
        # Determine novelty level
        scored.novelty_level = self._classify_novelty(scored.novelty_score)
        
        # Extract qualitative feedback
        scored.strengths = scores_data.get("strengths", [])
        scored.weaknesses = scores_data.get("weaknesses", [])
        scored.risks = scores_data.get("risks", [])
        
        # Estimate cost and duration
        scored.estimated_cost_usd = self._estimate_cost(idea, scored)
        scored.estimated_duration_hours = self._estimate_duration(idea, scored)
        
        return scored
    
    def _build_scoring_prompt(
        self,
        idea: ResearchIdea,
        domain_context: str,
    ) -> str:
        """Build LLM prompt for scoring."""
        return f"""You are an expert research reviewer evaluating a research idea.

Score this idea on 5 dimensions (1-10 scale):

1. NOVELTY: How novel is this idea compared to existing work?
   - 9-10: Groundbreaking, paradigm-shifting
   - 7-8: Highly novel, significant advance
   - 5-6: Moderately novel, solid improvement
   - 3-4: Incremental, minor variation
   - 1-2: Derivative, already published

2. FEASIBILITY: Can this be done with reasonable resources?
   - Consider: computational cost, data availability, time

3. IMPACT: If successful, how impactful would this be?
   - Consider: citations, practical applications, field advancement

4. CLARITY: Is the problem well-defined?
   - Consider: clear objectives, measurable outcomes

5. TESTABILITY: Can claims be empirically validated?
   - Consider: measurable metrics, baselines, statistical tests

IDEA:
Title: {idea.title}
Description: {idea.description}
Domain: {idea.domain}
Keywords: {', '.join(idea.keywords)}
Proposed Method: {idea.proposed_method}
Expected Contributions: {', '.join(idea.expected_contributions)}

{f"Domain Context: {domain_context}" if domain_context else ""}

OUTPUT FORMAT (JSON):
{{
    "novelty_score": <1-10>,
    "feasibility_score": <1-10>,
    "impact_score": <1-10>,
    "clarity_score": <1-10>,
    "testability_score": <1-10>,
    "confidence": <0-1>,
    "strengths": ["strength 1", ...],
    "weaknesses": ["weakness 1", ...],
    "risks": ["risk 1", ...],
    "reasoning": "<brief explanation>"
}}
"""
    
    def _generate_placeholder_scores(
        self,
        idea: ResearchIdea,
    ) -> dict[str, Any]:
        """Generate placeholder scores (replace with LLM call)."""
        import random
        
        # Base scores on idea characteristics (placeholder logic)
        base_novelty = random.uniform(5.0, 8.0)
        
        return {
            "novelty_score": base_novelty,
            "feasibility_score": random.uniform(6.0, 9.0),
            "impact_score": random.uniform(5.0, 8.5),
            "clarity_score": random.uniform(6.0, 9.0),
            "testability_score": random.uniform(6.0, 9.0),
            "confidence": random.uniform(0.6, 0.9),
            "strengths": [
                "Well-motivated problem",
                "Clear methodology proposed",
            ],
            "weaknesses": [
                "Could benefit from additional baselines",
                "Computational cost may be high",
            ],
            "risks": [
                "May require more data than available",
                "Results may be incremental",
            ],
        }
    
    def _classify_novelty(self, score: float) -> NoveltyLevel:
        """Classify novelty level from score."""
        if score >= 9.0:
            return NoveltyLevel.GROUNDBREAKING
        elif score >= 7.0:
            return NoveltyLevel.HIGHLY_NOVEL
        elif score >= 5.0:
            return NoveltyLevel.MODERATELY_NOVEL
        elif score >= 3.0:
            return NoveltyLevel.INCREMENTAL
        else:
            return NoveltyLevel.DERIVATIVE
    
    def _estimate_cost(
        self,
        idea: ResearchIdea,
        scored: ScoredIdea,
    ) -> float:
        """Estimate cost to pursue this idea."""
        # Base cost on feasibility and complexity
        base_cost = 0.50  # Base $0.50
        
        # Adjust based on scores
        if scored.feasibility_score < 5.0:
            base_cost *= 1.5  # Harder = more expensive
        
        if "large-scale" in idea.description.lower() or "training" in idea.description.lower():
            base_cost *= 2.0  # Large experiments cost more
        
        return round(base_cost, 2)
    
    def _estimate_duration(
        self,
        idea: ResearchIdea,
        scored: ScoredIdea,
    ) -> float:
        """Estimate duration in hours."""
        base_hours = 2.0  # Base 2 hours
        
        if scored.feasibility_score < 5.0:
            base_hours *= 1.5
        
        if scored.testability_score < 6.0:
            base_hours *= 1.3  # Harder to test = more time
        
        return round(base_hours, 1)
    
    def get_top_k(
        self,
        scored_ideas: list[ScoredIdea],
        k: int | None = None,
    ) -> list[ScoredIdea]:
        """Get top-k scored ideas.
        
        Args:
            scored_ideas: List of scored ideas
            k: Number to return (uses config default if None)
            
        Returns:
            Top-k ideas
        """
        k = k or self._config.top_k
        
        # Filter by minimum score
        qualified = [
            idea for idea in scored_ideas
            if idea.overall_score >= self._config.min_overall_score
        ]
        
        # Return top-k
        return qualified[:k]
    
    def record_outcome(
        self,
        idea_id: str,
        actual_score: float,
        success: bool,
    ) -> None:
        """Record actual outcome for calibration.
        
        Call this after an idea is pursued to track prediction accuracy.
        
        Args:
            idea_id: ID of the idea
            actual_score: Actual quality score achieved
            success: Whether the idea was successful
        """
        # Find the scored idea
        for scored in self._scoring_history:
            if scored.idea.id == idea_id:
                scored.actual_outcome_score = actual_score
                
                # Calculate accuracy
                if scored.overall_score > 0:
                    accuracy = 1.0 - abs(actual_score - scored.overall_score) / 10.0
                    scored.score_accuracy = max(0.0, accuracy)
                
                # Add to calibration data
                self._calibration_data.append({
                    "predicted": scored.overall_score,
                    "actual": actual_score,
                    "success": success,
                    "accuracy": scored.score_accuracy,
                })
                
                logger.info(
                    f"Recorded outcome for idea {idea_id}: "
                    f"predicted={scored.overall_score:.2f}, "
                    f"actual={actual_score:.2f}, "
                    f"accuracy={scored.score_accuracy:.2f}"
                )
                break
    
    def get_calibration_statistics(self) -> dict[str, Any]:
        """Get statistics on scoring accuracy."""
        if not self._calibration_data:
            return {"error": "No calibration data available"}
        
        accuracies = [d["accuracy"] for d in self._calibration_data]
        predicted = [d["predicted"] for d in self._calibration_data]
        actual = [d["actual"] for d in self._calibration_data]
        
        return {
            "total_ideas_tracked": len(self._calibration_data),
            "avg_accuracy": sum(accuracies) / len(accuracies),
            "min_accuracy": min(accuracies),
            "max_accuracy": max(accuracies),
            "avg_predicted_score": sum(predicted) / len(predicted),
            "avg_actual_score": sum(actual) / len(actual),
            "success_rate": sum(1 for d in self._calibration_data if d["success"]) / len(self._calibration_data),
        }
    
    def get_scoring_statistics(self) -> dict[str, Any]:
        """Get general scoring statistics."""
        if not self._scoring_history:
            return {"error": "No ideas scored yet"}
        
        scores = [s.overall_score for s in self._scoring_history]
        
        novelty_levels = {}
        for idea in self._scoring_history:
            level = idea.novelty_level.value
            novelty_levels[level] = novelty_levels.get(level, 0) + 1
        
        return {
            "total_ideas_scored": len(self._scoring_history),
            "avg_overall_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "novelty_distribution": novelty_levels,
            "ideas_above_threshold": sum(
                1 for s in self._scoring_history
                if s.overall_score >= self._config.min_overall_score
            ),
        }


# Convenience function
async def score_and_rank_ideas(
    ideas: list[ResearchIdea],
    top_k: int = 3,
) -> list[ScoredIdea]:
    """Quick function to score and rank ideas.
    
    Args:
        ideas: Ideas to score
        top_k: Number of top ideas to return
        
    Returns:
        Top-k scored ideas
    """
    config = ScoringConfig(top_k=top_k)
    scorer = IdeaQualityScorer(config)
    
    all_scored = await scorer.score_ideas(ideas)
    return scorer.get_top_k(all_scored, top_k)
