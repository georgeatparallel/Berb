"""Metric parsing and experiment result collection helpers.

Extracted from _helpers.py — all functions re-exported from _helpers.py
for backward compatibility.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from berb.experiment.metrics import is_metric_name

logger = logging.getLogger(__name__)


def _parse_metrics_from_stdout(stdout: str) -> dict[str, Any]:
    """Parse ``name: value`` metric lines from experiment stdout."""
    metrics: dict[str, Any] = {}
    for line in stdout.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        parts = line.rsplit(":", 1)
        if len(parts) != 2:
            continue
        name_part = parts[0].strip()
        value_part = parts[1].strip()
        if not is_metric_name(name_part):
            continue
        try:
            fval = float(value_part)
            metrics[name_part] = fval
        except (ValueError, TypeError):
            pass
    return metrics


def _collect_json_context(
    run_dir: Path,
    stage: int,
    keys: tuple[str, ...] = ("metrics", "artifact"),
) -> dict[str, Any]:
    """Collect JSON context from stage directories.

    Searches for ``.json`` files in the specified stage directories and
    collects the specified keys from each.
    """
    result: dict[str, Any] = {}
    for s in range(1, stage + 1):
        stage_dir = run_dir / f"stage-{s:02d}"
        if not stage_dir.is_dir():
            continue
        for json_file in sorted(stage_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for key in keys:
                        if key in data:
                            result[f"stage-{s:02d}/{json_file.name}/{key}"] = data[key]
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                pass
    return result


def _collect_experiment_results(
    run_dir: Path,
    metric_keys: tuple[str, ...] = ("primary_metric",),
    *,
    metric_key: str = "",
    metric_direction: str = "minimize",
) -> dict[str, Any]:
    """Collect experiment results from the latest stage-14 iteration."""
    import os

    if metric_key and metric_key not in metric_keys:
        metric_keys = (metric_key, *metric_keys)

    summary: dict[str, Any] = {}

    # Try experiment_summary_best.json first
    for candidate in ["experiment_summary_best.json", "stage-14/experiment_summary.json"]:
        _path = run_dir / candidate
        if _path.exists():
            try:
                data = json.loads(_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    summary.update(data)
                    break
            except (json.JSONDecodeError, OSError):
                continue

    # Extract primary metrics
    metrics: dict[str, float] = {}
    ms = summary.get("metrics_summary", {})
    if isinstance(ms, dict):
        for key in metric_keys:
            if key in ms:
                val = ms[key]
                if isinstance(val, dict):
                    val = val.get("mean", val.get("value", val))
                try:
                    metrics[key] = float(val)
                except (TypeError, ValueError):
                    pass

    # If no metric keys matched, collect all floats
    if not metrics and isinstance(ms, dict):
        for k, v in ms.items():
            if isinstance(v, (int, float)):
                metrics[k] = float(v)
            elif isinstance(v, dict) and "mean" in v:
                try:
                    metrics[k] = float(v["mean"])
                except (TypeError, ValueError):
                    pass

    return {
        "metrics_summary": ms,
        "experiment_summary": summary,
        "primary_metrics": metrics,
        "metric_direction": metric_direction,
        # These are pass-through fields from experiment_summary*.json when
        # stage 12/13 wrote them; default to empty rather than KeyError/None
        # when no experiment data exists yet (e.g. stage skipped/failed).
        "paired_comparisons": summary.get("paired_comparisons", []),
        "runs": summary.get("runs", []),
        "best_run": summary.get("best_run", {}),
        "latex_table": summary.get("latex_table", ""),
        "structured_results": summary.get("structured_results", {}),
    }


def _load_hardware_profile(run_dir: Path) -> dict[str, Any] | None:
    """Load hardware profile from a run directory."""
    hw_path = run_dir / "stage-01" / "hardware_profile.json"
    if hw_path.exists():
        try:
            return json.loads(hw_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


_DIVERGENCE_LOSS_THRESHOLD = 100.0
_DUMMY_METRIC_MIN_OCCURRENCES = 3


def _detect_runtime_issues(sandbox_result: object) -> str:
    """Detect common runtime issues from sandbox results.

    Returns a human-readable warning string, or empty string if no issues.
    """
    import math
    import re
    from collections import defaultdict

    warnings: list[str] = []
    stderr = getattr(sandbox_result, "stderr", "") or ""
    stdout = getattr(sandbox_result, "stdout", "") or ""
    metrics = getattr(sandbox_result, "metrics", {}) or {}
    returncode = getattr(sandbox_result, "returncode", 0)

    if returncode != 0 and returncode is not None:
        warnings.append(f"Non-zero exit code ({returncode})")

    # Structured metrics: NaN / Inf / diverging loss
    for key, value in metrics.items():
        try:
            fvalue = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(fvalue):
            warnings.append(f"NaN detected in metric '{key}'")
        elif math.isinf(fvalue):
            warnings.append(f"Inf detected in metric '{key}'")
        elif "loss" in key.lower() and fvalue > _DIVERGENCE_LOSS_THRESHOLD:
            warnings.append(f"DIVERGING loss detected in metric '{key}' (value={fvalue})")

    # Raw stdout/stderr fallback (metrics dict may be empty/unavailable)
    if not any("NaN" in w for w in warnings) and re.search(r"\bnan\b", stdout, re.IGNORECASE):
        warnings.append("NaN values detected in output")

    # RuntimeWarning lines in stderr — keep the actual message, not just
    # a generic label, so callers can see what triggered it.
    for line in stderr.splitlines():
        if "RuntimeWarning" in line:
            msg = line.split("RuntimeWarning:", 1)[-1].strip()
            warnings.append(f"RuntimeWarning: {msg}" if msg else "RuntimeWarning")

    # Python exception class names in stderr (e.g. ZeroDivisionError)
    exc_match = re.search(r"\b(\w*Error)\b", stderr)
    if exc_match:
        warnings.append(f"{exc_match.group(1)} detected in stderr")

    # Common infra/environment error patterns
    patterns = {
        "CUDA out of memory": "GPU memory exhausted — reduce batch size or model size",
        "No module named": "Missing Python dependency in sandbox",
        "Segmentation fault": "Memory corruption in native extension",
        "Timeout": "Experiment timed out",
        "Killed": "Process was killed (OOM or resource limit)",
    }
    for pattern, msg in patterns.items():
        if pattern in stderr or pattern in stdout:
            warnings.append(msg)

    # Dummy/hardcoded metric detection: the same metric name repeated with
    # an identical value across several distinct result lines suggests a
    # hardcoded fallback rather than a real computed result.
    metric_occurrences: dict[str, list[str]] = defaultdict(list)
    for match in re.finditer(r"(\w+):\s*(-?\d+\.\d+)", stdout):
        metric_occurrences[match.group(1)].append(match.group(2))
    for name, values in metric_occurrences.items():
        if len(values) >= _DUMMY_METRIC_MIN_OCCURRENCES and len(set(values)) == 1:
            warnings.append(
                f"DUMMY value detected for metric '{name}' "
                f"(all {len(values)} occurrences equal {values[0]})"
            )

    return "; ".join(warnings) if warnings else ""
