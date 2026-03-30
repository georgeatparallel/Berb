"""Reasoner Bridge - ARA Pipeline integration for Berb.

This module provides integration with Reasoner (ARA Pipeline) for:
- Multi-perspective reasoning (4 perspectives)
- Stress testing for experiment design
- Context vetting with CoT detection
- Structured critique scoring

Architecture: Strategy + Template Method patterns
Paradigm: Functional + Async

Example:
    >>> bridge = ReasonerBridge(config)
    >>> hypotheses = await bridge.generate_hypotheses(research_gap)
    >>> stress_test = await bridge.stress_test(experiment_design)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enums and Data Classes
# ─────────────────────────────────────────────────────────────────────────────

class PerspectiveType(str, Enum):
    """Reasoning perspective types."""
    CONSTRUCTIVE = "constructive"
    DESTRUCTIVE = "destructive"
    SYSTEMIC = "systemic"
    MINIMALIST = "minimalist"


class StressScenario(str, Enum):
    """Stress test scenarios."""
    OPTIMAL = "optimal"
    CONSTRAINT_VIOLATION = "constraint_violation"
    ADVERSARIAL = "adversarial"


@dataclass
class HypothesisCandidate:
    """Hypothesis from one perspective.
    
    Attributes:
        perspective: Perspective type
        content: Hypothesis content
        key_insights: Key insights
        confidence: Confidence score (0-1)
        model_used: Model used for generation
    """
    perspective: PerspectiveType
    content: str
    key_insights: List[str]
    confidence: float
    model_used: str
    total_score: float = 0.0


@dataclass
class StressTestResult:
    """Stress test result.
    
    Attributes:
        scenario: Test scenario
        survival_rate: Survival rate (0.0-1.0)
        failure_mode: Failure mode description
        recovery_path: Recovery path
        severity: low/medium/high/critical
    """
    scenario: StressScenario
    survival_rate: float
    failure_mode: str
    recovery_path: str
    severity: str


@dataclass
class CritiqueScore:
    """Critique score for hypothesis/experiment.
    
    Attributes:
        logical_consistency: 0-10 score
        evidence_support: 0-10 score
        failure_resilience: 0-10 score
        feasibility: 0-10 score
        bias_flags: List of bias flags
        steel_man: Strongest counter-argument
        confidence_penalty: Penalty for overconfidence
    """
    logical_consistency: float = 0.0
    evidence_support: float = 0.0
    failure_resilience: float = 0.0
    feasibility: float = 0.0
    bias_flags: List[str] = field(default_factory=list)
    steel_man: str = ""
    confidence_penalty: float = 0.0
    
    @property
    def total(self) -> float:
        """Total score (average of 4 dimensions)."""
        return (
            self.logical_consistency +
            self.evidence_support +
            self.failure_resilience +
            self.feasibility
        ) / 4.0


# ─────────────────────────────────────────────────────────────────────────────
# Complexity Classifier (Lightweight)
# ─────────────────────────────────────────────────────────────────────────────

class ComplexityClassifier:
    """Binary complexity classifier using heuristics.
    
    Classifies prompts as simple or complex using:
    - Length-based heuristics
    - Keyword detection
    - Structure analysis
    """
    
    COMPLEX_KEYWORDS = [
        "analyze", "design", "architect", "implement", "optimize",
        "compare", "evaluate", "synthesize", "debug", "refactor",
        "multi-step", "complex", "advanced", "comprehensive",
    ]
    
    SIMPLE_KEYWORDS = [
        "what is", "define", "list", "show", "print",
        "hello", "help", "quick", "simple", "basic",
    ]
    
    def __init__(self, length_threshold: int = 100):
        self.length_threshold = length_threshold
    
    def classify(self, prompt: str) -> Tuple[bool, float]:
        """Classify prompt complexity.
        
        Returns:
            (is_complex, confidence)
        """
        prompt_lower = prompt.lower()
        
        # Length scoring
        length_score = min(1.0, len(prompt) / self.length_threshold)
        
        # Keyword scoring
        complex_count = sum(1 for kw in self.COMPLEX_KEYWORDS if kw in prompt_lower)
        simple_count = sum(1 for kw in self.SIMPLE_KEYWORDS if kw in prompt_lower)
        
        keyword_score = (complex_count - simple_count) / 5
        complexity_score = (length_score + keyword_score) / 2
        
        is_complex = complexity_score > 0.5
        confidence = abs(complexity_score - 0.5) * 2
        
        return is_complex, min(1.0, confidence)


# ─────────────────────────────────────────────────────────────────────────────
# Reasoner Bridge
# ─────────────────────────────────────────────────────────────────────────────

class ReasonerBridge:
    """Bridge to Reasoner (ARA Pipeline) reasoning capabilities.
    
    Provides:
    - Multi-perspective hypothesis generation
    - Stress testing for experiments
    - Context vetting
    - Structured critique scoring
    
    Example:
        >>> bridge = ReasonerBridge(llm_client)
        >>> hypotheses = await bridge.generate_hypotheses(gap)
    """
    
    def __init__(self, llm_client: Any, config: Optional[Any] = None):
        """Initialize Reasoner Bridge.
        
        Args:
            llm_client: LLM client for reasoning calls
            config: Optional configuration
        """
        self._llm_client = llm_client
        self._classifier = ComplexityClassifier()
        
        self._perspectives = list(PerspectiveType)
        self._stress_scenarios = list(StressScenario)
        
        logger.info("ReasonerBridge initialized")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Multi-Perspective Hypothesis Generation
    # ─────────────────────────────────────────────────────────────────────────
    
    async def generate_hypotheses(
        self,
        research_gap: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[HypothesisCandidate]:
        """Generate hypotheses using multi-perspective analysis.
        
        Args:
            research_gap: Research gap to address
            context: Optional context dict
        
        Returns:
            List of HypothesisCandidate objects
        """
        import asyncio
        
        # Generate hypotheses in parallel for each perspective
        tasks = [
            self._generate_perspective(research_gap, context or {}, perspective)
            for perspective in self._perspectives
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        candidates = [r for r in results if isinstance(r, HypothesisCandidate)]
        
        # Score candidates
        scored = await self._score_candidates(candidates, research_gap)
        
        logger.info(
            f"Generated {len(scored)} hypotheses via "
            f"multi-perspective analysis"
        )
        
        return scored
    
    async def _generate_perspective(
        self,
        research_gap: str,
        context: Dict[str, Any],
        perspective: PerspectiveType,
    ) -> HypothesisCandidate:
        """Generate hypothesis from one perspective."""
        
        system_prompts = {
            PerspectiveType.CONSTRUCTIVE: (
                "Build the strongest possible hypothesis. "
                "Focus on evidence support and logical coherence."
            ),
            PerspectiveType.DESTRUCTIVE: (
                "Find every flaw in existing approaches. "
                "Be critical and thorough."
            ),
            PerspectiveType.SYSTEMIC: (
                "Identify 2nd and 3rd-order effects. "
                "Consider system-wide impacts."
            ),
            PerspectiveType.MINIMALIST: (
                "Apply Occam's Razor. "
                "Find the simplest 80% solution."
            ),
        }
        
        system_prompt = system_prompts[perspective]
        
        user_prompt = f"""Research Gap: {research_gap}

