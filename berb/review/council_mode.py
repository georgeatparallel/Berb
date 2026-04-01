"""Council Mode — Multi-model parallel analysis.

Based on Microsoft Copilot Researcher Council pattern:
1. Multiple models generate independent reports on same query
2. Judge model evaluates, identifies agreement/divergence/unique insights
3. Synthesis covers all perspectives

Key Difference from Critique:
- Critique: Generate → Evaluate (sequential, 2 models)
- Council: Generate in parallel → Synthesize (parallel, 3+ models)

Use Cases in Berb:
- Stage 7 (SYNTHESIS): Council on literature synthesis
- Stage 8 (HYPOTHESIS_GEN): Council on hypothesis generation
- Stage 15 (RESEARCH_DECISION): Council on go/no-go decision

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.review.council_mode import CouncilMode
    
    council = CouncilMode()
    result = await council.run_council(
        task="Evaluate this research direction",
        models=["claude-opus", "gpt-4o", "deepseek-v3.2"],
        judge_model="claude-sonnet",
    )
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CouncilReport:
    """Independent report from one council member.
    
    Attributes:
        model: Model that generated the report
        content: Full report content
        key_points: Key points extracted
        confidence: Confidence level (0-1)
        unique_insights: Insights others might miss
    """
    model: str
    content: str
    key_points: list[str] = field(default_factory=list)
    confidence: float = 0.5
    unique_insights: list[str] = field(default_factory=list)


@dataclass
class CouncilSynthesis:
    """Synthesized council output.
    
    Attributes:
        agreements: Points where models agree (high confidence)
        divergences: Points where models disagree
        unique_insights: Unique insights from each model
        consensus_score: Overall consensus (0-1)
        recommendation: Final recommendation
        cover_letter: Synthesized cover letter
    """
    agreements: list[str] = field(default_factory=list)
    divergences: list[str] = field(default_factory=list)
    unique_insights: dict[str, list[str]] = field(default_factory=dict)
    consensus_score: float = 0.5
    recommendation: str = ""
    cover_letter: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agreements": self.agreements,
            "divergences": self.divergences,
            "unique_insights": self.unique_insights,
            "consensus_score": self.consensus_score,
            "recommendation": self.recommendation,
            "cover_letter": self.cover_letter,
        }


@dataclass
class CouncilConfig:
    """Council configuration.
    
    Attributes:
        models: Models to use in council
        judge_model: Model to use for synthesis
        task: Task description
        parallel: Run models in parallel
        include_divergences: Include divergent opinions
        consensus_threshold: Threshold for high consensus
    """
    models: list[str] = field(default_factory=list)
    judge_model: str = "claude-sonnet"
    task: str = ""
    parallel: bool = True
    include_divergences: bool = True
    consensus_threshold: float = 0.8


class CouncilMode:
    """Microsoft Council-inspired multi-model analysis.
    
    Architecture:
        ┌─────────────────────────────────────────┐
        │            Council Mode                 │
        │                                         │
        │  ┌──────────┐  ┌──────────┐  ┌──────┐  │
        │  │ Model 1  │  │ Model 2  │  │ModelN│  │
        │  │ Report   │  │ Report   │  │Report│  │
        │  └────┬─────┘  └────┬─────┘  └──┬───┘  │
        │       │             │            │      │
        │       └─────────────┴────────────┘      │
        │                   │                     │
        │            ┌──────▼──────┐              │
        │            │ Judge Model │              │
        │            │  Synthesis  │              │
        │            └─────────────┘              │
        └─────────────────────────────────────────┘
    
    Usage:
        council = CouncilMode()
        
        # Stage 7: Literature synthesis council
        result = await council.run_council(
            task="Synthesize literature on X",
            models=["claude-opus", "gpt-4o", "gemini-pro"],
            judge_model="claude-sonnet",
        )
        
        # Use consensus for decision
        if result.consensus_score > 0.8:
            # High confidence — proceed
        else:
            # Low consensus — investigate divergences
    """
    
    def __init__(self, config: CouncilConfig | None = None):
        """Initialize council mode.
        
        Args:
            config: Council configuration (uses defaults if None)
        """
        self.config = config or CouncilConfig()
        logger.info("Initialized CouncilMode")
    
    async def run_council(
        self,
        task: str,
        models: list[str],
        judge_model: str = "claude-sonnet",
        context: dict[str, Any] | None = None,
    ) -> CouncilSynthesis:
        """Run council mode with multiple models.
        
        Process:
        1. Each model generates independent synthesis/analysis
        2. Judge model creates cover letter:
           - Where models agree (high confidence)
           - Where models diverge (requires investigation)
           - Unique insights from each model
        3. Return synthesized output
        
        Args:
            task: Task/query for council
            models: List of models to use
            judge_model: Model for synthesis
            context: Additional context for all models
            
        Returns:
            Council synthesis result
        """
        logger.info(f"Running council with {len(models)} models for: {task[:50]}...")
        
        # Generate independent reports in parallel
        reports = await self._generate_reports(task, models, context)
        
        # Synthesize with judge model
        synthesis = await self._synthesize(reports, judge_model, task)
        
        logger.info(
            f"Council complete: consensus={synthesis.consensus_score:.2f}, "
            f"agreements={len(synthesis.agreements)}, "
            f"divergences={len(synthesis.divergences)}"
        )
        
        return synthesis
    
    async def _generate_reports(
        self,
        task: str,
        models: list[str],
        context: dict[str, Any] | None,
    ) -> list[CouncilReport]:
        """Generate independent reports from each model.
        
        Args:
            task: Task description
            models: Models to use
            context: Additional context
            
        Returns:
            List of council reports
        """
        from berb.llm.client import get_llm_client
        
        async def generate_one(model: str) -> CouncilReport:
            """Generate single report."""
            client = get_llm_client(model=model)
            
            prompt = self._build_council_prompt(task, context)
            
            response = await client.chat(
                messages=[{"role": "user", "content": prompt}],
                system=f"You are an expert researcher providing INDEPENDENT analysis. "
                       f"Model: {model}",
            )
            
            # Extract key points and insights
            key_points = self._extract_key_points(response.content)
            unique_insights = self._extract_unique_insights(response.content)
            confidence = self._estimate_confidence(response.content)
            
            return CouncilReport(
                model=model,
                content=response.content,
                key_points=key_points,
                confidence=confidence,
                unique_insights=unique_insights,
            )
        
        # Run in parallel
        if len(models) > 1 and self.config.parallel:
            tasks = [generate_one(model) for model in models]
            reports = await asyncio.gather(*tasks)
        else:
            # Sequential for single model or if parallel disabled
            reports = [await generate_one(models[0])]
        
        return list(reports)
    
    async def _synthesize(
        self,
        reports: list[CouncilReport],
        judge_model: str,
        task: str,
    ) -> CouncilSynthesis:
        """Synthesize reports with judge model.
        
        Args:
            reports: Council reports
            judge_model: Judge model
            task: Original task
            
        Returns:
            Council synthesis
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=judge_model)
        
        prompt = self._build_synthesis_prompt(reports, task)
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are a judge synthesizing multiple expert opinions. "
                   "Identify agreements, divergences, and unique insights.",
        )
        
        # Parse synthesis
        synthesis = self._parse_synthesis(response.content, reports)
        
        return synthesis
    
    def _build_council_prompt(
        self,
        task: str,
        context: dict[str, Any] | None,
    ) -> str:
        """Build prompt for council member.
        
        Args:
            task: Task description
            context: Additional context
            
        Returns:
            Council prompt
        """
        context_str = ""
        if context:
            context_str = f"\nContext:\n{context}\n"
        
        return f"""
You are an expert researcher providing an INDEPENDENT analysis.
Your perspective should be unique — don't try to agree with others.

Task: {task}
{context_str}
Provide your analysis with:
1. Key findings (3-5 bullet points)
2. Unique insights that others might miss
3. Your confidence level (0-1) and why
4. Any caveats or limitations

Be thorough and independent. Focus on aspects others might overlook.
"""
    
    def _build_synthesis_prompt(
        self,
        reports: list[CouncilReport],
        task: str,
    ) -> str:
        """Build synthesis prompt for judge model.
        
        Args:
            reports: Council reports
            task: Original task
            
        Returns:
            Synthesis prompt
        """
        reports_str = "\n\n".join([
            f"=== {r.model} (confidence: {r.confidence:.2f}) ===\n{r.content}"
            for r in reports
        ])
        
        return f"""
You are synthesizing multiple independent expert analyses.

Task: {task}

Reports:
{reports_str}

Your job:
1. Identify where models AGREE (high confidence points)
2. Identify where models DIVERGE (requires investigation)
3. Extract UNIQUE insights from each model
4. Provide a final RECOMMENDATION
5. Write a COVER LETTER synthesizing everything

Format your response as JSON:
{{
    "agreements": ["point1", "point2"],
    "divergences": ["point1", "point2"],
    "unique_insights": {{
        "model1": ["insight1"],
        "model2": ["insight1"]
    }},
    "consensus_score": 0.85,
    "recommendation": "...",
    "cover_letter": "..."
}}
"""
    
    def _extract_key_points(self, content: str) -> list[str]:
        """Extract key points from report.
        
        Args:
            content: Report content
            
        Returns:
            List of key points
        """
        # Look for bullet points
        lines = content.split("\n")
        points = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("-", "*", "•", "1.", "2.", "3.")):
                # Remove bullet marker
                point = stripped.lstrip("-*•").strip()
                for i in range(1, 10):
                    point = point.lstrip(f"{i}.").strip()
                if point:
                    points.append(point)
        
        return points[:5] if points else []
    
    def _extract_unique_insights(self, content: str) -> list[str]:
        """Extract unique insights from report.
        
        Args:
            content: Report content
            
        Returns:
            List of unique insights
        """
        # Look for insight-related phrases
        insight_markers = [
            "unique insight",
            "often overlooked",
            "importantly",
            "critically",
            "key distinction",
            "notably",
            "unlike others",
            "in contrast",
        ]
        
        lines = content.split("\n")
        insights = []
        
        for line in lines:
            lower = line.lower()
            if any(marker in lower for marker in insight_markers):
                insights.append(line.strip())
        
        return insights[:3] if insights else []
    
    def _estimate_confidence(self, content: str) -> float:
        """Estimate confidence from report.
        
        Args:
            content: Report content
            
        Returns:
            Confidence estimate (0-1)
        """
        # Look for confidence indicators
        high_confidence_phrases = [
            "confident",
            "clearly",
            "definitely",
            "strong evidence",
            "conclusively",
            "undoubtedly",
        ]
        
        low_confidence_phrases = [
            "uncertain",
            "might",
            "possibly",
            "limited evidence",
            "further research needed",
            "speculative",
            "may",
            "could be",
        ]
        
        content_lower = content.lower()
        
        high_count = sum(1 for p in high_confidence_phrases if p in content_lower)
        low_count = sum(1 for p in low_confidence_phrases if p in content_lower)
        
        # Simple heuristic
        if high_count + low_count == 0:
            return 0.7  # Default
        
        confidence = 0.5 + 0.1 * (high_count - low_count)
        return max(0.0, min(1.0, confidence))
    
    def _parse_synthesis(
        self,
        content: str,
        reports: list[CouncilReport],
    ) -> CouncilSynthesis:
        """Parse synthesis from judge response.
        
        Args:
            content: Judge response
            reports: Original reports
            
        Returns:
            Council synthesis
        """
        import json
        
        try:
            # Extract JSON
            start = content.find("{")
            end = content.rfind("}") + 1
            
            if start == -1 or end == 0:
                raise ValueError("No JSON found")
            
            json_str = content[start:end]
            data = json.loads(json_str)
            
            return CouncilSynthesis(
                agreements=data.get("agreements", []),
                divergences=data.get("divergences", []),
                unique_insights=data.get("unique_insights", {}),
                consensus_score=float(data.get("consensus_score", 0.5)),
                recommendation=data.get("recommendation", ""),
                cover_letter=data.get("cover_letter", ""),
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse synthesis: {e}")
            
            # Fallback - create basic synthesis
            return CouncilSynthesis(
                agreements=[],
                divergences=[],
                unique_insights={r.model: r.unique_insights for r in reports},
                consensus_score=0.5,
                recommendation="Parse failed - see individual reports",
                cover_letter=content,
            )


async def run_council(
    task: str,
    models: list[str],
    judge_model: str = "claude-sonnet",
    context: dict[str, Any] | None = None,
) -> CouncilSynthesis:
    """Convenience function to run council mode.
    
    Args:
        task: Task for council
        models: Models to use
        judge_model: Judge model
        context: Additional context
        
    Returns:
        Council synthesis
    """
    council = CouncilMode()
    return await council.run_council(task, models, judge_model, context)


__all__ = [
    "CouncilMode",
    "CouncilReport",
    "CouncilSynthesis",
    "CouncilConfig",
    "run_council",
]
