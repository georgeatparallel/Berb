"""Chaos detection and analysis tools for dynamical systems.

This module provides:
- Lyapunov exponent computation (chaos detection)
- Bifurcation diagram generation
- Poincaré section computation
- Additional chaos indices (coming soon)

Usage:
    from berb.domains.chaos import (
        LyapunovExponentCalculator,
        BifurcationDiagram,
        PoincareSection,
        compute_lyapunov_exponents,
        is_chaotic,
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
]
