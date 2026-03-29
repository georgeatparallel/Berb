"""Hamiltonian mechanics tools for physics domain.

Provides:
- Symplectic integrators (Verlet, Yoshida)
- Pre-built Hamiltonian system templates
- Phase space analysis tools

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.physics.hamiltonian import (
        VerletIntegrator,
        YoshidaIntegrator,
        HarmonicOscillator,
        Pendulum,
        HenonHeiles,
        PhaseSpaceAnalyzer,
    )

    # Symplectic integration
    integrator = VerletIntegrator(dt=0.01)
    trajectory = integrator.integrate(hamiltonian, initial_state, steps=1000)

    # Use template system
    system = HarmonicOscillator(m=1.0, k=1.0)
    energy = system.hamiltonian(q=1.0, p=0.0)

    # Phase space analysis
    analyzer = PhaseSpaceAnalyzer()
    plot = analyzer.plot_phase_space(trajectory)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IntegrationResult:
    """Result from numerical integration.

    Attributes:
        q: Position trajectory (n_steps, n_dims)
        p: Momentum trajectory (n_steps, n_dims)
        t: Time array (n_steps,)
        energy: Energy trajectory (n_steps,)
        success: Whether integration succeeded
        error: Error message if failed
        metadata: Additional metadata
    """

    q: np.ndarray = field(default_factory=lambda: np.array([]))
    p: np.ndarray = field(default_factory=lambda: np.array([]))
    t: np.ndarray = field(default_factory=lambda: np.array([]))
    energy: np.ndarray = field(default_factory=lambda: np.array([]))
    success: bool = True
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "q": self.q.tolist() if self.q.size > 0 else [],
            "p": self.p.tolist() if self.p.size > 0 else [],
            "t": self.t.tolist() if self.t.size > 0 else [],
            "energy": self.energy.tolist() if self.energy.size > 0 else [],
            "success": self.success,
            "error": self.error,
            "n_steps": len(self.t),
        }


class SymplecticIntegrator(ABC):
    """Abstract base class for symplectic integrators."""

    def __init__(self, dt: float = 0.01):
        """
        Initialize integrator.

        Args:
            dt: Time step
        """
        self.dt = dt

    @abstractmethod
    def step(
        self,
        hamiltonian: Callable,
        q: np.ndarray,
        p: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Perform single integration step.

        Args:
            hamiltonian: Hamiltonian function H(q, p)
            q: Current position
            p: Current momentum

        Returns:
            Tuple of (new_q, new_p)
        """
        pass

    def integrate(
        self,
        hamiltonian: Callable,
        q0: np.ndarray,
        p0: np.ndarray,
        steps: int = 1000,
    ) -> IntegrationResult:
        """
        Integrate Hamiltonian system.

        Args:
            hamiltonian: Hamiltonian function H(q, p)
            q0: Initial position
            p0: Initial momentum
            steps: Number of integration steps

        Returns:
            IntegrationResult with trajectories
        """
        n_dims = len(q0)
        q_traj = np.zeros((steps, n_dims))
        p_traj = np.zeros((steps, n_dims))
        t_traj = np.zeros(steps)
        energy_traj = np.zeros(steps)

        q, p = q0.copy(), p0.copy()

        try:
            for i in range(steps):
                q_traj[i] = q
                p_traj[i] = p
                t_traj[i] = i * self.dt
                energy_traj[i] = hamiltonian(q, p)

                q, p = self.step(hamiltonian, q, p)

            return IntegrationResult(
                q=q_traj,
                p=p_traj,
                t=t_traj,
                energy=energy_traj,
                success=True,
                metadata={"dt": self.dt, "steps": steps},
            )

        except Exception as e:
            logger.error(f"Integration failed: {e}")
            return IntegrationResult(
                success=False,
                error=str(e),
            )


