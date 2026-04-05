"""Research gap analysis engine with multi-perspective reasoning.

This module identifies research gaps systematically using multiple
perspectives (novelty, feasibility, impact, temporal) to ensure
comprehensive gap coverage.

Uses Multi-Perspective reasoning for parallel gap identification.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from berb.reasoning.multi_perspective import (
    MultiPerspectiveMethod,
    PerspectiveType,
    PerspectiveResult,
)
from berb.reasoning.base import ReasoningContext, ReasoningResult
from berb.llm.client import LLMProvider

logger = logging.getLogger(__name__)


class GapType(str, Enum):
    """Type of research gap.

    Attributes:
        LITERATURE: Topic understudied or unexplored
        METHODOLOGY: Existing methods have limitations
        APPLICATION: Not applied to domain X yet
        INTERDISCIPLINARY: Gap between fields
        TEMPORAL: Outdated studies need updating
        DATA: Lack of data or benchmarks
        THEORETICAL: Missing theoretical framework
    """

    LITERATURE = "literature"
    METHODOLOGY = "methodology"
    APPLICATION = "application"
    INTERDISCIPLINARY = "interdisciplinary"
    TEMPORAL = "temporal"
    DATA = "data"
    THEORETICAL = "theoretical"


class ResearchGap(BaseModel):
    """Identified research gap.

    Attributes:
        id: Unique gap identifier
        type: Type of gap
        description: Detailed description
        domain: Research domain
        novelty_score: Novelty score (0-10)
        feasibility_score: Feasibility score (0-10)
        impact_score: Potential impact score (0-10)
        priority_score: Overall priority (novelty × feasibility × impact)
        supporting_evidence: Evidence supporting this gap
        related_works: Related existing works
        suggested_approach: Suggested research approach
        estimated_effort: Estimated effort (low/medium/high)
        perspective_origin: Which perspective identified this gap
    """

    id: str
    type: GapType
    description: str
    domain: str = ""
    novelty_score: float = Field(default=5.0, ge=0.0, le=10.0)
    feasibility_score: float = Field(default=5.0, ge=0.0, le=10.0)
    impact_score: float = Field(default=5.0, ge=0.0, le=10.0)
    priority_score: float = Field(default=0.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    related_works: list[str] = Field(default_factory=list)
    suggested_approach: str = ""
    estimated_effort: Literal["low", "medium", "high"] = "medium"
    perspective_origin: str = ""

    def compute_priority(self) -> float:
        """Compute priority score from component scores.

        Returns:
            Priority score (0-1000)
        """
        self.priority_score = (
            self.novelty_score * self.feasibility_score * self.impact_score
        )
        return self.priority_score


class GapAnalysisResult(BaseModel):
    """Result of gap analysis.

    Attributes:
        topic: Analyzed topic
        gaps: List of identified gaps
        total_gaps: Total number of gaps
        gaps_by_type: Count of gaps by type
        top_gaps: Top 5 gaps by priority
        analysis_timestamp: When analysis was performed
        perspectives_used: Which perspectives were used
    """

    topic: str
    gaps: list[ResearchGap] = Field(default_factory=list)
    total_gaps: int = 0
    gaps_by_type: dict[str, int] = Field(default_factory=dict)
    top_gaps: list[ResearchGap] = Field(default_factory=list)
    analysis_timestamp: str = ""
    perspectives_used: list[str] = Field(default_factory=list)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Auto-compute totals
        self.total_gaps = len(self.gaps)
        self._compute_gaps_by_type()
        self._compute_top_gaps()

    def _compute_gaps_by_type(self) -> None:
        """Compute gap counts by type."""
        type_counts: dict[str, int] = {}
        for gap in self.gaps:
            type_name = gap.type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        self.gaps_by_type = type_counts

    def _compute_top_gaps(self) -> None:
        """Get top 5 gaps by priority."""
        sorted_gaps = sorted(
            self.gaps, key=lambda g: g.priority_score, reverse=True
        )
        self.top_gaps = sorted_gaps[:5]


class GapAnalysisConfig(BaseModel):
    """Configuration for gap analysis.

    Attributes:
        use_multi_perspective: Whether to use multi-perspective reasoning
        perspectives: List of perspectives to use
        min_novelty_score: Minimum novelty score for gaps
        max_gaps: Maximum number of gaps to return
        llm_provider: LLM provider for reasoning
    """

    use_multi_perspective: bool = True
    perspectives: list[str] = Field(
        default_factory=lambda: [
            "novelty_seeker",
            "practitioner",
            "interdisciplinary",
            "temporal",
        ]
    )
    min_novelty_score: float = 3.0
    max_gaps: int = 20
    llm_provider: LLMProvider | None = None


class ResearchGapAnalyzer:
    """Systematic research gap analyzer using multi-perspective reasoning.

    This analyzer:
    1. Analyzes literature synthesis from multiple perspectives
    2. Identifies gaps from each perspective
    3. Scores gaps by novelty, feasibility, and impact
    4. Prioritizes gaps for hypothesis generation

    Usage::

        analyzer = ResearchGapAnalyzer(
            config=GapAnalysisConfig(
                use_multi_perspective=True,
                llm_provider=llm_provider,
            ),
        )

        gaps = await analyzer.analyze(
            topic="quantum error correction",
            synthesis="Literature synthesis...",
            literature_review=[paper1, paper2, ...],
        )

    Attributes:
        config: Configuration
        multi_perspective_method: Multi-perspective reasoning method
    """

    # Perspective definitions for gap analysis
    PERSPECTIVE_DEFINITIONS = {
        "novelty_seeker": {
            "role": "Novelty Seeker",
            "question": "What hasn't been tried yet? What would be genuinely new?",
            "gap_types": [GapType.LITERATURE, GapType.THEORETICAL],
        },
        "practitioner": {
            "role": "Practitioner",
            "question": "What's infeasible with current methods? What fails in practice?",
            "gap_types": [GapType.METHODOLOGY, GapType.DATA],
        },
        "interdisciplinary": {
            "role": "Interdisciplinary Bridge-Builder",
            "question": "What methods from other fields could apply here?",
            "gap_types": [GapType.INTERDISCIPLINARY, GapType.APPLICATION],
        },
        "temporal": {
            "role": "Temporal Analyst",
            "question": "What's outdated and needs updating with new data/methods?",
            "gap_types": [GapType.TEMPORAL],
        },
    }

    def __init__(self, config: GapAnalysisConfig | None = None):
        """Initialize gap analyzer.

        Args:
            config: Configuration
        """
        self.config = config or GapAnalysisConfig()

        # Initialize multi-perspective method
        self.multi_perspective_method = None
        if self.config.llm_provider and self.config.use_multi_perspective:
            self.multi_perspective_method = MultiPerspectiveMethod(
                llm_client=self.config.llm_provider,
            )

    async def analyze(
        self,
        topic: str,
        synthesis: str = "",
        literature_review: list[dict[str, Any]] | None = None,
        domain: str = "",
    ) -> GapAnalysisResult:
        """Analyze research topic for gaps.

        Args:
            topic: Research topic
            synthesis: Literature synthesis (optional)
            literature_review: List of paper metadata (optional)
            domain: Research domain

        Returns:
            GapAnalysisResult with identified gaps
        """
        logger.info(f"Starting gap analysis for topic: {topic}")

        # Build analysis context
        context = self._build_analysis_context(
            topic, synthesis, literature_review, domain
        )

        # Identify gaps using multi-perspective reasoning
        if self.multi_perspective_method:
            gaps = await self._multi_perspective_analysis(context)
        else:
            # Fallback to heuristic analysis
            gaps = await self._heuristic_analysis(context)

        # Filter by novelty threshold
        filtered_gaps = [
            g for g in gaps
            if g.novelty_score >= self.config.min_novelty_score
        ]

        # Sort by priority and limit
        sorted_gaps = sorted(
            filtered_gaps, key=lambda g: g.priority_score, reverse=True
        )[: self.config.max_gaps]

        # Build result
        result = GapAnalysisResult(
            topic=topic,
            gaps=sorted_gaps,
            analysis_timestamp=datetime.now().isoformat(),
            perspectives_used=self.config.perspectives,
        )

        logger.info(
            f"Gap analysis complete: {len(sorted_gaps)} gaps identified, "
            f"top priority: {sorted_gaps[0].priority_score if sorted_gaps else 0:.1f}"
        )

        return result

    def _build_analysis_context(
        self,
        topic: str,
        synthesis: str,
        literature_review: list[dict[str, Any]] | None,
        domain: str,
    ) -> dict[str, Any]:
        """Build analysis context.

        Args:
            topic: Research topic
            synthesis: Literature synthesis
            literature_review: Paper metadata
            domain: Research domain

        Returns:
            Context dictionary
        """
        # Summarize literature if provided
        literature_summary = ""
        if literature_review:
            literature_summary = self._summarize_literature(literature_review)

        return {
            "topic": topic,
            "domain": domain,
            "synthesis": synthesis,
            "literature_summary": literature_summary,
            "key_themes": self._extract_key_themes(synthesis, literature_review),
            "limitations": self._extract_limitations(literature_review),
        }

    def _summarize_literature(
        self,
        papers: list[dict[str, Any]],
    ) -> str:
        """Summarize literature review.

        Args:
            papers: List of paper metadata

        Returns:
            Literature summary
        """
        if not papers:
            return ""

        # Extract key information
        years = [p.get("year", 0) for p in papers if p.get("year")]
        venues = [p.get("venue", "") for p in papers if p.get("venue")]
        citations = [p.get("citations", 0) for p in papers]

        summary_parts = [
            f"Analyzed {len(papers)} papers",
        ]

        if years:
            summary_parts.append(
                f"published between {min(years)}-{max(years)}"
            )

        if citations:
            summary_parts.append(
                f"with average {sum(citations)/len(citations):.0f} citations"
            )

        return ". ".join(summary_parts) + "."

    def _extract_key_themes(
        self,
        synthesis: str,
        literature_review: list[dict[str, Any]] | None,
    ) -> list[str]:
        """Extract key themes from literature.

        Args:
            synthesis: Literature synthesis
            literature_review: Paper metadata

        Returns:
            List of key themes
        """
        themes = []

        # Extract from synthesis (simplified - would use NLP in production)
        if synthesis:
            # Look for repeated terms
            words = synthesis.lower().split()
            word_freq: dict[str, int] = {}
            for word in words:
                if len(word) > 6:
                    word_freq[word] = word_freq.get(word, 0) + 1

            # Top frequent words are themes
            themes = sorted(
                word_freq.keys(),
                key=lambda w: word_freq[w],
                reverse=True,
            )[:10]

        return themes

    def _extract_limitations(
        self,
        literature_review: list[dict[str, Any]] | None,
    ) -> list[str]:
        """Extract limitations from literature.

        Args:
            literature_review: Paper metadata

        Returns:
            List of limitations
        """
        limitations = []

        if literature_review:
            for paper in literature_review:
                paper_limitations = paper.get("limitations", [])
                if paper_limitations:
                    limitations.extend(paper_limitations[:3])

        return limitations[:10]  # Top 10

    async def _multi_perspective_analysis(
        self,
        context: dict[str, Any],
    ) -> list[ResearchGap]:
        """Analyze gaps using multi-perspective reasoning.

        Args:
            context: Analysis context

        Returns:
            List of identified gaps
        """
        if not self.multi_perspective_method:
            return await self._heuristic_analysis(context)

        all_gaps: list[ResearchGap] = []

        # Run analysis from each perspective
        for perspective_name in self.config.perspectives:
            perspective_def = self.PERSPECTIVE_DEFINITIONS.get(
                perspective_name,
                {
                    "role": perspective_name,
                    "question": "What gaps exist?",
                    "gap_types": [GapType.LITERATURE],
                },
            )

            # Build perspective-specific problem
            problem = self._build_perspective_problem(
                context, perspective_def
            )

            # Execute perspective analysis
            try:
                perspective_result = await self._run_perspective(
                    problem, perspective_name
                )

                # Extract gaps from result
                gaps = self._extract_gaps_from_perspective(
                    perspective_result,
                    perspective_name,
                    perspective_def["gap_types"],
                    context["domain"],
                )

                all_gaps.extend(gaps)

            except Exception as e:
                logger.warning(
                    f"Perspective {perspective_name} failed: {e}"
                )

        # Deduplicate gaps
        unique_gaps = self._deduplicate_gaps(all_gaps)

        return unique_gaps

    def _build_perspective_problem(
        self,
        context: dict[str, Any],
        perspective_def: dict[str, Any],
    ) -> str:
        """Build problem statement for a perspective.

        Args:
            context: Analysis context
            perspective_def: Perspective definition

        Returns:
            Problem statement
        """
        problem = f"""Research Topic: {context['topic']}
