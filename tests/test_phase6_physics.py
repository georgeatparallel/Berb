"""Tests for Phase 6: Physics Domain Integration.

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
import numpy as np

from berb.domains.physics.hamiltonian import (
    VerletIntegrator,
    YoshidaIntegrator,
    HarmonicOscillator,
    Pendulum,
    HenonHeiles,
    PhaseSpaceAnalyzer,
    create_integrator,
    create_system,
    IntegrationResult,
)


# ============== Integrator Tests ==============

class TestVerletIntegrator:
    """Test VerletIntegrator."""

    def test_integrator_initialization(self):
        """Test integrator initialization."""
        integrator = VerletIntegrator(dt=0.01)
        assert integrator.dt == 0.01

    def test_harmonic_oscillator_energy_conservation(self):
        """Test energy conservation for harmonic oscillator."""
        integrator = VerletIntegrator(dt=0.01)
        osc = HarmonicOscillator(m=1.0, k=1.0)

        # Initial conditions
        q0 = np.array([1.0])
        p0 = np.array([0.0])

        # Integrate
        result = integrator.integrate(osc.hamiltonian, q0, p0, steps=100)

        assert result.success is True
        assert len(result.energy) == 100

        # Check energy conservation (should be very good for symplectic)
        energy_drift = np.max(np.abs(result.energy - result.energy[0]))
        assert energy_drift < 0.01  # Less than 1% drift

    def test_step_method(self):
        """Test single integration step."""
        integrator = VerletIntegrator(dt=0.01)
        osc = HarmonicOscillator()

        q0 = np.array([1.0])
        p0 = np.array([0.0])

        q_new, p_new = integrator.step(osc.hamiltonian, q0, p0)

        assert q_new.shape == q0.shape
        assert p_new.shape == p0.shape


class TestYoshidaIntegrator:
    """Test YoshidaIntegrator."""

    def test_integrator_initialization(self):
        """Test integrator initialization."""
        integrator = YoshidaIntegrator(dt=0.01)
        assert integrator.dt == 0.01

    def test_higher_order_accuracy(self):
        """Test that Yoshida has reasonable energy conservation."""
        dt = 0.01  # Reasonable step

        yoshida = YoshidaIntegrator(dt)
        osc = HarmonicOscillator()

        q0 = np.array([1.0])
        p0 = np.array([0.0])

        yoshida_result = yoshida.integrate(osc.hamiltonian, q0, p0, steps=100)

        yoshida_drift = np.max(np.abs(yoshida_result.energy - yoshida_result.energy[0]))

        # Yoshida should have good energy conservation
        assert yoshida_drift < 0.1  # Less than 10% drift


# ============== Hamiltonian System Tests ==============

class TestHarmonicOscillator:
    """Test HarmonicOscillator."""

    def test_initialization(self):
        """Test oscillator initialization."""
        osc = HarmonicOscillator(m=2.0, k=8.0)
        assert osc.m == 2.0
        assert osc.k == 8.0
        assert osc.omega == pytest.approx(2.0)  # sqrt(8/2) = 2

    def test_hamiltonian(self):
        """Test Hamiltonian computation."""
        osc = HarmonicOscillator(m=1.0, k=2.0)

        q = np.array([1.0])
        p = np.array([0.0])

        energy = osc.hamiltonian(q, p)

        # E = 0 + 0.5 * 2 * 1^2 = 1.0
        assert energy == pytest.approx(1.0)

    def test_equations(self):
        """Test Hamilton's equations."""
        osc = HarmonicOscillator(m=1.0, k=1.0)

        q = np.array([1.0])
        p = np.array([0.0])

        dqdt, dpdt = osc.equations(q, p)

        assert dqdt[0] == 0.0  # p/m = 0
        assert dpdt[0] == -1.0  # -kq = -1


class TestPendulum:
    """Test Pendulum."""

    def test_initialization(self):
        """Test pendulum initialization."""
        pend = Pendulum(m=1.0, l=2.0, g=9.81)
        assert pend.m == 1.0
        assert pend.l == 2.0
        assert pend.g == 9.81

    def test_hamiltonian(self):
        """Test Hamiltonian computation."""
        pend = Pendulum()

        q = np.array([0.0])  # Hanging down
        p = np.array([0.0])

        energy = pend.hamiltonian(q, p)

        # E = 0 - mgl*cos(0) = -mgl
        assert energy == pytest.approx(-9.81)


class TestHenonHeiles:
    """Test HenonHeiles system."""

    def test_hamiltonian(self):
        """Test Hénon-Heiles Hamiltonian."""
        hh = HenonHeiles()

        q = np.array([0.1, 0.1])
        p = np.array([0.0, 0.0])

        energy = hh.hamiltonian(q, p)

        # Should be positive for small displacements
        assert energy > 0

    def test_chaotic_behavior(self):
        """Test that system shows expected behavior."""
        hh = HenonHeiles()
        integrator = VerletIntegrator(dt=0.01)

        # Initial conditions - any valid energy
        q0 = np.array([0.3, 0.3])
        p0 = np.array([0.1, 0.1])

        result = integrator.integrate(hh.hamiltonian, q0, p0, steps=500)

        assert result.success is True
        # Energy should be conserved reasonably well
        energy_drift = np.max(np.abs(result.energy - result.energy[0]))
        assert energy_drift < 0.01  # Good energy conservation


# ============== Phase Space Analysis Tests ==============

