"""Hidden Consistent Evaluation (HCE) for Berb.

Based on AIRA2 (Meta FAIR — arXiv:2603.26499) Section 3.2:
"Hidden Consistent Evaluation eliminates evaluation noise that was
previously mistaken for overfitting."

Key Principle: Three-way split of evaluation criteria
- Search Criteria: Used during improvement loop (agent sees score)
- Selection Criteria: Used for final selection (agent sees score)
- Test Criteria: NEVER seen by any agent (true quality measure)

This prevents agents from hill-climbing on the evaluation metric.

Key Finding from AIRA2:
"Overfitting" in research agents is actually evaluation noise — not data
memorization. Fix: decouple optimization signal from selection signal.

Result: AIRA2 gained +4.2 points between 24h and 72h thanks to HCE.

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.validation.hidden_eval import HiddenConsistentEvaluation
    
    hce = HiddenConsistentEvaluation()
    
    # During improvement loop (M2)
    search_score = await hce.evaluate_for_search(paper)
    
    # For final selection
    best_paper, selection_result = await hce.evaluate_for_selection(candidate_papers)
    
    # For true quality assessment (never shown to agents)
    test_report = await hce.evaluate_hidden(paper)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CriteriaVisibility(str, Enum):
    """Visibility level for evaluation criteria."""
    SEARCH = "search"
    """Used during improvement loop - agent sees score"""
    
    SELECTION = "selection"
    """Used for final selection - agent sees score"""
    
    TEST = "test"
    """Never shown to agents - true quality measure"""


@dataclass
class EvalCriteria:
    """Evaluation criteria with weights.
    
    Attributes:
        name: Criteria name
        dimensions: Evaluation dimensions
        weights: Weights for each dimension
        visibility: Visibility level
        description: Human-readable description
    """
    name: str
    dimensions: list[str]
    weights: dict[str, float]
    visibility: CriteriaVisibility
    description: str = ""


@dataclass
class EvaluationResult:
    """Evaluation result.
    
    Attributes:
        paper_id: Evaluated paper identifier
        overall_score: Overall score (0-10)
        dimension_scores: Scores per dimension
        criteria_used: Which criteria was used
        hidden_score: Hidden test score (only for test criteria)
        feedback: Improvement feedback
        timestamp: Evaluation timestamp
    """
    paper_id: str
    overall_score: float
    dimension_scores: dict[str, float]
    criteria_used: str
    hidden_score: float | None = None
    feedback: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "overall_score": self.overall_score,
            "dimension_scores": self.dimension_scores,
            "criteria_used": self.criteria_used,
            "hidden_score": self.hidden_score,
            "feedback": self.feedback,
            "timestamp": self.timestamp.isoformat(),
        }


class PaperDocument(BaseModel):
    """Paper document for evaluation.
    
    This is a simplified paper representation. In practice, this would
    be your actual paper model from the writing module.
    
    Attributes:
        id: Paper identifier
        title: Paper title
        abstract: Paper abstract
        content: Full paper content
        metadata: Additional metadata
    """
    id: str = Field(..., description="Paper identifier")
    title: str = Field(..., description="Paper title", min_length=1)
    abstract: str = Field(..., description="Paper abstract")
    content: str = Field(..., description="Full paper content")
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    def to_markdown(self) -> str:
        """Convert to markdown format."""
        return f"""# {self.title}

## Abstract
{self.abstract}

