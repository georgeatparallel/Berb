"""Symplectic integrators for Hamiltonian systems.

Provides:
- Verlet integrator (2nd order symplectic)
- Yoshida integrator (4th order symplectic)
- Energy conservation monitoring
- Adaptive step size control

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.physics.integrators import (
        VerletIntegrator,
        YoshidaIntegrator,
    )

    # Verlet integration
    integrator = VerletIntegrator(dt=0.01)
    trajectory = integrator.integrate(hamiltonian, q0, p0, steps=1000)

    # Yoshida (higher accuracy)
    integrator = YoshidaIntegrator(dt=0.01)
    trajectory = integrator.integrate(hamiltonian, q0, p0, steps=1000)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IntegrationState:
    """Integration state for Hamiltonian systems.

    Attributes:
        q: Position array (n_dims,)
        p: Momentum array (n_dims,)
        t: Current time
        energy: Current energy (Hamiltonian value)
    """

    q: np.ndarray
    p: np.ndarray
    t: float = 0.0
    energy: float = 0.0

    def copy(self) -> IntegrationState:
        """Create deep copy."""
        return IntegrationState(
            q=self.q.copy(),
            p=self.p.copy(),
            t=self.t,
            energy=self.energy,
        )


@dataclass
class IntegrationStats:
    """Integration statistics.

    Attributes:
        n_steps: Number of integration steps
        n_energy_evals: Number of energy evaluations
        energy_drift: Total energy drift
        max_energy_error: Maximum energy error
        execution_time: Execution time in seconds
    """

    n_steps: int = 0
    n_energy_evals: int = 0
    energy_drift: float = 0.0
    max_energy_error: float = 0.0
    execution_time: float = 0.0


class VerletIntegrator:
    """Velocity Verlet symplectic integrator (2nd order).

    Symplectic integrators preserve phase space volume and exhibit
    excellent long-term energy conservation, making them ideal for
    Hamiltonian systems.

    The velocity Verlet algorithm:
    1. p(t+dt/2) = p(t) - (dt/2) * ∂H/∂q(q(t))
    2. q(t+dt) = q(t) + dt * ∂H/∂p(p(t+dt/2))
    3. p(t+dt) = p(t+dt/2) - (dt/2) * ∂H/∂q(q(t+dt))

    Attributes:
        dt: Time step
        track_energy: Whether to track energy conservation
    """

    def __init__(
        self,
        dt: float = 0.01,
        track_energy: bool = True,
    ):
        """
        Initialize Verlet integrator.

        Args:
            dt: Time step size
            track_energy: Track energy conservation
        """
        self.dt = dt
        self.track_energy = track_energy

    def integrate(
        self,
        hamiltonian: Callable[[np.ndarray, np.ndarray], float],
        dH_dq: Callable[[np.ndarray, np.ndarray], np.ndarray],
        dH_dp: Callable[[np.ndarray, np.ndarray], np.ndarray],
        q0: np.ndarray,
        p0: np.ndarray,
        steps: int = 1000,
        t0: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, IntegrationStats]:
        """
        Integrate Hamiltonian system.

        Args:
            hamiltonian: Hamiltonian function H(q, p)
            dH_dq: Gradient ∂H/∂q
            dH_dp: Gradient ∂H/∂p (velocity)
            q0: Initial position
            p0: Initial momentum
            steps: Number of integration steps
            t0: Initial time

        Returns:
            Tuple of (q_trajectory, p_trajectory, time_array, stats)
        """
        q = np.asarray(q0, dtype=np.float64)
        p = np.asarray(p0, dtype=np.float64)

        n_dims = len(q)
        q_traj = np.zeros((steps + 1, n_dims))
        p_traj = np.zeros((steps + 1, n_dims))
        t_traj = np.zeros(steps + 1)

        q_traj[0] = q
        p_traj[0] = p
        t_traj[0] = t0

        energy_0 = hamiltonian(q, p) if self.track_energy else 0.0
        energies = [energy_0] if self.track_energy else []

        stats = IntegrationStats(n_energy_evals=1 if self.track_energy else 0)

        dt = self.dt
        half_dt = dt / 2.0

        import time
        t_start = time.monotonic()

        for i in range(steps):
            # Half step for momentum
            force = -dH_dq(q, p)
            p_half = p + half_dt * force

            # Full step for position
            q = q + dt * dH_dp(q, p_half)

            # Half step for momentum
            force_new = -dH_dq(q, p_half)
            p = p_half + half_dt * force_new

            # Update time
            t = t0 + (i + 1) * dt

            # Store trajectory
            q_traj[i + 1] = q
            p_traj[i + 1] = p
            t_traj[i + 1] = t

            # Track energy
            if self.track_energy:
                energy = hamiltonian(q, p)
                energies.append(energy)
                stats.n_energy_evals += 1

        stats.n_steps = steps

        # Calculate energy statistics
        if self.track_energy and energies:
            energies_arr = np.array(energies)
            energy_diff = energies_arr - energy_0
            stats.energy_drift = float(energies_arr[-1] - energy_0)
            stats.max_energy_error = float(np.max(np.abs(energy_diff)))

        stats.execution_time = time.monotonic() - t_start

        return q_traj, p_traj, t_traj, stats


class YoshidaIntegrator:
    """Yoshida 4th-order symplectic integrator.

    Higher-order symplectic integrator using Suzuki-Yoshida composition.
    Provides better accuracy than Verlet for the same step size, at the
    cost of more force evaluations per step.

    Uses the 3-stage 4th-order composition:
    Φ(dt) = Φ(w₃·dt) ∘ Φ(w₂·dt) ∘ Φ(w₁·dt)

    where w₁ = 1/(2-2^(1/3)), w₂ = -2^(1/3)/(2-2^(1/3)), w₃ = w₁

    Attributes:
        dt: Time step
        track_energy: Whether to track energy conservation
    """

    # Yoshida coefficients
    W1 = 1.0 / (2.0 - 2.0 ** (1.0 / 3.0))
    W2 = -2.0 ** (1.0 / 3.0) / (2.0 - 2.0 ** (1.0 / 3.0))
    W3 = W1

    def __init__(
        self,
        dt: float = 0.01,
        track_energy: bool = True,
    ):
        """
        Initialize Yoshida integrator.

        Args:
            dt: Time step size
            track_energy: Track energy conservation
        """
        self.dt = dt
        self.track_energy = track_energy

    def integrate(
        self,
        hamiltonian: Callable[[np.ndarray, np.ndarray], float],
        dH_dq: Callable[[np.ndarray, np.ndarray], np.ndarray],
        dH_dp: Callable[[np.ndarray, np.ndarray], np.ndarray],
        q0: np.ndarray,
        p0: np.ndarray,
        steps: int = 1000,
        t0: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, IntegrationStats]:
        """
        Integrate Hamiltonian system.

        Args:
            hamiltonian: Hamiltonian function H(q, p)
            dH_dq: Gradient ∂H/∂q
            dH_dp: Gradient ∂H/∂p (velocity)
            q0: Initial position
            p0: Initial momentum
            steps: Number of integration steps
            t0: Initial time

        Returns:
            Tuple of (q_trajectory, p_trajectory, time_array, stats)
        """
        q = np.asarray(q0, dtype=np.float64)
        p = np.asarray(p0, dtype=np.float64)

        n_dims = len(q)
        q_traj = np.zeros((steps + 1, n_dims))
        p_traj = np.zeros((steps + 1, n_dims))
        t_traj = np.zeros(steps + 1)

        q_traj[0] = q
        p_traj[0] = p
        t_traj[0] = t0

        energy_0 = hamiltonian(q, p) if self.track_energy else 0.0
        energies = [energy_0] if self.track_energy else []

        stats = IntegrationStats(n_energy_evals=1 if self.track_energy else 0)

        dt = self.dt
        w1, w2, w3 = self.W1, self.W2, self.W3

        import time
        t_start = time.monotonic()

        # Pre-allocate arrays for sub-steps
        q_temp = q.copy()
        p_temp = p.copy()

        for i in range(steps):
            # Stage 1
            force = -dH_dq(q, p)
            p_temp = p + w1 * dt * force
            q_temp = q + w1 * dt * dH_dp(q, p_temp)

            # Stage 2
            force = -dH_dq(q_temp, p_temp)
            p_temp = p_temp + w2 * dt * force
            q_temp = q_temp + w2 * dt * dH_dp(q_temp, p_temp)

            # Stage 3
            force = -dH_dq(q_temp, p_temp)
            p = p_temp + w3 * dt * force
            q = q_temp + w3 * dt * dH_dp(q, p)

            # Update time
            t = t0 + (i + 1) * dt

            # Store trajectory
            q_traj[i + 1] = q
            p_traj[i + 1] = p
            t_traj[i + 1] = t

            # Track energy
            if self.track_energy:
                energy = hamiltonian(q, p)
                energies.append(energy)
                stats.n_energy_evals += 1

        stats.n_steps = steps

        # Calculate energy statistics
        if self.track_energy and energies:
            energies_arr = np.array(energies)
            energy_diff = energies_arr - energy_0
            stats.energy_drift = float(energies_arr[-1] - energy_0)
            stats.max_energy_error = float(np.max(np.abs(energy_diff)))

        stats.execution_time = time.monotonic() - t_start

        return q_traj, p_traj, t_traj, stats


class AdaptiveVerletIntegrator:
    """Adaptive step-size Velocity Verlet integrator.

    Adjusts step size based on energy conservation to maintain
    accuracy while maximizing efficiency.

    Attributes:
        dt_initial: Initial time step
        dt_min: Minimum allowed step size
        dt_max: Maximum allowed step size
        energy_tolerance: Energy error tolerance
    """

    def __init__(
        self,
        dt_initial: float = 0.01,
        dt_min: float = 1e-6,
        dt_max: float = 0.1,
        energy_tolerance: float = 1e-4,
    ):
        """
        Initialize adaptive Verlet integrator.

        Args:
            dt_initial: Initial time step
            dt_min: Minimum step size
            dt_max: Maximum step size
            energy_tolerance: Energy error tolerance
        """
        self.dt = dt_initial
        self.dt_min = dt_min
        self.dt_max = dt_max
        self.energy_tolerance = energy_tolerance

    def integrate(
        self,
        hamiltonian: Callable[[np.ndarray, np.ndarray], float],
        dH_dq: Callable[[np.ndarray, np.ndarray], np.ndarray],
        dH_dp: Callable[[np.ndarray, np.ndarray], np.ndarray],
        q0: np.ndarray,
        p0: np.ndarray,
        steps: int = 1000,
        t0: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, IntegrationStats]:
        """
        Integrate with adaptive step size.

        Args:
            hamiltonian: Hamiltonian function H(q, p)
            dH_dq: Gradient ∂H/∂q
            dH_dp: Gradient ∂H/∂p (velocity)
            q0: Initial position
            p0: Initial momentum
            steps: Number of integration steps
            t0: Initial time

        Returns:
            Tuple of (q_trajectory, p_trajectory, time_array, stats)
        """
        q = np.asarray(q0, dtype=np.float64)
        p = np.asarray(p0, dtype=np.float64)

        n_dims = len(q)
        q_traj = np.zeros((steps + 1, n_dims))
        p_traj = np.zeros((steps + 1, n_dims))
        t_traj = np.zeros(steps + 1)

        q_traj[0] = q
        p_traj[0] = p
        t_traj[0] = t0

        energy_0 = hamiltonian(q, p)
        stats = IntegrationStats(n_energy_evals=1)

        dt = self.dt
        t_current = t0

        import time
        t_start = time.monotonic()

        for i in range(steps):
            # Try step with current dt
            force = -dH_dq(q, p)
            p_half = p + (dt / 2.0) * force
            q_new = q + dt * dH_dp(q, p_half)
            force_new = -dH_dq(q_new, p_half)
            p_new = p_half + (dt / 2.0) * force_new

            # Check energy
            energy_new = hamiltonian(q_new, p_new)
            stats.n_energy_evals += 1

            energy_error = abs(energy_new - energy_0) / max(abs(energy_0), 1.0)

            # Adjust step size
            if energy_error > self.energy_tolerance:
                # Reduce step size
                dt = max(self.dt_min, dt * 0.5)
                continue
            elif energy_error < self.energy_tolerance / 10.0:
                # Increase step size
                dt = min(self.dt_max, dt * 1.1)

            # Accept step
            q = q_new
            p = p_new
            t_current += dt

            q_traj[i + 1] = q
            p_traj[i + 1] = p
            t_traj[i + 1] = t_current

            # Update energy reference
            energy_0 = energy_new

        stats.n_steps = steps
        stats.energy_drift = float(energy_new - energy_0)
        stats.execution_time = time.monotonic() - t_start

        return q_traj, p_traj, t_traj, stats
