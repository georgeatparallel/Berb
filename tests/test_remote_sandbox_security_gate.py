"""Defect-hunt Pass 1 finding D1 (tasks/defect_hunt/pass-01-sandbox-boundary.md).

check_code_security() is documented in sandbox.py as "the single enforcement
point for every sandbox backend — each run()/run_project() implementation
calls this before spawning a subprocess". ExperimentSandbox and DockerSandbox
honor that (tests/test_sandbox_security_gate.py). SshRemoteSandbox and
ColabDriveSandbox did not: both staged and executed/uploaded code with no AST
scan at all. SSH mode runs it on a real remote host with real credentials;
Colab mode runs it via a bare, unsandboxed `subprocess.run` in the worker
notebook (COLAB_WORKER_TEMPLATE) — the weakest isolation of any backend.

These tests pin the fix: malicious code must be rejected before either
backend's network-touching step (_execute / _submit_and_wait) is ever called.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from berb.config import ColabDriveConfig, SshRemoteConfig
from berb.experiment.colab_sandbox import ColabDriveSandbox
from berb.experiment.ssh_sandbox import SshRemoteSandbox

_MALICIOUS = "import os\nos.system('rm -rf /')"
_SAFE = "print('hello')"


def _ssh_sandbox(tmp_path: Path) -> SshRemoteSandbox:
    return SshRemoteSandbox(SshRemoteConfig(host="test-host"), tmp_path / "work")


def _colab_sandbox(tmp_path: Path) -> ColabDriveSandbox:
    drive = tmp_path / "drive"
    drive.mkdir()
    return ColabDriveSandbox(ColabDriveConfig(drive_root=str(drive)), tmp_path / "work")


class TestSshSandboxSecurityGate:
    @patch.object(SshRemoteSandbox, "_execute")
    def test_run_rejects_malicious_code_without_touching_the_remote_host(
        self, mock_execute, tmp_path: Path
    ):
        sandbox = _ssh_sandbox(tmp_path)
        result = sandbox.run(_MALICIOUS)

        assert result.returncode == -1
        assert "security validation" in result.stderr.lower()
        assert result.rejected_reason is not None
        mock_execute.assert_not_called()

    @patch.object(SshRemoteSandbox, "_execute")
    def test_run_allows_safe_code(self, mock_execute, tmp_path: Path):
        from berb.experiment.sandbox import SandboxResult

        mock_execute.return_value = SandboxResult(
            returncode=0, stdout="ok\n", stderr="", elapsed_sec=0.1, metrics={}
        )
        result = _ssh_sandbox(tmp_path).run(_SAFE)

        assert result.returncode == 0
        mock_execute.assert_called_once()

    @patch.object(SshRemoteSandbox, "_execute")
    def test_run_project_rejects_a_malicious_file_without_touching_the_remote_host(
        self, mock_execute, tmp_path: Path
    ):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_MALICIOUS, encoding="utf-8")

        sandbox = _ssh_sandbox(tmp_path)
        result = sandbox.run_project(project_dir)

        assert result.returncode == -1
        assert "security validation" in result.stderr.lower()
        mock_execute.assert_not_called()

    @patch.object(SshRemoteSandbox, "_execute")
    def test_run_project_scans_every_file_not_just_the_entry_point(
        self, mock_execute, tmp_path: Path
    ):
        """A malicious helper module must be caught even if main.py is clean."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")
        (project_dir / "helper.py").write_text(_MALICIOUS, encoding="utf-8")

        result = _ssh_sandbox(tmp_path).run_project(project_dir)

        assert result.returncode == -1
        mock_execute.assert_not_called()

    @patch.object(SshRemoteSandbox, "_execute")
    def test_run_project_allows_a_safe_project(self, mock_execute, tmp_path: Path):
        from berb.experiment.sandbox import SandboxResult

        mock_execute.return_value = SandboxResult(
            returncode=0, stdout="ok\n", stderr="", elapsed_sec=0.1, metrics={}
        )
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")

        result = _ssh_sandbox(tmp_path).run_project(project_dir)

        assert result.returncode == 0
        mock_execute.assert_called_once()

    def test_entry_point_validation_still_runs_before_the_security_scan(self, tmp_path: Path):
        """No-regression: the pre-existing path-traversal guard is unaffected."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")

        result = _ssh_sandbox(tmp_path).run_project(project_dir, entry_point="../../etc/passwd")

        assert result.returncode == -1
        assert result.rejected_reason is None  # entry-point error, not a security rejection


class TestColabSandboxSecurityGate:
    @patch.object(ColabDriveSandbox, "_submit_and_wait")
    def test_run_rejects_malicious_code_without_writing_to_drive(self, mock_submit, tmp_path: Path):
        sandbox = _colab_sandbox(tmp_path)
        result = sandbox.run(_MALICIOUS)

        assert result.returncode == -1
        assert "security validation" in result.stderr.lower()
        assert result.rejected_reason is not None
        mock_submit.assert_not_called()

    @patch.object(ColabDriveSandbox, "_submit_and_wait")
    def test_run_allows_safe_code(self, mock_submit, tmp_path: Path):
        from berb.experiment.sandbox import SandboxResult

        mock_submit.return_value = SandboxResult(
            returncode=0, stdout="ok\n", stderr="", elapsed_sec=0.1, metrics={}
        )
        result = _colab_sandbox(tmp_path).run(_SAFE)

        assert result.returncode == 0
        mock_submit.assert_called_once()

    @patch.object(ColabDriveSandbox, "_submit_and_wait")
    def test_run_project_rejects_a_malicious_file_without_writing_to_drive(
        self, mock_submit, tmp_path: Path
    ):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_MALICIOUS, encoding="utf-8")

        result = _colab_sandbox(tmp_path).run_project(project_dir)

        assert result.returncode == -1
        assert "security validation" in result.stderr.lower()
        mock_submit.assert_not_called()

    @patch.object(ColabDriveSandbox, "_submit_and_wait")
    def test_run_project_scans_every_file_not_just_the_entry_point(
        self, mock_submit, tmp_path: Path
    ):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")
        (project_dir / "helper.py").write_text(_MALICIOUS, encoding="utf-8")

        result = _colab_sandbox(tmp_path).run_project(project_dir)

        assert result.returncode == -1
        mock_submit.assert_not_called()

    @patch.object(ColabDriveSandbox, "_submit_and_wait")
    def test_run_project_allows_a_safe_project(self, mock_submit, tmp_path: Path):
        from berb.experiment.sandbox import SandboxResult

        mock_submit.return_value = SandboxResult(
            returncode=0, stdout="ok\n", stderr="", elapsed_sec=0.1, metrics={}
        )
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")

        result = _colab_sandbox(tmp_path).run_project(project_dir)

        assert result.returncode == 0
        mock_submit.assert_called_once()

    def test_entry_point_validation_still_runs_before_the_security_scan(self, tmp_path: Path):
        """No-regression: the pre-existing (BUG-DA8-07) path-traversal guard is unaffected."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")

        result = _colab_sandbox(tmp_path).run_project(project_dir, entry_point="../../etc/passwd")

        assert result.returncode == -1
        assert result.rejected_reason is None
