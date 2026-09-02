"""Cyclic discovery loop — iterating on *which* result to pursue.

``berb/pipeline/iterative.py`` re-runs stages 16-22 until the write-up clears a
quality bar: it iterates on how a result is presented. Nothing iterated on the
research direction itself. This loop does, over the epistemic state in
:mod:`berb.research.world_model`.

Each cycle:

1. the world model proposes tasks from its contradictions, open questions and
   REFLECT guidance, skipping anything already ruled a dead end;
2. up to ``width`` tasks run concurrently through an injected executor;
3. each outcome updates the world model — findings admitted or refuted,
   new questions, new dead ends, new contradictions;
4. every ``reflect_every`` cycles, REFLECT synthesises fresh guidance;
5. the loop stops on convergence, budget exhaustion, or ``max_cycles``.

Restored 2026-09-02 from commit ``24eefec``. The original's step 2 was a stub:
it recorded a dead end per task with the reason "Task execution not yet wired
into pipeline (E2 stub)", so ``admitted`` was always empty and the loop could
never converge on anything. That stub is replaced by :data:`TaskExecutor`, an
injected coroutine. This module stays pipeline-agnostic — it never imports
``berb.pipeline``; the executor that re-runs the stage 7-15 slice lives in
``berb/pipeline/discovery.py``.

Usage::

    wm = WorldModel(objective="Find the optimal RL algorithm for X")
    loop = DiscoveryLoop(wm, DiscoveryConfig(enabled=True), executor=run_task)
    result = await loop.run()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from berb.research.world_model import (
    Contradiction,
    DeadEnd,
    Finding,
    Guidance,
    Question,
    WorldModel,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BudgetGovernor",
    "CycleResult",
    "DiscoveryConfig",
    "DiscoveryLoop",
    "DiscoveryResult",
    "TaskExecutor",
    "TaskOutcome",
    "reflect",
]


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiscoveryConfig:
    """Configuration for the discovery loop.

    ``enabled=False`` restores single-pass pipeline behaviour exactly.
    """

    enabled: bool = False
    """Master switch. False ⇒ single-pass, byte-identical to no loop at all."""

    max_cycles: int = 3
    """Maximum number of discovery cycles."""

    width: int = 3
    """Number of tasks to run concurrently per cycle."""

    reflect_every: int = 2
    """Run REFLECT every N cycles."""

    budget_usd: float = 0.0
    """Hard budget cap in USD. 0 = unlimited."""

    min_established_for_convergence: int = 3
    """Minimum established findings before convergence is even considered."""


# ─────────────────────────────────────────────────────────────────────────────
# Executor contract
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TaskOutcome:
    """What running one research task produced.

    Every field defaults to empty, so an executor reports only what it
    actually learned. An outcome with nothing in it is not an error — it means
    the task ran and settled nothing, which the loop records as a dead end so
    the next cycle does not propose it again.
    """

    findings: tuple[Finding, ...] = ()
    """Findings that passed the admissibility predicate."""

    rejected: tuple[Finding, ...] = ()
    """Findings that were produced but did not pass."""

    questions: tuple[Question, ...] = ()
    dead_ends: tuple[DeadEnd, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()

    cost_usd: float = 0.0
    """Spend attributable to this task, charged against the loop's budget."""

    def is_empty(self) -> bool:
        """True when the task settled nothing at all."""
        return not (
            self.findings
            or self.rejected
            or self.questions
            or self.dead_ends
            or self.contradictions
        )


TaskExecutor = Callable[[str, int], Awaitable[TaskOutcome]]
"""``(task_description, cycle_number) -> TaskOutcome``.

Implementations run the actual research work — in the pipeline's case, the
stage 7-15 slice. Raising is allowed: the loop records the failure as a dead
end and carries on with the remaining tasks.
"""


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
# Budget
# ─────────────────────────────────────────────────────────────────────────────


class BudgetGovernor:
    """Tracks spend and reports when a hard cap is reached."""

    def __init__(self, budget_usd: float) -> None:
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self.exhausted = False

    def spend(self, amount: float) -> bool:
        """Record a spend. Returns False once the budget is exhausted."""
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
# REFLECT
# ─────────────────────────────────────────────────────────────────────────────


def reflect(world: WorldModel) -> Guidance:
    """Derive strategic guidance from the world model's current state.

    Structural, not generative: it surfaces the highest-priority open
    questions as gaps, the unresolved contradictions as confounds, and pairs
    of established findings as compound hypotheses. No LLM call — which makes
    it deterministic, free, and testable. A model-backed REFLECT would be a
    drop-in replacement with the same signature.

    Args:
        world: The current world model.

    Returns:
        Guidance with gaps, confounds and compound hypotheses.
    """
    gaps = [
        f"High-priority question: {q.text}"
        for q in sorted(world.open_questions, key=lambda x: x.priority, reverse=True)[:3]
    ]
    confounds = [f"Unresolved contradiction: {c.description}" for c in world.contradictions[:3]]

    compound: list[str] = []
    for i in range(min(2, max(0, len(world.established) - 1))):
        a, b = world.established[i], world.established[i + 1]
        compound.append(f"Combine '{a.statement[:50]}...' with '{b.statement[:50]}...'")

    return Guidance(gaps=gaps, confounds=confounds, compound_hypotheses=compound)


# ─────────────────────────────────────────────────────────────────────────────
# The loop
# ─────────────────────────────────────────────────────────────────────────────