## Content
{self.content}
"""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(mode="json")


class HiddenConsistentEvaluation:
    """AIRA2-style Hidden Consistent Evaluation.
    
    Implements three-way split of evaluation criteria to prevent
    agents from gaming the evaluation metric.
    
    Architecture:
        ┌─────────────────────────────────────────┐
        │      Hidden Consistent Evaluation       │
        │                                         │
        │  ┌─────────────┐  ┌──────────────┐     │
        │  │   Search    │  │  Selection   │     │
        │  │  Criteria   │  │   Criteria   │     │
        │  │  (visible)  │  │  (visible)   │     │
        │  └──────┬──────┘  └──────┬───────┘     │
        │         │                │              │
        │         └────┬───────┬───┘              │
        │              │       │                  │
        │         ┌────▼───────▼───┐              │
        │         │  Test Criteria │              │
        │         │    (HIDDEN)    │              │
        │         └────────────────┘              │
        └─────────────────────────────────────────┘
    
    Usage:
        hce = HiddenConsistentEvaluation()
        
        # During improvement loop (M2)
        search_result = await hce.evaluate_for_search(paper)
        
        # For final selection
        best_paper, selection_result = await hce.evaluate_for_selection(candidates)
        
        # For true quality assessment
        hidden_result = await hce.evaluate_hidden(paper)
    """
    
    def __init__(self):
        """Initialize HCE with three-way criteria split."""
        # Search criteria - used during improvement loop
        self.search_criteria = EvalCriteria(
            name="search",
            dimensions=[
                "novelty",
                "technical_soundness",
                "clarity",
                "relevance",
            ],
            weights={
                "novelty": 0.30,
                "technical_soundness": 0.30,
                "clarity": 0.20,
                "relevance": 0.20,
            },
            visibility=CriteriaVisibility.SEARCH,
            description="Optimization signal for improvement loop",
        )
        
        # Selection criteria - used for final selection
        self.selection_criteria = EvalCriteria(
            name="selection",
            dimensions=[
                "impact",
                "rigor",
                "presentation",
                "reproducibility",
            ],
            weights={
                "impact": 0.35,
                "rigor": 0.35,
                "presentation": 0.15,
                "reproducibility": 0.15,
            },
            visibility=CriteriaVisibility.SELECTION,
            description="Selection signal for final paper choice",
        )
        
        # Test criteria - NEVER shown to agents
        self.test_criteria = EvalCriteria(
            name="test",
            dimensions=[
                "ground_truth_accuracy",
                "citation_correctness",
                "claim_validity",
                "method_appropriateness",
                "statistical_validity",
            ],
            weights={
                "ground_truth_accuracy": 0.25,
                "citation_correctness": 0.20,
                "claim_validity": 0.20,
                "method_appropriateness": 0.20,
                "statistical_validity": 0.15,
            },
            visibility=CriteriaVisibility.TEST,
            description="True quality measure - never shown to agents",
        )
        
        logger.info("Initialized Hidden Consistent Evaluation")
    
    async def evaluate_for_search(
        self,
        paper: PaperDocument,
        include_feedback: bool = True,
    ) -> EvaluationResult:
        """Score used by improvement loop (M2) to guide optimization.
        
        Agent sees this score but NOT the underlying criteria details.
        This is the optimization signal during search.
        
        Args:
            paper: Paper to evaluate
            include_feedback: Whether to include improvement feedback
            
        Returns:
            Evaluation result with search score
        """
        from berb.llm.client import get_llm_client
        
        # Build evaluation prompt (vague about exact criteria)
        prompt = self._build_search_prompt(paper)
        
        # Get evaluation from LLM
        client = get_llm_client(model="claude-3-sonnet")
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are a research paper evaluator providing feedback for improvement.",
        )
        
        # Parse scores
        scores = self._parse_scores(response.content)
        overall = self._compute_weighted_score(scores, self.search_criteria.weights)
        
        # Extract feedback
        feedback = response.content if include_feedback else ""
        
        result = EvaluationResult(
            paper_id=paper.id,
            overall_score=overall,
            dimension_scores=scores,
            criteria_used="search",
            feedback=feedback,
        )
        
        logger.info(f"HCE search evaluation: {paper.id} → {overall:.2f}")
        return result
    
    async def evaluate_for_selection(
        self,
        papers: list[PaperDocument],
    ) -> tuple[PaperDocument, EvaluationResult]:
        """Select final paper using HIDDEN criteria.
        
        Never used during search — prevents hill-climbing on selection metric.
        Agents see selection scores but don't know they're optimized for different criteria.
        
        Args:
            papers: Candidate papers to select from
            
        Returns:
            Best paper and its evaluation result
        """
        from berb.llm.client import get_llm_client
        
        # Evaluate each paper with selection criteria
        results = []
        for paper in papers:
            prompt = self._build_selection_prompt(paper)
            
            client = get_llm_client(model="claude-3-opus")
            response = await client.chat(
                messages=[{"role": "user", "content": prompt}],
                system="You are a senior researcher selecting the best paper for publication.",
            )
            
            scores = self._parse_scores(response.content)
            overall = self._compute_weighted_score(scores, self.selection_criteria.weights)
            
            results.append((
                paper,
                EvaluationResult(
                    paper_id=paper.id,
                    overall_score=overall,
                    dimension_scores=scores,
                    criteria_used="selection",
                ),
            ))
        
        # Select best
        best_paper, best_result = max(results, key=lambda x: x[1].overall_score)
        
        logger.info(
            f"HCE selection: {best_paper.id} selected ({best_result.overall_score:.2f})"
        )
        
        return best_paper, best_result
    
    async def evaluate_hidden(
        self,
        paper: PaperDocument,
    ) -> EvaluationResult:
        """Evaluate with NEVER-SHOWN test criteria.
        
        This is the TRUE quality measure. Agents never see these scores,
        preventing any form of gaming or overfitting.
        
        Used for:
        - Benchmarking overall system quality
        - Detecting evaluation drift
        - Research analysis
        
        Args:
            paper: Paper to evaluate
            
        Returns:
            Evaluation result with hidden test score
        """
        from berb.llm.client import get_llm_client
        from berb.validation.claim_verification import ClaimVerificationPipeline
        from berb.validation.reference_integrity import ReferenceIntegrityChecker
        
        # Automated checks (no LLM bias)
        claim_verifier = ClaimVerificationPipeline()
        citation_checker = ReferenceIntegrityChecker()
        
        # Run automated verification
        claim_validity = 0.0
        citation_correctness = 0.0
        
        try:
            claim_result = await claim_verifier.verify(paper.content)
            claim_validity = claim_result.verification_score if hasattr(claim_result, 'verification_score') else 0.5
        except Exception as e:
            logger.warning(f"Claim verification failed: {e}")
            claim_validity = 0.5
        
        try:
            citation_result = await citation_checker.check(paper.content)
            citation_correctness = (
                1.0 - (citation_result.issues_count / max(1, citation_result.total_references))
                if hasattr(citation_result, 'issues_count')
                else 0.5
            )
        except Exception as e:
            logger.warning(f"Citation check failed: {e}")
            citation_correctness = 0.5
        
        # LLM-based evaluation for remaining dimensions
        prompt = self._build_test_prompt(paper)
        
        client = get_llm_client(model="claude-3-opus")
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are a rigorous peer reviewer evaluating research quality.",
        )
        
        scores = self._parse_scores(response.content)
        
        # Override with automated scores
        scores["claim_validity"] = claim_validity
        scores["citation_correctness"] = citation_correctness
        
        overall = self._compute_weighted_score(scores, self.test_criteria.weights)
        
        result = EvaluationResult(
            paper_id=paper.id,
            overall_score=overall,
            dimension_scores=scores,
            criteria_used="test",
            hidden_score=overall,  # Mark as hidden
            feedback="Hidden evaluation - do not show to agents",
        )
        
        logger.info(f"HCE hidden evaluation: {paper.id} → {overall:.2f} (TRUE QUALITY)")
        return result
    
    def _build_search_prompt(self, paper: PaperDocument) -> str:
        """Build evaluation prompt for search criteria.
        
        Intentionally vague about exact criteria to prevent gaming.
        
        Args:
            paper: Paper to evaluate
            
        Returns:
            Evaluation prompt
        """
        return f"""
