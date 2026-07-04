"""Pipeline core — 23-stage research pipeline.

Includes improvement loop for iterative paper refinement
with Bayesian decision making and Iterative reasoning.
Enhanced with optimization upgrades (v3.0).

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .bayesian_improvement_loop import (
    BayesianImprovementConfig,
    BayesianImprovementLoop,
    IterativeFixPlanner,
    QualityBelief,
)
from .hallucination_detector import (
    CitationVerification,
    ClaimVerification,
    HallucinationDetector,
    HallucinationReport,
    verify_paper_for_hallucinations,
)
from .improvement_loop import (
    AutonomousImprovementLoop,
    ClaimRecord,
    ClaimTracker,
    ClaimVerdict,
    ClassifiedWeakness,
    ComputeGuard,
    FixType,
    ImprovementLoopConfig,
    ImprovementResult,
    RoundResult,
    ScoreProgression,
    improve_paper,
)
from .optimization_integration import (
    # Benchmark Integration (Upgrade 12)
    BenchmarkIntegration,
    BenchmarkReport,
    # Council Integration (Upgrade 3)
    CouncilIntegration,
    CouncilStageResult,
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
    run_council_stage,
    write_paper_parallel,
)

__all__ = [
    # Hallucination detection
    "HallucinationDetector",
    "HallucinationReport",
    "CitationVerification",
    "ClaimVerification",
    "verify_paper_for_hallucinations",
    # Improvement loop
    "AutonomousImprovementLoop",
    "ImprovementLoopConfig",
    "ImprovementResult",
    "ScoreProgression",
    "RoundResult",
    "ClaimTracker",
    "ClaimRecord",
    "ClaimVerdict",
    "FixType",
    "ClassifiedWeakness",
    "ComputeGuard",
    "improve_paper",
    # Bayesian improvement
    "BayesianImprovementLoop",
    "BayesianImprovementConfig",
    "QualityBelief",
    "IterativeFixPlanner",
    # Optimization Integration (NEW - v3.0)
    # Literature
    "LiteratureFSIntegration",
    "organize_literature_stage",
    # Council
    "CouncilIntegration",
    "run_council_stage",
    "CouncilStageResult",
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
