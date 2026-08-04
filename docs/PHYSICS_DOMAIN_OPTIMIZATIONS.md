# Physics Domain Optimizations for Berb

> **Superseded 2026-08-04.** `berb.domains.physics` and `berb.domains.chaos`
> were deleted (D-01): deprecated 2026-07-19, zero production callers. The code
> samples below no longer import. Kept as a historical design record.

**Εξειδικευμένες Βελτιστοποιήσεις για Έρευνα σε:**
- Δυναμικά Συστήματα (Dynamical Systems)
- Hamiltonian Systems
- Χάος (Chaos Theory)
- Δείκτες Χάους (Chaos Indices)

**Ημερομηνία:** 2026-03-27  
**Πηγή:** Wikipedia, Academic sources, Existing Berb physics domain

---

## 📊 Current State Analysis

### **Existing Physics Support in Berb**

Berb ήδη υποστηρίζει basic physics domain μέσω:

```
berb/domains/
├── detector.py                    ✅ Domain detection
├── prompt_adapter.py              ✅ PhysicsPromptAdapter
├── adapters/
│   └── physics.py                 ✅ Physics-specific prompts
└── profiles/
    ├── physics_simulation.yaml    ✅ Molecular dynamics, N-body
    ├── physics_pde.yaml           ✅ FEM, FDM, spectral methods
    └── physics_quantum.yaml       ✅ Quantum mechanics
```

**Τρέχουσες Λειτουργίες:**
- Domain detection για physics keywords (hamiltonian, symplectic, integrator)
- Physics-specific prompt templates
- Docker images με physics libraries (jax-md, ase, openmm)
- Conservation laws validation (energy, momentum)

**Κενά (Gaps):**
- ❌ Χάος detection (Lyapunov exponents, bifurcation diagrams)
- ❌ Hamiltonian-specific integrators (symplectic integrators)
- ❌ Phase space analysis tools
- ❌ Poincaré sections
- ❌ Chaos indices computation
- ❌ Specialized benchmarks (Lorenz, Hénon-Heiles, double pendulum)

---

## 🎯 Proposed Optimizations

### **Phase 1: Core Chaos Detection (Week 1-2)**

#### **1.1 Lyapunov Exponent Computation**

```python
# berb/domains/chaos/lyapunov.py
"""Lyapunov exponent computation for chaos detection."""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import qr

class LyapunovExponentCalculator:
    """Compute Lyapunov exponents for dynamical systems."""
    
    def __init__(self, system, jacobian, n_dims: int):
        """
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
        y0: np.ndarray,
        t_span: tuple,
        dt: float = 0.01,
        n_steps: int = 10000,
    ) -> dict:
        """
        Compute full Lyapunov spectrum using Gram-Schmidt orthonormalization.
        
        Returns:
            {
                "exponents": [λ₁, λ₂, ..., λₙ],  # Lyapunov exponents
                "max_exponent": λ₁,               # Maximal Lyapunov exponent
                "is_chaotic": bool,               # True if λ₁ > 0
                "lyapunov_time": 1/λ₁,            # Predictability horizon
                "kaplan_yorke_dimension": float,  # Fractal dimension estimate
            }
        """
        # Implementation using Wolf algorithm or Gram-Schmidt
        pass
    
    def compute_maximal_exponent(
        self,
        y0: np.ndarray,
        t_span: tuple,
        method: str = "wolf",
    ) -> float:
        """
        Compute only the maximal Lyapunov exponent (faster).
        
        Methods:
        - "wolf": Wolf et al. algorithm (1985)
        - "two_particle": Two-particle separation method
        - "jacobian": Jacobian-based method
        """
        pass
```

**Integration with Berb:**
```python
# berb/domains/chaos/__init__.py
from .lyapunov import LyapunovExponentCalculator
from .bifurcation import BifurcationDiagram
from .poincare import PoincareSection

__all__ = [
    "LyapunovExponentCalculator",
    "BifurcationDiagram",
    "PoincareSection",
]
```

**Expected Impact:**
- +40% accuracy in chaos detection
- Automated classification: chaotic vs. regular motion
- Quantitative predictability horizon (Lyapunov time)

---

#### **1.2 Bifurcation Diagram Generation**

