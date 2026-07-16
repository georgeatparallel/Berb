"""Unit tests for headless runners and CLI command handlers for external applications."""

from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from berb.commands.external_runners import (
    cmd_run_orchestrator,
    cmd_run_reasoner,
    run_orchestrator_headless,
    run_reasoner_headless,
)


@pytest.fixture
def mock_sub_run():
    """Mock subprocess.run."""
    with patch("subprocess.run") as mock:
        yield mock


class TestReasonerHeadlessRunner:
    """Test run_reasoner_headless function."""

    def test_run_reasoner_missing_dir(self):
        """Should raise FileNotFoundError when repository directory doesn't exist."""
        with pytest.raises(FileNotFoundError):
            run_reasoner_headless(
                problem="Test problem",
                reasoner_dir="/non/existent/path",
            )

    @patch("pathlib.Path.exists")
    def test_run_reasoner_success(self, mock_exists, mock_sub_run):
        """Should run successfully when main.py exists and returns 0."""
        # Mock directory structure existence
        mock_exists.side_effect = lambda: True

        # Mock successful subprocess result
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Execution successful"
        mock_res.stderr = ""
        mock_sub_run.return_value = mock_res

        result = run_reasoner_headless(
            problem="Test problem",
            preset="test-preset",
            reasoner_dir="/some/path",
            sequential=True,
            quiet=True,
        )

        assert result["status"] == "success"
        assert result["returncode"] == 0
        assert result["stdout"] == "Execution successful"
        assert result["stderr"] == ""
        assert result["data"] is None

        # Verify command arguments
        called_args = mock_sub_run.call_args[0][0]
        assert "main.py" in called_args[1]
        assert "--problem" in called_args
        assert "Test problem" in called_args
        assert "--preset" in called_args
        assert "test-preset" in called_args
        assert "--sequential" in called_args
        assert "--quiet" in called_args

    @patch("pathlib.Path.exists")
    def test_run_reasoner_failure(self, mock_exists, mock_sub_run):
        """Should return failed status when return code is non-zero."""
        mock_exists.side_effect = lambda: True

        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = ""
        mock_res.stderr = "Execution failed"
        mock_sub_run.return_value = mock_res

        result = run_reasoner_headless(
            problem="Test problem",
            reasoner_dir="/some/path",
        )

        assert result["status"] == "failed"
        assert result["returncode"] == 1
        assert result["stderr"] == "Execution failed"

    @patch("pathlib.Path.exists")
    def test_run_reasoner_with_output_parsing(self, mock_exists, mock_sub_run):
        """Should parse JSON output if output_path is provided and file exists."""
        mock_exists.side_effect = lambda: True

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Output exported"
        mock_res.stderr = ""
        mock_sub_run.return_value = mock_res

        json_data = {"status": "complete", "result": "42"}

        # Patch open to return custom JSON data
        with patch("builtins.open", mock_open(read_data=json.dumps(json_data))):
            result = run_reasoner_headless(
                problem="Test problem",
                output_path="/tmp/output.json",
                reasoner_dir="/some/path",
            )

        assert result["status"] == "success"
        assert result["data"] == json_data


class TestOrchestratorHeadlessRunner:
    """Test run_orchestrator_headless function."""

    def test_run_orchestrator_missing_dir(self):
        """Should raise FileNotFoundError when repository directory doesn't exist."""
        with pytest.raises(FileNotFoundError):
            run_orchestrator_headless(
                project="Test project",
                orchestrator_dir="/non/existent/path",
            )

    @patch("pathlib.Path.exists")
    def test_run_orchestrator_success(self, mock_exists, mock_sub_run):
        """Should execute the orchestrator with correct arguments."""
        mock_exists.side_effect = lambda: True

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Project built"
        mock_res.stderr = ""
        mock_sub_run.return_value = mock_res

        result = run_orchestrator_headless(
            project="Test project",
            budget=10.0,
            output_dir="/tmp/out",
            orchestrator_dir="/some/path",
            quiet=True,
        )

        assert result["status"] == "success"
        assert result["returncode"] == 0
        assert result["stdout"] == "Project built"

        called_args = mock_sub_run.call_args[0][0]
        assert "orchestrator.cli" in called_args
        assert "build" in called_args
        assert "--project" in called_args
        assert "Test project" in called_args
        assert "--budget" in called_args
        assert "10.0" in called_args
        assert "--output-dir" in called_args
        assert "--quiet" in called_args


class TestCLICommandHandlers:
    """Test cmd_run_reasoner and cmd_run_orchestrator command handlers."""

    @patch("berb.commands.external_runners.run_reasoner_headless")
    def test_cmd_run_reasoner_success(self, mock_run):
        """cmd_run_reasoner should print success message and return 0 on success."""
        mock_run.return_value = {
            "status": "success",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "data": None,
        }

        args = argparse.Namespace(
            problem="Test problem",
            preset="multi-perspective-budget",
            output="/tmp/out.json",
            path="/some/path",
            sequential=False,
            quiet=False,
        )

        exit_code = cmd_run_reasoner(args)
        assert exit_code == 0
        mock_run.assert_called_once_with(
            problem="Test problem",
            preset="multi-perspective-budget",
            output_path="/tmp/out.json",
            reasoner_dir="/some/path",
            sequential=False,
            quiet=False,
        )

    @patch("berb.commands.external_runners.run_reasoner_headless")
    def test_cmd_run_reasoner_failure(self, mock_run):
        """cmd_run_reasoner should print failure details and return the error code on failure."""
        mock_run.return_value = {
            "status": "failed",
            "returncode": 5,
            "stdout": "Command failed",
            "stderr": "Access denied",
            "data": None,
        }

        args = argparse.Namespace(
            problem="Test problem",
            preset="multi-perspective-budget",
            output=None,
            path="/some/path",
            sequential=False,
            quiet=False,
        )

        exit_code = cmd_run_reasoner(args)
        assert exit_code == 5

    @patch("berb.commands.external_runners.run_orchestrator_headless")
    def test_cmd_run_orchestrator_success(self, mock_run):
        """cmd_run_orchestrator should return 0 on success."""
        mock_run.return_value = {
            "status": "success",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

        args = argparse.Namespace(
            project="Test project",
            budget=5.0,
            output_dir="/tmp/out",
            path="/some/path",
            quiet=True,
        )

        exit_code = cmd_run_orchestrator(args)
        assert exit_code == 0
        mock_run.assert_called_once_with(
            project="Test project",
            budget=5.0,
            output_dir="/tmp/out",
            orchestrator_dir="/some/path",
            quiet=True,
        )
