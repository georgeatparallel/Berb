from __future__ import annotations

# ============================================================================
# Standard Library
# ============================================================================
import inspect
import json
import logging
import time as _time
from pathlib import Path

# ============================================================================
# Third-Party
# ============================================================================
# ============================================================================
# Internal - Core Modules
# ============================================================================
from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.llm import create_llm_client

# Re-exported for backward compatibility: callers (e.g. packaging.py) import
# _extract_paper_title from here rather than the _figure_helpers module it
# actually lives in.
from berb.pipeline._figure_helpers import _extract_paper_title  # noqa: F401

# ============================================================================
# Internal - Pipeline Core
# ============================================================================
from berb.pipeline.contracts import CONTRACTS, StageContract
from berb.pipeline.registry import get_registration
from berb.pipeline.stages import (
    Stage,
    StageStatus,
    TransitionEvent,
    advance,
    gate_required,
)
from berb.prompts import PromptManager

logger = logging.getLogger(__name__)

# ============================================================================
# Internal - Pipeline Stage Implementations
# Organized by pipeline execution order (Stages 1-23)
# ============================================================================

# Stages 1-2: Topic Scoping
# ============================================================================
# Internal - Shared Helpers (must load after stage implementations)
# ============================================================================
from berb.pipeline._helpers import (  # noqa: E402
    StageResult,
    _build_context_preamble,  # noqa: F401
    _detect_runtime_issues,  # noqa: F401
    _extract_multi_file_blocks,  # noqa: F401
    _extract_topic_keywords,  # noqa: F401
    _extract_yaml_block,  # noqa: F401
    _load_hardware_profile,  # noqa: F401
    _multi_perspective_generate,  # noqa: F401
    _parse_metrics_from_stdout,  # noqa: F401
    _read_prior_artifact,
    _safe_filename,  # noqa: F401
    _safe_json_loads,  # noqa: F401
    _synthesize_perspectives,  # noqa: F401
    _topic_constraint_block,  # noqa: F401
    _utcnow_iso,
    _write_stage_meta,
)

# Stages 14-15: Analysis & Decision
from berb.pipeline.stage_impls._analysis import (  # noqa: E402,F401
    _execute_research_decision,
    _execute_result_analysis,
    _parse_decision,
)

# Stage 10: Code Generation
from berb.pipeline.stage_impls._code_generation import (  # noqa: E402,F401
    _execute_code_generation,
)

# Stages 11-13: Experiment Execution
from berb.pipeline.stage_impls._execution import (  # noqa: E402,F401
    _execute_experiment_run,
    _execute_iterative_refine,
    _execute_resource_planning,
)

# Stage 9: Experiment Design
from berb.pipeline.stage_impls._experiment_design import (  # noqa: E402,F401
    _execute_experiment_design,
)

# Stages 3-6: Literature Search
from berb.pipeline.stage_impls._literature import (  # noqa: E402,F401
    _execute_knowledge_extract,
    _execute_literature_collect,
    _execute_literature_screen,
    _execute_search_strategy,
    _expand_search_queries,
)

# Stages 16-17: Paper Writing
from berb.pipeline.stage_impls._paper_writing import (  # noqa: E402,F401
    _collect_raw_experiment_metrics,
    _execute_paper_draft,
    _execute_paper_outline,
    _validate_draft_quality,
    _write_paper_sections,
)

# Stages 18-20: Peer review, paper revision, quality gate
from berb.pipeline.stage_impls._review import (  # noqa: E402,F401
    _collect_experiment_evidence,
    _execute_paper_revision,
    _execute_peer_review,
    _execute_quality_gate,
)

# Stage 21: Knowledge archive
from berb.pipeline.stage_impls._archive import (  # noqa: E402,F401
    _execute_knowledge_archive,
)

# Stage 22: Export & publish
from berb.pipeline.stage_impls._export import (  # noqa: E402,F401
    _execute_export_publish,
)

# Stage 23: Citation verify
from berb.pipeline.stage_impls._citations import (  # noqa: E402,F401
    _execute_citation_verify,
    _remove_bibtex_entries,
    _remove_citations_from_text,
)

# Stages 7-8: Synthesis & Hypothesis
from berb.pipeline.stage_impls._synthesis import (  # noqa: E402,F401
    _execute_hypothesis_gen,
    _execute_synthesis,
)
from berb.pipeline.stage_impls._topic import (  # noqa: E402,F401
    _execute_problem_decompose,
    _execute_topic_init,
)

