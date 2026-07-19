# Berb — Agentic Search & Scientific Rigor Implementation Audit Report

**Document ID:** BERB-AR-001  
**Version:** 1.0  
**Date:** 2026-07-19  
**Reviewer:** Gemini CLI (Interactive Engineering Auditor)  
**Target Commit:** `ffc98eaef0fc6474619ccc659a7b7b615e62f35a` (and top-up commit `fe682ec8692298e16233caebdf20cc6106479817`)  
**Reference Plan:** `scientist_implementation_plan.md`  

---

## 1. Executive Summary

This audit evaluates the codebase changes submitted on the `feature/extended-router-implementation` branch against the approved **Scientist Implementation Plan (`scientist_implementation_plan.md`)**.

The target commits represent the delivery of **Phases 0 & 1** (Truthful Surface and Experiment Journal) along with structural elements of **Phase 2** (Closed-Loop Search).

### Key Accomplishments
1. **Truthful Public Surface (Phase 0):** The dead tree-search stub (`tree_search.py`) was successfully removed from the public API, and zero-importer modules (`tdd_generation.py`, `diff_revisions.py`) were quarantined.
2. **Experiment Journal (Phase 1):** A robust `ExperimentJournal` and `JournalNode` data model were implemented, with ID-based topology tracking to support safe cross-process boundaries.
3. **Budget Governance and Search Runner (Phase 2):** A completely decoupled `SearchRunner` and `BestFirstDiversePolicy` were introduced, establishing clean boundaries between code generation (`CodeAgent`) and sandbox execution.
4. **Per-Run Cost Accounting (Phase 5 - delivered early):** Decoupled `CostTracker` and YAML-based pricing tables were successfully delivered, allowing tracking of actual cost per node, purpose, stage, and phase.

### Critical Concerns
1. **Zero Test Coverage for New Modules:** Over 2,500 lines of complex new code (`journal.py`, `runner.py`, `plot_verdict.py`, `scoring.py`, `cost_tracker.py`) were submitted with **zero new unit or integration tests**. This violates the primary project engineering standards.
2. **Regressions in Existing Tests (3 Failures):** The refactoring and deprecation of `CodeAgent`'s internal tree search broke existing test files. Specifically, `tests/test_code_agent.py` exhibits three failing test cases.
3. **Logic Bug in Policy Debug Depth:** A logical short-circuit was found in `_debug_depth` within `policy.py` due to a premature `break` in a `while` loop, rendering the debug-gating threshold logic ineffective.

---

## 2. Plan Compliance Matrix

[Plan Item | Status | Evidence | Notes]

| Plan Item | Status | Evidence | Notes |
| :--- | :--- | :--- | :--- |
| **F1 — Remove tree-search stub** | **Complete** | Deletion of `berb/research/tree_search.py`; stripped exports in `berb/research/__init__.py`. | No remaining imports or Python-side usages found. Resolves TD-1. |
| **F2 — Ground candidate scoring in the primary metric** | **Complete** | `berb/experiment/search/scoring.py` (`score_node`). | Completely decouples candidate scoring from stdout length, rewarding metric quality. Resolves TD-2. |
| **F3 — Convert seed-count validation warning to mechanism** | **Missing** | No `SeedValidity` model or disclosure path integrated in this branch. | Planned for Phase 3. |
| **F4 — Act on the triviality signal** | **Missing** | `ExecutionFeedback` is defined in `contracts.py` but not wired into the Stage 12/13 loop. | Planned for Phase 2. |
| **F5 — Retire zero-importer modules** | **Complete** | `tdd_generation.py` and `diff_revisions.py` moved to `berb/experimental/`. | Modules and their tests successfully quarantined. Resolves TD-5. |
| **F6 — Rename/redocument evolutionary search** | **Complete** | `DesignProposalEvolver` in `evolutionary_search.py` with deprecation alias. | Docstring clearly states non-execution LLM opinion semantics. `fitness_source` field added. Resolves TD-4. |
| **E1 — `ExperimentJournal` unified attempt tree** | **Complete** | `ExperimentJournal` and `JournalNode` in `berb/experiment/journal.py`. | Supports JSON serialization, tree operations, and `from_legacy_run_dir` synthesis. Resolves TD-3. |
| **E2 — Promote search into the execution stage** | **Complete** | `SearchRunner` (`runner.py`), `SearchConfig` (`policy.py`), Stage 12 wiring (`_execution.py`). | Integrates Stage 12 with search, enabling decoupled evaluations. Master switch in config defaults to False. |
| **E3 — `is_buggy_plots` VLM verdict** | **Complete** | `verify_plots` and `PlotVerdict` in `berb/experiment/plot_verdict.py`. | Capping, anti-hallucination instruction, fail-open, and confidence floor fully implemented. Gated in scoring. |
| **E4 — Staged research escalation** | **Missing** | Not implemented on this branch yet. | Planned for Phase 3. |
| **E5 — Multi-seed evaluation and aggregation** | **Missing** | Not implemented on this branch yet. | Planned for Phase 3. |
| **E6 — Canonical experiment result contract** | **Missing** | No new schema files or strict parsing integrated yet. | Planned for Phase 1. Falls back to legacy stdout parser. |
| **E7 — Evidence-driven writeup reflection** | **Missing** | Not implemented on this branch yet. | Planned for Phase 4. |
| **E8 — Negative-results track** | **Missing** | Not implemented on this branch yet. | Planned for Phase 4. |
| **E9 — Few-shot reviewer calibration** | **Missing** | Not implemented on this branch yet. | Planned for Phase 4. |
| **E10 — Per-run cost and token accounting** | **Complete** | `CostTracker` (`cost_tracker.py`), `PricingTable` (`pricing.py`), and `pricing.yaml`. | Thread-safe, yaml-supported lookup with Python fallback. Attributes per stage/phase/node/purpose. |
| **E11 — Search tree visualization** | **Missing** | Not implemented on this branch yet. | Planned for Phase 5. |

