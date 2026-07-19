"""Stage I/O contracts for the 23-stage Berb pipeline.

Each StageContract declares:
  - input_files: artifacts this stage reads (produced by prior stages)
  - output_files: artifacts this stage must produce
  - dod: Definition of Done — human-readable acceptance criterion
  - error_code: unique error identifier for diagnostics
  - max_retries: how many times the stage may be retried on failure

Phase 3 Step 8: ``CONTRACTS`` can be rebuilt from the plugin registry
via ``rebuild_from_registry()``.  Adding a new stage no longer requires
editing this module — the registry's decorator carries the contract inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from berb.pipeline.stages import Stage


@dataclass(frozen=True)
class ExecutionFeedback:
    """Carrier for execution-time signals consumed at refinement time.

    Produced by Stage 12 (EXPERIMENT_RUN) at detection sites such as
    trivial runtime, timeout, or budget underuse. Consumed by Stage 13
    (ITERATIVE_REFINE) to inform the refinement prompt.

    Written to execution_feedback.json.
    """

    kind: Literal["trivial_runtime", "timeout", "budget_underuse", "no_metrics"]
    severity: Literal["info", "warn", "block"]
    message: str
    suggested_action: str


@dataclass(frozen=True)
class SeedValidity:
    """Statistical validity status for experiment results.

    Produced by Stage 12 and consumed by Stage 14 (RESULT_ANALYSIS)
    to emit a limitations paragraph when seeds are insufficient.

    Written to seed_validity.json.
    """

    seeds_run: int = 0
    seeds_required: int = 3
    conditions_affected: tuple[str, ...] = ()
    remediation_attempted: str = "none"
    disclosed: bool = False


@dataclass(frozen=True)
class StageContract:
    stage: Stage
    input_files: tuple[str, ...]
    output_files: tuple[str, ...]
    dod: str
    error_code: str
    max_retries: int = 1
    depends_on: frozenset[Stage] = frozenset()


CONTRACTS: dict[Stage, StageContract] = {
    # Phase A: Research Scoping
    Stage.TOPIC_INIT: StageContract(
        stage=Stage.TOPIC_INIT,
        input_files=(),
        output_files=("goal.md", "hardware_profile.json"),
        dod="SMART goal statement with topic, scope, and constraints",
        error_code="E01_INVALID_GOAL",
        max_retries=0,
        depends_on=frozenset(),
    ),
    Stage.PROBLEM_DECOMPOSE: StageContract(
        stage=Stage.PROBLEM_DECOMPOSE,
        input_files=("goal.md",),
        output_files=("problem_tree.md",),
        dod=">=3 prioritized sub-questions identified",
        error_code="E02_DECOMP_FAIL",
        depends_on=frozenset({Stage.TOPIC_INIT}),
    ),
    # Phase B: Literature Discovery
    Stage.SEARCH_STRATEGY: StageContract(
        stage=Stage.SEARCH_STRATEGY,
        input_files=("problem_tree.md",),
        output_files=("search_plan.yaml", "sources.json", "queries.json"),
        dod=">=2 search strategies defined with verified data sources",
        error_code="E03_STRATEGY_BAD",
        depends_on=frozenset({Stage.PROBLEM_DECOMPOSE}),
    ),
    Stage.LITERATURE_COLLECT: StageContract(
        stage=Stage.LITERATURE_COLLECT,
        input_files=("search_plan.yaml",),
        output_files=("candidates.jsonl",),
        dod=">=N candidate papers collected from specified sources",
        error_code="E04_COLLECT_EMPTY",
        max_retries=2,
        depends_on=frozenset({Stage.SEARCH_STRATEGY}),
    ),
    Stage.LITERATURE_SCREEN: StageContract(
        stage=Stage.LITERATURE_SCREEN,
        input_files=("candidates.jsonl",),
        output_files=("shortlist.jsonl",),
        dod="Relevance + quality dual screening completed and approved",
        error_code="E05_GATE_REJECT",
        max_retries=0,
        depends_on=frozenset({Stage.LITERATURE_COLLECT}),
    ),
    Stage.KNOWLEDGE_EXTRACT: StageContract(
        stage=Stage.KNOWLEDGE_EXTRACT,
        input_files=("shortlist.jsonl",),
        output_files=("cards/",),
        dod="Structured knowledge card per shortlisted paper",
        error_code="E06_EXTRACT_FAIL",
        depends_on=frozenset({Stage.LITERATURE_SCREEN}),
    ),
    # Phase C: Knowledge Synthesis
    Stage.SYNTHESIS: StageContract(
        stage=Stage.SYNTHESIS,
        input_files=("cards/",),
        output_files=("synthesis.md",),
        dod="Topic clusters + >=2 research gaps identified",
        error_code="E07_SYNTHESIS_WEAK",
        depends_on=frozenset({Stage.KNOWLEDGE_EXTRACT}),
    ),
    Stage.HYPOTHESIS_GEN: StageContract(
        stage=Stage.HYPOTHESIS_GEN,
        input_files=("synthesis.md",),
        output_files=("hypotheses.md",),
        dod=">=2 falsifiable research hypotheses",
        error_code="E08_HYP_INVALID",
        depends_on=frozenset({Stage.SYNTHESIS}),
    ),
    # Phase D: Experiment Design
    Stage.EXPERIMENT_DESIGN: StageContract(
        stage=Stage.EXPERIMENT_DESIGN,
        input_files=("hypotheses.md",),
        output_files=("exp_plan.yaml",),
        dod="Experiment plan with baselines, ablations, metrics approved",
        error_code="E09_GATE_REJECT",
        max_retries=0,
        depends_on=frozenset({Stage.HYPOTHESIS_GEN}),
    ),
    Stage.CODE_GENERATION: StageContract(
        stage=Stage.CODE_GENERATION,
        input_files=("exp_plan.yaml",),
        output_files=("experiment/", "experiment_spec.md"),
        dod="Multi-file experiment project + spec document",
        error_code="E10_CODEGEN_FAIL",
        max_retries=2,
        depends_on=frozenset({Stage.EXPERIMENT_DESIGN}),
    ),
    Stage.RESOURCE_PLANNING: StageContract(
        stage=Stage.RESOURCE_PLANNING,
        input_files=("exp_plan.yaml",),
        output_files=("schedule.json",),
        dod="Resource schedule with GPU/time estimates",
        error_code="E11_SCHED_CONFLICT",
        depends_on=frozenset({Stage.EXPERIMENT_DESIGN}),
    ),
    # Phase E: Experiment Execution
    # EXPERIMENT_RUN depends on both CODE_GENERATION and RESOURCE_PLANNING
    Stage.EXPERIMENT_RUN: StageContract(
        stage=Stage.EXPERIMENT_RUN,
        input_files=("schedule.json", "experiment/"),
        output_files=("runs/",),
        dod="All scheduled experiment runs completed with artifacts",
        error_code="E12_RUN_FAIL",
        max_retries=2,
        depends_on=frozenset({Stage.CODE_GENERATION, Stage.RESOURCE_PLANNING}),
    ),
    Stage.ITERATIVE_REFINE: StageContract(
        stage=Stage.ITERATIVE_REFINE,
        input_files=("runs/",),
        output_files=("refinement_log.json", "experiment_final/"),
        dod="Edit-run-eval loop converged or max iterations reached",
        error_code="E13_REFINE_FAIL",
        max_retries=2,
        depends_on=frozenset({Stage.EXPERIMENT_RUN}),
    ),
    # Phase F: Analysis & Decision
    Stage.RESULT_ANALYSIS: StageContract(
        stage=Stage.RESULT_ANALYSIS,
        input_files=("runs/",),
        output_files=("analysis.md",),
        dod="Metrics analyzed with statistical tests and conclusions",
        error_code="E14_ANALYSIS_ERR",
        depends_on=frozenset({Stage.EXPERIMENT_RUN}),
    ),
    Stage.RESEARCH_DECISION: StageContract(
        stage=Stage.RESEARCH_DECISION,
        input_files=("analysis.md",),
        output_files=("decision.md",),
        dod="PROCEED/PIVOT decision with evidence-based justification",
        error_code="E15_DECISION_FAIL",
        depends_on=frozenset({Stage.RESULT_ANALYSIS}),
    ),
    # Phase G: Paper Writing
    Stage.PAPER_OUTLINE: StageContract(
        stage=Stage.PAPER_OUTLINE,
        input_files=("analysis.md", "decision.md"),
        output_files=("outline.md",),
        dod="Complete paper outline with section-level detail",
        error_code="E16_OUTLINE_FAIL",
        depends_on=frozenset({Stage.RESULT_ANALYSIS, Stage.RESEARCH_DECISION}),
    ),
    Stage.PAPER_DRAFT: StageContract(
        stage=Stage.PAPER_DRAFT,
        input_files=("outline.md",),
        output_files=("paper_draft.md",),
        dod="Full paper draft with all sections written",
        error_code="E17_DRAFT_FAIL",
        depends_on=frozenset({Stage.PAPER_OUTLINE}),
    ),
    Stage.PEER_REVIEW: StageContract(
        stage=Stage.PEER_REVIEW,
        input_files=("paper_draft.md",),
        output_files=("reviews.md",),
        dod=">=2 simulated review perspectives with actionable feedback",
        error_code="E18_REVIEW_FAIL",
        depends_on=frozenset({Stage.PAPER_DRAFT}),
    ),
    Stage.PAPER_REVISION: StageContract(
        stage=Stage.PAPER_REVISION,
        input_files=("paper_draft.md", "reviews.md"),
        output_files=("paper_revised.md",),
        dod="All review comments addressed with tracked changes",
        error_code="E19_REVISION_FAIL",
        depends_on=frozenset({Stage.PAPER_DRAFT, Stage.PEER_REVIEW}),
    ),
    # Phase H: Finalization
    Stage.QUALITY_GATE: StageContract(
        stage=Stage.QUALITY_GATE,
        input_files=("paper_revised.md",),
        output_files=("quality_report.json",),
        dod="Quality score meets threshold and approved",
        error_code="E20_GATE_REJECT",
        max_retries=0,
        depends_on=frozenset({Stage.PAPER_REVISION}),
    ),
    Stage.KNOWLEDGE_ARCHIVE: StageContract(
        stage=Stage.KNOWLEDGE_ARCHIVE,
        input_files=(),
        output_files=("archive.md", "bundle_index.json"),
        dod="Retrospective + reproducibility bundle archived",
        error_code="E21_ARCHIVE_FAIL",
        depends_on=frozenset({Stage.QUALITY_GATE}),
    ),
    Stage.EXPORT_PUBLISH: StageContract(
        stage=Stage.EXPORT_PUBLISH,
        input_files=("paper_revised.md",),
        output_files=("paper_final.md", "code/"),
        dod="Final paper exported in target format",
        error_code="E22_EXPORT_FAIL",
        depends_on=frozenset({Stage.PAPER_REVISION}),
    ),
    Stage.CITATION_VERIFY: StageContract(
        stage=Stage.CITATION_VERIFY,
        input_files=("paper_final.md",),
        output_files=("verification_report.json", "references_verified.bib"),
        dod="All citations verified against real APIs; hallucinated refs flagged",
        error_code="E23_VERIFY_FAIL",
        depends_on=frozenset({Stage.EXPORT_PUBLISH}),
    ),
}


def rebuild_from_registry() -> int:
    """Rebuild the CONTRACTS dict from the plugin stage registry.

    Phase 3 Step 8: After all stage_impls modules are imported and their
    ``@register_stage`` decorators have fired, call this to populate
    CONTRACTS from the registry's contract data.

    Returns the number of contracts rebuilt.

    Adding a new stage no longer requires editing this file — the
    decorator in the stage implementation carries the contract inline.
    """
    from berb.pipeline.registry import get_all_registrations

    count = 0
    for stage, reg in get_all_registrations().items():
        if reg.contract is not None:
            CONTRACTS[stage] = reg.contract
            count += 1
    return count
