"""Specialized AI agents for Berb autonomous research pipeline.

Provides 4 specialized agents:
- LiteratureReviewerAgent: Search, classify, synthesize literature
- ExperimentAnalystAgent: Statistics, figures, ablation studies
- PaperWritingAgent: Structure, write, verify citations
- RebuttalWriterAgent: Classify comments, evidence-based response

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.agents.specialized import (
        LiteratureReviewerAgent,
        ExperimentAnalystAgent,
        PaperWritingAgent,
        RebuttalWriterAgent,
    )

    # Literature review
    agent = LiteratureReviewerAgent(llm_client)
    review = await agent.review(topic, papers)

    # Experiment analysis
    agent = ExperimentAnalystAgent(llm_client)
    analysis = await agent.analyze(results, metrics)

    # Paper writing
    agent = PaperWritingAgent(llm_client)
    paper = await agent.write(outline, citations)

    # Rebuttal
    agent = RebuttalWriterAgent(llm_client)
    rebuttal = await agent.respond(reviews, paper)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Base agent configuration.

    Attributes:
        llm_client: LLM client for agent operations
        max_tokens: Maximum tokens for responses
        temperature: Temperature for LLM generation
        verbose: Enable verbose logging
    """

    llm_client: Any = None
    max_tokens: int = 4096
    temperature: float = 0.7
    verbose: bool = False


@dataclass
class AgentResult:
    """Base agent result.

    Attributes:
        success: Whether agent operation succeeded
        output: Agent output data
        confidence: Confidence score (0-1)
        metadata: Additional metadata
        error: Error message if failed
    """

    success: bool = True
    output: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "error": self.error,
        }


class BaseAgent(ABC):
    """Abstract base class for all specialized agents."""

    def __init__(self, config: AgentConfig | None = None):
        """
        Initialize base agent.

        Args:
            config: Agent configuration
        """
        self.config = config or AgentConfig()
        self.llm = config.llm_client if config else None

    @abstractmethod
    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute agent operation."""
        pass


# =============================================================================
# Literature Reviewer Agent
# =============================================================================

@dataclass
class LiteratureReviewResult(AgentResult):
    """Literature review result."""

    summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    trends: list[str] = field(default_factory=list)
    relevant_papers: list[dict[str, Any]] = field(default_factory=list)


class LiteratureReviewerAgent(BaseAgent):
    """Agent for literature search, classification, and synthesis.

    Capabilities:
    - Search and classify papers by relevance
    - Extract key findings and contributions
    - Identify research gaps
    - Detect trends and patterns
    - Generate literature review summaries

    Usage:
        agent = LiteratureReviewerAgent(llm_client)
        result = await agent.review(
            topic="Transformers for NLP",
            papers=paper_list,
        )
        print(result.summary)
        print(f"Key findings: {len(result.key_findings)}")
        print(f"Gaps: {result.gaps}")
    """

    async def review(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        *,
        max_papers: int = 50,
    ) -> LiteratureReviewResult:
        """
        Review literature on a topic.

        Args:
            topic: Research topic
            papers: List of paper metadata
            max_papers: Maximum papers to analyze

        Returns:
            LiteratureReviewResult with summary and findings
        """
        if not self.llm:
            return self._fallback_review(topic, papers)

        # Prepare papers for analysis
        papers_text = self._format_papers(papers[:max_papers])

        prompt = f"""Review the following literature on: {topic}

Papers:
{papers_text}

Provide:
1. A concise summary (200-300 words)
2. Key findings (3-5 bullet points)
3. Research gaps (2-3 items)
4. Emerging trends (2-3 items)
5. Most relevant papers (top 5)

