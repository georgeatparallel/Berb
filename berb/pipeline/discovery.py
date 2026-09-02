"""Drives the discovery loop over the pipeline's stage 7-15 slice.

:mod:`berb.research.discovery_loop` is deliberately pipeline-agnostic — it takes
a ``TaskExecutor`` coroutine and knows nothing about stages. This module is the
other half: the executor that turns one proposed research task into a real run
of stages 7 (SYNTHESIS) through 15 (RESEARCH_DECISION), and reads that slice's
artifacts back as a :class:`~berb.research.discovery_loop.TaskOutcome`.

Why this slice. Stages 1-6 establish the topic and the literature — they are
per-run, not per-direction. Stages 16-23 write the paper, and
``pipeline/iterative.py`` already loops over those. 7-15 is the part that
decides *what to investigate and whether it worked*, which is exactly what a
research-direction loop has to be able to repeat.

Off unless ``research.discovery.enabled`` is set. Every cycle re-runs nine
stages, so the cost is roughly ``max_cycles × width`` slice runs.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from berb.pipeline.stages import Stage
from berb.research.discovery_loop import (
    DiscoveryConfig,
    DiscoveryLoop,
    DiscoveryResult,
    TaskOutcome,
)
from berb.research.world_model import Finding, FindingVerdict, Question, WorldModel

if TYPE_CHECKING:
    from berb.config import RCConfig
    from berb.pipeline.contracts import AdapterBundle

logger = logging.getLogger(__name__)

__all__ = [
    "build_world_model",
    "make_stage_slice_executor",
    "promote_best_task",
    "run_discovery",
]

DISCOVERY_FIRST_STAGE = Stage.SYNTHESIS
DISCOVERY_LAST_STAGE = Stage.RESEARCH_DECISION


def build_world_model(config: RCConfig, run_dir: Path) -> WorldModel:
    """Build the loop's starting state, resuming a saved model when present.

    Args:
        config: Run config; ``research.topic`` becomes the objective.
        run_dir: Run directory. ``world_model.json`` there is restored if it
            parses, so an interrupted run resumes its epistemic state instead
            of re-deriving it.

    Returns:
        A :class:`WorldModel`.
    """
    saved = run_dir / "world_model.json"
    if saved.exists():
        try:
            return WorldModel.from_dict(json.loads(saved.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Could not restore %s (%s) — starting fresh", saved, exc)
    return WorldModel(objective=config.research.topic)


def make_stage_slice_executor(
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    auto_approve_gates: bool = False,
    kb_root: Path | None = None,
) -> Any:
    """Build the executor that runs one research task through stages 7-15.

    Each task gets its own run directory beneath ``run_dir/discovery/`` so
    concurrent tasks in a cycle cannot overwrite each other's stage artifacts —
    they all write ``stage-12/``, ``stage-15/`` and so on.

    Args:
        run_dir: The parent run directory.
        run_id: The parent run id; each task's id is derived from it.
        config: Run config, passed through to the stages unchanged.
        adapters: The adapter bundle the stages need.
        auto_approve_gates: Passed through to ``execute_pipeline``.
        kb_root: Passed through to ``execute_pipeline``.

    Returns:
        A coroutine matching
        :data:`~berb.research.discovery_loop.TaskExecutor`.
    """
    from berb.pipeline.runner import execute_pipeline

    async def _execute(task: str, cycle: int) -> TaskOutcome:
        task_dir = run_dir / "discovery" / f"cycle-{cycle}" / uuid.uuid4().hex[:8]
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.txt").write_text(task, encoding="utf-8")

        # Stages 7-15 read stages 1-6 artifacts from the parent run. Point them
        # at it rather than copying: the literature and topic are per-run, and
        # this slice does not write there.
        _seed_prior_artifacts(run_dir, task_dir)

        results = await execute_pipeline(
            run_dir=task_dir,
            run_id=f"{run_id}-c{cycle}-{task_dir.name}",
            config=config,
            adapters=adapters,
            from_stage=DISCOVERY_FIRST_STAGE,
            to_stage=DISCOVERY_LAST_STAGE,
            auto_approve_gates=auto_approve_gates,
            kb_root=kb_root,
        )
        outcome = _outcome_from_slice(task, cycle, task_dir, results)
        _record_task(run_dir, task, cycle, task_dir, outcome)
        return outcome

    return _execute


def _record_task(
    run_dir: Path,
    task: str,
    cycle: int,
    task_dir: Path,
    outcome: TaskOutcome,
) -> None:
    """Append one line to ``discovery/index.jsonl``.

    The index is what makes a completed loop auditable and lets
    :func:`promote_best_task` find the winning slice on disk — a Finding
    carries a statement and an effect size, not the directory that produced it.
    """
    index = run_dir / "discovery" / "index.jsonl"
    index.parent.mkdir(parents=True, exist_ok=True)
    finding = outcome.findings[0] if outcome.findings else None
    entry = {
        "cycle": cycle,
        "task": task,
        "task_dir": str(task_dir.relative_to(run_dir)),
        "admitted": bool(outcome.findings),
        "metric_key": finding.metric_key if finding else "",
        "effect_size": finding.effect_size if finding else 0.0,
        "cost_usd": outcome.cost_usd,
    }
    with index.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def promote_best_task(run_dir: Path, *, maximize: bool = True) -> str:
    """Copy the winning task's stage 7-15 artifacts into the parent run.

    Stages 16-23 read stage 14/15 output from the run directory, so the loop's
    chosen direction has to be materialised there before writing can start.

    Args:
        run_dir: The parent run directory.
        maximize: Whether a larger effect size is better.

    Returns:
        The promoted task's directory name, or ``""`` when no task was
        admitted — in which case the caller must fall back to a normal
        single-pass run rather than write a paper about nothing.
    """
    import shutil

    index = run_dir / "discovery" / "index.jsonl"
    if not index.exists():
        return ""

    admitted: list[dict[str, Any]] = []
    for line in index.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("admitted"):
            admitted.append(entry)

    if not admitted:
        logger.warning("Discovery loop admitted no findings — nothing to promote")
        return ""

    best = max(
        admitted,
        key=lambda e: float(e.get("effect_size", 0.0)) * (1 if maximize else -1),
    )
    src = run_dir / str(best["task_dir"])
    for stage in range(int(DISCOVERY_FIRST_STAGE), int(DISCOVERY_LAST_STAGE) + 1):
        stage_src = src / f"stage-{stage:02d}"
        if stage_src.is_dir():
            shutil.copytree(stage_src, run_dir / stage_src.name, dirs_exist_ok=True)

    logger.info("Promoted discovery task %s (effect=%s)", src.name, best.get("effect_size"))
    return str(src.name)


def _seed_prior_artifacts(run_dir: Path, task_dir: Path) -> None:
    """Symlink the parent run's stage 1-6 output into a task's run directory.

    Symlinks, not copies: these artifacts can be large (full-text PDFs, parsed
    bibliographies) and every task in every cycle would otherwise duplicate
    them. Falls back to a copy where symlinks are unavailable.
    """
    import shutil

    for stage in range(1, int(DISCOVERY_FIRST_STAGE)):
        src = run_dir / f"stage-{stage:02d}"
        if not src.is_dir():
            continue
        dst = task_dir / src.name
        if dst.exists():
            continue
        try:
            dst.symlink_to(src, target_is_directory=True)
        except (OSError, NotImplementedError):
            shutil.copytree(src, dst, dirs_exist_ok=True)


def _outcome_from_slice(
    task: str,
    cycle: int,
    task_dir: Path,
    results: list[Any],
) -> TaskOutcome:
    """Read a completed slice's artifacts into a TaskOutcome.

    The slice's verdict comes from stage 15's ``decision_structured.json``:
    PROCEED means the direction held up and becomes an established finding;
    anything else (PIVOT, REFINE) means it did not, and becomes a refuted one
    plus an open question for the next cycle to pick up.
    """
    finding_id = f"c{cycle}-{task_dir.name}"
    decision = _read_decision(task_dir)
    metric_key, effect = _read_metric(task_dir)

    if decision == "PROCEED":
        return TaskOutcome(
            findings=(
                Finding(
                    id=finding_id,
                    statement=task,
                    verdict=FindingVerdict.SUPPORTED,
                    metric_key=metric_key,
                    effect_size=effect,
                    source_cycle=cycle,
                ),
            ),
            cost_usd=_slice_cost(results),
        )

    if not decision:
        # The slice did not reach a decision — a failed or halted run. Report
        # nothing: the loop records an empty outcome as a dead end, which is
        # the honest reading of "we tried and learned nothing".
        logger.info("Discovery task reached no decision: %s", task[:80])
        return TaskOutcome(cost_usd=_slice_cost(results))

    return TaskOutcome(
        rejected=(
            Finding(
                id=finding_id,
                statement=task,
                verdict=FindingVerdict.REFUTED,
                metric_key=metric_key,
                effect_size=effect,
                source_cycle=cycle,
            ),
        ),
        questions=(
            Question(
                id=f"{finding_id}-q",
                text=f"Why did '{task[:120]}' yield {decision} rather than PROCEED?",
                priority=0.6,
                source_cycle=cycle,
            ),
        ),
        cost_usd=_slice_cost(results),
    )


def _read_decision(task_dir: Path) -> str:
    """Return stage 15's decision, or "" when the slice produced none."""
    path = task_dir / f"stage-{int(DISCOVERY_LAST_STAGE):02d}" / "decision_structured.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("decision", "")).upper() if isinstance(data, dict) else ""