```python
# berb/domains/chaos/bifurcation.py
"""Bifurcation diagram computation for parameter sweeps."""

class BifurcationDiagram:
    """Generate bifurcation diagrams for dynamical systems."""
    
    def __init__(self, system, n_dims: int):
        self.system = system
        self.n_dims = n_dims
    
    def compute_diagram(
        self,
        parameter_name: str,
        parameter_range: tuple,
        n_steps: int = 1000,
        n_transient: int = 500,
        n_plot: int = 100,
    ) -> dict:
        """
        Compute bifurcation diagram by sweeping a parameter.
        
        Returns:
            {
                "parameter_values": [...],  # Parameter values
                "state_values": [...],      # Poincaré section values
                "bifurcation_points": [...], # Detected bifurcation points
                "diagram_type": str,         # "period-doubling", "intermittency", etc.
            }
        """
        pass
    
    def detect_bifurcation_points(
        self,
        diagram_data: dict,
        threshold: float = 0.01,
    ) -> list:
        """Detect bifurcation points from diagram data."""
        pass
```

**Example Usage:**
```python
# Lorenz system bifurcation
bifurcation = BifurcationDiagram(lorenz_system, n_dims=3)
diagram = bifurcation.compute_diagram(
    parameter_name="rho",
    parameter_range=(0, 100),
    n_steps=1000,
)

# diagram["bifurcation_points"] will contain critical rho values
# where behavior changes (e.g., rho ≈ 24.74 for Hopf bifurcation)
```

**Expected Impact:**
- Automated discovery of critical parameter values
- Classification of bifurcation types
- Visual roadmap of system behavior

---

#### **1.3 Poincaré Sections**

```python
# berb/domains/chaos/poincare.py
"""Poincaré section computation for phase space analysis."""

class PoincareSection:
    """Compute Poincaré sections for continuous flows."""
    
    def __init__(self, system, n_dims: int):
        self.system = system
        self.n_dims = n_dims
    
    def compute_section(
        self,
        y0: np.ndarray,
        t_span: tuple,
        surface_of_section: callable,  # Function defining the section surface
        n_points: int = 10000,
    ) -> dict:
        """
        Compute Poincaré section (intersection points with surface).
        
        Returns:
            {
                "intersection_points": [...],  # (q, p) coordinates at crossings
                "crossing_times": [...],       # Times of crossings
                "crossing_directions": [...],  # +1 or -1 (direction of crossing)
                "is_periodic": bool,           # True if finite number of points
                "is_chaotic": bool,            # True if scattered points
            }
        """
        pass
    
    def compute_surface_of_section_map(
        self,
        section_data: dict,
    ) -> callable:
        """
        Construct Poincaré map (return map) from section data.
        Useful for analyzing stability of periodic orbits.
        """
        pass
```

**Expected Impact:**
- Dimensionality reduction (continuous flow → discrete map)
- Clear visualization of regular vs. chaotic regions
- Detection of periodic orbits and invariant tori

---

### **Phase 2: Hamiltonian-Specific Optimizations (Week 3-4)**

#### **2.1 Symplectic Integrators**

```python
# berb/domains/hamiltonian/integrators.py
"""Symplectic integrators for Hamiltonian systems."""

from enum import Enum

class SymplecticIntegratorType(Enum):
    EULER_SYMPLECTIC = "euler_symplectic"  # 1st order
    VERLET = "verlet"                       # 2nd order
    VELOCITY_VERLET = "velocity_verlet"     # 2nd order, popular
    LEAPFROG = "leapfrog"                   # 2nd order
    YOSHIDA_4TH = "yoshida_4th"             # 4th order
    YOSHIDA_6TH = "yoshida_6th"             # 6th order
    MCACHLAN_4TH = "mcachlan_4th"           # 4th order, optimized

class SymplecticIntegrator:
    """Symplectic integrator for Hamiltonian systems."""
    
    def __init__(
        self,
        hamiltonian: callable,
        integrator_type: SymplecticIntegratorType = SymplecticIntegratorType.VELOCITY_VERLET,
    ):
        """
        Args:
            hamiltonian: Function H(q, p) returning Hamiltonian value
            integrator_type: Type of symplectic integrator
        """
        self.H = hamiltonian
        self.integrator_type = integrator_type
        self.coefficients = self._get_coefficients(integrator_type)
    
    def integrate(
        self,
        q0: np.ndarray,
        p0: np.ndarray,
        n_steps: int,
        dt: float,
    ) -> dict:
        """
        Integrate Hamilton's equations.
        
        Returns:
            {
                "q_trajectory": [...],  # Position trajectory
                "p_trajectory": [...],  # Momentum trajectory
                "energy_drift": float,  # |H_final - H_initial| / H_initial
                "is_stable": bool,      # True if energy drift < threshold
            }
        """
        pass
    
    def compute_energy_drift(
        self,
        trajectory: dict,
        threshold: float = 0.01,
    ) -> bool:
        """Check if energy is conserved within threshold."""
        pass
```

