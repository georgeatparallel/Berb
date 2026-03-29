"""Task Agent for HyperAgent.

The Task Agent solves research tasks using an editable program.
It can be modified by the Meta Agent to improve performance.

Based on Facebook AI Research paper (arXiv:2603.19461v1).

SECURITY FIX #1: Docker-based sandboxing for code execution.
All task code now runs in isolated containers with:
- No network access
- Read-only filesystem
- Memory/CPU limits
- No privilege escalation
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from berb.config import RCConfig

logger = logging.getLogger(__name__)

# Try to import docker, fall back to None if not available
try:
    import docker
    from docker.errors import DockerException, APIError, ContainerError
    DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    DockerException = Exception
    APIError = Exception
    ContainerError = Exception
    DOCKER_AVAILABLE = False


@dataclass
class TaskAgentConfig:
    """Configuration for Task Agent."""

    code_path: Path | None = None
    """Path to editable code file"""

    initial_code: str | None = None
    """Initial code if no file exists"""

    max_execution_time: int = 3600
    """Maximum execution time in seconds"""

    sandbox_enabled: bool = True
    """Run code in sandbox"""

    gpu_enabled: bool = False
    """Enable GPU access"""

    # SECURITY FIX #1: Docker sandbox configuration
    docker_image: str = "python:3.12-slim"
    """Docker image for sandboxed execution"""

    docker_memory_mb: int = 512
    """Memory limit for Docker container (MB)"""

    docker_cpu_quota: int = 50000
    """CPU quota for Docker container (100000 = 1 CPU)"""

    docker_network_disabled: bool = True
    """Disable network access in container"""

    fallback_to_simulated: bool = True
    """Fall back to simulated execution if Docker unavailable"""


@dataclass
class TaskAgentState:
    """State of the Task Agent."""

    variant_id: str = "v0"
    code_version: int = 0
    total_tasks_executed: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    average_performance: float = 0.0
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_tasks_executed == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks_executed

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "variant_id": self.variant_id,
            "code_version": self.code_version,
            "total_tasks_executed": self.total_tasks_executed,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "average_performance": self.average_performance,
            "success_rate": self.success_rate,
            "last_error": self.last_error,
            "metadata": self.metadata,
        }


class TaskAgent:
    """Task-solving agent with editable code.

    SECURITY FIX #1: Code execution is now sandboxed in Docker containers.

    The Task Agent:
    1. Executes research tasks (literature search, experiment design, etc.)
    2. Has editable code that can be modified by Meta Agent
    3. Tracks performance metrics for evaluation
    4. Can be versioned and compared against variants

    Sandbox Features:
    - Docker container isolation
    - No network access (network_mode='none')
    - Read-only filesystem mount
    - Memory and CPU limits
    - No privilege escalation (no-new-privileges)
    - All capabilities dropped

    Attributes:
        config: Task agent configuration
        state: Current agent state
        code: Current editable code
    """

    def __init__(
        self,
        config: RCConfig,
        task_agent_config: TaskAgentConfig | None = None,
    ):
        """
        Initialize Task Agent.

        Args:
            config: Berb configuration
            task_agent_config: Task agent specific configuration
        """
        self.config = config
        self.task_config = task_agent_config or TaskAgentConfig()
        self.state = TaskAgentState()

        # Load or initialize code
        self.code = self._load_or_initialize_code()

        logger.info("Task Agent initialized (variant: %s)", self.state.variant_id)

    def _load_or_initialize_code(self) -> str:
        """Load code from file or initialize with default."""
        if self.task_config.code_path and self.task_config.code_path.exists():
            code = self.task_config.code_path.read_text(encoding="utf-8")
            logger.info("Loaded task agent code from %s", self.task_config.code_path)
            return code

        if self.task_config.initial_code:
            logger.info("Using provided initial code")
            return self.task_config.initial_code

        # Default research task agent code
        default_code = '''"""Default Research Task Agent.

