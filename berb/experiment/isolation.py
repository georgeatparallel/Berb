"""CAID-inspired isolation strategies for parallel experiments.

Based on CAID (CMU — arXiv:2603.21489) Centralized Asynchronous Isolated Delegation:
- Centralized: Single manager creates dependency-aware task plans
- Asynchronous: Subtasks run concurrently without blocking
- Isolated: Each agent works in its own git worktree (branch isolation)
- Delegation: Manager delegates, agents execute, manager integrates

Isolation Modes:
- docker: Each experiment in isolated Docker container (strongest)
- worktree: Each experiment in separate git worktree (CAID pattern)
- sandbox: Lightweight Python sandbox (minimal isolation)

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.experiment.isolation import create_isolation
    
    isolation = create_isolation("docker", gpu=True)
    context = await isolation.setup(design)
    result = await isolation.execute(context, code)
    await isolation.cleanup(context)
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from berb.reasoning.scientific import ExperimentDesign

logger = logging.getLogger(__name__)


@dataclass
class IsolationContext:
    """Isolation execution context.
    
    Attributes:
        experiment_id: Unique experiment identifier
        workspace: Path to isolated workspace
        resources: Additional resources (container IDs, branch names, etc.)
        metadata: Additional metadata
    """
    experiment_id: str
    workspace: Path
    resources: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class IsolationStrategy(ABC):
    """Base isolation strategy.
    
    All isolation strategies must implement:
    - setup: Create isolated environment
    - execute: Execute code in isolated environment
    - cleanup: Remove isolated environment
    """
    
    @abstractmethod
    async def setup(self, design: ExperimentDesign) -> IsolationContext:
        """Setup isolated environment.
        
        Args:
            design: Experiment design
            
        Returns:
            Isolation context
        """
        pass
    
    @abstractmethod
    async def execute(
        self,
        context: IsolationContext,
        code: str,
        timeout: int = 3600,
    ) -> str:
        """Execute code in isolated environment.
        
        Args:
            context: Isolation context
            code: Python code to execute
            timeout: Execution timeout in seconds
            
        Returns:
            Execution output (stdout)
        """
        pass
    
    @abstractmethod
    async def cleanup(self, context: IsolationContext) -> None:
        """Cleanup isolated environment.
        
        Args:
            context: Isolation context
        """
        pass


@dataclass
class DockerIsolationConfig:
    """Docker isolation configuration.
    
    Attributes:
        image: Docker image to use
        gpu: Whether to enable GPU access
        memory_limit: Memory limit (e.g., "4g")
        cpu_limit: CPU limit (e.g., "2.0")
        network: Network mode ("bridge", "host", "none")
        volumes: Additional volume mounts
    """
    image: str = "berb/experiment:latest"
    gpu: bool = True
    memory_limit: str = "4g"
    cpu_limit: str = "2.0"
    network: str = "bridge"
    volumes: list[str] = field(default_factory=list)


class DockerIsolation(IsolationStrategy):
    """Docker-based isolation (strongest isolation).
    
    Features:
    - Complete filesystem isolation
    - GPU support via --gpus flag
    - Resource limits (CPU, memory)
    - Network isolation options
    - Automatic cleanup
    
    Usage:
        isolation = DockerIsolation(gpu=True)
        context = await isolation.setup(design)
        output = await isolation.execute(context, code)
        await isolation.cleanup(context)
    """
    
    def __init__(self, config: DockerIsolationConfig | None = None):
        """Initialize Docker isolation.
        
        Args:
            config: Docker configuration (uses defaults if None)
        """
        self.config = config or DockerIsolationConfig()
    
    async def setup(self, design: ExperimentDesign) -> IsolationContext:
        """Create isolated Docker container.
        
        Args:
            design: Experiment design
            
        Returns:
            Isolation context with workspace path
        """
        # Create workspace directory
        workspace = Path(f"/tmp/berb/experiments/{design.id}")
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Write experiment files
        if hasattr(design, 'files') and design.files:
            for filename, content in design.files.items():
                file_path = workspace / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
                logger.debug(f"Written {filename} to {workspace}")
        
        logger.info(f"Created Docker workspace for {design.id} at {workspace}")
        
        return IsolationContext(
            experiment_id=design.id,
            workspace=workspace,
            resources={"container_id": None},
        )
    
    async def execute(
        self,
        context: IsolationContext,
        code: str,
        timeout: int = 3600,
    ) -> str:
        """Execute in Docker container.
        
        Args:
            context: Isolation context
            code: Python code to execute
            timeout: Execution timeout in seconds
            
        Returns:
            Standard output from execution
        """
        import asyncio
        
        # Build docker run command
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{context.workspace}:/workspace:rw",
            "--workdir", "/workspace",
            "--memory", self.config.memory_limit,
            "--cpus", self.config.cpu_limit,
        ]
        
        # Add GPU support
        if self.config.gpu:
            cmd.extend(["--gpus", "all"])
        
        # Add network configuration
        if self.config.network != "bridge":
            cmd.extend(["--network", self.config.network])
        
        # Add additional volumes
        for volume in self.config.volumes:
            cmd.extend(["-v", volume])
        
        # Add image and command
        cmd.append(self.config.image)
        cmd.extend(["python", "-c", code])
        
        logger.debug(f"Running Docker command: {' '.join(cmd)}")
        
        # Execute
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            
            if proc.returncode != 0:
                logger.error(f"Docker execution failed: {stderr.decode()}")
            
            return stdout.decode()
            
        except asyncio.TimeoutError:
            logger.error(f"Docker execution timeout after {timeout}s")
            raise
        except FileNotFoundError:
            logger.error("Docker not found. Is Docker installed and in PATH?")
            raise
    
    async def cleanup(self, context: IsolationContext) -> None:
        """Cleanup workspace directory.
        
        Args:
            context: Isolation context
        """
        try:
            if context.workspace.exists():
                shutil.rmtree(context.workspace)
                logger.debug(f"Cleaned up workspace {context.workspace}")
        except Exception as e:
            logger.warning(f"Failed to cleanup workspace: {e}")


@dataclass
class WorktreeIsolationConfig:
    """Git worktree isolation configuration.
    
    Attributes:
        repo_path: Path to main git repository
        base_branch: Base branch for worktrees
        cleanup_on_finish: Whether to auto-cleanup worktrees
    """
    repo_path: Path | None = None
    base_branch: str = "main"
    cleanup_on_finish: bool = True


class WorktreeIsolation(IsolationStrategy):
    """Git worktree-based isolation (CAID pattern).
    
    Features:
    - Branch isolation per experiment
    - Shared repository objects (efficient)
    - Clean integration with git workflows
    - Automatic worktree removal
    
    Usage:
        isolation = WorktreeIsolation(repo_path=Path("/path/to/repo"))
        context = await isolation.setup(design)
        output = await isolation.execute(context, code)
        await isolation.cleanup(context)
    """
    
    def __init__(self, config: WorktreeIsolationConfig | None = None):
        """Initialize worktree isolation.
        
        Args:
            config: Worktree configuration
        """
        self.config = config or WorktreeIsolationConfig()
        
        if self.config.repo_path is None:
            # Try to find git repo in current directory
            import subprocess
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.config.repo_path = Path(result.stdout.strip())
                logger.info(f"Found git repo: {self.config.repo_path}")
            except subprocess.CalledProcessError:
                raise ValueError(
                    "No git repository found. "
                    "Please specify repo_path in config."
                )
    
    async def setup(self, design: ExperimentDesign) -> IsolationContext:
        """Create isolated git worktree.
        
        Args:
            design: Experiment design
            
        Returns:
            Isolation context with worktree path
        """
        import subprocess
        
        worktree_path = (
            self.config.repo_path.parent /
            f"worktree-{design.id}"
        )
        
        # Create worktree on separate branch
        cmd = [
            "git", "-C", str(self.config.repo_path),
            "worktree", "add", "-b", f"exp-{design.id}",
            str(worktree_path),
        ]
        
        logger.info(f"Creating worktree: {worktree_path}")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            logger.error(f"Failed to create worktree: {stderr.decode()}")
            raise RuntimeError(f"Git worktree creation failed: {stderr.decode()}")
        
        # Write experiment files
        if hasattr(design, 'files') and design.files:
            for filename, content in design.files.items():
                file_path = worktree_path / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
        
        logger.info(f"Created worktree for {design.id} at {worktree_path}")
        
        return IsolationContext(
            experiment_id=design.id,
            workspace=worktree_path,
            resources={
                "branch": f"exp-{design.id}",
                "repo_path": str(self.config.repo_path),
            },
        )
    
    async def execute(
        self,
        context: IsolationContext,
        code: str,
        timeout: int = 3600,
    ) -> str:
        """Execute code in worktree directory.
        
        Args:
            context: Isolation context
            code: Python code to execute
            timeout: Execution timeout in seconds
            
        Returns:
            Standard output from execution
        """
        # Write code to temporary file
        code_file = context.workspace / "experiment.py"
        code_file.write_text(code)
        
        # Execute in worktree
        cmd = ["python", str(code_file)]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(context.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
        
        if proc.returncode != 0:
            logger.error(f"Worktree execution failed: {stderr.decode()}")
        
        return stdout.decode()
    
    async def cleanup(self, context: IsolationContext) -> None:
        """Remove git worktree.
        
        Args:
            context: Isolation context
        """
        if not self.config.cleanup_on_finish:
            logger.debug(f"Skipping cleanup for {context.experiment_id}")
            return
        
        import subprocess
        
        branch = context.resources.get("branch", f"exp-{context.experiment_id}")
        
        # Remove worktree
        cmd = [
            "git", "-C", str(self.config.repo_path),
            "worktree", "remove", str(context.workspace),
        ]
        
        logger.info(f"Removing worktree: {context.workspace}")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            await proc.communicate()
            
            if proc.returncode != 0:
                logger.warning(f"Failed to remove worktree")
        except Exception as e:
            logger.warning(f"Failed to cleanup worktree: {e}")


@dataclass
class SandboxIsolationConfig:
    """Sandbox isolation configuration.
    
    Attributes:
        workspace_root: Root directory for sandboxes
        strip_env_vars: Environment variables to strip
        resource_limits: Resource limits for sandbox
    """
    workspace_root: Path = Path("/tmp/berb/sandbox")
    strip_env_vars: list[str] = field(default_factory=lambda: [
        "API_KEY", "TOKEN", "SECRET", "PASSWORD"
    ])
    resource_limits: dict[str, Any] = field(default_factory=dict)


class SandboxIsolation(IsolationStrategy):
    """Lightweight sandbox isolation (minimal overhead).
    
    Features:
    - Minimal isolation (same process)
    - Environment variable stripping
    - Fast execution
    - Suitable for trusted code
    
    Usage:
        isolation = SandboxIsolation()
        context = await isolation.setup(design)
        output = await isolation.execute(context, code)
    """
    
    def __init__(self, config: SandboxIsolationConfig | None = None):
        """Initialize sandbox isolation.
        
        Args:
            config: Sandbox configuration
        """
        self.config = config or SandboxIsolationConfig()
    
    async def setup(self, design: ExperimentDesign) -> IsolationContext:
        """Create sandbox workspace.
        
        Args:
            design: Experiment design
            
        Returns:
            Isolation context with workspace path
        """
        workspace = self.config.workspace_root / design.id
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Write experiment files
        if hasattr(design, 'files') and design.files:
            for filename, content in design.files.items():
                file_path = workspace / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
        
        logger.debug(f"Created sandbox workspace for {design.id}")
        
        return IsolationContext(
            experiment_id=design.id,
            workspace=workspace,
            resources={},
        )
    
    async def execute(
        self,
        context: IsolationContext,
        code: str,
        timeout: int = 3600,
    ) -> str:
        """Execute in sandbox.

        Uses existing sandbox.py with stripped environment.

        Args:
            context: Isolation context
            code: Python code to execute
            timeout: Execution timeout in seconds

        Returns:
            Standard output from execution
        """
        from berb.experiment.sandbox import ExperimentSandbox
        from berb.config import SandboxConfig

        config = SandboxConfig()
        sandbox = ExperimentSandbox(config=config, workdir=context.workspace)

        result = sandbox.run(code, timeout_sec=timeout)

        return result.stdout
    
    async def cleanup(self, context: IsolationContext) -> None:
        """Cleanup sandbox workspace.
        
        Args:
            context: Isolation context
        """
        try:
            if context.workspace.exists():
                shutil.rmtree(context.workspace)
                logger.debug(f"Cleaned up sandbox {context.workspace}")
        except Exception as e:
            logger.warning(f"Failed to cleanup sandbox: {e}")


def create_isolation(
    mode: str,
    **kwargs: Any,
) -> IsolationStrategy:
    """Factory function for isolation strategies.
    
    Args:
        mode: Isolation mode ("docker", "worktree", "sandbox")
        **kwargs: Additional configuration arguments
        
    Returns:
        Configured isolation strategy
        
    Raises:
        ValueError: If mode is unknown
    """
    strategies: dict[str, type[IsolationStrategy]] = {
        "docker": DockerIsolation,
        "worktree": WorktreeIsolation,
        "sandbox": SandboxIsolation,
    }
    
    if mode not in strategies:
        raise ValueError(
            f"Unknown isolation mode: {mode}. "
            f"Valid modes: {list(strategies.keys())}"
        )
    
    # Create config class based on mode
    config_classes = {
        "docker": DockerIsolationConfig,
        "worktree": WorktreeIsolationConfig,
        "sandbox": SandboxIsolationConfig,
    }

    config_class = config_classes[mode]

    # Filter kwargs to only valid fields for each config class
    valid_fields = {f.name for f in dataclasses.fields(config_class)}
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_fields}

    config = config_class(**filtered_kwargs)

    return strategies[mode](config)


__all__ = [
    "IsolationContext",
    "IsolationStrategy",
    "DockerIsolation",
    "DockerIsolationConfig",
    "WorktreeIsolation",
    "WorktreeIsolationConfig",
    "SandboxIsolation",
    "SandboxIsolationConfig",
    "create_isolation",
]
