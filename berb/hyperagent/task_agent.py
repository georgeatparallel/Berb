"""Task Agent for HyperAgent.

The Task Agent solves research tasks using an editable program.
It can be modified by the Meta Agent to improve performance.

Based on Facebook AI Research paper (arXiv:2603.19461v1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from berb.config import RCConfig

logger = logging.getLogger(__name__)


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
        
        FIX-002a: Basic execution with timeout protection.
        ⚠️ NOT production-ready — lacks full sandboxing.
        
        TODO: Implement safe code execution with:
        - Sandboxing (docker, seccomp, etc.)
        - Resource limits (time, memory, CPU)
        - Import restrictions
        - Output validation
        """
        from berb.hyperagent.base import TaskResult
        import asyncio
        
        # FIX-002a: Add execution timeout to prevent resource exhaustion
        timeout = self.task_config.max_execution_time
        
        try:
            # Execute with timeout
            # In production, this would safely execute the editable code
            # For now, we use a simplified approach with timeout protection
            async def execute_with_timeout():
                # Placeholder implementation
                # TODO: Replace with actual code execution in sandbox
                await asyncio.sleep(0.1)  # Simulate execution
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
        
        FIX-002a: Basic validation for development use.
        ⚠️ NOT production-ready — does not prevent all attack vectors.
        
        Validates:
        - Syntax correctness
        - Dangerous import patterns
        - Dangerous function calls (eval, exec)
        - Unicode normalization
        
        Returns:
            True if code passes basic validation
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
            ]
            
            for pattern in dangerous_patterns:
                if pattern in normalized:
                    logger.warning("Dangerous pattern detected: %s", pattern)
                    return False
            
            # Check for excessive line length (potential DoS)
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
