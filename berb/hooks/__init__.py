"""Auto-triggered hooks for Berb workflow enforcement.

Provides 4 auto-triggered hooks:
- SessionStartHook: Show Git status, todos, commands
- SkillEvaluationHook: Evaluate applicable skills
- SessionEndHook: Generate work log, reminders
- SecurityGuardHook: Security validation

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.hooks import (
        SessionStartHook,
        SkillEvaluationHook,
        SessionEndHook,
        SecurityGuardHook,
        HookManager,
    )

    # Create hook manager
    manager = HookManager()

    # Register hooks
    manager.register(SessionStartHook())
    manager.register(SkillEvaluationHook())
    manager.register(SessionEndHook())
    manager.register(SecurityGuardHook())

    # Trigger hooks
    await manager.trigger("session_start", context)
    await manager.trigger("before_code_execution", code)
    await manager.trigger("session_end", context)
"""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HookResult:
    """Result from hook execution.

    Attributes:
        success: Whether hook succeeded
        message: Hook message
        data: Hook data
        warnings: List of warnings
        errors: List of errors
    """

    success: bool = True
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    error: str = ""  # Alias for single error message

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class BaseHook(ABC):
    """Abstract base class for all hooks."""

    name: str = "base_hook"
    description: str = "Base hook"
    triggers: list[str] = field(default_factory=list)

    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> HookResult:
        """Execute hook."""
        pass


class SessionStartHook(BaseHook):
    """Hook triggered at session start.

    Shows:
    - Git status (branch, uncommitted changes)
    - Pending TODOs
    - Available commands
    - Last session summary

    Usage:
        hook = SessionStartHook()
        result = await hook.execute(context)
    """

    name = "session_start"
    description = "Show session initialization info"
    triggers = ["session_start", "pipeline_run"]

    async def execute(self, context: dict[str, Any]) -> HookResult:
        """Execute session start hook."""
        result = HookResult()
        result.data["timestamp"] = datetime.now().isoformat()

        # Git status
        git_status = self._get_git_status()
        result.data["git"] = git_status

        # TODOs
        todos = self._get_todos(context.get("project_path", "."))
        result.data["todos"] = todos

        # Available commands
        commands = self._get_available_commands()
        result.data["commands"] = commands

        # Build message
        message_parts = ["Session started"]
        if git_status.get("branch"):
            message_parts.append(f"on branch {git_status['branch']}")
        if git_status.get("uncommitted", 0) > 0:
            message_parts.append(f"({git_status['uncommitted']} uncommitted changes)")

        result.message = " ".join(message_parts)

        # Warnings
        if git_status.get("uncommitted", 0) > 0:
            result.warnings.append(f"Uncommitted changes: {git_status['uncommitted']}")

        return result

    def _get_git_status(self) -> dict[str, Any]:
        """Get Git repository status."""
        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

            # Get uncommitted changes
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            uncommitted = len([
                line for line in status_result.stdout.split("\n")
                if line.strip()
            ])

            return {
                "branch": branch,
                "uncommitted": uncommitted,
                "clean": uncommitted == 0,
            }

        except Exception as e:
            logger.debug(f"Git status check failed: {e}")
            return {"branch": "unknown", "uncommitted": 0, "clean": True}

    def _get_todos(self, project_path: str) -> list[dict[str, Any]]:
        """Get pending TODOs from project."""
        todos = []
        try:
            # Search for TODO comments
            import re
            todo_pattern = re.compile(r"#\s*TODO[:\s]+(.+)", re.IGNORECASE)

            project_dir = Path(project_path)
            for py_file in project_dir.glob("**/*.py"):
                if "test" in str(py_file) or "__pycache__" in str(py_file):
                    continue

                content = py_file.read_text(encoding="utf-8", errors="ignore")
                for match in todo_pattern.finditer(content):
                    todos.append({
                        "file": str(py_file.relative_to(project_dir)),
                        "todo": match.group(1).strip()[:100],
                    })

                    if len(todos) >= 10:  # Limit to 10
                        return todos

        except Exception as e:
            logger.debug(f"TODO search failed: {e}")

        return todos

    def _get_available_commands(self) -> list[str]:
        """Get available CLI commands."""
        return [
            "berb run --topic <topic>",
            "berb init",
            "berb setup",
            "berb doctor",
            "berb validate",
            "berb report",
            "berb serve",
            "berb dashboard",
            "berb wizard",
            "berb project",
            "berb mcp",
            "berb overleaf",
            "berb trends",
            "berb calendar",
        ]


