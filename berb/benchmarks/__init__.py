"""Competitive Benchmarking Engine for Berb.

This module provides standardized benchmarks for measuring and comparing
Berb pipeline performance across different configurations and versions.

Features:
- 12 standard benchmark projects
- Quality, cost, and time metrics
- Public report generation
- Competitive comparison

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.benchmarks.runner import BenchmarkRunner
    
    runner = BenchmarkRunner()
    results = await runner.run_benchmark("hypothesis-generation")
    report = runner.generate_report()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BenchmarkCategory(str, Enum):
    """Benchmark categories."""
    HYPOTHESIS_GENERATION = "hypothesis-generation"
    EXPERIMENT_DESIGN = "experiment-design"
    LITERATURE_REVIEW = "literature-review"
    CODE_GENERATION = "code-generation"
    PAPER_WRITING = "paper-writing"
    FULL_PIPELINE = "full-pipeline"


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    
    benchmark_id: str
    category: str
    topic: str
    status: str  # success, failed, partial
    start_time: datetime
    end_time: datetime
    duration_sec: float
    total_cost: float
    total_tokens: int
    input_tokens: int
    output_tokens: int
    quality_score: float
    literature_count: int
    repair_cycles: int
    success_rate: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "benchmark_id": self.benchmark_id,
            "category": self.category,
            "topic": self.topic,
            "status": self.status,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_sec": self.duration_sec,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "quality_score": self.quality_score,
            "literature_count": self.literature_count,
            "repair_cycles": self.repair_cycles,
            "success_rate": self.success_rate,
            "metrics": self.metrics,
        }


@dataclass
class BenchmarkDefinition:
    """Definition of a benchmark task."""
    
    id: str
    name: str
    category: BenchmarkCategory
    topic: str
    description: str
    expected_outcomes: list[str]
    success_criteria: dict[str, Any]
    max_cost: float = 1.0
    max_duration_sec: float = 3600
    difficulty: str = "medium"  # easy, medium, hard


class BenchmarkSuite:
    """Standard benchmark suite with 12 projects."""
    
    def __init__(self) -> None:
        """Initialize benchmark suite."""
        self._benchmarks = self._create_benchmarks()
    
    def _create_benchmarks(self) -> dict[str, BenchmarkDefinition]:
        """Create 12 standard benchmarks."""
        return {
            "hypothesis-generation": BenchmarkDefinition(
                id="hypothesis-generation",
                name="Hypothesis Generation",
                category=BenchmarkCategory.HYPOTHESIS_GENERATION,
                topic="CRISPR gene editing for rare diseases",
                description="Generate 3-5 testable hypotheses for CRISPR applications",
                expected_outcomes=[
                    "3-5 distinct hypotheses",
                    "Each with clear mechanism",
                    "Testable predictions",
                ],
                success_criteria={
                    "min_hypotheses": 3,
                    "max_hypotheses": 5,
                    "min_quality_score": 7.0,
                },
                max_cost=0.50,
                max_duration_sec=600,
                difficulty="medium",
            ),
            "experiment-design": BenchmarkDefinition(
                id="experiment-design",
                name="Experiment Design",
                category=BenchmarkCategory.EXPERIMENT_DESIGN,
                topic="Machine learning for protein folding prediction",
                description="Design a complete experiment with controls and metrics",
                expected_outcomes=[
                    "Clear experimental protocol",
                    "Control groups defined",
                    "Success metrics specified",
                ],
                success_criteria={
                    "has_controls": True,
                    "has_metrics": True,
                    "min_quality_score": 7.5,
                },
                max_cost=0.75,
                max_duration_sec=900,
                difficulty="hard",
            ),
            "literature-review": BenchmarkDefinition(
                id="literature-review",
                name="Literature Review",
                category=BenchmarkCategory.LITERATURE_REVIEW,
                topic="Transformer architectures in computer vision",
                description="Comprehensive literature search and synthesis",
                expected_outcomes=[
                    "20+ relevant papers",
                    "Key findings synthesized",
                    "Research gaps identified",
                ],
                success_criteria={
                    "min_papers": 20,
                    "min_quality_score": 7.0,
                },
                max_cost=0.40,
                max_duration_sec=1200,
                difficulty="medium",
            ),
            "code-generation": BenchmarkDefinition(
                id="code-generation",
                name="Code Generation",
                category=BenchmarkCategory.CODE_GENERATION,
                topic="Implement a basic neural network from scratch",
                description="Generate working Python code with tests",
                expected_outcomes=[
                    "Working implementation",
                    "Unit tests included",
                    "Documentation provided",
                ],
                success_criteria={
                    "code_runs": True,
                    "tests_pass": True,
                    "min_coverage": 0.70,
                },
                max_cost=0.60,
                max_duration_sec=900,
                difficulty="medium",
            ),
            "paper-writing": BenchmarkDefinition(
                id="paper-writing",
                name="Paper Writing",
                category=BenchmarkCategory.PAPER_WRITING,
                topic="Survey of reinforcement learning in robotics",
                description="Write a complete survey paper section",
                expected_outcomes=[
                    "3000+ words",
                    "Proper citations",
                    "Clear structure",
                ],
                success_criteria={
                    "min_words": 3000,
                    "has_citations": True,
                    "min_quality_score": 7.5,
                },
                max_cost=0.80,
                max_duration_sec=1800,
                difficulty="hard",
            ),
            "full-pipeline-ml": BenchmarkDefinition(
                id="full-pipeline-ml",
                name="Full Pipeline - ML",
                category=BenchmarkCategory.FULL_PIPELINE,
                topic="Novel attention mechanism for time series",
                description="Complete pipeline from idea to paper",
                expected_outcomes=[
                    "Full research paper",
                    "Working experiments",
                    "Real literature",
                ],
                success_criteria={
                    "paper_complete": True,
                    "experiments_run": True,
                    "min_quality_score": 8.0,
                },
                max_cost=1.00,
                max_duration_sec=7200,
                difficulty="hard",
            ),
            "full-pipeline-bio": BenchmarkDefinition(
                id="full-pipeline-bio",
                name="Full Pipeline - Biology",
                category=BenchmarkCategory.FULL_PIPELINE,
                topic="Drug repurposing using graph neural networks",
                description="Complete pipeline for biology domain",
                expected_outcomes=[
                    "Full research paper",
                    "Domain-specific experiments",
                    "Biology literature",
                ],
                success_criteria={
                    "paper_complete": True,
                    "experiments_run": True,
                    "min_quality_score": 8.0,
                },
                max_cost=1.00,
                max_duration_sec=7200,
                difficulty="hard",
            ),
            "quick-hypothesis": BenchmarkDefinition(
                id="quick-hypothesis",
                name="Quick Hypothesis",
                category=BenchmarkCategory.HYPOTHESIS_GENERATION,
                topic="Quantum computing applications in finance",
                description="Rapid hypothesis generation",
                expected_outcomes=[
                    "2-3 hypotheses",
                    "Quick turnaround",
                ],
                success_criteria={
                    "min_hypotheses": 2,
                    "max_duration_sec": 300,
                },
                max_cost=0.20,
                max_duration_sec=300,
                difficulty="easy",
            ),
            "quick-literature": BenchmarkDefinition(
                id="quick-literature",
                name="Quick Literature",
                category=BenchmarkCategory.LITERATURE_REVIEW,
                topic="Federated learning for healthcare",
                description="Rapid literature search",
                expected_outcomes=[
                    "10+ papers",
                    "Key insights",
                ],
                success_criteria={
                    "min_papers": 10,
                },
                max_cost=0.25,
                max_duration_sec=600,
                difficulty="easy",
            ),
            "ablation-study": BenchmarkDefinition(
                id="ablation-study",
                name="Ablation Study",
                category=BenchmarkCategory.EXPERIMENT_DESIGN,
                topic="Component analysis of transformer model",
                description="Design and run ablation study",
                expected_outcomes=[
                    "Multiple variants tested",
                    "Clear comparisons",
                    "Statistical analysis",
                ],
                success_criteria={
                    "min_variants": 3,
                    "has_statistics": True,
                },
                max_cost=0.90,
                max_duration_sec=3600,
                difficulty="hard",
            ),
            "meta-analysis": BenchmarkDefinition(
                id="meta-analysis",
                name="Meta-Analysis",
                category=BenchmarkCategory.LITERATURE_REVIEW,
                topic="Effectiveness of different RL algorithms",
                description="Meta-analysis of existing studies",
                expected_outcomes=[
                    "25+ studies analyzed",
                    "Effect sizes computed",
                    "Forest plots",
                ],
                success_criteria={
                    "min_studies": 25,
                    "has_effect_sizes": True,
                },
                max_cost=0.70,
                max_duration_sec=2400,
                difficulty="hard",
            ),
            "proof-of-concept": BenchmarkDefinition(
                id="proof-of-concept",
                name="Proof of Concept",
                category=BenchmarkCategory.CODE_GENERATION,
                topic="Basic blockchain implementation",
                description="Minimal viable implementation",
                expected_outcomes=[
                    "Working prototype",
                    "Core features",
                ],
                success_criteria={
                    "code_runs": True,
                    "core_features": True,
                },
                max_cost=0.40,
                max_duration_sec=1200,
                difficulty="easy",
            ),
        }
    
    def get_benchmark(self, benchmark_id: str) -> BenchmarkDefinition | None:
        """Get benchmark by ID."""
        return self._benchmarks.get(benchmark_id)
    
    def list_benchmarks(
        self,
        category: BenchmarkCategory | None = None,
        difficulty: str | None = None,
    ) -> list[BenchmarkDefinition]:
        """List benchmarks with optional filters."""
        benchmarks = list(self._benchmarks.values())
        
        if category:
            benchmarks = [b for b in benchmarks if b.category == category]
        
        if difficulty:
            benchmarks = [b for b in benchmarks if b.difficulty == difficulty]
        
        return benchmarks
    
    @property
    def all_benchmarks(self) -> list[BenchmarkDefinition]:
        """Get all benchmarks."""
        return list(self._benchmarks.values())