Context: {self._format_context(context)}

Generate a hypothesis from {perspective.value} perspective.

Output JSON: {{
    "hypothesis": "...",
    "key_insights": ["insight1", "insight2"],
    "confidence": 0.0-1.0
}}"""
        
        try:
            start = time.time()
            response = await self._llm_client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1536,
            )
            latency_ms = int((time.time() - start) * 1000)
            
            # Parse response (simplified - in production use extract_json)
            import json
            try:
                data = json.loads(response.content)
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning("Failed to parse hypothesis response: %s", e)
                data = {"hypothesis": response.content, "key_insights": [], "confidence": 0.5}
            
            return HypothesisCandidate(
                perspective=perspective,
                content=data.get("hypothesis", ""),
                key_insights=data.get("key_insights", []),
                confidence=data.get("confidence", 0.5),
                model_used=response.model,
            )
        
        except Exception as e:
            logger.warning(f"Failed to generate {perspective.value} hypothesis: {e}")
            return HypothesisCandidate(
                perspective=perspective,
                content="",
                key_insights=[],
                confidence=0.0,
                model_used="error",
            )
    
    async def _score_candidates(
        self,
        candidates: List[HypothesisCandidate],
        research_gap: str,
    ) -> List[HypothesisCandidate]:
        """Score candidates with structured critique."""
        
        candidate_summaries = [
            {
                "perspective": c.perspective.value,
                "hypothesis": c.content[:200],
                "insights": c.key_insights[:2],
            }
            for c in candidates
        ]
        
        system_prompt = """You are an objective evaluator. Score each hypothesis 0-10 on:
- logical_consistency: Internal logic soundness
- evidence_support: Backed by literature
- failure_resilience: Survives adversarial scenarios
- feasibility: Can be tested with available resources

Apply confidence_vs_accuracy_penalty: Penalize overconfident but unsubstantiated claims."""
        
        user_prompt = f"""Research Gap: {research_gap}

Candidates:
{self._format_json(candidate_summaries)}