class VerletIntegrator(SymplecticIntegrator):
    """Velocity Verlet symplectic integrator.

    Second-order accurate, symplectic, time-reversible.
    Ideal for long-term Hamiltonian integration.

    Usage:
        integrator = VerletIntegrator(dt=0.01)
        result = integrator.integrate(H, q0, p0, steps=1000)
    """

    def step(
        self,
        hamiltonian: Callable,
        q: np.ndarray,
        p: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Perform Velocity Verlet step."""
        # For separable Hamiltonian H = T(p) + V(q)
        # where T = p^2/(2m) and V = V(q)

        # Half step for momentum
        dVdq = self._gradient_potential(hamiltonian, q)
        p_half = p - 0.5 * self.dt * dVdq

        # Full step for position
        q_new = q + self.dt * p_half

        # Half step for momentum
        dVdq_new = self._gradient_potential(hamiltonian, q_new)
        p_new = p_half - 0.5 * self.dt * dVdq_new

        return q_new, p_new

    def _gradient_potential(
        self,
        hamiltonian: Callable,
        q: np.ndarray,
        epsilon: float = 1e-6,
    ) -> np.ndarray:
        """Numerical gradient of potential."""
        grad = np.zeros_like(q)
        for i in range(len(q)):
            q_plus = q.copy()
            q_minus = q.copy()
            q_plus[i] += epsilon
            q_minus[i] -= epsilon
            grad[i] = (hamiltonian(q_plus, np.zeros_like(q)) -
                      hamiltonian(q_minus, np.zeros_like(q))) / (2 * epsilon)
        return grad


class YoshidaIntegrator(SymplecticIntegrator):
    """Yoshida 4th-order symplectic integrator.

    Higher-order symplectic integrator using Suzuki-Yoshida coefficients.
    Better energy conservation than Verlet for same step size.

    Usage:
        integrator = YoshidaIntegrator(dt=0.01)
        result = integrator.integrate(H, q0, p0, steps=1000)
    """

    # Yoshida coefficients for 4th order
    C1 = 0.6756035959798289
    C2 = -0.1756035959798288
    D1 = 1.3512071919596578
    D2 = -1.7024143839193155

    def __init__(self, dt: float = 0.01):
        super().__init__(dt)
        self.verlet = VerletIntegrator(dt)

    def step(
        self,
        hamiltonian: Callable,
        q: np.ndarray,
        p: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Perform Yoshida 4th-order step."""
        # Composition of three Verlet-like steps
        q1, p1 = self._substep(hamiltonian, q, p, self.C1, self.D1)
        q2, p2 = self._substep(hamiltonian, q1, p1, self.C2, self.D2)
        q3, p3 = self._substep(hamiltonian, q2, p2, self.C1, self.D1)

        return q3, p3

    def _substep(
        self,
        hamiltonian: Callable,
        q: np.ndarray,
        p: np.ndarray,
        c: float,
        d: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Single Yoshida substep."""
        dVdq = self.verlet._gradient_potential(hamiltonian, q)
        p_new = p + c * self.dt * (-dVdq)
        q_new = q + d * self.dt * p_new
        return q_new, p_new


# =============================================================================
# Hamiltonian System Templates
# =============================================================================

class HamiltonianSystem(ABC):
    """Abstract base class for Hamiltonian systems."""

    @abstractmethod
    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute Hamiltonian H(q, p)."""
        pass

    @abstractmethod
    def equations(self, q: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Compute Hamilton's equations: (dq/dt, dp/dt)."""
        pass


class HarmonicOscillator(HamiltonianSystem):
    """Simple harmonic oscillator.

    H = p^2/(2m) + (1/2)kq^2

    Parameters:
        m: Mass (default: 1.0)
        k: Spring constant (default: 1.0)
        omega: Natural frequency (default: sqrt(k/m))

    Usage:
        osc = HarmonicOscillator(m=1.0, k=1.0)
        energy = osc.hamiltonian(q=1.0, p=0.0)
    """

    def __init__(self, m: float = 1.0, k: float = 1.0):
        self.m = m
        self.k = k
        self.omega = np.sqrt(k / m)

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute total energy."""
        return np.sum(p**2 / (2 * self.m)) + 0.5 * self.k * np.sum(q**2)

    def equations(
        self,
        q: np.ndarray,
        p: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute Hamilton's equations."""
        dqdt = p / self.m
        dpdt = -self.k * q
        return dqdt, dpdt


class Pendulum(HamiltonianSystem):
    """Simple pendulum.

    H = p^2/(2ml^2) - mgl*cos(theta)

    Parameters:
        m: Mass (default: 1.0)
        l: Length (default: 1.0)
        g: Gravity (default: 9.81)

    Usage:
        pend = Pendulum(m=1.0, l=1.0, g=9.81)
        energy = pend.hamiltonian(q=np.pi/4, p=0.0)
    """

    def __init__(self, m: float = 1.0, l: float = 1.0, g: float = 9.81):
        self.m = m
        self.l = l
        self.g = g

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute total energy."""
        kinetic = np.sum(p**2 / (2 * self.m * self.l**2))
        potential = -self.m * self.g * self.l * np.sum(np.cos(q))
        return kinetic + potential

    def equations(
        self,
        q: np.ndarray,
        p: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute Hamilton's equations."""
        dqdt = p / (self.m * self.l**2)
        dpdt = -self.m * self.g * self.l * np.sin(q)
        return dqdt, dpdt


class HenonHeiles(HamiltonianSystem):
    """Hénon-Heiles system for chaos studies.

    H = (px^2 + py^2)/2 + (x^2 + y^2)/2 + x^2*y - y^3/3

    This system shows chaotic behavior for E > 1/6.

    Usage:
        hh = HenonHeiles()
        energy = hh.hamiltonian(q=[0.1, 0.1], p=[0.0, 0.0])
    """

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute total energy."""
        kinetic = np.sum(p**2) / 2
        harmonic = np.sum(q**2) / 2
        nonlinear = q[0]**2 * q[1] - q[1]**3 / 3 if len(q) >= 2 else 0
        return kinetic + harmonic + nonlinear

    def equations(
        self,
        q: np.ndarray,
        p: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute Hamilton's equations."""
        dqdt = p
        if len(q) >= 2:
            dpdt = np.array([
                -q[0] - 2*q[0]*q[1],
                -q[1] - q[0]**2 + q[1]**2,
            ])
        else:
            dpdt = -q
        return dqdt, dpdt


class DoublePendulum(HamiltonianSystem):
    """Double pendulum - chaotic system.

    Complex Hamiltonian for two coupled pendulums.

    Parameters:
        m1, m2: Masses (default: 1.0)
        l1, l2: Lengths (default: 1.0)
        g: Gravity (default: 9.81)

    Usage:
        dp = DoublePendulum()
        energy = dp.hamiltonian(q=[np.pi/2, np.pi], p=[0.0, 0.0])
    """

    def __init__(
        self,
        m1: float = 1.0,
        m2: float = 1.0,
        l1: float = 1.0,
        l2: float = 1.0,
        g: float = 9.81,
    ):
        self.m1 = m2
        self.m2 = m2
        self.l1 = l1
        self.l2 = l2
        self.g = g

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute total energy (simplified for demonstration)."""
        if len(q) < 2 or len(p) < 2:
            return 0.0

        theta1, theta2 = q
        p1, p2 = p

        # Simplified Hamiltonian
        kinetic = (p1**2 + p2**2) / 2
        potential = -(self.m1 + self.m2) * self.g * self.l1 * np.cos(theta1)
        potential -= self.m2 * self.g * self.l2 * np.cos(theta2)

        return kinetic + potential

    def equations(
        self,
        q: np.ndarray,
        p: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute approximate Hamilton's equations."""
        # Simplified for demonstration
        dqdt = p
        dpdt = -np.sin(q)
        return dqdt, dpdt


# =============================================================================
# Phase Space Analysis
# =============================================================================

class PhaseSpaceAnalyzer:
    """Phase space analysis tools.

    Provides:
    - Phase space trajectory plotting
    - Poincaré section computation
    - Lyapunov exponent estimation
    - Stability analysis

    Usage:
        analyzer = PhaseSpaceAnalyzer()
        plot = analyzer.plot_phase_space(q_traj, p_traj)
        poincare = analyzer.poincare_section(q_traj, p_traj)
    """

    def plot_phase_space(
        self,
        q: np.ndarray,
        p: np.ndarray,
        *,
        title: str = "Phase Space",
    ) -> dict[str, Any]:
        """
        Generate phase space plot data.

        Args:
            q: Position trajectory
            p: Momentum trajectory
            title: Plot title

        Returns:
            Plot data dictionary
        """
        return {
            "type": "phase_space",
            "title": title,
            "q": q.tolist() if isinstance(q, np.ndarray) else q,
            "p": p.tolist() if isinstance(p, np.ndarray) else p,
            "xlabel": "Position (q)",
            "ylabel": "Momentum (p)",
        }

    def poincare_section(
        self,
        q: np.ndarray,
        p: np.ndarray,
        *,
        surface: str = "q1=0",
        direction: str = "positive",
    ) -> dict[str, Any]:
        """
        Compute Poincaré section.

        Args:
            q: Position trajectory
            p: Momentum trajectory
            surface: Surface of section (e.g., "q1=0")
            direction: Crossing direction ("positive", "negative", "both")

        Returns:
            Poincaré section data
        """
        # Find crossings
        if surface == "q1=0" and q.ndim > 1:
            q1 = q[:, 0]
            crossings = self._find_crossings(q1, direction)

            return {
                "type": "poincare_section",
                "surface": surface,
                "q2": q[crossings, 1].tolist() if q.ndim > 1 else [],
                "p2": p[crossings, 1].tolist() if p.ndim > 1 else [],
                "n_crossings": len(crossings),
            }

        return {"type": "poincare_section", "error": "Invalid surface or data"}

    def _find_crossings(
        self,
        x: np.ndarray,
        direction: str = "positive",
    ) -> np.ndarray:
        """Find zero crossings in array."""
        if direction == "positive":
            return np.where((x[:-1] < 0) & (x[1:] >= 0))[0]
        elif direction == "negative":
            return np.where((x[:-1] > 0) & (x[1:] <= 0))[0]
        else:
            return np.where(np.diff(np.signbit(x)))[0]

    def lyapunov_exponent(
        self,
        trajectory1: np.ndarray,
        trajectory2: np.ndarray,
        dt: float = 0.01,
    ) -> float:
        """
        Estimate largest Lyapunov exponent.

        Args:
            trajectory1: First trajectory
            trajectory2: Second trajectory (slightly perturbed)
            dt: Time step

        Returns:
            Lyapunov exponent estimate
        """
        # Compute separation over time
        separations = np.linalg.norm(trajectory1 - trajectory2, axis=1)

        # Avoid log(0)
        separations = np.maximum(separations, 1e-10)

        # Linear fit to log(separation) vs time
        log_sep = np.log(separations)
        t = np.arange(len(log_sep)) * dt

        # Simple linear regression
        if len(t) > 2:
            slope = np.polyfit(t, log_sep, 1)[0]
            return slope

        return 0.0

    def energy_drift(
        self,
        energy: np.ndarray,
        initial_energy: float | None = None,
    ) -> dict[str, float]:
        """
        Compute energy drift statistics.

        Args:
            energy: Energy trajectory
            initial_energy: Initial energy (default: energy[0])

        Returns:
            Drift statistics
        """
        if initial_energy is None:
            initial_energy = energy[0]

        relative_drift = (energy - initial_energy) / np.abs(initial_energy)

        return {
            "max_relative_drift": float(np.max(np.abs(relative_drift))),
            "mean_relative_drift": float(np.mean(np.abs(relative_drift))),
            "rms_drift": float(np.sqrt(np.mean(relative_drift**2))),
            "final_drift": float(relative_drift[-1]),
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_integrator(
    method: str = "verlet",
    dt: float = 0.01,
) -> SymplecticIntegrator:
    """
    Create symplectic integrator.

    Args:
        method: Integration method ("verlet" or "yoshida")
        dt: Time step

    Returns:
        SymplecticIntegrator instance

    Examples:
        integrator = create_integrator("verlet", dt=0.01)
        integrator = create_integrator("yoshida", dt=0.001)
    """
    methods = {
        "verlet": VerletIntegrator,
        "yoshida": YoshidaIntegrator,
    }

    if method not in methods:
        raise ValueError(f"Unknown method: {method}. Available: {list(methods.keys())}")

    return methods[method](dt)


def create_system(
    system_type: str,
    **params: Any,
) -> HamiltonianSystem:
    """
    Create Hamiltonian system.

    Args:
        system_type: System type ("harmonic", "pendulum", "henon_heiles", "double_pendulum")
        **params: System parameters

    Returns:
        HamiltonianSystem instance

    Examples:
        osc = create_system("harmonic", m=1.0, k=1.0)
        pend = create_system("pendulum", l=1.0, g=9.81)
        hh = create_system("henon_heiles")
    """
    systems = {
        "harmonic": HarmonicOscillator,
        "pendulum": Pendulum,
        "henon_heiles": HenonHeiles,
        "double_pendulum": DoublePendulum,
    }

    if system_type not in systems:
        raise ValueError(
            f"Unknown system: {system_type}. Available: {list(systems.keys())}"
        )

    return systems[system_type](**params)
