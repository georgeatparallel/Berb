"""Recurrence plots and Recurrence Quantification Analysis (RQA).

Provides:
- Recurrence plot generation
- RQA metrics (RR, DET, LAM, L_max, etc.)
- Cross-recurrence analysis
- Joint recurrence analysis

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.chaos.recurrence import (
        RecurrencePlot,
        RecurrenceQuantificationAnalysis,
        compute_recurrence_matrix,
        compute_rqa_metrics,
    )

    # Generate recurrence plot
    rp = RecurrencePlot(threshold=0.1)
    recurrence_matrix = rp.compute(trajectory)

    # Compute RQA metrics
    rqa = RecurrenceQuantificationAnalysis()
    metrics = rqa.compute(recurrence_matrix)
    print(f"Recurrence rate: {metrics.RR:.3f}")
    print(f"Determinism: {metrics.DET:.3f}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.spatial.distance import cdist

logger = logging.getLogger(__name__)


@dataclass
class RQAMetrics:
    """Recurrence Quantification Analysis metrics.

    Attributes:
        RR: Recurrence rate (density of recurrence points)
        DET: Determinism (ratio of diagonal lines)
        L_max: Length of longest diagonal line
        L_mean: Mean diagonal line length
        DIV: Divergence (1/L_max)
        ENTR: Entropy (complexity of diagonal lines)
        LAM: Laminarity (ratio of vertical lines)
        V_max: Length of longest vertical line
        V_mean: Mean vertical line length
        TT: Trapping time (mean vertical line length)
    """

    RR: float = 0.0
    """Recurrence rate"""

    DET: float = 0.0
    """Determinism"""

    L_max: float = 0.0
    """Longest diagonal line"""

    L_mean: float = 0.0
    """Mean diagonal line length"""

    DIV: float = 0.0
    """Divergence (1/L_max)"""

    ENTR: float = 0.0
    """Entropy of diagonal lines"""

    LAM: float = 0.0
    """Laminarity"""

    V_max: float = 0.0
    """Longest vertical line"""

    V_mean: float = 0.0
    """Mean vertical line length"""

    TT: float = 0.0
    """Trapping time"""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "RR": self.RR,
            "DET": self.DET,
            "L_max": self.L_max,
            "L_mean": self.L_mean,
            "DIV": self.DIV,
            "ENTR": self.ENTR,
            "LAM": self.LAM,
            "V_max": self.V_max,
            "V_mean": self.V_mean,
            "TT": self.TT,
        }


@dataclass
class RecurrenceResult:
    """Result from recurrence analysis.

    Attributes:
        recurrence_matrix: Binary recurrence matrix
        metrics: RQA metrics
        parameters: Parameters used
        warnings: List of warnings
    """

    recurrence_matrix: np.ndarray
    metrics: RQAMetrics
    parameters: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class RecurrencePlot:
    """Recurrence plot generator.

    A recurrence plot visualizes when a state recurs (returns close to
    a previous state).

    R(i,j) = Θ(ε - ||x(i) - x(j)||)

    where Θ is the Heaviside step function.

    Attributes:
        threshold: Recurrence threshold ε
        metric: Distance metric ('euclidean', 'manhattan', etc.)
        include_diagonal: Include main diagonal (default: False)
    """

    def __init__(
        self,
        threshold: float = 0.1,
        metric: str = "euclidean",
        include_diagonal: bool = False,
    ):
        """
        Initialize recurrence plot.

        Args:
            threshold: Recurrence threshold ε
            metric: Distance metric for cdist
            include_diagonal: Include main diagonal
        """
        self.threshold = threshold
        self.metric = metric
        self.include_diagonal = include_diagonal

    def compute(self, trajectory: np.ndarray) -> np.ndarray:
        """
        Compute recurrence matrix.

        Args:
            trajectory: Trajectory array (n_points, n_dims)

        Returns:
            Binary recurrence matrix (n_points, n_points)
        """
        n_points = len(trajectory)

        # Compute pairwise distances
        distances = cdist(trajectory, trajectory, metric=self.metric)

        # Apply threshold
        recurrence = (distances <= self.threshold).astype(np.int8)

        # Remove diagonal if not requested
        if not self.include_diagonal:
            np.fill_diagonal(recurrence, 0)

        return recurrence

    def compute_adaptive(
        self,
        trajectory: np.ndarray,
        recurrence_rate: float = 0.05,
    ) -> np.ndarray:
        """
        Compute recurrence matrix with adaptive threshold.

        Adjusts threshold to achieve target recurrence rate.

        Args:
            trajectory: Trajectory array
            recurrence_rate: Target recurrence rate (0-1)

        Returns:
            Binary recurrence matrix
        """
        distances = cdist(trajectory, trajectory, metric=self.metric)

        # Remove diagonal for threshold calculation
        distances_no_diag = distances.copy()
        np.fill_diagonal(distances_no_diag, np.inf)

        # Find threshold for target recurrence rate
        flat_distances = distances_no_diag.flatten()
        threshold = np.percentile(flat_distances, recurrence_rate * 100)

        self.threshold = threshold
        return self.compute(trajectory)


class RecurrenceQuantificationAnalysis:
    """Recurrence Quantification Analysis (RQA).

    Extracts quantitative measures from recurrence plots:
    - Recurrence rate (RR): Density of recurrence points
    - Determinism (DET): Ratio of points forming diagonal lines
    - Laminarity (LAM): Ratio of points forming vertical lines
    - Entropy (ENTR): Complexity of recurrence structure
    - Divergence (DIV): Inverse of longest diagonal line

    Attributes:
        min_line_length: Minimum line length for analysis
    """

    def __init__(self, min_line_length: int = 2):
        """
        Initialize RQA.

        Args:
            min_line_length: Minimum line length to consider
        """
        self.min_line_length = min_line_length

    def compute(self, recurrence_matrix: np.ndarray) -> RQAMetrics:
        """
        Compute RQA metrics.

        Args:
            recurrence_matrix: Binary recurrence matrix

        Returns:
            RQA metrics
        """
        n = len(recurrence_matrix)
        total_points = np.sum(recurrence_matrix)

        # Recurrence rate
        RR = total_points / (n * n) if n > 0 else 0.0

        # Find diagonal and vertical lines
        diag_lines = self._find_diagonal_lines(recurrence_matrix)
        vert_lines = self._find_vertical_lines(recurrence_matrix)

        # Filter by minimum length
        diag_lines = [l for l in diag_lines if l >= self.min_line_length]
        vert_lines = [l for l in vert_lines if l >= self.min_line_length]

        # Determinism (ratio of diagonal line points)
        if total_points > 0:
            det = sum(l * diag_lines.count(l) for l in set(diag_lines)) / total_points
        else:
            det = 0.0

        # Laminarity (ratio of vertical line points)
        if total_points > 0:
            lam = sum(l * vert_lines.count(l) for l in set(vert_lines)) / total_points
        else:
            lam = 0.0

        # Diagonal line statistics
        if diag_lines:
            L_max = max(diag_lines)
            L_mean = np.mean(diag_lines)
            DIV = 1.0 / L_max if L_max > 0 else 0.0

            # Entropy of diagonal line lengths
            unique, counts = np.unique(diag_lines, return_counts=True)
            probs = counts / np.sum(counts)
            ENTR = -np.sum(probs * np.log(probs + 1e-10))
        else:
            L_max = 0
            L_mean = 0
            DIV = 0
            ENTR = 0

        # Vertical line statistics
        if vert_lines:
            V_max = max(vert_lines)
            V_mean = np.mean(vert_lines)
            TT = V_mean  # Trapping time
        else:
            V_max = 0
            V_mean = 0
            TT = 0

        return RQAMetrics(
            RR=RR,
            DET=det,
            L_max=L_max,
            L_mean=L_mean,
            DIV=DIV,
            ENTR=ENTR,
            LAM=lam,
            V_max=V_max,
            V_mean=V_mean,
            TT=TT,
        )

    def _find_diagonal_lines(self, matrix: np.ndarray) -> list[int]:
        """Find all diagonal line lengths."""
        n = len(matrix)
        lines = []

        # Check all diagonals
        for k in range(-n + 1, n):
            diag = np.diag(matrix, k)
            lines.extend(self._find_line_lengths(diag))

        return lines

    def _find_vertical_lines(self, matrix: np.ndarray) -> list[int]:
        """Find all vertical line lengths."""
        lines = []
        for col in range(len(matrix)):
            lines.extend(self._find_line_lengths(matrix[:, col]))
        return lines

    def _find_line_lengths(self, binary_array: np.ndarray) -> list[int]:
        """Find lengths of all lines in binary array."""
        lengths = []
        current_length = 0

        for val in binary_array:
            if val:
                current_length += 1
            else:
                if current_length >= self.min_line_length:
                    lengths.append(current_length)
                current_length = 0

        # Don't forget last line
        if current_length >= self.min_line_length:
            lengths.append(current_length)

        return lengths


def compute_recurrence_matrix(
    trajectory: np.ndarray,
    threshold: float = 0.1,
    adaptive: bool = False,
    target_rr: float = 0.05,
) -> np.ndarray:
    """
    Convenience function to compute recurrence matrix.

    Args:
        trajectory: Trajectory array (n_points, n_dims)
        threshold: Recurrence threshold
        adaptive: Use adaptive threshold
        target_rr: Target recurrence rate for adaptive mode

    Returns:
        Binary recurrence matrix
    """
    rp = RecurrencePlot(threshold=threshold)

    if adaptive:
        return rp.compute_adaptive(trajectory, target_rr)
    else:
        return rp.compute(trajectory)


def compute_rqa_metrics(
    recurrence_matrix: np.ndarray,
    min_line_length: int = 2,
) -> RQAMetrics:
    """
    Convenience function to compute RQA metrics.

    Args:
        recurrence_matrix: Binary recurrence matrix
        min_line_length: Minimum line length

    Returns:
        RQA metrics
    """
    rqa = RecurrenceQuantificationAnalysis(min_line_length=min_line_length)
    return rqa.compute(recurrence_matrix)


def cross_recurrence(
    trajectory1: np.ndarray,
    trajectory2: np.ndarray,
    threshold: float = 0.1,
) -> np.ndarray:
    """
    Compute cross-recurrence plot between two trajectories.

    Useful for comparing two systems or detecting synchronization.

    Args:
        trajectory1: First trajectory (n1, d)
        trajectory2: Second trajectory (n2, d)
        threshold: Recurrence threshold

    Returns:
        Cross-recurrence matrix (n1, n2)
    """
    distances = cdist(trajectory1, trajectory2, metric="euclidean")
    return (distances <= threshold).astype(np.int8)


def joint_recurrence(
    trajectory1: np.ndarray,
    trajectory2: np.ndarray,
    threshold1: float = 0.1,
    threshold2: float = 0.1,
) -> np.ndarray:
    """
    Compute joint recurrence plot.

    JR(i,j) = R1(i,j) AND R2(i,j)

    Useful for detecting generalized synchronization.

    Args:
        trajectory1: First trajectory
        trajectory2: Second trajectory
        threshold1: Threshold for first system
        threshold2: Threshold for second system

    Returns:
        Joint recurrence matrix
    """
    rp1 = RecurrencePlot(threshold=threshold1)
    rp2 = RecurrencePlot(threshold=threshold2)

    R1 = rp1.compute(trajectory1)
    R2 = rp2.compute(trajectory2)

    # Element-wise AND
    return np.logical_and(R1, R2).astype(np.int8)
