"""Chaos detection and analysis tools for dynamical systems.

This module provides:
- Lyapunov exponent computation (chaos detection)
- Bifurcation diagram generation
- Poincaré section computation
- Advanced chaos indices (entropy, recurrence, 0-1 test)

Usage:
    from berb.domains.chaos import (
        LyapunovExponentCalculator,
        BifurcationDiagram,
        PoincareSection,
        compute_lyapunov_exponents,
        is_chaotic,
        kolmogorov_sinai_entropy,
        correlation_dimension,
        sample_entropy,
        permutation_entropy,
        RecurrencePlot,
        RecurrenceQuantificationAnalysis,
        test_01_chaos,
    )

    # Check if Lorenz system is chaotic
    def lorenz(t, y):
        sigma, rho, beta = 10, 28, 8/3
        return [sigma*(y[1]-y[0]), y[0]*(rho-y[2])-y[1], y[0]*y[1]-beta*y[2]]

    def lorenz_jacobian(t, y):
        sigma, rho, beta = 10, 28, 8/3
        return np.array([
            [-sigma, sigma, 0],
            [rho-y[2], -1, -y[0]],
            [y[1], y[0], -beta]
        ])

    result = compute_lyapunov_exponents(lorenz, lorenz_jacobian, [1, 1, 1], (0, 100))
    print(f"Is chaotic: {result.is_chaotic}")  # True
    print(f"λ₁ = {result.max_exponent:.4f}")   # ~0.9056

    # Advanced chaos indices
    ks_result = kolmogorov_sinai_entropy([0.9, 0.0, -2.5])
    print(f"KS entropy: {ks_result.value:.3f}")

    sampen_result = sample_entropy(time_series)
    print(f"Sample entropy: {sampen_result.value:.3f}")

    chaos_test = test_01_chaos(signal)
    print(f"0-1 test K: {chaos_test.K:.3f}")  # ~1 for chaotic
"""

from .lyapunov import (
    LyapunovExponentCalculator,
    LyapunovResult,
    compute_lyapunov_exponents,
    is_chaotic,
)
from .bifurcation import (
    BifurcationDiagram,
    BifurcationResult,
)
from .poincare import (
    PoincareSection,
    PoincareResult,
    compute_poincare_section,
    hamiltonian_poincare_section,
)
from .entropy import (
    kolmogorov_sinai_entropy,
    correlation_dimension,
    approximate_entropy,
    sample_entropy,
    permutation_entropy,
    EntropyResult,
)
from .recurrence import (
    RecurrencePlot,
    RecurrenceQuantificationAnalysis,
    compute_recurrence_matrix,
    compute_rqa_metrics,
    cross_recurrence,
    joint_recurrence,
    RQAMetrics,
    RecurrenceResult,
)
from .test_01 import (
    run_01_chaos_test,
    run_01_chaos_batch,
    compute_translation_variables,
    compute_mean_square_displacement,
    Test01Result,
)

__all__ = [
    # Lyapunov exponents
    "LyapunovExponentCalculator",
    "LyapunovResult",
    "compute_lyapunov_exponents",
    "is_chaotic",

    # Bifurcation diagrams
    "BifurcationDiagram",
    "BifurcationResult",

    # Poincaré sections
    "PoincareSection",
    "PoincareResult",
    "compute_poincare_section",
    "hamiltonian_poincare_section",

    # Entropy measures
    "kolmogorov_sinai_entropy",
    "correlation_dimension",
    "approximate_entropy",
    "sample_entropy",
    "permutation_entropy",
    "EntropyResult",

    # Recurrence analysis
    "RecurrencePlot",
    "RecurrenceQuantificationAnalysis",
    "compute_recurrence_matrix",
    "compute_rqa_metrics",
    "cross_recurrence",
    "joint_recurrence",
    "RQAMetrics",
    "RecurrenceResult",

    # 0-1 test for chaos
    "test_01_chaos",
    "test_01_batch",
    "compute_translation_variables",
    "compute_mean_square_displacement",
    "Test01Result",
]
