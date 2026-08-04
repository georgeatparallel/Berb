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

.. deprecated::
    This numerical-library subpackage has zero production callers in the
    pipeline (verified via ``scripts/check_reachability.py``). It is retained
    only for its test suite and is scheduled for removal. Do not add new
    dependencies on it. Decision recorded as D-01 in ``implementation_plan2.md``
    (deprecated 2026-07-19). If the physics/chaos vertical is revived, remove
    this notice and wire it through ``berb/domains/detector.py``.
"""

import warnings

warnings.warn(
    "berb.domains.physics is deprecated (D-01, 2026-07-19): no production "
    "callers; scheduled for removal. See implementation_plan2.md.",
    DeprecationWarning,
    stacklevel=2,
)

from berb.domains.physics.hamiltonian import (
    DoublePendulum,
    HamiltonianSystem,
    HarmonicOscillator,
    HenonHeiles,
    IntegrationResult,
    Pendulum,
    PhaseSpaceAnalyzer,
    SymplecticIntegrator,
    VerletIntegrator,
    YoshidaIntegrator,
    create_integrator,
    create_system,
)
from berb.domains.physics.integrators import (
    AdaptiveVerletIntegrator,
    IntegrationState,
    IntegrationStats,
)
from berb.domains.physics.templates import (
    TEMPLATES,
    CoupledOscillators,
    DuffingOscillator,
    KeplerProblem,
    SimplePendulum,
    StandardMap,
    get_template,
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
