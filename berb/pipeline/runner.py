"""Pipeline orchestrator — async DAG-based stage execution with event sourcing.

Thin orchestrator that delegates to domain-specific sub-modules for
checkpointing, summary generation, packaging, experiment diagnosis/repair,
and the iterative improvement loop. Converted to async in Phase 3 Step 7
to enable concurrent stage execution via ``asyncio.gather()``.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.evolution import EvolutionStore, extract_lessons
from berb.knowledge.base import write_stage_to_kb
from berb.pipeline.checkpoint import CheckpointManager, write_heartbeat
from berb.pipeline.executor import StageResult, execute_stage
from berb.pipeline.iterative import (
    _check_experiment_quality,
    _consecutive_empty_metrics,
    _promote_best_stage14,
    _version_rollback_stages,
    read_pivot_count,
    record_decision_history,
)
from berb.pipeline.metaclaw_post import metaclaw_post_pipeline
from berb.pipeline.packaging import package_deliverables
from berb.pipeline.resolution import resolve_stage_order
from berb.pipeline.stages import (
    DECISION_ROLLBACK,
    MAX_DECISION_PIVOTS,
    NONCRITICAL_STAGES,
    EventStore,
    Stage,
    StageStatus,
    StageTransitionEvent,
    TransitionEvent,
)
from berb.pipeline.summary import build_pipeline_summary, write_pipeline_summary

logger = logging.getLogger(__name__)


# ============================================================================
# Pure helper functions (synchronous, shared by sync and async paths)
# ============================================================================


def _should_pivot(result: StageResult, pivot_depth: int) -> bool:
    return result.decision in DECISION_ROLLBACK and pivot_depth < MAX_DECISION_PIVOTS


def _get_rollback_target(stage: Stage, decision: str) -> Stage:
    return DECISION_ROLLBACK.get(decision, stage)


def _should_force_proceed(pivot_count: int, run_dir: Path) -> bool:
    return pivot_count > 0 and _consecutive_empty_metrics(run_dir, pivot_count)


def _create_pivot_event(
    run_id: str,
    stage: Stage,
    rollback_target: Stage,
    pivot_count: int,
) -> StageTransitionEvent:
    return StageTransitionEvent(
        run_id=run_id,
        from_stage=stage,
        to_stage=rollback_target,
        from_status=StageStatus.DONE,
        to_status=StageStatus.RUNNING,
        event=TransitionEvent.SUCCEED,
        metadata={
            "decision": "pivot",
            "rollback_target": rollback_target.name,
            "pivot_count": pivot_count,
        },
    )


def _should_start(stage: Stage, from_stage: Stage, started: bool) -> bool:
    if started:
        return True
    return stage == from_stage


# ============================================================================
# DAG level builder — groups stages by dependency depth
# ============================================================================


def _build_dag_levels(order: tuple[Stage, ...]) -> list[set[Stage]]:
    """Group stages into levels where all deps of a level are in prior levels.

    Each level is a set of stages that can run concurrently (all dependencies
    from earlier levels are satisfied). Levels are returned in topological order.
    """

    from berb.pipeline.contracts import CONTRACTS

    # Track in-degree (remaining unmet dependencies) for each stage
    in_degree: dict[Stage, int] = {}
    for stage in order:
        contract = CONTRACTS[stage]
        # Count deps that are within the start_from window
        deps_in_order = [d for d in contract.depends_on if d in order]
        in_degree[stage] = len(deps_in_order)

    levels: list[set[Stage]] = []
    remaining = set(order)

    while remaining:
        # Find stages with zero in-degree (all deps met)
        ready = {s for s in remaining if in_degree.get(s, 0) == 0}
        if not ready:
            # Shouldn't happen in a valid DAG — break to avoid infinite loop
            logger.warning("DAG level builder stalled with %d remaining stages", len(remaining))
            break

        levels.append(ready)
        remaining -= ready

        # Update in-degree for remaining stages
        for stage in ready:
            for candidate in remaining:
                contract = CONTRACTS[candidate]
                if stage in contract.depends_on:
                    in_degree[candidate] = max(0, in_degree.get(candidate, 1) - 1)

    return levels


# ============================================================================
# Single stage execution helper (async)
# ============================================================================


async def _execute_single_stage(
    stage: Stage,
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    checkpoint_mgr: CheckpointManager,
    event_store: EventStore,
    previous_status: StageStatus,
    total_stages: int,
    kb_root: Path | None = None,
    auto_approve_gates: bool = False,
) -> StageResult:
    """Run one stage: print status, record events, write checkpoint."""
    import time as _time

    stage_num = int(stage)
    prefix = f"[{run_id}] Stage {stage_num:02d}/{total_stages}"
    model_info = (
        config.llm.primary_model.split("/")[-1] if config.llm.primary_model else "unknown"
    )
    print(f"{prefix} {stage.name} — running... [model: {model_info}]")

    start_event = StageTransitionEvent(
        run_id=run_id,
        from_stage=stage,
        to_stage=stage,
        from_status=previous_status,
        to_status=StageStatus.RUNNING,
        event=TransitionEvent.START,
        metadata={"model": model_info},
    )
    event_store.append(start_event)

    if stage == Stage.PAPER_OUTLINE:
        _promote_best_stage14(run_dir, config)

    t0 = _time.monotonic()
    result = await _run_sync_stage_internal(
        stage,
        run_dir=run_dir,
        run_id=run_id,
        config=config,
        adapters=adapters,
        checkpoint_mgr=checkpoint_mgr,
        auto_approve_gates=auto_approve_gates,
    )
    elapsed = _time.monotonic() - t0

    if result.status == StageStatus.DONE:
        arts = ", ".join(result.artifacts) if result.artifacts else "none"
        if result.decision == "degraded":
            print(f"{prefix} {stage.name} — DEGRADED ({elapsed:.1f}s) — continuing with sanitization -> {arts}")
        else:
            print(f"{prefix} {stage.name} — done ({elapsed:.1f}s) -> {arts}")
    elif result.status == StageStatus.FAILED:
        err = result.error or "unknown error"
        print(f"{prefix} {stage.name} — FAILED ({elapsed:.1f}s) — {err}")
    elif result.status == StageStatus.BLOCKED_APPROVAL:
        print(f"{prefix} {stage.name} — blocked (awaiting approval)")

    completion_event = StageTransitionEvent(
        run_id=run_id,
        from_stage=stage,
        to_stage=stage,
        from_status=StageStatus.RUNNING,
        to_status=result.status,
        event=TransitionEvent.SUCCEED
        if result.status == StageStatus.DONE
        else TransitionEvent.FAIL,
        metadata={
            "elapsed_sec": elapsed,
            "decision": result.decision,
            "artifacts": list(result.artifacts) if result.artifacts else [],
            "error": result.error,
        },
    )
    event_store.append(completion_event)

    if kb_root is not None and result.status == StageStatus.DONE:
        try:
            stage_dir = run_dir / f"stage-{int(stage):02d}"
            # NOTE: intentionally NOT re-importing write_stage_to_kb here —
            # it's already imported at module scope so that callers/tests can
            # monkeypatch `berb.pipeline.runner.write_stage_to_kb`. A local
            # re-import previously shadowed that binding, silently defeating
            # any monkeypatch of the module-level name.
            write_stage_to_kb(
                kb_root,
                stage_id=int(stage),
                stage_name=stage.name.lower(),
                run_id=run_id,
                artifacts=list(result.artifacts),
                stage_dir=stage_dir,
                backend=config.knowledge_base.backend,
                topic=config.research.topic,
            )
        except Exception:
            logger.debug("Knowledge base store failed", exc_info=True)

    return result


# ============================================================================
# Async pipeline orchestrator
# ============================================================================


async def execute_pipeline(
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    from_stage: Stage = Stage.TOPIC_INIT,
    auto_approve_gates: bool = False,
    stop_on_gate: bool = False,
    skip_noncritical: bool = False,
    kb_root: Path | None = None,
    _pivot_depth: int = 0,
) -> list[StageResult]:
    """Execute pipeline stages using DAG-based scheduling.

    Stages whose dependencies are satisfied run concurrently via
    ``asyncio.gather()`` when multiple are eligible in the same DAG level.
    """
    event_store_path = run_dir / "event_log.json" if run_dir else None
    event_store = EventStore(run_id=run_id, storage_path=str(event_store_path))
    checkpoint_mgr = CheckpointManager()

    if _pivot_depth > MAX_DECISION_PIVOTS:
        logger.error(
            "execute_pipeline recursion depth %d exceeds MAX_DECISION_PIVOTS (%d); aborting.",
            _pivot_depth,
            MAX_DECISION_PIVOTS,
        )
        return []

    results: list[StageResult] = []
    total_stages = len(Stage)
    previous_status = StageStatus.PENDING

    # Build DAG levels for concurrent execution
    # Each level is a set of stages whose dependencies are met
    # Levels are processed sequentially; stages within a level run concurrently
    levels = _build_dag_levels(resolve_stage_order(from_stage))

    for level_stages in levels:
        # Run all stages in this level — they're eligible by construction
        if len(level_stages) == 1:
            stage = next(iter(level_stages))
            stage_results = [await _execute_single_stage(
                stage,
                run_dir=run_dir,
                run_id=run_id,
                config=config,
                adapters=adapters,
                checkpoint_mgr=checkpoint_mgr,
                event_store=event_store,
                previous_status=previous_status,
                total_stages=total_stages,
                kb_root=kb_root,
                auto_approve_gates=auto_approve_gates,
            )]
        else:
            names = ", ".join(s.name for s in level_stages)
            logger.info("CONCURRENT: running %d stages: %s", len(level_stages), names)
            stage_results = await asyncio.gather(*[
                _execute_single_stage(
                    s,
                    run_dir=run_dir,
                    run_id=run_id,
                    config=config,
                    adapters=adapters,
                    checkpoint_mgr=checkpoint_mgr,
                    event_store=event_store,
                    previous_status=previous_status,
                    total_stages=total_stages,
                    kb_root=kb_root,
                    auto_approve_gates=auto_approve_gates,
                ) for s in level_stages
            ])

        for result in stage_results:
            results.append(result)
            previous_status = result.status

            stage = result.stage

            # Experiment diagnosis + repair after Stage 14
            if (
                stage == Stage.RESULT_ANALYSIS
                and result.status == StageStatus.DONE
                and config.experiment.repair.enabled
            ):
                await _run_diagnosis_and_repair(run_dir, config, run_id)

            # PIVOT/REFINE decision handling
            if (
                stage == Stage.RESEARCH_DECISION
                and result.status == StageStatus.DONE
                and _should_pivot(result, _pivot_depth)
            ):
                pivot_results = await _handle_pivot(
                    run_dir=run_dir,
                    run_id=run_id,
                    config=config,
                    adapters=adapters,
                    stage=stage,
                    result=result,
                    pivot_depth=_pivot_depth,
                    auto_approve_gates=auto_approve_gates,
                    stop_on_gate=stop_on_gate,
                    skip_noncritical=skip_noncritical,
                    kb_root=kb_root,
                    event_store=event_store,
                )
                results.extend(pivot_results)
                break

            if result.status == StageStatus.FAILED:
                if skip_noncritical and stage in NONCRITICAL_STAGES:
                    logger.warning("Noncritical stage %s failed — skipping", stage.name)
                else:
                    break
            if result.status == StageStatus.BLOCKED_APPROVAL and stop_on_gate:
                break
        else:
            continue
        break

    summary = build_pipeline_summary(
        run_id=run_id,
        results=results,
        from_stage=from_stage,
        run_dir=run_dir,
    )
    write_pipeline_summary(run_dir, summary)

    lessons: list[object] = []
    try:
        lessons = extract_lessons(results, run_id=run_id, run_dir=run_dir)
        if lessons:
            store = EvolutionStore(run_dir / "evolution")
            store.append_many(lessons)
            logger.info("Extracted %d lessons from pipeline run", len(lessons))
    except Exception:
        logger.warning("Evolution lesson extraction failed", exc_info=True)

    try:
        metaclaw_post_pipeline(config, results, lessons, run_id, run_dir)
    except Exception:
        logger.warning("MetaClaw post-pipeline hook failed", exc_info=True)

    try:
        deliverables_dir = package_deliverables(run_dir, run_id, config)
        if deliverables_dir is not None:
            print(f"[{run_id}] Deliverables packaged -> {deliverables_dir}")
    except Exception:
        logger.warning("Deliverables packaging failed", exc_info=True)

    return results


# ============================================================================
# Internal helpers (async)
# ============================================================================


def _time_module() -> float:
    """Return monotonic time (imported here to avoid clobbering the `time` module)."""
    import time as _t

    return _t.monotonic()


async def _run_sync_stage_internal(
    stage: Stage,
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    checkpoint_mgr: CheckpointManager,
    auto_approve_gates: bool = False,
) -> StageResult:
    """Run a stage via asyncio.to_thread, write checkpoint and heartbeat on success."""
    import asyncio as _asyncio

    result = await _asyncio.to_thread(
        execute_stage,
        stage,
        run_dir=run_dir,
        run_id=run_id,
        config=config,
        adapters=adapters,
        auto_approve_gates=auto_approve_gates,
    )
    if result.status == StageStatus.DONE:
        checkpoint_mgr.write(run_dir, stage, run_id)
    write_heartbeat(run_dir, stage, run_id)
    return result


async def _handle_pivot(
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    stage: Stage,
    result: StageResult,
    pivot_depth: int,
    auto_approve_gates: bool,
    stop_on_gate: bool,
    skip_noncritical: bool,
    kb_root: Path | None,
    event_store: EventStore,
) -> list[StageResult]:
    """Handle a PIVOT/REFINE decision from the orchestrator."""
    pivot_count = read_pivot_count(run_dir)
    if _should_force_proceed(pivot_count, run_dir):
        logger.warning("Consecutive REFINE cycles produced empty metrics — forcing PROCEED")
        print(f"[{run_id}] Consecutive empty metrics across REFINE cycles — forcing PROCEED")
        _promote_best_stage14(run_dir, config)
        return []
    elif pivot_count < MAX_DECISION_PIVOTS:
        rollback_target = _get_rollback_target(stage, result.decision)
        record_decision_history(run_dir, result.decision, rollback_target, pivot_count + 1)
        logger.info(
            "Decision %s: rolling back to %s (attempt %d/%d)",
            result.decision.upper(),
            rollback_target.name,
            pivot_count + 1,
            MAX_DECISION_PIVOTS,
        )
        print(
            f"[{run_id}] Decision: {result.decision.upper()} -> "
            f"rollback to {rollback_target.name} "
            f"(attempt {pivot_count + 1}/{MAX_DECISION_PIVOTS})"
        )
        _version_rollback_stages(run_dir, rollback_target, pivot_count + 1)
        pivot_event = _create_pivot_event(run_id, stage, rollback_target, pivot_count + 1)
        event_store.append(pivot_event)

        pivot_results = await execute_pipeline(
            run_dir=run_dir,
            run_id=run_id,
            config=config,
            adapters=adapters,
            from_stage=rollback_target,
            auto_approve_gates=auto_approve_gates,
            stop_on_gate=stop_on_gate,
            skip_noncritical=skip_noncritical,
            kb_root=kb_root,
            _pivot_depth=pivot_depth + 1,
        )
        _promote_best_stage14(run_dir, config)
        return pivot_results
    else:
        _quality_ok, _quality_msg = _check_experiment_quality(run_dir, pivot_count)
        if not _quality_ok:
            logger.warning(
                "Max pivot attempts (%d) reached — forcing PROCEED "
                "with quality warning: %s",
                MAX_DECISION_PIVOTS,
                _quality_msg,
            )
            print(f"[{run_id}] QUALITY WARNING: {_quality_msg}")
            _qw_path = run_dir / "quality_warning.txt"
            _qw_path.write_text(
                f"Max pivots ({MAX_DECISION_PIVOTS}) reached.\n"
                f"Quality gate failed: {_quality_msg}\n"
                f"Paper will be written but may have significant issues.\n",
                encoding="utf-8",
            )
        else:
            logger.warning(
                "Max pivot attempts (%d) reached — forcing PROCEED",
                MAX_DECISION_PIVOTS,
            )
        print(f"[{run_id}] Max pivot attempts reached — forcing PROCEED")
        _promote_best_stage14(run_dir, config)
        return []


async def _run_diagnosis_and_repair(
    run_dir: Path,
    config: RCConfig,
    run_id: str,
) -> None:
    """Run experiment diagnosis after Stage 14 and optionally repair."""
    from berb.pipeline.experiment_diagnosis import run_experiment_diagnosis

    await asyncio.to_thread(run_experiment_diagnosis, run_dir, config, run_id)

    _diag_path = run_dir / "experiment_diagnosis.json"
    if _diag_path.exists():
        try:
            _diag_data = json.loads(_diag_path.read_text(encoding="utf-8"))
            if _diag_data.get("repair_needed"):
                from berb.pipeline.experiment_repair import _summary_quality_score, run_repair_loop

                repair_result = await asyncio.to_thread(run_repair_loop, run_dir, config, run_id)
                (run_dir / "experiment_repair_result.json").write_text(
                    json.dumps(repair_result.to_dict(), indent=2), encoding="utf-8"
                )
                if repair_result.best_experiment_summary:
                    best_path = run_dir / "stage-14" / "experiment_summary.json"
                    existing_score = 0.0
                    if best_path.exists():
                        try:
                            existing = json.loads(best_path.read_text(encoding="utf-8"))
                            existing_score = _summary_quality_score(existing)
                        except (json.JSONDecodeError, OSError):
                            pass
                    repair_score = _summary_quality_score(
                        repair_result.best_experiment_summary
                    )
                    if repair_score > existing_score:
                        best_path.write_text(
                            json.dumps(repair_result.best_experiment_summary, indent=2),
                            encoding="utf-8",
                        )
                    if repair_result.success:
                        await asyncio.to_thread(run_experiment_diagnosis, run_dir, config, run_id)
        except (json.JSONDecodeError, OSError):
            pass