Domain: {context['domain']}

Literature Summary: {context.get('literature_summary', 'Not provided')}

Key Themes: {', '.join(context.get('key_themes', [])[:5])}

Known Limitations: {', '.join(context.get('limitations', [])[:5])}

---

Role: {perspective_def['role']}
Your Task: {perspective_def['question']}

Identify specific research gaps from your perspective. For each gap:
1. Describe what's missing
2. Explain why it matters
3. Suggest how it could be addressed
"""
        return problem

    async def _run_perspective(
        self,
        problem: str,
        perspective_name: str,
    ) -> PerspectiveResult:
        """Run single perspective analysis.

        Args:
            problem: Problem statement
            perspective_name: Perspective name

        Returns:
            PerspectiveResult
        """
        context = ReasoningContext(
            stage_id="GAP_ANALYSIS",
            stage_name=f"Gap Analysis - {perspective_name}",
            input_data={"problem": problem},
        )

        result = await self.multi_perspective_method.execute(context)

        # Convert to PerspectiveResult
        return PerspectiveResult(
            perspective_type=PerspectiveType.CONSTRUCTIVE,
            content=result.output.get("content", "") if isinstance(result.output, dict) else str(result.output),
            reasoning=result.output.get("reasoning", "") if isinstance(result.output, dict) else "",
            confidence=0.7,
        )

    def _extract_gaps_from_perspective(
        self,
        result: PerspectiveResult,
        perspective_name: str,
        gap_types: list[GapType],
        domain: str,
    ) -> list[ResearchGap]:
        """Extract gaps from perspective result.

        Args:
            result: Perspective result
            perspective_name: Perspective name
            gap_types: Allowed gap types
            domain: Research domain

        Returns:
            List of ResearchGap objects
        """
        gaps = []
        content = result.content

        # Parse gaps from content (simplified - would use structured output in production)
        # Look for numbered or bulleted items
        import re

        gap_patterns = [
            r"(\d+[\.\)]\s*[A-Z][^.]+)",  # Numbered items
            r"(•\s*[A-Z][^.]+)",  # Bulleted items
            r"(Gap[:\s]+[A-Z][^.]+)",  # Explicit "Gap:" markers
        ]

        gap_id = 0
        for pattern in gap_patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            for match in matches:
                gap_id += 1
                gap_text = match.strip("• \n\t")

                # Score the gap (simplified heuristic)
                novelty = self._estimate_novelty(gap_text, result.content)
                feasibility = self._estimate_feasibility(gap_text)
                impact = self._estimate_impact(gap_text, domain)

                gap = ResearchGap(
                    id=f"gap_{perspective_name}_{gap_id}",
                    type=gap_types[gap_id % len(gap_types)],
                    description=gap_text,
                    domain=domain,
                    novelty_score=novelty,
                    feasibility_score=feasibility,
                    impact_score=impact,
                    perspective_origin=perspective_name,
                )
                gap.compute_priority()
                gaps.append(gap)

        return gaps[:5]  # Max 5 gaps per perspective

    def _estimate_novelty(
        self,
        gap_text: str,
        full_content: str,
    ) -> float:
        """Estimate novelty score for a gap.

        Args:
            gap_text: Gap description
            full_content: Full perspective content

        Returns:
            Novelty score (0-10)
        """
        # Keywords indicating high novelty
        novelty_keywords = [
            "first", "novel", "unexplored", "never", "new",
            "未曾", "新しい", "neu", "premier",
        ]

        score = 5.0  # Base score
        gap_lower = gap_text.lower()

        for keyword in novelty_keywords:
            if keyword.lower() in gap_lower:
                score += 1.0

        return min(10.0, score)

    def _estimate_feasibility(self, gap_text: str) -> float:
        """Estimate feasibility score for a gap.

        Args:
            gap_text: Gap description

        Returns:
            Feasibility score (0-10)
        """
        # Keywords indicating low feasibility
        difficulty_keywords = [
            "impossible", "infeasible", "extremely difficult",
            "prohibitive", "requires breakthrough",
        ]

        # Keywords indicating high feasibility
        easy_keywords = [
            "straightforward", "simple", "feasible",
            "can be done", "with existing",
        ]

        score = 6.0  # Base score (slightly optimistic)
        gap_lower = gap_text.lower()

        for keyword in difficulty_keywords:
            if keyword in gap_lower:
                score -= 1.5

        for keyword in easy_keywords:
            if keyword in gap_lower:
                score += 1.0

        return max(0.0, min(10.0, score))

    def _estimate_impact(self, gap_text: str, domain: str) -> float:
        """Estimate impact score for a gap.

        Args:
            gap_text: Gap description
            domain: Research domain

        Returns:
            Impact score (0-10)
        """
        # Keywords indicating high impact
        impact_keywords = [
            "significant", "important", "critical", "essential",
            "broad", "wide", "many", "fundamental",
            "practical", "real-world", "application",
        ]

        score = 5.0  # Base score
        gap_lower = gap_text.lower()

        for keyword in impact_keywords:
            if keyword in gap_lower:
                score += 0.8

        return min(10.0, score)

    async def _heuristic_analysis(
        self,
        context: dict[str, Any],
    ) -> list[ResearchGap]:
        """Heuristic gap analysis without LLM.

        Args:
            context: Analysis context

        Returns:
            List of identified gaps
        """
        gaps = []

        # Generate gaps from known limitations
        for i, limitation in enumerate(context.get("limitations", [])[:5]):
            gap = ResearchGap(
                id=f"gap_heuristic_{i}",
                type=GapType.METHODOLOGY,
                description=f"Address limitation: {limitation}",
                domain=context["domain"],
                novelty_score=5.0,
                feasibility_score=6.0,
                impact_score=6.0,
                perspective_origin="heuristic",
            )
            gap.compute_priority()
            gaps.append(gap)

        # Generate gaps from themes
        for i, theme in enumerate(context.get("key_themes", [])[:5]):
            gap = ResearchGap(
                id=f"gap_theme_{i}",
                type=GapType.LITERATURE,
                description=f"Explore {theme} further",
                domain=context["domain"],
                novelty_score=4.0,
                feasibility_score=7.0,
                impact_score=5.0,
                perspective_origin="heuristic",
            )
            gap.compute_priority()
            gaps.append(gap)

        return gaps

    def _deduplicate_gaps(
        self,
        gaps: list[ResearchGap],
    ) -> list[ResearchGap]:
        """Deduplicate similar gaps.

        Args:
            gaps: List of gaps

        Returns:
            Deduplicated list
        """
        unique: dict[str, ResearchGap] = {}

        for gap in gaps:
            # Create similarity key (first 50 chars normalized)
            key = gap.description[:50].lower().strip()

            if key not in unique:
                unique[key] = gap
            else:
                # Keep higher priority gap
                if gap.priority_score > unique[key].priority_score:
                    unique[key] = gap

        return list(unique.values())


class GapToHypothesisConverter:
    """Convert research gaps to hypotheses.

    This converter takes identified gaps and generates
    testable hypotheses for Stage 8 (HYPOTHESIS_GEN).

    Usage::

        converter = GapToHypothesisConverter()
        hypotheses = await converter.convert(gaps)
    """

    async def convert(
        self,
        gaps: list[ResearchGap],
        max_hypotheses: int = 5,
    ) -> list[dict[str, Any]]:
        """Convert gaps to hypotheses.

        Args:
            gaps: List of research gaps
            max_hypotheses: Maximum hypotheses to generate

        Returns:
            List of hypothesis dictionaries
        """
        hypotheses = []

        # Top gaps become hypotheses
        sorted_gaps = sorted(
            gaps, key=lambda g: g.priority_score, reverse=True
        )[:max_hypotheses]

        for gap in sorted_gaps:
            hypothesis = {
                "title": f"Address {gap.type.value} gap: {gap.description[:50]}",
                "description": gap.description,
                "novelty_score": gap.novelty_score,
                "feasibility_score": gap.feasibility_score,
                "impact_score": gap.impact_score,
                "suggested_approach": gap.suggested_approach,
                "estimated_effort": gap.estimated_effort,
                "gap_id": gap.id,
            }
            hypotheses.append(hypothesis)

        return hypotheses


# Convenience function
async def analyze_research_gaps(
    topic: str,
    synthesis: str = "",
    literature_review: list[dict[str, Any]] | None = None,
    llm_provider: LLMProvider | None = None,
    domain: str = "",
) -> GapAnalysisResult:
    """Convenience function for gap analysis.

    Args:
        topic: Research topic
        synthesis: Literature synthesis
        literature_review: Paper metadata
        llm_provider: LLM provider
        domain: Research domain

    Returns:
        GapAnalysisResult
    """
    analyzer = ResearchGapAnalyzer(
        config=GapAnalysisConfig(
            use_multi_perspective=llm_provider is not None,
            llm_provider=llm_provider,
        ),
    )
    return await analyzer.analyze(
        topic=topic,
        synthesis=synthesis,
        literature_review=literature_review,
        domain=domain,
    )
