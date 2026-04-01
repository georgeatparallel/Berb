"""AIRA2-inspired asynchronous experiment execution pool.

Based on AIRA2 (Meta FAIR — arXiv:2603.26499) Section 3.1:
"Asynchronous Multi-GPU Worker Pool decouples decision-making from execution.
8 workers run in parallel — no synchronization barriers."

Key Features:
- Decouples decision-making from execution
- Workers run in parallel without synchronization barriers
- Steady-state evolution: dispatch as workers become available
- Linear throughput scaling (8 GPUs ≈ 8× experiments)
- CAID-inspired isolation (docker/worktree/sandbox)

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.experiment.async_pool import AsyncExperimentPool
    
    pool = AsyncExperimentPool(max_workers=4)
    results = await pool.execute_parallel(experiments)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from berb.experiment.runner import ExperimentResult
from berb.reasoning.scientific import ExperimentDesign

logger = logging.getLogger(__name__)


@dataclass
class WorkerStatus:
    """Worker status information.
    
    Attributes:
        worker_id: Unique worker identifier
        is_busy: Whether worker is currently executing
        current_experiment: ID of current experiment (if busy)
        completed_count: Number of successfully completed experiments
        failed_count: Number of failed experiments
        last_heartbeat: Last activity timestamp
    """
    worker_id: str
    is_busy: bool = False
    current_experiment: str | None = None
    completed_count: int = 0
    failed_count: int = 0
    last_heartbeat: float = field(default_factory=time.time)


class ExperimentWorker(Protocol):
    """Individual experiment worker interface.
    
    Attributes:
        worker_id: Unique worker identifier
    """
    worker_id: str
    
    async def execute(self, design: ExperimentDesign) -> ExperimentResult:
        """Execute single experiment.
        
        Args:
            design: Experiment design to execute
            
        Returns:
            Experiment result
        """
        ...
    
    async def get_status(self) -> WorkerStatus:
        """Get worker status.
        
        Returns:
            Current worker status
        """
        ...


@dataclass
class PoolConfig:
    """Configuration for async experiment pool.
    
    Attributes:
        max_workers: Maximum number of parallel workers
        isolation: Isolation mode (docker/worktree/sandbox)
        gpu_enabled: Whether to enable GPU access
        timeout_per_experiment: Default timeout per experiment (seconds)
        docker_image: Docker image to use (if isolation=docker)
    """
    max_workers: int = 4
    isolation: str = "docker"
    gpu_enabled: bool = True
    timeout_per_experiment: int = 3600
    docker_image: str = "berb/experiment:latest"


class AsyncExperimentPool:
    """AIRA2-inspired asynchronous experiment execution pool.
    
    Implements parallel experiment execution with:
    - CAID-inspired isolation (each experiment isolated)
    - AIRA2-inspired scheduling (steady-state dispatch)
    - No synchronization barriers
    - Linear throughput scaling
    
    Usage:
        pool = AsyncExperimentPool(max_workers=4)
        results = await pool.execute_parallel(experiments)
    
    Architecture:
        ┌─────────────────────────────────────────┐
        │         AsyncExperimentPool             │
        │  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐    │
        │  │ W-0 │  │ W-1 │  │ W-2 │  │ W-3 │    │
        │  └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘    │
        │     │        │        │        │        │
        │     └────────┴────────┴────────┘        │
        │              Queue                      │
        └─────────────────────────────────────────┘
    """
    
    def __init__(
        self,
        config: PoolConfig | None = None,
    ):
        """Initialize async experiment pool.
        
        Args:
            config: Pool configuration (uses defaults if None)
        """
        self.config = config or PoolConfig()
        self.max_workers = self.config.max_workers
        self.isolation = self.config.isolation
        self.gpu_enabled = self.config.gpu_enabled
        self.timeout = self.config.timeout_per_experiment
        
        self._workers: list[ExperimentWorker] = []
        self._result_db: dict[str, ExperimentResult] = {}
        self._queue: asyncio.Queue[ExperimentDesign] = asyncio.Queue()
        self._running = False
        self._status: dict[str, WorkerStatus] = {}
    
    async def execute_parallel(
        self,
        experiments: list[ExperimentDesign],
        timeout_per_experiment: int | None = None,
    ) -> list[ExperimentResult]:
        """Run experiments in parallel isolated environments.
        
        CAID-inspired isolation:
        - Each experiment runs in its own Docker container or git worktree
        - No shared state between experiments
        - Results collected asynchronously
        - Failed experiments don't affect others
        
        AIRA2-inspired scheduling:
        - Steady-state: dispatch new experiment as worker frees
        - No synchronization barriers
        - Linear throughput scaling with workers
        
        Args:
            experiments: List of experiment designs to execute
            timeout_per_experiment: Timeout per experiment in seconds
                (overrides config default if provided)
            
        Returns:
            List of experiment results (order preserved to match input)
            
        Raises:
            RuntimeError: If pool is already running
        """
        if self._running:
            raise RuntimeError("Pool is already running")
        
        timeout = timeout_per_experiment or self.timeout
        
        # Initialize workers
        logger.info(f"Initializing {self.max_workers} workers...")
        await self._initialize_workers()
        
        # Queue all experiments
        for exp in experiments:
            await self._queue.put(exp)
        
        # Start workers
        self._running = True
        start_time = time.time()
        
        # Dispatch workers
        tasks = [
            asyncio.create_task(self._worker_loop(worker, timeout))
            for worker in self._workers
        ]
        
        logger.info(f"Started {len(tasks)} worker tasks")
        
        # Wait for queue to be empty
        await self._queue.join()
        
        # Stop workers
        self._running = False
        await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        # Log summary
        total_completed = sum(
            s.completed_count for s in self._status.values()
        )
        total_failed = sum(
            s.failed_count for s in self._status.values()
        )
        logger.info(
            f"Pool execution complete: {total_completed} succeeded, "
            f"{total_failed} failed in {elapsed:.2f}s"
        )
        
        # Return results in original order
        return [self._result_db[exp.id] for exp in experiments]
    
    async def _initialize_workers(self) -> None:
        """Initialize worker pool."""
        from berb.experiment.worker import ExperimentWorkerImpl
        
        for i in range(self.max_workers):
            worker = ExperimentWorkerImpl(
                worker_id=f"worker-{i}",
                isolation=self.isolation,
                gpu_enabled=self.gpu_enabled,
                docker_image=self.config.docker_image,
            )
            self._workers.append(worker)
            
            status = WorkerStatus(worker_id=worker.worker_id)
            self._status[worker.worker_id] = status
            
            logger.info(f"Initialized {worker.worker_id} (isolation={self.isolation})")
    
    async def _worker_loop(
        self,
        worker: ExperimentWorker,
        timeout: int,
    ) -> None:
        """Worker main loop - process queue until stopped.
        
        Args:
            worker: Worker instance
            timeout: Timeout per experiment in seconds
        """
        worker_name = worker.worker_id
        
        while self._running or not self._queue.empty():
            try:
                # Get next experiment (non-blocking check)
                try:
                    design = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.1)
                    continue
                
                # Update status
                status = self._status[worker_name]
                status.is_busy = True
                status.current_experiment = design.id
                status.last_heartbeat = time.time()
                
                logger.info(f"{worker_name} executing {design.id}")
                
                # Execute experiment with timeout
                try:
                    result = await asyncio.wait_for(
                        worker.execute(design),
                        timeout=timeout,
                    )
                    self._result_db[design.id] = result
                    status.completed_count += 1
                    logger.info(f"{worker_name} completed {design.id}")
                    
                except asyncio.TimeoutError:
                    logger.error(f"{worker_name} timeout on {design.id}")
                    result = ExperimentResult(
                        run_id=design.id,
                        iteration=0,
                        code="",
                        metrics={},
                        primary_metric=None,
                        improved=False,
                        kept=False,
                        elapsed_sec=timeout,
                        stdout="",
                        stderr=f"Timeout after {timeout}s",
                        error="Timeout",
                    )
                    self._result_db[design.id] = result
                    status.failed_count += 1
                    
                except Exception as e:
                    logger.exception(f"{worker_name} failed on {design.id}: {e}")
                    result = ExperimentResult(
                        run_id=design.id,
                        iteration=0,
                        code="",
                        metrics={},
                        primary_metric=None,
                        improved=False,
                        kept=False,
                        elapsed_sec=0,
                        stdout="",
                        stderr=str(e),
                        error=str(e),
                    )
                    self._result_db[design.id] = result
                    status.failed_count += 1
                
                # Mark task done
                self._queue.task_done()
                
                # Update status
                status.is_busy = False
                status.current_experiment = None
                status.last_heartbeat = time.time()
                
            except Exception as e:
                logger.exception(f"{worker_name} loop error: {e}")
                if not self._queue.empty():
                    # Mark task done to avoid deadlock
                    try:
                        self._queue.task_done()
                    except ValueError:
                        pass
    
    def get_pool_status(self) -> dict[str, Any]:
        """Get current pool status.
        
        Returns:
            Dictionary with pool status information
        """
        return {
            "running": self._running,
            "queue_size": self._queue.qsize(),
            "workers": {
                wid: {
                    "is_busy": status.is_busy,
                    "current_experiment": status.current_experiment,
                    "completed": status.completed_count,
                    "failed": status.failed_count,
                }
                for wid, status in self._status.items()
            },
            "results_count": len(self._result_db),
        }
    
    async def shutdown(self) -> None:
        """Shutdown the pool gracefully."""
        logger.info("Shutting down pool...")
        self._running = False
        
        # Wait for queue to drain
        if not self._queue.empty():
            logger.info(f"Waiting for {self._queue.qsize()} pending experiments")
            await self._queue.join()
        
        logger.info("Pool shutdown complete")


async def create_pool(config: PoolConfig | None = None) -> AsyncExperimentPool:
    """Factory function to create and initialize pool.
    
    Args:
        config: Pool configuration
        
    Returns:
        Initialized AsyncExperimentPool
    """
    pool = AsyncExperimentPool(config)
    await pool._initialize_workers()
    return pool