class DiscoveryLoop:
    """Runs discovery cycles until convergence, budget exhaustion, or max_cycles."""

    def __init__(
        self,
        world_model: WorldModel,
        config: DiscoveryConfig | None = None,
        executor: TaskExecutor | None = None,
    ) -> None:
        """Build a discovery loop.

        Args:
            world_model: Epistemic state, carried and mutated across cycles.
            config: Loop configuration; defaults leave the loop disabled.
            executor: Coroutine that runs one task. Without it the loop does
                nothing and says so — the deleted version spun for max_cycles
                producing only stub dead ends, which looked like work.
        """
        self.wm = world_model
        self.config = config or DiscoveryConfig()
        self.executor = executor
        self.budget = BudgetGovernor(self.config.budget_usd)

    async def run(self) -> DiscoveryResult:
        """Run the discovery loop to completion.

        Returns:
            A :class:`DiscoveryResult` whose ``stop_reason`` names why the loop
            ended: ``disabled``, ``no_executor``, ``no_tasks_remaining``,
            ``converged``, ``budget_exhausted`` or ``max_cycles_reached``.
        """
        if not self.config.enabled:
            logger.info("Discovery loop disabled — single-pass mode")
            return DiscoveryResult(world_model=self.wm, stop_reason="disabled")

        if self.executor is None:
            logger.warning("Discovery loop enabled but no executor supplied — nothing to run")
            return DiscoveryResult(world_model=self.wm, stop_reason="no_executor")

        result = DiscoveryResult(world_model=self.wm)
        start_time = time.monotonic()

        for cycle in range(1, self.config.max_cycles + 1):
            logger.info("Discovery cycle %d/%d", cycle, self.config.max_cycles)
            self.wm.current_cycle = cycle

            tasks = [
                t for t in self.wm.propose_tasks(k=self.config.width) if not self.wm.is_dead_end(t)
            ]
            if not tasks:
                logger.info("No tasks left to propose — stopping")
                result.stop_reason = "no_tasks_remaining"
                break

            cycle_result = await self._run_cycle(cycle, tasks)
            result.cycles.append(cycle_result)
            self.budget.spend(cycle_result.cost_usd)

            if self.wm.converged(self.config.min_established_for_convergence):
                logger.info("World model converged after %d cycle(s)", cycle)
                result.stop_reason = "converged"
                break

            if self.budget.exhausted:
                logger.warning("Budget exhausted after %d cycle(s)", cycle)
                result.stop_reason = "budget_exhausted"
                break

        result.total_cycles = len(result.cycles)
        result.converged = self.wm.converged(self.config.min_established_for_convergence)
        result.total_cost_usd = self.budget.spent_usd
        result.admitted_findings = list(self.wm.established)
        if not result.stop_reason:
            result.stop_reason = "max_cycles_reached"

        logger.info(
            "Discovery loop finished — %d cycle(s), %d finding(s), %.1fs, stop=%s",
            result.total_cycles,
            len(result.admitted_findings),
            time.monotonic() - start_time,
            result.stop_reason,
        )
        return result

    async def _run_cycle(self, cycle: int, tasks: list[str]) -> CycleResult:
        """Execute one cycle's tasks concurrently and fold the outcomes in."""
        assert self.executor is not None  # guarded in run()
        cycle_start = time.monotonic()

        outcomes = await asyncio.gather(
            *(self.executor(task, cycle) for task in tasks),
            return_exceptions=True,
        )

        admitted: list[Finding] = []
        rejected: list[Finding] = []
        new_questions: list[Question] = []
        new_dead_ends: list[DeadEnd] = []
        new_contradictions: list[Contradiction] = []
        cost = 0.0

        for task, outcome in zip(tasks, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, Exception):
                    raise outcome  # never swallow CancelledError
                logger.warning("Discovery task failed: %s — %s", task[:80], outcome)
                new_dead_ends.append(
                    DeadEnd(
                        description=task,
                        reason=f"Task execution failed: {outcome}",
                        source_cycle=cycle,
                    )
                )
                continue

            if outcome.is_empty():
                # Ran and settled nothing: record it so cycle N+1 does not
                # propose the same direction again.
                new_dead_ends.append(
                    DeadEnd(
                        description=task,
                        reason="Task produced no findings, questions or contradictions",
                        source_cycle=cycle,
                    )
                )

            admitted.extend(outcome.findings)
            rejected.extend(outcome.rejected)
            new_questions.extend(outcome.questions)
            new_dead_ends.extend(outcome.dead_ends)
            new_contradictions.extend(outcome.contradictions)
            cost += outcome.cost_usd

        guidance: Guidance | None = None
        if self.config.reflect_every > 0 and cycle % self.config.reflect_every == 0:
            guidance = reflect(self.wm)
            self.wm.guidance = guidance
            logger.info(
                "REFLECT: %d gap(s), %d confound(s)",
                len(guidance.gaps),
                len(guidance.confounds),
            )

        self.wm.update(
            new_findings=admitted,
            rejected=rejected,
            new_questions=new_questions,
            new_dead_ends=new_dead_ends,
            new_contradictions=new_contradictions,
        )

        return CycleResult(
            cycle_number=cycle,
            tasks=tasks,
            admitted=admitted,
            rejected=rejected,
            new_questions=new_questions,
            new_dead_ends=new_dead_ends,
            new_contradictions=new_contradictions,
            cost_usd=cost,
            wall_clock_sec=time.monotonic() - cycle_start,
            reflect_output=guidance,
        )

    def save_world_model(self, path: str | Path) -> Path:
        """Persist the world model as JSON, so a run is resumable and replayable."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.wm.to_dict(), indent=2, default=str), encoding="utf-8")
        logger.info("World model saved to %s", p)
        return p
