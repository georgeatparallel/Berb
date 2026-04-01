"""Physics domain module for Berb.

Provides Hamiltonian mechanics tools including:
- Symplectic integrators (Verlet, Yoshida, Adaptive)
- Pre-built Hamiltonian system templates
- Phase space analysis tools

Usage:
    from berb.domains.physics import (
        VerletIntegrator,
        YoshidaIntegrator,
        AdaptiveVerletIntegrator,
        HarmonicOscillator,
        HenonHeiles,
        DoublePendulum,
        get_template,
    )

    # Use template system
    system = get_template("henon_heiles")
    integrator = VerletIntegrator(dt=0.01)
    trajectory = integrator.integrate(...)
"""

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
from berb.domains.physics.integrators import (
    AdaptiveVerletIntegrator,
    IntegrationState,
    IntegrationStats,
)
from berb.domains.physics.templates import (
    SimplePendulum,
    CoupledOscillators,
    DuffingOscillator,
    KeplerProblem,
    StandardMap,
    get_template,
    TEMPLATES,
)

__all__ = [
    # Integrators
    "VerletIntegrator",
    "YoshidaIntegrator",
    "AdaptiveVerletIntegrator",
    "SymplecticIntegrator",
    "IntegrationState",
    "IntegrationStats",

    # Systems (from hamiltonian.py)
    "HarmonicOscillator",
    "Pendulum",
    "HenonHeiles",
    "DoublePendulum",
    "HamiltonianSystem",

    # Systems (from templates.py)
    "SimplePendulum",
    "CoupledOscillators",
    "DuffingOscillator",
    "KeplerProblem",
    "StandardMap",

    # Template registry
    "get_template",
    "TEMPLATES",

    # Analysis
    "PhaseSpaceAnalyzer",

    # Results
    "IntegrationResult",

    # Factory
    "create_integrator",
    "create_system",
]