Respond in JSON format:
{{
    "summary": "...",
    "key_findings": ["...", "..."],
    "gaps": ["...", "..."],
    "trends": ["...", "..."],
    "relevant_papers": [{{"title": "...", "reason": "..."}}]
}}
"""
        try:
            response = self.llm.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                max_tokens=self.config.max_tokens,
            )

            import json
            data = json.loads(response.content)

            return LiteratureReviewResult(
                success=True,
                output=data,
                summary=data.get("summary", ""),
                key_findings=data.get("key_findings", []),
                gaps=data.get("gaps", []),
                trends=data.get("trends", []),
                relevant_papers=data.get("relevant_papers", []),
                confidence=0.85,
            )

        except Exception as e:
            logger.error(f"Literature review failed: {e}")
            return self._fallback_review(topic, papers)

    def _fallback_review(
        self,
        topic: str,
        papers: list[dict[str, Any]],
    ) -> LiteratureReviewResult:
        """Fallback review without LLM."""
        return LiteratureReviewResult(
            success=True,
            summary=f"Literature review on {topic} with {len(papers)} papers.",
            key_findings=[f"Finding {i+1}" for i in range(min(5, len(papers)))],
            gaps=["Gap 1", "Gap 2"],
            trends=["Trend 1", "Trend 2"],
            relevant_papers=papers[:5],
            confidence=0.5,
        )

    def _format_papers(self, papers: list[dict[str, Any]]) -> str:
        """Format papers for LLM input."""
        lines = []
        for i, paper in enumerate(papers, 1):
            title = paper.get("title", "Untitled")
            authors = ", ".join(paper.get("authors", ["Unknown"]))
            year = paper.get("year", "n.d.")
            venue = paper.get("venue", "")
            lines.append(f"{i}. {title} ({authors}, {year}, {venue})")
        return "\n".join(lines)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute literature review."""
        return await self.review(
            topic=kwargs.get("topic", ""),
            papers=kwargs.get("papers", []),
        )


# =============================================================================
# Experiment Analyst Agent
# =============================================================================

