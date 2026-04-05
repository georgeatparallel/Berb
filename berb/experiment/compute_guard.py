"""Experiment compute guards and monitoring.

This module provides:
- Experiment cost estimation (GPU hours, API cost, wall-clock time)
- Budget/time decision logic (run/skip/suggest alternative)
- Pre-Mortem risk assessment for experiments
- Real-time experiment monitoring
- Early failure detection

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExperimentStatus(str, Enum):
    """Experiment execution status.

    Attributes:
        QUEUED: Experiment queued for execution
        RUNNING: Experiment currently running
        COMPLETED: Experiment completed successfully
        FAILED: Experiment failed
        STOPPED: Experiment stopped early
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class ExperimentCostEstimate(BaseModel):
    """Estimated experiment cost.

    Attributes:
        gpu_hours: Estimated GPU hours
        api_cost_usd: Estimated API cost
        wall_clock_minutes: Estimated wall-clock time
        total_cost_usd: Total estimated cost
        confidence: Confidence in estimate (0-1)
    """

    gpu_hours: float = 0.0
    api_cost_usd: float = 0.0
    wall_clock_minutes: float = 0.0
    total_cost_usd: float = 0.0
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    def is_affordable(
        self,
        budget_remaining: float,
        time_remaining_minutes: float,
        max_gpu_hours: float = 4.0,
    ) -> tuple[bool, str]:
        """Check if experiment is affordable.

        Args:
            budget_remaining: Remaining budget
            time_remaining_minutes: Remaining time
            max_gpu_hours: Maximum GPU hours allowed

        Returns:
            Tuple of (is_affordable, reason)
        """
        if self.api_cost_usd > budget_remaining * 0.5:
            return (
                False,
                f"Cost ${self.api_cost_usd:.2f} exceeds 50% of remaining budget ${budget_remaining:.2f}",
            )

        if self.wall_clock_minutes > time_remaining_minutes:
            return (
                False,
                f"Time {self.wall_clock_minutes:.0f}min exceeds remaining time {time_remaining_minutes:.0f}min",
            )

        if self.gpu_hours > max_gpu_hours:
            return (
                False,
                f"GPU hours {self.gpu_hours:.1f} exceeds {max_gpu_hours}hr limit",
            )

        return (
            True,
            f"Within budget: ${self.api_cost_usd:.2f}, {self.wall_clock_minutes:.0f}min, {self.gpu_hours:.1f} GPU-hr",
        )


class ExperimentProgress(BaseModel):
    """Real-time experiment progress.

    Attributes:
        experiment_id: Experiment identifier
        status: Current status
        progress_percent: Progress percentage (0-100)
        current_epoch: Current epoch (for training)
        total_epochs: Total epochs
        current_metric: Current metric value
        eta_minutes: Estimated time remaining
        started_at: When experiment started
    """

    experiment_id: str
    status: ExperimentStatus = ExperimentStatus.QUEUED
    progress_percent: float = 0.0
    current_epoch: int = 0
    total_epochs: int = 0
    current_metric: float | None = None
    eta_minutes: float | None = None
    started_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(mode="json")


class ExperimentResults(BaseModel):
    """Experiment results.

    Attributes:
        experiment_id: Experiment identifier
        status: Final status
        metrics: Final metrics
        figures: Generated figure paths
        logs: Log file paths
        artifacts: Additional artifacts
        duration_minutes: Total duration
        cost_usd: Total cost
    """

    experiment_id: str
    status: ExperimentStatus
    metrics: dict[str, float] = Field(default_factory=dict)
    figures: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    duration_minutes: float = 0.0
    cost_usd: float = 0.0


