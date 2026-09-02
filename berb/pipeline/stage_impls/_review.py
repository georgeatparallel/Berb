"""Stage 18-20: Peer review, paper revision, quality gate."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml  # noqa: F401 — available for downstream use

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.integrity.revision_guard import (
    conserved_tokens,
    find_claim_drift_candidates,
    strength_advisory,
)
from berb.llm.client import LLMClient
from berb.pipeline._domain import _detect_domain  # noqa: F401
from berb.pipeline._helpers import (
    StageResult,
    _chat_with_prompt,
    _collect_experiment_results,  # noqa: F401
    _default_quality_report,
    _find_prior_file,
    _get_evolution_overlay,
    _read_prior_artifact,
    _safe_json_loads,
    _topic_constraint_block,  # noqa: F401
    _utcnow_iso,
)
from berb.pipeline.contracts import StageContract
from berb.pipeline.registry import register_stage
from berb.pipeline.stages import Stage, StageStatus
from berb.prompts import PromptManager
from berb.writing.anti_ai import AntiAIEncoder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers imported from executor.py (not yet moved to _helpers.py).
# Lazy-imported inside functions to avoid circular import when executor.py
# imports this module.
# ---------------------------------------------------------------------------


def _get_collect_raw_experiment_metrics():
    from berb.pipeline.stage_impls._paper_writing import _collect_raw_experiment_metrics

    return _collect_raw_experiment_metrics


def _get_review_compiled_pdf():
    from berb.pipeline.stage_impls._paper_writing import _review_compiled_pdf

    return _review_compiled_pdf


# ---------------------------------------------------------------------------
# _collect_experiment_evidence
# ---------------------------------------------------------------------------


def _collect_experiment_evidence(run_dir: Path) -> str:
    """Collect actual experiment parameters and results for peer review."""
    evidence_parts: list[str] = []

    # 1. Read experiment code to find actual trial count, methods used
    exp_dir = _read_prior_artifact(run_dir, "experiment/")
    if exp_dir and Path(exp_dir).is_dir():
        main_py = Path(exp_dir) / "main.py"
        if main_py.exists():
            code = main_py.read_text(encoding="utf-8")
            evidence_parts.append(
                f"### Actual Experiment Code (main.py)\n```python\n{code[:3000]}\n```"
            )

    # 2. Read sandbox run results (actual metrics, runtime, stderr)
    runs_text = _read_prior_artifact(run_dir, "runs/")
    if runs_text and Path(runs_text).is_dir():
        for run_file in sorted(Path(runs_text).glob("*.json"))[:5]:
            payload = _safe_json_loads(run_file.read_text(encoding="utf-8"), {})
            if isinstance(payload, dict):
                summary = {
                    "metrics": payload.get("metrics"),
                    "elapsed_sec": payload.get("elapsed_sec"),
                    "timed_out": payload.get("timed_out"),
                }
                stderr = payload.get("stderr", "")
                if stderr:
                    summary["stderr_excerpt"] = stderr[:500]
                evidence_parts.append(
                    f"### Run Result: {run_file.name}\n```json\n{json.dumps(summary, indent=2)}\n```"
                )

    # 3. Read refinement log for actual iteration count
    refine_log_text = _read_prior_artifact(run_dir, "refinement_log.json")
    if refine_log_text:
        try:
            rlog = json.loads(refine_log_text)
            summary = {
                "iterations_executed": len(rlog.get("iterations", [])),
                "converged": rlog.get("converged"),
                "stop_reason": rlog.get("stop_reason"),
                "best_metric": rlog.get("best_metric"),
            }
            evidence_parts.append(
                f"### Refinement Summary\n```json\n{json.dumps(summary, indent=2)}\n```"
            )
        except (json.JSONDecodeError, TypeError):
            pass

    # 4. Count actual number of experiment runs
    actual_run_count = 0
    for stage_subdir in sorted(run_dir.glob("stage-*/runs")):
        for rf in stage_subdir.glob("*.json"):
            if rf.name != "results.json":
                actual_run_count += 1
    if actual_run_count > 0:
        evidence_parts.append(
            f"### Actual Trial Count\n"
            f"**The experiment was executed {actual_run_count} time(s).** "
            f"If the paper claims a different number of trials, this is a CRITICAL discrepancy."
        )

    if not evidence_parts:
        return ""

    return (
        "\n\n## Actual Experiment Evidence\n"
        "Use the evidence below to verify the paper's methodology claims.\n\n"
        + "\n\n".join(evidence_parts)
    )


# ---------------------------------------------------------------------------
# Stage 18: Peer Review
# ---------------------------------------------------------------------------


@register_stage(
    stage=Stage.PEER_REVIEW,
    depends_on=frozenset({Stage.PAPER_DRAFT}),
    contract=StageContract(
        stage=Stage.PEER_REVIEW,
        input_files=("paper_draft.md",),
        output_files=("reviews.md",),
        dod=">=2 simulated review perspectives with actionable feedback",
        error_code="E18_REVIEW_FAIL",
    ),
)
def _execute_peer_review(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    draft = _read_prior_artifact(run_dir, "paper_draft.md") or ""
    experiment_evidence = _collect_experiment_evidence(run_dir)

    # Load draft quality warnings from Stage 17 (if available)
    _quality_suffix = ""
    _quality_json_path = _find_prior_file(run_dir, "draft_quality.json")
    if _quality_json_path and _quality_json_path.exists():
        try:
            _dq = json.loads(_quality_json_path.read_text(encoding="utf-8"))
            _dq_warnings = _dq.get("overall_warnings", [])
            if _dq_warnings:
                _quality_suffix = (
                    "\n\nAUTOMATED QUALITY ISSUES (flag these in your review):\n"
                    + "\n".join(f"- {w}" for w in _dq_warnings)
                    + "\n"
                )
        except Exception:  # noqa: BLE001
            pass

    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "peer_review")
        sp = _pm.for_stage(
            "peer_review",
            evolution_overlay=_overlay,
            topic=config.research.topic,
            draft=draft,
            experiment_evidence=experiment_evidence,
        )
        _review_user = sp.user + _quality_suffix
        resp = _chat_with_prompt(
            llm,
            sp.system,
            _review_user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        reviews = resp.content
    else:
        reviews = """# Reviews