---

## 3. Architecture Compliance Assessment

The implementation demonstrates exceptional compliance with Clean Architecture boundaries and project style guidelines:

*   **Boundary Separation (Correction of V-1):** The implementation successfully shifts execution-level logic out of the `CodeAgent` (generation) into the Stage 12 pipeline execution utilizing `SearchRunner`. Decoupling these concerns makes both code generation and search selection independently testable.
*   **Dependency Direction:** Follows the standard direction: `interfaces` → `pipeline` → `subsystems` → `config`. Core search logic is independent of specific I/O and LLM providers.
*   **SOLID Principles:**
    *   **S:** Decoupled scoring (`scoring.py`), policy (`policy.py`), and tracking (`cost_tracker.py`) have a single well-defined responsibility.
    *   **O/D:** `SearchRunner` depends on the `SearchPolicy` Protocol rather than concrete classes, allowing new selection policies to be plugged in easily.
    *   **L:** `BestFirstDiversePolicy` is fully substitutable for `SearchPolicy`.
*   **Security Invariant:** Evaluated candidates are correctly routed through the sandbox factory (`create_sandbox`), preventing raw subprocess execution on the host and safeguarding system integrity.
*   **Backward Compatibility:** Preserves single-run logic if `search.enabled` is `False`. Legacy run files (e.g. `run-1.json`, `run-2.json`) are written for downstream stage compatibility even when search is active.

---

## 4. Code Quality Findings

### Q-01: Premature Loop Break in `_debug_depth` Helper
*   **Location:** `berb/experiment/search/policy.py:214-223` (`_debug_depth`)
*   **Description:** The function is written to compute how many ancestors of a given node have `origin == "debug"`. However, the `while` loop has a premature `break` at the end of its first iteration. It also lacks a reference to `journal` or another lookup mechanism to retrieve the parent node from its `parent_id`.
*   **Impact:** Medium. Since it only inspects the target node, it returns either `0` or `1` and fails to traverse the tree hierarchy. This breaks the debug-gating threshold rule (`_debug_depth(l) < config.max_debug_depth`) for deep branches.
*   **Code Evidence:**
    ```python
    def _debug_depth(node: JournalNode) -> int:
        """Count how many times this node has been debugged/repaired."""
        debug_count = 0
        current = node
        while current is not None:
            if current.origin == "debug":
                debug_count += 1
            # For depth counting, we just look at the node's own depth
            # and how many ancestors have origin=debug
            break # Premature break prevents looping!
        return debug_count
    ```

### Q-02: Loss vs. Accuracy Ambiguity on Scoring Baseline
*   **Location:** `berb/experiment/search/scoring.py:126-131`
*   **Description:** When the `baseline` is supplied but there is no `cohort`, the primary metric normalization behaves differently. If `maximize=False`, the normalized value is `baseline / metric_value`. This can result in values exceeding `1.0` if `metric_value < baseline`, but is capped to `1.0` on line 133.
*   **Impact:** Low. Robustness is maintained by min-max capping on line 133, but the cohort-relative min-max path should be preferred for most searches.