class ComputeGuard:
    """Prevent expensive experiments from blowing the budget.

    This guard estimates experiment costs and blocks those that
    exceed budget or time limits.

    Usage::

        guard = ComputeGuard(budget_remaining=10.0, time_remaining_minutes=120)
        estimate = await guard.estimate_experiment_cost(experiment_design)
        should_run, reason = await guard.should_run(estimate)

    Attributes:
        budget_remaining: Remaining budget in USD
        time_remaining_minutes: Remaining time in minutes
        max_gpu_hours: Maximum GPU hours allowed
    """

    def __init__(
        self,
        budget_remaining: float = 10.0,
        time_remaining_minutes: float = 120.0,
        max_gpu_hours: float = 4.0,
    ):
        """Initialize compute guard.

        Args:
            budget_remaining: Remaining budget
            time_remaining_minutes: Remaining time
            max_gpu_hours: Maximum GPU hours
        """
        self.budget_remaining = budget_remaining
        self.time_remaining_minutes = time_remaining_minutes
        self.max_gpu_hours = max_gpu_hours

        # Cost estimates (per unit)
        self.gpu_hour_cost = 0.50  # $ per GPU hour
        self.api_call_cost = 0.001  # $ per API call

    async def estimate_experiment_cost(
        self,
        experiment_design: dict[str, Any],
    ) -> ExperimentCostEstimate:
        """Estimate experiment cost.

        Args:
            experiment_design: Experiment design dictionary

        Returns:
            ExperimentCostEstimate
        """
        # Extract design parameters
        dataset_size = experiment_design.get("dataset_size", 1000)
        num_configurations = experiment_design.get("num_configurations", 1)
        epochs = experiment_design.get("epochs", 10)
        gpu_required = experiment_design.get("gpu_required", False)
        model_size = experiment_design.get("model_size", "small")
        api_calls = experiment_design.get("api_calls", 0)

        # Estimate GPU hours
        base_hours = self._estimate_gpu_hours(
            dataset_size, num_configurations, epochs, model_size
        )
        gpu_hours = base_hours * (2.0 if gpu_required else 1.0)

        # Estimate API cost
        api_cost = api_calls * self.api_call_cost

        # Estimate wall-clock time
        wall_clock = gpu_hours * 60  # minutes (simplified)

        # Total cost
        total_cost = gpu_hours * self.gpu_hour_cost + api_cost

        return ExperimentCostEstimate(
            gpu_hours=gpu_hours,
            api_cost_usd=api_cost,
            wall_clock_minutes=wall_clock,
            total_cost_usd=total_cost,
            confidence=0.7,  # Simplified
        )

    def _estimate_gpu_hours(
        self,
        dataset_size: int,
        num_configurations: int,
        epochs: int,
        model_size: str,
    ) -> float:
        """Estimate GPU hours for training.

        Args:
            dataset_size: Dataset size
            num_configurations: Number of configurations
            epochs: Number of epochs
            model_size: Model size (small/medium/large)

        Returns:
            Estimated GPU hours
        """
        # Base time per epoch (hours)
        size_multipliers = {
            "small": 0.01,
            "medium": 0.05,
            "large": 0.2,
            "xlarge": 0.5,
        }
        multiplier = size_multipliers.get(model_size, 0.05)

        # Scale with dataset size
        dataset_factor = dataset_size / 10000.0

        base_hours = epochs * multiplier * dataset_factor
        return base_hours * num_configurations

    async def should_run(
        self,
        estimate: ExperimentCostEstimate,
        experiment_design: dict[str, Any] | None = None,
        use_pre_mortem: bool = True,
        llm_client: Any | None = None,
    ) -> tuple[bool, str]:
        """Decide whether experiment should run.

        Args:
            estimate: Cost estimate
            experiment_design: Experiment design for risk assessment
            use_pre_mortem: Whether to use pre-mortem risk assessment
            llm_client: LLM client for pre-mortem analysis

        Returns:
            Tuple of (should_run, reason)
        """
        # Basic affordability check
        affordable, reason = estimate.is_affordable(
            self.budget_remaining,
            self.time_remaining_minutes,
            self.max_gpu_hours,
        )

        if not affordable:
            return False, reason

        # Pre-mortem risk assessment if enabled
        if use_pre_mortem and experiment_design and llm_client:
            risk_assessment = await self._pre_mortem_risk_assessment(
                experiment_design, llm_client
            )

            if risk_assessment.get("high_risk", False):
                return False, f"High risk experiment: {risk_assessment.get('primary_risk', 'Unknown risk')}"

        return True, reason

    async def _pre_mortem_risk_assessment(
        self,
        experiment_design: dict[str, Any],
        llm_client: Any,
    ) -> dict[str, Any]:
        """Conduct pre-mortem risk assessment for experiment.

        Uses pre-mortem analysis to identify potential failure modes:
        1. Failure Narrative - Imagine the experiment failed
        2. Root Cause Backtrack - What caused the failure?
        3. Early Warning Signals - What would we see?
        4. Hardened Redesign - How to prevent failure?

        Args:
            experiment_design: Experiment design dictionary
            llm_client: LLM client for analysis

        Returns:
            Risk assessment dictionary with high_risk flag
        """
        from berb.reasoning.pre_mortem import PreMortemMethod

        # Build pre-mortem problem statement
        problem = f"""Imagine this experiment has failed after consuming 80% of the allocated budget.

Experiment Design:
- Dataset size: {experiment_design.get('dataset_size', 'N/A')}
- Model: {experiment_design.get('model_size', 'N/A')}
- Epochs: {experiment_design.get('epochs', 'N/A')}
- GPU required: {experiment_design.get('gpu_required', False)}
- API calls: {experiment_design.get('api_calls', 'N/A')}

Write a post-mortem analysis:
1. What was the primary cause of failure?
2. What early warning signals appeared in the first 30% of execution?
3. What decision was the pivot point to failure?
4. How could this failure have been prevented?

Respond with JSON:
{{
    "failure_narrative": "description of how it failed",
    "root_causes": ["cause1", "cause2"],
    "early_signals": ["signal1", "signal2"],
    "pivot_decision": "the decision that led to failure",
    "risk_level": "low|medium|high",
    "prevention_strategies": ["strategy1", "strategy2"]
}}"""

        try:
            # Use Pre-Mortem method
            pm_method = PreMortemMethod(llm_client=llm_client)

            # For now, use simplified analysis (would use full PM framework with LLM)
            risk_assessment = self._analyze_experiment_risks(experiment_design)

            return risk_assessment

        except Exception as e:
            logger.warning(f"Pre-mortem analysis failed: {e}")
            return {"high_risk": False, "primary_risk": "Analysis failed"}

    def _analyze_experiment_risks(
        self,
        experiment_design: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze experiment risks using heuristic rules.

        Args:
            experiment_design: Experiment design

        Returns:
            Risk assessment dictionary
        """
        risks = []
        risk_level = "low"

        # Risk 1: Large dataset without pilot testing
        dataset_size = experiment_design.get("dataset_size", 0)
        if dataset_size > 50000:
            risks.append("Large dataset without pilot testing")
            risk_level = "medium"

        # Risk 2: Large model with limited budget
        model_size = experiment_design.get("model_size", "small")
        budget = self.budget_remaining
        if model_size in ["large", "xlarge"] and budget < 5.0:
            risks.append("Large model with insufficient budget")
            risk_level = "high"

        # Risk 3: Many configurations without early stopping
        num_configs = experiment_design.get("num_configurations", 1)
        if num_configs > 10:
            risks.append("Too many configurations")
            if risk_level == "medium":
                risk_level = "high"

        # Risk 4: Long training without checkpointing
        epochs = experiment_design.get("epochs", 0)
        if epochs > 100:
            risks.append("Long training without intermediate checkpoints")

        # Risk 5: GPU required with tight timeline
        gpu_required = experiment_design.get("gpu_required", False)
        time_remaining = self.time_remaining_minutes
        if gpu_required and time_remaining < 120:
            risks.append("GPU experiment with tight timeline")
            risk_level = "high"

        return {
            "high_risk": risk_level == "high",
            "risk_level": risk_level,
            "risks": risks,
            "primary_risk": risks[0] if risks else "No significant risks",
            "recommendations": [
                "Run pilot study with 10% of data",
                "Implement early stopping",
                "Add intermediate checkpoints",
                "Start with smaller model",
            ] if risks else ["Proceed with caution"],
        }

    async def suggest_cheaper_alternative(
        self,
        experiment: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Suggest cheaper alternative experiment.

        Args:
            experiment: Original experiment design

        Returns:
            Modified experiment design or None
        """
        alternatives = []

        # Suggest smaller dataset
        if experiment.get("dataset_size", 0) > 1000:
            alt = experiment.copy()
            alt["dataset_size"] = experiment["dataset_size"] // 2
            alt["suggestion"] = "Use 50% of dataset for faster iteration"
            alternatives.append(alt)

        # Suggest fewer epochs
        if experiment.get("epochs", 0) > 20:
            alt = experiment.copy()
            alt["epochs"] = experiment["epochs"] // 2
            alt["suggestion"] = "Use fewer epochs with early stopping"
            alternatives.append(alt)

        # Suggest simpler model
        model_sizes = ["small", "medium", "large", "xlarge"]
        current_size = experiment.get("model_size", "medium")
        current_idx = model_sizes.index(current_size) if current_size in model_sizes else 1

        if current_idx > 0:
            alt = experiment.copy()
            alt["model_size"] = model_sizes[current_idx - 1]
            alt["suggestion"] = f"Use {alt['model_size']} model instead of {current_size}"
            alternatives.append(alt)

        # Return first viable alternative
        for alt in alternatives:
            estimate = await self.estimate_experiment_cost(alt)
            should_run, _ = await self.should_run(estimate)
            if should_run:
                return alt

        return None


class ExperimentMonitor:
    """Monitor running experiments in real-time.

    This monitor tracks experiment progress and detects failures early.

    Usage::

        monitor = ExperimentMonitor()
        progress = await monitor.check_progress(experiment_id)
        if await monitor.detect_failure_early(experiment_id, metrics):
            await stop_experiment(experiment_id)

    Attributes:
        experiments: Active experiment tracking
    """

    def __init__(self):
        """Initialize experiment monitor."""
        self._experiments: dict[str, dict[str, Any]] = {}
        self._metrics_history: dict[str, list[float]] = {}

    def register_experiment(
        self,
        experiment_id: str,
        total_epochs: int,
        start_time: datetime | None = None,
    ) -> None:
        """Register experiment for monitoring.

        Args:
            experiment_id: Experiment identifier
            total_epochs: Total epochs
            start_time: When experiment started
        """
        self._experiments[experiment_id] = {
            "status": ExperimentStatus.RUNNING,
            "total_epochs": total_epochs,
            "current_epoch": 0,
            "started_at": (start_time or datetime.now(timezone.utc)).isoformat(),
        }
        self._metrics_history[experiment_id] = []

    async def check_progress(
        self,
        experiment_id: str,
    ) -> ExperimentProgress:
        """Check experiment progress.

        Args:
            experiment_id: Experiment identifier

        Returns:
            ExperimentProgress
        """
        if experiment_id not in self._experiments:
            return ExperimentProgress(
                experiment_id=experiment_id,
                status=ExperimentStatus.QUEUED,
            )

        exp = self._experiments[experiment_id]
        total = exp["total_epochs"]
        current = exp["current_epoch"]

        progress = (current / total * 100) if total > 0 else 0.0

        # Calculate ETA
        started = datetime.fromisoformat(exp["started_at"])
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 60
        eta = None
        if progress > 0:
            total_estimated = elapsed / (progress / 100)
            eta = total_estimated - elapsed

        return ExperimentProgress(
            experiment_id=experiment_id,
            status=exp["status"],
            progress_percent=progress,
            current_epoch=current,
            total_epochs=total,
            eta_minutes=eta,
            started_at=exp["started_at"],
        )

    async def update_progress(
        self,
        experiment_id: str,
        epoch: int,
        metric: float,
    ) -> None:
        """Update experiment progress.

        Args:
            experiment_id: Experiment identifier
            epoch: Current epoch
            metric: Current metric value
        """
        if experiment_id in self._experiments:
            self._experiments[experiment_id]["current_epoch"] = epoch
            self._experiments[experiment_id]["current_metric"] = metric

        if experiment_id in self._metrics_history:
            self._metrics_history[experiment_id].append(metric)

    async def detect_failure_early(
        self,
        experiment_id: str,
        metrics: list[float],
        min_epochs: int = 5,
    ) -> bool:
        """Detect failure early based on metrics.

        Args:
            experiment_id: Experiment identifier
            metrics: List of metric values over epochs
            min_epochs: Minimum epochs before checking

        Returns:
            True if failure detected
        """
        if len(metrics) < min_epochs:
            return False

        # Check for NaN/Inf
        if any(not (0 <= m < float("inf")) for m in metrics[-3:]):
            logger.warning(f"Experiment {experiment_id}: NaN/Inf detected")
            return True

        # Check for divergence
        if len(metrics) >= 10:
            recent = metrics[-10:]
            if all(recent[i] > recent[i - 1] * 2 for i in range(1, len(recent))):
                logger.warning(f"Experiment {experiment_id}: Loss diverging")
                return True

        # Check for no improvement
        if len(metrics) >= 20:
            recent = metrics[-20:]
            best_early = min(recent[:10])
            best_recent = min(recent[10:])
            if best_recent > best_early * 1.1:
                logger.warning(f"Experiment {experiment_id}: No improvement")
                return True

        return False

    async def collect_results(
        self,
        experiment_id: str,
        final_metrics: dict[str, float],
        figures: list[str] | None = None,
        logs: list[str] | None = None,
    ) -> ExperimentResults:
        """Collect experiment results.

        Args:
            experiment_id: Experiment identifier
            final_metrics: Final metrics
            figures: Figure file paths
            logs: Log file paths

        Returns:
            ExperimentResults
        """
        exp = self._experiments.get(experiment_id, {})

        # Calculate duration
        duration = 0.0
        if "started_at" in exp:
            started = datetime.fromisoformat(exp["started_at"])
            duration = (datetime.now(timezone.utc) - started).total_seconds() / 60

        return ExperimentResults(
            experiment_id=experiment_id,
            status=exp.get("status", ExperimentStatus.COMPLETED),
            metrics=final_metrics,
            figures=figures or [],
            logs=logs or [],
            duration_minutes=duration,
        )

    async def stop_experiment(
        self,
        experiment_id: str,
        reason: str,
    ) -> None:
        """Stop experiment early.

        Args:
            experiment_id: Experiment identifier
            reason: Reason for stopping
        """
        if experiment_id in self._experiments:
            self._experiments[experiment_id]["status"] = ExperimentStatus.STOPPED
            logger.info(f"Stopped experiment {experiment_id}: {reason}")


@dataclass
class ComputeGuardConfig:
    """Configuration for compute guards.

    Attributes:
        budget_remaining: Remaining budget
        time_remaining_minutes: Remaining time
        max_gpu_hours: Maximum GPU hours
        enable_early_stopping: Enable early failure detection
        min_improvement_threshold: Minimum improvement per epoch
    """

    budget_remaining: float = 10.0
    time_remaining_minutes: float = 120.0
    max_gpu_hours: float = 4.0
    enable_early_stopping: bool = True
    min_improvement_threshold: float = 0.01


# Convenience functions
async def check_experiment_affordability(
    experiment_design: dict[str, Any],
    budget_remaining: float = 10.0,
    time_remaining_minutes: float = 120.0,
) -> tuple[bool, str, ExperimentCostEstimate]:
    """Check if experiment is affordable.

    Args:
        experiment_design: Experiment design
        budget_remaining: Remaining budget
        time_remaining_minutes: Remaining time

    Returns:
        Tuple of (should_run, reason, estimate)
    """
    guard = ComputeGuard(
        budget_remaining=budget_remaining,
        time_remaining_minutes=time_remaining_minutes,
    )

    estimate = await guard.estimate_experiment_cost(experiment_design)
    should_run, reason = await guard.should_run(estimate)

    return should_run, reason, estimate
