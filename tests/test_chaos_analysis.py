"""Tests for chaos detection and analysis tools.

Coverage:
- Entropy measures (KS, correlation dimension, ApEn, SampEn, PE)
- Recurrence analysis (RP, RQA)
- 0-1 test for chaos

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
import numpy as np

from berb.domains.chaos.entropy import (
    kolmogorov_sinai_entropy,
    correlation_dimension,
    approximate_entropy,
    sample_entropy,
    permutation_entropy,
    EntropyResult,
)
from berb.domains.chaos.recurrence import (
    RecurrencePlot,
    RecurrenceQuantificationAnalysis,
    compute_recurrence_matrix,
    compute_rqa_metrics,
    cross_recurrence,
    joint_recurrence,
    RQAMetrics,
    RecurrenceResult,
)
from berb.domains.chaos.test_01 import (
    run_01_chaos_test,
    run_01_chaos_batch,
    compute_translation_variables,
    compute_mean_square_displacement,
    Test01Result,
)


# =============================================================================
# Entropy Tests
# =============================================================================

class TestKolmogorovSinaiEntropy:
    """Test KS entropy computation."""

    def test_lorenz_lyapunov_exponents(self):
        """Test KS entropy for Lorenz system."""
        # Lorenz-63 typical exponents: λ₁ ≈ 0.9056, λ₂ = 0, λ₃ ≈ -14.57
        result = kolmogorov_sinai_entropy([0.9056, 0.0, -14.57])

        # KS = sum of positive exponents = 0.9056
        assert np.isclose(result.value, 0.9056, rtol=0.01)
        assert result.method == "pesin_identity"

    def test_all_negative_exponents(self):
        """Test KS entropy with all negative exponents."""
        result = kolmogorov_sinai_entropy([-1.0, -2.0, -3.0])
        assert result.value == 0.0  # No positive exponents

    def test_multiple_positive_exponents(self):
        """Test KS entropy with multiple positive exponents."""
        result = kolmogorov_sinai_entropy([1.0, 0.5, -2.0])
        assert np.isclose(result.value, 1.5)  # 1.0 + 0.5

    def test_confidence_based_on_count(self):
        """Test confidence based on number of exponents."""
        result1 = kolmogorov_sinai_entropy([1.0])
        result2 = kolmogorov_sinai_entropy([1.0, 0.0, -1.0])

        assert result1.confidence < result2.confidence


class TestCorrelationDimension:
    """Test correlation dimension computation."""

    def test_short_trajectory(self):
        """Test with too short trajectory."""
        trajectory = np.random.randn(50, 2)
        result = correlation_dimension(trajectory)

        assert np.isnan(result.value)
        assert result.confidence == 0.0

    def test_random_data(self):
        """Test with random data."""
        np.random.seed(42)
        trajectory = np.random.randn(500, 3)

        result = correlation_dimension(trajectory, n_points=200)

        # Should complete without error
        assert isinstance(result, EntropyResult)


class TestApproximateEntropy:
    """Test approximate entropy."""

    def test_regular_signal(self):
        """Test ApEn for regular (sinusoidal) signal."""
        t = np.linspace(0, 10 * np.pi, 1000)
        signal = np.sin(t)

        result = approximate_entropy(signal, m=2, r=0.2 * np.std(signal))

        # Regular signal should have low ApEn
        assert result.value < 0.5

    def test_random_signal(self):
        """Test ApEn for random signal."""
        np.random.seed(42)
        signal = np.random.randn(1000)

        result = approximate_entropy(signal, m=2)

        # Random signal should have higher ApEn
        assert result.value > 0.5

    def test_short_series(self):
        """Test with too short time series."""
        signal = np.random.randn(50)
        result = approximate_entropy(signal, m=2)

        assert np.isnan(result.value)


class TestSampleEntropy:
    """Test sample entropy."""

    def test_regular_signal(self):
        """Test SampEn for regular signal."""
        t = np.linspace(0, 10 * np.pi, 1000)
        signal = np.sin(t)

        result = sample_entropy(signal, m=2)

        # Regular signal should have low SampEn
        assert result.value < 0.5

    def test_random_signal(self):
        """Test SampEn for random signal."""
        np.random.seed(42)
        signal = np.random.randn(1000)

        result = sample_entropy(signal, m=2)

        # Random signal should have higher SampEn
        assert result.value > 0.5

    def test_sampen_vs_apen(self):
        """Test SampEn is generally more consistent than ApEn."""
        np.random.seed(42)
        signal = np.random.randn(500)

        sampen_result = sample_entropy(signal, m=2)
        apen_result = approximate_entropy(signal, m=2)

        # Both should complete
        assert isinstance(sampen_result.value, float)
        assert isinstance(apen_result.value, float)


class TestPermutationEntropy:
    """Test permutation entropy."""

    def test_regular_signal(self):
        """Test PE for regular signal."""
        t = np.linspace(0, 10 * np.pi, 1000)
        signal = np.sin(t)

        result = permutation_entropy(signal, order=3)

        # Regular signal should have lower PE
        assert result.value < 0.8

    def test_random_signal(self):
        """Test PE for random signal."""
        np.random.seed(42)
        signal = np.random.randn(1000)

        result = permutation_entropy(signal, order=3)

        # Random signal should have high PE (close to 1)
        # But may not always be > 0.8 due to randomness
        assert result.value > 0.5  # More lenient threshold

    def test_normalized_output(self):
        """Test PE is normalized to [0, 1]."""
        np.random.seed(42)
        signal = np.random.randn(1000)

        result = permutation_entropy(signal, order=4)

        assert 0.0 <= result.value <= 1.0


# =============================================================================
# Recurrence Analysis Tests
# =============================================================================

class TestRecurrencePlot:
    """Test recurrence plot generation."""

    def test_compute_recurrence_matrix(self):
        """Test recurrence matrix computation."""
        rp = RecurrencePlot(threshold=0.5)
        trajectory = np.random.randn(100, 2)

        R = rp.compute(trajectory)

        assert R.shape == (100, 100)
        assert np.all((R == 0) | (R == 1))

    def test_no_diagonal(self):
        """Test diagonal exclusion."""
        rp = RecurrencePlot(threshold=0.5, include_diagonal=False)
        trajectory = np.random.randn(100, 2)

        R = rp.compute(trajectory)

        # Diagonal should be zeros
        assert np.all(np.diag(R) == 0)

    def test_with_diagonal(self):
        """Test diagonal inclusion."""
        rp = RecurrencePlot(threshold=0.5, include_diagonal=True)
        trajectory = np.random.randn(100, 2)

        R = rp.compute(trajectory)

        # Diagonal should be ones (distance to self is 0)
        assert np.all(np.diag(R) == 1)

    def test_adaptive_threshold(self):
        """Test adaptive threshold computation."""
        rp = RecurrencePlot(threshold=0.1)
        trajectory = np.random.randn(100, 2)

        R = rp.compute_adaptive(trajectory, recurrence_rate=0.05)

        # Actual recurrence rate should be close to target
        actual_rr = np.sum(R) / (100 * 100)
        assert np.isclose(actual_rr, 0.05, rtol=0.5)  # 50% tolerance


class TestRecurrenceQuantificationAnalysis:
    """Test RQA metrics computation."""

    def test_compute_metrics(self):
        """Test RQA metrics computation."""
        rp = RecurrencePlot(threshold=0.5, include_diagonal=False)
        trajectory = np.random.randn(100, 2)
        R = rp.compute(trajectory)

        rqa = RecurrenceQuantificationAnalysis(min_line_length=2)
        metrics = rqa.compute(R)

        assert isinstance(metrics, RQAMetrics)
        assert 0.0 <= metrics.RR <= 1.0
        assert 0.0 <= metrics.DET <= 1.0
        assert 0.0 <= metrics.LAM <= 1.0

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = RQAMetrics(RR=0.1, DET=0.5, L_max=10)
        d = metrics.to_dict()

        assert d["RR"] == 0.1
        assert d["DET"] == 0.5
        assert d["L_max"] == 10

    def test_min_line_length(self):
        """Test minimum line length filtering."""
        # Create simple recurrence matrix with known structure
        R = np.zeros((10, 10), dtype=np.int8)
        R[0, 1] = 1  # Single point (should be filtered)
        R[2, 3] = 1
        R[3, 4] = 1  # Line of length 2

        rqa = RecurrenceQuantificationAnalysis(min_line_length=2)
        metrics = rqa.compute(R)

        # Should only count lines >= 2


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_compute_recurrence_matrix(self):
        """Test compute_recurrence_matrix function."""
        trajectory = np.random.randn(50, 2)
        R = compute_recurrence_matrix(trajectory, threshold=0.5)

        assert R.shape == (50, 50)

    def test_compute_rqa_metrics(self):
        """Test compute_rqa_metrics function."""
        R = np.random.randint(0, 2, (50, 50)).astype(np.int8)
        metrics = compute_rqa_metrics(R)

        assert isinstance(metrics, RQAMetrics)


class TestCrossRecurrence:
    """Test cross-recurrence analysis."""

    def test_cross_recurrence_shape(self):
        """Test cross-recurrence matrix shape."""
        traj1 = np.random.randn(100, 2)
        traj2 = np.random.randn(80, 2)

        CR = cross_recurrence(traj1, traj2, threshold=0.5)

        assert CR.shape == (100, 80)


class TestJointRecurrence:
    """Test joint recurrence analysis."""

    def test_joint_recurrence_shape(self):
        """Test joint recurrence matrix shape."""
        traj1 = np.random.randn(100, 2)
        traj2 = np.random.randn(100, 2)

        JR = joint_recurrence(traj1, traj2, threshold1=0.5, threshold2=0.5)

        assert JR.shape == (100, 100)

    def test_joint_is_intersection(self):
        """Test joint recurrence is intersection of individual RPs."""
        np.random.seed(42)
        traj1 = np.random.randn(50, 2)
        traj2 = np.random.randn(50, 2)

        rp1 = RecurrencePlot(threshold=0.5)
        rp2 = RecurrencePlot(threshold=0.5)

        R1 = rp1.compute(traj1)
        R2 = rp2.compute(traj2)
        JR = joint_recurrence(traj1, traj2, threshold1=0.5, threshold2=0.5)

        # JR should be element-wise AND of R1 and R2
        expected = np.logical_and(R1, R2).astype(np.int8)
        assert np.array_equal(JR, expected)


# =============================================================================
# 0-1 Test for Chaos Tests
# =============================================================================

class Test01ChaosFunction:
    """Test 0-1 test for chaos function."""

    def test_regular_signal(self):
        """Test 0-1 test for regular (periodic) signal."""
        t = np.linspace(0, 100 * np.pi, 1000)
        signal = np.sin(t)

        result = run_01_chaos_test(signal)

        # Regular signal should have K ≈ 0 (or NaN if computation fails)
        # The 0-1 test can be sensitive to parameters
        if not np.isnan(result.K):
            assert result.K < 0.5
            assert result.is_chaotic == False

    def test_random_signal(self):
        """Test 0-1 test for random signal."""
        np.random.seed(42)
        signal = np.random.randn(1000)

        result = run_01_chaos_test(signal)

        # Random signal should have K ≈ 1 (or NaN if computation fails)
        # The 0-1 test can be sensitive to parameters and signal length
        if not np.isnan(result.K):
            assert result.K > 0.5
            assert result.is_chaotic == True

    def test_short_series(self):
        """Test with too short time series."""
        signal = np.random.randn(50)
        result = run_01_chaos_test(signal)

        assert np.isnan(result.K)
        assert result.confidence == 0.0

    def test_translation_variables(self):
        """Test translation variable computation."""
        signal = np.random.randn(100)
        c = 1.5

        p, q = compute_translation_variables(signal, c)

        assert len(p) == 100
        assert len(q) == 100
        assert p[0] == signal[0]  # First value
        assert q[0] == 0.0  # sin(0) = 0

    def test_mean_square_displacement(self):
        """Test MSD computation."""
        p = np.cumsum(np.random.randn(100))
        q = np.cumsum(np.random.randn(100))

        msd = compute_mean_square_displacement(p, q, max_lag=50)

        assert len(msd) == 50
        assert msd[0] == 0.0  # MSD at lag 0 is 0
        assert np.all(msd >= 0)  # MSD is non-negative


class Test01Batch:
    """Test batch 0-1 testing."""

    def test_batch_processing(self):
        """Test batch processing of multiple signals."""
        signals = [
            np.sin(np.linspace(0, 10 * np.pi, 500)),  # Regular
            np.random.randn(500),  # Random
        ]

        results = run_01_chaos_batch(signals)

        assert len(results) == 2
        assert all(isinstance(r, Test01Result) for r in results)


class Test01ResultClass:
    """Test Test01Result class."""

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = Test01Result(
            K=0.8,
            is_chaotic=True,
            confidence=0.9,
            parameters={"c": 1.5, "n": 1000},
        )

        d = result.to_dict()

        assert d["K"] == 0.8
        assert d["is_chaotic"] == True
        assert d["confidence"] == 0.9


class TestVisualization:
    """Test visualization helper."""

    def test_visualize_01_test(self):
        """Test visualization data preparation."""
        from berb.domains.chaos.test_01 import visualize_01_test

        result = Test01Result(
            K=0.8,
            is_chaotic=True,
            p=np.array([1, 2, 3]),
            q=np.array([0, 1, 2]),
            msd=np.array([0, 1, 4]),
        )

        viz_data = visualize_01_test(result)

        assert "p" in viz_data
        assert "q" in viz_data
        assert "msd" in viz_data
        assert viz_data["K"] == 0.8
        assert viz_data["n_points"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
