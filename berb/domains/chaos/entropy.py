"""Advanced chaos indices and entropy measures.

Provides:
- Kolmogorov-Sinai (KS) entropy estimation
- Correlation dimension computation
- Approximate entropy (ApEn)
- Sample entropy (SampEn)
- Permutation entropy

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.chaos.entropy import (
        kolmogorov_sinai_entropy,
        correlation_dimension,
        approximate_entropy,
        sample_entropy,
        permutation_entropy,
    )

    # Compute KS entropy from Lyapunov exponents
    ks_entropy = kolmogorov_sinai_entropy([0.9, 0.0, -2.5])

    # Correlation dimension from trajectory
    D2 = correlation_dimension(trajectory)

    # Sample entropy for time series
    sampen = sample_entropy(time_series)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.spatial.distance import cdist

logger = logging.getLogger(__name__)


@dataclass
class EntropyResult:
    """Result from entropy computation.

    Attributes:
        value: Entropy value
        method: Computation method used
        confidence: Confidence score (0-1)
        parameters: Parameters used
        warnings: List of warnings
    """

    value: float
    method: str
    confidence: float = 1.0
    parameters: dict = None
    warnings: list[str] = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.warnings is None:
            self.warnings = []


def kolmogorov_sinai_entropy(lyapunov_exponents: Sequence[float]) -> EntropyResult:
    """
    Compute Kolmogorov-Sinai entropy from Lyapunov exponents.

    KS entropy = sum of positive Lyapunov exponents (Pesin's identity)

    Args:
        lyapunov_exponents: List of Lyapunov exponents

    Returns:
        EntropyResult with KS entropy value

    Example:
        >>> result = kolmogorov_sinai_entropy([0.9056, 0.0, -2.5])
        >>> print(f"KS entropy: {result.value:.4f}")  # ~0.9056
    """
    lyap = np.array(lyapunov_exponents)
    positive_lyap = lyap[lyap > 0]

    ks_entropy = float(np.sum(positive_lyap))

    # Confidence based on number of exponents
    confidence = min(1.0, len(lyapunov_exponents) / 3.0)

    warnings = []
    if len(lyapunov_exponents) < 2:
        warnings.append("Few exponents provided - result may be incomplete")

    return EntropyResult(
        value=ks_entropy,
        method="pesin_identity",
        confidence=confidence,
        parameters={"n_exponents": len(lyapunov_exponents)},
        warnings=warnings,
    )


def correlation_dimension(
    trajectory: np.ndarray,
    r_min: float | None = None,
    r_max: float | None = None,
    n_points: int = 1000,
) -> EntropyResult:
    """
    Estimate correlation dimension D₂ using Grassberger-Procaccia algorithm.

    The correlation dimension measures the fractal dimension of the attractor.

    Args:
        trajectory: Trajectory array (n_points, n_dims)
        r_min: Minimum radius for scaling (default: auto)
        r_max: Maximum radius for scaling (default: auto)
        n_points: Number of points to use

    Returns:
        EntropyResult with correlation dimension

    Example:
        >>> # Lorenz attractor
        >>> D2 = correlation_dimension(lorenz_trajectory)
        >>> print(f"D₂ ≈ {result.value:.2f}")  # ~2.06 for Lorenz
    """
    if len(trajectory) < 100:
        return EntropyResult(
            value=np.nan,
            method="grassberger_procaccia",
            confidence=0.0,
            warnings=["Trajectory too short (need >100 points)"],
        )

    # Subsample if needed
    if len(trajectory) > n_points:
        indices = np.random.choice(len(trajectory), n_points, replace=False)
        trajectory = trajectory[indices]

    n_points = len(trajectory)

    # Compute pairwise distances
    distances = cdist(trajectory, trajectory, metric="euclidean")

    # Set radius range
    if r_min is None:
        r_min = np.percentile(distances[distances > 0], 1)
    if r_max is None:
        r_max = np.percentile(distances, 90)

    # Compute correlation integral for different radii
    n_radii = 20
    radii = np.logspace(np.log10(r_min), np.log10(r_max), n_radii)
    correlation_integrals = []

    for r in radii:
        # Count pairs within radius r
        C_r = np.sum(distances < r) / (n_points * (n_points - 1))
        correlation_integrals.append(C_r)

    correlation_integrals = np.array(correlation_integrals)

    # Fit slope in log-log plot (D₂ = d(ln C)/d(ln r))
    valid = correlation_integrals > 0
    if np.sum(valid) < 3:
        return EntropyResult(
            value=np.nan,
            method="grassberger_procaccia",
            confidence=0.0,
            warnings=["Insufficient valid scaling region"],
        )

    log_r = np.log(radii[valid])
    log_C = np.log(correlation_integrals[valid])

    # Linear fit
    coeffs = np.polyfit(log_r, log_C, 1)
    D2 = coeffs[0]

    # Goodness of fit
    log_C_fit = np.polyval(coeffs, log_r)
    r_squared = 1 - np.sum((log_C - log_C_fit) ** 2) / np.sum((log_C - np.mean(log_C)) ** 2)

    confidence = max(0.0, min(1.0, r_squared))

    return EntropyResult(
        value=float(D2),
        method="grassberger_procaccia",
        confidence=confidence,
        parameters={
            "r_min": r_min,
            "r_max": r_max,
            "n_points": n_points,
            "r_squared": float(r_squared),
        },
    )


def approximate_entropy(
    time_series: np.ndarray,
    m: int = 2,
    r: float | None = None,
) -> EntropyResult:
    """
    Compute approximate entropy (ApEn).

    ApEn measures the regularity/complexity of a time series.
    Lower ApEn = more regular/predictable
    Higher ApEn = more complex/unpredictable

    Args:
        time_series: Input time series
        m: Pattern length (embedding dimension)
        r: Tolerance threshold (default: 0.2 * std)

    Returns:
        EntropyResult with ApEn value

    Example:
        >>> # Regular signal (low ApEn)
        >>> apen = approximate_entropy(np.sin(np.linspace(0, 10*np.pi, 1000)))
        >>> print(f"ApEn ≈ {result.value:.3f}")  # ~0.1-0.3

        >>> # Random signal (high ApEn)
        >>> apen = approximate_entropy(np.random.randn(1000))
        >>> print(f"ApEn ≈ {result.value:.3f}")  # ~1.5-2.0
    """
    n = len(time_series)

    if n < 10 ** m:
        return EntropyResult(
            value=np.nan,
            method="approximate_entropy",
            confidence=0.0,
            warnings=["Time series too short for reliable ApEn"],
        )

    if r is None:
        r = 0.2 * np.std(time_series)

    # Form template vectors
    def form_vectors(x: np.ndarray, m: int) -> np.ndarray:
        n_vec = len(x) - m + 1
        vectors = np.zeros((n_vec, m))
        for i in range(n_vec):
            vectors[i] = x[i : i + m]
        return vectors

    X_m = form_vectors(time_series, m)
    X_m1 = form_vectors(time_series, m + 1)

    # Count matches within tolerance r
    def count_matches(vectors: np.ndarray, r: float) -> float:
        n = len(vectors)
        matches = np.zeros(n)

        for i in range(n):
            # Distance to all other vectors (Chebyshev distance)
            distances = np.max(np.abs(vectors - vectors[i]), axis=1)
            # Count matches (excluding self)
            matches[i] = np.sum((distances <= r) & (np.arange(n) != i))

        return np.mean(matches / (n - 1))

    C_m = count_matches(X_m, r)
    C_m1 = count_matches(X_m1, r)

    if C_m <= 0 or C_m1 <= 0:
        return EntropyResult(
            value=np.nan,
            method="approximate_entropy",
            confidence=0.0,
            warnings=["No matches found - try larger r or longer series"],
        )

    apen = -np.log(C_m1 / C_m)

    return EntropyResult(
        value=float(apen),
        method="approximate_entropy",
        confidence=0.8,
        parameters={"m": m, "r": r, "n": n},
    )


def sample_entropy(
    time_series: np.ndarray,
    m: int = 2,
    r: float | None = None,
) -> EntropyResult:
    """
    Compute sample entropy (SampEn).

    Improved version of ApEn that is less biased and more consistent.
    Lower SampEn = more regular
    Higher SampEn = more complex

    Args:
        time_series: Input time series
        m: Pattern length (embedding dimension)
        r: Tolerance threshold (default: 0.2 * std)

    Returns:
        EntropyResult with SampEn value

    Example:
        >>> sampen = sample_entropy(heartbeat_intervals)
        >>> print(f"SampEn ≈ {result.value:.3f}")
    """
    n = len(time_series)

    if n < 10 ** m:
        return EntropyResult(
            value=np.nan,
            method="sample_entropy",
            confidence=0.0,
            warnings=["Time series too short for reliable SampEn"],
        )

    if r is None:
        r = 0.2 * np.std(time_series)

    # Form template vectors
    def form_vectors(x: np.ndarray, m: int) -> np.ndarray:
        n_vec = len(x) - m + 1
        vectors = np.zeros((n_vec, m))
        for i in range(n_vec):
            vectors[i] = x[i : i + m]
        return vectors

    X_m = form_vectors(time_series, m)
    X_m1 = form_vectors(time_series, m + 1)

    n_m = len(X_m)
    n_m1 = len(X_m1)

    # Count template matches (excluding self-matches)
    def count_matches_nodiag(vectors: np.ndarray, r: float) -> int:
        n = len(vectors)
        total_matches = 0

        for i in range(n - 1):
            for j in range(i + 1, n):
                dist = np.max(np.abs(vectors[i] - vectors[j]))
                if dist < r:
                    total_matches += 1

        return total_matches

    A = count_matches_nodiag(X_m1, r)  # Matches of length m+1
    B = count_matches_nodiag(X_m, r)   # Matches of length m

    if B == 0:
        return EntropyResult(
            value=np.nan,
            method="sample_entropy",
            confidence=0.0,
            warnings=["No matches found - try larger r"],
        )

    sampen = -np.log(A / B)

    return EntropyResult(
        value=float(sampen),
        method="sample_entropy",
        confidence=0.9,
        parameters={"m": m, "r": r, "n": n},
    )


def permutation_entropy(
    time_series: np.ndarray,
    order: int = 3,
    delay: int = 1,
) -> EntropyResult:
    """
    Compute permutation entropy (PE).

    PE measures complexity based on ordinal patterns.
    Robust to noise and computationally efficient.

    Args:
        time_series: Input time series
        order: Order of permutation entropy (3-7 typical)
        delay: Time delay for embedding

    Returns:
        EntropyResult with normalized PE value (0-1)

    Example:
        >>> pe = permutation_entropy(chaotic_signal)
        >>> print(f"PE ≈ {result.value:.3f}")  # 0=regular, 1=complex
    """
    n = len(time_series)
    m = order

    # Check length
    min_length = math.factorial(m) * delay
    if n < min_length:
        return EntropyResult(
            value=np.nan,
            method="permutation_entropy",
            confidence=0.0,
            warnings=["Time series too short for given order"],
        )

    # Form embedding vectors
    n_vectors = n - (m - 1) * delay
    vectors = np.zeros((n_vectors, m))

    for i in range(m):
        vectors[:, i] = time_series[i * delay : i * delay + n_vectors]

    # Get ordinal patterns (rank order)
    patterns = np.argsort(vectors, axis=1)

    # Count pattern frequencies
    n_patterns = math.factorial(m)
    pattern_counts = np.zeros(n_patterns)

    for pattern in patterns:
        # Convert pattern to index
        idx = 0
        for i, p in enumerate(pattern):
            idx += p * math.factorial(i)
        pattern_counts[idx] += 1

    # Normalize to probabilities
    probs = pattern_counts / n_vectors

    # Remove zeros for entropy calculation
    probs = probs[probs > 0]

    # Compute Shannon entropy
    H = -np.sum(probs * np.log(probs))

    # Normalize by maximum entropy
    H_max = np.log(n_patterns)
    PE = H / H_max if H_max > 0 else 0.0

    return EntropyResult(
        value=float(PE),
        method="permutation_entropy",
        confidence=0.95,
        parameters={"order": order, "delay": delay, "n": n},
    )
