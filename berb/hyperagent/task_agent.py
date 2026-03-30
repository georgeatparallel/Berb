"""Task Agent for HyperAgent.

The Task Agent solves research tasks using an editable program.
It can be modified by the Meta Agent to improve performance.

Based on Facebook AI Research paper (arXiv:2603.19461v1).
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from berb.config import RCConfig

logger = logging.getLogger(__name__)

# SECURITY FIX #1: Docker-based sandboxing for task agent code execution.
# Code submitted by the Meta Agent is executed inside a resource-constrained
# Docker container rather than the host process, preventing privilege
# escalation, file-system access, and network-based exfiltration.
DOCKER_AVAILABLE: bool = shutil.which("docker") is not None


@dataclass
class TaskAgentConfig:
    """Configuration for Task Agent.

    SECURITY FIX #1 fields (docker_*) enforce resource limits and network
    isolation for code executed by the Task Agent.  These are intentionally
    conservative defaults — tighten further for production deployments.
    """

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

    # SECURITY FIX #1: Docker sandbox resource controls -----------------------

    docker_image: str = "python:3.11-slim"
    """Docker image to use for sandboxed execution"""

    docker_memory_mb: int = 2048
    """Hard memory limit for the Docker container (MiB, ≤ 4096 recommended)"""

    docker_cpu_quota: int = 50000
    """Docker CPU quota in microseconds per 100 ms period (50000 = 50% of one core)"""

    docker_network_disabled: bool = True
    """Disable all network access inside the container (prevents data exfiltration)"""

    fallback_to_simulated: bool = False
    """Fall back to a lightweight simulated execution when Docker is unavailable.
    Only enable in development/testing — simulated execution does NOT provide
    any security guarantees."""


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
    
    ⚠️ SECURITY WARNING: This is a FOUNDATION implementation.
    Code execution is NOT sandboxed. DO NOT use in production environments
    or with untrusted code modifications.
    
    The Task Agent:
    1. Executes research tasks (literature search, experiment design, etc.)
    2. Has editable code that can be modified by Meta Agent
    3. Tracks performance metrics for evaluation
    4. Can be versioned and compared against variants
    
    TODO: Implement safe code execution with:
    - Sandboxing (docker, seccomp, etc.)
    - Resource limits (time, memory, CPU)
    - Import restrictions
    - Output validation
    
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
            # Execute task using current code
            # In production, this would exec/eval the editable code safely
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

        SECURITY FIX #1: Routes to Docker sandbox when available.  If
        ``DOCKER_AVAILABLE`` is False *and* ``fallback_to_simulated`` is
        enabled, falls back to a lightweight simulated path (development only).
        Raises NotImplementedError when neither option is available so callers
        never silently skip execution.
        """
        if not DOCKER_AVAILABLE:
            if self.task_config.fallback_to_simulated:
                logger.warning(
                    "Docker not available — falling back to simulated execution. "
                    "This provides NO security guarantees."
                )
                return await self._execute_simulated(task, self.task_config.max_execution_time)
            raise NotImplementedError(
                "TaskAgent._execute_task_code requires Docker (not found on PATH). "
                "Set fallback_to_simulated=True for development use, or install Docker. "
                "See berb/experiment/docker_sandbox.py for the production implementation."
            )

        return await self._execute_in_docker(task)

    async def _execute_in_docker(self, task: str) -> Any:
        """Execute the task agent code inside a Docker sandbox.

        Writes *self.code* plus a thin runner shim to a Docker container via
        :class:`berb.experiment.docker_sandbox.DockerSandbox`, captures stdout
        JSON, and converts it to a :class:`berb.hyperagent.base.TaskResult`.
        """
        import asyncio
        import json
        import tempfile
        from pathlib import Path

        from berb.config import DockerSandboxConfig
        from berb.experiment.docker_sandbox import DockerSandbox
        from berb.hyperagent.base import TaskResult

        # Build a self-contained runner that embeds the agent code and calls
        # execute_task(), then emits a JSON result line on stdout.
        agent_code_escaped = self.code.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        runner = (
            "import json, sys\n"
            "\n"
            "# --- agent code begin ---\n"
            f"{self.code}\n"
            "# --- agent code end ---\n"
            "\n"
            "try:\n"
            f"    _result = execute_task({json.dumps(task)})\n"
            "    if isinstance(_result, dict):\n"
            "        print(json.dumps(_result))\n"
            "    else:\n"
            "        print(json.dumps({'success': True, 'output': str(_result)}))\n"
            "except Exception as _exc:\n"
            "    print(json.dumps({'success': False, 'error': str(_exc)}))\n"
        )

        # Map TaskAgentConfig → DockerSandboxConfig (conservative network policy)
        sandbox_cfg = DockerSandboxConfig(
            image=self.task_config.docker_image,
            memory_limit_mb=self.task_config.docker_memory_mb,
            # Convert CPU quota (µs per 100ms period) to fractional cores
            cpu_limit=self.task_config.docker_cpu_quota / 100_000,
            network_policy="none" if self.task_config.docker_network_disabled else "setup_only",
            fallback_to_sandbox=False,
        )

        with tempfile.TemporaryDirectory(prefix="berb_taskagent_") as tmpdir:
            sandbox = DockerSandbox(config=sandbox_cfg, workdir=Path(tmpdir))
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: sandbox.run(runner, timeout_sec=self.task_config.max_execution_time),
            )

        if result.timed_out:
            return TaskResult(
                task_id=task,
                success=False,
                error=f"Execution timed out after {self.task_config.max_execution_time}s",
                metrics={"timeout": True},
            )

        if result.returncode != 0:
            return TaskResult(
                task_id=task,
                success=False,
                error=(result.stderr[:500] if result.stderr else f"exit code {result.returncode}"),
                metrics={"exit_code": float(result.returncode)},
            )

        # Parse the last JSON line from stdout
        stdout_lines = [l for l in result.stdout.splitlines() if l.strip().startswith("{")]
        if stdout_lines:
            try:
                output = json.loads(stdout_lines[-1])
                return TaskResult(
                    task_id=task,
                    success=output.get("success", True),
                    output=output,
                    error=output.get("error"),
                    metrics={k: float(v) for k, v in result.metrics.items()
                             if isinstance(v, (int, float))},
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: treat any stdout as raw output
        return TaskResult(
            task_id=task,
            success=True,
            output={"raw_output": result.stdout[:2000]},
            metrics={k: float(v) for k, v in result.metrics.items()
                     if isinstance(v, (int, float))},
        )

    async def _execute_simulated(self, task: str, timeout: int) -> Any:
        """Lightweight simulated execution for development / CI environments.

        SECURITY FIX #1: Only reachable when ``fallback_to_simulated=True``.
        Returns a stub TaskResult so the agent state machine can progress
        without real code execution.  Must NOT be used in production.
        """
        import asyncio
        from berb.hyperagent.base import TaskResult

        logger.debug("Simulated execution: task=%r timeout=%d", task, timeout)
        await asyncio.sleep(0)  # yield to event loop
        return TaskResult(
            task_id=task,
            success=True,
            output={"mode": "simulated", "task": task, "message": "Simulated execution (no Docker)"},
            metrics={"execution_time": 0.0, "simulated": True},
        )

    async def _execute_task_code_UNREACHABLE(self, task: str, **kwargs: Any) -> Any:
        """Dead code retained for reference only — not called."""
        from berb.hyperagent.base import TaskResult
        import asyncio

        timeout = self.task_config.max_execution_time

        try:
            async def execute_with_timeout():
                await asyncio.sleep(0.1)
                return TaskResult(
                    task_id=task,
                    success=True,
                    output={"message": f"Task '{task}' executed (placeholder)"},
                    metrics={"execution_time": 0.1},
                )

            result = await asyncio.wait_for(execute_with_timeout(), timeout=timeout)
            return result

        except asyncio.TimeoutError:
            logger.error("Task execution timeout exceeded: %ds", timeout)
            return TaskResult(
                task_id=task,
                success=False,
                error=f"Execution timeout after {timeout}s",
                metrics={"timeout": True},
            )
        except Exception as e:
            logger.error("Task execution failed: %s", e)
            return TaskResult(
                task_id=task,
                success=False,
                error=str(e),
            )
    
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

        SECURITY FIX #1: Extended validation to block network-capable imports
        and enforce a total code-size limit that prevents memory exhaustion
        when the validator itself processes the string.

        ⚠️ NOT production-ready — does not prevent all attack vectors.

        Validates:
        - Total code size (≤ 1 MB)
        - Syntax correctness
        - Dangerous import and call patterns (OS, network, subprocess, eval…)
        - Excessive single-line length (≥ 10 000 chars)
        - Unicode normalization (prevents homoglyph bypass)

        Returns:
            True if code passes all checks
        """
        try:
            # Guard against memory exhaustion from huge inputs BEFORE any
            # further processing — keep this check first.
            if len(code) > 1_000_000:  # 1 MB hard limit
                logger.warning("Code rejected: size %d bytes exceeds 1 MB limit", len(code))
                return False

            # Syntax check
            compile(code, "<string>", "exec")

            # Normalize unicode to prevent homoglyph / invisible-char bypass
            import unicodedata
            normalized = unicodedata.normalize("NFKC", code)

            # SECURITY FIX #1: Include network-capable imports in the block
            # list so Meta-Agent modifications cannot exfiltrate data or open
            # reverse shells even when the network is theoretically disabled at
            # the Docker layer.  Defence-in-depth.
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
                # Network-capable modules
                "import socket",
                "socket.socket(",
                "import urllib",
                "urllib.request",
                "urllib.urlopen",
                "import http.client",
                "import ftplib",
                "import smtplib",
                "import telnetlib",
                "import xmlrpc",
                "import paramiko",
                "import requests",
            ]

            for pattern in dangerous_patterns:
                if pattern in normalized:
                    logger.warning("Dangerous pattern detected: %s", pattern)
                    return False

            # Check for excessive line length (potential DoS via regex / syntax)
            if any(len(line) > 10000 for line in normalized.splitlines()):
                logger.warning("Excessive line length detected (potential DoS)")
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
            },
            "state": self.state.to_dict(),
            "code": self.code,
        }