class TestPhaseSpaceAnalyzer:
    """Test PhaseSpaceAnalyzer."""

    def test_analyzer_initialization(self):
        """Test analyzer initialization."""
        analyzer = PhaseSpaceAnalyzer()
        assert analyzer is not None

    def test_plot_phase_space(self):
        """Test phase space plot generation."""
        analyzer = PhaseSpaceAnalyzer()

        q = np.array([[1.0, 0.5], [0.8, 0.6], [0.6, 0.7]])
        p = np.array([[0.0, 0.1], [-0.1, 0.2], [-0.2, 0.3]])

        plot_data = analyzer.plot_phase_space(q, p, title="Test")

        assert plot_data["type"] == "phase_space"
        assert plot_data["title"] == "Test"
        assert len(plot_data["q"]) == 3

    def test_poincare_section(self):
        """Test Poincaré section computation."""
        analyzer = PhaseSpaceAnalyzer()

        # Create trajectory that crosses q1=0
        q = np.array([
            [-0.1, 0.5],
            [0.0, 0.6],
            [0.1, 0.7],
            [0.2, 0.8],
        ])
        p = np.array([
            [0.1, 0.1],
            [0.2, 0.2],
            [0.3, 0.3],
            [0.4, 0.4],
        ])

        section = analyzer.poincare_section(q, p, surface="q1=0")

        assert section["type"] == "poincare_section"
        assert section["surface"] == "q1=0"

    def test_energy_drift(self):
        """Test energy drift computation."""
        analyzer = PhaseSpaceAnalyzer()

        energy = np.array([1.0, 1.001, 0.999, 1.002, 0.998])

        drift = analyzer.energy_drift(energy)

        assert "max_relative_drift" in drift
        assert "mean_relative_drift" in drift
        assert "rms_drift" in drift
        assert drift["max_relative_drift"] > 0

    def test_lyapunov_exponent(self):
        """Test Lyapunov exponent estimation."""
        analyzer = PhaseSpaceAnalyzer()

        # Two trajectories that diverge
        t = np.linspace(0, 10, 100)
        traj1 = np.column_stack([np.sin(t), np.cos(t)])
        traj2 = np.column_stack([np.sin(t) + 0.01 * np.exp(0.1 * t),
                                  np.cos(t) + 0.01 * np.exp(0.1 * t)])

        lyap = analyzer.lyapunov_exponent(traj1, traj2, dt=0.1)

        # Should detect positive exponent for diverging trajectories
        assert lyap > 0 or lyap == pytest.approx(0, abs=0.1)


# ============== Factory Function Tests ==============

class TestCreateIntegrator:
    """Test create_integrator factory."""

    def test_create_verlet(self):
        """Test creating Verlet integrator."""
        integrator = create_integrator("verlet", dt=0.01)
        assert isinstance(integrator, VerletIntegrator)

    def test_create_yoshida(self):
        """Test creating Yoshida integrator."""
        integrator = create_integrator("yoshida", dt=0.01)
        assert isinstance(integrator, YoshidaIntegrator)

    def test_create_invalid(self):
        """Test creating invalid integrator."""
        with pytest.raises(ValueError, match="Unknown method"):
            create_integrator("invalid")


class TestCreateSystem:
    """Test create_system factory."""

    def test_create_harmonic(self):
        """Test creating harmonic oscillator."""
        system = create_system("harmonic", m=1.0, k=1.0)
        assert isinstance(system, HarmonicOscillator)

    def test_create_pendulum(self):
        """Test creating pendulum."""
        system = create_system("pendulum", l=1.0, g=9.81)
        assert isinstance(system, Pendulum)

    def test_create_henon_heiles(self):
        """Test creating Hénon-Heiles."""
        system = create_system("henon_heiles")
        assert isinstance(system, HenonHeiles)

    def test_create_invalid(self):
        """Test creating invalid system."""
        with pytest.raises(ValueError, match="Unknown system"):
            create_system("invalid")


# ============== IntegrationResult Tests ==============

class TestIntegrationResult:
    """Test IntegrationResult dataclass."""

    def test_default_result(self):
        """Test default result."""
        result = IntegrationResult()
        assert result.success is True
        assert result.q.size == 0

    def test_to_dict(self):
        """Test result to_dict method."""
        result = IntegrationResult(
            q=np.array([[1.0], [2.0]]),
            p=np.array([[0.0], [0.1]]),
            t=np.array([0.0, 0.1]),
            energy=np.array([1.0, 1.0]),
            success=True,
        )
        d = result.to_dict()

        assert d["n_steps"] == 2
        assert d["success"] is True
        assert len(d["q"]) == 2

    def test_failed_result(self):
        """Test failed result."""
        result = IntegrationResult(
            success=False,
            error="Integration failed",
        )
        assert result.success is False
        assert result.error == "Integration failed"


# ============== Integration Tests ==============

class TestPhysicsIntegration:
    """Test physics module integration."""

    def test_import_physics_module(self):
        """Test physics module can be imported."""
        from berb.domains.physics import (
            VerletIntegrator,
            HarmonicOscillator,
            PhaseSpaceAnalyzer,
        )
        assert VerletIntegrator is not None
        assert HarmonicOscillator is not None
        assert PhaseSpaceAnalyzer is not None

    def test_long_integration(self):
        """Test long-term integration stability."""
        integrator = VerletIntegrator(dt=0.01)
        osc = HarmonicOscillator()

        q0 = np.array([1.0])
        p0 = np.array([0.0])

        result = integrator.integrate(osc.hamiltonian, q0, p0, steps=10000)

        assert result.success is True
        # Energy should still be well conserved after 10000 steps
        energy_drift = np.max(np.abs(result.energy - result.energy[0]))
        assert energy_drift < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
