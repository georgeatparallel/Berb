"""Unit tests for TDD-first generation."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from berb.pipeline.tdd_generation import (
    TDDCodeGenerator,
    TDDResult,
    PytestRunner,
    get_tdd_generator,
)


class TestTDDResult:
    """Test TDDResult dataclass."""

    def test_create_result(self):
        """Test creating a TDD result."""
        result = TDDResult(
            tests="def test_x(): pass",
            implementation="def x(): pass",
            tests_pass=True,
            test_output="1 passed",
            iterations=1,
            test_count=1,
            passed_count=1,
        )

        assert result.tests_pass is True
        assert result.iterations == 1


class TestTDDCodeGenerator:
    """Test TDDCodeGenerator class."""

    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful TDD generation."""
        mock_client = AsyncMock()

        # Mock responses for each phase
        mock_client.chat.side_effect = [
            MagicMock(content="def test_x(): assert x() == 1"),  # Tests
            MagicMock(content="def x(): return 1"),  # Implementation
            MagicMock(content="def x(): return 1"),  # Repaired (if needed)
        ]

        generator = TDDCodeGenerator(mock_client)

        result = await generator.generate(requirement="Implement function x that returns 1")

        assert result.tests is not None
        assert result.implementation is not None
        assert result.iterations >= 1

    @pytest.mark.asyncio
    async def test_generate_with_repair(self):
        """Test TDD generation with repair iteration."""
        mock_client = AsyncMock()

        # Track call count
        call_count = [0]

        async def mock_chat(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(content="def test_x(): assert x() == 1")
            elif call_count[0] == 2:
                return MagicMock(content="def x(): return 0")  # Wrong impl
            else:
                return MagicMock(content="def x(): return 1")  # Fixed impl

        mock_client.chat.side_effect = mock_chat

        # Mock test runner
        mock_runner = AsyncMock()
        mock_runner.run.side_effect = [
            "1 failed",  # First run fails
            "1 passed",  # Second run passes
        ]

        generator = TDDCodeGenerator(
            mock_client,
            test_runner=mock_runner,
            max_iterations=2,
        )

        result = await generator.generate(requirement="Implement function x that returns 1")

        assert result.iterations == 2  # One repair iteration
        assert result.tests_pass is True

    @pytest.mark.asyncio
    async def test_generate_max_iterations(self):
        """Test TDD generation respects max iterations."""
        mock_client = AsyncMock()
        mock_client.chat.return_value = MagicMock(content="def x(): pass")

        # Mock test runner to always fail
        mock_runner = AsyncMock()
        mock_runner.run.return_value = "1 failed"

        generator = TDDCodeGenerator(
            mock_client,
            test_runner=mock_runner,
            max_iterations=2,
        )

        result = await generator.generate(requirement="Implement x")

        # Should stop after max iterations
        assert result.iterations == 3  # Initial + 2 retries
        assert result.tests_pass is False

    def test_parse_test_results_pytest_format(self):
        """Test parsing pytest output format."""
        mock_client = AsyncMock()
        generator = TDDCodeGenerator(mock_client)

        # Format: "X passed, Y failed"
        passed, total, output = generator._parse_test_results("2 passed, 1 failed")
        assert passed == 2
        assert total == 3

        # Format: "X passed"
        passed, total, output = generator._parse_test_results("5 passed")
        assert passed == 5
        assert total == 5

    def test_parse_test_results_generic_format(self):
        """Test parsing generic test output."""
        mock_client = AsyncMock()
        generator = TDDCodeGenerator(mock_client)

        output = "test_1 PASSED\ntest_2 FAILED\ntest_3 PASSED"
        passed, total, parsed = generator._parse_test_results(output)

        assert passed == 2
        assert total == 3

    def test_parse_test_results_no_failures(self):
        """Test parsing output with no failures."""
        mock_client = AsyncMock()
        generator = TDDCodeGenerator(mock_client)

        output = "All tests completed successfully"
        passed, total, parsed = generator._parse_test_results(output)

        assert passed == 1
        assert total == 1


class TestPytestRunner:
    """Test PytestRunner class."""

    @pytest.mark.asyncio
    async def test_run_valid_tests(self):
        """Test running valid tests."""
        # Spawns a nested `python -m pytest` subprocess; 10s is too tight
        # under a loaded machine (full plugin autoload + interpreter
        # startup), so use a generous margin.
        runner = PytestRunner(timeout=60)

        tests = """
def test_addition():
    assert 1 + 1 == 2
"""
        implementation = """
def add(a, b):
    return a + b
"""

        output = await runner.run(tests, implementation)

        assert "passed" in output.lower() or "PASSED" in output

    @pytest.mark.asyncio
    async def test_run_failing_tests(self):
        """Test running failing tests."""
        # Spawns a nested `python -m pytest` subprocess; 10s is too tight
        # under a loaded machine (full plugin autoload + interpreter
        # startup), so use a generous margin.
        runner = PytestRunner(timeout=60)

        tests = """
def test_failure():
    assert False, "This should fail"
"""
        implementation = """
def x(): pass
"""

        output = await runner.run(tests, implementation)

        assert "failed" in output.lower() or "FAILED" in output or "assert" in output


class TestGetTDDGenerator:
    """Test get_tdd_generator function."""

    def test_python_with_pytest(self):
        """Test getting Python TDD generator with pytest."""
        mock_client = AsyncMock()

        generator = get_tdd_generator(mock_client, language="python", use_pytest=True)

        assert generator._language == "python"
        assert generator._test_runner is not None
        assert isinstance(generator._test_runner, PytestRunner)

    def test_python_without_pytest(self):
        """Test getting Python TDD generator without pytest."""
        mock_client = AsyncMock()

        generator = get_tdd_generator(mock_client, language="python", use_pytest=False)

        assert generator._language == "python"
        assert generator._test_runner is None

    def test_other_language(self):
        """Test getting TDD generator for other languages."""
        mock_client = AsyncMock()

        generator = get_tdd_generator(mock_client, language="javascript")

        assert generator._language == "javascript"
        assert generator._test_runner is None  # No test runner for JS yet
