"""HyperAgent base classes and interfaces.

This module defines the core abstractions for Hyperagents:
- Hyperagent: Main self-improving agent
- HyperagentState: State tracking
- ImprovementResult: Result of self-improvement

Based on Facebook AI Research paper (arXiv:2603.19461v1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AgentPhase(str, Enum):
    """Phase of Hyperagent execution."""
    
    INIT = "init"
    TASK_EXECUTION = "task_execution"
    PERFORMANCE_TRACKING = "performance_tracking"
    META_ANALYSIS = "meta_analysis"
    SELF_MODIFICATION = "self_modification"
    EVALUATION = "evaluation"
    SELECTION = "selection"


@dataclass
class TaskResult:
    """Result from task execution."""
    
    task_id: str
    success: bool
    output: Any = None
    error: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    duration_sec: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metrics": self.metrics,
            "duration_sec": self.duration_sec,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Improvement:
    """A self-improvement made by the Hyperagent."""
    
    improvement_id: str
    description: str
    code_diff: str  # Git-style diff
    affected_component: str  # "task_agent" or "meta_agent"
    expected_benefit: str
    actual_benefit: float | None = None  # Measured after evaluation
    confidence: float = 0.0  # 0-1 confidence in improvement
    transferable: bool = True  # Can transfer to other domains
    source_domain: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "improvement_id": self.improvement_id,
            "description": self.description,
            "code_diff": self.code_diff,
            "affected_component": self.affected_component,
            "expected_benefit": self.expected_benefit,
            "actual_benefit": self.actual_benefit,
            "confidence": self.confidence,
            "transferable": self.transferable,
            "source_domain": self.source_domain,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ImprovementResult:
    """Result of self-improvement iteration."""
    
    iteration: int
    improvements_made: list[Improvement] = field(default_factory=list)
    performance_delta: float = 0.0  # Change in performance
    selected_variant: str = ""
    evaluation_scores: dict[str, float] = field(default_factory=dict)
    success: bool = True
    error: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "iteration": self.iteration,
            "improvements_made": [i.to_dict() for i in self.improvements_made],
            "performance_delta": self.performance_delta,
            "selected_variant": self.selected_variant,
            "evaluation_scores": self.evaluation_scores,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class HyperagentState:
    """State of the Hyperagent."""
    
    phase: AgentPhase = AgentPhase.INIT
    current_variant_id: str = "v0"
    iteration: int = 0
    total_tasks_executed: int = 0
    total_improvements: int = 0
    cumulative_performance_gain: float = 0.0
    current_task_result: TaskResult | None = None
    last_improvement_result: ImprovementResult | None = None
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "phase": self.phase.value,
            "current_variant_id": self.current_variant_id,
            "iteration": self.iteration,
            "total_tasks_executed": self.total_tasks_executed,
            "total_improvements": self.total_improvements,
            "cumulative_performance_gain": self.cumulative_performance_gain,
            "current_task_result": self.current_task_result.to_dict() if self.current_task_result else None,
            "last_improvement_result": self.last_improvement_result.to_dict() if self.last_improvement_result else None,
            "errors": self.errors,
            "metadata": self.metadata,
        }
    
    def record_error(self, error: str):
        """Record an error."""
        self.errors.append(error)
        logger.error("Hyperagent error: %s", error)
    
    def record_improvement(self, result: ImprovementResult):
        """Record an improvement result."""
        self.last_improvement_result = result
        self.iteration += 1
        self.total_improvements += len(result.improvements_made)
        self.cumulative_performance_gain += result.performance_delta


class Hyperagent:
    """Base class for Hyperagents.
    
    Hyperagents are self-referential self-improving agents that:
    1. Integrate task agent + meta agent into single editable program
    2. Have editable meta-level modification procedure (metacognitive)
    3. Accumulate improvements across runs
    4. Transfer improvements across domains
    
    Attributes:
        config: Berb configuration
        state: Current Hyperagent state
        memory: Persistent memory for improvements
    """
    
    def __init__(self, config: Any, storage_path: Path | None = None):
        """
        Initialize Hyperagent.
        
        Args:
            config: Berb configuration
            storage_path: Path for persistent memory (default: ~/.berb/hyperagent)
        """
        self.config = config
        self.state = HyperagentState()
        
        # Storage path for persistent memory
        if storage_path is None:
            storage_path = Path.home() / ".berb" / "hyperagent"
        self.storage_path = storage_path
        storage_path.mkdir(parents=True, exist_ok=True)
        
        # Components (initialized in subclasses)
        self.task_agent = None
        self.meta_agent = None
        self.memory = None
        self.improvement_loop = None
        
        logger.info("Hyperagent initialized (storage: %s)", storage_path)
    
    async def run_task(self, task: str, **kwargs: Any) -> TaskResult:
        """
        Execute a research task.
        
        Args:
            task: Task description
            **kwargs: Additional task parameters
        
        Returns:
            TaskResult with output and metrics
        """
        self.state.phase = AgentPhase.TASK_EXECUTION
        
        if self.task_agent is None:
            error = "Task agent not initialized"
            self.state.record_error(error)
            return TaskResult(
                task_id=task,
                success=False,
                error=error,
            )
        
        try:
            result = await self.task_agent.execute(task, **kwargs)
            self.state.current_task_result = result
            self.state.total_tasks_executed += 1
            
            # Track performance
            self.state.phase = AgentPhase.PERFORMANCE_TRACKING
            await self._track_performance(result)
            
            return result
            
        except Exception as e:
            error = f"Task execution failed: {e}"
            self.state.record_error(error)
            return TaskResult(
                task_id=task,
                success=False,
                error=error,
            )
    
    async def self_improve(self, n_iterations: int = 1) -> list[ImprovementResult]:
        """
        Run self-improvement loop.
        
        Args:
            n_iterations: Number of improvement iterations
        
        Returns:
            List of ImprovementResult for each iteration
        """
        if self.improvement_loop is None:
            error = "Improvement loop not initialized"
            self.state.record_error(error)
            return []
        
        results = []
        self.state.phase = AgentPhase.SELF_MODIFICATION
        
        for i in range(n_iterations):
            result = await self.improvement_loop.run_iteration(self)
            results.append(result)
            self.state.record_improvement(result)
        
        self.state.phase = AgentPhase.INIT
        return results
    
    async def _track_performance(self, result: TaskResult) -> None:
        """Track task performance in memory."""
        if self.memory is None:
            return
        
        # Store performance metrics
        await self.memory.store_performance(
            variant_id=self.state.current_variant_id,
            task_id=result.task_id,
            metrics=result.metrics,
            success=result.success,
        )
    
    def get_state(self) -> HyperagentState:
        """Get current Hyperagent state."""
        return self.state
    
    def get_improvement_history(self) -> list[Improvement]:
        """Get history of all improvements."""
        if self.memory is None:
            return []
        return self.memory.get_all_improvements()
    
    def transfer_improvements(self, target_domain: str) -> list[Improvement]:
        """Transfer improvements to target domain."""
        if self.memory is None:
            return []
        
        current_domain = self.config.research.topic if hasattr(self.config, "research") else "unknown"
        return self.memory.transfer_improvements(
            source_domain=current_domain,
            target_domain=target_domain,
        )
    
    async def close(self) -> None:
        """Clean up resources."""
        if self.memory is not None:
            await self.memory.close()
        logger.info("Hyperagent closed")
