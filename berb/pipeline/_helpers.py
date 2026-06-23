"""Shared constants, data classes, and utility functions for the pipeline executor.

This module re-exports all utilities from focused sub-modules for backward
compatibility. Direct imports from the sub-modules are preferred for new code.

Split during Phase 4 cleanup:
  - _io_helpers.py: File I/O (read/write artifacts, JSONL, YAML blocks)
  - _prompt_helpers.py: Prompt building, LLM chat, context preamble
  - _metric_helpers.py: Metric parsing from stdout, experiment result collection
  - _figure_helpers.py: Figure generation prompts, paper title extraction, defaults

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from berb.config import RCConfig
from berb.llm.client import LLMClient
from berb.pipeline._figure_helpers import (
    _default_hypotheses,
    _default_paper_outline,
    _default_quality_report,
    _extract_paper_title,
    _generate_framework_diagram_prompt,
    _generate_neurips_checklist,
    _multi_perspective_generate,
    _safe_filename,
    _synthesize_perspectives,
    reconcile_figure_refs,
)
from berb.pipeline._io_helpers import (
    _extract_code_block,
    _extract_multi_file_blocks,
    _extract_yaml_block,
    _find_prior_file,
    _parse_jsonl_rows,
    _read_prior_artifact,
    _write_jsonl,
)
from berb.pipeline._metric_helpers import (
    _collect_experiment_results,
    _collect_json_context,
    _detect_runtime_issues,
    _load_hardware_profile,
    _parse_metrics_from_stdout,
)
from berb.pipeline._prompt_helpers import (
    _build_context_preamble,
    _build_fallback_queries,
    _chat_with_prompt,
    _ensure_sandbox_deps,
    _extract_topic_keywords,
    _get_evolution_overlay,
    _read_best_analysis,
    _topic_constraint_block,
)
from berb.pipeline.stages import Stage, StageStatus
from berb.prompts import PromptManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes (kept inline — foundational type)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageResult:
    """Outcome of executing a single stage."""

    stage: Stage
    status: StageStatus
    artifacts: tuple[str, ...]
    error: str | None = None
    decision: str = "proceed"
    evidence_refs: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SANDBOX_SAFE_PACKAGES = {
    "numpy",
    "scipy",
    "torch",
    "sklearn",
    "pandas",
    "matplotlib",
    "seaborn",
    "tqdm",
    "gymnasium",
    "networkx",
    "torchdiffeq",
    "PIL",
    "Pillow",
    "timm",
    "einops",
    "torchmetrics",
    "transformers",
    "datasets",
    "accelerate",
    "peft",
    "trl",
    "sentencepiece",
    "tokenizers",
    "safetensors",
}


# ---------------------------------------------------------------------------
# Utility functions kept in core (used by multiple sub-modules)
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_json_loads(text: str, default: Any) -> Any:
    """Safely parse JSON, returning *default* on failure."""
    try:
        text_s = text.strip()
        if text_s == "" or text_s == "null":
            return default
        result = json.loads(text_s)
        # Accept: dicts, lists, strings, numbers, bools, None
        if not isinstance(result, dict | list | str | int | float | bool | None):
            return default
        return result
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return default


def _write_stage_meta(
    stage_dir: Path,
    stage: Stage,
    run_id: str,
    result: StageResult,
) -> None:
    """Write stage execution metadata to decision.json."""
    next_stage = Stage(int(stage) + 1) if int(stage) < 23 else None
    meta = {
        "stage_id": f"{int(stage):02d}-{stage.name.lower()}",
        "run_id": run_id,
        "status": result.status.value,
        "decision": result.decision,
        "output_artifacts": list(result.artifacts),
        "evidence_refs": list(result.evidence_refs),
        "error": result.error,
        "ts": _utcnow_iso(),
        "next_stage": int(next_stage) if next_stage is not None else None,
    }
    (stage_dir / "decision.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


__all__ = [
    "StageResult",
    "_utcnow_iso",
    "_safe_json_loads",
    "_write_stage_meta",
    # I/O helpers
    "_read_prior_artifact",
    "_find_prior_file",
    "_write_jsonl",
    "_parse_jsonl_rows",
    "_extract_code_block",
    "_extract_multi_file_blocks",
    "_extract_yaml_block",
    # Prompt helpers
    "_build_context_preamble",
    "_build_fallback_queries",
    "_chat_with_prompt",
    "_ensure_sandbox_deps",
    "_extract_topic_keywords",
    "_get_evolution_overlay",
    "_read_best_analysis",
    "_topic_constraint_block",
    # Metric helpers
    "_parse_metrics_from_stdout",
    "_collect_experiment_results",
    "_collect_json_context",
    "_load_hardware_profile",
    "_detect_runtime_issues",
    # Figure helpers
    "_safe_filename",
    "_default_hypotheses",
    "_default_paper_outline",
    "_default_quality_report",
    "_extract_paper_title",
    "_generate_neurips_checklist",
    "_generate_framework_diagram_prompt",
    "_multi_perspective_generate",
    "_synthesize_perspectives",
    "reconcile_figure_refs",
]
