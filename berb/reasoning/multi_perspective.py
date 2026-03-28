"""Multi-Perspective Reasoning Method for Berb.

Based on AI Scientist V2 (Nature 2026) - Section 3.1

This method analyzes problems from 4 distinct perspectives:
1. Constructive: Build the strongest solution
2. Destructive: Find every flaw
3. Systemic: Identify second/third-order effects
4. Minimalist: Find simplest 80% solution (Occam's Razor)

Key Features:
- Parallel perspective generation
- Critique and scoring
- Top-k selection
- Steel-man arguments for weakest candidates

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.reasoning.multi_perspective import MultiPerspectiveMethod
    
    method = MultiPerspectiveMethod(router)
    result = await method.execute(context)
    
    # Access results
    perspectives = result.output["perspectives"]
    scores = result.output["scores"]
    top_candidates = result.output["top_candidates"]
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from berb.reasoning.base import (
    MethodType,
    ReasoningContext,
    ReasoningMethod,
    ReasoningResult,
)

logger = logging.getLogger(__name__)


class PerspectiveType(str, Enum):
    """Type of perspective for multi-perspective analysis."""
    
    CONSTRUCTIVE = "constructive"
    """Build the strongest solution"""
    
    DESTRUCTIVE = "destructive"
    """Find every flaw"""
    
    SYSTEMIC = "systemic"
    """Identify second/third-order effects"""
    
    MINIMALIST = "minimalist"
    """Find simplest 80% solution (Occam's Razor)"""


@dataclass
class PerspectiveCandidate:
    """Candidate solution from a perspective."""
    
    perspective: PerspectiveType
    content: str
    key_insights: list[str] = field(default_factory=list)
    model_used: str = ""
    tokens_used: int = 0
    cost: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "perspective": self.perspective.value,
            "content": self.content,
            "key_insights": self.key_insights,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
        }


@dataclass
class PerspectiveScore:
    """Score for a perspective candidate."""
    
    perspective: PerspectiveType
    logical_consistency: float = 0.0  # 0-10
    evidence_support: float = 0.0  # 0-10
    feasibility: float = 0.0  # 0-10
    novelty: float = 0.0  # 0-10
    steel_man: str = ""  # Strongest counter-argument
    confidence_vs_accuracy_penalty: float = 0.0  # Penalty for overconfidence
    
    @property
    def total(self) -> float:
        """Calculate total score (0-10)."""
        return (
            self.logical_consistency
            + self.evidence_support
            + self.feasibility
            + self.novelty
        ) / 4.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "perspective": self.perspective.value,
            "logical_consistency": self.logical_consistency,
            "evidence_support": self.evidence_support,
            "feasibility": self.feasibility,
            "novelty": self.novelty,
            "total": self.total,
            "steel_man": self.steel_man,
            "confidence_vs_accuracy_penalty": self.confidence_vs_accuracy_penalty,
        }