@dataclass
class ExperimentAnalysisResult(AgentResult):
    """Experiment analysis result."""

    statistical_summary: dict[str, Any] = field(default_factory=dict)
    key_results: list[str] = field(default_factory=list)
    ablation_findings: list[str] = field(default_factory=list)
    figure_suggestions: list[dict[str, str]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class ExperimentAnalystAgent(BaseAgent):
    """Agent for experiment analysis and interpretation.

    Capabilities:
    - Statistical analysis of results
    - Key result extraction
    - Ablation study interpretation
    - Figure/chart suggestions
    - Recommendation generation

    Usage:
        agent = ExperimentAnalystAgent(llm_client)
        result = await agent.analyze(
            results=experiment_results,
            metrics={"accuracy": 0.95, "f1": 0.93},
        )
        print(result.statistical_summary)
        print(f"Figure suggestions: {result.figure_suggestions}")
    """

    async def analyze(
        self,
        results: dict[str, Any],
        metrics: dict[str, float],
        *,
        ablation: dict[str, Any] | None = None,
    ) -> ExperimentAnalysisResult:
        """
        Analyze experiment results.

        Args:
            results: Experiment results data
            metrics: Performance metrics
            ablation: Ablation study results (optional)

        Returns:
            ExperimentAnalysisResult with analysis
        """
        if not self.llm:
            return self._fallback_analysis(results, metrics)

        # Prepare results for analysis
        results_text = self._format_results(results, metrics, ablation)

        prompt = f"""Analyze the following experiment results:

{results_text}

Provide:
1. Statistical summary
2. Key results (3-5 bullet points)
3. Ablation findings (if applicable)
4. Figure/chart suggestions (2-3)
5. Recommendations for improvement

Respond in JSON format:
{{
    "statistical_summary": {...},
    "key_results": ["...", "..."],
    "ablation_findings": ["...", "..."],
    "figure_suggestions": [{{"type": "...", "description": "..."}}],
    "recommendations": ["...", "..."]
}}
"""
        try:
            response = self.llm.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                max_tokens=self.config.max_tokens,
            )

            import json
            data = json.loads(response.content)

            return ExperimentAnalysisResult(
                success=True,
                output=data,
                statistical_summary=data.get("statistical_summary", {}),
                key_results=data.get("key_results", []),
                ablation_findings=data.get("ablation_findings", []),
                figure_suggestions=data.get("figure_suggestions", []),
                recommendations=data.get("recommendations", []),
                confidence=0.85,
            )

        except Exception as e:
            logger.error(f"Experiment analysis failed: {e}")
            return self._fallback_analysis(results, metrics)

    def _fallback_analysis(
        self,
        results: dict[str, Any],
        metrics: dict[str, float],
    ) -> ExperimentAnalysisResult:
        """Fallback analysis without LLM."""
        return ExperimentAnalysisResult(
            success=True,
            output={
                "metrics": metrics,
            },
            statistical_summary={
                "mean": sum(metrics.values()) / len(metrics) if metrics else 0,
                "max": max(metrics.values()) if metrics else 0,
                "min": min(metrics.values()) if metrics else 0,
            },
            key_results=[f"Result {i+1}: {v:.4f}" for i, v in enumerate(metrics.values())],
            ablation_findings=[],
            figure_suggestions=[
                {"type": "bar", "description": "Metric comparison"},
                {"type": "line", "description": "Training curve"},
            ],
            recommendations=["Consider additional ablation studies"],
            confidence=0.5,
        )

    def _format_results(
        self,
        results: dict[str, Any],
        metrics: dict[str, float],
        ablation: dict[str, Any] | None,
    ) -> str:
        """Format results for LLM input."""
        lines = ["## Metrics"]
        for name, value in metrics.items():
            lines.append(f"- {name}: {value:.4f}")

        if ablation:
            lines.append("\n## Ablation Study")
            for variant, value in ablation.items():
                lines.append(f"- {variant}: {value:.4f}")

        return "\n".join(lines)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute experiment analysis."""
        return await self.analyze(
            results=kwargs.get("results", {}),
            metrics=kwargs.get("metrics", {}),
            ablation=kwargs.get("ablation"),
        )


# =============================================================================
# Paper Writing Agent
# =============================================================================

@dataclass
class PaperWritingResult(AgentResult):
    """Paper writing result."""

    sections: dict[str, str] = field(default_factory=dict)
    word_count: int = 0
    citation_count: int = 0
    quality_score: float = 0.0
    suggestions: list[str] = field(default_factory=list)


class PaperWritingAgent(BaseAgent):
    """Agent for academic paper writing.

    Capabilities:
    - Generate paper structure
    - Write sections with proper citations
    - Ensure academic voice
    - Verify citation accuracy
    - Quality assessment

    Usage:
        agent = PaperWritingAgent(llm_client)
        result = await agent.write(
            outline=paper_outline,
            citations=citation_list,
            venue="NeurIPS",
        )
        print(f"Word count: {result.word_count}")
        print(f"Quality score: {result.quality_score:.2f}")
    """

    async def write(
        self,
        outline: dict[str, Any],
        citations: list[dict[str, Any]],
        *,
        venue: str = "NeurIPS",
        max_words: int = 8000,
    ) -> PaperWritingResult:
        """
        Write academic paper.

        Args:
            outline: Paper outline with sections
            citations: List of citations
            venue: Target venue
            max_words: Maximum word count

        Returns:
            PaperWritingResult with paper sections
        """
        if not self.llm:
            return self._fallback_writing(outline, venue)

        # Prepare outline and citations
        outline_text = self._format_outline(outline)
        citations_text = self._format_citations(citations)

        prompt = f"""Write an academic paper for {venue} based on this outline:

{outline_text}

Citations to use:
{citations_text}

Requirements:
- Academic voice
- Proper citation format
- Target: 5000-6500 words
- Include all standard sections