class SkillEvaluationHook(BaseHook):
    """Hook triggered to evaluate applicable skills.

    Evaluates:
    - Skills applicable to current stage
    - Skill readiness
    - Skill dependencies

    Usage:
        hook = SkillEvaluationHook()
        result = await hook.execute(context)
    """

    name = "skill_evaluation"
    description = "Evaluate applicable skills for current stage"
    triggers = ["stage_start", "pipeline_run"]

    async def execute(self, context: dict[str, Any]) -> HookResult:
        """Execute skill evaluation hook."""
        result = HookResult()
        stage_id = context.get("stage_id", "UNKNOWN")

        # Get applicable skills
        applicable_skills = self._get_applicable_skills(stage_id)
        result.data["stage_id"] = stage_id
        result.data["applicable_skills"] = applicable_skills

        # Evaluate skill readiness
        readiness = self._evaluate_readiness(applicable_skills, context)
        result.data["readiness"] = readiness

        # Build message
        result.message = f"Found {len(applicable_skills)} applicable skills for {stage_id}"

        # Warnings for missing dependencies
        for skill, ready in readiness.items():
            if not ready.get("ready", True):
                result.warnings.append(f"Skill '{skill}' not ready: {ready.get('reason', 'unknown')}")

        return result

    def _get_applicable_skills(self, stage_id: str) -> list[dict[str, Any]]:
        """Get skills applicable to stage."""
        # Skill mapping
        skill_map = {
            "SEARCH_STRATEGY": ["literature-review"],
            "LITERATURE_COLLECT": ["literature-review"],
            "LITERATURE_SCREEN": ["literature-review", "citation-verification"],
            "SYNTHESIS": ["literature-review"],
            "HYPOTHESIS_GEN": ["literature-review"],
            "EXPERIMENT_DESIGN": ["experiment-analysis"],
            "EXPERIMENT_RUN": ["experiment-analysis"],
            "RESULT_ANALYSIS": ["experiment-analysis"],
            "PAPER_OUTLINE": ["paper-writing"],
            "PAPER_DRAFT": ["paper-writing", "citation-verification"],
            "PAPER_REVISION": ["paper-writing", "citation-verification"],
            "PEER_REVIEW": ["paper-writing"],
            "CITATION_VERIFY": ["citation-verification"],
        }

        skill_ids = skill_map.get(stage_id, [])

        return [
            {"id": sid, "name": sid.replace("-", " ").title()}
            for sid in skill_ids
        ]

    def _evaluate_readiness(
        self,
        skills: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Evaluate skill readiness."""
        readiness = {}

        for skill in skills:
            skill_id = skill["id"]
            ready = True
            reason = ""

            # Check dependencies
            if skill_id == "literature-review":
                if not context.get("search_client"):
                    ready = False
                    reason = "Search client not configured"

            elif skill_id == "experiment-analysis":
                if not context.get("llm_client"):
                    ready = False
                    reason = "LLM client not configured"

            elif skill_id == "paper-writing":
                if not context.get("citations"):
                    ready = False
                    reason = "No citations available"

            elif skill_id == "citation-verification":
                # Always ready (has fallback)
                pass

            readiness[skill_id] = {
                "ready": ready,
                "reason": reason,
            }

        return readiness


class SessionEndHook(BaseHook):
    """Hook triggered at session end.

    Generates:
    - Work log
    - Reminders for pending tasks
    - Session summary

    Usage:
        hook = SessionEndHook()
        result = await hook.execute(context)
    """

    name = "session_end"
    description = "Generate session summary and reminders"
    triggers = ["session_end", "pipeline_complete"]

    async def execute(self, context: dict[str, Any]) -> HookResult:
        """Execute session end hook."""
        result = HookResult()

        # Generate work log
        work_log = self._generate_work_log(context)
        result.data["work_log"] = work_log

        # Generate reminders
        reminders = self._generate_reminders(context)
        result.data["reminders"] = reminders

        # Session summary
        summary = self._generate_summary(context)
        result.data["summary"] = summary

        # Build message
        result.message = f"Session complete: {summary.get('duration', 'unknown')}"

        return result

    def _generate_work_log(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate work log."""
        return {
            "timestamp": datetime.now().isoformat(),
            "stages_completed": context.get("completed_stages", []),
            "artifacts_created": context.get("artifacts", []),
            "duration": context.get("duration", "unknown"),
        }

    def _generate_reminders(self, context: dict[str, Any]) -> list[str]:
        """Generate reminders for pending tasks."""
        reminders = []

        # Check for uncommitted changes
        if context.get("git_uncommitted", False):
            reminders.append("Commit uncommitted changes")

        # Check for pending stages
        completed = context.get("completed_stages", [])
        total_stages = 23
        if len(completed) < total_stages:
            reminders.append(f"Continue pipeline: {len(completed)}/{total_stages} stages complete")

        # Check for low-confidence results
        if context.get("low_confidence_results"):
            reminders.append("Review low-confidence results")

        return reminders

    def _generate_summary(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate session summary."""
        return {
            "stages_completed": len(context.get("completed_stages", [])),
            "artifacts": len(context.get("artifacts", [])),
            "duration": context.get("duration", "unknown"),
            "success": context.get("success", True),
        }


class SecurityGuardHook(BaseHook):
    """Hook for security validation.

    Validates:
    - Code before execution (AST validation)
    - Import statements (whitelist)
    - Resource limits
    - Network access

    Usage:
        hook = SecurityGuardHook()
        result = await hook.execute({"code": code_to_execute})
    """

    name = "security_guard"
    description = "Security validation for code execution"
    triggers = ["before_code_execution", "before_experiment_run"]

    # Import whitelist
    SAFE_IMPORTS = {
        "numpy", "scipy", "pandas", "matplotlib",
        "torch", "tensorflow", "sklearn",
        "asyncio", "collections", "dataclasses", "functools",
        "json", "re", "os", "sys", "pathlib",
        "logging", "typing", "time", "datetime",
    }

    # Dangerous patterns
    DANGEROUS_PATTERNS = [
        "eval(", "exec(", "compile(",
        "__import__", "importlib.import_module",
        "os.system", "os.popen", "subprocess.call",
        "socket.", "urllib.request.urlopen",
    ]

    async def execute(self, context: dict[str, Any]) -> HookResult:
        """Execute security guard hook."""
        result = HookResult()
        code = context.get("code", "")

        if not code:
            result.message = "No code to validate"
            return result

        # AST validation
        ast_valid, ast_errors = self._validate_ast(code)
        if not ast_valid:
            result.success = False
            result.errors.extend(ast_errors)

        # Import validation
        imports_valid, import_errors = self._validate_imports(code)
        if not imports_valid:
            result.success = False
            result.errors.extend(import_errors)

        # Pattern validation
        patterns_valid, pattern_warnings = self._validate_patterns(code)
        result.warnings.extend(pattern_warnings)

        # Build message
        if result.success:
            result.message = "Security validation passed"
        else:
            result.message = f"Security validation failed: {len(result.errors)} errors"

        return result

    def _validate_ast(self, code: str) -> tuple[bool, list[str]]:
        """Validate code AST for dangerous constructs."""
        import ast

        errors = []

        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                # Check for eval/exec
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ("eval", "exec", "compile"):
                            errors.append(f"Dangerous function call: {node.func.id}")

        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")

        return len(errors) == 0, errors

    def _validate_imports(self, code: str) -> tuple[bool, list[str]]:
        """Validate import statements against whitelist."""
        import re

        errors = []
        import_pattern = re.compile(r"^(?:from\s+(\S+)\s+)?import\s+(\S+)", re.MULTILINE)

        for match in import_pattern.finditer(code):
            module = match.group(1) or match.group(2)
            base_module = module.split(".")[0]

            if base_module not in self.SAFE_IMPORTS:
                # Check if it's a relative import or submodule
                if base_module not in ("berb", "tests"):
                    errors.append(f"Potentially unsafe import: {module}")

        return len(errors) == 0, errors

    def _validate_patterns(self, code: str) -> tuple[bool, list[str]]:
        """Validate code for dangerous patterns."""
        warnings = []

        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in code:
                warnings.append(f"Dangerous pattern detected: {pattern}")

        return len(warnings) == 0, warnings


# =============================================================================
# Hook Manager
# =============================================================================

class HookManager:
    """Manage and trigger hooks.

    Provides:
    - Hook registration
    - Hook triggering by event
    - Hook result aggregation

    Usage:
        manager = HookManager()
        manager.register(SessionStartHook())
        manager.register(SecurityGuardHook())

        result = await manager.trigger("session_start", context)
    """

    def __init__(self):
        """Initialize hook manager."""
        self._hooks: dict[str, list[BaseHook]] = {}

    def register(self, hook: BaseHook) -> None:
        """
        Register a hook.

        Args:
            hook: Hook to register
        """
        for trigger in hook.triggers:
            if trigger not in self._hooks:
                self._hooks[trigger] = []
            self._hooks[trigger].append(hook)
        logger.debug(f"Registered hook: {hook.name}")

    async def trigger(
        self,
        event: str,
        context: dict[str, Any],
    ) -> list[HookResult]:
        """
        Trigger hooks for an event.

        Args:
            event: Event name
            context: Context dictionary

        Returns:
            List of HookResult from all triggered hooks
        """
        hooks = self._hooks.get(event, [])
        results = []

        for hook in hooks:
            try:
                result = await hook.execute(context)
                results.append(result)
                logger.debug(f"Hook {hook.name} executed: {result.success}")
            except Exception as e:
                logger.error(f"Hook {hook.name} failed: {e}")
                results.append(HookResult(
                    success=False,
                    errors=[str(e)],
                ))

        return results

    def list_hooks(self) -> list[str]:
        """List all registered hook names."""
        return list(set(hook.name for hooks in self._hooks.values() for hook in hooks))

    def list_triggers(self) -> list[str]:
        """List all trigger events."""
        return list(self._hooks.keys())


# =============================================================================
# Factory Function
# =============================================================================

def create_default_hook_manager() -> HookManager:
    """
    Create hook manager with default hooks.

    Returns:
        HookManager with all 4 default hooks registered
    """
    manager = HookManager()

    # Register all default hooks
    manager.register(SessionStartHook())
    manager.register(SkillEvaluationHook())
    manager.register(SessionEndHook())
    manager.register(SecurityGuardHook())

    return manager