class MultiPerspectiveMethod(ReasoningMethod):
    """Multi-perspective reasoning method.
    
    Analyzes problems from 4 distinct perspectives in parallel,
    then critiques and scores each to select the best candidates.
    
    Attributes:
        router: LLM model router for perspective generation
        parallel: Whether to run perspectives in parallel
        top_k: Number of top candidates to return
    """
    
    method_type = MethodType.MULTI_PERSPECTIVE
    
    def __init__(
        self,
        router: Any | None = None,
        parallel: bool = True,
        top_k: int = 2,
        name: str | None = None,
        description: str | None = None,
    ):
        """
        Initialize multi-perspective method.
        
        Args:
            router: LLM model router (provides get_provider_for_role)
            parallel: Run perspectives in parallel (default: True)
            top_k: Number of top candidates to return (default: 2)
            name: Human-readable name
            description: Description of the method
        """
        super().__init__(
            name=name or "Multi-Perspective Analysis",
            description=description or (
                "Analyzes problems from 4 perspectives: "
                "constructive, destructive, systemic, minimalist"
            ),
        )
        self.router = router
        self.parallel = parallel
        self.top_k = top_k
    
    async def execute(self, context: ReasoningContext) -> ReasoningResult:
        """
        Execute multi-perspective analysis.
        
        Args:
            context: Reasoning context with problem description
        
        Returns:
            ReasoningResult with perspectives, scores, and top candidates
        """
        import time
        t0 = time.monotonic()
        
        # Validate context
        if not self.validate_context(context):
            return ReasoningResult.error_result(
                self.method_type,
                "Invalid context: missing stage_id or input_data",
            )
        
        # Extract problem from context
        problem = context.get("problem") or context.get("query") or context.get("topic")
        if not problem:
            return ReasoningResult.error_result(
                self.method_type,
                "Context missing problem/query/topic",
            )
        
        try:
            # Generate perspectives
            perspectives = await self._generate_perspectives(problem)
            
            # Critique and score
            scores = await self._critique_and_score(perspectives, problem)
            
            # Select top-k candidates
            top_candidates = self._select_top_candidates(perspectives, scores, self.top_k)
            
            # Generate steel-man arguments for weakest
            await self._generate_steel_man(perspectives, scores)
            
            elapsed = time.monotonic() - t0
            
            return ReasoningResult.success_result(
                method_type=self.method_type,
                output={
                    "perspectives": [p.to_dict() for p in perspectives],
                    "scores": [s.to_dict() for s in scores],
                    "top_candidates": [c.to_dict() for c in top_candidates],
                },
                confidence=max(s.total for s in scores) / 10.0 if scores else 0.0,
                metadata={
                    "num_perspectives": len(perspectives),
                    "parallel": self.parallel,
                    "top_k": self.top_k,
                    "duration_sec": elapsed,
                },
            )
            
        except Exception as e:
            self._logger.error("Multi-perspective analysis failed: %s", e)
            return ReasoningResult.error_result(
                self.method_type,
                str(e),
            )
    
    async def _generate_perspectives(
        self,
        problem: str,
    ) -> list[PerspectiveCandidate]:
        """Generate perspectives in parallel or sequentially."""
        perspectives = list(PerspectiveType)
        
        if self.parallel:
            # Run all perspectives concurrently
            tasks = [
                self._generate_single_perspective(p, problem)
                for p in perspectives
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions
            candidates = [r for r in results if isinstance(r, PerspectiveCandidate)]
            
            if len(candidates) < len(perspectives):
                self._logger.warning(
                    "Only %d/%d perspectives generated successfully",
                    len(candidates),
                    len(perspectives),
                )
            
            return candidates
        else:
            # Run sequentially
            candidates = []
            for p in perspectives:
                try:
                    candidate = await self._generate_single_perspective(p, problem)
                    candidates.append(candidate)
                except Exception as e:
                    self._logger.warning("Perspective %s failed: %s", p.value, e)
            
            return candidates
    
    async def _generate_single_perspective(
        self,
        perspective: PerspectiveType,
        problem: str,
    ) -> PerspectiveCandidate:
        """Generate single perspective."""
        # Get LLM provider for this perspective
        provider = self._get_provider_for_perspective(perspective)
        
        # Build prompt
        prompt = self._build_perspective_prompt(perspective, problem)
        
        # Call LLM
        response = await provider.complete(prompt)
        
        # Parse response
        content, insights = self._parse_perspective_response(response.content)
        
        return PerspectiveCandidate(
            perspective=perspective,
            content=content,
            key_insights=insights,
            model_used=getattr(provider, "model", "unknown"),
            tokens_used=getattr(response, "tokens", 0),
            cost=getattr(response, "cost", 0.0),
        )
    
    def _get_provider_for_perspective(self, perspective: PerspectiveType) -> Any:
        """Get LLM provider for perspective."""
        if self.router is None:
            self._logger.warning("No router configured, using fallback")
            return _FallbackProvider()
        
        # Get provider based on perspective role
        role_map = {
            PerspectiveType.CONSTRUCTIVE: "constructive",
            PerspectiveType.DESTRUCTIVE: "destructive",
            PerspectiveType.SYSTEMIC: "systemic",
            PerspectiveType.MINIMALIST: "minimalist",
        }
        
        role = role_map[perspective]
        return self.router.get_provider_for_role(role)
    
    def _build_perspective_prompt(
        self,
        perspective: PerspectiveType,
        problem: str,
    ) -> str:
        """Build prompt for perspective generation."""
        prompts = {
            PerspectiveType.CONSTRUCTIVE: f"""You are a constructive problem solver.
Your task is to build the STRONGEST possible solution to this problem.

Problem: {problem}

Focus on:
- Building a robust, well-supported solution
- Identifying strengths and opportunities
- Providing concrete, actionable steps

Output your solution with key insights as bullet points.

JSON format: {{"solution": "...", "key_insights": ["insight1", "insight2"]}}""",
            
            PerspectiveType.DESTRUCTIVE: f"""You are a critical adversary.
Your task is to find EVERY FLAW in potential solutions to this problem.

Problem: {problem}

Focus on:
- Identifying weaknesses and vulnerabilities
- Finding edge cases and failure modes
- Challenging assumptions

Output your critique with key flaws as bullet points.

JSON format: {{"critique": "...", "key_insights": ["flaw1", "flaw2"]}}""",
            
            PerspectiveType.SYSTEMIC: f"""You are a systems thinker.
Your task is to identify SECOND and THIRD-ORDER EFFECTS of solutions.

Problem: {problem}

Focus on:
- Long-term consequences
- Unintended side effects
- Systemic interactions and feedback loops

Output your analysis with key systemic effects as bullet points.

JSON format: {{"analysis": "...", "key_insights": ["effect1", "effect2"]}}""",
            
            PerspectiveType.MINIMALIST: f"""You are a minimalist problem solver (Occam's Razor).
Your task is to find the SIMPLEST solution that achieves 80% of the value.

Problem: {problem}

Focus on:
- Simplest viable solution
- Minimum complexity
- Core essentials only

Output your minimal solution with key simplifications as bullet points.

JSON format: {{"solution": "...", "key_insights": ["simplification1", "simplification2"]}}""",
        }
        
        return prompts[perspective]
    
    def _parse_perspective_response(
        self,
        response: str,
    ) -> tuple[str, list[str]]:
        """Parse perspective response."""
        import json
        import re
        
        # Try to extract JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                content = data.get("solution", data.get("critique", data.get("analysis", "")))
                insights = data.get("key_insights", [])
                return content, insights
            except json.JSONDecodeError:
                pass
        
        # Fallback: use entire response
        return response, []
    
    async def _critique_and_score(
        self,
        perspectives: list[PerspectiveCandidate],
        problem: str,
    ) -> list[PerspectiveScore]:
        """Critique and score all perspectives."""
        # Get scoring provider
        provider = self._get_scoring_provider()
        
        # Build critique prompt
        prompt = self._build_critique_prompt(perspectives, problem)
        
        # Call LLM for scoring
        response = await provider.complete(prompt)
        
        # Parse scores
        scores = self._parse_critique_response(response.content, perspectives)
        
        return scores
    
    def _get_scoring_provider(self) -> Any:
        """Get LLM provider for scoring."""
        if self.router is None:
            return _FallbackProvider()
        
        return self.router.get_provider_for_role("scoring")
    
    def _build_critique_prompt(
        self,
        perspectives: list[PerspectiveCandidate],
        problem: str,
    ) -> str:
        """Build critique prompt."""
        candidates_str = "\n\n".join([
            f"### {p.perspective.value.upper()}:\n{p.content}\nInsights: {', '.join(p.key_insights)}"
            for p in perspectives
        ])
        
        return f"""You are an objective evaluator. Score each perspective on the following criteria:

Problem: {problem}

Candidates:
{candidates_str}

Scoring Criteria (0-10 for each):
1. Logical Consistency: Is the reasoning sound?
2. Evidence Support: Is it grounded in evidence?
3. Feasibility: Can it be implemented?
4. Novelty: Does it provide new insights?

CRITICAL: Apply a negative penalty (0.0-10.0) for claims made with high confidence that are factually incorrect or unsubstantiated. Reward honest uncertainty.

Output JSON format:
{{
    "scores": [
        {{"perspective": "constructive", "logical_consistency": 8, "evidence_support": 7, "feasibility": 9, "novelty": 6, "confidence_vs_accuracy_penalty": 0.0}},
        ...
    ]
}}"""
    
    def _parse_critique_response(
        self,
        response: str,
        perspectives: list[PerspectiveCandidate],
    ) -> list[PerspectiveScore]:
        """Parse critique response."""
        import json
        import re
        
        # Try to extract JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                scores_data = data.get("scores", [])
                
                scores = []
                for s in scores_data:
                    perspective = PerspectiveType(s.get("perspective", "constructive"))
                    scores.append(PerspectiveScore(
                        perspective=perspective,
                        logical_consistency=s.get("logical_consistency", 5.0),
                        evidence_support=s.get("evidence_support", 5.0),
                        feasibility=s.get("feasibility", 5.0),
                        novelty=s.get("novelty", 5.0),
                        confidence_vs_accuracy_penalty=s.get("confidence_vs_accuracy_penalty", 0.0),
                    ))
                
                return scores
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Fallback: equal scores
        return [
            PerspectiveScore(perspective=p.perspective)
            for p in perspectives
        ]
    
    def _select_top_candidates(
        self,
        perspectives: list[PerspectiveCandidate],
        scores: list[PerspectiveScore],
        top_k: int,
    ) -> list[PerspectiveCandidate]:
        """Select top-k candidates based on scores."""
        # Create score lookup
        score_map = {s.perspective: s.total for s in scores}
        
        # Sort by score
        sorted_perspectives = sorted(
            perspectives,
            key=lambda p: score_map.get(p.perspective, 0.0),
            reverse=True,
        )
        
        return sorted_perspectives[:top_k]
    
    async def _generate_steel_man(
        self,
        perspectives: list[PerspectiveCandidate],
        scores: list[PerspectiveScore],
    ) -> None:
        """Generate steel-man arguments for weakest candidates."""
        if not scores:
            return
        
        # Find weakest candidate
        weakest_score = min(scores, key=lambda s: s.total)
        weakest_perspective = next(
            p for p in perspectives if p.perspective == weakest_score.perspective
        )
        
        # Generate steel-man argument
        provider = self._get_scoring_provider()
        prompt = f"""Generate the STRONGEST possible argument (steel-man) for this perspective:

Perspective: {weakest_perspective.perspective.value}
Content: {weakest_perspective.content[:500]}

What is the most compelling case for this perspective, even if you disagree?"""
        
        response = await provider.complete(prompt)
        weakest_score.steel_man = response.content


class _FallbackProvider:
    """Fallback LLM provider when router is not configured."""
    
    model = "fallback"
    
    async def complete(self, prompt: str) -> Any:
        """Return mock response."""
        from dataclasses import dataclass
        
        @dataclass
        class MockResponse:
            content: str = '{"solution": "Fallback solution", "key_insights": ["fallback"]}'
            tokens: int = 0
            cost: float = 0.0
        
        return MockResponse()
