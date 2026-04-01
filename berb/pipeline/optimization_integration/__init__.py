"""Pipeline Integration for Optimization Upgrades.

This module integrates all 12 optimization upgrades into the 23-stage pipeline:

Stage Integration Map:
- Stages 4-6: FS-Based Literature Processor (Upgrade 4)
- Stage 7: Council Mode (Upgrade 3)
- Stage 8: Council Mode + Verifiable Math (Upgrades 3, 6)
- Stage 9: Physics Code Guards (Upgrade 5)
- Stages 10-13: Async Pool + ReAct + Evolutionary (Upgrades 1, 7, 10)
- Stage 15: Council + HCE (Upgrades 2, 3)
- Stage 17: Parallel Writing (Upgrade 9)
- Stages 19-20: HCE + Critique (Upgrade 2)
- Stage 21: Humanitarian Impact (Upgrade 8)
- Post-Pipeline: Benchmark Framework (Upgrade 12)

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .literature_integration import (
    LiteratureFSIntegration,
    organize_literature_stage,
)
from .council_integration import (
    CouncilIntegration,
    run_council_stage,
)
from .experiment_integration import (
    ExperimentPoolIntegration,
    execute_experiment_parallel,
)
from .writing_integration import (
    WritingIntegration,
    write_paper_parallel,
)
from .validation_integration import (
    ValidationIntegration,
    evaluate_with_hce,
)
from .benchmark_integration import (
    BenchmarkIntegration,
    run_benchmark_evaluation,
)

__all__ = [
    # Literature Integration (Upgrade 4)
    "LiteratureFSIntegration",
    "organize_literature_stage",
    # Council Integration (Upgrade 3)
    "CouncilIntegration",
    "run_council_stage",
    # Experiment Integration (Upgrades 1, 5, 7, 10)
    "ExperimentPoolIntegration",
    "execute_experiment_parallel",
    # Writing Integration (Upgrade 9)
    "WritingIntegration",
    "write_paper_parallel",
    # Validation Integration (Upgrade 2)
    "ValidationIntegration",
    "evaluate_with_hce",
    # Benchmark Integration (Upgrade 12)
    "BenchmarkIntegration",
    "run_benchmark_evaluation",
]