Score each hypothesis."""
        
        try:
            response = await self._llm_client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1024,
            )
            
            import json
            try:
                data = json.loads(response.content)
                scores = data.get("scores", [])
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning("Failed to parse scoring response: %s", e)
                scores = []
            
            # Attach scores to candidates
            for candidate in candidates:
                score = next(
                    (s for s in scores if s.get("perspective") == candidate.perspective.value),
                    None,
                )
                if score:
                    critique = CritiqueScore(
                        logical_consistency=score.get("logical_consistency", 5),
                        evidence_support=score.get("evidence_support", 5),
                        failure_resilience=score.get("failure_resilience", 5),
                        feasibility=score.get("feasibility", 5),
                    )
                    candidate.total_score = critique.total
            
            # Sort by score
            candidates.sort(key=lambda c: c.total_score, reverse=True)
            
        except Exception as e:
            logger.warning(f"Failed to score candidates: {e}")
        
        return candidates
    
    # ─────────────────────────────────────────────────────────────────────────
    # Stress Testing
    # ─────────────────────────────────────────────────────────────────────────
    
    async def stress_test(
        self,
        experiment_design: Dict[str, Any],
        hypothesis: str,
        resource_limits: Optional[Dict[str, Any]] = None,
    ) -> List[StressTestResult]:
        """Run stress tests on experiment design.
        
        Args:
            experiment_design: Experiment design dict
            hypothesis: Research hypothesis
            resource_limits: Resource limits (memory, time, etc.)
        
        Returns:
            List of StressTestResult objects
        """
        import asyncio
        
        tasks = [
            self._run_scenario(experiment_design, hypothesis, resource_limits or {}, scenario)
            for scenario in self._stress_scenarios
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = [r for r in results if isinstance(r, StressTestResult)]
        
        # Check for critical failures
        critical = [r for r in valid_results if r.severity == "critical"]
        if critical:
            logger.warning(
                f"Critical failures detected: "
                f"{[r.failure_mode for r in critical]}"
            )
        
        return valid_results
    
    async def _run_scenario(
        self,
        experiment_design: Dict[str, Any],
        hypothesis: str,
        resource_limits: Dict[str, Any],
        scenario: StressScenario,
    ) -> StressTestResult:
        """Run single stress test scenario."""
        
        scenario_prompts = {
            StressScenario.OPTIMAL: "All resources available, ideal conditions",
            StressScenario.CONSTRAINT_VIOLATION: f"Resource limits: {resource_limits}",
            StressScenario.ADVERSARIAL: "Worst-case: noisy data, edge cases, distribution shift",
        }
        
        system_prompt = f"""You are simulating {scenario.value} conditions.

Analyze how this experiment design performs under stress.
Be specific about failure mechanics.

Output JSON: {{
    "survival_rate": 0.0-1.0,
    "failure_mode": "<specific failure>",
    "recovery_path": "<how to fix>",
    "severity": "low|medium|high|critical"
}}"""
        
        user_prompt = f"""Hypothesis: {hypothesis}

Experiment Design: {self._format_json(experiment_design)}

Scenario: {scenario_prompts[scenario]}

Analyze experiment performance."""
        
        try:
            response = await self._llm_client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1024,
            )
            
            import json
            try:
                data = json.loads(response.content)
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning("Failed to parse stress-test response: %s", e)
                data = {}

            return StressTestResult(
                scenario=scenario,
                survival_rate=float(data.get("survival_rate", 0.5)),
                failure_mode=data.get("failure_mode", ""),
                recovery_path=data.get("recovery_path", ""),
                severity=data.get("severity", "medium"),
            )
        
        except Exception as e:
            logger.warning(f"Failed stress test for {scenario.value}: {e}")
            return StressTestResult(
                scenario=scenario,
                survival_rate=0.0,
                failure_mode=str(e),
                recovery_path="",
                severity="high",
            )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Context Vetting
    # ─────────────────────────────────────────────────────────────────────────
    
    async def vet_context(
        self,
        paper_abstract: str,
        research_topic: str,
    ) -> Dict[str, Any]:
        """Vet a paper for quality issues.
        
        Args:
            paper_abstract: Paper abstract
            research_topic: Research topic
        
        Returns:
            Vetting result dict
        """
        
        system_prompt = """Detect these red flags:
1. COT_LEAKAGE: Chain-of-thought leakage
2. UNSUBSTANTIATED: Claims without citations
3. SPECULATIVE_AS_FACT: Speculation as fact
4. CONFLICT_OF_INTEREST: Undisclosed funding
5. OUTDATED: Information >5 years old

Output JSON: {
    "cot_leakage": bool,
    "unsubstantiated_claims": [str],
    "speculative_as_factual": bool,
    "conflict_of_interest": bool,
    "outdated": bool,
    "severity": "low|medium|high"
}"""
        
        user_prompt = f"""Research Topic: {research_topic}

Paper Abstract: {paper_abstract}

Vet this paper for quality issues."""
        
        try:
            response = await self._llm_client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=512,
            )
            
            import json
            try:
                data = json.loads(response.content)
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning("Failed to parse vetting response: %s", e)
                data = {}

            return data
        
        except Exception as e:
            logger.warning(f"Failed context vetting: {e}")
            return {"severity": "unknown", "error": str(e)}
    
    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def _format_context(context: Dict[str, Any]) -> str:
        """Format context dict for prompt."""
        import json
        return json.dumps(context, indent=2)
    
    @staticmethod
    def _format_json(obj: Any) -> str:
        """Format object as JSON string."""
        import json
        return json.dumps(obj, indent=2)
