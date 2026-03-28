"""Experiment Progress Manager for Berb.

Based on AI Scientist (Nature 2026) - Section 3.3

Implements structured 4-stage experiment progression:
1. Investigation (baseline implementation)
2. Tuning (hyperparameter optimization)
3. Agenda Execution (planned ablation studies)
4. Ablation (component analysis)

Each stage has entry/exit criteria, max iterations, and go/no-go decisions.

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.experiment.progress import ExperimentProgressManager
    
    manager = ExperimentProgressManager()
    result = await manager.run_experiment(experiment_config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ExperimentStage(str, Enum):
    """Four stages of experiment progression."""
    INVESTIGATION = "investigation"
    TUNING = "tuning"
    AGENDA_EXECUTION = "agenda_execution"
    ABLATION = "ablation"


class StageStatus(str, Enum):
    """Status of experiment stage."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageConfig:
    """Configuration for a single experiment stage."""
    
    stage: ExperimentStage
    max_iterations: int = 3
    timeout_sec: int = 1800  # 30 min per iteration
    min_success_rate: float = 0.5  # Minimum conditions to pass
    required_metrics: list[str] = field(default_factory=list)
    entry_criteria: list[str] = field(default_factory=list)
    exit_criteria: list[str] = field(default_factory=list)


@dataclass
class StageResult:
    """Results from a single stage."""
    
    stage: ExperimentStage
    status: StageStatus
    iterations_completed: int
    metrics: dict[str, float]
    success_rate: float
    error_message: str | None = None
    duration_sec: float = 0.0
    artifacts: list[str] = field(default_factory=list)


@dataclass
class ExperimentProgressConfig:
    """Configuration for experiment progression."""
    
    stages: list[StageConfig] = field(default_factory=lambda: [
        StageConfig(
            stage=ExperimentStage.INVESTIGATION,
            max_iterations=2,
            timeout_sec=1200,
            min_success_rate=0.5,
            required_metrics=["baseline_score"],
            entry_criteria=["experiment_design_approved"],
            exit_criteria=["baseline_implemented", "metrics_collected"],
        ),
        StageConfig(
            stage=ExperimentStage.TUNING,
            max_iterations=3,
            timeout_sec=1800,
            min_success_rate=0.6,
            required_metrics=["best_score", "improvement_over_baseline"],
            entry_criteria=["baseline_established"],
            exit_criteria=["hyperparameters_optimized", "improvement_confirmed"],
        ),
        StageConfig(
            stage=ExperimentStage.AGENDA_EXECUTION,
            max_iterations=2,
            timeout_sec=2400,
            min_success_rate=0.7,
            required_metrics=["all_conditions_tested"],
            entry_criteria=["tuning_complete"],
            exit_criteria=["agenda_completed", "results_significant"],
        ),
        StageConfig(
            stage=ExperimentStage.ABLATION,
            max_iterations=2,
            timeout_sec=2400,
            min_success_rate=0.8,
            required_metrics=["component_contributions"],
            entry_criteria=["main_results_established"],
            exit_criteria=["ablation_completed", "insights_documented"],
        ),
    ])
    max_total_cost_usd: float = 2.0
    early_stopping_enabled: bool = True
    early_stopping_threshold: float = 0.3  # Stop if improvement < 30%


