"""Benchmarks module for Berb.

Automated benchmarking for quality validation including
PRBench, DRACO, and HorizonMath evaluation frameworks,
plus performance benchmarking for optimization upgrades.

Re-exports are lazy (PEP 562): the performance suite imports the whole
literature stack, so eager re-export made every benchmark consumer pay for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from berb._lazy import lazy_exports

_EXPORTS = {
    # Evaluation Framework
    "BerbBenchmarkFramework": "evaluation_framework",
    "DRACOScore": "evaluation_framework",
    "MathScore": "evaluation_framework",
    "PRBenchScore": "evaluation_framework",
    "BenchmarkResult": "evaluation_framework",
    # Performance Suite
    "OptimizationBenchmarkSuite": "performance_suite",
    "BenchmarkMetric": "performance_suite",
    "BenchmarkReport": "performance_suite",
    "run_benchmarks": "performance_suite",
    # Suite
    "BerbBenchmarkSuite": "suite",
    "ReviewScore": "suite",
    "ReproductionResult": "suite",
    "QualityReport": "suite",
    "BenchmarkSet": "suite",
    "BENCHMARK_SETS": "suite",
    "run_benchmark": "suite",
}

__getattr__, __dir__ = lazy_exports(__name__, _EXPORTS, globals())

if TYPE_CHECKING:
    from .evaluation_framework import (
        BenchmarkResult,
        BerbBenchmarkFramework,
        DRACOScore,
        MathScore,
        PRBenchScore,
    )
    from .performance_suite import (
        BenchmarkMetric,
        BenchmarkReport,
        OptimizationBenchmarkSuite,
        run_benchmarks,
    )
    from .suite import (
        BENCHMARK_SETS,
        BenchmarkSet,
        BerbBenchmarkSuite,
        QualityReport,
        ReproductionResult,
        ReviewScore,
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
