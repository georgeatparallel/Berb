"""Tests for Phase 7: Auto-Triggered Hooks.

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from berb.hooks import (
    HookResult,
    BaseHook,
    SessionStartHook,
    SkillEvaluationHook,
    SessionEndHook,
    SecurityGuardHook,
    HookManager,
    create_default_hook_manager,
)


# ============== Hook Result Tests ==============

class TestHookResult:
    """Test HookResult dataclass."""

    def test_default_result(self):
        """Test default result."""
        result = HookResult()
        assert result.success is True
        assert result.message == ""
        assert result.data == {}
        assert result.warnings == []
        assert result.errors == []

    def test_to_dict(self):
        """Test result to_dict method."""
        result = HookResult(
            success=True,
            message="Test message",
            data={"key": "value"},
            warnings=["Warning 1"],
            errors=["Error 1"],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["message"] == "Test message"
        assert d["data"]["key"] == "value"
        assert len(d["warnings"]) == 1
        assert len(d["errors"]) == 1


# ============== Session Start Hook Tests ==============

class TestSessionStartHook:
    """Test SessionStartHook."""

    @pytest.mark.asyncio
    async def test_hook_initialization(self):
        """Test hook initialization."""
        hook = SessionStartHook()
        assert hook.name == "session_start"
        assert len(hook.triggers) > 0

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test hook execution."""
        hook = SessionStartHook()
        context = {"project_path": "."}
        result = await hook.execute(context)

        assert result.success is True
        assert "timestamp" in result.data
        assert "git" in result.data
        assert "commands" in result.data

    @pytest.mark.asyncio
    async def test_git_status(self):
        """Test Git status detection."""
        hook = SessionStartHook()
        git_status = hook._get_git_status()

        assert "branch" in git_status
        assert "uncommitted" in git_status
        assert "clean" in git_status

    @pytest.mark.asyncio
    async def test_get_todos(self):
        """Test TODO detection."""
        hook = SessionStartHook()
        todos = hook._get_todos(".")

        assert isinstance(todos, list)
        # May be empty if no TODOs in project

    @pytest.mark.asyncio
    async def test_get_commands(self):
        """Test command list."""
        hook = SessionStartHook()
        commands = hook._get_available_commands()

        assert len(commands) > 0
        assert "berb run" in commands[0]


# ============== Skill Evaluation Hook Tests ==============

class TestSkillEvaluationHook:
    """Test SkillEvaluationHook."""

    @pytest.mark.asyncio
    async def test_hook_initialization(self):
        """Test hook initialization."""
        hook = SkillEvaluationHook()
        assert hook.name == "skill_evaluation"

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test hook execution."""
        hook = SkillEvaluationHook()
        context = {
            "stage_id": "LITERATURE_SCREEN",
            "search_client": Mock(),
            "llm_client": Mock(),
        }
        result = await hook.execute(context)

        assert result.success is True
        assert "applicable_skills" in result.data
        assert "readiness" in result.data

    @pytest.mark.asyncio
    async def test_get_applicable_skills(self):
        """Test skill mapping."""
        hook = SkillEvaluationHook()

        # Test different stages
        skills = hook._get_applicable_skills("LITERATURE_SCREEN")
        assert len(skills) >= 1

        skills = hook._get_applicable_skills("EXPERIMENT_RUN")
        assert len(skills) >= 1

        skills = hook._get_applicable_skills("PAPER_DRAFT")
        assert len(skills) >= 1

    @pytest.mark.asyncio
    async def test_evaluate_readiness(self):
        """Test readiness evaluation."""
        hook = SkillEvaluationHook()
        skills = [{"id": "literature-review", "name": "Literature Review"}]
        context = {"search_client": Mock()}

        readiness = hook._evaluate_readiness(skills, context)

        assert "literature-review" in readiness
        assert readiness["literature-review"]["ready"] is True

    @pytest.mark.asyncio
    async def test_evaluate_readiness_missing_deps(self):
        """Test readiness with missing dependencies."""
        hook = SkillEvaluationHook()
        skills = [{"id": "literature-review", "name": "Literature Review"}]
        context = {}  # No search_client

        readiness = hook._evaluate_readiness(skills, context)

        assert readiness["literature-review"]["ready"] is False


# ============== Session End Hook Tests ==============

class TestSessionEndHook:
    """Test SessionEndHook."""

    @pytest.mark.asyncio
    async def test_hook_initialization(self):
        """Test hook initialization."""
        hook = SessionEndHook()
        assert hook.name == "session_end"

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test hook execution."""
        hook = SessionEndHook()
        context = {
            "completed_stages": ["stage1", "stage2"],
            "artifacts": ["artifact1"],
            "duration": "1h 30m",
            "success": True,
        }
        result = await hook.execute(context)

        assert result.success is True
        assert "work_log" in result.data
        assert "reminders" in result.data
        assert "summary" in result.data

    @pytest.mark.asyncio
    async def test_generate_work_log(self):
        """Test work log generation."""
        hook = SessionEndHook()
        context = {"completed_stages": ["stage1"]}
        log = hook._generate_work_log(context)

        assert "timestamp" in log
        assert "stages_completed" in log

    @pytest.mark.asyncio
    async def test_generate_reminders(self):
        """Test reminder generation."""
        hook = SessionEndHook()
        context = {
            "completed_stages": ["stage1"],  # Less than 23
            "git_uncommitted": True,
        }
        reminders = hook._generate_reminders(context)

        assert len(reminders) >= 1

    @pytest.mark.asyncio
    async def test_generate_summary(self):
        """Test summary generation."""
        hook = SessionEndHook()
        context = {
            "completed_stages": ["stage1", "stage2"],
            "artifacts": ["artifact1", "artifact2"],
        }
        summary = hook._generate_summary(context)

        assert "stages_completed" in summary
        assert "artifacts" in summary