## Reviewer A
- Strengths: Clear problem statement.
- Weaknesses: Limited ablation details.
- Actionable revisions: Add uncertainty analysis and stronger baselines.

## Reviewer B
- Strengths: Reproducibility focus.
- Weaknesses: Discussion underdeveloped.
- Actionable revisions: Expand limitations and broader impact.
"""
    (stage_dir / "reviews.md").write_text(reviews, encoding="utf-8")
    return StageResult(
        stage=Stage.PEER_REVIEW,
        status=StageStatus.DONE,
        artifacts=("reviews.md",),
        evidence_refs=("stage-18/reviews.md",),
    )


# ---------------------------------------------------------------------------
# Stage 19: Paper Revision
# ---------------------------------------------------------------------------


@register_stage(
    stage=Stage.PAPER_REVISION,
    depends_on=frozenset({Stage.PAPER_DRAFT, Stage.PEER_REVIEW}),
    contract=StageContract(
        stage=Stage.PAPER_REVISION,
        input_files=("paper_draft.md", "reviews.md"),
        output_files=("paper_revised.md",),
        dod="All review comments addressed with tracked changes",
        error_code="E19_REVISION_FAIL",
    ),
)
def _execute_paper_revision(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    draft = _read_prior_artifact(run_dir, "paper_draft.md") or ""
    reviews = _read_prior_artifact(run_dir, "reviews.md") or ""
    draft_word_count = len(draft.split())

    # R4-2: Collect real metrics for anti-fabrication guard in revision
    # BUG-47: _collect_raw_experiment_metrics returns tuple[str, bool], must unpack
    _raw_metrics_tuple = _get_collect_raw_experiment_metrics()(run_dir)
    raw_metrics_revision = (
        _raw_metrics_tuple[0]
        if isinstance(_raw_metrics_tuple, tuple)
        else (_raw_metrics_tuple or "")
    )
    data_integrity_revision = ""
    if raw_metrics_revision:
        data_integrity_revision = (
            raw_metrics_revision + "\nDATA INTEGRITY: Do NOT add new numbers that are not in the "
            "experiment data above. If a reviewer asks for additional results "
            "you do not have, state 'Due to computational constraints, "
            "this analysis was not conducted' instead of fabricating data.\n"
        )

    if llm is not None:
        _pm = prompts or PromptManager()
        try:
            _ws_revision = _pm.block("writing_structure")
        except (KeyError, Exception):  # noqa: BLE001
            _ws_revision = ""
        # IMP-20/25/31/24: Load style blocks for revision prompt
        _rev_blocks: dict[str, str] = {}
        for _bname in (
            "academic_style_guide",
            "narrative_writing_rules",
            "anti_hedging_rules",
            "anti_repetition_rules",
        ):
            try:
                _rev_blocks[_bname] = _pm.block(_bname)
            except (KeyError, Exception):  # noqa: BLE001
                _rev_blocks[_bname] = ""
        # Load draft quality directives from Stage 17
        _quality_prefix = ""
        _quality_json_path = _find_prior_file(run_dir, "draft_quality.json")
        if _quality_json_path and _quality_json_path.exists():
            try:
                _dq = json.loads(_quality_json_path.read_text(encoding="utf-8"))
                _dq_directives = _dq.get("revision_directives", [])
                if _dq_directives:
                    _quality_prefix = (
                        "MANDATORY QUALITY FIXES (address ALL of these):\n"
                        + "\n".join(f"- {d}" for d in _dq_directives)
                        + "\n\n"
                    )
            except Exception:  # noqa: BLE001
                pass

        # Note: AI-writing-slop detection already happened in Stage 17
        # (_validate_draft_quality → draft_quality.json.revision_directives,
        # loaded into _quality_prefix above) since it runs AntiAIEncoder on
        # this same draft text. No need to re-detect here.

        _overlay = _get_evolution_overlay(run_dir, "paper_revision")
        sp = _pm.for_stage(
            "paper_revision",
            evolution_overlay=_overlay,
            topic_constraint=_pm.block("topic_constraint", topic=config.research.topic),
            writing_structure=_ws_revision,
            draft=draft,
            reviews=_quality_prefix + reviews + data_integrity_revision,
            **_rev_blocks,
        )
        # R10-Fix2: Ensure max_tokens is sufficient for full paper revision
        revision_max_tokens = sp.max_tokens
        if revision_max_tokens and draft_word_count > 0:
            # ~1.5 tokens per word, 20% headroom
            min_tokens_needed = int(draft_word_count * 1.5 * 1.2)
            if revision_max_tokens < min_tokens_needed:
                revision_max_tokens = min_tokens_needed
                logger.info(
                    "Stage 19: Increased max_tokens from %d to %d to fit full paper revision",
                    sp.max_tokens,
                    revision_max_tokens,
                )

        # R10-Fix4: Retry on timeout for paper revision (critical stage)
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=revision_max_tokens,
            retries=2,
        )
        revised = resp.content
        revised_word_count = len(revised.split())
        # Length guard: if revision is shorter than 80% of draft, retry once
        if draft_word_count > 500 and revised_word_count < int(draft_word_count * 0.8):
            logger.warning(
                "Paper revision (%d words) is shorter than draft (%d words). "
                "Retrying with stronger length enforcement.",
                revised_word_count,
                draft_word_count,
            )
            retry_user = (
                f"CRITICAL LENGTH REQUIREMENT: The draft is {draft_word_count} words. "
                f"Your revision MUST be at least {draft_word_count} words — ideally longer. "
                f"Do NOT summarize or condense ANY section. Copy each section verbatim "
                f"and ONLY make targeted improvements to address reviewer comments. "
                f"If a section has no reviewer comments, include it UNCHANGED.\n\n" + sp.user
            )
            resp2 = _chat_with_prompt(
                llm,
                sp.system,
                retry_user,
                json_mode=sp.json_mode,
                max_tokens=revision_max_tokens,
            )
            revised2 = resp2.content
            revised2_word_count = len(revised2.split())
            if revised2_word_count >= int(draft_word_count * 0.8):
                revised = revised2
            elif revised2_word_count > revised_word_count:
                # Retry improved but still not enough — use the longer version
                revised = revised2
                logger.warning(
                    "Retry improved (%d → %d words) but still shorter than draft (%d).",
                    revised_word_count,
                    revised2_word_count,
                    draft_word_count,
                )
            else:
                # Both attempts produced short output — preserve full original draft
                logger.warning(
                    "Retry also produced short output (%d words). "
                    "Falling back to FULL ORIGINAL DRAFT to prevent content loss.",
                    revised2_word_count,
                )
                # Extract useful revision points as appendix
                revision_words = revised.split()
                revision_summary = (
                    " ".join(revision_words[:500]) + "\n\n*(Revision summary truncated)*"
                    if len(revision_words) > 500
                    else revised
                )
                if revision_summary.strip():
                    # Save revision notes to internal file, not paper body
                    (stage_dir / "revision_notes_internal.md").write_text(
                        revision_summary, encoding="utf-8"
                    )
                revised = draft
    else:
        revised = draft
    if revised:
        try:
            revised = AntiAIEncoder().fix_mechanical(revised)
        except Exception:  # noqa: BLE001
            pass

    # tasks/ars_integration_plan.md W6: Layer A (deterministic token
    # conservation, WARN) plus Layer B (LLM-advisory claim-strength
    # drift, ADVISORY). Neither ever fails the stage -- Layer A's known
    # false-positive shape is legitimate rewording that happens to touch
    # a number's neighborhood; Layer B is a judgment call by design (see
    # revision_guard.py's module docstring) and skips itself entirely
    # when no llm is available for this run.
    artifacts = ["paper_revised.md"]
    evidence_refs = ["stage-19/paper_revised.md"]
    if draft and revised:
        try:
            revision_findings = conserved_tokens(draft, revised)
        except Exception:  # noqa: BLE001 - advisory check must never fail the stage
            logger.debug("Revision token-conservation check failed", exc_info=True)
            revision_findings = ()

        if llm is not None:
            _drift_llm = llm
            try:
                drift_candidates = find_claim_drift_candidates(draft, revised)
                drift_findings = strength_advisory(
                    drift_candidates,
                    lambda prompt: _chat_with_prompt(
                        _drift_llm, "", prompt, json_mode=True, max_tokens=256
                    ).content,
                )
                revision_findings = revision_findings + drift_findings
            except Exception:  # noqa: BLE001 - advisory check must never fail the stage
                logger.debug("Claim-strength drift check failed", exc_info=True)

        if revision_findings:
            (stage_dir / "revision_findings.json").write_text(
                json.dumps([f.to_dict() for f in revision_findings], indent=2),
                encoding="utf-8",
            )
            artifacts.append("revision_findings.json")
            evidence_refs.append("stage-19/revision_findings.json")
            for finding in revision_findings:
                logger.warning("[revision] %s: %s", finding.locator, finding.message)

    (stage_dir / "paper_revised.md").write_text(revised, encoding="utf-8")
    return StageResult(
        stage=Stage.PAPER_REVISION,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts),
        evidence_refs=tuple(evidence_refs),
    )


# ---------------------------------------------------------------------------
# Stage 20: Quality Gate
# ---------------------------------------------------------------------------


def _build_ensemble_structured_context(run_dir: Path) -> str:
    """Format the claim manifest + experiment plan for the review ensemble.

    P1-01: this is ScholarPeer's "summary agent" output (claims/method/
    evidence) — Berb already builds it at stage 17 (claim_manifest.json)
    but no reviewer ever read it; the ensemble got raw paper text only.
    """
    parts: list[str] = []

    manifest_path = _find_prior_file(run_dir, "claim_manifest.json")
    if manifest_path is not None:
        try:
            from berb.integrity import ClaimManifest

            manifest = ClaimManifest.load(manifest_path)
            if manifest.claims:
                lines = [
                    f"Extracted claims ({manifest.total_claims} total, "
                    f"{manifest.supported_claims} supported, "
                    f"{manifest.unsupported_claims} unsupported):"
                ]
                for claim in manifest.claims[:40]:
                    lines.append(
                        f"- [{claim.claim_type.value}/{claim.verdict.value}] {claim.text[:200]}"
                    )
                parts.append("\n".join(lines))
        except Exception:  # noqa: BLE001
            logger.debug("Structured context: claim manifest unavailable", exc_info=True)

    exp_plan = _read_prior_artifact(run_dir, "exp_plan.yaml")
    if exp_plan:
        parts.append("Experiment plan:\n" + exp_plan[:3000])

    if not parts:
        return ""

    return (
        "=== STRUCTURED PAPER SUMMARY (auto-extracted; cross-check against "
        "the prose below rather than trusting it blindly) ===\n\n"
        + "\n\n".join(parts)
        + "\n\n=== END STRUCTURED SUMMARY ===\n\n"
    )


@register_stage(
    stage=Stage.QUALITY_GATE,
    depends_on=frozenset({Stage.PAPER_REVISION}),
    contract=StageContract(
        stage=Stage.QUALITY_GATE,
        input_files=("paper_revised.md",),
        output_files=("quality_report.json",),
        dod="Quality score meets threshold and approved",
        error_code="E20_GATE_REJECT",
        max_retries=0,
    ),
)
def _execute_quality_gate(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    revised = _read_prior_artifact(run_dir, "paper_revised.md") or ""
    report: dict[str, Any] | None = None

    # BUG-25 + BUG-180: Load the RICHEST experiment summary for cross-checking.
    # _read_prior_artifact returns the first match in reverse-sorted order,
    # which may be a repair stage with 0 conditions.  Instead, scan all
    # stage-14* experiment summaries and pick the one with the most data.
    _exp_summary: dict[str, Any] = {}
    _exp_summary_text = ""
    _best_richness = -1
    for _es_path in sorted(run_dir.glob("stage-14*/experiment_summary.json")):
        try:
            _es_text = _es_path.read_text(encoding="utf-8")
            _es_data = _safe_json_loads(_es_text, {})
            if not isinstance(_es_data, dict):
                continue
            _richness = len(_es_data.get("condition_summaries", {}))
            if _richness > _best_richness:
                _best_richness = _richness
                _exp_summary = _es_data
                _exp_summary_text = _es_text
        except OSError:
            continue
    # Also check experiment_summary_best.json at run root
    _root_best = run_dir / "experiment_summary_best.json"
    if _root_best.is_file():
        try:
            _rb_text = _root_best.read_text(encoding="utf-8")
            _rb_data = _safe_json_loads(_rb_text, {})
            if isinstance(_rb_data, dict):
                _rb_rich = len(_rb_data.get("condition_summaries", {}))
                if _rb_rich > _best_richness:
                    _exp_summary = _rb_data
                    _exp_summary_text = _rb_text
        except OSError:
            pass
    # Fallback to _read_prior_artifact if nothing found above
    if not _exp_summary:
        _exp_summary_text = _read_prior_artifact(run_dir, "experiment_summary.json") or ""
        _exp_summary = _safe_json_loads(_exp_summary_text, {}) if _exp_summary_text else {}

    _exp_failed = False
    if isinstance(_exp_summary, dict):
        _best_run = _exp_summary.get("best_run", {})
        if isinstance(_best_run, dict):
            _exp_failed = _best_run.get("status") == "failed" and not _best_run.get("metrics")
        # Also check if metrics_summary is empty
        if not _exp_summary.get("metrics_summary"):
            _exp_failed = True
        # BUG-180: If we found real condition data, don't mark as failed
        if _best_richness > 0:
            _exp_failed = False

    if llm is not None:
        _pm = prompts or PromptManager()
        # IMP-33: Evaluate the full paper instead of truncating to 12K chars.
        # Split into chunks if very long, but prefer sending the full text.
        paper_for_eval = revised[:40000] if len(revised) > 40000 else revised

        # BUG-25: Inject experiment status into quality gate prompt
        _exp_context = ""
        if _exp_summary and isinstance(_exp_summary, dict):
            _exp_status_keys = {
                k: _exp_summary.get(k)
                for k in (
                    "total_conditions",
                    "total_metric_keys",
                    "metrics_summary",
                )
                if _exp_summary.get(k) is not None
            }
            # BUG-180: Include condition count from condition_summaries
            _cond_summ = _exp_summary.get("condition_summaries", {})
            if isinstance(_cond_summ, dict) and _cond_summ:
                _exp_status_keys["completed_conditions"] = len(_cond_summ)
                _exp_status_keys["condition_names"] = list(_cond_summ.keys())[:20]
            if _best_run := _exp_summary.get("best_run"):
                _exp_status_keys["best_run_status"] = (
                    _best_run.get("status") if isinstance(_best_run, dict) else str(_best_run)
                )
            _exp_context = (
                "\n\nExperiment summary (for cross-checking reported numbers):\n"
                + json.dumps(_exp_status_keys, indent=2, default=str)[:4000]
                + "\n\nCross-check: If the experiment status is 'failed' with "
                "empty metrics, any numerical results in tables constitute "
                "fabrication. Penalize severely.\n"
            )

        _overlay = _get_evolution_overlay(run_dir, "quality_gate")
        sp = _pm.for_stage(
            "quality_gate",
            evolution_overlay=_overlay,
            quality_threshold=str(config.research.quality_threshold),
            revised=paper_for_eval + _exp_context,
        )
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        parsed = _safe_json_loads(resp.content, {})
        if isinstance(parsed, dict):
            report = parsed
    # BUG-25: If experiment failed with no metrics, cap the quality score
    if report is not None and _exp_failed:
        _orig_score = report.get("score_1_to_10", 5)
        if isinstance(_orig_score, (int, float)) and _orig_score > 3:
            report["score_1_to_10"] = min(_orig_score, 3.0)
            report.setdefault("weaknesses", []).append(
                "Experiment failed with no metrics — any reported numerical "
                "results are unsupported and likely fabricated."
            )
            logger.warning(
                "BUG-25: Experiment failed — capping quality score from %.1f to 3.0",
                _orig_score,
            )
    if report is None:
        report = _default_quality_report(config.research.quality_threshold)
    report.setdefault("generated", _utcnow_iso())
    (stage_dir / "quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    # T2.1: Enforce quality gate — fail if score below threshold
    score = report.get("score_1_to_10", 0)
    # BUG-R5-01: score can be string from LLM JSON — coerce to float
    if not isinstance(score, (int, float)):
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0
    verdict = report.get("verdict", "proceed")
    threshold = config.research.quality_threshold or 5.0

    # --- Fabrication flag: collect real metrics for Stage 22 sanitization ---
    _fabrication_info: dict[str, Any] = {
        "experiment_failed": _exp_failed,
        "quality_score": score,
        "real_metric_values": [],
    }
    if isinstance(_exp_summary, dict):
        # Collect ALL real numeric values from experiment_summary.json
        _cond_summaries = _exp_summary.get("condition_summaries", {})
        if isinstance(_cond_summaries, dict):
            for _cond_name, cond_data in _cond_summaries.items():
                if not isinstance(cond_data, dict):
                    continue
                cond_status = cond_data.get("status", "")
                if cond_status == "failed":
                    continue  # skip failed conditions
                for k, v in cond_data.items():
                    if isinstance(v, (int, float)) and k not in (
                        "seed_count",
                        "total_steps",
                        "training_steps",
                    ):
                        _fabrication_info["real_metric_values"].append(round(float(v), 4))
        _ms = _exp_summary.get("metrics_summary", {})
        if isinstance(_ms, dict):
            for _mk, _mv in _ms.items():
                if isinstance(_mv, dict):
                    for _stat in ("mean", "min", "max"):
                        _sv = _mv.get(_stat)
                        if isinstance(_sv, (int, float)):
                            _fabrication_info["real_metric_values"].append(round(float(_sv), 4))
    _fabrication_info["has_real_data"] = bool(_fabrication_info["real_metric_values"])
    _fabrication_info["fabrication_suspected"] = (
        _exp_failed and not _fabrication_info["has_real_data"]
    )
    # Phase 1: Enhanced fabrication detection via VerifiedRegistry
    # BUG-108: Also pass refinement_log so NaN best_metric is properly handled
    _rl20_candidates = sorted(run_dir.glob("stage-13*/refinement_log.json"), reverse=True)
    _rl20_path = _rl20_candidates[0] if _rl20_candidates else None
    _rl20: dict | None = None
    if _rl20_path and _rl20_path.is_file():
        try:
            _rl20 = json.loads(_rl20_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    try:
        from berb.pipeline.verified_registry import (
            VerifiedRegistry as _VR20,  # noqa: N814
        )

        _vr20 = (
            _VR20.from_run_dir(
                run_dir,
                metric_direction=config.experiment.metric_direction,
                best_only=True,
            )
            if isinstance(_exp_summary, dict)
            else None
        )
        if _vr20:
            _fabrication_info["verified_values_count"] = len(_vr20.values)
            _fabrication_info["verified_conditions"] = sorted(_vr20.condition_names)
    except Exception:
        pass
    (stage_dir / "fabrication_flags.json").write_text(
        json.dumps(_fabrication_info, indent=2), encoding="utf-8"
    )

    # P2-03: surface stage 9's omitted-baseline check here. Informational
    # only, not a veto — a missing baseline is a paper-quality concern, not
    # a fabrication/integrity issue, so it doesn't carry P1-03's rollback
    # weight. Logged so it's visible in the same place as the other gate
    # signals rather than buried in stage-09 logs.
    _omitted_baselines_path = _find_prior_file(run_dir, "omitted_baselines.json")
    if _omitted_baselines_path is not None:
        try:
            _omitted_data = json.loads(_omitted_baselines_path.read_text(encoding="utf-8"))
            _omitted_missing = _omitted_data.get("missing", [])
            if _omitted_missing:
                logger.warning(
                    "Stage 20: %d method(s) from the literature corpus have no "
                    "matching baseline in the experiment plan: %s",
                    len(_omitted_missing),
                    ", ".join(_omitted_missing),
                )
        except (json.JSONDecodeError, OSError):
            pass

    # P2-02: claim-vs-evidence adjudication (technical-soundness half of
    # ScholarPeer's Q&A engine, its single largest ablation at -26%).
    # Stage 17's numeric-regex pass (_extract_numeric_claims) only resolves
    # bare-number EMPIRICAL claims; comparative/causal claims it can't
    # classify are left NOT_CHECKED forever. This targets that gap using an
    # LLM cross-reference against the evidence registry — informational
    # only, like the omitted-baselines check above, since an LLM verdict on
    # claim-evidence alignment is not reliable enough to hard-gate on.
    if llm is not None:
        try:
            _claim_manifest_path = _find_prior_file(run_dir, "claim_manifest.json")
            if _claim_manifest_path is not None:
                from berb.integrity import ClaimManifest, VerifiedEvidenceRegistry
                from berb.review.interrogation import adjudicate_claims

                _manifest = ClaimManifest.load(_claim_manifest_path)
                _evidence_reg = VerifiedEvidenceRegistry.load(run_dir / "evidence_registry.json")
                _verdicts = adjudicate_claims(llm, _manifest.claims, _evidence_reg)
                if _verdicts:
                    (stage_dir / "claim_adjudication.json").write_text(
                        json.dumps(
                            [
                                {
                                    "claim_id": v.claim_id,
                                    "status": v.status.value,
                                    "reasoning": v.reasoning,
                                }
                                for v in _verdicts
                            ],
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    _unsupported = [v for v in _verdicts if v.status.value == "unsupported"]
                    if _unsupported:
                        logger.warning(
                            "Stage 20: claim adjudication found %d unsupported claim(s) "
                            "not caught by stage 17's numeric check",
                            len(_unsupported),
                        )
        except Exception:  # noqa: BLE001
            logger.debug("Stage 20: claim adjudication skipped", exc_info=True)

    # P1-03: 5-reviewer ensemble + Area Chair meta-review, now feeding the
    # gate decision. Previously this ran at stage 22 (_execute_export_publish,
    # AFTER export) inside a debug-swallowed try/except, and MetaReview was
    # written to ensemble_review.md and read by nothing — a review nobody
    # can act on. Moved here because stage 20 is the designated GATE with a
    # PAPER_OUTLINE rollback target (stages.py GATE_ROLLBACK).
    # Independent veto only — does not touch the numeric score path below —
    # so wiring this in cannot make outcomes worse than before. Bounded to
    # one veto per run via ensemble_veto_used.json so a paper can't loop
    # forever if the ensemble keeps rejecting.
    _ens_meta = None
    if llm is not None:
        try:
            import asyncio

            from berb.review.ensemble import AutomatedReviewerEnsemble, Decision

            _ensemble = AutomatedReviewerEnsemble(llm_client=llm)
            # P1-01: prepend the claim manifest + exp plan so every persona
            # shares the structured signal via the existing cached_prefix
            # mechanism (ensemble.py builds cached_prefix from paper_text) —
            # no ensemble.py changes needed, this is purely what the caller
            # hands it as the "paper".
            _structured_context = _build_ensemble_structured_context(run_dir)
            # P3-05: condition on the actually-targeted venue.
            # config.export.target_conference already drives stage 22's
            # template selection and NeurIPS-checklist generation — the
            # internal review should judge against the same venue rather
            # than a generic implicit standard.
            try:
                from berb.templates import get_template as _get_venue_template

                _venue = _get_venue_template(config.export.target_conference)
                _structured_context = (
                    f"## Target Venue\nThis paper targets {_venue.display_name}. "
                    f"Judge novelty, rigor, and presentation against that venue's "
                    f"typical standards, not a generic bar.\n\n" + _structured_context
                )
            except Exception:  # noqa: BLE001
                logger.debug("Stage 20: venue conditioning unavailable", exc_info=True)
            _ens_reviews = asyncio.run(
                _ensemble.review_paper(
                    run_dir / "stage-19" / "paper_revised.md",
                    paper_text=_structured_context + revised,
                    use_batch=config.llm.batch_review_enabled,
                )
            )
            _ens_meta = _ensemble.area_chair_decision(_ens_reviews)
            # P3-03: cross-reviewer critique synthesis, purely additive —
            # area_chair_decision's scoring math above is untouched.
            try:
                _ens_meta.critique_synthesis = asyncio.run(
                    _ensemble.synthesize_critiques(_ens_reviews)
                )
            except Exception:  # noqa: BLE001
                logger.debug("Stage 20: Critique synthesis skipped", exc_info=True)
            _ensemble.generate_review_report(
                _ens_reviews, _ens_meta, output_path=stage_dir / "ensemble_review.md"
            )
            logger.info(
                "Stage 20: Ensemble review %.2f/10 (%s), %d conflict(s)",
                _ens_meta.average_score,
                _ens_meta.consensus_decision.value,
                len(_ens_meta.reviewer_conflicts),
            )
        except Exception as _ens_exc:  # noqa: BLE001
            logger.debug("Stage 20: Ensemble review skipped: %s", _ens_exc)

    _ens_veto = False
    _ens_veto_reason = ""
    if _ens_meta is not None and _ens_meta.consensus_decision in (
        Decision.REJECT,
        Decision.STRONG_REJECT,
    ):
        _veto_marker = run_dir / "ensemble_veto_used.json"
        if not _veto_marker.is_file():
            _ens_veto = True
            _ens_veto_reason = (
                f"Ensemble consensus {_ens_meta.consensus_decision.value} "
                f"({_ens_meta.average_score:.1f}/10)"
            )
            _veto_marker.write_text(
                json.dumps(
                    {
                        "triggered_at": _utcnow_iso(),
                        "consensus_decision": _ens_meta.consensus_decision.value,
                        "average_score": _ens_meta.average_score,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.warning(
                "Stage 20: %s — vetoing quality gate (one-time; further "
                "ensemble rejects this run will not re-veto).",
                _ens_veto_reason,
            )
        else:
            logger.info(
                "Stage 20: Ensemble consensus %s (%.1f/10) but veto already "
                "used this run — proceeding.",
                _ens_meta.consensus_decision.value,
                _ens_meta.average_score,
            )

    _score_failed = isinstance(score, (int, float)) and score < threshold
    if _score_failed or _ens_veto:
        _fail_reason = (
            f"score {score:.1f} < threshold {threshold:.1f}" if _score_failed else _ens_veto_reason
        )
        _gate_artifacts = ("quality_report.json", "fabrication_flags.json")
        if (stage_dir / "ensemble_review.md").is_file():
            _gate_artifacts = (*_gate_artifacts, "ensemble_review.md")
        if (stage_dir / "claim_adjudication.json").is_file():
            _gate_artifacts = (*_gate_artifacts, "claim_adjudication.json")
        if config.research.graceful_degradation:
            logger.warning(
                "Quality gate DEGRADED: %s — continuing with sanitization "
                "(graceful_degradation=True)",
                _fail_reason,
            )
            # Write degradation signal for downstream stages
            signal = {
                "score": score,
                "threshold": threshold,
                "verdict": verdict,
                "weaknesses": report.get("weaknesses", []),
                "ensemble_veto": _ens_veto,
                "ensemble_veto_reason": _ens_veto_reason,
                "generated": _utcnow_iso(),
            }
            (run_dir / "degradation_signal.json").write_text(
                json.dumps(signal, indent=2), encoding="utf-8"
            )
            return StageResult(
                stage=Stage.QUALITY_GATE,
                status=StageStatus.DONE,
                artifacts=_gate_artifacts,
                evidence_refs=("stage-20/quality_report.json",),
                decision="degraded",
            )
        logger.warning("Quality gate FAILED: %s (verdict=%s)", _fail_reason, verdict)
        return StageResult(
            stage=Stage.QUALITY_GATE,
            status=StageStatus.FAILED,
            artifacts=_gate_artifacts,
            evidence_refs=("stage-20/quality_report.json",),
            error=f"Quality gate failed: {_fail_reason}. Paper needs revision before export.",
        )

    logger.info(
        "Quality gate PASSED: score %.1f >= threshold %.1f",
        score,
        threshold,
    )
    _passed_artifacts = ("quality_report.json", "fabrication_flags.json")
    if (stage_dir / "ensemble_review.md").is_file():
        _passed_artifacts = (*_passed_artifacts, "ensemble_review.md")
    if (stage_dir / "claim_adjudication.json").is_file():
        _passed_artifacts = (*_passed_artifacts, "claim_adjudication.json")
    return StageResult(
        stage=Stage.QUALITY_GATE,
        status=StageStatus.DONE,
        artifacts=_passed_artifacts,
        evidence_refs=("stage-20/quality_report.json",),
    )


# ---------------------------------------------------------------------------
# Stage 21: Knowledge Archive
# ---------------------------------------------------------------------------