def _read_metric(task_dir: Path) -> tuple[str, float]:
    """Return stage 14's headline metric as ``(key, value)``, or ``("", 0.0)``."""
    path = task_dir / f"stage-{int(Stage.RESULT_ANALYSIS):02d}" / "metrics.json"
    if not path.exists():
        return "", 0.0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", 0.0
    if not isinstance(data, dict):
        return "", 0.0
    for key, value in data.items():
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(key), float(value)
    return "", 0.0


def _slice_cost(results: list[Any]) -> float:
    """Sum whatever cost the slice's stage results reported."""
    return sum(float(getattr(r, "cost_usd", 0.0) or 0.0) for r in results)


async def run_discovery(
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    auto_approve_gates: bool = False,
    kb_root: Path | None = None,
) -> DiscoveryResult:
    """Run the discovery loop for this run, if it is enabled.

    Returns a result with ``stop_reason="disabled"`` when
    ``research.discovery.enabled`` is False, so callers can invoke this
    unconditionally.
    """
    discovery_cfg = getattr(config.research, "discovery", None)
    if discovery_cfg is None or not discovery_cfg.enabled:
        return DiscoveryResult(stop_reason="disabled")

    world = build_world_model(config, run_dir)
    loop = DiscoveryLoop(
        world,
        DiscoveryConfig(
            enabled=True,
            max_cycles=discovery_cfg.max_cycles,
            width=discovery_cfg.width,
            reflect_every=discovery_cfg.reflect_every,
            budget_usd=discovery_cfg.budget_usd,
            min_established_for_convergence=discovery_cfg.min_established_for_convergence,
        ),
        executor=make_stage_slice_executor(
            run_dir=run_dir,
            run_id=run_id,
            config=config,
            adapters=adapters,
            auto_approve_gates=auto_approve_gates,
            kb_root=kb_root,
        ),
    )
    result = await loop.run()
    loop.save_world_model(run_dir / "world_model.json")
    return result
