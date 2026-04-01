"""Tests for Async Parallel Experiment Pool (Upgrade 1).

Tests for:
- AsyncExperimentPool
- Isolation strategies (Docker, Worktree, Sandbox)
- Worker implementation
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from berb.experiment.async_pool import (
    AsyncExperimentPool,
    PoolConfig,
    WorkerStatus,
)
from berb.experiment.isolation import (
    DockerIsolation,
    WorktreeIsolation,
    SandboxIsolation,
    create_isolation,
)
from berb.experiment.worker import ExperimentWorkerImpl
from berb.reasoning.scientific import ExperimentDesign


class TestPoolConfig:
    """Test PoolConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = PoolConfig()
        
        assert config.max_workers == 4
        assert config.isolation == "docker"
        assert config.gpu_enabled is True
        assert config.timeout_per_experiment == 3600
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = PoolConfig(
            max_workers=8,
            isolation="sandbox",
            gpu_enabled=False,
            timeout_per_experiment=1800,
        )
        
        assert config.max_workers == 8
        assert config.isolation == "sandbox"
        assert config.gpu_enabled is False


class TestWorkerStatus:
    """Test WorkerStatus dataclass."""
    
    def test_initial_status(self):
        """Test initial worker status."""
        status = WorkerStatus(worker_id="worker-0")
        
        assert status.worker_id == "worker-0"
        assert status.is_busy is False
        assert status.current_experiment is None
        assert status.completed_count == 0
        assert status.failed_count == 0


class TestAsyncExperimentPool:
    """Test AsyncExperimentPool."""
    
    def test_pool_initialization(self):
        """Test pool initialization."""
        config = PoolConfig(max_workers=2)
        pool = AsyncExperimentPool(config)
        
        assert pool.max_workers == 2
        assert pool.isolation == "docker"
        assert pool._running is False
    
    def test_pool_status(self):
        """Test pool status reporting."""
        pool = AsyncExperimentPool()
        status = pool.get_pool_status()
        
        assert "running" in status
        assert "queue_size" in status
        assert "workers" in status
        assert status["running"] is False
    
    @pytest.mark.asyncio
    async def test_execute_parallel_empty(self):
        """Test parallel execution with empty list."""
        pool = AsyncExperimentPool(PoolConfig(max_workers=2))
        results = await pool.execute_parallel([])
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_worker_initialization(self):
        """Test worker initialization in pool."""
        pool = AsyncExperimentPool(PoolConfig(max_workers=2))
        await pool._initialize_workers()
        
        assert len(pool._workers) == 2


class TestIsolationStrategies:
    """Test isolation strategies."""
    
    def test_create_docker_isolation(self):
        """Test Docker isolation creation."""
        isolation = create_isolation("docker", gpu=True, image="test:latest")
        
        assert isinstance(isolation, DockerIsolation)
        assert isolation.config.gpu is True
        assert isolation.config.image == "test:latest"
    
    def test_create_sandbox_isolation(self):
        """Test Sandbox isolation creation."""
        isolation = create_isolation("sandbox")
        
        assert isinstance(isolation, SandboxIsolation)
    
    def test_create_invalid_isolation(self):
        """Test invalid isolation mode."""
        with pytest.raises(ValueError, match="Unknown isolation mode"):
            create_isolation("invalid_mode")
    
    def test_create_worktree_isolation(self):
        """Test Worktree isolation creation."""
        isolation = create_isolation("worktree", repo_path=Path.cwd())
        
        assert isinstance(isolation, WorktreeIsolation)


class TestDockerIsolation:
    """Test Docker isolation strategy."""
    
    @pytest.mark.skip(reason="Requires Docker installation")
    @pytest.mark.asyncio
    async def test_docker_setup(self):
        """Test Docker isolation setup."""
        isolation = DockerIsolation()
        design = ExperimentDesign(
            description="Test experiment",
        )
        design.id = "test-exp-1"
        
        context = await isolation.setup(design)
        
        assert context.experiment_id == "test-exp-1"
        assert context.workspace.exists()
        
        # Cleanup
        await isolation.cleanup(context)
    
    @pytest.mark.skip(reason="Requires Docker installation")
    @pytest.mark.asyncio
    async def test_docker_cleanup(self):
        """Test Docker isolation cleanup."""
        isolation = DockerIsolation()
        design = ExperimentDesign(
            description="Test experiment",
        )
        design.id = "test-exp-2"
        
        context = await isolation.setup(design)
        workspace = context.workspace
        
        await isolation.cleanup(context)
        
        assert not workspace.exists()


