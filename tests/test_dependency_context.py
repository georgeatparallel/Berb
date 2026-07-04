"""Unit tests for dependency context injection."""

import pytest
from berb.pipeline.dependency_context import (
    CompletedTask,
    DependencyContextBuilder,
    PipelineContextManager,
)


class TestCompletedTask:
    """Test CompletedTask dataclass."""

    def test_create_task(self):
        """Test creating a completed task."""
        task = CompletedTask(
            task_id="task_1",
            stage="CODE_GENERATION",
            code="print('hello')",
            imports=["numpy", "pandas"],
            classes=["MyClass"],
            functions=["my_function"],
        )

        assert task.task_id == "task_1"
        assert task.stage == "CODE_GENERATION"
        assert len(task.imports) == 2
        assert len(task.classes) == 1
        assert len(task.functions) == 1


class TestDependencyContextBuilder:
    """Test DependencyContextBuilder class."""

    def test_add_completed_task(self):
        """Test adding a completed task."""
        builder = DependencyContextBuilder()

        builder.add_completed_task(
            task_id="task_1",
            stage="CODE_GENERATION",
            code="import numpy\nclass MyClass:\n    pass",
            imports=["numpy"],
            classes=["MyClass"],
            functions=[],
        )

        task = builder.get_task("task_1")
        assert task is not None
        assert task.stage == "CODE_GENERATION"

    def test_get_all_completed(self):
        """Test getting all completed tasks."""
        builder = DependencyContextBuilder()

        builder.add_completed_task("task_1", "STAGE_1")
        builder.add_completed_task("task_2", "STAGE_2")
        builder.add_completed_task("task_3", "STAGE_3")

        tasks = builder.get_all_completed()
        assert len(tasks) == 3

    def test_build_context_for_task(self):
        """Test building context for a new task."""
        builder = DependencyContextBuilder()

        code1 = "import numpy\nclass DataProcessor:\n    pass"
        builder.add_completed_task(
            task_id="task_1",
            stage="CODE_GENERATION",
            code=code1,
            imports=["numpy"],
            classes=["DataProcessor"],
        )

        context = builder.build_context_for_task("task_2", dependencies=["task_1"])

        assert "Previously Generated Code" in context
        assert "DataProcessor" in context
        assert "numpy" in context
        assert "IMPORTANT" in context

    def test_build_context_empty_dependencies(self):
        """Test building context with no dependencies."""
        builder = DependencyContextBuilder()

        builder.add_completed_task("task_1", "STAGE_1")

        # When dependencies is empty list, auto-detect kicks in
        # and uses all completed tasks
        context = builder.build_context_for_task("task_2", dependencies=[])

        # Should have context from auto-detected dependencies
        assert "Previously Generated Code" in context
        assert "task_1" in context

    def test_build_context_missing_dependency(self):
        """Test building context with missing dependency."""
        builder = DependencyContextBuilder()

        builder.add_completed_task("task_1", "STAGE_1")

        # Reference non-existent task
        context = builder.build_context_for_task("task_2", dependencies=["task_999"])

        # Should return empty (missing deps are logged but not fatal)
        assert context == ""

    def test_context_length_limit(self):
        """Test context respects length limit."""
        builder = DependencyContextBuilder()

        # Add task with long code
        long_code = "x" * 5000
        builder.add_completed_task(
            task_id="task_1",
            stage="CODE_GENERATION",
            code=long_code,
        )

        context = builder.build_context_for_task(
            "task_2",
            dependencies=["task_1"],
            max_context_length=1000,
        )

        assert len(context) <= 1500  # Some overhead from headers

    def test_extract_imports_from_code(self):
        """Test extracting imports from code."""
        builder = DependencyContextBuilder()

        code = """
import numpy as np
from pandas import DataFrame
import os
from collections import defaultdict
"""

        imports = builder.get_imports_from_code(code)

        assert "numpy" in imports
        assert "pandas" in imports
        assert "os" in imports
        assert "collections" in imports

    def test_extract_classes_from_code(self):
        """Test extracting classes from code."""
        builder = DependencyContextBuilder()

        code = """
class MyClass:
    pass

class AnotherClass(BaseClass):
    def __init__(self):
        pass
"""

        classes = builder.get_classes_from_code(code)

        assert "MyClass" in classes
        assert "AnotherClass" in classes

    def test_extract_functions_from_code(self):
        """Test extracting functions from code."""
        builder = DependencyContextBuilder()

        code = """
def my_function():
    pass

def another_function(arg1, arg2):
    return arg1 + arg2
"""

        functions = builder.get_functions_from_code(code)

        assert "my_function" in functions
        assert "another_function" in functions


class TestPipelineContextManager:
    """Test PipelineContextManager class."""

    def test_record_task_completion(self):
        """Test recording task completion."""
        manager = PipelineContextManager()

        code = "import numpy\nclass Processor:\n    def run(self):\n        pass\ndef helper():\n    return True"

        manager.record_task_completion(
            task_id="task_1",
            stage="CODE_GENERATION",
            code=code,
        )

        summary = manager.get_summary()

        assert summary["total_tasks"] == 1
        assert summary["total_imports"] >= 1
        assert summary["total_classes"] >= 1
        assert summary["total_functions"] >= 1  # helper() is a top-level function

    def test_get_context_for_stage(self):
        """Test getting context for a stage."""
        manager = PipelineContextManager()

        # Record some tasks
        manager.record_task_completion("task_1", "CODE_GENERATION", "import numpy")
        manager.record_task_completion("task_2", "CODE_GENERATION", "import pandas")

        # Get context for code generation stage
        context = manager.get_context_for_stage("CODE_GENERATION", "task_3")

        assert context != ""
        assert "Previously Generated Code" in context

    def test_get_context_for_non_code_stage(self):
        """Test that non-code stages get empty context."""
        manager = PipelineContextManager()

        manager.record_task_completion("task_1", "CODE_GENERATION", "import numpy")

        # Non-code stages should get empty context
        context = manager.get_context_for_stage("LITERATURE_COLLECT", "task_2")

        assert context == ""

    def test_get_summary(self):
        """Test getting summary."""
        manager = PipelineContextManager()

        manager.record_task_completion("task_1", "CODE_GENERATION", "import numpy")
        manager.record_task_completion("task_2", "EXPERIMENT_RUN", "import pandas")
        manager.record_task_completion("task_3", "CODE_GENERATION", "import torch")

        summary = manager.get_summary()

        assert summary["total_tasks"] == 3
        assert "CODE_GENERATION" in summary["tasks_by_stage"]
        assert summary["tasks_by_stage"]["CODE_GENERATION"] == 2
