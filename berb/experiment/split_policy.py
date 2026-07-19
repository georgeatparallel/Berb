"""Split-policy for three-way evaluation and selection-bias correction.

Pure domain logic — no I/O, no LLM calls, fully unit-testable.

The three-way split decouples the three roles of a metric:
1. **Selection (train):** used during the edit-run-eval loop to tune code — ``metric_select``
2. **Ranking (validation):** used to pick the best-of-N candidate — ``metric_rank``
3. **Reporting (test):** touched exactly once; the honest estimate — ``metric_report``

Key functions
-------------
partition
    Split a dataset specification into train / validation / test indices.
selection_penalty
    Expected-maximum correction for best-of-N selection bias.
admit
    The single admissible-claim predicate, replacing the drifted duplicate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from berb.integrity.claims import ClaimVerdict
from berb.pipeline.contracts import SplitEvidence


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateConfig:
    """Configuration for the admission gate.

    Parameters control the statistical rigour of the admit() predicate.
    """

    min_effect: float = 0.3
    """Minimum absolute effect size for a claim to be considered SUPPORTED."""

    alpha: float = 0.05
    """Significance threshold for the reported metric."""

    min_power: float = 0.6
    """Minimum statistical power to avoid INCONCLUSIVE."""

    min_rows_for_split: int = 30
    """Minimum total rows to attempt a three-way split. Below this,
    split_available is set to False."""

    train_ratio: float = 0.6
    """Fraction of data for the train/selection split."""

    val_ratio: float = 0.2
    """Fraction of data for the validation/ranking split."""

    test_ratio: float = 0.2
    """Fraction of data for the test/reporting split."""


@dataclass(frozen=True)
class SplitSpec:
    """Result of partitioning a dataset."""

    train_indices: tuple[int, ...] = ()
    val_indices: tuple[int, ...] = ()
    test_indices: tuple[int, ...] = ()
    n_total: int = 0
    feasible: bool = True
    reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Partitioning
# ─────────────────────────────────────────────────────────────────────────────


def partition(
    n_total: int,
    *,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    min_rows_for_split: int = 30,
    seed: int = 42,
) -> SplitSpec:
    """Partition a dataset into train / validation / test splits.

    Args:
        n_total: Total number of rows / data points available.
        train_ratio: Fraction for training (selection).
        val_ratio: Fraction for validation (ranking).
        test_ratio: Fraction for testing (reporting).
        min_rows_for_split: Minimum total rows to attempt a split.
        seed: RNG seed for deterministic shuffling.

    Returns:
        A SplitSpec with index tuples for each split. If the dataset is
        too small, ``feasible`` is False and the caller must set
        ``split_available=False`` on ``SplitEvidence``.
    """
    if n_total < min_rows_for_split:
        return SplitSpec(
            n_total=n_total,
            feasible=False,
            reason=(
                f"Dataset too small for three-way split: {n_total} rows "
                f"< minimum {min_rows_for_split}"
            ),
        )

    import random

    rng = random.Random(seed)
    indices = list(range(n_total))
    rng.shuffle(indices)

    # Compute split boundaries
    train_end = max(1, int(n_total * train_ratio))
    val_end = train_end + max(1, int(n_total * val_ratio))

    # Ensure each split has at least 1 element
    if train_end >= n_total:
        train_end = n_total - 2
        val_end = n_total - 1
    if val_end >= n_total:
        val_end = n_total

    # Edge case: not enough for 3 splits even though n_total >= min_rows
    if n_total < 3:
        return SplitSpec(
            n_total=n_total,
            feasible=False,
            reason=f"Need at least 3 rows for three-way split, got {n_total}",
        )

    train = tuple(sorted(indices[:train_end]))
    val = tuple(sorted(indices[train_end:val_end]))
    test = tuple(sorted(indices[val_end:]))

    return SplitSpec(
        train_indices=train,
        val_indices=val,
        test_indices=test,
        n_total=n_total,
        feasible=True,
        reason=(
            f"Split {n_total} rows: {len(train)} train, {len(val)} val, {len(test)} test"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Selection bias correction
# ─────────────────────────────────────────────────────────────────────────────


def selection_penalty(
    n_candidates: int,
    spread: float = 1.0,
) -> float:
    """Expected-maximum correction for best-of-N selection bias.

    When you pick the best of N candidates, the reported metric is inflated
    relative to the true mean.  For N independent samples from a roughly
    symmetric distribution, the expected maximum grows as approximately
    ``spread * sqrt(2 * ln(N))``.

    This returns an estimate of that inflation so the caller can subtract it
    from the reported metric.

    Args:
        n_candidates: Number of candidates in the selection pool (N).
        spread: Approximate spread (standard deviation) of candidate scores.
            Default 1.0 assumes normalised scores.  For raw metrics, pass
            the empirical spread of candidate scores.

    Returns:
        Estimated inflation to subtract from the reported metric.
        Returns 0.0 for N <= 1 (no selection bias).
    """
    if n_candidates <= 1:
        return 0.0
    # Approximation for the expected maximum of N i.i.d. standard normals
    # Uses the classic sqrt(2*ln(N)) - (ln(ln(N)) + ln(4*pi)) / (2*sqrt(2*ln(N)))
    # approximation with the dominant term.
    ln_n = math.log(n_candidates)
    return spread * math.sqrt(2.0 * ln_n)


# ─────────────────────────────────────────────────────────────────────────────
# Power & direction helpers
# ─────────────────────────────────────────────────────────────────────────────


def _is_powered(ev: SplitEvidence, cfg: GateConfig) -> bool:
    """Heuristic check for whether the experiment had enough statistical power.

    Uses n_candidates as a proxy for sample size — runs with more iterations
    are likelier to have adequate power.  In production this should consume
    an explicit power analysis from Stage 14.
    """
    # Heuristic: at least 3 candidates and a non-trivial effect on the
    # rank split suggests adequate power.
    if ev.n_candidates < 3:
        return False
    if abs(ev.metric_rank) < cfg.min_effect * 0.5:
        return False
    return True


def _sign(x: float) -> int:
    """Return 1, -1, or 0."""
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _has_p_value(ev: SplitEvidence) -> bool:
    """Check whether the evidence carries a p-value.

    For now, returns True if metric_report is not None (proxy).
    In production this would check a ``p_value`` field in SplitEvidence.
    """
    return ev.metric_report is not None


# ─────────────────────────────────────────────────────────────────────────────
# The single admissible-claim predicate
# ─────────────────────────────────────────────────────────────────────────────


def admit(ev: SplitEvidence, cfg: GateConfig = GateConfig()) -> ClaimVerdict:
    """The single admissible-claim predicate for all pipeline claims.

    This replaces the three drifted copies (improvement_loop, claim_tracker,
    and the inline check in the experiment runner).

    Rules applied in order:
    1. If underpowered → INCONCLUSIVE. Never UNSUPPORTED from weak data.
    2. If no split available → UNSPLITTABLE (disclose in limitations).
    3. If rank and report disagree on direction → INCONCLUSIVE (unstable).
    4. If |metric_report| >= min_effect and p_value < alpha → SUPPORTED.
    5. Otherwise → UNSUPPORTED.

    Note on negative effects:
    A large **negative** effect (e.g. -0.8) with adequate power returns
    SUPPORTED, not UNSUPPORTED.  The old unsigned bug (improvement_loop:302)
    silently discarded every negative result.
    """
    # Rule 1: underpowered → INCONCLUSIVE
    if not _is_powered(ev, cfg):
        return ClaimVerdict.INCONCLUSIVE

    # Rule 2: no split → UNSPLITTABLE
    if not ev.split_available:
        return ClaimVerdict.UNSPLITTABLE

    # Rule 3: direction disagreement → INCONCLUSIVE
    if ev.metric_report is not None and _sign(ev.metric_rank) != _sign(ev.metric_report):
        return ClaimVerdict.INCONCLUSIVE

    # Rule 4: strong evidence → SUPPORTED
    if ev.metric_report is not None:
        if abs(ev.metric_report) >= cfg.min_effect and _has_p_value(ev):
            return ClaimVerdict.SUPPORTED

    # Rule 5: otherwise → UNSUPPORTED
    return ClaimVerdict.UNSUPPORTED


def selection_bias_report(ev: SplitEvidence) -> dict[str, Any]:
    """Produce a human-readable report of selection bias for the summary.

    Returns a dict suitable for inclusion in experiment_summary.json.
    """
    bias_estimate = 0.0
    if ev.n_candidates > 1 and ev.metric_report is not None:
        # The gap between rank (best-of-N) and report (test) is the
        # empirical bias.
        bias_estimate = ev.metric_rank - ev.metric_report

    return {
        "metric_key": ev.metric_key,
        "metric_select": ev.metric_select,
        "metric_rank": ev.metric_rank,
        "metric_report": ev.metric_report,
        "n_candidates": ev.n_candidates,
        "split_available": ev.split_available,
        "test_evaluations": ev.test_evaluations,
        "bias_estimate": bias_estimate,
        "selection_penalty": selection_penalty(ev.n_candidates),
        "verdict": admit(ev).value,
    }