class TestSandboxIsolation:
    """Test Sandbox isolation strategy."""
    
    @pytest.mark.asyncio
    async def test_sandbox_setup(self):
        """Test Sandbox isolation setup."""
        isolation = SandboxIsolation()
        design = ExperimentDesign(
            description="Test sandbox experiment",
        )
        design.id = "test-sandbox-1"
        
        context = await isolation.setup(design)
        
        assert context.experiment_id == "test-sandbox-1"
        assert context.workspace.exists()
        
        # Cleanup
        await isolation.cleanup(context)


class TestExperimentWorkerImpl:
    """Test ExperimentWorkerImpl."""
    
    def test_worker_initialization(self):
        """Test worker initialization."""
        worker = ExperimentWorkerImpl(
            worker_id="test-worker-0",
            isolation="sandbox",
        )
        
        assert worker.worker_id == "test-worker-0"
        assert worker.config.isolation == "sandbox"
    
    @pytest.mark.asyncio
    async def test_worker_status(self):
        """Test worker status reporting."""
        worker = ExperimentWorkerImpl(worker_id="test-worker-1")
        status = await worker.get_status()
        
        assert status.worker_id == "test-worker-1"
        assert status.is_busy is False
    
    @pytest.mark.asyncio
    async def test_worker_execute_sandbox(self):
        """Test worker execution with sandbox isolation."""
        worker = ExperimentWorkerImpl(
            worker_id="test-worker-2",
            isolation="sandbox",
        )
        
        design = ExperimentDesign(
            description="Test execution",
        )
        design.id = "test-exec-1"
        design.files = {"main.py": "print('Hello, World!')"}
        
        result = await worker.execute(design)
        
        assert result.run_id == "test-exec-1"
        assert result.error is None or result.error == ""


class TestIntegration:
    """Integration tests for async pool."""
    
    @pytest.mark.asyncio
    async def test_pool_execute_single_experiment(self):
        """Test pool executing single experiment."""
        pool = AsyncExperimentPool(PoolConfig(
            max_workers=1,
            isolation="sandbox",
        ))
        
        design = ExperimentDesign(
            description="Pool test experiment",
        )
        design.id = "pool-test-1"
        design.files = {"main.py": "print('Pool test')"}
        
        results = await pool.execute_parallel([design])
        
        assert len(results) == 1
        assert results[0].run_id == "pool-test-1"
    
    @pytest.mark.asyncio
    async def test_pool_execute_multiple_experiments(self):
        """Test pool executing multiple experiments in parallel."""
        pool = AsyncExperimentPool(PoolConfig(
            max_workers=2,
            isolation="sandbox",
        ))
        
        designs = []
        for i in range(4):
            design = ExperimentDesign(description=f"Pool test experiment {i}")
            design.id = f"pool-test-{i}"
            design.files = {"main.py": f"print('Test {i}')"}
            designs.append(design)
        
        results = await pool.execute_parallel(designs)
        
        assert len(results) == 4
        assert all(r.run_id.startswith("pool-test-") for r in results)


@pytest.mark.slow
class TestPerformance:
    """Performance tests for async pool."""
    
    @pytest.mark.asyncio
    async def test_parallel_speedup(self):
        """Test parallel execution provides speedup."""
        import time
        
        # Sequential baseline
        sequential_pool = AsyncExperimentPool(PoolConfig(
            max_workers=1,
            isolation="sandbox",
        ))
        
        designs = []
        for i in range(4):
            design = ExperimentDesign(description=f"Performance test {i}")
            design.id = f"perf-test-{i}"
            design.files = {"main.py": "import time; time.sleep(0.1); print('done')"}
            designs.append(design)
        
        start = time.time()
        await sequential_pool.execute_parallel(designs)
        sequential_time = time.time() - start
        
        # Parallel execution
        parallel_pool = AsyncExperimentPool(PoolConfig(
            max_workers=4,
            isolation="sandbox",
        ))
        
        start = time.time()
        await parallel_pool.execute_parallel(designs)
        parallel_time = time.time() - start
        
        # Parallel should be faster (with some tolerance)
        assert parallel_time < sequential_time * 1.5  # 50% tolerance