class ExperimentProgressManager:
    """Manage structured 4-stage experiment progression."""
    
    def __init__(
        self,
        config: ExperimentProgressConfig | None = None,
        llm_client: Any | None = None,
    ) -> None:
        """Initialize progress manager.
        
        Args:
            config: Progress configuration
            llm_client: LLM client for decision-making
        """
        self._config = config or ExperimentProgressConfig()
        self._llm_client = llm_client
        self._stage_results: list[StageResult] = []
        self._total_cost: float = 0.0
        self._start_time: datetime | None = None
    
    async def run_experiment(
        self,
        experiment_config: dict[str, Any],
    ) -> ExperimentReport:
        """Run experiment through all stages.
        
        Args:
            experiment_config: Experiment configuration
            
        Returns:
            Complete experiment report
        """
        self._start_time = datetime.now()
        logger.info(f"Starting 4-stage experiment progression")
        
        for stage_config in self._config.stages:
            # Check if we should skip this stage
            if not self._should_run_stage(stage_config):
                logger.info(f"Skipping stage {stage_config.stage.value}")
                self._stage_results.append(StageResult(
                    stage=stage_config.stage,
                    status=StageStatus.SKIPPED,
                    iterations_completed=0,
                    metrics={},
                    success_rate=0.0,
                ))
                continue
            
            # Check budget
            if self._total_cost >= self._config.max_total_cost_usd:
                logger.warning("Budget exceeded, stopping experiment progression")
                break
            
            # Run stage
            logger.info(f"Running stage: {stage_config.stage.value}")
            result = await self._run_stage(stage_config, experiment_config)
            self._stage_results.append(result)
            
            # Check if stage passed
            if result.status == StageStatus.FAILED:
                logger.error(f"Stage {stage_config.stage.value} failed: {result.error_message}")
                
                if self._config.early_stopping_enabled:
                    logger.info("Early stopping enabled, halting experiment")
                    break
            
            # Check for diminishing returns
            if self._config.early_stopping_enabled:
                if not self._check_improvement_threshold():
                    logger.warning("Improvement below threshold, considering early stop")
        
        # Generate final report
        return self._generate_report(experiment_config)
    
    def _should_run_stage(self, stage_config: StageConfig) -> bool:
        """Check if stage should run based on entry criteria."""
        if not stage_config.entry_criteria:
            return True
        
        # Check if previous stages completed required criteria
        for criteria in stage_config.entry_criteria:
            if not self._check_criteria_met(criteria):
                logger.debug(f"Entry criteria not met: {criteria}")
                return False
        
        return True
    
    def _check_criteria_met(self, criteria: str) -> bool:
        """Check if a specific criterion is met."""
        # Map criteria to checks
        criteria_checks = {
            "experiment_design_approved": lambda: self._has_completed_stage(ExperimentStage.INVESTIGATION),
            "baseline_established": lambda: self._has_metric("baseline_score"),
            "tuning_complete": lambda: self._has_completed_stage(ExperimentStage.TUNING),
            "main_results_established": lambda: self._has_completed_stage(ExperimentStage.AGENDA_EXECUTION),
        }
        
        check = criteria_checks.get(criteria)
        if check:
            return check()
        
        return False
    
    def _has_completed_stage(self, stage: ExperimentStage) -> bool:
        """Check if a stage has been completed successfully."""
        for result in self._stage_results:
            if result.stage == stage and result.status == StageStatus.COMPLETED:
                return True
        return False
    
    def _has_metric(self, metric_name: str) -> bool:
        """Check if a metric has been collected."""
        for result in self._stage_results:
            if metric_name in result.metrics:
                return True
        return False
    
    async def _run_stage(
        self,
        stage_config: StageConfig,
        experiment_config: dict[str, Any],
    ) -> StageResult:
        """Run a single experiment stage."""
        stage_result = StageResult(
            stage=stage_config.stage,
            status=StageStatus.IN_PROGRESS,
            iterations_completed=0,
            metrics={},
            success_rate=0.0,
        )
        
        stage_start = datetime.now()
        
        for iteration in range(stage_config.max_iterations):
            logger.info(f"Stage {stage_config.stage.value}, iteration {iteration + 1}")
            
            try:
                # Run iteration based on stage type
                iteration_result = await self._run_stage_iteration(
                    stage_config.stage,
                    experiment_config,
                    iteration,
                )
                
                stage_result.iterations_completed = iteration + 1
                stage_result.metrics.update(iteration_result.get("metrics", {}))
                
                # Check if iteration succeeded
                if iteration_result.get("success", False):
                    stage_result.success_rate = (
                        (stage_result.iterations_completed * 1.0) /
                        (iteration + 1)
                    )
                    
                    # Check exit criteria
                    if self._check_exit_criteria(stage_config):
                        stage_result.status = StageStatus.COMPLETED
                        break
                else:
                    stage_result.success_rate = (
                        (stage_result.iterations_completed - 1) * 1.0 /
                        (iteration + 1)
                    )
                
            except Exception as e:
                logger.error(f"Iteration failed: {e}")
                stage_result.error_message = str(e)
                
                if iteration >= stage_config.max_iterations - 1:
                    stage_result.status = StageStatus.FAILED
        
        # Final status if not set
        if stage_result.status == StageStatus.IN_PROGRESS:
            if stage_result.success_rate >= stage_config.min_success_rate:
                stage_result.status = StageStatus.COMPLETED
            else:
                stage_result.status = StageStatus.FAILED
        
        stage_result.duration_sec = (datetime.now() - stage_start).total_seconds()
        
        return stage_result
    
    async def _run_stage_iteration(
        self,
        stage: ExperimentStage,
        experiment_config: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        """Run single iteration of a stage."""
        # Placeholder - integrate with actual experiment execution
        # In production, this would call the experiment runner
        
        import random
        
        stage_handlers = {
            ExperimentStage.INVESTIGATION: self._investigation_iteration,
            ExperimentStage.TUNING: self._tuning_iteration,
            ExperimentStage.AGENDA_EXECUTION: self._agenda_iteration,
            ExperimentStage.ABLATION: self._ablation_iteration,
        }
        
        handler = stage_handlers.get(stage)
        if handler:
            return await handler(experiment_config, iteration)
        
        # Default: simulate success with random metrics
        return {
            "success": random.random() > 0.3,
            "metrics": {
                f"{stage.value}_score": random.uniform(0.5, 0.9),
            },
        }
    
    async def _investigation_iteration(
        self,
        experiment_config: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        """Investigation stage: implement and run baseline."""
        # Placeholder for actual implementation
        return {
            "success": True,
            "metrics": {
                "baseline_score": 0.65,
                "baseline_std": 0.05,
            },
            "artifacts": ["baseline_results.json"],
        }
    
    async def _tuning_iteration(
        self,
        experiment_config: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        """Tuning stage: hyperparameter optimization."""
        # Placeholder
        return {
            "success": True,
            "metrics": {
                "best_score": 0.72 + (iteration * 0.03),
                "improvement_over_baseline": 0.07 + (iteration * 0.03),
                "best_hyperparameters": {"lr": 0.001, "batch_size": 32},
            },
        }
    
    async def _agenda_iteration(
        self,
        experiment_config: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        """Agenda execution: run planned experiments."""
        # Placeholder
        return {
            "success": True,
            "metrics": {
                "all_conditions_tested": 1.0,
                "statistical_significance": 0.95,
            },
        }
    
    async def _ablation_iteration(
        self,
        experiment_config: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        """Ablation stage: component analysis."""
        # Placeholder
        return {
            "success": True,
            "metrics": {
                "component_contributions": {
                    "component_a": 0.15,
                    "component_b": 0.10,
                    "component_c": 0.05,
                },
                "full_model_score": 0.85,
            },
        }
    
    def _check_exit_criteria(self, stage_config: StageConfig) -> bool:
        """Check if all exit criteria are met."""
        for criteria in stage_config.exit_criteria:
            if not self._check_criteria_met(criteria):
                return False
        return True
    
    def _check_improvement_threshold(self) -> bool:
        """Check if improvement meets early stopping threshold."""
        if len(self._stage_results) < 2:
            return True
        
        # Compare last two completed stages
        completed = [r for r in self._stage_results if r.status == StageStatus.COMPLETED]
        if len(completed) < 2:
            return True
        
        # Check if latest stage showed sufficient improvement
        prev_metrics = completed[-2].metrics
        curr_metrics = completed[-1].metrics
        
        # Find common metrics to compare
        common_metrics = set(prev_metrics.keys()) & set(curr_metrics.keys())
        if not common_metrics:
            return True
        
        avg_improvement = sum(
            (curr_metrics[m] - prev_metrics[m]) / max(prev_metrics[m], 0.01)
            for m in common_metrics
        ) / len(common_metrics)
        
        return avg_improvement >= self._config.early_stopping_threshold
    
    def _generate_report(self, experiment_config: dict[str, Any]) -> ExperimentReport:
        """Generate final experiment report."""
        completed_stages = [
            r for r in self._stage_results
            if r.status == StageStatus.COMPLETED
        ]
        
        # Aggregate metrics from all stages
        all_metrics: dict[str, list[float]] = {}
        for result in self._stage_results:
            for key, value in result.metrics.items():
                if isinstance(value, (int, float)):
                    if key not in all_metrics:
                        all_metrics[key] = []
                    all_metrics[key].append(value)
        
        # Calculate final metrics (average across stages)
        final_metrics = {
            key: sum(values) / len(values)
            for key, values in all_metrics.items()
        }
        
        return ExperimentReport(
            experiment_id=str(datetime.now().timestamp()),
            config=experiment_config,
            stages_completed=len(completed_stages),
            total_stages=len(self._config.stages),
            stage_results=self._stage_results,
            final_metrics=final_metrics,
            total_cost=self._total_cost,
            total_duration_sec=sum(r.duration_sec for r in self._stage_results),
            success=len(completed_stages) == len(self._config.stages),
            timestamp=datetime.now(),
        )
    
    def get_progress_summary(self) -> dict[str, Any]:
        """Get summary of experiment progress."""
        return {
            "stages_completed": sum(
                1 for r in self._stage_results
                if r.status == StageStatus.COMPLETED
            ),
            "total_stages": len(self._config.stages),
            "current_stage": self._stage_results[-1].stage.value if self._stage_results else None,
            "total_cost": self._total_cost,
            "total_duration_sec": sum(r.duration_sec for r in self._stage_results),
            "stage_results": [
                {
                    "stage": r.stage.value,
                    "status": r.status.value,
                    "success_rate": r.success_rate,
                }
                for r in self._stage_results
            ],
        }


@dataclass
class ExperimentReport:
    """Final report from experiment progression."""
    
    experiment_id: str
    config: dict[str, Any]
    stages_completed: int
    total_stages: int
    stage_results: list[StageResult]
    final_metrics: dict[str, float]
    total_cost: float
    total_duration_sec: float
    success: bool
    timestamp: datetime
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "stages_completed": self.stages_completed,
            "total_stages": self.total_stages,
            "success": self.success,
            "final_metrics": self.final_metrics,
            "total_cost": self.total_cost,
            "total_duration_sec": self.total_duration_sec,
            "timestamp": self.timestamp.isoformat(),
            "stage_results": [
                {
                    "stage": r.stage.value,
                    "status": r.status.value,
                    "iterations": r.iterations_completed,
                    "success_rate": r.success_rate,
                }
                for r in self.stage_results
            ],
        }


# Convenience function
async def run_structured_experiment(
    experiment_config: dict[str, Any],
    max_cost_usd: float = 2.0,
) -> ExperimentReport:
    """Run experiment with structured 4-stage progression.
    
    Args:
        experiment_config: Experiment configuration
        max_cost_usd: Maximum budget
        
    Returns:
        Experiment report
    """
    config = ExperimentProgressConfig(max_total_cost_usd=max_cost_usd)
    manager = ExperimentProgressManager(config)
    return await manager.run_experiment(experiment_config)
