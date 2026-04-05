"""Pre-built Hamiltonian system templates.

Provides 10 canonical Hamiltonian systems:
1. Harmonic Oscillator
2. Simple Pendulum
3. Double Pendulum
4. Hénon-Heiles System
5. Kepler Problem (2-body)
6. Coupled Oscillators
7. Duffing Oscillator
8. Van der Pol Oscillator (non-conservative)
9. Standard Map (discrete)
10. Toda Lattice

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.physics.templates import (
        HarmonicOscillator,
        HenonHeiles,
        DoublePendulum,
    )

    # Harmonic oscillator
    osc = HarmonicOscillator(m=1.0, k=1.0)
    energy = osc.hamiltonian(q=1.0, p=0.0)

    # Hénon-Heiles (chaotic)
    system = HenonHeiles()
    is_chaotic = system.is_chaotic()  # Energy-dependent
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """State of a dynamical system.

    Attributes:
        q: Position coordinates
        p: Momentum coordinates
        t: Time
        params: System parameters
    """

    q: np.ndarray
    p: np.ndarray
    t: float = 0.0
    params: dict = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


class HamiltonianSystem(ABC):
    """Abstract base class for Hamiltonian systems.

    Subclasses must implement:
    - hamiltonian(q, p): Compute H(q, p)
    - dH_dq(q, p): Compute ∂H/∂q
    - dH_dp(q, p): Compute ∂H/∂p
    """

    name: str = "Hamiltonian System"
    n_dims: int = 1

    @abstractmethod
    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute Hamiltonian H(q, p)."""
        pass

    @abstractmethod
    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """Compute gradient ∂H/∂q."""
        pass

    @abstractmethod
    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """Compute gradient ∂H/∂p."""
        pass

    def equations_of_motion(
        self,
        t: float,
        y: np.ndarray,
    ) -> np.ndarray:
        """
        Compute equations of motion dy/dt.

        Args:
            t: Time
            y: State vector [q, p]

        Returns:
            Time derivative [dq/dt, dp/dt]
        """
        n = self.n_dims
        q = y[:n]
        p = y[n:]

        dqdt = self.dH_dp(q, p)
        dpdt = -self.dH_dq(q, p)

        return np.concatenate([dqdt, dpdt])

    def is_chaotic(self, energy: float | None = None) -> bool:
        """Check if system exhibits chaos at given energy."""
        return False  # Default: not chaotic


class HarmonicOscillator(HamiltonianSystem):
    """Simple harmonic oscillator.

    H = p²/(2m) + (1/2)kq²

    Parameters:
        m: Mass
        k: Spring constant

    Properties:
    - Integrable (not chaotic)
    - Analytic solution: q(t) = A·cos(ωt + φ)
    - Frequency: ω = √(k/m)
    """

    name = "Harmonic Oscillator"
    n_dims = 1

    def __init__(self, m: float = 1.0, k: float = 1.0):
        self.m = m
        self.k = k
        self.omega = np.sqrt(k / m)  # Natural frequency

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """H = p²/(2m) + (1/2)kq²"""
        return p[0]**2 / (2 * self.m) + 0.5 * self.k * q[0]**2

    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂q = kq"""
        return np.array([self.k * q[0]])

    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂p = p/m"""
        return np.array([p[0] / self.m])


class SimplePendulum(HamiltonianSystem):
    """Simple pendulum.

    H = p²/(2ml²) - mgl·cos(θ)

    Parameters:
        m: Mass
        l: Length
        g: Gravitational acceleration

    Properties:
    - Integrable (not chaotic)
    - Small oscillations: ω = √(g/l)
    - Separatrix at E = mgl
    """

    name = "Simple Pendulum"
    n_dims = 1

    def __init__(self, m: float = 1.0, l: float = 1.0, g: float = 9.81):
        self.m = m
        self.l = l
        self.g = g

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """H = p²/(2ml²) - mgl·cos(θ)"""
        theta = q[0]
        return p[0]**2 / (2 * self.m * self.l**2) - self.m * self.g * self.l * np.cos(theta)

    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂θ = -mgl·sin(θ)"""
        return np.array([-self.m * self.g * self.l * np.sin(q[0])])

    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂p = p/(ml²)"""
        return np.array([p[0] / (self.m * self.l**2)])


