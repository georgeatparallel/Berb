"""Experiment Integration (Upgrades 1, 5, 7, 10).

Integrates experiment optimizations with pipeline stages:
- Stage 9: Physics Code Guards (Upgrade 5)
- Stage 10: ReAct Agents (Upgrade 10)
- Stage 12: Async Pool (Upgrade 1)
- Stage 13: Evolutionary Search (Upgrade 7)

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from berb.experiment.async_pool import AsyncExperimentPool, PoolConfig
from berb.experiment.evolutionary_search import (
    EvolutionaryExperimentSearch,
    EvolutionResult,
)
from berb.experiment.physics_guards import (
    PhysicsCodeGuard,
    CodeQualityIssue,
)
from berb.experiment.react_agent import ExperimentReActAgent
from berb.reasoning.scientific import ExperimentDesign

logger = logging.getLogger(__name__)


@dataclass
class ExperimentExecutionResult:
    """Result from experiment execution.
    
    Attributes:
        results: List of experiment results
        best_result: Best experiment result
        quality_issues: List of code quality issues
        used_evolution: Whether evolutionary search was used
    """
    results: list[Any]
    best_result: Any | None
    quality_issues: list[CodeQualityIssue]
    used_evolution: bool


class ExperimentPoolIntegration:
    """Integrates experiment optimizations with pipeline.
    
    Usage in pipeline:
        integration = ExperimentPoolIntegration(workspace)
        result = await integration.execute_experiment(design)
    """
    
    def __init__(
        self,
        workspace: Path,
        max_workers: int = 4,
        isolation: str = "docker",
        gpu_enabled: bool = True,
        use_evolution: bool = True,
        use_react: bool = True,
        use_physics_guards: bool = True,
    ):
        """Initialize experiment pool integration.
        
        Args:
            workspace: Workspace directory
            max_workers: Maximum parallel workers
            isolation: Isolation mode
            gpu_enabled: GPU access
            use_evolution: Use evolutionary search
            use_react: Use ReAct agents
            use_physics_guards: Use physics code guards
        """
        self.workspace = workspace
        self.max_workers = max_workers
        self.isolation = isolation
        self.gpu_enabled = gpu_enabled
        self.use_evolution = use_evolution
        self.use_react = use_react
        self.use_physics_guards = use_physics_guards
        
        self.pool = AsyncExperimentPool(PoolConfig(
            max_workers=max_workers,
            isolation=isolation,
            gpu_enabled=gpu_enabled,
        ))
        
        self.evolutionary_search = EvolutionaryExperimentSearch() if use_evolution else None
        self.react_agent = ExperimentReActAgent() if use_react else None
        self.physics_guard = PhysicsCodeGuard() if use_physics_guards else None
        
        logger.info(
            f"Initialized ExperimentPoolIntegration: "
            f"workers={max_workers}, evolution={use_evolution}, "
            f"react={use_react}, guards={use_physics_guards}"
        )
    
    async def validate_experiment_code(
        self,
        code: str,
        domain: str = "physics",
    ) -> list[CodeQualityIssue]:
        """Stage 9: Validate experiment code quality.
        
        Args:
            code: Experiment code
            domain: Domain context
            
        Returns:
            List of quality issues
        """
        if not self.physics_guard:
            return []
        
        issues = await self.physics_guard.check_experiment_code(code, domain)
        
        if issues:
            logger.warning(f"Found {len(issues)} code quality issues")
        
        return issues
    
    async def execute_experiment_react(
        self,
        design: ExperimentDesign,
    ) -> Any:
        """Stage 10: Execute experiment with ReAct agent.
        
        Args:
            design: Experiment design
            
        Returns:
            Experiment result
        """
        if not self.react_agent:
            raise ValueError("ReAct agent not enabled")
        
        logger.info(f"Executing experiment with ReAct: {design.id}")
        
        result = await self.react_agent.run_experiment(design)
        
        logger.info(f"ReAct experiment complete: {design.id}")
        
        return result
    
    async def execute_experiment_parallel(
        self,
        designs: list[ExperimentDesign],
    ) -> list[Any]:
        """Stage 12: Execute experiments in parallel.
        
        Args:
            designs: List of experiment designs
            
        Returns:
            List of experiment results
        """
        logger.info(
            f"Executing {len(designs)} experiments in parallel "
            f"with {self.max_workers} workers"
        )
        
        results = await self.pool.execute_parallel(designs)
        
        logger.info(f"Parallel execution complete: {len(results)} results")
        
        return results
    
    async def execute_experiment_evolutionary(
        self,
        base_design: ExperimentDesign,
        population_size: int = 8,
        max_generations: int = 4,
    ) -> EvolutionResult:
        """Stage 13: Execute with evolutionary search.
        
        Args:
            base_design: Base experiment design
            population_size: Population size
            max_generations: Maximum generations
            
        Returns:
            Evolution result
        """
        if not self.evolutionary_search:
            raise ValueError("Evolutionary search not enabled")
        
        logger.info(
            f"Running evolutionary search: pop={population_size}, "
            f"gen={max_generations}"
        )
        
        result = await self.evolutionary_search.search(
            base_experiment=base_design,
            population_size=population_size,
            max_generations=max_generations,
        )
        
        logger.info(
            f"Evolution complete: {result.generations} generations, "
            f"best fitness={result.best_variant.fitness:.2f}"
        )
        
        return result


async def execute_experiment_parallel(
    designs: list[ExperimentDesign],
    workspace: Path,
    max_workers: int = 4,
    isolation: str = "docker",
    gpu_enabled: bool = True,
) -> list[Any]:
    """Stage 12 integration: Execute experiments in parallel.
    
    Args:
        designs: Experiment designs
        workspace: Workspace directory
        max_workers: Maximum workers
        isolation: Isolation mode
        gpu_enabled: GPU access
        
    Returns:
        Experiment results
    """
    integration = ExperimentPoolIntegration(
        workspace=workspace,
        max_workers=max_workers,
        isolation=isolation,
        gpu_enabled=gpu_enabled,
    )
    
    return await integration.execute_experiment_parallel(designs)
