"""Iterative pipeline — quality-driven improvement loop.

Runs the full pipeline, then iteratively re-runs stages 16-22 (paper writing +
finalization) with review feedback until quality threshold is met or convergence
is detected.

Extracted from pipeline/runner.py as part of the Phase 2 runner split.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.pipeline.stages import Stage

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _consecutive_empty_metrics(run_dir: Path, pivot_count: int) -> bool:
    """Check if the current and previous REFINE cycles both produced empty metrics."""
    current = run_dir / "stage-14" / "experiment_summary.json"
    if not current.exists():
        for _v in range(pivot_count + 1, 0, -1):
            alt = run_dir / f"stage-14_v{_v}" / "experiment_summary.json"
            if alt.exists():
                current = alt
                break
    prev = run_dir / f"stage-14_v{pivot_count}" / "experiment_summary.json"
    for path in (current, prev):
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            has_metrics = False
            ms = data.get("metrics_summary", {})
            if isinstance(ms, dict) and ms:
                has_metrics = True
            br = data.get("best_run", {})
            if isinstance(br, dict) and br.get("metrics"):
                has_metrics = True
            if has_metrics:
                return False
        except (json.JSONDecodeError, OSError, AttributeError):
            return False
    return True


# ==== Quality helpers for iterative pipeline ====


def read_pivot_count(run_dir: Path) -> int:
    """Read how many PIVOT/REFINE decisions have been made so far."""
    history_path = run_dir / "decision_history.json"
    if not history_path.exists():
        return 0
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return len(data)
    except (json.JSONDecodeError, OSError):
        pass
    return 0


def record_decision_history(
    run_dir: Path, decision: str, rollback_target: Stage, attempt: int
) -> None:
    """Append a decision event to the history log."""
    history_path = run_dir / "decision_history.json"
    history: list[dict[str, object]] = []
    if history_path.exists():
        try:
            data = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                history = data
        except (json.JSONDecodeError, OSError):
            pass
    history.append(
        {
            "decision": decision,
            "rollback_target": rollback_target.name,
            "rollback_stage_num": int(rollback_target),
            "attempt": attempt,
            "timestamp": _utcnow_iso(),
        }
    )
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def read_quality_score(run_dir: Path) -> float | None:
    """Extract quality score from the most recent quality_report.json."""
    report_path = run_dir / "stage-20" / "quality_report.json"
    if not report_path.exists():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in ("score_1_to_10", "score", "quality_score", "overall_score"):
                if key in data:
                    return float(data[key])
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return None


def write_iteration_context(
    run_dir: Path, iteration: int, reviews: str, quality_score: float | None
) -> None:
    """Write iteration feedback file so next round can read it."""
    ctx = {
        "iteration": iteration,
        "quality_score": quality_score,
        "reviews_excerpt": reviews[:3000] if reviews else "",
        "generated": _utcnow_iso(),
    }
    (run_dir / "iteration_context.json").write_text(json.dumps(ctx, indent=2), encoding="utf-8")


def _version_rollback_stages(run_dir: Path, rollback_target: Stage, attempt: int) -> None:
    """Rename stage directories that will be overwritten by a PIVOT/REFINE."""
    import shutil as _shutil

    from berb.pipeline.stages import Stage as _Stage

    rollback_num = int(rollback_target)
    decision_num = int(_Stage.RESEARCH_DECISION)

    for stage_num in range(rollback_num, decision_num + 1):
        stage_dir = run_dir / f"stage-{stage_num:02d}"
        if stage_dir.exists():
            version_dir = run_dir / f"stage-{stage_num:02d}_v{attempt}"
            if version_dir.exists():
                _shutil.rmtree(version_dir)
            stage_dir.rename(version_dir)


def _promote_best_stage14(run_dir: Path, config: RCConfig) -> None:
    """After forced PROCEED, promote the best stage-14 experiment.

    Scans all stage-14* directories, scores them by primary metric,
    and copies the best results into stage-14/.
    """
    import shutil as _shutil

    metric_key = config.experiment.metric_key or "primary_metric"
    metric_dir = config.experiment.metric_direction or "maximize"

    candidates: list[tuple[float, Path]] = []
    for d in sorted(run_dir.glob("stage-14*")):
        summary_path = d / "experiment_summary.json"
        if not summary_path.exists():
            continue
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ms = data.get("metrics_summary", {})
        pm_val: float | None = None
        if metric_key in ms:
            _v = ms[metric_key]
            try:
                pm_val = float(_v["mean"] if isinstance(_v, dict) else _v)
            except (TypeError, ValueError, KeyError):
                pass
        if pm_val is None:
            for k, v in ms.items():
                if metric_key in k:
                    try:
                        pm_val = float(v["mean"] if isinstance(v, dict) else v)
                    except (TypeError, ValueError, KeyError):
                        pass
                    break
        if pm_val is not None:
            candidates.append((pm_val, d))

    if not candidates:
        return

    current_dir = run_dir / "stage-14"
    candidates.sort(key=lambda x: x[0], reverse=(metric_dir == "maximize"))

    if metric_dir == "minimize" and len(candidates) > 1:
        _bv, _bd = candidates[0]
        _sv = candidates[1][0]
        if 0 < _bv < _sv * 1e-3:
            logger.warning(
                "BUG-226: Degenerate best value %.6g is >1000x smaller than "
                "second-best %.6g — skipping degenerate iteration %s",
                _bv,
                _sv,
                _bd.name,
            )
            candidates.pop(0)

    best_val, best_dir = candidates[0]
    _best_src = best_dir / "experiment_summary.json"
    if _best_src.exists():
        _shutil.copy2(_best_src, run_dir / "experiment_summary_best.json")
        _best_analysis = best_dir / "analysis.md"
        if _best_analysis.exists():
            _shutil.copy2(_best_analysis, run_dir / "analysis_best.md")

    if best_dir == current_dir:
        return

    current_summary = current_dir / "experiment_summary.json"
    best_summary = best_dir / "experiment_summary.json"
    if best_summary.exists():
        current_dir.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(best_summary, current_summary)
        for fname in [
            "analysis.md",
            "results_table.tex",
            "figure_plan.json",
            "figure_plan_final.json",
        ]:
            src = best_dir / fname
            if src.exists():
                _shutil.copy2(src, current_dir / fname)
        best_charts = best_dir / "charts"
        current_charts = current_dir / "charts"
        if best_charts.is_dir():
            if current_charts.is_dir():
                _shutil.rmtree(current_charts)
            _shutil.copytree(best_charts, current_charts)


def _check_experiment_quality(run_dir: Path, pivot_count: int) -> tuple[bool, str]:
    """Quality gate before forced PROCEED.

    Returns (ok, message). ok=False means experiment results have critical
    quality issues.
    """
    summary_path = run_dir / "experiment_summary_best.json"
    if not summary_path.exists():
        summary_path = run_dir / "stage-14" / "experiment_summary.json"
    if not summary_path.exists():
        for v in range(pivot_count, 0, -1):
            alt = run_dir / f"stage-14_v{v}" / "experiment_summary.json"
            if alt.exists():
                summary_path = alt
                break

    if not summary_path.exists():
        return False, "No experiment_summary.json found — no metrics produced"

    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "experiment_summary.json is malformed"

    ms = data.get("metrics_summary", {})
    if isinstance(ms, dict):
        values: list[float] = []
        for _k, v in ms.items():
            if isinstance(v, (int, float)):
                values.append(float(v))
            elif isinstance(v, dict) and "mean" in v:
                _mv = v["mean"]
                if isinstance(_mv, (int, float)):
                    values.append(float(_mv))
        if values and all(v == 0.0 for v in values):
            return False, "All experiment metrics are zero — experiments likely failed"

    ablation_warnings = data.get("ablation_warnings", [])
    conditions = data.get("condition_summaries", data.get("condition_metrics", {}))
    if isinstance(conditions, dict) and len(conditions) >= 2:
        primary_values: list[float] = []
        for _cond_name, cond_data in conditions.items():
            if isinstance(cond_data, dict):
                _metrics = cond_data.get("metrics", cond_data)
                pm = _metrics.get("primary_metric", _metrics.get("primary_metric_mean"))
                if isinstance(pm, (int, float)):
                    primary_values.append(float(pm))
        if len(primary_values) >= 2 and len(set(primary_values)) == 1:
            return False, (
                f"All {len(primary_values)} conditions have identical primary_metric "
                f"({primary_values[0]}) — condition implementations are likely broken"
            )

    if isinstance(ablation_warnings, list) and len(ablation_warnings) >= 3:
        return False, (
            f"{len(ablation_warnings)} ablation warnings — most conditions "
            f"produce identical results"
        )

    quality = data.get("analysis_quality", data.get("quality_score"))
    if isinstance(quality, (int, float)) and quality < 3.0:
        return False, f"Analysis quality score {quality}/10 — below minimum threshold"

    return True, "Quality checks passed"


async def execute_iterative_pipeline(
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    auto_approve_gates: bool = False,
    kb_root: Path | None = None,
    max_iterations: int = 3,
    quality_threshold: float = 7.0,
    convergence_rounds: int = 2,
) -> dict[str, object]:
    """Run the full pipeline with iterative quality improvement.

    After the first full pass (stages 1-22), if the quality gate score is below
    *quality_threshold*, re-run stages 16-22 (paper writing + finalization) with
    review feedback injected. Stops when:
      - Score >= quality_threshold, OR
      - Score hasn't improved for *convergence_rounds* consecutive iterations, OR
      - *max_iterations* reached.

    Returns a summary dict with iteration history.
    """
    from berb.pipeline.packaging import package_deliverables
    from berb.pipeline.runner import execute_pipeline
    from berb.pipeline.stages import Stage

    iteration_scores: list[float | None] = []
    all_results: list[list[object]] = []

    # First full pass
    logger.info("Iteration 1/%d: running full pipeline (stages 1-22)", max_iterations)
    results = await execute_pipeline(
        run_dir=run_dir,
        run_id=f"{run_id}-iter1",
        config=config,
        adapters=adapters,
        auto_approve_gates=auto_approve_gates,
        kb_root=kb_root,
    )
    all_results.append(results)
    score = read_quality_score(run_dir)
    iteration_scores.append(score)
    logger.info("Iteration 1 score: %s", score)

    for iteration in range(2, max_iterations + 1):
        if score is not None and score >= quality_threshold:
            logger.info(
                "Quality threshold %.1f met (score=%.1f). Stopping.",
                quality_threshold,
                score,
            )
            break

        if len(iteration_scores) >= convergence_rounds:
            recent = iteration_scores[-convergence_rounds:]
            if all(s is not None for s in recent):
                recent_scores = [float(s) for s in recent if s is not None]
                if max(recent_scores) - min(recent_scores) < 0.5:
                    logger.info(
                        "Convergence detected: scores %s unchanged for %d rounds. Stopping.",
                        recent,
                        convergence_rounds,
                    )
                    break

        reviews_text = ""
        reviews_path = run_dir / "stage-18" / "reviews.md"
        if reviews_path.exists():
            reviews_text = reviews_path.read_text(encoding="utf-8")
        write_iteration_context(run_dir, iteration, reviews_text, score)

        logger.info(
            "Iteration %d/%d: re-running stages 16-22 with feedback",
            iteration,
            max_iterations,
        )
        results = await execute_pipeline(
            run_dir=run_dir,
            run_id=f"{run_id}-iter{iteration}",
            config=config,
            adapters=adapters,
            from_stage=Stage.PAPER_OUTLINE,
            auto_approve_gates=auto_approve_gates,
            kb_root=kb_root,
        )
        all_results.append(results)
        score = read_quality_score(run_dir)
        iteration_scores.append(score)
        logger.info("Iteration %d score: %s", iteration, score)

    converged = False
    if len(iteration_scores) >= convergence_rounds:
        recent_window = iteration_scores[-convergence_rounds:]
        if all(s is not None for s in recent_window):
            recent_scores = [float(s) for s in recent_window if s is not None]
            converged = max(recent_scores) - min(recent_scores) < 0.5

    summary: dict[str, object] = {
        "run_id": run_id,
        "total_iterations": len(iteration_scores),
        "iteration_scores": iteration_scores,
        "quality_threshold": quality_threshold,
        "converged": converged,
        "final_score": iteration_scores[-1] if iteration_scores else None,
        "met_threshold": score is not None and score >= quality_threshold,
        "stages_per_iteration": [len(r) for r in all_results],
        "generated": _utcnow_iso(),
    }
    (run_dir / "iteration_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    try:
        deliverables_dir = package_deliverables(run_dir, run_id, config)
        if deliverables_dir is not None:
            print(f"[{run_id}] Deliverables packaged -> {deliverables_dir}")
    except Exception:
        logger.warning("Deliverables packaging failed", exc_info=True)

    return summary