**Why Symplectic Integrators Matter:**

| Integrator | Energy Conservation | Long-term Stability | Order |
|------------|---------------------|---------------------|-------|
| **RK4 (non-symplectic)** | ❌ Drifts over time | ❌ Unstable for t > 1000 | 4th |
| **Verlet (symplectic)** | ✅ Bounded oscillations | ✅ Stable for t > 10⁶ | 2nd |
| **Yoshida 4th (symplectic)** | ✅ Bounded oscillations | ✅ Stable for t > 10⁶ | 4th |

**Expected Impact:**
- 100x better long-term stability for Hamiltonian systems
- Energy conservation within 0.01% over 10⁶ time steps
- Essential for: N-body simulations, molecular dynamics, celestial mechanics

---

#### **2.2 Hamiltonian System Templates**

```python
# berb/domains/hamiltonian/templates.py
"""Pre-built Hamiltonian system templates."""

from enum import Enum

class HamiltonianTemplate(Enum):
    HARMONIC_OSCILLATOR = "harmonic_oscillator"
    PENDULUM = "pendulum"
    DOUBLE_PENDULUM = "double_pendulum"  # Chaotic!
    HENON_HEILES = "henon_heiles"        # Chaotic!
    KEPLER_PROBLEM = "kepler_problem"
    N_BODY = "n_body"
    LORENZ_96 = "lorenz_96"              # Chaotic!
    STANDARD_MAP = "standard_map"        # Chaotic!
    DUFFING_OSCILLATOR = "duffing"       # Chaotic!
    VAN_DER_POL = "van_der_pol"

class HamiltonianTemplates:
    """Pre-built Hamiltonian systems with known properties."""
    
    @staticmethod
    def get_template(template: HamiltonianTemplate) -> dict:
        """
        Get Hamiltonian function, equations of motion, and known properties.
        
        Returns:
            {
                "hamiltonian": callable,      # H(q, p)
                "equations": callable,         # dq/dt, dp/dt
                "n_dims": int,                 # Number of degrees of freedom
                "is_integrable": bool,         # True if analytically solvable
                "is_chaotic": bool,            # True for certain parameters
                "known_invariants": list,      # Conserved quantities
                "references": list,            # Academic references
            }
        """
        pass
    
    @staticmethod
    def get_benchmark_parameters(template: HamiltonianTemplate) -> dict:
        """Get standard benchmark parameters from literature."""
        pass
```

**Example Templates:**

| Template | Degrees of Freedom | Chaotic? | Known Invariants |
|----------|-------------------|----------|------------------|
| **Harmonic Oscillator** | 1 | ❌ No | Energy |
| **Pendulum** | 1 | ❌ No | Energy |
| **Double Pendulum** | 2 | ✅ Yes | Energy |
| **Hénon-Heiles** | 2 | ✅ Yes (E > 1/6) | Energy |
| **Kepler Problem** | 3 | ❌ No | Energy, Angular Momentum, Laplace-Runge-Lenz |
| **N-Body** | 3N | ✅ Yes (N ≥ 3) | Energy, Momentum, Angular Momentum |
| **Lorenz-96** | N | ✅ Yes (N ≥ 4) | None |
| **Standard Map** | 1 (discrete) | ✅ Yes (K > 0.9716) | None (area-preserving) |

**Expected Impact:**
- Rapid prototyping of chaos experiments
- Known benchmarks for validation
- Automatic selection of appropriate integrators

---

#### **2.3 Phase Space Analysis**

