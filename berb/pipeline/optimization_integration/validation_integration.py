"""Validation Integration (Upgrade 2).

Integrates Hidden Consistent Evaluation with pipeline stages:
- Stage 15: RESEARCH_DECISION
- Stage 19: PAPER_REVISION
- Stage 20: QUALITY_GATE

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from berb.validation.hidden_eval import (
    HiddenConsistentEvaluation,
    PaperDocument,
    EvaluationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class HCEStageResult:
    """Result from HCE stage integration.
    
    Attributes:
        search_result: Search evaluation result
        selection_result: Selection evaluation result (if applicable)
        hidden_result: Hidden test result
        recommendation: Stage recommendation
    """
    search_result: EvaluationResult
    selection_result: EvaluationResult | None
    hidden_result: EvaluationResult | None
    recommendation: str


class ValidationIntegration:
    """Integrates HCE with pipeline stages.
    
    Usage in pipeline:
        integration = ValidationIntegration()
        result = await integration.evaluate_with_hce(paper)
    """
    
    def __init__(
        self,
        use_in_improvement_loop: bool = True,
        use_for_selection: bool = True,
        track_hidden_scores: bool = True,
    ):
        """Initialize validation integration.
        
        Args:
            use_in_improvement_loop: Use HCE in improvement loop
            use_for_selection: Use HCE for final selection
            track_hidden_scores: Track hidden scores
        """
        self.use_in_improvement_loop = use_in_improvement_loop
        self.use_for_selection = use_for_selection
        self.track_hidden_scores = track_hidden_scores
        self.hce = HiddenConsistentEvaluation()
        
        logger.info(
            f"Initialized ValidationIntegration: "
            f"loop={use_in_improvement_loop}, "
            f"selection={use_for_selection}, "
            f"tracking={track_hidden_scores}"
        )
    
    async def evaluate_for_improvement(
        self,
        paper_content: str,
        title: str,
        abstract: str,
    ) -> EvaluationResult:
        """Stage 19: Evaluate for improvement loop.
        
        Args:
            paper_content: Paper content
            title: Paper title
            abstract: Paper abstract
            
        Returns:
            Evaluation result
        """
        if not self.use_in_improvement_loop:
            logger.warning("HCE improvement loop disabled")
            return EvaluationResult(
                paper_id="unknown",
                overall_score=5.0,
                dimension_scores={},
                criteria_used="disabled",
            )
        
        paper = PaperDocument(
            id=f"rev_{title[:20]}",
            title=title,
            abstract=abstract,
            content=paper_content,
        )
        
        result = await self.hce.evaluate_for_search(paper)
        
        logger.info(
            f"Improvement evaluation: score={result.overall_score:.2f}"
        )
        
        return result
    
    async def evaluate_for_selection(
        self,
        papers: list[PaperDocument],
    ) -> tuple[PaperDocument, EvaluationResult]:
        """Stage 20: Evaluate for final selection.
        
        Args:
            papers: Candidate papers
            
        Returns:
            Best paper and its evaluation
        """
        if not self.use_for_selection:
            logger.warning("HCE selection disabled")
            return papers[0], EvaluationResult(
                paper_id=papers[0].id,
                overall_score=5.0,
                dimension_scores={},
                criteria_used="disabled",
            )
        
        best_paper, result = await self.hce.evaluate_for_selection(papers)
        
        logger.info(
            f"Selection evaluation: {best_paper.id} "
            f"score={result.overall_score:.2f}"
        )
        
        return best_paper, result
    
    async def evaluate_hidden(
        self,
        paper_content: str,
        title: str,
        abstract: str,
    ) -> EvaluationResult | None:
        """Stage 20: Hidden test evaluation.
        
        Args:
            paper_content: Paper content
            title: Paper title
            abstract: Paper abstract
            
        Returns:
            Hidden evaluation result or None
        """
        if not self.track_hidden_scores:
            return None
        
        paper = PaperDocument(
            id=f"hidden_{title[:20]}",
            title=title,
            abstract=abstract,
            content=paper_content,
        )
        
        result = await self.hce.evaluate_hidden(paper)
        
        logger.info(
            f"Hidden evaluation: score={result.overall_score:.2f} (TRUE QUALITY)"
        )
        
        return result
    
    async def evaluate_quality_gate(
        self,
        paper_content: str,
        title: str,
        abstract: str,
        threshold: float = 7.0,
    ) -> HCEStageResult:
        """Stage 20: Complete quality gate evaluation.
        
        Args:
            paper_content: Paper content
            title: Paper title
            abstract: Paper abstract
            threshold: Quality threshold
            
        Returns:
            HCE stage result
        """
        paper = PaperDocument(
            id=f"gate_{title[:20]}",
            title=title,
            abstract=abstract,
            content=paper_content,
        )
        
        # Search evaluation (visible)
        search_result = await self.hce.evaluate_for_search(paper)
        
        # Hidden evaluation (not visible to agents)
        hidden_result = None
        if self.track_hidden_scores:
            hidden_result = await self.hce.evaluate_hidden(paper)
        
        # Determine recommendation
        if search_result.overall_score >= threshold:
            recommendation = "PASS - Proceed to publication"
        else:
            recommendation = f"FAIL - Score {search_result.overall_score:.2f} < {threshold}"
        
        logger.info(
            f"Quality gate: {recommendation}"
        )
        
        return HCEStageResult(
            search_result=search_result,
            selection_result=None,
            hidden_result=hidden_result,
            recommendation=recommendation,
        )


async def evaluate_with_hce(
    paper_content: str,
    title: str,
    abstract: str,
    stage_id: str = "QUALITY_GATE",
    threshold: float = 7.0,
) -> HCEStageResult | EvaluationResult:
    """Evaluate paper with HCE for specific stage.
    
    Args:
        paper_content: Paper content
        title: Paper title
        abstract: Paper abstract
        stage_id: Pipeline stage ID
        threshold: Quality threshold
        
    Returns:
        HCE result
    """
    integration = ValidationIntegration()
    
    if stage_id == "QUALITY_GATE":
        return await integration.evaluate_quality_gate(
            paper_content, title, abstract, threshold
        )
    elif stage_id == "IMPROVEMENT":
        return await integration.evaluate_for_improvement(
            paper_content, title, abstract
        )
    else:
        raise ValueError(f"Unknown HCE stage: {stage_id}")