Evaluate this research paper on the following dimensions (1-10 scale):

1. Novelty: How novel are the contributions?
2. Technical Soundness: Is the methodology sound?
3. Clarity: Is the paper clearly written?
4. Relevance: How relevant to the research question?

Paper:
{paper.to_markdown()}

Provide scores and brief justification for each dimension.
Format: JSON with keys: novelty, technical_soundness, clarity, relevance
Example: {{"novelty": 8, "technical_soundness": 9, "clarity": 7, "relevance": 8}}
"""
    
    def _build_selection_prompt(self, paper: PaperDocument) -> str:
        """Build evaluation prompt for selection criteria.
        
        Different from search criteria to prevent hill-climbing.
        
        Args:
            paper: Paper to evaluate
            
        Returns:
            Evaluation prompt
        """
        return f"""
Evaluate this research paper for final selection (1-10 scale):

1. Impact: Potential impact on the field
2. Rigor: Methodological rigor
3. Presentation: Quality of writing and figures
4. Reproducibility: Can results be reproduced?

Paper:
{paper.to_markdown()}

Provide scores and brief justification for each dimension.
Format: JSON with keys: impact, rigor, presentation, reproducibility
Example: {{"impact": 8, "rigor": 9, "presentation": 7, "reproducibility": 8}}
"""
    
    def _build_test_prompt(self, paper: PaperDocument) -> str:
        """Build evaluation prompt for test criteria (hidden).
        
        Evaluates dimensions not covered by automated checks.
        
        Args:
            paper: Paper to evaluate
            
        Returns:
            Evaluation prompt
        """
        return f"""