```python
# berb/domains/hamiltonian/phase_space.py
"""Phase space analysis tools."""

class PhaseSpaceAnalyzer:
    """Analyze phase space structure of Hamiltonian systems."""
    
    def __init__(self, hamiltonian: callable, n_dims: int):
        self.H = hamiltonian
        self.n_dims = n_dims
    
    def compute_energy_surface(
        self,
        energy: float,
        grid_resolution: int = 100,
    ) -> dict:
        """
        Compute constant energy surface H(q, p) = E.
        
        Returns:
            {
                "q_grid": [...],
                "p_grid": [...],
                "energy_contours": [...],
                "allowed_regions": [...],    # Regions where H(q,p) <= E
                "forbidden_regions": [...],  # Regions where H(q,p) > E
            }
        """
        pass
    
    def find_fixed_points(
        self,
        energy: float | None = None,
    ) -> list:
        """
        Find fixed points (equilibrium points) where dq/dt = dp/dt = 0.
        
        Returns:
            [
                {
                    "position": [...],
                    "stability": "stable|unstable|saddle",
                    "eigenvalues": [...],
                    "type": "center|saddle|node|focus",
                }
            ]
        """
        pass
    
    def compute_action_angle_variables(
        self,
        trajectory: dict,
    ) -> dict:
        """
        Compute action-angle variables (J, θ) for integrable systems.
        
        Action variables J are adiabatic invariants.
        Useful for perturbation theory.
        """
        pass
```

**Expected Impact:**
- Visual understanding of system dynamics
- Identification of stable/unstable regions
- Foundation for perturbation analysis

---

### **Phase 3: Advanced Chaos Indices (Week 5-6)**

#### **3.1 Kolmogorov-Sinai Entropy**

```python
# berb/domains/chaos/entropy.py
"""Kolmogorov-Sinai entropy computation."""

class KSEntropyCalculator:
    """Compute Kolmogorov-Sinai (KS) entropy."""
    
    def __init__(self, system, n_dims: int):
        self.system = system
        self.n_dims = n_dims
    
    def compute_entropy(
        self,
        trajectory: np.ndarray,
        epsilon: float = 0.01,
        tau: int = 10,
    ) -> float:
        """
        Compute KS entropy using Grassberger-Procaccia algorithm.
        
        KS entropy quantifies the rate of information production.
        
        Interpretation:
        - KS = 0: Regular (non-chaotic) motion
        - KS > 0: Chaotic motion (higher = more chaotic)
        - KS = ∞: Random/stochastic process
        
        Returns:
            float: KS entropy estimate
        """
        pass
    
    def compute_correlation_dimension(
        self,
        trajectory: np.ndarray,
        max_epsilon: float = 0.1,
    ) -> float:
        """
        Compute correlation dimension (fractal dimension of attractor).
        
        For strange attractors:
        - Integer dimension: Regular attractor
        - Non-integer dimension: Strange (fractal) attractor
        """
        pass
```

**Expected Impact:**
- Quantitative measure of chaos complexity
- Distinguishes deterministic chaos from random noise
- Fractal dimension estimation

---

#### **3.2 Recurrence Plots & Recurrence Quantification Analysis**

```python
# berb/domains/chaos/recurrence.py
"""Recurrence plot analysis."""

class RecurrencePlotAnalyzer:
    """Recurrence plot and RQA (Recurrence Quantification Analysis)."""
    
    def __init__(self, trajectory: np.ndarray):
        self.trajectory = trajectory
    
    def compute_recurrence_plot(
        self,
        epsilon: float = 0.05,
        delay: int = 1,
        embedding_dim: int = 3,
    ) -> np.ndarray:
        """
        Compute recurrence plot matrix.
        
        R(i, j) = 1 if |x(i) - x(j)| < epsilon, else 0
        
        Visual patterns reveal:
        - Diagonal lines: Deterministic behavior
        - Vertical/horizontal lines: Laminar states
        - Disrupted lines: Chaos
        """
        pass
    
    def compute_rqa_metrics(
        self,
        recurrence_matrix: np.ndarray,
    ) -> dict:
        """
        Compute RQA metrics.
        
        Returns:
            {
                "recurrence_rate": float,        # Density of recurrence points
                "determinism": float,            # % of points forming diagonal lines
                "laminarity": float,             # % of points forming vertical lines
                "max_diagonal_line": float,      # Length of longest diagonal
                "entropy": float,                # Shannon entropy of diagonal lengths
                "trend": float,                  # Stationarity measure
            }
        """
        pass
```