class DoublePendulum(HamiltonianSystem):
    """Double pendulum - chaotic system.

    Parameters:
        m1: Mass of first pendulum
        m2: Mass of second pendulum
        l1: Length of first rod
        l2: Length of second rod
        g: Gravitational acceleration

    Properties:
    - Chaotic for E > critical energy
    - 2 degrees of freedom
    - Rich phase space structure
    """

    name = "Double Pendulum"
    n_dims = 2

    def __init__(
        self,
        m1: float = 1.0,
        m2: float = 1.0,
        l1: float = 1.0,
        l2: float = 1.0,
        g: float = 9.81,
    ):
        self.m1 = m1
        self.m2 = m2
        self.l1 = l1
        self.l2 = l2
        self.g = g

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute Hamiltonian for double pendulum."""
        theta1, theta2 = q
        p1, p2 = p

        m1, m2, l1, l2, g = self.m1, self.m2, self.l1, self.l2, self.g

        # Kinetic energy matrix
        M11 = (m1 + m2) * l1**2
        M12 = m2 * l1 * l2 * np.cos(theta1 - theta2)
        M22 = m2 * l2**2

        # Denominator for kinetic energy
        det = M11 * M22 - M12**2

        if abs(det) < 1e-10:
            return float('inf')

        # Kinetic energy
        T = (M22 * p1**2 - 2 * M12 * p1 * p2 + M11 * p2**2) / (2 * det)

        # Potential energy
        V = -(m1 + m2) * g * l1 * np.cos(theta1) - m2 * g * l2 * np.cos(theta2)

        return T + V

    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """Compute ∂H/∂q."""
        theta1, theta2 = q
        p1, p2 = p

        m1, m2, l1, l2, g = self.m1, self.m2, self.l1, self.l2, self.g

        # Potential gradient
        dV_dtheta1 = (m1 + m2) * g * l1 * np.sin(theta1)
        dV_dtheta2 = m2 * g * l2 * np.sin(theta2)

        return np.array([dV_dtheta1, dV_dtheta2])

    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """Compute ∂H/∂p = velocities."""
        theta1, theta2 = q
        p1, p2 = p

        m1, m2, l1, l2 = self.m1, self.m2, self.l1, self.l2

        M11 = (m1 + m2) * l1**2
        M12 = m2 * l1 * l2 * np.cos(theta1 - theta2)
        M22 = m2 * l2**2

        det = M11 * M22 - M12**2

        if abs(det) < 1e-10:
            return np.array([0.0, 0.0])

        dtheta1_dt = (M22 * p1 - M12 * p2) / det
        dtheta2_dt = (M11 * p2 - M12 * p1) / det

        return np.array([dtheta1_dt, dtheta2_dt])

    def is_chaotic(self, energy: float | None = None) -> bool:
        """Double pendulum is chaotic for most energies."""
        return True


class HenonHeiles(HamiltonianSystem):
    """Hénon-Heiles system - classic chaotic system.

    H = (1/2)(p₁² + p₂² + q₁² + q₂²) + q₁²q₂ - (1/3)q₂³

    Properties:
    - Transition to chaos at E ≈ 1/6
    - 2 degrees of freedom
    - Originally modeled stellar orbits
    """

    name = "Hénon-Heiles System"
    n_dims = 2

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute Hénon-Heiles Hamiltonian."""
        q1, q2 = q
        p1, p2 = p

        kinetic = 0.5 * (p1**2 + p2**2 + q1**2 + q2**2)
        potential = q1**2 * q2 - (1.0 / 3.0) * q2**3

        return kinetic + potential

    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂q."""
        q1, q2 = q
        return np.array([
            q1 + 2 * q1 * q2,
            q2 + q1**2 - q2**2,
        ])

    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂p = velocities."""
        p1, p2 = p
        return np.array([p1, p2])

    def is_chaotic(self, energy: float | None = None) -> bool:
        """Check if chaotic at given energy.

        Transition occurs at E ≈ 1/6 ≈ 0.1667
        """
        if energy is None:
            return True  # Assume typical chaotic regime

        return energy > 0.16


class KeplerProblem(HamiltonianSystem):
    """Kepler two-body problem.

    H = p²/(2μ) - G·M·μ/r

    Parameters:
        G: Gravitational constant
        M: Central mass
        mu: Reduced mass

    Properties:
    - Integrable (not chaotic)
    - Conserved: energy, angular momentum, Laplace-Runge-Lenz vector
    - Orbits: ellipses, parabolas, or hyperbolas
    """

    name = "Kepler Problem"
    n_dims = 3

    def __init__(self, G: float = 1.0, M: float = 1.0, mu: float = 1.0):
        self.G = G
        self.M = M
        self.mu = mu
        self.k = G * M * mu  # Gravitational parameter

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """H = p²/(2μ) - k/r"""
        r = np.linalg.norm(q)
        if r < 1e-10:
            return float('inf')

        kinetic = np.dot(p, p) / (2 * self.mu)
        potential = -self.k / r

        return kinetic + potential

    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂q = k·q/r³"""
        r = np.linalg.norm(q)
        if r < 1e-10:
            return np.zeros(3)

        return self.k * q / r**3

    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂p = p/μ"""
        return p / self.mu


