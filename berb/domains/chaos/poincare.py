"""Poincaré Section Computation for Phase Space Analysis.

Poincaré sections reduce continuous flows to discrete maps by recording
intersections with a surface of section. They reveal:
- Periodic orbits (finite number of points)
- Quasiperiodic motion (closed curves)
- Chaotic motion (scattered points)

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.chaos.poincare import PoincareSection
    
    section = PoincareSection(hamiltonian_system, n_dims=4)
    result = await section.compute_section(
        y0=[1, 0, 0, 1],
        t_span=(0, 1000),
        surface_of_section=lambda y: y[0],  # Cross when y[0] = 0
    )
    
    # result["intersection_points"] contains (q, p) coordinates
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

logger = logging.getLogger(__name__)


@dataclass
class PoincareResult:
    """Result of Poincaré section computation."""
    
    intersection_points: list[list[float]]
    """(q, p) coordinates at crossings"""
    
    crossing_times: list[float]
    """Times of crossings"""
    
    crossing_directions: list[int]
    """Direction of crossing (+1 or -1)"""
    
    is_periodic: bool
    """True if finite number of points (periodic orbit)"""
    
    is_chaotic: bool
    """True if scattered points (chaotic motion)"""
    
    n_points: int
    """Total number of crossings"""
    
    period: float | None
    """Estimated period if periodic"""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "intersection_points": self.intersection_points,
            "crossing_times": self.crossing_times,
            "crossing_directions": self.crossing_directions,
            "is_periodic": self.is_periodic,
            "is_chaotic": self.is_chaotic,
            "n_points": self.n_points,
            "period": self.period,
        }


class PoincareSection:
    """Compute Poincaré sections for continuous flows.
    
    Examples:
        >>> # Double pendulum (chaotic for high energy)
        >>> def double_pendulum(t, y):
        ...     # y = [theta1, omega1, theta2, omega2]
        ...     # Returns dy/dt
        ...     pass
        >>> 
        >>> section = PoincareSection(double_pendulum, n_dims=4)
        >>> result = section.compute_section(
        ...     y0=[np.pi/2, 0, np.pi, 0],
        ...     t_span=(0, 1000),
        ...     surface_func=lambda y: y[0],  # Cross when theta1 = 0
        ...     surface_value=0.0,
        ... )
    """
    
    def __init__(
        self,
        system: Callable[[float, np.ndarray], np.ndarray],
        n_dims: int,
        jacobian: Callable[[float, np.ndarray], np.ndarray] | None = None,
    ):
        """
        Initialize Poincaré section computer.
        
        Args:
            system: Function f(t, y) defining dy/dt = f(t, y)
            n_dims: Dimension of the system (must be even for Hamiltonian)
            jacobian: Optional Jacobian for stability analysis
        """
        self.system = system
        self.n_dims = n_dims
        self.jacobian = jacobian
    
    async def compute_section(
        self,
        y0: np.ndarray | list[float],
        t_span: tuple[float, float],
        surface_func: Callable[[np.ndarray], float],
        surface_value: float = 0.0,
        max_points: int = 10000,
        dt_max: float = 1.0,
    ) -> PoincareResult:
        """
        Compute Poincaré section (intersection points with surface).
        
        Args:
            y0: Initial condition
            t_span: Time span (t_start, t_end)
            surface_func: Function g(y) defining surface g(y) = surface_value
            surface_value: Value of surface function (default 0)
            max_points: Maximum number of crossings to record
            dt_max: Maximum time step between crossings
        
        Returns:
            PoincareResult with intersection points and diagnostics
        """
        y0 = np.asarray(y0, dtype=float)
        
        intersection_points = []
        crossing_times = []
        crossing_directions = []
        
        t_current = t_span[0]
        y_current = y0
        
        logger.info("Computing Poincaré section")
        
        while t_current < t_span[1] and len(intersection_points) < max_points:
            # Integrate forward
            t_next = min(t_current + dt_max, t_span[1])
            
            sol = solve_ivp(
                self.system,
                (t_current, t_next),
                y_current,
                method='RK45',
                rtol=1e-8,
                atol=1e-10,
                dense_output=True,  # For event location
            )
            
            if not sol.success:
                logger.warning(f"Integration failed: {sol.message}")
                break
            
            # Find crossings using event detection
            crossings = self._find_crossings(
                sol, surface_func, surface_value
            )
            
            for t_cross, y_cross, direction in crossings:
                # Record crossing
                intersection_points.append(y_cross.tolist())
                crossing_times.append(t_cross)
                crossing_directions.append(direction)
                
                if len(intersection_points) >= max_points:
                    break
            
            # Continue from end of integration
            y_current = sol.y[:, -1]
            t_current = t_next
        
        # Analyze results
        is_periodic, period = self._analyze_periodicity(
            intersection_points, crossing_times
        )
        
        is_chaotic = self._analyze_chaos(intersection_points)
        
        return PoincareResult(
            intersection_points=intersection_points,
            crossing_times=crossing_times,
            crossing_directions=crossing_directions,
            is_periodic=is_periodic,
            is_chaotic=is_chaotic,
            n_points=len(intersection_points),
            period=period,
        )
    
    def _find_crossings(
        self,
        solution: Any,
        surface_func: Callable[[np.ndarray], float],
        surface_value: float,
    ) -> list[tuple[float, np.ndarray, int]]:
        """
        Find all crossings of surface within solution.
        
        Returns:
            List of (t_cross, y_cross, direction) tuples
        """
        crossings = []
        t_eval = solution.t
        y_eval = solution.y.T
        
        # Evaluate surface function at all points
        g_values = [surface_func(y) - surface_value for y in y_eval]
        
        # Find sign changes
        for i in range(len(g_values) - 1):
            if g_values[i] * g_values[i+1] < 0:
                # Sign change: crossing detected
                direction = 1 if g_values[i+1] > g_values[i] else -1
                
                # Refine crossing time using Brent's method
                t_cross = brentq(
                    lambda t: surface_func(solution.sol(t)) - surface_value,
                    t_eval[i],
                    t_eval[i+1],
                )
                
                # Get state at crossing
                y_cross = solution.sol(t_cross)
                
                crossings.append((t_cross, y_cross, direction))
        
        return crossings
    
    def _analyze_periodicity(
        self,
        points: list[list[float]],
        times: list[float],
    ) -> tuple[bool, float | None]:
        """
        Analyze if motion is periodic based on Poincaré section.
        
        Returns:
            (is_periodic, period)
        """
        if len(points) < 10:
            return False, None
        
        # Convert to numpy array
        points_arr = np.array(points)
        
        # Check if points cluster around finite number of locations
        # Use simple clustering: points within tolerance are same
        tolerance = 0.01 * (np.max(points_arr) - np.min(points_arr))
        
        unique_points = []
        for point in points_arr:
            is_new = True
            for unique in unique_points:
                if np.linalg.norm(point - unique) < tolerance:
                    is_new = False
                    break
            if is_new:
                unique_points.append(point)
        
        # If finite number of unique points, motion is periodic
        if len(unique_points) <= 10:
            # Estimate period from crossing times
            if len(times) > len(unique_points):
                period = (times[-1] - times[0]) / (len(times) / len(unique_points))
                return True, period
        
        return False, None
    
    def _analyze_chaos(
        self,
        points: list[list[float]],
    ) -> bool:
        """
        Analyze if motion is chaotic based on Poincaré section.
        
        Chaotic motion shows:
        - Scattered points (not on smooth curves)
        - Fractal structure
        - Sensitive dependence on initial conditions
        """
        if len(points) < 100:
            return False  # Not enough data
        
        points_arr = np.array(points)
        
        # Simple heuristic: check if points fill area vs. lie on curves
        # Compute 2D histogram and check uniformity
        
        if self.n_dims >= 2:
            # Use first two coordinates
            x = points_arr[:, 0]
            y = points_arr[:, 1]
            
            # Compute correlation dimension (simplified)
            # If D > 1.5, likely chaotic
            n_neighbors = min(10, len(points) // 10)
            
            # Count neighbors within radius r for different r
            radii = np.logspace(-3, 0, 10)
            counts = []
            
            for r in radii:
                count = 0
                for i in range(min(100, len(points))):
                    distances = np.sqrt((x - x[i])**2 + **(y - y[i])2)
                    count += np.sum(distances < r)
                counts.append(count / len(points))
            
            # Fit slope in log-log plot (correlation dimension)
            log_r = np.log(radii)
            log_count = np.log(counts + 1)  # Avoid log(0)
            
            if len(log_r) > 2:
                slope = np.polyfit(log_r, log_count, 1)[0]
                
                # Slope > 1.5 suggests chaotic motion
                return slope > 1.5
        
        return False
    
    def compute_surface_of_section_map(
        self,
        result: PoincareResult,
    ) -> Callable[[np.ndarray], np.ndarray] | None:
        """
        Construct Poincaré map (return map) from section data.
        
        The Poincaré map P: Σ → Σ maps one crossing to the next.
        Useful for analyzing stability of periodic orbits.
        
        Args:
            result: PoincareResult from compute_section
        
        Returns:
            Poincaré map function P(y) or None if not enough points
        """
        if len(result.intersection_points) < 10:
            return None
        
        points = np.array(result.intersection_points)
        
        # Simple interpolation-based map
        def poincare_map(y: np.ndarray) -> np.ndarray:
            """Map from one crossing to next."""
            # Find nearest neighbor in recorded points
            distances = np.linalg.norm(points - y, axis=1)
            nearest_idx = np.argmin(distances)
            
            # Return next point (with wraparound)
            next_idx = (nearest_idx + 1) % len(points)
            return points[next_idx]
        
        return poincare_map


# Convenience functions

def compute_poincare_section(
    system: Callable,
    y0: np.ndarray | list[float],
    t_span: tuple[float, float],
    surface_func: Callable[[np.ndarray], float],
    **kwargs,
) -> PoincareResult:
    """
    Compute Poincaré section for a dynamical system.
    
    Args:
        system: Function f(t, y) defining dy/dt = f(t, y)
        y0: Initial condition
        t_span: Time span (t_start, t_end)
        surface_func: Function g(y) defining surface g(y) = 0
        **kwargs: Additional arguments for compute_section
    
    Returns:
        PoincareResult
    """
    n_dims = len(np.asarray(y0))
    section = PoincareSection(system, n_dims)
    return section.compute_section(y0, t_span, surface_func, **kwargs)


def hamiltonian_poincare_section(
    hamiltonian: Callable[[np.ndarray, np.ndarray], float],
    q0: np.ndarray | list[float],
    p0: np.ndarray | list[float],
    t_span: tuple[float, float],
    surface_coord: str = "q1",
    surface_value: float = 0.0,
) -> PoincareResult:
    """
    Compute Poincaré section for Hamiltonian system.
    
    Automatically constructs equations of motion from Hamiltonian.
    
    Args:
        hamiltonian: Function H(q, p) returning Hamiltonian value
        q0: Initial positions
        p0: Initial momenta
        t_span: Time span
        surface_coord: Coordinate for surface (e.g., "q1", "p2")
        surface_value: Value of surface coordinate
    
    Returns:
        PoincareResult
    """
    q0 = np.asarray(q0, dtype=float)
    p0 = np.asarray(p0, dtype=float)
    
    n_dof = len(q0)  # Number of degrees of freedom
    n_dims = 2 * n_dof
    
    # Construct Hamilton's equations
    def hamiltons_equations(t, y):
        """dq/dt = ∂H/∂p, dp/dt = -∂H/∂q"""
        q = y[:n_dof]
        p = y[n_dof:]
        
        # Numerical derivatives
        eps = 1e-8
        
        dqdt = np.zeros(n_dof)
        dpdt = np.zeros(n_dof)
        
        # ∂H/∂p (for dq/dt)
        for i in range(n_dof):
            p_plus = p.copy()
            p_plus[i] += eps
            p_minus = p.copy()
            p_minus[i] -= eps
            dqdt[i] = (hamiltonian(q, p_plus) - hamiltonian(q, p_minus)) / (2 * eps)
        
        # ∂H/∂q (for dp/dt)
        for i in range(n_dof):
            q_plus = q.copy()
            q_plus[i] += eps
            q_minus = q.copy()
            q_minus[i] -= eps
            dpdt[i] = -(hamiltonian(q_plus, p) - hamiltonian(q_minus, p)) / (2 * eps)
        
        return np.concatenate([dqdt, dpdt])
    
    # Construct surface function
    coord_names = [f"q{i+1}" for i in range(n_dof)] + [f"p{i+1}" for i in range(n_dof)]
    
    try:
        coord_idx = coord_names.index(surface_coord)
    except ValueError:
        raise ValueError(f"Unknown coordinate: {surface_coord}. Use one of {coord_names}")
    
    def surface_func(y: np.ndarray) -> float:
        return y[coord_idx] - surface_value
    
    # Compute section
    y0 = np.concatenate([q0, p0])
    section = PoincareSection(hamiltons_equations, n_dims)
    
    return section.compute_section(
        y0, t_span, surface_func, surface_value=surface_value
    )