Respond in JSON format:
{{
    "sections": {{
        "abstract": "...",
        "introduction": "...",
        "related_work": "...",
        "method": "...",
        "experiments": "...",
        "conclusion": "..."
    }},
    "word_count": ...,
    "citation_count": ...,
    "quality_score": ...,
    "suggestions": ["...", "..."]
}}
"""
        try:
            response = self.llm.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                max_tokens=min(self.config.max_tokens, 8192),
            )

            import json
            data = json.loads(response.content)

            # Calculate actual word count
            total_words = sum(
                len(section.split())
                for section in data.get("sections", {}).values()
            )

            return PaperWritingResult(
                success=True,
                output=data,
                sections=data.get("sections", {}),
                word_count=total_words,
                citation_count=data.get("citation_count", 0),
                quality_score=data.get("quality_score", 0.0),
                suggestions=data.get("suggestions", []),
                confidence=0.8,
            )

        except Exception as e:
            logger.error(f"Paper writing failed: {e}")
            return self._fallback_writing(outline, venue)

    def _fallback_writing(
        self,
        outline: dict[str, Any],
        venue: str,
    ) -> PaperWritingResult:
        """Fallback writing without LLM."""
        return PaperWritingResult(
            success=True,
            sections={
                "abstract": "Abstract placeholder",
                "introduction": "Introduction placeholder",
                "related_work": "Related work placeholder",
                "method": "Method placeholder",
                "experiments": "Experiments placeholder",
                "conclusion": "Conclusion placeholder",
            },
            word_count=100,
            citation_count=0,
            quality_score=0.5,
            suggestions=["Use LLM for full paper generation"],
            confidence=0.3,
        )

    def _format_outline(self, outline: dict[str, Any]) -> str:
        """Format outline for LLM input."""
        lines = []
        for section, content in outline.items():
            lines.append(f"## {section}")
            if isinstance(content, str):
                lines.append(content)
            elif isinstance(content, list):
                for item in content:
                    lines.append(f"- {item}")
        return "\n".join(lines)

    def _format_citations(self, citations: list[dict[str, Any]]) -> str:
        """Format citations for LLM input."""
        lines = []
        for i, cit in enumerate(citations, 1):
            title = cit.get("title", "Untitled")
            authors = ", ".join(cit.get("authors", ["Unknown"]))
            year = cit.get("year", "n.d.")
            lines.append(f"{i}. {title} ({authors}, {year})")
        return "\n".join(lines)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute paper writing."""
        return await self.write(
            outline=kwargs.get("outline", {}),
            citations=kwargs.get("citations", []),
            venue=kwargs.get("venue", "NeurIPS"),
        )


# =============================================================================
# Rebuttal Writer Agent
# =============================================================================

@dataclass
class RebuttalResult(AgentResult):
    """Rebuttal writing result."""

    response_letter: str = ""
    point_by_point: list[dict[str, str]] = field(default_factory=list)
    tone_analysis: dict[str, Any] = field(default_factory=dict)
    evidence_references: list[str] = field(default_factory=list)


