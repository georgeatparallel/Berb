"""0-1 test for chaos.

A simple binary test that distinguishes chaotic from regular dynamics
directly from time series data, without phase space reconstruction.

The test returns K ≈ 0 for regular dynamics and K ≈ 1 for chaotic dynamics.

Algorithm:
1. Compute translation variables p(n), q(n) from time series
2. Analyze asymptotic growth rate of mean square displacement
3. K = 0 (regular) or K = 1 (chaotic)

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.chaos.test_01 import (
        test_01_chaos,
        compute_translation_variables,
        compute_mean_square_displacement,
    )

    # Test if signal is chaotic
    result = test_01_chaos(time_series)
    print(f"K = {result.K:.3f}")  # ~0 for regular, ~1 for chaotic
    print(f"Is chaotic: {result.is_chaotic}")

    # Lorenz system (chaotic): K ≈ 0.9-1.0
    # Harmonic oscillator (regular): K ≈ 0.0-0.1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Test01Result:
    """Result from 0-1 test for chaos.

    Attributes:
        K: Asymptotic growth rate (0=regular, 1=chaotic)
        is_chaotic: Whether dynamics appear chaotic
        confidence: Confidence score (0-1)
        p: Translation variable p(n)
        q: Translation variable q(n)
        msd: Mean square displacement
        parameters: Parameters used
        warnings: List of warnings
    """

    K: float = 0.0
    is_chaotic: bool = False
    confidence: float = 1.0
    p: np.ndarray = None
    q: np.ndarray = None
    msd: np.ndarray = None
    parameters: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "K": self.K,
            "is_chaotic": self.is_chaotic,
            "confidence": self.confidence,
            "parameters": self.parameters,
            "warnings": self.warnings,
        }


def run_01_chaos_test(
    time_series: np.ndarray,
    c: float = None,
    n_samples: int = 1000,
    cutoff: int = 100,
) -> Test01Result:
    """
    Perform 0-1 test for chaos.

    Args:
        time_series: Input time series (1D array)
        c: Translation parameter (default: random in (0, 2π))
        n_samples: Number of samples to use
        cutoff: Initial transient to discard

    Returns:
        Test01Result with K value and chaos determination

    Example:
        >>> # Regular signal (periodic)
        >>> result = test_01_chaos(np.sin(np.linspace(0, 100*np.pi, 1000)))
        >>> print(f"K = {result.K:.3f}")  # ~0.0
        >>> print(f"Is chaotic: {result.is_chaotic}")  # False

        >>> # Chaotic signal (Lorenz)
        >>> result = test_01_chaos(lorenz_x)
        >>> print(f"K = {result.K:.3f}")  # ~0.9-1.0
        >>> print(f"Is chaotic: {result.is_chaotic}")  # True
    """
    # Validate input
    if len(time_series) < 100:
        return Test01Result(
            K=np.nan,
            confidence=0.0,
            warnings=["Time series too short (need >100 points)"],
        )

    # Use subset of data
    if len(time_series) > n_samples:
        time_series = time_series[:n_samples]

    n = len(time_series)

    # Choose translation parameter
    if c is None:
        c = np.random.uniform(0, 2 * np.pi)

    # Compute translation variables
    p, q = compute_translation_variables(time_series, c)

    # Compute mean square displacement
    msd = compute_mean_square_displacement(p, q)

    # Compute asymptotic growth rate K
    # Use linear regression on log(MSD) vs log(n)
    n_vals = np.arange(cutoff, n)
    msd_vals = msd[cutoff:]

    # Filter out zeros and negative values
    valid = msd_vals > 0
    if np.sum(valid) < 10:
        return Test01Result(
            K=np.nan,
            confidence=0.0,
            warnings=["Insufficient valid MSD values"],
        )

    log_n = np.log(n_vals[valid])
    log_msd = np.log(msd_vals[valid])

    # Linear regression
    try:
        coeffs = np.polyfit(log_n, log_msd, 1)
        K = coeffs[0]  # Slope is the growth rate
    except Exception as e:
        logger.warning(f"Linear regression failed: {e}")
        K = np.nan

    # K should be in [0, 1]
    K = np.clip(K, 0, 1)

    # Determine if chaotic
    is_chaotic = K > 0.5

    # Confidence based on K value (high confidence near 0 or 1)
    confidence = 1.0 - 2.0 * abs(K - 0.5)

    return Test01Result(
        K=float(K),
        is_chaotic=is_chaotic,
        confidence=float(confidence),
        p=p,
        q=q,
        msd=msd,
        parameters={"c": c, "n": n, "cutoff": cutoff},
    )


def compute_translation_variables(
    time_series: np.ndarray,
    c: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute translation variables p(n) and q(n).

    p(n) = Σ φ(j) cos(j·c)
    q(n) = Σ φ(j) sin(j·c)

    where φ is the observable (time series).

    Args:
        time_series: Input time series
        c: Translation parameter

    Returns:
        Tuple of (p, q) arrays
    """
    n = len(time_series)
    p = np.zeros(n)
    q = np.zeros(n)

    # Cumulative sum approach (more efficient)
    indices = np.arange(n)

    p = np.cumsum(time_series * np.cos(indices * c))
    q = np.cumsum(time_series * np.sin(indices * c))

    return p, q


