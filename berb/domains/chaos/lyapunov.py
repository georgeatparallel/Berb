"""Lyapunov Exponent Computation for Chaos Detection.

Based on Wolf et al. algorithm (1985) and Gram-Schmidt orthonormalization.

Lyapunov exponents quantify the rate at which nearby trajectories diverge.
- λ₁ > 0: Chaotic system (exponential divergence)
- λ₁ ≤ 0: Regular system (convergence or neutral stability)

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.chaos.lyapunov import LyapunovExponentCalculator
    
    calc = LyapunovExponentCalculator(system, jacobian, n_dims=3)
    results = await calc.compute_exponents(y0, t_span, dt=0.01)
    
    print(f"Max Lyapunov exponent: {results['max_exponent']:.4f}")
    print(f"Is chaotic: {results['is_chaotic']}")
    print(f"Lyapunov time: {results['lyapunov_time']:.2f} seconds")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import qr

logger = logging.getLogger(__name__)


@dataclass
class LyapunovResult:
    """Result of Lyapunov exponent computation."""
    
    exponents: list[float]
    """Full Lyapunov spectrum [λ₁, λ₂, ..., λₙ]"""
    
    max_exponent: float
    """Maximal Lyapunov exponent (λ₁)"""
    
    is_chaotic: bool
    """True if λ₁ > 0"""
    
    lyapunov_time: float | None
    """Predictability horizon (1/λ₁), None if λ₁ ≤ 0"""
    
    kaplan_yorke_dimension: float | None
    """Fractal dimension estimate"""
    
    convergence_achieved: bool
    """True if exponents converged"""
    
    iterations: int
    """Number of iterations performed"""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exponents": self.exponents,
            "max_exponent": self.max_exponent,
            "is_chaotic": self.is_chaotic,
            "lyapunov_time": self.lyapunov_time,
            "kaplan_yorke_dimension": self.kaplan_yorke_dimension,
            "convergence_achieved": self.convergence_achieved,
            "iterations": self.iterations,
        }


class LyapunovExponentCalculator:
    """Compute Lyapunov exponents for dynamical systems.
    
    Implements two methods:
    1. Gram-Schmidt orthonormalization (full spectrum)
    2. Wolf algorithm (maximal exponent only, faster)
    
    Examples:
        >>> # Lorenz system
        >>> def lorenz(t, y):
        ...     sigma, rho, beta = 10, 28, 8/3
        ...     return [sigma*(y[1]-y[0]), y[0]*(rho-y[2])-y[1], y[0]*y[1]-beta*y[2]]
        >>> 
        >>> def lorenz_jacobian(t, y):
        ...     sigma, rho, beta = 10, 28, 8/3
        ...     return np.array([
        ...         [-sigma, sigma, 0],
        ...         [rho-y[2], -1, -y[0]],
        ...         [y[1], y[0], -beta]
        ...     ])
        >>> 
        >>> calc = LyapunovExponentCalculator(lorenz, lorenz_jacobian, n_dims=3)
        >>> result = calc.compute_exponents([1, 1, 1], (0, 100), dt=0.01)
        >>> print(f"λ₁ = {result.max_exponent:.4f}")  # Should be ~0.9056
    """
    
    def __init__(
        self,
        system: Callable[[float, np.ndarray], np.ndarray],
        jacobian: Callable[[float, np.ndarray], np.ndarray],
        n_dims: int,
    ):
        """
        Initialize Lyapunov exponent calculator.
        
        Args:
            system: Function f(t, y) defining dy/dt = f(t, y)
            jacobian: Jacobian matrix function J(t, y) = df/dy
            n_dims: Dimension of the system
        """
        self.system = system
        self.jacobian = jacobian
        self.n_dims = n_dims
    
    def compute_exponents(
        self,
        y0: np.ndarray | list[float],
        t_span: tuple[float, float],
        dt: float = 0.01,
        n_steps: int = 10000,
        tolerance: float = 1e-6,
        method: str = "gram_schmidt",
    ) -> LyapunovResult:
        """
        Compute full Lyapunov spectrum using Gram-Schmidt orthonormalization.
        
        Args:
            y0: Initial condition
            t_span: Time span (t_start, t_end)
            dt: Time step
            n_steps: Maximum number of steps
            tolerance: Convergence tolerance
            method: "gram_schmidt" or "wolf"
        
        Returns:
            LyapunovResult with exponents and diagnostics
        """
        y0 = np.asarray(y0, dtype=float)
        
        if method == "gram_schmidt":
            return self._gram_schmidt_method(y0, t_span, dt, n_steps, tolerance)
        elif method == "wolf":
            return self._wolf_method(y0, t_span, dt, n_steps)
        else:
            raise ValueError(f"Unknown method: {method}. Use 'gram_schmidt' or 'wolf'.")
    
    def _gram_schmidt_method(
        self,
        y0: np.ndarray,
        t_span: tuple[float, float],
        dt: float,
        n_steps: int,
        tolerance: float,
    ) -> LyapunovResult:
        """
        Compute Lyapunov exponents using Gram-Schmidt orthonormalization.
        
        This method computes the full spectrum of Lyapunov exponents by:
        1. Evolving n orthogonal perturbation vectors
        2. Periodically reorthonormalizing using Gram-Schmidt
        3. Accumulating the logarithmic growth rates
        """
        n = self.n_dims
        
        # Initialize trajectory and tangent vectors
        y = y0.copy()
        Q = np.eye(n)  # Orthonormal basis for tangent space
        
        # Accumulate logarithms of stretching factors
        log_stretches = np.zeros(n)
        t = t_span[0]
        
        exponents_history = []
        converged = False
        
        for step in range(n_steps):
            # Evolve trajectory by dt
            sol = solve_ivp(
                self.system,
                (t, t + dt),
                y,
                method='RK45',
                rtol=1e-8,
                atol=1e-10,
            )
            y = sol.y[:, -1]
            
            # Evolve tangent vectors (linearized equations)
            J = self.jacobian(t, y)
            Q = Q + dt * J @ Q
            
            # Gram-Schmidt orthonormalization
            Q, R = qr(Q, mode='reduced')
            
            # Accumulate logarithmic stretching factors
            for i in range(n):
                norm_i = np.linalg.norm(R[:, i])
                if norm_i > 1e-12:
                    log_stretches[i] += np.log(norm_i)
            
            # Compute current exponent estimates
            current_time = t + dt
            exponents = log_stretches / current_time
            
            # Check convergence
            if step > n_steps // 2:  # Only check after halfway
                exponents_history.append(exponents.copy())
                
                if len(exponents_history) > 100:
                    # Check if exponents have stabilized
                    recent = np.array(exponents_history[-100:])
                    std_dev = np.std(recent, axis=0)
                    
                    if np.all(std_dev < tolerance):
                        converged = True
                        logger.info(f"Lyapunov exponents converged at step {step}")
                        break
            
            t += dt
        
        # Sort exponents in descending order
        exponents = sorted(exponents, reverse=True)
        max_exp = exponents[0]
        
        # Compute Lyapunov time (predictability horizon)
        lyapunov_time = 1.0 / max_exp if max_exp > 0 else None
        
        # Compute Kaplan-Yorke dimension
        ky_dim = self._kaplan_yorke_dimension(exponents)
        
        return LyapunovResult(
            exponents=exponents,
            max_exponent=max_exp,
            is_chaotic=max_exp > 0,
            lyapunov_time=lyapunov_time,
            kaplan_yorke_dimension=ky_dim,
            convergence_achieved=converged,
            iterations=step + 1,
        )
    
    def _wolf_method(
        self,
        y0: np.ndarray,
        t_span: tuple[float, float],
        dt: float,
        n_steps: int,
    ) -> LyapunovResult:
        """
        Compute maximal Lyapunov exponent using Wolf algorithm.
        
        This method is faster but only computes λ₁ (maximal exponent).
        It tracks the divergence of two nearby trajectories.
        """
        n = self.n_dims
        
        # Reference trajectory
        y_ref = y0.copy()
        
        # Perturbed trajectory (infinitesimally close)
        epsilon = 1e-8
        y_pert = y0 + epsilon * np.random.randn(n)
        y_pert = y_pert / np.linalg.norm(y_pert - y_ref) * epsilon
        
        total_log_divergence = 0.0
        t = t_span[0]
        renormalizations = 0
        
        for step in range(n_steps):
            # Evolve both trajectories by dt
            sol_ref = solve_ivp(
                self.system,
                (t, t + dt),
                y_ref,
                method='RK45',
                rtol=1e-8,
                atol=1e-10,
            )
            y_ref_new = sol_ref.y[:, -1]
            
            sol_pert = solve_ivp(
                self.system,
                (t, t + dt),
                y_pert,
                method='RK45',
                rtol=1e-8,
                atol=1e-10,
            )
            y_pert_new = sol_pert.y[:, -1]
            
            # Compute separation
            separation = y_pert_new - y_ref_new
            separation_norm = np.linalg.norm(separation)
            
            if separation_norm > epsilon:
                # Accumulate logarithmic divergence
                total_log_divergence += np.log(separation_norm / epsilon)
                renormalizations += 1
                
                # Renormalize perturbation
                y_pert = y_ref_new + epsilon * separation / separation_norm
            
            y_ref = y_ref_new
            t += dt
        
        # Compute maximal exponent
        current_time = t - t_span[0]
        max_exp = total_log_divergence / current_time if renormalizations > 0 else 0.0
        
        # Compute Lyapunov time
        lyapunov_time = 1.0 / max_exp if max_exp > 0 else None
        
        return LyapunovResult(
            exponents=[max_exp] + [0.0] * (n - 1),  # Only λ₁ is accurate
            max_exponent=max_exp,
            is_chaotic=max_exp > 0,
            lyapunov_time=lyapunov_time,
            kaplan_yorke_dimension=None,  # Need full spectrum
            convergence_achieved=renormalizations > 10,
            iterations=step + 1,
        )
    
    def _kaplan_yorke_dimension(self, exponents: list[float]) -> float | None:
        """
        Compute Kaplan-Yorke (Lyapunov) dimension.
        
        D_KY = j + (λ₁ + λ₂ + ... + λ_j) / |λ_{j+1}|
        where j is the largest integer such that λ₁ + ... + λ_j ≥ 0
        """
        cumsum = 0.0
        
        for j, exp in enumerate(exponents):
            cumsum += exp
            
            if cumsum < 0:
                if j == 0:
                    return None  # All exponents negative
                
                # Interpolate
                ky_dim = j + cumsum / abs(exp)
                return ky_dim
        
        # All exponents positive (rare)
        return len(exponents)
    
    def compute_maximal_exponent(
        self,
        y0: np.ndarray | list[float],
        t_span: tuple[float, float],
        method: str = "wolf",
    ) -> float:
        """
        Compute only the maximal Lyapunov exponent (faster).
        
        Args:
            y0: Initial condition
            t_span: Time span
            method: "wolf" or "two_particle"
        
        Returns:
            Maximal Lyapunov exponent λ₁
        """
        result = self.compute_exponents(
            y0, t_span, method=method, n_steps=1000
        )
        return result.max_exponent


# Convenience functions

def compute_lyapunov_exponents(
    system: Callable,
    jacobian: Callable,
    y0: np.ndarray | list[float],
    t_span: tuple[float, float],
    **kwargs,
) -> LyapunovResult:
    """
    Compute Lyapunov exponents for a dynamical system.
    
    Args:
        system: Function f(t, y) defining dy/dt = f(t, y)
        jacobian: Jacobian matrix function J(t, y)
        y0: Initial condition
        t_span: Time span (t_start, t_end)
        **kwargs: Additional arguments for compute_exponents
    
    Returns:
        LyapunovResult
    """
    n_dims = len(np.asarray(y0))
    calc = LyapunovExponentCalculator(system, jacobian, n_dims)
    return calc.compute_exponents(y0, t_span, **kwargs)


def is_chaotic(
    system: Callable,
    jacobian: Callable,
    y0: np.ndarray | list[float],
    t_span: tuple[float, float],
    threshold: float = 0.0,
) -> bool:
    """
    Determine if a system is chaotic based on maximal Lyapunov exponent.
    
    Args:
        system: Function f(t, y) defining dy/dt = f(t, y)
        jacobian: Jacobian matrix function J(t, y)
        y0: Initial condition
        t_span: Time span
        threshold: Threshold for chaos (default 0, can be >0 for robustness)
    
    Returns:
        True if λ₁ > threshold
    """
    result = compute_lyapunov_exponents(system, jacobian, y0, t_span)
    return result.max_exponent > threshold
