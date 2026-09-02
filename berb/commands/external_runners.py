"""Headless runners and CLI command handlers for Reasoner and AI Orchestrator.

Provides programmatic Python helpers and CLI command integrations to run both external
repositories headlessly.

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_REASONER_DIR = r"E:\Documents\Vibe-Coding\Reasoner"
DEFAULT_ORCHESTRATOR_DIR = r"E:\Documents\Vibe-Coding\Ai Orchestrator"


# =============================================================================
# Programmatic API Helpers (Headless Methods)
# =============================================================================


def run_reasoner_headless(
    problem: str,
    preset: str = "multi-perspective-budget",
    output_path: str | Path | None = None,
    reasoner_dir: str | Path = DEFAULT_REASONER_DIR,
    sequential: bool = False,
    quiet: bool = False,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Execute the Reasoner application headlessly inside its repository.

    Args:
        problem: The problem statement to solve.
        preset: Named routing preset.
        output_path: Optional path to export the full pipeline state JSON.
        reasoner_dir: Path to the Reasoner repository.
        sequential: Whether to run perspectives sequentially.
        quiet: Whether to suppress phase-by-phase logging.
        extra_args: Additional arbitrary arguments to pass to the CLI.

    Returns:
        A dictionary containing "status" ("success" or "failed"), "returncode",
        "stdout", "stderr", and "data" (the parsed JSON output if output_path was used).
    """
    reasoner_path = Path(reasoner_dir).resolve()
    if not reasoner_path.exists() or not (reasoner_path / "main.py").exists():
        raise FileNotFoundError(f"Reasoner repository or main.py not found at: {reasoner_path}")

    cmd = [sys.executable, "main.py", "--problem", problem, "--preset", preset]

    if output_path:
        cmd.extend(["--output", str(Path(output_path).resolve())])
    if sequential:
        cmd.append("--sequential")
    if quiet:
        cmd.append("--quiet")
    if extra_args:
        cmd.extend(extra_args)

    logger.info(f"Running Reasoner headlessly: {' '.join(cmd)} (cwd={reasoner_path})")

    # Inherit full environment (including API keys)
    res = subprocess.run(
        cmd,
        cwd=str(reasoner_path),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    result_dict = {
        "status": "success" if res.returncode == 0 else "failed",
        "returncode": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "data": None,
    }

    if res.returncode == 0 and output_path:
        out_p = Path(output_path).resolve()
        if out_p.exists():
            try:
                with open(out_p, encoding="utf-8") as f:
                    result_dict["data"] = json.load(f)
            except Exception as e:
                logger.error(f"Failed to parse Reasoner JSON output: {e}")

    return result_dict


def run_orchestrator_headless(
    project: str,
    budget: float = 8.0,
    output_dir: str | Path | None = None,
    orchestrator_dir: str | Path = DEFAULT_ORCHESTRATOR_DIR,
    quiet: bool = False,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Execute the AI Orchestrator build pipeline headlessly.

    Args:
        project: Project description or user intent.
        budget: Max budget in USD.
        output_dir: Optional directory to write structured output files.
        orchestrator_dir: Path to the AI Orchestrator repository.
        quiet: Whether to suppress progress outputs.
        extra_args: Additional arbitrary arguments to pass to the CLI.

    Returns:
        A dictionary containing "status" ("success" or "failed"), "returncode",
        "stdout", and "stderr".
    """
    orch_path = Path(orchestrator_dir).resolve()
    if not orch_path.exists():
        raise FileNotFoundError(f"AI Orchestrator repository not found at: {orch_path}")

    # Build command utilizing orchestrator.cli module
    cmd = [
        sys.executable,
        "-m",
        "orchestrator.cli",
        "build",
        "--project",
        project,
        "--budget",
        str(budget),
    ]

    if output_dir:
        cmd.extend(["--output-dir", str(Path(output_dir).resolve())])
    if quiet:
        cmd.append("--quiet")
    if extra_args:
        cmd.extend(extra_args)

    logger.info(f"Running AI Orchestrator headlessly: {' '.join(cmd)} (cwd={orch_path})")

    res = subprocess.run(
        cmd,
        cwd=str(orch_path),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    return {
        "status": "success" if res.returncode == 0 else "failed",
        "returncode": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }


# =============================================================================
# CLI Command Handlers
# =============================================================================


def cmd_run_reasoner(args: argparse.Namespace) -> int:
    """CLI handler for running the Reasoner application."""
    print("=" * 70)
    print("Executing Reasoner Headlessly...")
    print(f"Problem: {args.problem}")
    print(f"Preset:  {args.preset}")
    print(f"Path:    {args.path}")
    print("=" * 70)

    try:
        res = run_reasoner_headless(
            problem=args.problem,
            preset=args.preset,
            output_path=args.output,
            reasoner_dir=args.path,
            sequential=args.sequential,
            quiet=args.quiet,
        )

        if res["status"] == "success":
            print("\nReasoner run completed successfully!")
            if args.output:
                print(f"Results exported to: {args.output}")
            return 0
        else:
            print(f"\nReasoner run failed with exit code: {res['returncode']}")
            print("\nSTDOUT:")
            print(res["stdout"])
            print("\nSTDERR:")
            print(res["stderr"])
            return res["returncode"]

    except Exception as e:
        print(f"\nAn error occurred while launching Reasoner: {e}")
        return 1


def cmd_run_orchestrator(args: argparse.Namespace) -> int:
    """CLI handler for running the AI Orchestrator application."""
    print("=" * 70)
    print("Executing AI Orchestrator Headlessly...")
    print(f"Project: {args.project}")
    print(f"Budget:  ${args.budget:.2f}")
    print(f"Path:    {args.path}")
    print("=" * 70)

    try:
        res = run_orchestrator_headless(
            project=args.project,
            budget=args.budget,
            output_dir=args.output_dir,
            orchestrator_dir=args.path,
            quiet=args.quiet,
        )

        if res["status"] == "success":
            print("\nAI Orchestrator run completed successfully!")
            if args.output_dir:
                print(f"Outputs written to: {args.output_dir}")
            return 0
        else:
            print(f"\nAI Orchestrator run failed with exit code: {res['returncode']}")
            print("\nSTDOUT:")
            print(res["stdout"])
            print("\nSTDERR:")
            print(res["stderr"])
            return res["returncode"]

    except Exception as e:
        print(f"\nAn error occurred while launching AI Orchestrator: {e}")
        return 1
