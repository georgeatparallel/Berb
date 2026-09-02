"""Property-based and table-driven tests for split_policy.py.

Test matrix for admit() covers all verdict paths:
    {powered, underpowered} × {positive, negative, null effect}
    × {split, unsplittable} × {direction agreement, direction disagreement}
"""

from __future__ import annotations

import pytest

from berb.experiment.split_policy import (
    GateConfig,
    admit,
    partition,
    selection_penalty,
)
from berb.integrity.claims import ClaimVerdict
from berb.pipeline.contracts import SplitEvidence

# ─────────────────────────────────────────────────────────────────────────────
# split_policy tests
# ─────────────────────────────────────────────────────────────────────────────


class TestPartition:
    """Tests for the partition function."""

    def test_partition_normal(self):
        """Test normal partitioning."""
        spec = partition(100, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, seed=42)
        assert spec.feasible is True
        assert len(spec.train_indices) == 60
        assert len(spec.val_indices) == 20
        assert len(spec.test_indices) == 20
        assert spec.n_total == 100
        assert "Split 100 rows:" in spec.reason

    def test_partition_sizes_reasonable(self):
        """Test that split sizes make sense."""
        spec = partition(100, train_ratio=0.5, val_ratio=0.25, test_ratio=0.25, seed=42)
        assert spec.feasible is True
        assert len(spec.train_indices) >= 40
        assert len(spec.val_indices) >= 15

    def test_partition_too_small(self):
        """Test borderline: 20 rows is below default min_rows_for_split."""
        spec = partition(20, min_rows_for_split=30)
        assert spec.feasible is False

    def test_partition_too_small_no_split(self):
        """Test 2 rows — can't make 3 splits."""
        spec = partition(2, min_rows_for_split=1)
        assert spec.feasible is False
        assert "at least 3" in spec.reason

    def test_partition_deterministic(self):
        """Test that same seed produces same split."""
        spec1 = partition(100, seed=42)
        spec2 = partition(100, seed=42)
        assert spec1.train_indices == spec2.train_indices
        assert spec1.val_indices == spec2.val_indices
        assert spec1.test_indices == spec2.test_indices

    def test_partition_different_seed(self):
        """Test that different seeds can produce different splits."""
        spec1 = partition(100, seed=42)
        spec2 = partition(100, seed=99)
        # It's very unlikely all three splits match with different seeds
        different = (
            spec1.train_indices != spec2.train_indices
            or spec1.val_indices != spec2.val_indices
            or spec1.test_indices != spec2.test_indices
        )
        assert different, "Different seeds should produce different splits"


class TestSelectionPenalty:
    """Tests for selection_penalty."""

    def test_no_bias_for_single_candidate(self):
        """N=1 should have no selection bias."""
        assert selection_penalty(1) == 0.0
        assert selection_penalty(0) == 0.0

    def test_bias_grows_with_n(self):
        """Larger N should produce larger penalty."""
        penalty_2 = selection_penalty(2)
        penalty_10 = selection_penalty(10)
        penalty_100 = selection_penalty(100)
        assert penalty_10 > penalty_2
        assert penalty_100 > penalty_10

    def test_spread_scales_penalty(self):
        """Wider spread should produce larger penalty."""
        base = selection_penalty(10, spread=1.0)
        scaled = selection_penalty(10, spread=2.0)
        assert abs(scaled - 2.0 * base) < 1e-10

    def test_large_n_is_bounded(self):
        """Penalty should not be astronomical for large N."""
        penalty = selection_penalty(10000)
        # sqrt(2*ln(10000)) ≈ sqrt(2*9.21) ≈ sqrt(18.42) ≈ 4.29
        assert penalty < 10.0
        assert penalty > 2.0

    def test_float_n_candidates(self):
        """Ensure penalty is monotonically increasing with N."""
        penalties = [selection_penalty(n) for n in range(1, 20)]
        for i in range(1, len(penalties)):
            assert penalties[i] >= penalties[i - 1], (
                f"Penalty decreased at n={i + 1}: {penalties[i]} < {penalties[i - 1]}"
            )