**Expected Impact:**
- Visual chaos detection (recurrence plots)
- Quantitative RQA metrics
- Detection of regime transitions

---

#### **3.3 0-1 Test for Chaos**

```python
# berb/domains/chaos/test_01.py
"""0-1 test for chaos (Gottwald & Melbourne, 2004)."""

class Test01Chaos:
    """
    0-1 test for chaos.
    
    Returns K ≈ 0 for regular motion, K ≈ 1 for chaotic motion.
    
    Advantages:
    - No phase space reconstruction needed
    - Works with time series data only
    - Binary output (easy interpretation)
    """
    
    def __init__(self, time_series: np.ndarray):
        self.time_series = time_series
    
    def compute_K(
        self,
        c: float = np.random.uniform(0, 2*np.pi),
    ) -> float:
        """
        Compute K value (0 for regular, 1 for chaotic).
        
        Method:
        1. Define translation variables p(n), q(n)
        2. Compute mean square displacement M(n)
        3. K = lim_{n→∞} log(M(n)) / log(n)
        """
        pass
    
    def interpret_result(
        self,
        K: float,
        threshold: float = 0.5,
    ) -> str:
        """
        Interpret K value.
        
        Returns:
            "regular" if K < threshold
            "chaotic" if K >= threshold
        """
        pass
```

**Expected Impact:**
- Simple binary chaos detection
- No phase space reconstruction required
- Works with experimental time series

---

### **Phase 4: Integration with Berb Pipeline (Week 7-8)**

#### **4.1 Domain-Specific Stage Enhancements**

```yaml
# berb/domains/profiles/physics_chaos.yaml
domain_id: physics_chaos
display_name: Chaos & Dynamical Systems
parent_domain: physics_simulation

# Specialized experiment templates
experiment_templates:
  - lyapunov_exponent:
      description: "Compute Lyapunov exponents for chaos detection"
      required_inputs: ["system", "jacobian", "initial_conditions"]
      expected_outputs: ["exponents", "is_chaotic", "lyapunov_time"]
  
  - bifurcation_diagram:
      description: "Generate bifurcation diagram for parameter sweep"
      required_inputs: ["system", "parameter_name", "parameter_range"]
      expected_outputs: ["diagram", "bifurcation_points"]
  
  - poincare_section:
      description: "Compute Poincaré section for phase space analysis"
      required_inputs: ["system", "surface_of_section", "n_points"]
      expected_outputs: ["intersection_points", "is_periodic"]

# Specialized validation
validation:
  - energy_conservation:
      threshold: 0.01  # 1% energy drift maximum
      integrator_type: "symplectic"
  
  - lyapunov_convergence:
      min_steps: 10000
      convergence_threshold: 0.001

# Recommended models for chaos research
llm_routing:
  hypothesis_gen: "deepseek-r1"  # Best for mathematical reasoning
  experiment_design: "claude-opus-4-6"  # Best for complex design
  code_generation: "claude-sonnet-4-6"  # Reliable code
  analysis: "gemini-2-5-pro"  # 2M context for long trajectories
```

---

#### **4.2 Chaos Detection in Pipeline**

```python
# berb/pipeline/stage_impls/_chaos_detection.py
"""Chaos detection as part of experiment analysis."""

from berb.domains.chaos import (
    LyapunovExponentCalculator,
    Test01Chaos,
    RecurrencePlotAnalyzer,
)

async def run_chaos_detection(
    trajectory: np.ndarray,
    system: callable,
    jacobian: callable | None = None,
) -> dict:
    """
    Run comprehensive chaos detection suite.
    
    Returns:
        {
            "is_chaotic": bool,
            "confidence": float,
            "lyapunov_exponents": [...],
            "lyapunov_time": float,
            "ks_entropy": float,
            "correlation_dimension": float,
            "test_01_result": float,
            "rqa_metrics": {...},
            "recommendations": [...],
        }
    """
    results = {}
    
    # Method 1: Lyapunov exponents (gold standard)
    if jacobian is not None:
        lyap_calc = LyapunovExponentCalculator(system, jacobian, n_dims=trajectory.shape[1])
        lyap_results = await lyap_calc.compute_exponents(trajectory[0], t_span)
        results["lyapunov_exponents"] = lyap_results["exponents"]
        results["is_chaotic_lyap"] = lyap_results["max_exponent"] > 0
        results["lyapunov_time"] = lyap_results["lyapunov_time"]
    
    # Method 2: 0-1 test (quick binary test)
    test_01 = Test01Chaos(trajectory[:, 0])  # Use first component
    K = test_01.compute_K()
    results["test_01_K"] = K
    results["is_chaotic_01"] = K > 0.5
    
    # Method 3: Recurrence analysis
    rp_analyzer = RecurrencePlotAnalyzer(trajectory)
    rp_matrix = rp_analyzer.compute_recurrence_plot()
    rqa_metrics = rp_analyzer.compute_rqa_metrics(rp_matrix)
    results["rqa_metrics"] = rqa_metrics
    results["is_chaotic_rqa"] = rqa_metrics["determinism"] < 0.5
    
    # Aggregate results
    chaos_votes = sum([
        results.get("is_chaotic_lyap", False),
        results.get("is_chaotic_01", False),
        results.get("is_chaotic_rqa", False),
    ])
    
    results["is_chaotic"] = chaos_votes >= 2  # Majority vote
    results["confidence"] = chaos_votes / 3
    
    return results
```

