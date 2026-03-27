"""Bifurcation Diagram Computation for Dynamical Systems.

Bifurcation diagrams show how system behavior changes as a parameter varies.
They reveal:
- Critical parameter values where behavior changes
- Period-doubling cascades to chaos
- Windows of periodicity within chaotic regions

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.domains.chaos.bifurcation import BifurcationDiagram
    
    bifurcation = BifurcationDiagram(lorenz_system, n_dims=3)
    diagram = await bifurcation.compute_diagram(
        parameter_name="rho",
        parameter_range=(0, 100),
        n_steps=1000,
    )
    
    # diagram["bifurcation_points"] contains critical rho values
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from scipy.integrate import solve_ivp
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)


@dataclass
class BifurcationResult:
    """Result of bifurcation diagram computation."""
    
    parameter_name: str
    """Name of the bifurcation parameter"""
    
    parameter_values: list[float]
    """Parameter values sampled"""
    
    state_values: list[list[float]]
    """Poincaré section values at each parameter value"""
    
    bifurcation_points: list[dict[str, Any]]
    """Detected bifurcation points"""
    
    diagram_type: str
    """Type of bifurcation diagram"""
    
    is_chaotic_region: list[bool]
    """True if chaotic at each parameter value"""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "parameter_name": self.parameter_name,
            "parameter_values": self.parameter_values,
            "state_values": self.state_values,
            "bifurcation_points": self.bifurcation_points,
            "diagram_type": self.diagram_type,
            "is_chaotic_region": self.is_chaotic_region,
        }


class BifurcationDiagram:
    """Generate bifurcation diagrams for dynamical systems.
    
    Examples:
        >>> # Logistic map: x_{n+1} = r * x_n * (1 - x_n)
        >>> def logistic_map(r, x):
        ...     return r * x * (1 - x)
        >>> 
        >>> bifurcation = BifurcationDiagram(lambda t, y: [logistic_map(r, y[0]) for r in [3.0]], n_dims=1)
        >>> diagram = bifurcation.compute_1d_map_diagram(
        ...     logistic_map,
        ...     parameter_range=(2.5, 4.0),
        ...     n_steps=1000,
        ... )
    """
    
    def __init__(
        self,
        system: Callable[[float, np.ndarray], np.ndarray],
        n_dims: int,
        jacobian: Callable[[float, np.ndarray], np.ndarray] | None = None,
    ):
        """
        Initialize bifurcation diagram generator.
        
        Args:
            system: Function f(t, y, param) defining dy/dt = f(t, y, param)
            n_dims: Dimension of the system
            jacobian: Optional Jacobian for stability analysis
        """
        self.system = system
        self.n_dims = n_dims
        self.jacobian = jacobian
    
    async def compute_diagram(
        self,
        parameter_name: str,
        parameter_range: tuple[float, float],
        n_steps: int = 1000,
        n_transient: int = 500,
        n_plot: int = 100,
        y0: np.ndarray | list[float] | None = None,
        t_span: tuple[float, float] | None = None,
    ) -> BifurcationResult:
        """
        Compute bifurcation diagram by sweeping a parameter.
        
        Args:
            parameter_name: Name of parameter to sweep
            parameter_range: (param_min, param_max)
            n_steps: Number of parameter values to sample
            n_transient: Transient iterations to discard
            n_plot: Points to plot after transient
            y0: Initial condition (default: random)
            t_span: Time span for integration (default: (0, 100))
        
        Returns:
            BifurcationResult with diagram data and bifurcation points
        """
        param_min, param_max = parameter_range
        param_values = np.linspace(param_min, param_max, n_steps)
        
        state_values = []
        is_chaotic = []
        
        # Default initial condition
        if y0 is None:
            y0 = np.random.randn(self.n_dims) * 0.1
        
        # Default time span
        if t_span is None:
            t_span = (0, 100)
        
        logger.info(f"Computing bifurcation diagram for {parameter_name} from {param_min} to {param_max}")
        
        for i, param in enumerate(param_values):
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{n_steps} ({i/n_steps*100:.1f}%)")
            
            # Integrate system with current parameter
            trajectory = self._integrate_with_parameter(
                parameter_name, param, y0, t_span, n_transient + n_plot
            )
            
            if trajectory is None:
                state_values.append([])
                is_chaotic.append(False)
                continue
            
            # Discard transient
            trajectory = trajectory[n_transient:, :]
            
            # Take Poincaré section (local maxima)
            poincare_points = self._compute_poincare_section(trajectory)
            
            state_values.append(poincare_points)
            
            # Detect chaos from number of points
            is_chaotic.append(len(poincare_points) > 10)
            
            # Use last point as initial condition for next parameter
            # (continuation method)
            if len(trajectory) > 0:
                y0 = trajectory[-1, :]
        
        # Detect bifurcation points
        bifurcation_points = self._detect_bifurcation_points(
            param_values, state_values
        )
        
        # Determine diagram type
        diagram_type = self._classify_diagram(bifurcation_points, is_chaotic)
        
        return BifurcationResult(
            parameter_name=parameter_name,
            parameter_values=param_values.tolist(),
            state_values=state_values,
            bifurcation_points=bifurcation_points,
            diagram_type=diagram_type,
            is_chaotic_region=is_chaotic,
        )
    
    def _integrate_with_parameter(
        self,
        parameter_name: str,
        param: float,
        y0: np.ndarray,
        t_span: tuple[float, float],
        n_points: int,
    ) -> np.ndarray | None:
        """Integrate system with given parameter value."""
        try:
            # Create parameterized system
            def system_with_param(t, y):
                # Try to pass parameter to system
                try:
                    return self.system(t, y, **{parameter_name: param})
                except TypeError:
                    # System doesn't accept keyword arguments
                    return self.system(t, y, param)
            
            # Integrate
            t_eval = np.linspace(t_span[0], t_span[1], n_points)
            sol = solve_ivp(
                system_with_param,
                t_span,
                y0,
                method='RK45',
                t_eval=t_eval,
                rtol=1e-8,
                atol=1e-10,
            )
            
            if not sol.success:
                logger.warning(f"Integration failed for {parameter_name}={param}: {sol.message}")
                return None
            
            return sol.y.T
            
        except Exception as e:
            logger.warning(f"Error integrating for {parameter_name}={param}: {e}")
            return None
    
    def _compute_poincare_section(
        self,
        trajectory: np.ndarray,
    ) -> list[float]:
        """
        Compute Poincaré section (local maxima) from trajectory.
        
        For 1D maps, returns all points.
        For continuous flows, returns local maxima.
        """
        if self.n_dims == 1:
            # 1D map: return all points
            return trajectory[:, 0].tolist()
        
        # Higher dimensions: find local maxima in first component
        x = trajectory[:, 0]
        peaks, _ = find_peaks(x, distance=5)
        
        if len(peaks) == 0:
            # No peaks found, return all points
            return x[::10].tolist()  # Subsample
        
        # Return values at peaks
        return x[peaks].tolist()
    
    def _detect_bifurcation_points(
        self,
        param_values: np.ndarray,
        state_values: list[list[float]],
    ) -> list[dict[str, Any]]:
        """Detect bifurcation points from diagram data."""
        bifurcation_points = []
        
        # Compute number of points at each parameter value
        n_points = [len(sv) for sv in state_values]
        
        # Detect sudden changes in number of points
        for i in range(1, len(n_points) - 1):
            # Period-doubling: number of points doubles
            if n_points[i] > 0 and n_points[i-1] > 0:
                ratio = n_points[i] / n_points[i-1]
                
                if 1.8 < ratio < 2.2:  # Period-doubling
                    bifurcation_points.append({
                        "parameter": float(param_values[i]),
                        "type": "period_doubling",
                        "before_points": n_points[i-1],
                        "after_points": n_points[i],
                    })
                
                # Sudden increase to many points (onset of chaos)
                elif n_points[i] > 20 and n_points[i-1] <= 4:
                    bifurcation_points.append({
                        "parameter": float(param_values[i]),
                        "type": "onset_of_chaos",
                        "before_points": n_points[i-1],
                        "after_points": n_points[i],
                    })
                
                # Window of periodicity in chaos
                elif n_points[i] <= 4 and n_points[i-1] > 20:
                    bifurcation_points.append({
                        "parameter": float(param_values[i]),
                        "type": "periodic_window",
                        "before_points": n_points[i-1],
                        "after_points": n_points[i],
                    })
        
        return bifurcation_points
    
    def _classify_diagram(
        self,
        bifurcation_points: list[dict[str, Any]],
        is_chaotic: list[bool],
    ) -> str:
        """Classify the type of bifurcation diagram."""
        types = [bp["type"] for bp in bifurcation_points]
        
        if "period_doubling" in types:
            if "onset_of_chaos" in types:
                return "period_doubling_cascade_to_chaos"
            else:
                return "period_doubling"
        elif "onset_of_chaos" in types:
            return "intermittency_or_quasiperiodicity"
        elif "periodic_window" in types:
            return "chaos_with_windows"
        elif sum(is_chaotic) > len(is_chaotic) / 2:
            return "predominantly_chaotic"
        else:
            return "predominantly_regular"
    
    def compute_1d_map_diagram(
        self,
        map_func: Callable[[float, float], float],
        parameter_range: tuple[float, float],
        n_steps: int = 1000,
        n_transient: int = 500,
        n_plot: int = 100,
        x0: float = 0.5,
    ) -> BifurcationResult:
        """
        Compute bifurcation diagram for 1D discrete map.
        
        Args:
            map_func: Function f(r, x) defining x_{n+1} = f(r, x_n)
            parameter_range: (r_min, r_max)
            n_steps: Number of parameter values
            n_transient: Transient iterations to discard
            n_plot: Points to plot after transient
            x0: Initial condition
        
        Returns:
            BifurcationResult
        """
        r_min, r_max = parameter_range
        r_values = np.linspace(r_min, r_max, n_steps)
        
        state_values = []
        is_chaotic = []
        
        x = x0
        
        for r in r_values:
            # Iterate map
            for _ in range(n_transient):
                x = map_func(r, x)
                # Keep x bounded
                if not np.isfinite(x):
                    x = x0
                    break
            
            # Collect points
            points = []
            for _ in range(n_plot):
                x = map_func(r, x)
                if np.isfinite(x):
                    points.append(x)
            
            state_values.append(points)
            
            # Estimate Lyapunov exponent for this r
            lyap = self._compute_map_lyapunov(map_func, r, x, n_transient)
            is_chaotic.append(lyap > 0)
        
        # Detect bifurcation points
        bifurcation_points = self._detect_bifurcation_points(
            r_values, state_values
        )
        
        diagram_type = self._classify_diagram(bifurcation_points, is_chaotic)
        
        return BifurcationResult(
            parameter_name="r",
            parameter_values=r_values.tolist(),
            state_values=state_values,
            bifurcation_points=bifurcation_points,
            diagram_type=diagram_type,
            is_chaotic_region=is_chaotic,
        )
    
    def _compute_map_lyapunov(
        self,
        map_func: Callable[[float, float], float],
        r: float,
        x0: float,
        n_iter: int,
    ) -> float:
        """Compute Lyapunov exponent for 1D map."""
        x = x0
        lyap_sum = 0.0
        
        for _ in range(n_iter):
            # Compute derivative numerically
            eps = 1e-8
            f_x = map_func(r, x)
            f_x_eps = map_func(r, x + eps)
            derivative = (f_x_eps - f_x) / eps
            
            if abs(derivative) > 1e-12:
                lyap_sum += np.log(abs(derivative))
            
            x = f_x
            
            if not np.isfinite(x):
                return 0.0
        
        return lyap_sum / n_iter