# _STAGE_EXECUTORS removed in cleanup — registry is the sole source.
# Stage _execute_* imports above trigger @register_stage decorators.


def execute_stage(
    stage: Stage,
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    auto_approve_gates: bool = False,
) -> StageResult:
    """Execute one pipeline stage, validate outputs, and apply gate logic."""

    stage_dir = run_dir / f"stage-{int(stage):02d}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    _t_health_start = _time.monotonic()
    contract: StageContract = CONTRACTS[stage]

    if contract.input_files:
        for input_file in contract.input_files:
            found = _read_prior_artifact(run_dir, input_file)
            if found is None:
                result = StageResult(
                    stage=stage,
                    status=StageStatus.FAILED,
                    artifacts=(),
                    error=f"Missing input: {input_file} (required by {stage.name})",
                    decision="retry",
                )
                _write_stage_meta(stage_dir, stage, run_id, result)
                return result

    bridge = config.openclaw_bridge
    if bridge.use_message and config.notifications.on_stage_start:
        adapters.message.notify(
            config.notifications.channel,
            f"stage-{int(stage):02d}-start",
            f"Starting {stage.name}",
        )
    if bridge.use_memory:
        adapters.memory.append("stages", f"{run_id}:{int(stage)}:running")

    llm = None
    try:
        # A1-2 (tasks/hardening_plan_2026-08-13.md): previously only the
        # "acp" branch went through create_llm_client() — every other
        # provider bypassed it via LLMClient.from_rc_config() directly, so
        # configured fallback_providers (MultiProviderLLMClient) and
        # NadirClaw/token-tracking (SmartLLMClient) never engaged outside
        # ACP, even when set in config. The factory already branches on
        # both internally; call it unconditionally.
        candidate = create_llm_client(config)
        if config.llm.provider == "acp":
            # ACP spawns a subprocess agent rather than making HTTP calls,
            # so it has no base_url/api_key to gate on — preserve the
            # original ungated behavior for this provider.
            llm = candidate
        else:
            # Preserve the original guard: stage impls rely on llm=None
            # when nothing is configured, not a client with an empty
            # base_url/api_key that will fail on first real call.
            candidate_config = getattr(candidate, "config", None)
            if (
                candidate_config is not None
                and candidate_config.base_url
                and candidate_config.api_key
            ):
                llm = candidate
    except Exception as _llm_exc:  # noqa: BLE001
        logger.warning("LLM client creation failed: %s", _llm_exc)
        llm = None

    try:
        _ = advance(stage, StageStatus.PENDING, TransitionEvent.START)
        # Wire port to concrete llm so stage impls can use adapters.llm
        adapters.llm = llm  # type: ignore[assignment]
        # Lookup stage implementation from plugin registry
        reg = get_registration(stage)
        if reg is None:
            raise KeyError(
                f"No stage implementation registered for {stage.name} ({int(stage)}). "
                f"Ensure the stage_impls module is imported."
            )
        executor = reg.fn
        prompts = PromptManager(config.prompts.custom_file or None)  # type: ignore[attr-defined]
        # Detect at call-time whether this executor accepts a 'prompts' kwarg by
        # inspecting its signature.  The previous approach caught TypeError and
        # checked the exception message string, which is fragile (message text
        # differs across Python versions) and silently masked real TypeErrors
        # raised *inside* the executor (BUG-003).
        try:
            sig = inspect.signature(executor)
            _accepts_prompts = "prompts" in sig.parameters
        except (ValueError, TypeError):
            # inspect.signature can fail for C extensions; assume no prompts.
            _accepts_prompts = False
        # Phase 2: Port adapters are available via adapters.llm, adapters.lit,
        # adapters.sandbox, adapters.store. Stage implementations that want to
        # use port interfaces can access them through the AdapterBundle directly.
        # This avoids signature changes to every stage function.
        if _accepts_prompts:
            result = executor(stage_dir, run_dir, config, adapters, llm=llm, prompts=prompts)
        else:
            result = executor(stage_dir, run_dir, config, adapters, llm=llm)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Stage %s failed", stage.name)
        result = StageResult(
            stage=stage,
            status=StageStatus.FAILED,
            artifacts=(),
            error=str(exc),
            decision="retry",
        )

    if result.status == StageStatus.DONE:
        for output_file in contract.output_files:
            if output_file.endswith("/"):
                path = stage_dir / output_file.rstrip("/")
                if not path.is_dir() or not any(path.iterdir()):
                    result = StageResult(
                        stage=stage,
                        status=StageStatus.FAILED,
                        artifacts=result.artifacts,
                        error=f"Missing output directory: {output_file}",
                        decision="retry",
                        evidence_refs=result.evidence_refs,
                    )
                    break
            else:
                path = stage_dir / output_file
                if not path.exists() or path.stat().st_size == 0:
                    result = StageResult(
                        stage=stage,
                        status=StageStatus.FAILED,
                        artifacts=result.artifacts,
                        error=f"Missing or empty output: {output_file}",
                        decision="retry",
                        evidence_refs=result.evidence_refs,
                    )
                    break

    # --- MetaClaw PRM quality gate evaluation ---
    try:
        mc_bridge = getattr(config, "metaclaw_bridge", None)
        if mc_bridge and getattr(mc_bridge, "enabled", False) and result.status == StageStatus.DONE:
            mc_prm = getattr(mc_bridge, "prm", None)
            if mc_prm and getattr(mc_prm, "enabled", False):
                prm_stages = getattr(mc_prm, "gate_stages", (5, 9, 15, 20))
                if int(stage) in prm_stages:
                    from berb.metaclaw_bridge.prm_gate import ResearchPRMGate

                    prm_gate = ResearchPRMGate.from_bridge_config(mc_prm)
                    if prm_gate is not None:
                        # Read stage output for PRM evaluation
                        output_text = ""
                        for art in result.artifacts:
                            art_path = stage_dir / art
                            if art_path.exists() and art_path.is_file():
                                try:
                                    output_text += art_path.read_text(encoding="utf-8")[:4000]
                                except (UnicodeDecodeError, OSError):
                                    pass
                        if output_text:
                            prm_score = prm_gate.evaluate_stage(int(stage), output_text)
                            logger.info(
                                "MetaClaw PRM score for stage %d: %.1f",
                                int(stage),
                                prm_score,
                            )
                            # Write PRM score to stage health
                            import json as _prm_json

                            prm_report = {
                                "stage": int(stage),
                                "prm_score": prm_score,
                                "model": prm_gate.model,
                                "votes": prm_gate.votes,
                            }
                            (stage_dir / "prm_score.json").write_text(
                                _prm_json.dumps(prm_report, indent=2),
                                encoding="utf-8",
                            )
                            # If PRM score is -1 (fail), mark stage as failed
                            if prm_score == -1.0:
                                logger.warning(
                                    "MetaClaw PRM rejected stage %d output",
                                    int(stage),
                                )
                                result = StageResult(
                                    stage=result.stage,
                                    status=StageStatus.FAILED,
                                    artifacts=result.artifacts,
                                    error="PRM quality gate: output below quality threshold",
                                    decision="retry",
                                    evidence_refs=result.evidence_refs,
                                )
    except Exception:  # noqa: BLE001
        logger.warning("MetaClaw PRM evaluation failed (non-blocking)")

    if gate_required(stage, config.security.hitl_required_stages):
        if auto_approve_gates:
            if bridge.use_memory:
                adapters.memory.append("gates", f"{run_id}:{int(stage)}:auto-approved")
        else:
            result = StageResult(
                stage=result.stage,
                status=StageStatus.BLOCKED_APPROVAL,
                artifacts=result.artifacts,
                error=result.error,
                decision="block",
                evidence_refs=result.evidence_refs,
            )
            if bridge.use_message and config.notifications.on_gate_required:
                adapters.message.notify(
                    config.notifications.channel,
                    f"gate-{int(stage):02d}",
                    f"Approval required for {stage.name}",
                )

    if bridge.use_memory:
        adapters.memory.append("stages", f"{run_id}:{int(stage)}:{result.status.value}")

    _write_stage_meta(stage_dir, stage, run_id, result)

    _t_health_end = _time.monotonic()
    stage_health = {
        "stage_id": f"{int(stage):02d}-{stage.name.lower()}",
        "run_id": run_id,
        "duration_sec": round(_t_health_end - _t_health_start, 2),
        "status": result.status.value,
        "artifacts_count": len(result.artifacts),
        "error": result.error,
        "timestamp": _utcnow_iso(),
    }
    try:
        (stage_dir / "stage_health.json").write_text(
            json.dumps(stage_health, indent=2), encoding="utf-8"
        )
    except OSError:
        pass

    return result


from berb.pipeline.stage_impls._archive import (  # noqa: E402,F401
    _sanitize_fabricated_data,
)
