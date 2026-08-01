"""Pipeline core — 23-stage research pipeline.

Enhanced with optimization upgrades (v3.0).

Re-exports are lazy (PEP 562): importing a pipeline submodule such as
``berb.pipeline.stages`` no longer drags in the benchmark, literature and LLM
stacks. Names below resolve on first attribute access.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from berb._lazy import lazy_exports

_EXPORTS = {
    # Hallucination detection
    "CitationVerification": "hallucination_detector",
    "ClaimVerification": "hallucination_detector",
    "HallucinationDetector": "hallucination_detector",
    "HallucinationReport": "hallucination_detector",
    "verify_paper_for_hallucinations": "hallucination_detector",
    # Optimization Integration (v3.0)
    "BenchmarkIntegration": "optimization_integration",
    "BenchmarkReport": "optimization_integration",
    "ExperimentExecutionResult": "optimization_integration",
    "ExperimentPoolIntegration": "optimization_integration",
    "HCEStageResult": "optimization_integration",
    "LiteratureFSIntegration": "optimization_integration",
    "ValidationIntegration": "optimization_integration",
    "WritingIntegration": "optimization_integration",
    "evaluate_with_hce": "optimization_integration",
    "execute_experiment_parallel": "optimization_integration",
    "organize_literature_stage": "optimization_integration",
    "run_benchmark_evaluation": "optimization_integration",
    "write_paper_parallel": "optimization_integration",
}

__getattr__, __dir__ = lazy_exports(__name__, _EXPORTS, globals())

if TYPE_CHECKING:
    from .hallucination_detector import (
        CitationVerification,
        ClaimVerification,
        HallucinationDetector,
        HallucinationReport,
        verify_paper_for_hallucinations,
    )
    from .optimization_integration import (
        BenchmarkIntegration,
        BenchmarkReport,
        ExperimentExecutionResult,
        ExperimentPoolIntegration,
        HCEStageResult,
        LiteratureFSIntegration,
        ValidationIntegration,
        WritingIntegration,
        evaluate_with_hce,
        execute_experiment_parallel,
        organize_literature_stage,
        run_benchmark_evaluation,
        write_paper_parallel,
    )

__all__ = [
    # Hallucination detection
    "HallucinationDetector",
    "HallucinationReport",
    "CitationVerification",
    "ClaimVerification",
    "verify_paper_for_hallucinations",
    # Optimization Integration (NEW - v3.0)
    # Literature
    "LiteratureFSIntegration",
    "organize_literature_stage",
    # Experiment
    "ExperimentPoolIntegration",
    "execute_experiment_parallel",
    "ExperimentExecutionResult",
    # Writing
    "WritingIntegration",
    "write_paper_parallel",
    # Validation
    "ValidationIntegration",
    "evaluate_with_hce",
    "HCEStageResult",
    # Benchmark
    "BenchmarkIntegration",
    "run_benchmark_evaluation",
    "BenchmarkReport",
]
