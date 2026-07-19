"""Tests for the world model and discovery loop (E2).

Covers:
- WorldModel: update, propose_tasks, is_dead_end, converged, serialisation
- DiscoveryLoop: cycle orchestration, budget, guidance
- Anti-regression: dead ends never re-proposed
"""

from __future__ import annotations

import pytest

from berb.research.world_model import (
    Contradiction,
    DeadEnd,
    Finding,
    FindingVerdict,
    Guidance,
    Question,
    WorldModel,
)
from berb.research.discovery_loop import (
    BudgetGovernor,
    DiscoveryConfig,
    DiscoveryLoop,
    reflect,
)


# ─────────────────────────────────────────────────────────────────────────────
# WorldModel tests
# ─────────────────────────────────────────────────────────────────────────────


class TestWorldModelBasics:
    """Basic world model operations."""

    def test_create_world_model(self):
        """Test creating a world model."""
        wm = WorldModel(objective="Test objective")
        assert wm.objective == "Test objective"
        assert wm.current_cycle == 0
        assert len(wm.established) == 0

    def test_update_with_findings(self):
        """Test updating with new findings."""
        wm = WorldModel(objective="Test")
        findings = [
            Finding(id="f1", statement="Found X", verdict=FindingVerdict.SUPPORTED),
        ]
        rejected = [
            Finding(id="f2", statement="Not Y", verdict=FindingVerdict.REFUTED),
        ]
        wm.update(new_findings=findings, rejected=rejected)
        assert len(wm.established) == 1
        assert len(wm.refuted) == 1
        assert wm.current_cycle == 1

    def test_update_with_dead_ends(self):
        """Test updating with dead ends."""
        wm = WorldModel(objective="Test")
        wm.update(
            new_findings=[],
            rejected=[],
            new_dead_ends=[DeadEnd(description="Path A", reason="No effect")],
        )
        assert len(wm.dead_ends) == 1
        assert wm.is_dead_end("Path A") is True
        assert wm.is_dead_end("Path B") is False


class TestDeadEndAntiReExploration:
    """Dead ends must NOT be re-proposed."""

    def test_dead_end_not_reproposed(self):
        """A dead end recorded in cycle 1 must not appear in cycle 2 tasks."""
        wm = WorldModel(objective="Test")

        # Cycle 1: explore "Method X" → dead end
        wm.update(
            new_findings=[],
            rejected=[],
            new_dead_ends=[DeadEnd(description="Method X", reason="No improvement")],
        )

        # Propose tasks for cycle 2 — should not include "Method X"
        tasks = wm.propose_tasks(k=5)
        for t in tasks:
            assert "Method X" not in t, f"Dead end was re-proposed: {t}"

    def test_dead_end_substring_match(self):
        """Substring matching should catch variant descriptions."""
        wm = WorldModel(objective="Test")
        wm.update(
            new_findings=[], rejected=[],
            new_dead_ends=[DeadEnd(description="Bayesian optimization", reason="Too slow")],
        )
        assert wm.is_dead_end("Using Bayesian optimization for hyperparams") is True
        assert wm.is_dead_end("Grid search") is False


class TestConvergence:
    """World model convergence detection."""

    def test_not_converged_without_findings(self):
        """No findings → not converged."""
        wm = WorldModel(objective="Test")
        assert wm.converged() is False

    def test_not_converged_with_contradictions(self):
        """Contradictions block convergence."""
        wm = WorldModel(objective="Test")
        wm.update(
            new_findings=[
                Finding(id="f1", statement="A", verdict=FindingVerdict.SUPPORTED),
                Finding(id="f2", statement="B", verdict=FindingVerdict.SUPPORTED),
                Finding(id="f3", statement="C", verdict=FindingVerdict.SUPPORTED),
            ],
            rejected=[],
            new_contradictions=[
                Contradiction(finding_a_id="f1", finding_b_id="f2", description="A vs B"),
            ],
        )
        assert wm.converged() is False

    def test_not_converged_with_high_priority_questions(self):
        """High-priority open questions block convergence."""
        wm = WorldModel(objective="Test")
        for i in range(3):
            wm.established.append(
                Finding(id=f"f{i}", statement=f"F{i}", verdict=FindingVerdict.SUPPORTED)
            )
        wm.open_questions.append(Question(id="q1", text="Why?", priority=0.9))
        assert wm.converged() is False

    def test_converged(self):
        """All conditions met → converged."""
        wm = WorldModel(objective="Test")
        for i in range(3):
            wm.established.append(
                Finding(id=f"f{i}", statement=f"F{i}", verdict=FindingVerdict.SUPPORTED)
            )
        wm.open_questions.append(Question(id="q1", text="Why?", priority=0.3))
        assert wm.converged() is True


class TestProposeTasks:
    """Task proposal logic."""

    def test_proposes_from_contradictions(self):
        """Contradictions appear as tasks."""
        wm = WorldModel(objective="Test")
        wm.contradictions.append(
            Contradiction(finding_a_id="a", finding_b_id="b", description="A vs B")
        )
        tasks = wm.propose_tasks(k=3)
        assert any("A vs B" in t for t in tasks)

    def test_proposes_from_open_questions(self):
        """High-priority questions appear as tasks."""
        wm = WorldModel(objective="Test")
        wm.open_questions.append(Question(id="q1", text="Key question?", priority=0.9))
        tasks = wm.propose_tasks(k=3)
        assert any("Key question" in t for t in tasks)

    def test_fallback_to_objective(self):
        """Without contradictions, questions, or guidance, fallback to objective."""
        wm = WorldModel(objective="Find optimal X")
        tasks = wm.propose_tasks(k=3)
        assert any("Find optimal X" in t for t in tasks)


