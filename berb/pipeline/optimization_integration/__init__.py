"""Pipeline Integration for Optimization Upgrades.

This module integrates all 12 optimization upgrades into the 23-stage pipeline:

Stage Integration Map:
- Stages 4-6: FS-Based Literature Processor (Upgrade 4)
- Stage 8: Verifiable Math (Upgrade 6)
- Stages 9: Physics Code Guards (Upgrade 5)
- Stages 10-13: Async Pool + ReAct + Evolutionary (Upgrades 1, 7, 10)
- Stage 15: HCE (Upgrade 2)
- Stage 17: Parallel Writing (Upgrade 9)
- Stages 19-20: HCE + Critique (Upgrade 2)
- Stage 21: Humanitarian Impact (Upgrade 8)
- Post-Pipeline: Benchmark Framework (Upgrade 12)

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .benchmark_integration import (
    BenchmarkIntegration,
    BenchmarkReport,
    run_benchmark_evaluation,
)
from .experiment_integration import (
    ExperimentExecutionResult,
    ExperimentPoolIntegration,
    execute_experiment_parallel,
)
from .literature_integration import (
    LiteratureFSIntegration,
    organize_literature_stage,
)
from .validation_integration import (
    HCEStageResult,
    ValidationIntegration,
    evaluate_with_hce,
)
from .writing_integration import (
    WritingIntegration,
    write_paper_parallel,
)

__all__ = [
    # Literature Integration (Upgrade 4)
    "LiteratureFSIntegration",
    "organize_literature_stage",
    # Experiment Integration (Upgrades 1, 5, 7, 10)
    "ExperimentPoolIntegration",
    "execute_experiment_parallel",
    "ExperimentExecutionResult",
    # Writing Integration (Upgrade 9)
    "WritingIntegration",
    "write_paper_parallel",
    # Validation Integration (Upgrade 2)
    "ValidationIntegration",
    "evaluate_with_hce",
    "HCEStageResult",
    # Benchmark Integration (Upgrade 12)
    "BenchmarkIntegration",
    "run_benchmark_evaluation",
    "BenchmarkReport",
]
