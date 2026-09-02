---
name: berb-integrity
description: Map of berb/integrity/ — anti-fabrication subsystem: evidence registry, claim manifests, and hidden evaluation. Use when working on claim verification, evidence provenance, integrity gates, or HCE scoring.
---

# berb/integrity

Research-integrity subsystem that prevents AI-fabricated results: every paper claim is extracted into a `ClaimManifest` (persisted as `claim_manifest.json`) and checked against a `VerifiedEvidenceRegistry` (`evidence_registry.json`) of machine-readable provenance records. The `eval/` subpackage adds Hidden Consistent Evaluation (AIRA2-style three-way criteria split). **Mostly wired**: claims/evidence/registry and `eval.hidden_eval` run inside the pipeline. `eval.finding_reproduction` was deleted 2026-09-01 (tasks/ars_integration_plan.md W7) — it was a `random.random()` coin-flip simulation, never real execution, and had no importer.

Note: this file predates several `berb/integrity/` modules added under tasks/ars_integration_plan.md (`findings.py`, `anchors.py`, `uncited.py`, `revision_guard.py`) — the Files table below has not been extended to cover them.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | package exports: `ClaimManifest`, `ClaimRecord`, `ClaimType`, `ClaimVerdict`, `EvidenceRecord`, `EvidenceSource`, `EvidenceType`, `VerifiedEvidenceRegistry` |
| `claims.py` | Claim manifest models: `ClaimType` taxonomy (empirical, comparative, causal, novelty, citation, ...), `ClaimVerdict` (supported/unsupported/...), `ClaimRecord`, `ClaimManifest` with JSON persistence |
| `evidence.py` | Evidence schema: `EvidenceType` (metric, statistical_test, dataset_access, run_config, figure, source_snippet, ...), `EvidenceSource`, `EvidenceRecord`, `make_evidence_id` |
| `registry.py` | `VerifiedEvidenceRegistry` — dict-like store of evidence records; load/save/merge; factory that builds the registry by scanning a run directory |
| `eval/__init__.py` | subpackage marker (import via full module paths) |
| `eval/hidden_eval.py` | `HiddenConsistentEvaluation` (HCE, AIRA2 arXiv:2603.26499) — separate search/selection/test criteria so agents can't hill-climb the eval metric; LLM-scored via `berb.llm.client.get_llm_client`. Scores one paper's overall quality for the pipeline's own search/selection loop — unrelated to reviewer-ensemble recall measurement (W7's `tests/fixtures/seeded_defects.py` corrected an earlier plan mistake conflating the two) |

## Wiring & entry points

- Pipeline: `pipeline/stage_impls/_paper_writing.py` (claim extraction + registry), `_review.py` (ClaimManifest in review gates), `_analysis.py` (evidence registry).
- `review/interrogation.py` uses `ClaimRecord`/`ClaimVerdict`/`VerifiedEvidenceRegistry`; `experiment/split_policy.py` uses `ClaimVerdict`.
- HCE: `experiment/evolutionary_search.py` and `pipeline/optimization_integration/validation_integration.py` import `eval.hidden_eval`.
- Artifacts written per run: `claim_manifest.json`, `evidence_registry.json` (`EVIDENCE_REGISTRY_FILE`).