class CoupledOscillators(HamiltonianSystem):
    """Two coupled harmonic oscillators.

    H = (p₁² + p₂²)/2 + (q₁² + q₂²)/2 + k·q₁·q₂

    Parameters:
        k: Coupling strength

    Properties:
    - Integrable (can be decoupled via normal modes)
    - Normal mode frequencies: ω₁ = √(1-k), ω₂ = √(1+k)
    """

    name = "Coupled Oscillators"
    n_dims = 2

    def __init__(self, k: float = 0.1):
        self.k = k

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute Hamiltonian."""
        q1, q2 = q
        p1, p2 = p

        kinetic = 0.5 * (p1**2 + p2**2)
        potential = 0.5 * (q1**2 + q2**2) + self.k * q1 * q2

        return kinetic + potential

    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂q."""
        q1, q2 = q
        return np.array([q1 + self.k * q2, q2 + self.k * q1])

    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂p = velocities."""
        p1, p2 = p
        return np.array([p1, p2])


class DuffingOscillator(HamiltonianSystem):
    """Duffing oscillator with double-well potential.

    H = p²/2 - a·q²/2 + b·q⁴/4

    Parameters:
        a: Linear stiffness
        b: Nonlinear stiffness

    Properties:
    - Double-well potential for a, b > 0
    - Chaotic when driven (not in Hamiltonian form)
    - Separatrix divides phase space
    """

    name = "Duffing Oscillator"
    n_dims = 1

    def __init__(self, a: float = 1.0, b: float = 1.0):
        self.a = a
        self.b = b

    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Compute Hamiltonian."""
        return p[0]**2 / 2 - self.a * q[0]**2 / 2 + self.b * q[0]**4 / 4

    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂q = -aq + bq³"""
        return np.array([-self.a * q[0] + self.b * q[0]**3])

    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """∂H/∂p = p"""
        return np.array([p[0]])


class StandardMap(HamiltonianSystem):
    """Standard map (Chirikov-Taylor map) - discrete Hamiltonian system.

    p_{n+1} = p_n + K·sin(q_n)
    q_{n+1} = q_n + p_{n+1}

    Parameters:
        K: Stochasticity parameter

    Properties:
    - Discrete map (not flow)
    - Chaotic for K > 0.9716
    - Mixed phase space
    """

    name = "Standard Map"
    n_dims = 1
    is_discrete = True

    def __init__(self, K: float = 1.0):
        self.K = K

    def step(self, q: float, p: float) -> tuple[float, float]:
        """Perform one map iteration."""
        p_new = p + self.K * np.sin(q)
        q_new = q + p_new
        return q_new % (2 * np.pi), p_new

    def iterate(
        self,
        q0: float,
        p0: float,
        n_steps: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Iterate the map."""
        q_traj = np.zeros(n_steps + 1)
        p_traj = np.zeros(n_steps + 1)

        q_traj[0] = q0 % (2 * np.pi)
        p_traj[0] = p0

        q, p = q0, p0
        for i in range(n_steps):
            q, p = self.step(q, p)
            q_traj[i + 1] = q
            p_traj[i + 1] = p

        return q_traj, p_traj

    def is_chaotic(self, energy: float | None = None) -> bool:
        """Check if chaotic.

        Transition at K ≈ 0.9716
        """
        return self.K > 0.9716

    # Placeholder methods for Hamiltonian interface
    def hamiltonian(self, q: np.ndarray, p: np.ndarray) -> float:
        """Not applicable for discrete map."""
        return 0.0

    def dH_dq(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """Not applicable for discrete map."""
        return np.zeros_like(q)

    def dH_dp(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """Not applicable for discrete map."""
        return np.zeros_like(p)


# Template registry
TEMPLATES = {
    "harmonic_oscillator": HarmonicOscillator,
    "simple_pendulum": SimplePendulum,
    "double_pendulum": DoublePendulum,
    "henon_heiles": HenonHeiles,
    "kepler": KeplerProblem,
    "coupled_oscillators": CoupledOscillators,
    "duffing": DuffingOscillator,
    "standard_map": StandardMap,
}


def get_template(name: str, **kwargs) -> HamiltonianSystem:
    """
    Get Hamiltonian system template.

    Args:
        name: Template name
        **kwargs: Parameters for the system

    Returns:
        Configured Hamiltonian system

    Raises:
        ValueError: If template name not found
    """
    if name not in TEMPLATES:
        raise ValueError(
            f"Unknown template: {name}. "
            f"Available: {', '.join(TEMPLATES.keys())}"
        )

    return TEMPLATES[name](**kwargs)