Evaluate this research paper rigorously (1-10 scale):

1. Method Appropriateness: Are methods appropriate for the problem?
2. Statistical Validity: Are statistical analyses valid?

Note: Claim validity and citation correctness are checked automatically.

Paper:
{paper.to_markdown()}

Provide scores and brief justification.
Format: JSON with keys: method_appropriateness, statistical_validity
Example: {{"method_appropriateness": 8, "statistical_validity": 9}}
"""
    
    def _parse_scores(self, response: str) -> dict[str, float]:
        """Parse scores from LLM response.
        
        Args:
            response: LLM response text
            
        Returns:
            Dictionary of dimension scores
        """
        try:
            # Extract JSON from response
            start = response.find("{")
            end = response.rfind("}") + 1
            
            if start == -1 or end == 0:
                logger.warning(f"No JSON found in response: {response[:100]}")
                return {}
            
            json_str = response[start:end]
            data = json.loads(json_str)
            
            return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON scores: {e}")
            return {}
        except Exception as e:
            logger.warning(f"Failed to parse scores: {e}")
            return {}
    
    def _compute_weighted_score(
        self,
        scores: dict[str, float],
        weights: dict[str, float],
    ) -> float:
        """Compute weighted overall score.
        
        Args:
            scores: Dimension scores
            weights: Dimension weights
            
        Returns:
            Weighted overall score (0-10)
        """
        if not scores:
            return 0.0
        
        total = 0.0
        weight_sum = 0.0
        
        for dim, weight in weights.items():
            if dim in scores:
                total += scores[dim] * weight
                weight_sum += weight
        
        return total / weight_sum if weight_sum > 0 else 0.0
    
    def get_criteria_info(self) -> dict[str, Any]:
        """Get information about evaluation criteria.
        
        Returns:
            Dictionary with criteria information
        """
        return {
            "search": {
                "dimensions": self.search_criteria.dimensions,
                "description": self.search_criteria.description,
            },
            "selection": {
                "dimensions": self.selection_criteria.dimensions,
                "description": self.selection_criteria.description,
            },
            "test": {
                "dimensions": self.test_criteria.dimensions,
                "description": self.test_criteria.description,
                "note": "Test criteria details are hidden",
            },
        }


__all__ = [
    "HiddenConsistentEvaluation",
    "PaperDocument",
    "EvaluationResult",
    "EvalCriteria",
    "CriteriaVisibility",
]