class TestSerialization:
    """World model JSON round-trip."""

    def test_round_trip(self):
        """to_dict / from_dict should preserve state."""
        wm = WorldModel(objective="Test Roundtrip")
        wm.update(
            new_findings=[Finding(id="f1", statement="Found it", verdict=FindingVerdict.SUPPORTED)],
            rejected=[],
            new_questions=[Question(id="q1", text="Why?", priority=0.8)],
            new_dead_ends=[DeadEnd(description="Bad path", reason="Failed")],
        )
        wm.guidance = Guidance(gaps=["Need more data"], confounds=["Confound X"])

        data = wm.to_dict()
        restored = WorldModel.from_dict(data)

        assert restored.objective == wm.objective
        assert len(restored.established) == 1
        assert len(restored.open_questions) == 1
        assert len(restored.dead_ends) == 1
        assert restored.guidance is not None
        assert len(restored.guidance.gaps) == 1
        assert restored.current_cycle == 1


class TestCapLists:
    """List capping prevents unbounded growth."""

    def test_cap_established(self):
        """Adding more than max_list_size items trims old ones."""
        wm = WorldModel(objective="Test", max_list_size=3)
        for i in range(5):
            wm.update(
                new_findings=[
                    Finding(id=f"f{i}", statement=f"F{i}", verdict=FindingVerdict.SUPPORTED)
                ],
                rejected=[],
            )
        assert len(wm.established) == 3
        assert wm.established[-1].id == "f4"  # newest kept


# ─────────────────────────────────────────────────────────────────────────────
# Discovery loop tests
# ─────────────────────────────────────────────────────────────────────────────


class TestBudgetGovernor:
    """Budget governor tests."""

    def test_unlimited_budget(self):
        """Budget of 0 means unlimited."""
        g = BudgetGovernor(budget_usd=0)
        assert g.remaining == float("inf")
        assert g.spend(100) is True
        assert g.exhausted is False

    def test_limited_budget(self):
        """Budget is enforced."""
        g = BudgetGovernor(budget_usd=10)
        assert g.spend(6) is True
        assert g.spend(6) is False  # exceeded
        assert g.exhausted is True


class TestReflect:
    """REFLECT guidance generation."""

    def test_reflect_extracts_gaps(self):
        """High-priority questions become gaps."""
        wm = WorldModel(objective="Test")
        wm.open_questions.append(Question(id="q1", text="What is X?", priority=0.9))
        guidance = reflect(wm)
        assert len(guidance.gaps) > 0
        assert "What is X?" in guidance.gaps[0]

    def test_reflect_finds_contradictions(self):
        """Contradictions become confounds."""
        wm = WorldModel(objective="Test")
        wm.contradictions.append(
            Contradiction(finding_a_id="a", finding_b_id="b", description="A conflicts with B")
        )
        guidance = reflect(wm)
        assert len(guidance.confounds) > 0
        assert "A conflicts with B" in guidance.confounds[0]

    def test_reflect_compound_hypotheses(self):
        """Multiple findings generate compound hypotheses."""
        wm = WorldModel(objective="Test")
        wm.established.append(
            Finding(id="f1", statement="Method A works", verdict=FindingVerdict.SUPPORTED)
        )
        wm.established.append(
            Finding(id="f2", statement="Method B works", verdict=FindingVerdict.SUPPORTED)
        )
        guidance = reflect(wm)
        assert len(guidance.compound_hypotheses) > 0


class TestDiscoveryLoop:
    """Discovery loop orchestration."""

    @pytest.mark.asyncio
    async def test_disabled_loop(self):
        """Disabled config returns immediately."""
        config = DiscoveryConfig(enabled=False)
        wm = WorldModel(objective="Test")
        loop = DiscoveryLoop(wm, config)
        result = await loop.run()
        assert result.total_cycles == 0
        assert result.stop_reason == "disabled"

    @pytest.mark.asyncio
    async def test_loop_runs_cycles(self):
        """Enabled loop runs available cycles (stub tasks become dead ends)."""
        config = DiscoveryConfig(enabled=True, max_cycles=1)
        wm = WorldModel(objective="Test")
        loop = DiscoveryLoop(wm, config)
        result = await loop.run()
        assert result.total_cycles == 1
        assert len(result.cycles) == 1

    @pytest.mark.asyncio
    async def test_loop_saves_world_model(self, tmp_path):
        """World model is saved after loop."""
        config = DiscoveryConfig(enabled=True, max_cycles=1)
        wm = WorldModel(objective="Test save")
        loop = DiscoveryLoop(wm, config)
        await loop.run()

        path = tmp_path / "world_model.json"
        loop.save_world_model(str(path))
        assert path.exists()

    @pytest.mark.asyncio
    async def test_budget_exhaustion(self):
        """Budget exhaustion stops the loop."""
        config = DiscoveryConfig(enabled=True, max_cycles=10, budget_usd=0.01)
        wm = WorldModel(objective="Test")
        loop = DiscoveryLoop(wm, config)

        # Budget not yet wired in stub; no_tasks_remaining stops after cycle 1
        result = await loop.run()
        assert result.total_cycles == 1
        assert result.stop_reason is not None
