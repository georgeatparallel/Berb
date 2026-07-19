"""Cyclic discovery loop for Berb (E2).

Wraps stages 7→15 into a re-entrant discovery cycle, using the
``WorldModel`` to track epistemic state across cycles.

Designed to be the outer loop around the existing pipeline::

    loop = DiscoveryLoop(world_model, config)
    result = await loop.run()

    if result.admitted_findings:
        # Stages 16-23 run once over accumulated claim store
        ...

Architecture
------------
Each cycle:
1. WorldModel proposes tasks (contradictions, open questions, guidance gaps)
2. Stage slice 7→15 executes each task in parallel (width=cfg.width)
3. F2/F3 predicate evaluates outputs → admitted / rejected
4. WorldModel is updated
5. Every ``reflect_every`` cycles, REFLECT synthesises guidance
6. Cycle ends; repeat or converge
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from berb.research.world_model import (
    Contradiction,
    DeadEnd,
    Finding,
    FindingVerdict,
    Guidance,
    Question,
    WorldModel,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DiscoveryConfig:
    """Configuration for the discovery loop.

    Set ``enabled`` to False to restore single-pass pipeline behaviour.
    """

    enabled: bool = False
    """Master switch.  False ⇒ single-pass, byte-identical to pre-E2."""

    max_cycles: int = 3
    """Maximum number of discovery cycles."""

    width: int = 3
    """Number of parallel tasks per cycle."""

    reflect_every: int = 2
    """Run REFLECT every N cycles."""

    budget_usd: float = 0.0
    """Hard budget cap in USD.  0 = unlimited."""

    min_established_for_convergence: int = 3
    """Minimum established findings to consider converged."""


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CycleResult:
    """Result of a single discovery cycle."""

    cycle_number: int
    tasks: list[str]
    admitted: list[Finding]
    rejected: list[Finding]
    new_questions: list[Question]
    new_dead_ends: list[DeadEnd]
    new_contradictions: list[Contradiction]
    cost_usd: float = 0.0
    wall_clock_sec: float = 0.0
    reflect_output: Guidance | None = None


@dataclass
class DiscoveryResult:
    """Result of the full discovery loop."""

    cycles: list[CycleResult] = field(default_factory=list)
    world_model: WorldModel | None = None
    converged: bool = False
    total_cost_usd: float = 0.0
    total_cycles: int = 0
    admitted_findings: list[Finding] = field(default_factory=list)
    stop_reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Budget tracker
# ─────────────────────────────────────────────────────────────────────────────


class BudgetGovernor:
    """Tracks spend and enforces a hard budget cap."""

    def __init__(self, budget_usd: float):
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self.exhausted = False

    def spend(self, amount: float) -> bool:
        """Record a spend.  Returns False if budget is now exhausted."""
        self.spent_usd += amount
        if self.budget_usd > 0 and self.spent_usd >= self.budget_usd:
            self.exhausted = True
            return False
        return True

    @property
    def remaining(self) -> float:
        if self.budget_usd <= 0:
            return float("inf")
        return max(0.0, self.budget_usd - self.spent_usd)


# ─────────────────────────────────────────────────────────────────────────────
# REFLECT guidance
# ─────────────────────────────────────────────────────────────────────────────


def reflect(world: WorldModel) -> Guidance:
    """Produce strategic guidance from the current world model.

    This is a stub — in production it would call an LLM with the full
    world model state.  For now, it extracts structured signals from
    the established and refuted findings.

    Args:
        world: The current world model.

    Returns:
        Guidance with gaps, confounds, and compound hypotheses.
    """
    gaps: list[str] = []
    confounds: list[str] = []
    compound: list[str] = []

    # Gaps: open questions with high priority
    for q in sorted(world.open_questions, key=lambda x: x.priority, reverse=True)[:3]:
        gaps.append(f"High-priority question: {q.text}")

    # Confounds: contradictions that remain unresolved
    for c in world.contradictions[:3]:
        confounds.append(
            f"Unresolved contradiction: {c.description}"
        )

    # Compound hypotheses: combine two established findings
    if len(world.established) >= 2:
        for i in range(min(2, len(world.established) - 1)):
            a = world.established[i]
            b = world.established[i + 1]
            compound.append(
                f"Combine '{a.statement[:50]}...' with '{b.statement[:50]}...'"
            )

    return Guidance(gaps=gaps, confounds=confounds, compound_hypotheses=compound)


# ─────────────────────────────────────────────────────────────────────────────
# Discovery loop
# ─────────────────────────────────────────────────────────────────────────────


class DiscoveryLoop:
    """Cyclic discovery loop runner.

    Usage::

        config = DiscoveryConfig(enabled=True, max_cycles=3)
        wm = WorldModel(objective="Find optimal RL algorithm")
        loop = DiscoveryLoop(wm, config)
        result = await loop.run()
    """

    def __init__(
        self,
        world_model: WorldModel,
        config: DiscoveryConfig | None = None,
    ):
        self.wm = world_model
        self.config = config or DiscoveryConfig()
        self.budget = BudgetGovernor(self.config.budget_usd)

    async def run(self) -> DiscoveryResult:
        """Run the discovery loop.

        Returns:
            A DiscoveryResult with all cycle results and final world model.
        """
        if not self.config.enabled:
            logger.info("E2: Discovery loop disabled — single-pass mode")
            return DiscoveryResult(stop_reason="disabled")

        result = DiscoveryResult(world_model=self.wm)
        start_time = __import__("time").time()

        for cycle in range(1, self.config.max_cycles + 1):
            logger.info("E2: Starting discovery cycle %d/%d", cycle, self.config.max_cycles)

            # --- Propose tasks ---
            tasks = self.wm.propose_tasks(k=self.config.width)

            # Filter out dead ends
            tasks = [t for t in tasks if not self.wm.is_dead_end(t)]

            if not tasks:
                logger.info("E2: No tasks remaining — converged")
                result.stop_reason = "no_tasks_remaining"
                break

            # --- Execute tasks (stub — in production runs stage slice) ---
            # TODO: Wire into pipeline stage execution (stages 7→15)
            # For now, use no-op task outputs
            cycle_start = __import__("time").time()
            admitted: list[Finding] = []
            rejected: list[Finding] = []
            new_questions: list[Question] = []
            new_dead_ends: list[DeadEnd] = []
            new_contradictions: list[Contradiction] = []

            for t in tasks:
                logger.info("E2:   Task: %s", t[:100])
                # Placeholder: each task records a dead end until wired
                new_dead_ends.append(DeadEnd(
                    description=t,
                    reason="Task execution not yet wired into pipeline (E2 stub)",
                    source_cycle=cycle,
                ))

            cycle_wall = __import__("time").time() - cycle_start

            # --- REFLECT step ---
            cycle_guidance: Guidance | None = None
            if cycle % self.config.reflect_every == 0:
                cycle_guidance = reflect(self.wm)
                logger.info("E2: REFLECT produced %d gaps, %d confounds",
                            len(cycle_guidance.gaps), len(cycle_guidance.confounds))
                self.wm.guidance = cycle_guidance

            # --- Update world model ---
            self.wm.update(
                new_findings=admitted,
                rejected=rejected,
                new_questions=new_questions,
                new_dead_ends=new_dead_ends,
                new_contradictions=new_contradictions,
            )

            # --- Record cycle ---
            cycle_result = CycleResult(
                cycle_number=cycle,
                tasks=tasks,
                admitted=admitted,
                rejected=rejected,
                new_questions=new_questions,
                new_dead_ends=new_dead_ends,
                new_contradictions=new_contradictions,
                wall_clock_sec=cycle_wall,
                reflect_output=cycle_guidance,
            )
            result.cycles.append(cycle_result)

            # --- Check convergence ---
            if self.wm.converged(self.config.min_established_for_convergence):
                logger.info("E2: World model converged after %d cycles", cycle)
                result.stop_reason = "converged"
                break

            # --- Check budget ---
            if self.budget.exhausted:
                logger.warning("E2: Budget exhausted after %d cycles", cycle)
                result.stop_reason = "budget_exhausted"
                break

        # --- Finalise ---
        result.total_cycles = len(result.cycles)
        result.converged = self.wm.converged()
        result.total_cost_usd = self.budget.spent_usd
        result.admitted_findings = self.wm.established
        if not result.stop_reason:
            result.stop_reason = "max_cycles_reached"

        total_wall = __import__("time").time() - start_time
        logger.info(
            "E2: Discovery loop completed — %d cycles, %d findings, %.1fs wall",
            result.total_cycles,
            len(result.admitted_findings),
            total_wall,
        )

        return result

    def save_world_model(self, path: str | Path) -> Path:
        """Persist the world model to a JSON file.

        Follows the standard idiom from ``contracts.py`` — produces
        ``world_model.json`` that is resumable and replayable.
        """
        p = Path(path)
        p.write_text(json.dumps(self.wm.to_dict(), indent=2, default=str), encoding="utf-8")
        logger.info("E2: World model saved to %s", p)
        return p