def compute_mean_square_displacement(
    p: np.ndarray,
    q: np.ndarray,
    max_lag: int = None,
) -> np.ndarray:
    """
    Compute mean square displacement (MSD).

    MSD(n) = lim_{N→∞} (1/N) Σ [p(j+n) - p(j)]² + [q(j+n) - q(j)]²

    Args:
        p: Translation variable p(n)
        q: Translation variable q(n)
        max_lag: Maximum lag to compute (default: n/10)

    Returns:
        MSD array for lags 1 to max_lag
    """
    n = len(p)

    if max_lag is None:
        max_lag = n // 10

    max_lag = min(max_lag, n - 1)

    msd = np.zeros(max_lag)

    for lag in range(1, max_lag):
        # Compute displacement
        dp = p[lag:] - p[:-lag]
        dq = q[lag:] - q[:-lag]

        # Mean square displacement
        msd[lag] = np.mean(dp**2 + dq**2)

    return msd


def compute_modified_msd(
    p: np.ndarray,
    q: np.ndarray,
    max_lag: int = None,
) -> np.ndarray:
    """
    Compute modified mean square displacement.

    Uses windowing to reduce noise in MSD estimation.
    Recommended for noisy or short time series.

    Args:
        p: Translation variable p(n)
        q: Translation variable q(n)
        max_lag: Maximum lag

    Returns:
        Modified MSD array
    """
    n = len(p)

    if max_lag is None:
        max_lag = n // 10

    max_lag = min(max_lag, n - 1)

    msd = np.zeros(max_lag)

    # Window size for averaging
    window_size = max(10, n // 100)

    for lag in range(1, max_lag):
        displacements = []

        # Average over windows
        for start in range(0, n - lag, window_size):
            end = min(start + window_size, n - lag)
            if end <= start:
                continue

            dp = p[start:end] - p[start - lag:end - lag] if start >= lag else p[start:end]
            dq = q[start:end] - q[start - lag:end - lag] if start >= lag else q[start:end]

            displacements.append(np.mean(dp**2 + dq**2))

        if displacements:
            msd[lag] = np.mean(displacements)

    return msd


def run_01_chaos_batch(
    time_series_list: list[np.ndarray],
    c: float = None,
) -> list[Test01Result]:
    """
    Perform 0-1 test on multiple time series.

    Args:
        time_series_list: List of time series
        c: Translation parameter (shared or None for random)

    Returns:
        List of Test01Result
    """
    results = []

    for ts in time_series_list:
        result = test_01_chaos(ts, c=c)
        results.append(result)

    return results


def visualize_01_test(result: Test01Result) -> dict:
    """
    Prepare visualization data for 0-1 test.

    Args:
        result: Test01Result

    Returns:
        Dictionary with plotting data
    """
    n = len(result.p) if result.p is not None else 0

    return {
        "p": result.p.tolist() if result.p is not None else [],
        "q": result.q.tolist() if result.q is not None else [],
        "msd": result.msd.tolist() if result.msd is not None else [],
        "K": result.K,
        "is_chaotic": result.is_chaotic,
        "n_points": n,
    }


# Backward compatibility aliases
test_01_chaos = run_01_chaos_test
test_01_batch = run_01_chaos_batch