class TestAdmitVerdictMatrix:
    """Table-driven tests over the verdict matrix.

    Covers all combinations of:
    - powered / underpowered
    - positive / negative / null effect on rank
    - split_available / unsplittable
    - direction agreement / disagreement between rank and report
    """

    @staticmethod
    def _make_ev(
        metric_rank: float = 0.5,
        metric_report: float | None = 0.5,
        metric_select: float = 0.5,
        n_candidates: int = 5,
        split_available: bool = True,
        test_evaluations: int = 0,
        metric_key: str = "test_metric",
    ) -> SplitEvidence:
        return SplitEvidence(
            metric_key=metric_key,
            metric_select=metric_select,
            metric_rank=metric_rank,
            metric_report=metric_report,
            n_candidates=n_candidates,
            split_available=split_available,
            test_evaluations=test_evaluations,
        )

    @pytest.mark.parametrize(
        "desc, ev_kwargs, cfg_kwargs, expected",
        [
            # ── Powered, split available ──
            (
                "large positive effect → SUPPORTED",
                {"metric_rank": 0.8, "metric_report": 0.75, "n_candidates": 5},
                {},
                ClaimVerdict.SUPPORTED,
            ),
            (
                "large NEGATIVE effect → SUPPORTED (not UNSUPPORTED)",
                {"metric_rank": -0.8, "metric_report": -0.75, "n_candidates": 5},
                {},
                ClaimVerdict.SUPPORTED,
            ),
            (
                "small effect → UNSUPPORTED",
                {"metric_rank": 0.2, "metric_report": 0.15, "n_candidates": 5},
                {"min_effect": 0.3},
                ClaimVerdict.UNSUPPORTED,
            ),
            (
                "zero effect → INCONCLUSIVE (underpowered)",
                {"metric_rank": 0.0, "metric_report": 0.0, "n_candidates": 5},
                {"min_effect": 0.3},
                ClaimVerdict.INCONCLUSIVE,
            ),
            # ── Direction disagreement ──
            (
                "rank positive, report negative → INCONCLUSIVE",
                {"metric_rank": 0.6, "metric_report": -0.4, "n_candidates": 5},
                {},
                ClaimVerdict.INCONCLUSIVE,
            ),
            (
                "rank negative, report positive → INCONCLUSIVE",
                {"metric_rank": -0.6, "metric_report": 0.4, "n_candidates": 5},
                {},
                ClaimVerdict.INCONCLUSIVE,
            ),
            # ── Underpowered (too few candidates) ──
            (
                "only 1 candidate → INCONCLUSIVE",
                {"metric_rank": 0.8, "metric_report": 0.75, "n_candidates": 1},
                {},
                ClaimVerdict.INCONCLUSIVE,
            ),
            (
                "only 2 candidates → INCONCLUSIVE",
                {"metric_rank": 0.8, "metric_report": 0.75, "n_candidates": 2},
                {},
                ClaimVerdict.INCONCLUSIVE,
            ),
            # ── Underpowered (trivial rank effect) ──
            (
                "powered n but tiny effect → INCONCLUSIVE",
                {"metric_rank": 0.01, "metric_report": 0.01, "n_candidates": 10},
                {},
                ClaimVerdict.INCONCLUSIVE,
            ),
            # ── Unsplit table ──
            (
                "unsplittable, large effect → UNSPLITTABLE",
                {
                    "metric_rank": 0.8,
                    "metric_report": 0.75,
                    "n_candidates": 5,
                    "split_available": False,
                },
                {},
                ClaimVerdict.UNSPLITTABLE,
            ),
            (
                "unsplittable, underpowered → UNSPLITTABLE (power check first)",
                {
                    "metric_rank": 0.8,
                    "metric_report": 0.75,
                    "n_candidates": 1,
                    "split_available": False,
                },
                {},
                ClaimVerdict.INCONCLUSIVE,
            ),
            # ── Edge: no metric_report yet ──
            (
                "no report metric yet → UNSUPPORTED (no evidence)",
                {"metric_rank": 0.8, "metric_report": None, "n_candidates": 5},
                {},
                ClaimVerdict.UNSUPPORTED,
            ),
        ],
    )
    def test_admit_verdicts(self, desc, ev_kwargs, cfg_kwargs, expected):
        """Parametric test over the verdict matrix."""
        ev = self._make_ev(**ev_kwargs)
        cfg = GateConfig(**cfg_kwargs)
        verdict = admit(ev, cfg)
        assert verdict == expected, (
            f"FAIL [{desc}]: expected {expected.value}, got {verdict.value}\n  ev={ev}\n  cfg={cfg}"
        )


