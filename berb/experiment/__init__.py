"""Experiment execution module for Berb.

Includes sandbox execution, Docker support, compute guards,
experiment monitoring, async parallel execution, physics
code quality guards, evolutionary search, and ReAct agents.

Re-exports are lazy (PEP 562), so importing a light submodule such as
``berb.experiment.metrics`` no longer drags in the compute guard, Docker
isolation and ReAct agent stacks.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from berb._lazy import lazy_exports

_EXPORTS = {
    # Async Pool
    "AsyncExperimentPool": "async_pool",
    "PoolConfig": "async_pool",
    "WorkerStatus": "async_pool",
    "create_pool": "async_pool",
    # Compute Guard
    "ComputeGuard": "compute_guard",
    "ComputeGuardConfig": "compute_guard",
    "ExperimentMonitor": "compute_guard",
    "ExperimentCostEstimate": "compute_guard",
    "ExperimentProgress": "compute_guard",
    "ExperimentResults": "compute_guard",
    "ExperimentStatus": "compute_guard",
    "check_experiment_affordability": "compute_guard",
    # Evolutionary Search (Design Proposal Evolver)
    "DesignProposalEvolver": "evolutionary_search",
    "EvolutionaryExperimentSearch": "evolutionary_search",  # deprecated alias
    "ExperimentVariant": "evolutionary_search",
    "EvolutionResult": "evolutionary_search",
    # Isolation
    "IsolationContext": "isolation",
    "IsolationStrategy": "isolation",
    "DockerIsolation": "isolation",
    "DockerIsolationConfig": "isolation",
    "WorktreeIsolation": "isolation",
    "WorktreeIsolationConfig": "isolation",
    "SandboxIsolation": "isolation",
    "SandboxIsolationConfig": "isolation",
    "create_isolation": "isolation",
    # Physics Guards
    "PhysicsCodeGuard": "physics_guards",
    "CodeQualityIssue": "physics_guards",
    # ReAct Agent
    "ExperimentReActAgent": "react_agent",
    "ReActTrajectory": "react_agent",
    "ReActStep": "react_agent",
    # Worker
    "ExperimentWorkerImpl": "worker",
    "WorkerConfig": "worker",
}

__getattr__, __dir__ = lazy_exports(__name__, _EXPORTS, globals())

if TYPE_CHECKING:
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