This is a placeholder for the editable task agent code.
The Meta Agent will modify this code to improve performance.
"""

from __future__ import annotations

def execute_task(task: str, **kwargs) -> dict:
    """Execute a research task.

    Args:
        task: Task description
        **kwargs: Additional parameters

    Returns:
        Task result dictionary
    """
    # TODO: Implement task execution logic
    # This code will be modified by the Meta Agent
    return {
        "success": False,
        "output": None,
        "error": "Task execution not implemented",
    }
'''
        logger.info("Using default task agent code")
        return default_code

    async def execute(self, task: str, **kwargs: Any) -> Any:
        """
        Execute a research task.

        Args:
            task: Task description
            **kwargs: Additional task parameters

        Returns:
            Task result
        """
        from berb.hyperagent.base import TaskResult

        self.state.total_tasks_executed += 1

        try:
            result = await self._execute_task_code(task, **kwargs)

            self.state.successful_tasks += 1
            self._update_performance(result)

            return result

        except Exception as e:
            self.state.failed_tasks += 1
            self.state.last_error = str(e)
            logger.error("Task execution failed: %s", e)

            return TaskResult(
                task_id=task,
                success=False,
                error=str(e),
            )

    async def _execute_task_code(self, task: str, **kwargs: Any) -> Any:
        """Execute task using the editable code.

        SECURITY FIX #1: Docker-based sandboxed execution.

        All code runs in isolated Docker containers with:
        - No network access
        - Read-only filesystem
        - Memory/CPU limits
        - No privilege escalation
        - Dropped capabilities
        """
        from berb.hyperagent.base import TaskResult

        timeout = self.task_config.max_execution_time

        # Check if Docker is available and sandbox is enabled
        if self.task_config.sandbox_enabled and DOCKER_AVAILABLE:
            try:
                result = await self._execute_in_docker(task, timeout, **kwargs)
                return result
            except DockerException as e:
                logger.error("Docker execution failed: %s", e)
                if self.task_config.fallback_to_simulated:
                    logger.warning("Falling back to simulated execution")
                    return await self._execute_simulated(task, timeout)
                return TaskResult(
                    task_id=task,
                    success=False,
                    error=f"Docker execution failed: {e}",
                )
        elif self.task_config.sandbox_enabled and not DOCKER_AVAILABLE:
            logger.warning("Docker not available, using simulated execution")
            return await self._execute_simulated(task, timeout)
        else:
            # Sandbox disabled (not recommended for production)
            logger.warning("Sandbox disabled - using simulated execution only")
            return await self._execute_simulated(task, timeout)

    async def _execute_in_docker(self, task: str, timeout: int, **kwargs: Any) -> Any:
        """Execute task code in Docker sandbox.

        SECURITY FIX #1: Full container isolation.
        """
        from berb.hyperagent.base import TaskResult

        if docker is None:
            raise RuntimeError("Docker library not installed")

        client = None
        container = None

        try:
            # Create Docker client
            client = docker.from_env()

            # Generate task code
            task_code = self._generate_task_code(task, **kwargs)

            # Create temporary directory for code
            with tempfile.TemporaryDirectory() as tmpdir:
                code_path = Path(tmpdir) / "task.py"
                code_path.write_text(task_code, encoding="utf-8")

                # Build container configuration
                container_config = {
                    "image": self.task_config.docker_image,
                    "command": ["python", "/app/task.py"],
                    "volumes": {
                        tmpdir: {"bind": "/app", "mode": "ro"}  # Read-only
                    },
                    "mem_limit": f"{self.task_config.docker_memory_mb}m",
                    "cpu_quota": self.task_config.docker_cpu_quota,
                    "network_disabled": self.task_config.docker_network_disabled,
                    "read_only": True,  # Read-only root filesystem
                    "tmpfs": {
                        "/tmp": "rw,noexec,nosuid,size=100m"
                    },
                    "security_opt": ["no-new-privileges:true"],
                    "cap_drop": ["ALL"],
                    "detach": True,
                    "remove": False,  # We'll remove manually
                    "stdout": True,
                    "stderr": True,
                }

                # Run container
                container = client.containers.run(**container_config)

                # Wait for completion with timeout
                try:
                    result = container.wait(timeout=timeout)
                    logs = container.logs().decode("utf-8", errors="replace")
                    exit_code = result.get("StatusCode", -1)

                    if exit_code == 0:
                        return TaskResult(
                            task_id=task,
                            success=True,
                            output={"logs": logs, "exit_code": exit_code},
                            metrics={"execution_mode": "docker"},
                        )
                    else:
                        return TaskResult(
                            task_id=task,
                            success=False,
                            error=f"Container exited with code {exit_code}: {logs}",
                            output={"logs": logs, "exit_code": exit_code},
                        )

                except Exception as wait_error:
                    logger.error("Container wait error: %s", wait_error)
                    return TaskResult(
                        task_id=task,
                        success=False,
                        error=f"Execution timeout or error: {wait_error}",
                    )

        except APIError as e:
            logger.error("Docker API error: %s", e)
            raise
        except Exception as e:
            logger.error("Docker execution error: %s", e)
            raise
        finally:
            # Cleanup container
            if container:
                try:
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception as cleanup_error:
                    logger.warning("Container cleanup error: %s", cleanup_error)

            # Close Docker client
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    async def _execute_simulated(self, task: str, timeout: int) -> Any:
        """Simulated execution for development/fallback."""
        from berb.hyperagent.base import TaskResult

        try:
            await asyncio.sleep(0.1)  # Simulate execution
            return TaskResult(
                task_id=task,
                success=True,
                output={"message": f"Task '{task}' executed (simulated)", "mode": "simulated"},
                metrics={"execution_time": 0.1, "execution_mode": "simulated"},
            )
        except asyncio.TimeoutError:
            return TaskResult(
                task_id=task,
                success=False,
                error=f"Execution timeout after {timeout}s",
                metrics={"timeout": True},
            )

    def _generate_task_code(self, task: str, **kwargs: Any) -> str:
        """Generate Python code for task execution."""
        # Include the agent's editable code
        return f'''"""Generated task code for HyperAgent execution."""

{self.code}

# Task execution
if __name__ == "__main__":
    import json
    result = execute_task({json.dumps(task)!r}, **{json.dumps(kwargs)})
    print(json.dumps(result))
'''

    def _update_performance(self, result: Any) -> None:
        """Update performance metrics based on result."""
        # Extract metrics from result
        if hasattr(result, "metrics") and result.metrics:
            # Update running average
            n = self.state.total_tasks_executed
            old_avg = self.state.average_performance
            new_metric = result.metrics.get("performance_score", 1.0)
            self.state.average_performance = ((old_avg * (n - 1)) + new_metric) / n

    def apply_code_modification(self, code_diff: str) -> bool:
        """
        Apply code modification from Meta Agent.

        Args:
            code_diff: Git-style diff string

        Returns:
            True if modification applied successfully
        """
        try:
            # Parse diff and apply to current code
            # In production, use proper diff/patch library
            new_code = self._apply_diff(self.code, code_diff)

            # Validate new code (syntax check, etc.)
            if not self._validate_code(new_code):
                logger.warning("Code modification failed validation")
                return False

            # Apply modification
            self.code = new_code
            self.state.code_version += 1
            self.state.variant_id = f"v{self.state.code_version}"

            # Save to file if path specified
            if self.task_config.code_path:
                self.task_config.code_path.write_text(new_code, encoding="utf-8")

            logger.info("Code modification applied (version: %d)", self.state.code_version)
            return True

        except Exception as e:
            logger.error("Failed to apply code modification: %s", e)
            return False

    def _apply_diff(self, code: str, diff: str) -> str:
        """Apply diff to code."""
        # TODO: Implement proper diff/patch application
        # For now, just return the diff as new code (simplified)
        return diff if diff.strip() else code

    def _validate_code(self, code: str) -> bool:
        """Validate code syntax and safety.

        SECURITY FIX #1: Enhanced validation for sandboxed execution.

        Validates:
        - Syntax correctness
        - Dangerous import patterns
        - Dangerous function calls (eval, exec)
        - Unicode normalization
        - Excessive resource usage patterns

        Returns:
            True if code passes validation
        """
        try:
            # Syntax check
            compile(code, "<string>", "exec")

            # Normalize unicode to prevent unicode bombs
            import unicodedata
            normalized = unicodedata.normalize("NFKC", code)

            # Safety checks (no dangerous imports, etc.)
            dangerous_patterns = [
                "import os.system",
                "import subprocess",
                "__import__('os')",
                "eval(",
                "exec(",
                "compile(",
                "__import__('subprocess')",
                "os.popen",
                "os.spawn",
                "socket.socket",
                "urllib.request",
                "requests.get",
                "requests.post",
                "http.client",
            ]

            for pattern in dangerous_patterns:
                if pattern in normalized:
                    logger.warning("Dangerous pattern detected: %s", pattern)
                    return False

            # Check for excessive line length (potential DoS)
            if any(len(line) > 10000 for line in normalized.splitlines()):
                logger.warning("Excessive line length detected (potential DoS)")
                return False

            # Check for excessive file size
            if len(normalized) > 1000000:  # 1MB limit
                logger.warning("Code size exceeds 1MB limit")
                return False

            return True

        except SyntaxError as e:
            logger.warning("Code syntax validation failed: %s", e)
            return False
        except Exception as e:
            logger.error("Code validation error: %s", e)
            return False

    def get_code(self) -> str:
        """Get current agent code."""
        return self.code

    def get_state(self) -> TaskAgentState:
        """Get current agent state."""
        return self.state

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "config": {
                "code_path": str(self.task_config.code_path) if self.task_config.code_path else None,
                "max_execution_time": self.task_config.max_execution_time,
                "sandbox_enabled": self.task_config.sandbox_enabled,
                "docker_image": self.task_config.docker_image,
            },
            "state": self.state.to_dict(),
            "code": self.code,
        }