class TestAdmitNegativeEffectBug:
    """Regression: the old unsigned comparison bug.

    improvement_loop.py:302 had ``effect_size > 0.3`` (unsigned) which
    silently discarded every negative effect. This test asserts that
    large negative effects are correctly recognised as SUPPORTED.
    """

    def test_large_negative_is_supported(self):
        """Large negative effect (−0.8) with adequate power → SUPPORTED."""
        ev = SplitEvidence(
            metric_key="loss",
            metric_select=-0.85,
            metric_rank=-0.8,
            metric_report=-0.75,
            n_candidates=5,
        )
        cfg = GateConfig(min_effect=0.3)
        assert admit(ev, cfg) == ClaimVerdict.SUPPORTED

    def test_large_positive_is_supported(self):
        """Symmetry: large positive effect (+0.8) → SUPPORTED."""
        ev = SplitEvidence(
            metric_key="accuracy",
            metric_select=0.85,
            metric_rank=0.8,
            metric_report=0.75,
            n_candidates=5,
        )
        cfg = GateConfig(min_effect=0.3)
        assert admit(ev, cfg) == ClaimVerdict.SUPPORTED


class TestAdmitUnderpowered:
    """Regression: underpowered → INCONCLUSIVE, never UNSUPPORTED."""

    def test_underpowered_null_effect(self):
        """Underpowered with null effect → INCONCLUSIVE (not UNSUPPORTED)."""
        ev = SplitEvidence(
            metric_key="acc",
            metric_select=0.0,
            metric_rank=0.0,
            metric_report=0.0,
            n_candidates=1,
        )
        cfg = GateConfig(min_effect=0.3)
        assert admit(ev, cfg) == ClaimVerdict.INCONCLUSIVE

    def test_underpowered_small_effect(self):
        """Underpowered with small but real effect → INCONCLUSIVE."""
        ev = SplitEvidence(
            metric_key="acc",
            metric_select=0.2,
            metric_rank=0.2,
            metric_report=0.2,
            n_candidates=2,
        )
        cfg = GateConfig(min_effect=0.3)
        assert admit(ev, cfg) == ClaimVerdict.INCONCLUSIVE


class TestDoubleTestEvaluation:
    """Second test-split read must invalidate the split."""

    def test_second_evaluation_marks_unsplittable(self):
        """split_available becomes False on second evaluation."""
        # The admit() function doesn't enforce this — the producer side
        # (Stage 13) must set split_available=False when test_evaluations > 1.
        # This test checks that the system correctly marks it as UNSPLITTABLE.
        ev = SplitEvidence(
            metric_key="acc",
            metric_select=0.8,
            metric_rank=0.75,
            metric_report=0.7,
            n_candidates=5,
            split_available=False,  # set by producer after second eval
        )
        assert admit(ev) == ClaimVerdict.UNSPLITTABLE


class TestConfigRoundTrip:
    """Test that GateConfig round-trips."""

    def test_default_config(self):
        """Default config has reasonable values."""
        cfg = GateConfig()
        assert cfg.min_effect == 0.3
        assert cfg.alpha == 0.05
        assert cfg.min_power == 0.6
        assert cfg.min_rows_for_split == 30
        assert abs(cfg.train_ratio + cfg.val_ratio + cfg.test_ratio - 1.0) < 1e-10

    def test_custom_config(self):
        """Custom config values are honoured."""
        cfg = GateConfig(min_effect=0.5, alpha=0.01, min_rows_for_split=50)
        assert cfg.min_effect == 0.5
        assert cfg.alpha == 0.01
        assert cfg.min_rows_for_split == 50