---

## 5. Testing & Coverage Assessment

The testing posture of this submission is **inadequate** and represents a major regression in engineering standards:

1.  **Zero Tests for New Core Features:**
    The submission introduces massive files with complex logic:
    *   `journal.py` (587 lines) - 0% coverage.
    *   `runner.py` (450 lines) - 0% coverage.
    *   `policy.py` (222 lines) - 0% coverage.
    *   `scoring.py` (271 lines) - 0% coverage.
    *   `plot_verdict.py` (250 lines) - 0% coverage.
    *   `cost_tracker.py` (275 lines) - 0% coverage.
    
    No unit tests, property tests, or mock-sandbox integration tests were added in the target commit.

2.  **Existing CodeAgent Test Failures (Regressions):**
    The refactoring in `CodeAgent` broke three existing tests in `tests/test_code_agent.py`:
    *   `TestPhase3TreeSearch.test_tree_search_generates_multiple_candidates` (**FAILED**): Fails because `tree_nodes_explored` returns `0` due to deprecation of the `CodeAgent._phase3_tree_search` implementation.
    *   `TestPhase3TreeSearch.test_tree_search_fixes_crashing_candidates` (**FAILED**): Fails due to the same `CodeAgent` internal tree search deprecation.
    *   `TestSolutionNodeScoring.test_score_partial_output` (**FAILED**): Fails because `CodeAgent._score_node` (shim) delegates to `new_score_node` which returns `0.0` for runs with no metrics, while the old heuristic returned `1.0` solely for `runs_ok`.

---

## 6. Risk & Regression Analysis

### R-01: Execution without Verification
Deploying a major parallel tree search and budget governor without a deterministic mock-sandbox unit test suite poses a high risk of execution stalls, budget leaks, and search loop deadlocks. A parallel worker race condition or a deadlock in `asyncio.Semaphore` could easily go undetected.

### R-02: Decoupled Scoring Range Discrepancies
The delegation of `_score_node` to `new_score_node` modifies the scoring ranges of legacy components. This is what caused the failure in `test_score_partial_output`. Downstream stages or integration components that rely on specific metric score thresholds could behave unexpectedly when receiving `0.0` instead of `1.0` for non-metric runs.

### R-03: Debug Loop Inefficiency
Due to Q-01, the system will not correctly track the depth of debugging iterations. It may either debug forever (bypassing the safety depth gate) or prune repair opportunities prematurely, reducing overall experimental search success.

---

## 7. Required Corrections

[Severity | File | Issue | Recommendation]

| Severity | File | Issue | Recommendation |
| :--- | :--- | :--- | :--- |
| **High** | `tests/` | Complete absence of automated tests for new components. | Author a dedicated test suite (e.g. `tests/test_search_runner.py`, `tests/test_experiment_journal.py`, `tests/test_plot_verdict.py`, and `tests/test_cost_tracker.py`) verifying lossless JSON serialization, min-max scoring, diversity selection, and budget governor stopping. |
| **High** | `tests/test_code_agent.py` | Regressions in existing tests (`test_tree_search_generates_multiple_candidates`, `test_tree_search_fixes_crashing_candidates`, `test_score_partial_output`). | Refactor or mock these tests. Update the scoring assertion to match the new delegated `score_node` behaviors, and mock/re-route the tree-search expectations to the new Stage 12 execution context. |
| **Medium** | `berb/experiment/search/policy.py` | premature `break` and lack of journal/parent-lookup in `_debug_depth` helper. | Refactor `_debug_depth` to take `journal` and recursively traverse up the `parent_id` chain to correctly calculate debugging depth. Remove the premature `break` statement. |

---

## 8. Final Verdict

### APPROVED WITH CHANGES ⚠️

**Rationale:**  
The implementation is architecturally superb, exceptionally clean, and strictly conforms to the DRY, SOLID, and separation-of-concerns principles laid out in the plan. It solves the core problem of decoupling the execution and generation stages (remedying V-1) and provides a strong foundation for closed-loop, metric-grounded search.

However, the complete absence of unit test coverage for the newly submitted modules and the three test failures in `test_code_agent.py` represent a critical regression in our technical standards. Once the required corrections (test coverage, regression resolution, and the `_debug_depth` fix) are applied, this branch will be in a state of high readiness for main integration.