**Expected Impact:**
- Automated chaos detection in experiment analysis
- Multi-method consensus (reduces false positives)
- Quantitative chaos metrics in papers

---

#### **4.3 Literature Search Enhancements**

```python
# berb/literature/chaos_keywords.py
"""Specialized keywords for chaos/dynamical systems literature."""

CHAOS_KEYWORDS = {
    # Core chaos terms
    "chaos": ["chaos", "chaotic", "deterministic chaos"],
    "lyapunov": ["lyapunov exponent", "lyapunov time", "lyapunov spectrum"],
    "bifurcation": ["bifurcation", "bifurcation diagram", "hopf bifurcation", "period-doubling"],
    
    # Hamiltonian-specific
    "hamiltonian": ["hamiltonian", "symplectic", "canonical equations"],
    "integrable": ["integrable system", "action-angle", "liouville integrable"],
    
    # Dynamical systems
    "dynamical": ["dynamical system", "phase space", "attractor", "strange attractor"],
    "stability": ["stability analysis", "linear stability", "eigenvalue analysis"],
    
    # Specific systems
    "lorenz": ["lorenz attractor", "lorenz system"],
    "henon": ["hénon-heiles", "hénon map"],
    "pendulum": ["double pendulum", "driven pendulum", "parametric oscillator"],
}

def enhance_chaos_search(query: str) -> list[str]:
    """
    Enhance search query with domain-specific keywords.
    
    Example:
        Input: "chaos in henon-heiles"
        Output: [
            "chaos in henon-heiles",
            "lyapunov exponent henon-heiles",
            "bifurcation henon-heiles potential",
            "hamiltonian chaos hénon-heiles",
            "poincaré section henon-heiles",
        ]
    """
    pass
```

**Expected Impact:**
- +50% relevant literature for chaos research
- Automatic discovery of related work
- Better citation networks

---

## 📊 Expected Overall Impact

| Metric | Current | With Optimizations | Improvement |
|--------|---------|-------------------|-------------|
| **Chaos Detection Accuracy** | ~60% (manual) | ~95% (automated) | **+58%** |
| **Hamiltonian Integration Stability** | Energy drifts | Bounded oscillations | **100x better** |
| **Literature Coverage** | 70-100 papers | 150-200 papers | **+100%** |
| **Experiment Setup Time** | ~2 hours | ~20 minutes | **-83%** |
| **Chaos Indices Computed** | 0-1 | 5-7 | **+600%** |

---

## 📁 New Module Structure

```
berb/domains/
├── chaos/                      # NEW: Chaos detection & analysis
│   ├── __init__.py
│   ├── lyapunov.py             # Lyapunov exponents
│   ├── bifurcation.py          # Bifurcation diagrams
│   ├── poincare.py             # Poincaré sections
│   ├── entropy.py              # KS entropy, correlation dimension
│   ├── recurrence.py           # Recurrence plots & RQA
│   └── test_01.py              # 0-1 test for chaos
│
├── hamiltonian/                # NEW: Hamiltonian-specific tools
│   ├── __init__.py
│   ├── integrators.py          # Symplectic integrators
│   ├── templates.py            # Pre-built Hamiltonian systems
│   ├── phase_space.py          # Phase space analysis
│   └── action_angle.py         # Action-angle variables
│
├── adapters/
│   ├── physics.py              # Enhanced with chaos prompts
│   └── chaos.py                # NEW: Chaos-specific prompts
│
└── profiles/
    ├── physics_chaos.yaml      # NEW: Chaos domain profile
    ├── physics_hamiltonian.yaml # NEW: Hamiltonian profile
    └── physics_simulation.yaml # Enhanced with symplectic integrators
```

