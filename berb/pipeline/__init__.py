"""Pipeline core — 23-stage research pipeline.

Enhanced with optimization upgrades (v3.0).

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .hallucination_detector import (
    CitationVerification,
    ClaimVerification,
    HallucinationDetector,
    HallucinationReport,
    verify_paper_for_hallucinations,
)
from .optimization_integration import (
    # Benchmark Integration (Upgrade 12)
    BenchmarkIntegration,
    BenchmarkReport,
    ExperimentExecutionResult,
    # Experiment Integration (Upgrades 1, 5, 7, 10)
    ExperimentPoolIntegration,
    HCEStageResult,
    # Literature Integration (Upgrade 4)
    LiteratureFSIntegration,
    # Validation Integration (Upgrade 2)
    ValidationIntegration,
    # Writing Integration (Upgrade 9)
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
