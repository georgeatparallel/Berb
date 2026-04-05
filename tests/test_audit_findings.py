"""Detection tests for verified audit findings.

These tests verify that specific bugs are present (will fail initially)
and can be used to verify fixes (will pass after fixes applied).
"""

import pytest
from pathlib import Path
import tempfile
import os


class TestAutoDebuggerDeadCode:
    """FINDING: auto_debugger.py:608 - f-string prompt never used."""

    def test_llm_generate_fix_uses_prompt(self):
        """Verify that _llm_generate_fix actually uses the prompt."""
        from berb.experiment.auto_debugger import AutomatedDebugger
        
        debugger = AutomatedDebugger(llm_client=None)  # type: ignore
        
        # Check source code for the bug
        import inspect
        source = inspect.getsource(debugger._llm_generate_fix)
        
        # The bug: f-string on line 608 is not assigned to any variable
        # After fix, the prompt should be assigned and used
        assert "prompt =" in source or "prompt=" in source, \
            "BUG: f-string prompt is built but never assigned to variable"


class TestAutoDebuggerDivisionByZero:
    """FINDING: auto_debugger.py:743 - Division by zero risk exists but is guarded at line 728."""

    def test_get_debugging_statistics_empty_history(self):
        """Verify that get_debugging_statistics handles empty fix_history."""
        from berb.experiment.auto_debugger import AutomatedDebugger
        
        debugger = AutomatedDebugger(llm_client=None)  # type: ignore
        
        # With empty history, should return error message, not raise
        stats = debugger.get_debugging_statistics()
        assert "error" in stats, "Should return error dict for empty history"


class TestOpenRouterAdapterContract:
    """FINDING: openrouter_adapter.py:363-370 - Missing LLMResponse fields."""

    def test_llm_response_has_all_fields(self):
        """Verify LLMResponse includes truncated and raw fields."""
        from berb.llm.client import LLMResponse
        import inspect
        
        sig = inspect.signature(LLMResponse.__init__)
        params = list(sig.parameters.keys())
        
        assert "truncated" in params, "LLMResponse missing 'truncated' field"
        assert "raw" in params, "LLMResponse missing 'raw' field"


class TestSandboxPathTraversal:
    """FINDING: sandbox.py - Path traversal protection via validate_entry_point_resolved."""

    def test_validate_entry_point_resolved_detects_symlink_escape(self, tmp_path: Path):
        """Verify that validate_entry_point_resolved catches symlink escapes."""
        from berb.experiment.sandbox import validate_entry_point_resolved
        
        # Create a symlink that points outside the staging area
        outside_file = tmp_path / "outside" / "secret.py"
        outside_file.parent.mkdir(parents=True)
        outside_file.write_text("# secret")
        
        staging = tmp_path / "staging"
        staging.mkdir()
        
        symlink_entry = staging / "entry.py"
        # Skip test on Windows if symlinks not supported
        try:
            symlink_entry.symlink_to(outside_file)
        except OSError:
            pytest.skip("Symlinks not supported on this system")
        
        # validate_entry_point_resolved should catch this
        result = validate_entry_point_resolved(staging, "entry.py")
        
        assert result is not None, \
            "BUG: validate_entry_point_resolved should detect symlink-based path traversal"


class TestSelfCorrectingResourceLeak:
    """FINDING: self_correcting.py:347 - Temp file not cleaned up on error paths."""

    def test_temp_file_cleanup_on_error(self, tmp_path: Path):
        """Verify temp files are cleaned up even when execution fails."""
        import asyncio
        from berb.experiment.self_correcting import SimulationExecutorAgent
        from berb.memory.shared_memory import SharedResearchMemory
        
        memory = SharedResearchMemory(project_id="test-project")
        executor = SimulationExecutorAgent(memory)
        
        # Track temp files before
        initial_files = set(Path(tempfile.gettempdir()).glob("*.py"))
        
        # Execute code that will fail (async)
        async def run_test():
            return await executor.execute("raise ValueError('test error')", timeout_sec=1)
        
        result = asyncio.run(run_test())
        
        # Check temp files after
        final_files = set(Path(tempfile.gettempdir()).glob("*.py"))
        new_files = final_files - initial_files
        
        # Cleanup any leaked files
        for f in new_files:
            try:
                f.unlink()
            except OSError:
                pass
        
        if new_files:
            pytest.fail(f"BUG: Temp files not cleaned up: {new_files}")


class TestComputeGuardDivisionByZero:
    """FINDING: compute_guard.py - Division by zero in success rate calculation."""

    def test_success_rate_with_empty_history(self):
        """Verify success_rate calculation handles empty fix_history."""
        # This test covers the same issue as TestAutoDebuggerDivisionByZero
        # since the code is in auto_debugger.py, not compute_guard.py
        pass