# ============== Security Guard Hook Tests ==============

class TestSecurityGuardHook:
    """Test SecurityGuardHook."""

    @pytest.mark.asyncio
    async def test_hook_initialization(self):
        """Test hook initialization."""
        hook = SecurityGuardHook()
        assert hook.name == "security_guard"
        assert len(hook.SAFE_IMPORTS) > 0
        assert len(hook.DANGEROUS_PATTERNS) > 0

    @pytest.mark.asyncio
    async def test_execute_safe_code(self):
        """Test validation of safe code."""
        hook = SecurityGuardHook()
        code = """
import numpy as np
from collections import defaultdict

def test():
    return np.array([1, 2, 3])
"""
        context = {"code": code}
        result = await hook.execute(context)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_dangerous_code(self):
        """Test validation of dangerous code."""
        hook = SecurityGuardHook()
        code = """
import os
result = eval("1 + 1")
os.system("ls")
"""
        context = {"code": code}
        result = await hook.execute(context)

        assert result.success is False
        assert len(result.errors) > 0 or len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_validate_ast(self):
        """Test AST validation."""
        hook = SecurityGuardHook()

        # Safe code
        valid, errors = hook._validate_ast("x = 1 + 1")
        assert valid is True
        assert len(errors) == 0

        # Dangerous code
        valid, errors = hook._validate_ast("eval('1+1')")
        assert valid is False
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_validate_imports(self):
        """Test import validation."""
        hook = SecurityGuardHook()

        # Safe imports
        valid, errors = hook._validate_imports("import numpy as np")
        assert valid is True

        # Potentially unsafe imports
        valid, errors = hook._validate_imports("import socket")
        assert valid is False or len(errors) > 0

    @pytest.mark.asyncio
    async def test_validate_patterns(self):
        """Test pattern validation."""
        hook = SecurityGuardHook()

        # Safe code
        valid, warnings = hook._validate_patterns("x = 1 + 1")
        assert valid is True
        assert len(warnings) == 0

        # Dangerous patterns
        valid, warnings = hook._validate_patterns("os.system('ls')")
        assert len(warnings) > 0


# ============== Hook Manager Tests ==============

class TestHookManager:
    """Test HookManager."""

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = HookManager()
        assert len(manager.list_hooks()) == 0
        assert len(manager.list_triggers()) == 0

    def test_register_hook(self):
        """Test hook registration."""
        manager = HookManager()
        hook = SessionStartHook()
        manager.register(hook)

        hooks = manager.list_hooks()
        assert "session_start" in hooks

        triggers = manager.list_triggers()
        assert "session_start" in triggers

    @pytest.mark.asyncio
    async def test_trigger_hooks(self):
        """Test triggering hooks."""
        manager = HookManager()
        manager.register(SessionStartHook())

        context = {"project_path": "."}
        results = await manager.trigger("session_start", context)

        assert len(results) > 0
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_trigger_no_hooks(self):
        """Test triggering with no registered hooks."""
        manager = HookManager()
        results = await manager.trigger("unknown_event", {})

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_trigger_hook_failure(self):
        """Test triggering hook that fails."""
        manager = HookManager()

        # Create a failing hook
        class FailingHook(BaseHook):
            name = "failing"
            triggers = ["test"]

            async def execute(self, context):
                raise Exception("Test failure")

        manager.register(FailingHook())
        results = await manager.trigger("test", {})

        assert len(results) == 1
        assert results[0].success is False


# ============== Factory Function Tests ==============

class TestCreateDefaultHookManager:
    """Test create_default_hook_manager."""

    def test_create_default_manager(self):
        """Test creating default hook manager."""
        manager = create_default_hook_manager()

        hooks = manager.list_hooks()
        assert len(hooks) == 4  # All 4 default hooks

        assert "session_start" in hooks
        assert "skill_evaluation" in hooks
        assert "session_end" in hooks
        assert "security_guard" in hooks

    @pytest.mark.asyncio
    async def test_default_manager_triggers(self):
        """Test default manager can trigger all hooks."""
        manager = create_default_hook_manager()

        # Test session_start
        results = await manager.trigger("session_start", {"project_path": "."})
        assert len(results) >= 1

        # Test stage_start
        results = await manager.trigger("stage_start", {"stage_id": "TEST"})
        assert len(results) >= 1

        # Test before_code_execution
        results = await manager.trigger("before_code_execution", {"code": "x = 1"})
        assert len(results) >= 1


# ============== Integration Tests ==============

class TestHooksIntegration:
    """Test hooks integration."""

    def test_import_hooks(self):
        """Test hooks can be imported."""
        from berb.hooks import (
            SessionStartHook,
            SkillEvaluationHook,
            SessionEndHook,
            SecurityGuardHook,
        )
        assert SessionStartHook is not None
        assert SkillEvaluationHook is not None
        assert SessionEndHook is not None
        assert SecurityGuardHook is not None

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete hook workflow."""
        manager = create_default_hook_manager()

        # Session start
        context = {"project_path": "."}
        results = await manager.trigger("session_start", context)
        assert all(r.success for r in results)

        # Stage start
        context["stage_id"] = "LITERATURE_SCREEN"
        results = await manager.trigger("stage_start", context)
        assert all(r.success for r in results)

        # Security check
        context["code"] = "import numpy as np\nx = np.array([1, 2, 3])"
        results = await manager.trigger("before_code_execution", context)
        assert all(r.success for r in results)

        # Session end
        context["completed_stages"] = ["stage1"]
        context["duration"] = "30m"
        results = await manager.trigger("session_end", context)
        assert all(r.success for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
