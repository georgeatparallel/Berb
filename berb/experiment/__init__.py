"""Experiment execution module for Berb.

Includes sandbox execution, Docker support, compute guards,
experiment monitoring, async parallel execution, physics
code quality guards, evolutionary search, and ReAct agents.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .async_pool import (
    AsyncExperimentPool,
    PoolConfig,
    WorkerStatus,
    create_pool,
)
from .compute_guard import (
    ComputeGuard,
    ComputeGuardConfig,
    ExperimentCostEstimate,
    ExperimentMonitor,
    ExperimentProgress,
    ExperimentResults,
    ExperimentStatus,
    check_experiment_affordability,
)
from .evolutionary_search import (
    DesignProposalEvolver,
    EvolutionaryExperimentSearch,  # deprecated alias
    EvolutionResult,
    ExperimentVariant,
)
from .isolation import (
    DockerIsolation,
    DockerIsolationConfig,
    IsolationContext,
    IsolationStrategy,
    SandboxIsolation,
    SandboxIsolationConfig,
    WorktreeIsolation,
    WorktreeIsolationConfig,
    create_isolation,
)
from .physics_guards import (
    CodeQualityIssue,
    PhysicsCodeGuard,
)
from .react_agent import (
    ExperimentReActAgent,
    ReActStep,
    ReActTrajectory,
)
from .worker import (
    ExperimentWorkerImpl,
    WorkerConfig,
)

__all__ = [
    # Async Pool
    "AsyncExperimentPool",
    "PoolConfig",
    "WorkerStatus",
    "create_pool",
    # Compute Guard
    "ComputeGuard",
    "ComputeGuardConfig",
    "ExperimentMonitor",
    "ExperimentCostEstimate",
    "ExperimentProgress",
    "ExperimentResults",
    "ExperimentStatus",
    "check_experiment_affordability",
    # Evolutionary Search (Design Proposal Evolver)
    "DesignProposalEvolver",
    "EvolutionaryExperimentSearch",  # deprecated alias
    "ExperimentVariant",
    "EvolutionResult",
    # Isolation
    "IsolationContext",
    "IsolationStrategy",
    "DockerIsolation",
    "DockerIsolationConfig",
    "WorktreeIsolation",
    "WorktreeIsolationConfig",
    "SandboxIsolation",
    "SandboxIsolationConfig",
    "create_isolation",
    # Physics Guards
    "PhysicsCodeGuard",
    "CodeQualityIssue",
    # ReAct Agent
    "ExperimentReActAgent",
    "ReActTrajectory",
    "ReActStep",
    # Worker
    "ExperimentWorkerImpl",
    "WorkerConfig",
]
