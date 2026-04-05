"""Benchmark Integration (Upgrade 12).

Integrates Benchmark Framework with post-pipeline evaluation:
- Post-Pipeline: Quality assessment
- Continuous: Improvement tracking

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from berb.benchmarks.evaluation_framework import (
    BerbBenchmarkFramework,
    DRACOScore,
    BenchmarkResult,
)

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkReport:
    """Benchmark evaluation report.
    
    Attributes:
        draco_score: DRACO evaluation score
        paper_id: Evaluated paper ID
        timestamp: Evaluation timestamp
        passed: Whether paper passed benchmarks
        issues: List of identified issues
    """
    draco_score: DRACOScore
    paper_id: str
    timestamp: datetime
    passed: bool
    issues: list[str]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "draco_score": {
                "overall": self.draco_score.overall_score,
                "factual_accuracy": self.draco_score.factual_accuracy,
                "breadth_depth": self.draco_score.breadth_depth,
                "presentation": self.draco_score.presentation,
                "citation_quality": self.draco_score.citation_quality,
            },
            "timestamp": self.timestamp.isoformat(),
            "passed": self.passed,
            "issues": self.issues,
        }


class BenchmarkIntegration:
    """Integrates benchmark framework with pipeline.
    
    Usage in pipeline:
        integration = BenchmarkIntegration(output_dir)
        report = await integration.evaluate_paper(paper)
    """
    
    def __init__(
        self,
        output_dir: Path,
        draco_threshold: float = 7.0,
    ):
        """Initialize benchmark integration.
        
        Args:
            output_dir: Directory for benchmark reports
            draco_threshold: DRACO score threshold
        """
        self.output_dir = output_dir
        self.draco_threshold = draco_threshold
        self.framework = BerbBenchmarkFramework()
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            f"Initialized BenchmarkIntegration: "
            f"output={output_dir}, threshold={draco_threshold}"
        )
    
    async def evaluate_paper(
        self,
        paper: Any,
        paper_id: str,
    ) -> BenchmarkReport:
        """Post-pipeline: Evaluate paper quality.
        
        Args:
            paper: Paper to evaluate
            paper_id: Paper identifier
            
        Returns:
            Benchmark report
        """
        logger.info(f"Evaluating paper {paper_id} with DRACO")
        
        # DRACO evaluation
        scores = await self.framework.evaluate_paper_quality([paper])
        draco_score = scores[0] if scores else DRACOScore(
            overall_score=0.0,
            factual_accuracy=0.0,
            breadth_depth=0.0,
            presentation=0.0,
            citation_quality=0.0,
        )
        
        # Determine pass/fail
        passed = draco_score.overall_score >= self.draco_threshold
        
        # Collect issues
        issues = []
        if draco_score.factual_accuracy < self.draco_threshold:
            issues.append(f"Factual accuracy below threshold: {draco_score.factual_accuracy:.1f}")
        if draco_score.citation_quality < self.draco_threshold:
            issues.append(f"Citation quality below threshold: {draco_score.citation_quality:.1f}")
        
        # Create report
        report = BenchmarkReport(
            draco_score=draco_score,
            paper_id=paper_id,
            timestamp=datetime.now(),
            passed=passed,
            issues=issues,
        )
        
        # Save report
        await self._save_report(report)
        
        logger.info(
            f"Benchmark complete: {paper_id} - "
            f"DRACO={draco_score.overall_score:.1f}, passed={passed}"
        )
        
        return report
    
    async def _save_report(self, report: BenchmarkReport) -> None:
        """Save benchmark report to file.
        
        Args:
            report: Benchmark report
        """
        report_file = self.output_dir / f"{report.paper_id}_benchmark.json"
        
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)
        
        logger.debug(f"Saved benchmark report to {report_file}")
    
    async def compare_with_baseline(
        self,
        current_score: DRACOScore,
        baseline_file: Path,
    ) -> dict[str, Any]:
        """Compare current score with baseline.
        
        Args:
            current_score: Current DRACO score
            baseline_file: Path to baseline report
            
        Returns:
            Comparison results
        """
        if not baseline_file.exists():
            return {"error": "Baseline not found"}
        
        with open(baseline_file, encoding="utf-8") as f:
            baseline_data = json.load(f)
        
        baseline_score = baseline_data["draco_score"]["overall"]
        current_overall = current_score.overall_score
        
        improvement = current_overall - baseline_score
        improvement_pct = (improvement / baseline_score * 100) if baseline_score > 0 else 0
        
        return {
            "baseline_score": baseline_score,
            "current_score": current_overall,
            "improvement": improvement,
            "improvement_pct": improvement_pct,
            "improved": improvement > 0,
        }
    
    async def generate_summary_report(
        self,
        papers_evaluated: int,
        avg_draco_score: float,
        pass_rate: float,
    ) -> dict[str, Any]:
        """Generate summary report for multiple papers.
        
        Args:
            papers_evaluated: Number of papers evaluated
            avg_draco_score: Average DRACO score
            pass_rate: Pass rate percentage
            
        Returns:
            Summary report
        """
        summary = {
            "papers_evaluated": papers_evaluated,
            "avg_draco_score": avg_draco_score,
            "pass_rate": pass_rate,
            "quality_assessment": self._assess_quality(avg_draco_score),
            "timestamp": datetime.now().isoformat(),
        }
        
        # Save summary
        summary_file = self.output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Generated summary report: {summary_file}")
        
        return summary
    
    def _assess_quality(self, avg_score: float) -> str:
        """Assess overall quality level.
        
        Args:
            avg_score: Average DRACO score
            
        Returns:
            Quality assessment
        """
        if avg_score >= 9.0:
            return "Excellent - Publication ready"
        elif avg_score >= 7.5:
            return "Good - Minor revisions needed"
        elif avg_score >= 6.0:
            return "Fair - Significant revisions needed"
        else:
            return "Poor - Major revision or rejection"


async def run_benchmark_evaluation(
    paper: Any,
    paper_id: str,
    output_dir: Path,
    draco_threshold: float = 7.0,
) -> BenchmarkReport:
    """Post-pipeline: Run benchmark evaluation.
    
    Args:
        paper: Paper to evaluate
        paper_id: Paper identifier
        output_dir: Output directory
        draco_threshold: DRACO threshold
        
    Returns:
        Benchmark report
    """
    integration = BenchmarkIntegration(output_dir, draco_threshold)
    return await integration.evaluate_paper(paper, paper_id)
