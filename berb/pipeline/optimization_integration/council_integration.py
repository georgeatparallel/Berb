"""Council Mode Integration (Upgrade 3).

Integrates Council Mode with pipeline stages:
- Stage 7: SYNTHESIS
- Stage 8: HYPOTHESIS_GEN
- Stage 15: RESEARCH_DECISION

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from berb.review.council_mode import (
    CouncilMode,
    CouncilSynthesis,
    CouncilConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class CouncilStageResult:
    """Result from council stage integration.
    
    Attributes:
        synthesis: Council synthesis
        stage_id: Pipeline stage ID
        consensus_reached: Whether consensus was reached
        recommendation: Council recommendation
    """
    synthesis: CouncilSynthesis
    stage_id: str
    consensus_reached: bool
    recommendation: str


class CouncilIntegration:
    """Integrates Council Mode with pipeline stages.
    
    Usage in pipeline:
        integration = CouncilIntegration()
        result = await integration.run_synthesis_council(
            task="Synthesize literature",
            stage_id="SYNTHESIS",
        )
    """
    
    def __init__(
        self,
        models: list[str] | None = None,
        judge_model: str = "claude-sonnet",
        consensus_threshold: float = 0.8,
    ):
        """Initialize council integration.
        
        Args:
            models: Models to use in council
            judge_model: Judge model for synthesis
            consensus_threshold: Threshold for high consensus
        """
        self.models = models or ["claude-opus", "gpt-4o", "deepseek-v3.2"]
        self.judge_model = judge_model
        self.consensus_threshold = consensus_threshold
        self.council = CouncilMode()
        
        logger.info(
            f"Initialized CouncilIntegration with {len(self.models)} models"
        )
    
    async def run_synthesis_council(
        self,
        literature_summary: str,
        topic: str,
        stage_id: str = "SYNTHESIS",
    ) -> CouncilStageResult:
        """Stage 7: Run council on literature synthesis.
        
        Args:
            literature_summary: Summary of collected literature
            topic: Research topic
            stage_id: Pipeline stage ID
            
        Returns:
            Council stage result
        """
        task = f"""
Synthesize the literature on: {topic}

Literature Summary:
{literature_summary}

Provide a comprehensive synthesis that:
1. Identifies key themes and patterns
2. Highlights agreements and contradictions
3. Identifies research gaps
4. Suggests promising directions
"""
        
        synthesis = await self.council.run_council(
            task=task,
            models=self.models,
            judge_model=self.judge_model,
        )
        
        consensus_reached = synthesis.consensus_score >= self.consensus_threshold
        
        recommendation = (
            "Proceed with synthesis - high consensus"
            if consensus_reached
            else "Review divergences before proceeding"
        )
        
        logger.info(
            f"Stage {stage_id}: Council consensus={synthesis.consensus_score:.2f}"
        )
        
        return CouncilStageResult(
            synthesis=synthesis,
            stage_id=stage_id,
            consensus_reached=consensus_reached,
            recommendation=recommendation,
        )
    
    async def run_hypothesis_council(
        self,
        synthesis_report: str,
        topic: str,
        stage_id: str = "HYPOTHESIS_GEN",
    ) -> CouncilStageResult:
        """Stage 8: Run council on hypothesis generation.
        
        Args:
            synthesis_report: Literature synthesis report
            topic: Research topic
            stage_id: Pipeline stage ID
            
        Returns:
            Council stage result
        """
        task = f"""
Generate research hypotheses based on:

Topic: {topic}

Synthesis Report:
{synthesis_report}

Provide diverse hypotheses that:
1. Address identified research gaps
2. Are testable and falsifiable
3. Have potential for high impact
4. Represent different perspectives
"""
        
        synthesis = await self.council.run_council(
            task=task,
            models=self.models,
            judge_model=self.judge_model,
        )
        
        consensus_reached = synthesis.consensus_score >= self.consensus_threshold
        
        recommendation = (
            "Proceed with top hypotheses - high consensus"
            if consensus_reached
            else "Consider multiple hypotheses - diverse perspectives"
        )
        
        logger.info(
            f"Stage {stage_id}: Council consensus={synthesis.consensus_score:.2f}"
        )
        
        return CouncilStageResult(
            synthesis=synthesis,
            stage_id=stage_id,
            consensus_reached=consensus_reached,
            recommendation=recommendation,
        )
    
    async def run_decision_council(
        self,
        analysis_report: str,
        results_summary: str,
        stage_id: str = "RESEARCH_DECISION",
    ) -> CouncilStageResult:
        """Stage 15: Run council on research decision.
        
        Args:
            analysis_report: Result analysis report
            results_summary: Summary of experimental results
            stage_id: Pipeline stage ID
            
        Returns:
            Council stage result
        """
        task = f"""
Make a research decision: PROCEED, REFINE, or PIVOT

Results Summary:
{results_summary}

Analysis Report:
{analysis_report}

Provide recommendation on:
1. Whether to PROCEED to writing
2. REFINE experiments (specify what)
3. PIVOT to new hypothesis (specify which)
"""
        
        synthesis = await self.council.run_council(
            task=task,
            models=self.models,
            judge_model=self.judge_model,
        )
        
        consensus_reached = synthesis.consensus_score >= self.consensus_threshold
        
        recommendation = synthesis.recommendation
        
        logger.info(
            f"Stage {stage_id}: Council consensus={synthesis.consensus_score:.2f}, "
            f"decision={recommendation}"
        )
        
        return CouncilStageResult(
            synthesis=synthesis,
            stage_id=stage_id,
            consensus_reached=consensus_reached,
            recommendation=recommendation,
        )


async def run_council_stage(
    stage_id: str,
    context: dict[str, Any],
    models: list[str] | None = None,
    judge_model: str = "claude-sonnet",
) -> CouncilStageResult:
    """Run council mode for specific pipeline stage.
    
    Args:
        stage_id: Pipeline stage ID
        context: Stage context data
        models: Models to use
        judge_model: Judge model
        
    Returns:
        Council stage result
    """
    integration = CouncilIntegration(models=models, judge_model=judge_model)
    
    if stage_id == "SYNTHESIS":
        return await integration.run_synthesis_council(
            literature_summary=context.get("literature_summary", ""),
            topic=context.get("topic", ""),
            stage_id=stage_id,
        )
    elif stage_id == "HYPOTHESIS_GEN":
        return await integration.run_hypothesis_council(
            synthesis_report=context.get("synthesis_report", ""),
            topic=context.get("topic", ""),
            stage_id=stage_id,
        )
    elif stage_id == "RESEARCH_DECISION":
        return await integration.run_decision_council(
            analysis_report=context.get("analysis_report", ""),
            results_summary=context.get("results_summary", ""),
            stage_id=stage_id,
        )
    else:
        raise ValueError(f"Unknown council stage: {stage_id}")
