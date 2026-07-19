"""Metric-grounded scoring for experiment candidates.

Pure functions that score JournalNodes based on the primary metric,
with cohort-relative normalization, hard gates (crash, buggy plots),
and explainability.

This replaces the heuristic in CodeAgent._score_node which rewards
stdout length rather than scientific quality.

Usage:
    from berb.experiment.search.scoring import score_node, ScoreBreakdown

    breakdown = score_node(node, "accuracy", maximize=True)
    print(breakdown.reason)
    print(breakdown.total)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScoreBreakdown:
    """Breakdown of a scored candidate.

    Attributes:
        total: Final score (0.0-10.0)
        runs_ok: Whether the candidate ran without crashes
        metric_value: Raw value of the primary metric (None if absent)
        metric_normalized: Min-max normalized metric across cohort (None if N/A)
        buggy_plots: Whether VLM deemed plots invalid
        penalties: List of penalty reasons applied
        reason: Human-readable explanation, persisted to the journal
    """

    total: float = 0.0
    runs_ok: bool = False
    metric_value: float | None = None
    metric_normalized: float | None = None
    buggy_plots: bool | None = None
    penalties: tuple[str, ...] = ()
    reason: str = ""


def score_node(
    node: Any,
    metric_key: str,
    *,
    maximize: bool = True,
    baseline: float | None = None,
    cohort: list[Any] | None = None,
) -> ScoreBreakdown:
    """Score a single experiment candidate based on its primary metric.

    Scoring rules, in order:
    1. HARD GATE: runs_ok is False → total 0.0.
    2. HARD GATE: is_buggy_plots is True → total 0.0 (VLM figure verdict).
    3. PRIMARY TERM: Normalized primary metric, direction-aware.
    4. SECONDARY TERM: Small bonus for metric completeness.
    5. PENALTIES: NaN/Inf metric, timeout, stderr traceback.
    6. EXPLAINABILITY: Every score carries a human-readable reason.

    Args:
        node: A candidate object with .runs_ok, .metrics dict, and optional
            .is_buggy_plots, .stderr, .timed_out attributes.
        metric_key: The primary metric name (e.g., "accuracy", "loss").
        maximize: True if higher metric is better, False if lower is better.
        baseline: Optional baseline score for normalization reference.
            If None, the score is compared against a 0-1 ideal range.
        cohort: Optional list of all candidates in this batch. If provided,
            min-max normalization is applied across the cohort so scores
            are comparable across heterogenous metric scales.

    Returns:
        A ScoreBreakdown with the final score and explanation.
    """
    reasons: list[str] = []
    penalties: list[str] = []

    # Extract attributes safely
    runs_ok = getattr(node, "runs_ok", False)
    is_buggy_plots = getattr(node, "is_buggy_plots", None)
    metrics = getattr(node, "metrics") if hasattr(node, "metrics") else {}
    stderr = getattr(node, "stderr", "") or ""
    timed_out = getattr(node, "timed_out", False)

    # --- Hard gate 1: crash --------------------------------------------------
    if not runs_ok:
        return ScoreBreakdown(
            total=0.0,
            runs_ok=False,
            buggy_plots=is_buggy_plots,
            reason="Candidate crashed (runs_ok=False). Score = 0.",
        )

    reasons.append("Run completed without crash")

    # --- Hard gate 2: buggy plots --------------------------------------------
    if is_buggy_plots is True:  # None = not evaluated, skip gate
        return ScoreBreakdown(
            total=0.0,
            runs_ok=True,
            buggy_plots=True,
            reason="Candidate produced invalid figures (is_buggy_plots=True). Score = 0.",
        )

    if is_buggy_plots is None:
        reasons.append("Figures not evaluated (is_buggy_plots=None)")
    else:
        reasons.append("Figures verified valid")

    # --- Primary metric -------------------------------------------------------
    metric_value: float | None = None
    metric_normalized: float | None = None

    if metric_key and metric_key in metrics:
        raw = metrics[metric_key]
        if raw is not None:
            try:
                metric_value = float(raw)
            except (TypeError, ValueError):
                metric_value = None

    if metric_value is not None and _is_valid_finite(metric_value):
        # Determine normalization range
        if cohort and len(cohort) > 1:
            # Cohort-relative min-max normalization
            values = []
            for c in cohort:
                m = _safe_get_metric(c, metric_key)
                if m is not None and _is_valid_finite(m):
                    values.append(m)

            if len(values) >= 2:
                cmin, cmax = min(values), max(values)
                if cmax > cmin:
                    if maximize:
                        metric_normalized = (metric_value - cmin) / (cmax - cmin)
                    else:
                        metric_normalized = (cmax - metric_value) / (cmax - cmin)
                else:
                    metric_normalized = 0.5  # All equal → neutral
            else:
                metric_normalized = 0.5  # Not enough data for cohort norm
        else:
            # Baseline or absolute comparison
            if baseline is not None:
                if maximize:
                    metric_normalized = metric_value / max(abs(baseline), 1e-10)
                else:
                    metric_normalized = max(abs(baseline), 1e-10) / max(metric_value, 1e-10)
            else:
                metric_normalized = 0.5  # Neutral without baseline

        metric_normalized = max(0.0, min(1.0, metric_normalized))

        # Primary term contributes up to 5 points
        primary_score = metric_normalized * 5.0
        reasons.append(
            f"Primary metric '{metric_key}' = {metric_value:.4f} "
            f"(normalized {metric_normalized:.4f}) → {primary_score:.2f} pts"
        )
    else:
        primary_score = 0.0
        if metric_value is not None and not _is_valid_finite(metric_value):
            penalties.append("NaN/Inf metric")
            reasons.append("Primary metric is NaN or Inf; penalty applied")
        else:
            reasons.append(f"Primary metric '{metric_key}' not found in results")

    # --- Secondary: metric completeness bonus --------------------------------
    completeness_bonus = 0.0
    if metrics and len(metrics) >= 2:
        completeness_bonus = 0.5
        reasons.append("Multiple metrics present (+0.5 completeness bonus)")

    # --- Penalties -----------------------------------------------------------
    if "Error" in stderr:
        penalties.append("stderr contains errors")
        reasons.append("stderr contains error messages; penalty applied")

    if timed_out:
        penalties.append("timed out")
        reasons.append("Candidate timed out; penalty applied")

    penalty = len(penalties) * 0.3  # -0.3 per penalty

    # --- Final calculation ---------------------------------------------------
    total = primary_score + completeness_bonus - penalty
    total = max(0.0, min(10.0, total))
    reason_str = "; ".join(reasons) or "No reason recorded"

    return ScoreBreakdown(
        total=total,
        runs_ok=True,
        metric_value=metric_value,
        metric_normalized=metric_normalized,
        buggy_plots=is_buggy_plots,
        penalties=tuple(penalties),
        reason=reason_str,
    )


def normalize_cohort(
    nodes: list[Any],
    metric_key: str,
    *,
    maximize: bool = True,
) -> dict[str, float]:
    """Compute min-max normalized scores for a cohort of candidates.

    Args:
        nodes: List of candidate objects.
        metric_key: Primary metric key.
        maximize: True if higher is better.

    Returns:
        Dict mapping node id (str(node.node_id) or str(id(node))) to
        normalized score (0.0-1.0). Nodes without the metric or with
        invalid values get 0.0.
    """
    values: list[tuple[str, float]] = []
    for n in nodes:
        m = _safe_get_metric(n, metric_key)
        if m is not None and _is_valid_finite(m):
            nid = str(getattr(n, "node_id", id(n)))
            values.append((nid, m))

    if len(values) < 2:
        return {nid: 0.5 if v is not None else 0.0 for nid, v in values}

    cmin = min(v for _, v in values)
    cmax = max(v for _, v in values)

    result: dict[str, float] = {}
    for nid, v in values:
        if cmax > cmin:
            if maximize:
                result[nid] = (v - cmin) / (cmax - cmin)
            else:
                result[nid] = (cmax - v) / (cmax - cmin)
        else:
            result[nid] = 0.5

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _safe_get_metric(node: Any, metric_key: str) -> float | None:
    """Safely extract a metric value from a candidate object."""
    if not hasattr(node, "metrics") or not node.metrics:
        return None
    raw = node.metrics.get(metric_key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _is_valid_finite(value: float) -> bool:
    """Check if a float is finite (not NaN, not Inf)."""
    return not (math.isnan(value) or math.isinf(value))
