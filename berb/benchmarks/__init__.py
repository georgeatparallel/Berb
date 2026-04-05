"""Benchmarks module for Berb.

Automated benchmarking for quality validation including
PRBench, DRACO, and HorizonMath evaluation frameworks,
plus performance benchmarking for optimization upgrades.
"""

from .evaluation_framework import (
    BerbBenchmarkFramework,
    DRACOScore,
    MathScore,
    PRBenchScore,
    BenchmarkResult,
)
from .performance_suite import (
    OptimizationBenchmarkSuite,
    BenchmarkMetric,
    BenchmarkReport,
    run_benchmarks,
)
from .suite import (
    BerbBenchmarkSuite,
    ReviewScore,
    ReproductionResult,
    QualityReport,
    BenchmarkSet,
    BENCHMARK_SETS,
    run_benchmark,
)

__all__ = [
    # Evaluation Framework
    "BerbBenchmarkFramework",
    "DRACOScore",
    "MathScore",
    "PRBenchScore",
    "BenchmarkResult",
    # Performance Suite (NEW)
    "OptimizationBenchmarkSuite",
    "BenchmarkMetric",
    "BenchmarkReport",
    "run_benchmarks",
    # Suite
    "BerbBenchmarkSuite",
    "ReviewScore",
    "ReproductionResult",
    "QualityReport",
    "BenchmarkSet",
    "BENCHMARK_SETS",
    "run_benchmark",
]
