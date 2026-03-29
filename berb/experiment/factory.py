"""Factory for creating sandbox backends based on experiment config."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from berb.config import ExperimentConfig
from berb.experiment.sandbox import ExperimentSandbox, SandboxProtocol

if TYPE_CHECKING:
    from berb.experiment.agentic_sandbox import AgenticSandbox

logger = logging.getLogger(__name__)


def create_sandbox(config: ExperimentConfig, workdir: Path) -> SandboxProtocol:
    """Return the appropriate sandbox backend for *config.mode*.

    - ``"sandbox"`` → :class:`ExperimentSandbox` (subprocess)
    - ``"docker"``  → :class:`DockerSandbox`  (Docker container)

    P0 FIX: Automatic fallback to sandbox when Docker is unavailable.
    Controlled by `config.docker.fallback_to_sandbox` (default: True).
    """
    if config.mode == "docker":
        from berb.experiment.docker_sandbox import DockerSandbox

        docker_cfg = config.docker
        fallback_enabled = docker_cfg.fallback_to_sandbox

        # Check 1: Docker daemon availability
        if not DockerSandbox.check_docker_available():
            if fallback_enabled:
                logger.warning(
                    "Docker daemon is not reachable — "
                    "AUTOMATIC FALLBACK to subprocess sandbox. "
                    "To disable fallback, set docker.fallback_to_sandbox: false"
                )
                return ExperimentSandbox(config.sandbox, workdir)
            else:
                raise RuntimeError(
                    "Docker daemon is not reachable and fallback_to_sandbox is disabled. "
                    "Start Docker or enable fallback_to_sandbox: true"
                )

        # Check 2: Docker image availability
        if not DockerSandbox.ensure_image(docker_cfg.image):
            if fallback_enabled:
                logger.warning(
                    "Docker image '%s' not found locally — "
                    "AUTOMATIC FALLBACK to subprocess sandbox. "
                    "To use Docker, build the image: docker build -t %s berb/docker/",
                    docker_cfg.image,
                    docker_cfg.image,
                )
                return ExperimentSandbox(config.sandbox, workdir)
            else:
                raise RuntimeError(
                    f"Docker image '{docker_cfg.image}' not found locally and "
                    f"fallback_to_sandbox is disabled. "
                    f"Build it: docker build -t {docker_cfg.image} berb/docker/"
                )

        if docker_cfg.gpu_enabled:
            logger.info("Docker sandbox: GPU passthrough enabled")

        return DockerSandbox(docker_cfg, workdir)

    if config.mode == "ssh_remote":
        from berb.experiment.ssh_sandbox import SshRemoteSandbox

        ssh_cfg = config.ssh_remote
        if not ssh_cfg.host:
            raise RuntimeError(
                "ssh_remote mode requires experiment.ssh_remote.host in config."
            )

        ok, msg = SshRemoteSandbox.check_ssh_available(ssh_cfg)
        if not ok:
            raise RuntimeError(f"SSH connectivity check failed: {msg}")

        logger.info("SSH remote sandbox: %s", msg)
        return SshRemoteSandbox(ssh_cfg, workdir)

    if config.mode == "colab_drive":
        from berb.experiment.colab_sandbox import ColabDriveSandbox

        colab_cfg = config.colab_drive
        ok, msg = ColabDriveSandbox.check_drive_available(colab_cfg)
        if not ok:
            raise RuntimeError(f"Colab Drive check failed: {msg}")

        logger.info("Colab Drive sandbox: %s", msg)

        # Write worker template for user convenience
        worker_path = Path(colab_cfg.drive_root).expanduser() / "colab_worker.py"
        if not worker_path.exists():
            ColabDriveSandbox.write_worker_notebook(worker_path)
            logger.info(
                "Colab worker template written to %s — "
                "upload this to Colab and run it.",
                worker_path,
            )

        return ColabDriveSandbox(colab_cfg, workdir)

    if config.mode != "sandbox":
        raise RuntimeError(
            f"Unsupported experiment mode for create_sandbox(): {config.mode}"
        )

    return ExperimentSandbox(config.sandbox, workdir)


def create_agentic_sandbox(
    config: ExperimentConfig,
    workdir: Path,
    skills_dir: Path | None = None,
) -> "AgenticSandbox":  # noqa: F821
    """Return an :class:`AgenticSandbox` for agentic experiment mode.

    Validates that Docker is available before returning.
    """
    from berb.experiment.agentic_sandbox import AgenticSandbox

    if not AgenticSandbox.check_docker_available():
        raise RuntimeError(
            "Docker daemon is not reachable. "
            "Agentic mode requires Docker. Start Docker first."
        )

    agentic_cfg = config.agentic
    if agentic_cfg.gpu_enabled:
        logger.info("Agentic sandbox: GPU passthrough enabled")

    return AgenticSandbox(agentic_cfg, workdir, skills_dir=skills_dir)
