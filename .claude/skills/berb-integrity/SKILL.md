---
name: berb-integrity
description: Map of berb/integrity/ — anti-fabrication subsystem: evidence registry, claim manifests, and hidden evaluation. Use when working on claim verification, evidence provenance, integrity gates, or HCE scoring.
---

# berb/integrity

Research-integrity subsystem that prevents AI-fabricated results: every paper claim is extracted into a `ClaimManifest` (persisted as `claim_manifest.json`) and checked against a `VerifiedEvidenceRegistry` (`evidence_registry.json`) of machine-readable provenance records. The `eval/` subpackage adds Hidden Consistent Evaluation (AIRA2-style three-way criteria split) and finding reproduction. **Mostly wired**: claims/evidence/registry and `eval.hidden_eval` run inside the pipeline; `eval.finding_reproduction` is **unwired/dormant** (no importer anywhere).

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | package exports: `ClaimManifest`, `ClaimRecord`, `ClaimType`, `ClaimVerdict`, `EvidenceRecord`, `EvidenceSource`, `EvidenceType`, `VerifiedEvidenceRegistry` |
| `claims.py` | Claim manifest models: `ClaimType` taxonomy (empirical, comparative, causal, novelty, citation, ...), `ClaimVerdict` (supported/unsupported/...), `ClaimRecord`, `ClaimManifest` with JSON persistence |
| `evidence.py` | Evidence schema: `EvidenceType` (metric, statistical_test, dataset_access, run_config, figure, source_snippet, ...), `EvidenceSource`, `EvidenceRecord`, `make_evidence_id` |
| `registry.py` | `VerifiedEvidenceRegistry` — dict-like store of evidence records; load/save/merge; factory that builds the registry by scanning a run directory |
| `eval/__init__.py` | subpackage marker (import via full module paths) |
| `eval/hidden_eval.py` | `HiddenConsistentEvaluation` (HCE, AIRA2 arXiv:2603.26499) — separate search/selection/test criteria so agents can't hill-climb the eval metric; LLM-scored via `berb.llm.client.get_llm_client` |
| `eval/finding_reproduction.py` | `FindingReproducer` — reproduce known scientific findings as validation benchmarks (Edison Scientific style). **Unwired** — no importer |

## Wiring & entry points

- Pipeline: `pipeline/stage_impls/_paper_writing.py` (claim extraction + registry), `_review.py` (ClaimManifest in review gates), `_analysis.py` (evidence registry).
- `review/interrogation.py` uses `ClaimRecord`/`ClaimVerdict`/`VerifiedEvidenceRegistry`; `experiment/split_policy.py` uses `ClaimVerdict`.
- HCE: `experiment/evolutionary_search.py` and `pipeline/optimization_integration/validation_integration.py` import `eval.hidden_eval`.
- `eval.finding_reproduction` has **no importer** — dormant (CLAUDE.md confirms).
- Artifacts written per run: `claim_manifest.json`, `evidence_registry.json` (`EVIDENCE_REGISTRY_FILE`).