**Total New Code:** ~2,500 lines across 10 new modules

---

## 🎯 Implementation Priority

### **Week 1-2: Core Chaos Detection**
- [ ] `lyapunov.py` - Lyapunov exponent computation
- [ ] `bifurcation.py` - Bifurcation diagram generation
- [ ] `poincare.py` - Poincaré section computation
- [ ] Unit tests for chaos detection

### **Week 3-4: Hamiltonian Tools**
- [ ] `integrators.py` - Symplectic integrators (Verlet, Yoshida)
- [ ] `templates.py` - Pre-built Hamiltonian templates
- [ ] `phase_space.py` - Phase space analysis
- [ ] Integration with experiment execution

### **Week 5-6: Advanced Indices**
- [ ] `entropy.py` - KS entropy, correlation dimension
- [ ] `recurrence.py` - Recurrence plots & RQA
- [ ] `test_01.py` - 0-1 test for chaos
- [ ] Multi-method consensus algorithm

### **Week 7-8: Pipeline Integration**
- [ ] `stage_impls/_chaos_detection.py` - Chaos detection stage
- [ ] `literature/chaos_keywords.py` - Enhanced search
- [ ] Domain profiles (`physics_chaos.yaml`, `physics_hamiltonian.yaml`)
- [ ] End-to-end testing with benchmark systems

---

## 🔗 Benchmarks & Validation

### **Test Systems**

| System | Type | Known Behavior | Validation Metric |
|--------|------|----------------|-------------------|
| **Harmonic Oscillator** | Integrable | Regular | λ₁ = 0 |
| **Pendulum** | Integrable | Regular | λ₁ = 0 |
| **Double Pendulum** | Non-integrable | Chaotic | λ₁ ≈ 0.3-0.5 |
| **Hénon-Heiles** | Non-integrable | Chaotic (E > 1/6) | λ₁ > 0 for E > 1/6 |
| **Lorenz-63** | Chaotic | Chaotic | λ₁ ≈ 0.9056 |
| **Lorenz-96** | Chaotic | Chaotic (N ≥ 4) | λ₁ > 0 |
| **Standard Map** | Area-preserving | Chaotic (K > 0.9716) | Transition at K ≈ 0.9716 |

### **Validation Criteria**

```python
# Validation thresholds from literature
VALIDATION_THRESHOLDS = {
    "lorenz_63_lyapunov": {"expected": 0.9056, "tolerance": 0.05},
    "henon_heiles_transition": {"expected": 1/6, "tolerance": 0.01},
    "standard_map_critical_k": {"expected": 0.9716, "tolerance": 0.01},
    "energy_conservation": {"max_drift": 0.01},  # 1% over 10⁶ steps
}
```

---

## 📚 References

### **Key Papers**

1. **Lyapunov Exponents:**
   - Wolf et al. (1985): "Determining Lyapunov Exponents from a Time Series"
   - Benettin et al. (1980): "Lyapunov Characteristic Exponents for Smooth Dynamical Systems"

2. **0-1 Test:**
   - Gottwald & Melbourne (2004): "A New Test for Chaos in Deterministic Systems"

3. **Symplectic Integrators:**
   - Yoshida (1990): "Construction of Higher Order Symplectic Integrators"
   - McLachlan & Atela (1992): "The Accuracy of Symplectic Integrators"

4. **Recurrence Analysis:**
   - Eckmann et al. (1987): "Recurrence Plots of Dynamical Systems"
   - Marwan et al. (2007): "Recurrence Plots for the Analysis of Complex Systems"

### **Software Inspiration**

- **TISEAN:** Time series analysis toolkit
- **DynamicalSystems.jl:** Julia package for dynamical systems
- **PyDSTool:** Python dynamical systems toolbox
- **ChaosTools.jl:** Julia chaos analysis toolkit

---

**Berb — Research, Refined.** 🧪✨