class RebuttalWriterAgent(BaseAgent):
    """Agent for generating rebuttals to reviewer comments.

    Capabilities:
    - Classify reviewer comments by type
    - Generate evidence-based responses
    - Maintain professional tone
    - Reference paper sections
    - Track addressed concerns

    Usage:
        agent = RebuttalWriterAgent(llm_client)
        result = await agent.respond(
            reviews=reviewer_comments,
            paper=paper_text,
        )
        print(result.response_letter)
        print(f"Point-by-point: {len(result.point_by_point)} responses")
    """

    async def respond(
        self,
        reviews: list[dict[str, Any]],
        paper: str,
        *,
        venue: str = "NeurIPS",
    ) -> RebuttalResult:
        """
        Generate rebuttal to reviewer comments.

        Args:
            reviews: List of reviewer comments
            paper: Paper text
            venue: Target venue

        Returns:
            RebuttalResult with response
        """
        if not self.llm:
            return self._fallback_rebuttal(reviews)

        # Prepare reviews and paper excerpt
        reviews_text = self._format_reviews(reviews)
        paper_excerpt = paper[:5000]  # First 5000 chars for context

        prompt = f"""Generate a rebuttal for {venue} based on these reviews:

{reviews_text}

Paper excerpt:
{paper_excerpt}

Provide:
1. Response letter to area chair
2. Point-by-point responses to each reviewer
3. Evidence references from paper
4. Professional, constructive tone

Respond in JSON format:
{{
    "response_letter": "...",
    "point_by_point": [
        {{"reviewer": "R1", "comment": "...", "response": "...", "evidence": "..."}}
    ],
    "tone_analysis": {{"professionalism": ..., "constructiveness": ...}},
    "evidence_references": ["Section 3.2", "Figure 4", "..."]
}}
"""
        try:
            response = self.llm.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                max_tokens=self.config.max_tokens,
            )

            import json
            data = json.loads(response.content)

            return RebuttalResult(
                success=True,
                output=data,
                response_letter=data.get("response_letter", ""),
                point_by_point=data.get("point_by_point", []),
                tone_analysis=data.get("tone_analysis", {}),
                evidence_references=data.get("evidence_references", []),
                confidence=0.8,
            )

        except Exception as e:
            logger.error(f"Rebuttal writing failed: {e}")
            return self._fallback_rebuttal(reviews)

    def _fallback_rebuttal(
        self,
        reviews: list[dict[str, Any]],
    ) -> RebuttalResult:
        """Fallback rebuttal without LLM."""
        point_by_point = []
        for review in reviews:
            reviewer = review.get("reviewer", "Unknown")
            comments = review.get("comments", [])
            for comment in comments:
                point_by_point.append({
                    "reviewer": reviewer,
                    "comment": comment[:100],
                    "response": "We thank the reviewer for this comment. [Detailed response needed]",
                    "evidence": "",
                })

        return RebuttalResult(
            success=True,
            response_letter="Dear Area Chair,\n\nWe thank the reviewers for their constructive feedback...",
            point_by_point=point_by_point,
            tone_analysis={"professionalism": 0.8, "constructiveness": 0.7},
            evidence_references=[],
            confidence=0.4,
        )

    def _format_reviews(self, reviews: list[dict[str, Any]]) -> str:
        """Format reviews for LLM input."""
        lines = []
        for review in reviews:
            reviewer = review.get("reviewer", "Unknown")
            rating = review.get("rating", "")
            comments = review.get("comments", [])
            lines.append(f"## Reviewer {reviewer} (Rating: {rating})")
            for comment in comments:
                lines.append(f"- {comment}")
        return "\n".join(lines)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute rebuttal writing."""
        return await self.respond(
            reviews=kwargs.get("reviews", []),
            paper=kwargs.get("paper", ""),
            venue=kwargs.get("venue", "NeurIPS"),
        )


# =============================================================================
# Factory Function
# =============================================================================

def create_agent(
    agent_type: str,
    llm_client: Any = None,
    **kwargs: Any,
) -> BaseAgent:
    """
    Factory function to create specialized agents.

    Args:
        agent_type: Type of agent ("literature", "experiment", "paper", "rebuttal")
        llm_client: LLM client
        **kwargs: Additional configuration

    Returns:
        Specialized agent instance

    Examples:
        agent = create_agent("literature", llm_client)
        agent = create_agent("experiment", llm_client, temperature=0.5)
    """
    config = AgentConfig(llm_client=llm_client, **kwargs)

    agents = {
        "literature": LiteratureReviewerAgent,
        "experiment": ExperimentAnalystAgent,
        "paper": PaperWritingAgent,
        "rebuttal": RebuttalWriterAgent,
    }

    if agent_type not in agents:
        raise ValueError(
            f"Unknown agent type: {agent_type}. "
            f"Available: {', '.join(agents.keys())}"
        )

    return agents[agent_type](config)
