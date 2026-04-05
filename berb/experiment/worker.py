"""Experiment worker implementation for async pool.

This module provides the concrete worker implementation that executes
individual experiments within the AsyncExperimentPool.

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.experiment.worker import ExperimentWorkerImpl
    
    worker = ExperimentWorkerImpl(worker_id="worker-0")
    result = await worker.execute(design)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from berb.experiment.async_pool import ExperimentWorker, WorkerStatus
from berb.experiment.isolation import (
    IsolationContext,
    IsolationStrategy,
    create_isolation,
)
from berb.experiment.runner import ExperimentResult
from berb.reasoning.scientific import ExperimentDesign

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Worker configuration.
    
    Attributes:
        worker_id: Unique worker identifier
        isolation: Isolation mode (docker/worktree/sandbox)
        gpu_enabled: Whether to enable GPU access
        docker_image: Docker image to use
        timeout: Default timeout in seconds
    """
    worker_id: str
    isolation: str = "docker"
    gpu_enabled: bool = True
    docker_image: str = "berb/experiment:latest"
    timeout: int = 3600


class ExperimentWorkerImpl(ExperimentWorker):
    """Concrete experiment worker implementation.
    
    Executes individual experiments within the AsyncExperimentPool.
    
    Features:
    - Isolated execution via Docker/worktree/sandbox
    - Automatic timeout handling
    - Resource cleanup
    - Status tracking
    
    Usage:
        worker = ExperimentWorkerImpl(worker_id="worker-0")
        result = await worker.execute(design)
        status = await worker.get_status()
    """
    
    def __init__(
        self,
        worker_id: str,
        isolation: str = "docker",
        gpu_enabled: bool = True,
        docker_image: str = "berb/experiment:latest",
        timeout: int = 3600,
    ):
        """Initialize experiment worker.
        
        Args:
            worker_id: Unique worker identifier
            isolation: Isolation mode (docker/worktree/sandbox)
            gpu_enabled: Whether to enable GPU access
            docker_image: Docker image to use (for docker isolation)
            timeout: Default timeout in seconds
        """
        self.worker_id = worker_id
        self.config = WorkerConfig(
            worker_id=worker_id,
            isolation=isolation,
            gpu_enabled=gpu_enabled,
            docker_image=docker_image,
            timeout=timeout,
        )
        
        # Create isolation strategy
        self._isolation: IsolationStrategy = create_isolation(
            isolation,
            gpu=gpu_enabled,
            image=docker_image,
        )
        
        # State tracking
        self._current_context: IsolationContext | None = None
        self._is_busy = False
        self._completed_count = 0
        self._failed_count = 0
        self._last_heartbeat = time.time()
    
    async def execute(self, design: ExperimentDesign) -> ExperimentResult:
        """Execute single experiment.
        
        Process:
        1. Setup isolated environment
        2. Execute experiment code
        3. Collect results
        4. Cleanup environment
        
        Args:
            design: Experiment design to execute
            
        Returns:
            Experiment result
            
        Raises:
            RuntimeError: If execution fails
        """
        start_time = time.time()
        self._is_busy = True
        self._last_heartbeat = start_time
        
        logger.info(f"{self.worker_id} starting {design.id}")
        
        try:
            # Step 1: Setup isolated environment
            self._current_context = await self._isolation.setup(design)
            logger.debug(f"{self.worker_id} setup complete for {design.id}")
            
            # Step 2: Get experiment code
            code = self._extract_code(design)
            
            # Step 3: Execute in isolated environment
            stdout = await self._isolation.execute(
                self._current_context,
                code,
                timeout=self.config.timeout,
            )
            
            # Step 4: Create result
            elapsed = time.time() - start_time
            result = ExperimentResult(
                run_id=design.id,
                iteration=0,
                code=code,
                metrics={"elapsed": elapsed},
                primary_metric=None,  # Will be set by evaluator
                improved=False,
                kept=True,
                elapsed_sec=elapsed,
                stdout=stdout,
                stderr="",
                error=None,
            )
            
            self._completed_count += 1
            logger.info(f"{self.worker_id} completed {design.id} in {elapsed:.2f}s")
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(f"{self.worker_id} failed {design.id}: {e}")
            
            self._failed_count += 1
            return ExperimentResult(
                run_id=design.id,
                iteration=0,
                code="",
                metrics={},
                primary_metric=None,
                improved=False,
                kept=False,
                elapsed_sec=elapsed,
                stdout="",
                stderr=str(e),
                error=str(e),
            )
            
        finally:
            # Step 5: Cleanup
            if self._current_context:
                try:
                    await self._isolation.cleanup(self._current_context)
                    logger.debug(f"{self.worker_id} cleanup complete for {design.id}")
                except Exception as e:
                    logger.warning(f"{self.worker_id} cleanup failed: {e}")
            
            self._current_context = None
            self._is_busy = False
            self._last_heartbeat = time.time()
    
    async def get_status(self) -> WorkerStatus:
        """Get worker status.
        
        Returns:
            Current worker status
        """
        return WorkerStatus(
            worker_id=self.worker_id,
            is_busy=self._is_busy,
            current_experiment=self._current_context.experiment_id if self._current_context else None,
            completed_count=self._completed_count,
            failed_count=self._failed_count,
            last_heartbeat=self._last_heartbeat,
        )
    
    def _extract_code(self, design: ExperimentDesign) -> str:
        """Extract experiment code from design.
        
        Args:
            design: Experiment design
            
        Returns:
            Python code to execute
            
        Raises:
            ValueError: If no code found in design
        """
        # Check if design has files attribute
        if hasattr(design, 'files') and design.files:
            # Look for main experiment file
            for filename in ["main.py", "experiment.py", "run.py"]:
                if filename in design.files:
                    return design.files[filename]
            
            # Return first Python file
            for filename, content in design.files.items():
                if filename.endswith('.py'):
                    return content
        
        # Check if design has code attribute
        if hasattr(design, 'code'):
            return design.code
        
        # Check if design has methodology that can be converted to code
        if hasattr(design, 'methodology') and design.methodology:
            # Generate placeholder code
            return self._generate_placeholder_code(design)
        
        raise ValueError(
            f"No code found in experiment design {design.id}. "
            f"Expected 'files', 'code', or 'methodology' attribute."
        )
    
    def _generate_placeholder_code(self, design: ExperimentDesign) -> str:
        """Generate placeholder code from design.
        
        Args:
            design: Experiment design
            
        Returns:
            Placeholder Python code
        """
        description = getattr(design, 'description', 'Experiment')
        
        return f'''
"""
Experiment: {description}
Design ID: {design.id}

This is a placeholder experiment generated from design.
Replace with actual implementation.
"""

import time
import random

def main():
    print("Running experiment: {description}")
    
    # Simulate experiment
    time.sleep(1)
    
    # Generate random metric
    metric = random.random()
    print(f"Result: {{metric:.4f}}")
    
    return metric

if __name__ == "__main__":
    result = main()
    print(f"Experiment complete. Metric: {{result}}")
'''


__all__ = [
    "ExperimentWorkerImpl",
    "WorkerConfig",
]
