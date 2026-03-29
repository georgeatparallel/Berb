"""Physics domain module for Berb."""

from berb.domains.physics.hamiltonian import (
    VerletIntegrator,
    YoshidaIntegrator,
    HarmonicOscillator,
    Pendulum,
    HenonHeiles,
    DoublePendulum,
    PhaseSpaceAnalyzer,
    create_integrator,
    create_system,
    IntegrationResult,
    HamiltonianSystem,
    SymplecticIntegrator,
)

__all__ = [
    # Integrators
    "VerletIntegrator",
    "YoshidaIntegrator",
    "SymplecticIntegrator",
    # Systems
    "HarmonicOscillator",
    "Pendulum",
    "HenonHeiles",
    "DoublePendulum",
    "HamiltonianSystem",
    # Analysis
    "PhaseSpaceAnalyzer",
    # Results
    "IntegrationResult",
    # Factory
    "create_integrator",
    "create_system",
]
