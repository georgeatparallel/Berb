"""Benchmark Framework for Berb.

Based on PRBench (Peking U), HorizonMath, and DRACO:
"Evaluate Berb outputs against established research benchmarks."

Key Features:
- PRBench physics reproduction evaluation
- DRACO quality evaluation
- HorizonMath verification scoring
- External benchmark comparison

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.benchmarks.evaluation_framework import BerbBenchmarkFramework
    
    framework = BerbBenchmarkFramework()
    score = await framework.evaluate_paper_quality(papers)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PRBenchScore:
    """PRBench physics reproduction score.
    
    Attributes:
        overall_score: Overall score (0-100)
        code_correctness: Code correctness score
        result_reproduction: Result reproduction score
        efficiency: Computational efficiency score
        task_name: Benchmark task name
    """
    overall_score: float
    code_correctness: float
    result_reproduction: float
    efficiency: float
    task_name: str = ""


@dataclass
class DRACOScore:
    """DRACO evaluation score.
    
    Attributes:
        overall_score: Overall score (0-10)
        factual_accuracy: Factual accuracy (0-10)
        breadth_depth: Breadth and depth (0-10)
        presentation: Presentation quality (0-10)
        citation_quality: Citation quality (0-10)
    """
    overall_score: float
    factual_accuracy: float
    breadth_depth: float
    presentation: float
    citation_quality: float


@dataclass
class MathScore:
    """HorizonMath-inspired math verification score.
    
    Attributes:
        overall_score: Overall score (0-100)
        claims_verified: Number of verified claims
        claims_total: Total claims
        verification_rate: Claim verification rate
    """
    overall_score: float
    claims_verified: int
    claims_total: int
    verification_rate: float


@dataclass
class BenchmarkResult:
    """Complete benchmark result.
    
    Attributes:
        prbench: PRBench score (if applicable)
        draco: DRACO score
        math: Math score (if applicable)
        paper_id: Evaluated paper ID
        issues: List of identified issues
    """
    draco: DRACOScore
    prbench: PRBenchScore | None = None
    math: MathScore | None = None
    paper_id: str = ""
    issues: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "draco": {
                "overall_score": self.draco.overall_score,
                "factual_accuracy": self.draco.factual_accuracy,
                "breadth_depth": self.draco.breadth_depth,
                "presentation": self.draco.presentation,
                "citation_quality": self.draco.citation_quality,
            },
            "prbench": self.prbench.__dict__ if self.prbench else None,
            "math": self.math.__dict__ if self.math else None,
            "issues": self.issues,
        }


class BerbBenchmarkFramework:
    """Evaluate Berb outputs against established benchmarks.
    
    Benchmarks:
    - PRBench: Physics paper reproduction
    - DRACO: Research quality evaluation
    - HorizonMath: Mathematical verification
    
    Usage:
        framework = BerbBenchmarkFramework()
        result = await framework.evaluate_paper_quality(papers)
    """
    
    def __init__(self):
        """Initialize benchmark framework."""
        logger.info("Initialized BerbBenchmarkFramework")
    
    async def evaluate_on_prbench(
        self,
        physics_tasks: list[dict[str, Any]],
    ) -> list[PRBenchScore]:
        """Run Berb on PRBench physics reproduction tasks.
        
        Args:
            physics_tasks: List of physics tasks with ground truth
            
        Returns:
            List of PRBench scores
        """
        scores = []
        
        for task in physics_tasks:
            score = await self._evaluate_prbench_task(task)
            scores.append(score)
            logger.info(
                f"PRBench {task.get('name', 'unknown')}: "
                f"{score.overall_score:.1f}/100"
            )
        
        return scores
    
    async def _evaluate_prbench_task(
        self,
        task: dict[str, Any],
    ) -> PRBenchScore:
        """Evaluate single PRBench task.
        
        Args:
            task: Task dictionary
            
        Returns:
            PRBench score
        """
        # Compare output with ground truth
        ground_truth = task.get("ground_truth", {})
        output = task.get("output", {})
        
        # Code correctness
        code_correctness = self._compare_code(
            ground_truth.get("code", ""),
            output.get("code", ""),
        )
        
        # Result reproduction
        result_reproduction = self._compare_results(
            ground_truth.get("results", {}),
            output.get("results", {}),
        )
        
        # Efficiency
        efficiency = self._evaluate_efficiency(
            output.get("code", ""),
        )
        
        # Overall score
        overall = (
            code_correctness * 0.4 +
            result_reproduction * 0.4 +
            efficiency * 0.2
        )
        
        return PRBenchScore(
            overall_score=overall * 100,
            code_correctness=code_correctness * 100,
            result_reproduction=result_reproduction * 100,
            efficiency=efficiency * 100,
            task_name=task.get("name", "unknown"),
        )
    
    async def evaluate_paper_quality(
        self,
        papers: list[Any],
    ) -> list[DRACOScore]:
        """Evaluate using DRACO framework.
        
        Args:
            papers: List of papers to evaluate
            
        Returns:
            List of DRACO scores
        """
        scores = []
        
        for paper in papers:
            score = await self._evaluate_draco(paper)
            scores.append(score)
            logger.info(
                f"DRACO evaluation: {paper.id if hasattr(paper, 'id') else 'unknown'} "
                f"→ {score.overall_score:.1f}/10"
            )
        
        return scores
    
    async def _evaluate_draco(self, paper: Any) -> DRACOScore:
        """Evaluate paper using DRACO.
        
        Args:
            paper: Paper to evaluate
            
        Returns:
            DRACO score
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model="claude-3-opus")
        
        # Get paper content
        content = self._get_paper_content(paper)
        
        prompt = f"""
Evaluate this research paper using DRACO framework:

{content[:5000]}...

Rate on scale 1-10:
1. Factual Accuracy: Are claims factually correct?
2. Breadth & Depth: Comprehensive coverage?
3. Presentation: Clear writing and figures?
4. Citation Quality: Accurate, relevant citations?

Format as JSON:
{{
    "factual_accuracy": 8,
    "breadth_depth": 7,
    "presentation": 9,
    "citation_quality": 8
}}
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are evaluating research quality using DRACO.",
        )
        
        # Parse response
        scores = self._parse_draco_scores(response.content)
        
        overall = (
            scores["factual_accuracy"] * 0.35 +
            scores["breadth_depth"] * 0.30 +
            scores["presentation"] * 0.15 +
            scores["citation_quality"] * 0.20
        )
        
        return DRACOScore(
            overall_score=overall,
            factual_accuracy=scores["factual_accuracy"],
            breadth_depth=scores["breadth_depth"],
            presentation=scores["presentation"],
            citation_quality=scores["citation_quality"],
        )
    
    async def evaluate_mathematical_content(
        self,
        papers: list[Any],
    ) -> list[MathScore]:
        """HorizonMath-inspired: verify mathematical claims.
        
        Args:
            papers: List of papers to evaluate
            
        Returns:
            List of Math scores
        """
        scores = []
        
        for paper in papers:
            score = await self._evaluate_math(paper)
            scores.append(score)
            logger.info(
                f"Math verification: {paper.id if hasattr(paper, 'id') else 'unknown'} "
                f"→ {score.verification_rate:.1%}"
            )
        
        return scores
    
    async def _evaluate_math(self, paper: Any) -> MathScore:
        """Evaluate mathematical content.
        
        Args:
            paper: Paper to evaluate
            
        Returns:
            Math score
        """
        from berb.math.verification import VerifiableMathContent
        
        verifier = VerifiableMathContent()
        
        # Extract claims from paper
        claims = await self._extract_math_claims(paper)
        
        # Verify each claim
        verified = 0
        for claim in claims:
            result = await verifier.verify_equation_numerically(
                claim.get("equation", ""),
                claim.get("test_values", {}),
            )
            if result:
                verified += 1
        
        total = len(claims)
        rate = verified / total if total > 0 else 0.0
        
        return MathScore(
            overall_score=rate * 100,
            claims_verified=verified,
            claims_total=total,
            verification_rate=rate,
        )
    
    def _compare_code(
        self,
        ground_truth: str,
        output: str,
    ) -> float:
        """Compare output code with ground truth.
        
        Args:
            ground_truth: Ground truth code
            output: Output code
            
        Returns:
            Similarity score (0-1)
        """
        # Simple string comparison (could be improved with AST)
        if not ground_truth or not output:
            return 0.0
        
        # Normalize
        gt_normalized = self._normalize_code(ground_truth)
        out_normalized = self._normalize_code(output)
        
        # Compare
        if gt_normalized == out_normalized:
            return 1.0
        
        # Partial match
        common_lines = set(gt_normalized.split("\n")) & set(out_normalized.split("\n"))
        total_lines = len(set(gt_normalized.split("\n")))
        
        return len(common_lines) / total_lines if total_lines > 0 else 0.0
    
    def _compare_results(
        self,
        ground_truth: dict[str, Any],
        output: dict[str, Any],
    ) -> float:
        """Compare output results with ground truth.
        
        Args:
            ground_truth: Ground truth results
            output: Output results
            
        Returns:
            Similarity score (0-1)
        """
        if not ground_truth or not output:
            return 0.0
        
        # Compare numeric values
        matches = 0
        total = 0
        
        for key, gt_value in ground_truth.items():
            if key in output:
                total += 1
                out_value = output[key]
                
                if isinstance(gt_value, (int, float)) and isinstance(out_value, (int, float)):
                    # Check if within 5% tolerance
                    if abs(gt_value - out_value) / max(abs(gt_value), 1e-10) < 0.05:
                        matches += 1
                elif str(gt_value) == str(out_value):
                    matches += 1
        
        return matches / total if total > 0 else 0.0
    
    def _evaluate_efficiency(self, code: str) -> float:
        """Evaluate code efficiency.
        
        Args:
            code: Code to evaluate
            
        Returns:
            Efficiency score (0-1)
        """
        # Check for efficiency anti-patterns
        anti_patterns = [
            ("for i in range(len(", "vectorization"),
            ("np.kron", "tensor_ops"),
            ("dense", "sparse"),
        ]
        
        score = 1.0
        for pattern, _ in anti_patterns:
            if pattern in code:
                score -= 0.2
        
        return max(0.0, score)
    
    def _normalize_code(self, code: str) -> str:
        """Normalize code for comparison.
        
        Args:
            code: Code to normalize
            
        Returns:
            Normalized code
        """
        # Remove comments
        import re
        code = re.sub(r'#.*', '', code)
        
        # Remove whitespace
        code = code.strip()
        
        return code
    
    def _get_paper_content(self, paper: Any) -> str:
        """Extract paper content.
        
        Args:
            paper: Paper object
            
        Returns:
            Paper content string
        """
        if hasattr(paper, 'to_markdown'):
            return paper.to_markdown()
        elif hasattr(paper, 'content'):
            return str(paper.content)
        elif hasattr(paper, 'text'):
            return str(paper.text)
        else:
            return str(paper)
    
    def _parse_draco_scores(self, response: str) -> dict[str, float]:
        """Parse DRACO scores from response.
        
        Args:
            response: LLM response
            
        Returns:
            Score dictionary
        """
        import json
        
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)
                
                return {
                    "factual_accuracy": float(data.get("factual_accuracy", 5)),
                    "breadth_depth": float(data.get("breadth_depth", 5)),
                    "presentation": float(data.get("presentation", 5)),
                    "citation_quality": float(data.get("citation_quality", 5)),
                }
        except Exception as e:
            logger.warning(f"Failed to parse DRACO scores: {e}")
        
        return {
            "factual_accuracy": 5.0,
            "breadth_depth": 5.0,
            "presentation": 5.0,
            "citation_quality": 5.0,
        }
    
    async def _extract_math_claims(self, paper: Any) -> list[dict[str, Any]]:
        """Extract mathematical claims from paper.
        
        Args:
            paper: Paper object
            
        Returns:
            List of claims
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model="gpt-4o")
        
        content = self._get_paper_content(paper)
        
        prompt = f"""
Extract mathematical claims (equations, theorems) from this paper:

{content[:5000]}...

For each claim, provide:
1. The equation/claim
2. Test values for verification

Format as JSON list:
[
    {"equation": "a^2 + b^2 = c^2", "test_values": {"a": 3, "b": 4, "c": 5}}
]
"""
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
        )
        
        import json
        try:
            start = response.content.find("[")
            end = response.content.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(response.content[start:end])
        except Exception:
            pass
        
        return []


__all__ = [
    "BerbBenchmarkFramework",
    "PRBenchScore",
    "DRACOScore",
    "MathScore",
    "BenchmarkResult",
]
