# Berb Research Integrity Implementation Plan

## 1. Executive Summary

Berb already contains several strong anti-fabrication primitives: a 23-stage event-sourced research pipeline, deterministic numeric verification through `VerifiedRegistry` and `paper_verifier.py`, citation verification at Stage 23, manuscript self-checking, claim confidence checks, source alignment checks, sandboxed experiment execution, and reproducibility artifacts. The current architecture is therefore a good base for preventing AI-generated research fabrication.

The main gap is that integrity controls are not yet unified around a single provenance contract. Numeric values are strongly protected, but prose claims, dataset-access claims, citation-support claims, statistical claims, figure references, and rewrite drift are handled by a mix of prompts, heuristics, and late-stage checks. The planned upgrade moves Berb from "prompt the model not to fabricate" to "only publish facts that can be traced to registered evidence."

The recommended implementation is an evidence-first integrity subsystem:

- Add a `VerifiedEvidenceRegistry` and per-run `evidence_registry.json`.
- Require claim-level provenance through a `claim_manifest.json`.
- Extend `paper_verifier.py` from numeric verification to full claim, dataset, method, statistic, figure, and citation-support verification.
- Make strict research-integrity mode fail closed for high-risk domains and submission outputs.
- Run verification after every write or rewrite stage.
- Improve source grounding from metadata and keyword overlap to snippet-backed claim-citation alignment.
- Add targeted regression tests for fake datasets, fake p-values, fake baselines, unsupported citations, and rewrite drift.

The plan below is phased to preserve backward compatibility. Draft mode remains permissive while submission/strict mode becomes fail-closed.

## 2. Current Architecture Assessment

### 2.1 Pipeline Architecture

Berb is organized around a 23-stage research pipeline defined in `berb/pipeline/stages.py` and `berb/pipeline/contracts.py`. Stage implementations live under `berb/pipeline/stage_impls/`. The pipeline spans scoping, literature discovery, synthesis, experiment design, code generation, experiment execution, analysis, paper drafting, peer review, revision, quality gate, export, and citation verification.

Current strengths:

- Explicit stage contracts with input/output artifacts and definitions of done.
- Event-sourced state machine and checkpoint/resume support.
- Modular stage registration through decorators.
- Separate modules for literature, experiment, writing, validation, export, audit, and web integrations.
- Critical final citation verification stage.
- Deterministic numeric verification through `VerifiedRegistry` and `paper_verifier.py`.
- Existing tests for paper verifier, citation verification, checkpoint behavior, and stage ordering.

Current limitations:

- Integrity evidence is distributed across artifacts rather than normalized into one registry.
- Stage 17 paper drafting consumes evidence mostly through prompt context, not through a strict machine-readable claim contract.
- Claim extraction and source alignment are mostly heuristic and can miss or misclassify claims.
- Citation verification proves source existence better than source support for each sentence.
- Some fallback paths preserve unverified content to avoid breaking output.
- Verification is strongest after export, but rewrites and polishing can alter claims before final checks.

### 2.2 Module Boundaries

Relevant modules and boundaries:

- `berb/pipeline/`: orchestration, stage implementations, verification gates, artifacts, pipeline state.
- `berb/pipeline/verified_registry.py`: verified numeric values, condition names, training configuration.
- `berb/pipeline/paper_verifier.py`: deterministic post-generation numeric and condition checks.
- `berb/pipeline/citation_verification.py`: layered citation format/API/info/content/web checks.
- `berb/pipeline/hallucination_detector.py`: final paper hallucination scan.
- `berb/validation/`: claim confidence, source alignment, manuscript self-check, reference integrity.
- `berb/literature/`: candidate collection, citation verification, source search.
- `berb/writing/`: drafting, source writing, citation engine, style and anti-AI polishing.
- `berb/experiment/`: execution and sandboxing.
- `berb/audit/`: reproducibility bundle and audit trail.

Recommended boundary adjustment:

- Add an integrity service layer under `berb/integrity/` or `berb/validation/integrity/`.
- Keep deterministic registries free of LLM dependencies.
- Keep LLM-based claim classification behind replaceable interfaces.
- Make stage implementations call a small set of integrity APIs instead of embedding verification logic directly.

### 2.3 Data Flow

Current data flow:

1. Literature stages collect candidates and knowledge cards.
2. Experiment stages generate code, execute runs, and produce summaries/refinement logs.
3. Analysis stages produce conclusions.
4. Writing stages draft/revise the paper from prompts and artifacts.
5. Export/finalization stages verify citations and package outputs.

Target data flow:

1. Evidence-producing stages append structured evidence records.
2. Writing stages consume only approved evidence records for empirical claims.
3. Drafting emits `claim_manifest.json` alongside prose.
4. Verification gates compare the manuscript against evidence and claim manifests.
5. Exported outputs include integrity reports and provenance appendix artifacts.

### 2.4 Dependencies

Runtime dependencies are mainly Python libraries such as Pydantic, httpx, numpy, rich, PyYAML, optional LLM SDKs, PyMuPDF, search/crawl libraries, and scientific tooling. The proposed plan can be implemented mostly with existing dependencies.

Potential new dependencies should be avoided initially. If semantic sentence classification requires model assistance, use the existing LLM abstraction. For deterministic parsing, use standard library regex, Pydantic models, and existing artifact formats.

### 2.5 Scalability and Maintainability

Scalability risks:

- Verifying every claim against every source can become expensive.
- Full-text citation alignment may require many API calls.
- Re-verification after every rewrite can duplicate work.

Mitigations:

- Cache evidence IDs and claim-verification results by content hash.
- Verify changed claims only after rewrites.
- Batch LLM checks.
- Use deterministic checks first and LLM checks only for ambiguous support.
- Store normalized source snippets during literature collection to avoid repeated fetches.

Maintainability risks:

- Integrity logic is currently spread across several modules.
- Stage implementations are already long and complex.

Mitigations:

- Add a cohesive integrity API with stable Pydantic schemas.
- Keep stage code limited to loading artifacts, invoking integrity services, and writing reports.
- Add focused unit tests for each verifier.

### 2.6 Security and Technical Debt

Security considerations:

- Source fetching must continue to respect SSRF protections and existing web client safeguards.
- Evidence registries must not leak API keys, tokens, proprietary data, or patient data.
- Dataset-access records should store metadata/provenance, not raw sensitive records.
- Strict mode should refuse to publish unsupported biomedical/clinical/legal/financial claims.

Technical debt addressed:

- Prompt-only data integrity instructions.
- Heuristic claim extraction.
- Late-stage-only verification.
- Citation existence checks not always tied to claim support.
- Fallback paths that prioritize output continuity over integrity.

## 3. Target Architecture

### 3.1 New Integrity Subsystem

Add a new package:

```text
berb/integrity/
  __init__.py
  evidence.py
  claims.py
  registry.py
  verifier.py
  gates.py
  drift.py
  reports.py
  source_support.py
```

Responsibilities:

- `evidence.py`: Pydantic models for evidence records.
- `claims.py`: claim models, claim type classifier interface, extraction helpers.
- `registry.py`: `VerifiedEvidenceRegistry`, load/save/merge APIs.
- `verifier.py`: deterministic and hybrid claim verification.
- `gates.py`: strict/draft/submission gate policy.
- `drift.py`: rewrite drift detection.
- `reports.py`: integrity score and provenance appendix generation.
- `source_support.py`: source snippet alignment and citation-support verdicts.

### 3.2 Core Artifacts

Add these run artifacts:

- `evidence_registry.json`: all verified evidence records.
- `claim_manifest.json`: claims in the paper and their evidence links.
- `integrity_report.json`: pass/fail, issue list, scores, and recommendations.
- `provenance_appendix.md`: human-readable provenance appendix.
- `source_snippets.jsonl`: normalized support snippets from literature sources.
- `rewrite_drift_report.json`: changes introduced during revision/polishing/export.

### 3.3 Evidence Types

Initial evidence types:

- `metric`: numeric result from experiment artifacts.
- `statistical_test`: p-value, confidence interval, test name, effect size.
- `dataset_access`: dataset/database acquisition and access metadata.
- `method_implementation`: methods/baselines/ablations actually implemented.
- `run_config`: seeds, trial count, hyperparameters, hardware, training config.
- `figure`: generated figure/table with data/script provenance.
- `source_snippet`: literature excerpt supporting a claim.
- `analysis_finding`: derived finding from Stage 14 analysis.
- `limitation`: explicitly registered limitation or negative result.

### 3.4 Gate Policy

Add config:

```yaml
integrity:
  mode: draft        # draft | submission | strict
  fail_on_unsupported_claims: true
  fail_on_unverified_statistics: true
  fail_on_citation_fallback: true
  require_source_snippets: true
  auto_strict_domains:
    - biomedical
    - clinical
    - legal
    - finance
    - policy
```

Mode behavior:

- `draft`: warn and annotate.
- `submission`: fail on critical integrity issues.
- `strict`: fail closed; no unverified empirical/comparative/causal/novelty claims.

## 4. Detailed Implementation Plan

### Phase 0: Baseline and Safety Net

Milestone: establish current behavior and regression fixtures before changing gates.

Tasks:

- Inventory current integrity checks and artifact paths.
- Add fixtures for fabricated datasets, fake p-values, fake baselines, unsupported citations, and rewrite drift.
- Snapshot current Stage 17, Stage 20, Stage 22, and Stage 23 behavior.
- Add `integrity.mode` config parsing with no behavior change initially.

Dependencies:

- Existing tests under `tests/test_paper_verifier.py`, `tests/test_berb_citation_verify.py`, and `tests/test_berb_executor.py`.

Acceptance criteria:

- New config loads with defaults.
- Existing tests remain green.
- Negative fixtures exist but may initially be marked xfail where functionality is not implemented.

### Phase 1: Evidence Registry Foundation

Milestone: create a machine-readable registry for all non-numeric provenance.

Tasks:

- Add Pydantic models for `EvidenceRecord`, `EvidenceType`, `EvidenceSource`, and `EvidenceRegistryReport`.
- Add `VerifiedEvidenceRegistry` with `add_record`, `lookup`, `verify`, `save`, `load`, `merge`, and `from_run_dir`.
- Extend `VerifiedRegistry` or add adapters so numeric values can be exposed as evidence records.
- Emit `evidence_registry.json` from experiment, literature, analysis, and figure stages.

Acceptance criteria:

- A full run produces `evidence_registry.json`.
- Numeric values in `VerifiedRegistry` are mirrored with source artifact paths.
- No LLM dependency is required to build the registry.

### Phase 2: Claim Manifest and Drafting Contract

Milestone: Stage 17 emits claims linked to evidence.

Tasks:

- Add `ClaimRecord` and `ClaimManifest` models.
- Implement deterministic sentence extraction and claim classification.
- Add optional LLM classifier behind the existing LLM client for ambiguous claim types.
- Modify Stage 17 to write `claim_manifest.json`.
- Modify paper-writing prompts to require evidence IDs for empirical/comparative/causal/novelty claims.
- Validate that every generated result sentence can be traced to registry evidence.

Acceptance criteria:

- Stage 17 outputs `paper_draft.md` and `claim_manifest.json`.
- Claims with numbers reference verified numeric evidence.
- Claims about methods/baselines/datasets reference non-numeric evidence.

### Phase 3: Deterministic Integrity Gate Expansion

Milestone: extend `paper_verifier.py` into a broader deterministic verifier.

Tasks:

- Add checks for dataset/database claims.
- Add checks for baselines, ablations, methods, sample sizes, trial counts, seeds, hardware, and training claims.
- Add checks for statistical tests, p-values, confidence intervals, and significance language.
- Add checks for invented figures and tables.
- Add strict/draft/submission policy handling.

Acceptance criteria:

- Fake p-values fail in submission/strict mode.
- Fake dataset-access claims fail in submission/strict mode.
- Fake baseline and ablation claims fail in submission/strict mode.
- Draft mode annotates issues without blocking.

### Phase 4: Citation and Source Support Grounding

Milestone: citations prove sentence support, not just source existence.

Tasks:

- Store source snippets during literature collection and knowledge extraction.
- Link source snippets to evidence records.
- Replace source-alignment keyword overlap with a snippet-backed support verdict.
- Add citation-use records for each in-text citation.
- Make Stage 23 fail closed in strict mode when verification strips too many citations.
- Remove or gate the bibliography restoration fallback.

Acceptance criteria:

- A real citation that does not support the sentence is flagged.
- A missing or hallucinated citation blocks strict/submission finalization.
- `references_verified.bib` never silently restores unverified entries in strict mode.

### Phase 5: Rewrite Drift and Multi-Pass Verification

Milestone: verification runs after every transformation that can alter claims.

Tasks:

- Add rewrite drift detection for numbers, method names, comparisons, significance claims, limitations, citations, and dataset references.
- Run integrity checks after draft, revision, anti-AI/style polishing, LaTeX conversion, export, and final citation verification.
- Cache claim hashes so unchanged claims are not rechecked.
- Write `rewrite_drift_report.json`.

Acceptance criteria:

- If revision changes "A outperforms B" to "B outperforms A" without evidence, the run fails in strict/submission mode.
- If style polishing changes a number, the run fails in strict/submission mode.
- Drift reports identify the source and target stages.

### Phase 6: Observability, CLI/API, and Reports

Milestone: integrity failures are visible and actionable.

Tasks:

- Add integrity metrics to run summary.
- Add CLI output for failed claims and missing evidence.
- Add API fields for integrity status and report artifacts.
- Generate `provenance_appendix.md`.
- Update docs and example configs.

Acceptance criteria:

- Users can see which claim failed, where it appears, and what evidence is missing.
- Run summary includes claim counts, citation alignment rate, unverified numbers, fabricated condition count, and integrity pass/fail.

### Phase 7: Strict Domain Defaults and CI Hardening

Milestone: high-risk domains get safer defaults.

Tasks:

- Auto-enable strict mode for biomedical, clinical, legal, financial, and policy topics.
- Prevent `--skip-noncritical-stage` from bypassing integrity-critical stages in strict mode.
- Add CI jobs for integrity tests.
- Add documentation for draft vs submission vs strict mode.

Acceptance criteria:

- Biomedical topics default to strict mode.
- Integrity-critical failures cannot be skipped in strict mode.
- CI rejects regressions in anti-fabrication tests.

## 5. Impact Assessment

| Area | Impact | Affected Components |
|---|---|---|
| Pipeline contracts | New artifacts and possible new stage outputs | `berb/pipeline/contracts.py`, stage decorators |
| Stage 4-6 literature | Source snippets and evidence records | `berb/literature/*`, `berb/pipeline/stage_impls/_literature.py` |
| Stage 12-14 experiments | Metrics, config, statistics, figure provenance | `berb/experiment/*`, `berb/pipeline/stage_impls/_execution.py`, `_analysis.py` |
| Stage 17 writing | Claim manifest and evidence ID constraints | `berb/pipeline/stage_impls/_paper_writing.py`, `prompts.default.yaml` |
| Stage 19 revision | Rewrite drift and re-verification | `berb/pipeline/stage_impls/_review_publish.py` |
| Stage 20 quality | Integrity score and hard fail policy | `berb/pipeline/stage_impls/_review_publish.py` |
| Stage 22 export | Final paper, figure/table provenance, LaTeX checks | `berb/export/*`, `berb/templates/*`, `_review_publish.py` |
| Stage 23 citation verify | Fail-closed citation and support checks | `berb/pipeline/citation_verification.py`, `berb/literature/verify.py` |
| Validation modules | Claim classification, source support verdicts | `berb/validation/*`, new `berb/integrity/*` |
| CLI/API | Integrity config and report exposure | `berb/cli.py`, `berb/api/server.py`, `berb/config.py` |
| Tests | New negative and integration tests | `tests/test_*integrity*.py`, existing verifier tests |
| Deployment | No infrastructure migration required initially | CI config, docs, optional API fields |

## 6. Task Breakdown Structure

The rows below map the requested additions, enhancements, and fixes to implementation work. "Rollback" means the lowest-risk fallback if the change causes regressions.

| ID | Objective | Affected Components | Design and Implementation Tasks | Testing Strategy | Acceptance Criteria | Rollback Strategy |
|---|---|---|---|---|---|---|
| 1 | Add `VerifiedEvidenceRegistry` | New `berb/integrity/registry.py`, validation modules | Define evidence models, load/save/merge APIs, source artifact references | Unit tests for add/load/merge/lookup | Registry persists and reloads records deterministically | Feature flag registry writes off |
| 2 | Extend numeric registry metadata | `verified_registry.py` | Add metric name, condition, run ID, seed, artifact path, source kind | Unit tests with experiment summaries and refinement logs | Lookup returns value and provenance | Keep existing `values` map as compatibility path |
| 3 | Create `evidence_registry.json` per run | Stage 4-23 implementations | Add append/merge helper and stage calls | Integration test synthetic run | Run directory contains valid registry JSON | Stop writing registry but preserve stage behavior |
| 4 | Require claim-level provenance in drafting | Stage 17, prompts, new claims module | Draft emits evidence IDs for supported claims | Stage 17 tests with fake LLM output | Claims without IDs are flagged | Disable hard gate, keep manifest as warning |
| 5 | Add `claim_manifest.json` | Stage 17, Stage 19, Stage 22 | Define schema and writer/loader | Schema and integration tests | Manifest exists for drafts and final papers | Keep manifest optional in draft mode |
| 6 | Upgrade claim extraction | `claims.py`, `claim_confidence.py` | Sentence parser, claim type classifier, optional LLM classifier | Unit tests by claim type | Empirical/comparative/causal/novelty claims are detected | Fall back to existing keyword extractor |
| 7 | Hard gate unsupported claims | `gates.py`, Stage 20/22/23 | Add gate policy and failure result | Negative integration tests | Unsupported critical claims fail strict/submission mode | Config downgrade to draft mode |
| 8 | Extend `paper_verifier.py` | `paper_verifier.py`, new registry adapters | Add dataset, baseline, statistic, figure, hardware checks | Negative tests for each fake claim category | Fabricated non-numeric claims are rejected | Disable individual verifier rules by config |
| 9 | Verify statistical claims | Stage 14, verifier | Register tests, p-values, CIs, effect sizes from analysis artifacts | Tests for fake and real p-values | Significance claims require registered statistic evidence | Warn-only in draft mode |
| 10 | Dataset-access verification | Literature/data acquisition, verifier | Register dataset/database access records and license notes | Tests for MarketScan-style fake claim | Dataset claim fails without access record | Allow "planned dataset" label in draft mode |
| 11 | Make citation fallback fail closed | Stage 23 | Replace bibliography restore with mode-aware fail/quarantine | Stage 23 tests for mass stripping | Strict mode never restores unverified bib silently | Keep old fallback only in draft mode |
| 12 | Verify citation support using snippets | Literature, source support, citation verifier | Store snippets and align each citation use | Tests for real citation/unsupported sentence | Topical but unsupported citation is flagged | Fall back to metadata-only with warning |
| 13 | Store source snippets | Literature collect/extract | Persist `source_snippets.jsonl` with section/page/source URL | Fixture tests for snippet schema | Snippets load into evidence registry | Store abstracts only if full text unavailable |
| 14 | Add citation-claim alignment scoring | Source support module | Verdict enum: direct, partial, background, contradicts, unrelated, unknown | Unit tests for verdict thresholds | Each citation use has a support verdict | Report only, no gate in draft mode |
| 15 | Block mismatched citations | Stage 20/23 gates | Fail or rewrite sentence when citation is unrelated/contradictory | Negative citation tests | Mismatched citations cannot pass strict mode | Allow manual override artifact |
| 16 | Verify after every rewrite | Stage 17/19/22/23 | Add verification hook after draft, revision, polish, export | Integration tests with altered claim | Final report shows each verification pass | Run only final verification if disabled |
| 17 | Protect against rewrite drift | `drift.py`, Stage 19/22 | Semantic and deterministic diff of claims, numbers, citation placement | Tests for number and direction changes | Unsupported drift fails strict mode | Drift check warn-only |
| 18 | Add strict integrity mode | Config, gates, CLI | Add config schema and policy resolution | Config tests | `integrity.mode: strict` changes gates to fail closed | Default remains draft/submission as configured |
| 19 | Auto-strict high-risk domains | Domain detector, config | Map detected domains to strict mode | Domain tests | Biomedical/clinical/legal/finance/policy topics strict by default | Allow explicit config override |
| 20 | Improve manuscript self-check | `manuscript_self_check.py` | Consume claim manifest and evidence registry | Unit tests comparing manifest-based checks | Self-check no longer relies only on text patterns | Keep heuristic path if manifest missing |
| 21 | Improve source alignment | `source_alignment.py`, `source_support.py` | Replace overlap-only scoring with snippet and verdict pipeline | Alignment fixtures | Conservative `cannot_determine` on weak evidence | Existing overlap checker remains fallback |
| 22 | Add provenance appendix | Reports, export | Generate markdown appendix from registries and reports | Snapshot tests | Appendix lists claims, metrics, sources, hashes | Generate as optional artifact only |
| 23 | Figure/table provenance | Figure agent, export, verifier | Register data file, script, source metrics, timestamp | Tests with generated and missing figures | Each figure/table has provenance | Warn if missing in draft mode |
| 24 | Detect invented figure references | Export verifier | Parse Figure/Table refs and validate artifacts | Tests for missing Figure 3/Table 2 | Invented refs fail strict mode | Convert to warning in draft mode |
| 25 | Add negative regression tests | Tests | Add fake p-value, fake dataset, fake baseline, fake citation, rewrite drift tests | CI test suite | All anti-fabrication regressions are covered | Mark slow LLM tests optional |
| 26 | Add integrity score to summary | `summary.py`, API, CLI | Aggregate claim/citation/number/condition metrics | Summary tests | Run summary exposes integrity pass/fail and counts | Keep old summary fields unchanged |
| 27 | Expose clear failures | CLI/API/logging | Add issue formatting with claim, location, evidence gap | CLI/API tests | Failure messages identify exact claim and missing evidence | Write report artifact even if CLI formatting fails |
| 28 | Separate draft/submission modes | Config, gates, CLI | Add policy matrix for warnings vs failures | Config and integration tests | Draft allows warnings, submission blocks critical issues | Default to draft for backward compatibility |
| 29 | Prevent LLM-generated references everywhere | Stage 17/19/22 | Strip generated references after draft/revision/export | Tests with generated References section | LLM cannot add final references outside verified bib | Keep stripped content in internal notes |
| 30 | Audit fallback paths | Stage impls, verifiers | Identify fallbacks and make integrity-sensitive fallbacks mode-aware | Regression tests for fallbacks | Strict mode fails/quarantines instead of silently preserving unverified content | Keep old behavior in draft mode |

## 7. Risk and Mitigation Matrix

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| False positives block valid papers | Medium | High | Start with draft warnings, add strict mode opt-in, allow documented manual overrides |
| Source snippets unavailable for paywalled literature | High | Medium | Use abstracts as weaker evidence, mark support as partial/cannot-determine, do not fabricate full-text support |
| LLM-based claim classifier is inconsistent | Medium | Medium | Deterministic extraction first, cache classifier results by hash, keep conservative defaults |
| Runtime and API cost increase | Medium | Medium | Batch checks, cache by claim/source hash, skip unchanged claims after rewrites |
| Backward compatibility breaks existing runs | Medium | High | Add new artifacts without changing old outputs first, gate strict behavior by config |
| Stage implementations become more complex | High | Medium | Centralize logic in `berb/integrity/`, keep stages as orchestration adapters |
| Sensitive data leaks into provenance appendix | Low | High | Store metadata and hashes, redact secrets/PHI, use existing sanitization utilities |
| Citation verification rate limits cause failures | Medium | Medium | Cache API results, support skipped/unavailable statuses, only fail strict mode on true hallucination or unsupported claim |
| Strict defaults surprise users | Medium | Medium | Log mode selection clearly, document overrides, show domain detection rationale |
| Manual overrides are abused | Medium | High | Require override reason, author, timestamp, and affected claim IDs in audit trail |

## 8. Testing and Quality Assurance Strategy

### 8.1 Unit Tests

Add focused tests for:

- Evidence registry model validation and merge behavior.
- Numeric registry provenance metadata.
- Claim type extraction and classification.
- Dataset/database claim detection.
- Baseline and ablation verification.
- Statistical claim verification.
- Figure/table reference detection.
- Source snippet support verdicts.
- Gate policy behavior across draft/submission/strict modes.

### 8.2 Integration Tests

Add synthetic run directories with:

- Valid experiment metrics and matching paper claims.
- Fake trial counts.
- Fake p-values and fake confidence intervals.
- Fake baselines not present in run artifacts.
- Fake dataset/database claims.
- Real citation with unsupported claim.
- Rewritten number after polishing.
- Missing figure/table reference.

### 8.3 Regression Tests

Promote the most important negative cases into CI:

- `test_integrity_fake_p_value_rejected`
- `test_integrity_fake_dataset_rejected`
- `test_integrity_fake_baseline_rejected`
- `test_integrity_unsupported_citation_rejected`
- `test_integrity_rewrite_drift_rejected`
- `test_integrity_draft_mode_warns`
- `test_integrity_strict_mode_fails_closed`

### 8.4 Property and Fuzz Tests

Use lightweight fuzzing for:

- Numeric extraction with LaTeX commands.
- Citation parsing with multi-key citations.
- Figure/table reference parsing.
- Claim manifest load/save round trips.

### 8.5 Manual QA

Manual review scenarios:

- Biomedical topic defaults to strict mode.
- Non-high-risk topic remains configurable.
- A valid paper with partial source snippets produces warnings, not false critical failures in draft mode.
- A submission build with unsupported claims fails with actionable messages.

### 8.6 Quality Gates

CI should run:

- `pytest tests/test_paper_verifier.py`
- new integrity unit tests
- citation verifier tests
- stage contract tests
- config tests
- targeted pipeline integration tests

Optional slow CI:

- live citation API verification
- LLM-backed claim support checks
- full end-to-end run in draft mode

## 9. Engineering Practices

### SOLID and Clean Architecture

- Use single-purpose services: registry, claim extraction, support verification, gate policy, report generation.
- Depend on interfaces for LLM and source clients.
- Keep deterministic verification independent from model providers.
- Keep stage implementations thin.

### Separation of Concerns

- Evidence production belongs in literature, experiment, analysis, and figure stages.
- Evidence validation belongs in integrity services.
- Paper generation consumes evidence but does not certify it.
- Export packages reports but does not invent verification state.

### DRY, KISS, and YAGNI

- Reuse `VerifiedRegistry` for numeric values instead of duplicating numeric logic.
- Add a minimal evidence schema first.
- Avoid adding new infrastructure or databases until JSON artifacts become insufficient.
- Do not introduce a new ML dependency for claim classification unless existing LLM interfaces are inadequate.

### Secure by Design

- Redact secrets from evidence artifacts.
- Store sensitive dataset provenance as metadata/hashes, not raw records.
- Respect existing SSRF protections in web fetchers.
- Treat clinical/biomedical/legal/financial claims as high-risk by default.

### Defensive Programming

- Fail closed in strict mode.
- Treat missing evidence as unsupported, not as implicitly valid.
- Distinguish "cannot determine" from "supported."
- Preserve old artifacts when writing new reports so failures are debuggable.

### Observability

- Log integrity mode, gate decisions, and counts.
- Emit structured `integrity_report.json`.
- Add run summary metrics.
- Include claim IDs in logs and CLI output.

### CI/CD

- Keep fast deterministic integrity tests in default CI.
- Run live-source and LLM checks in optional scheduled CI.
- Add regression fixtures before enabling hard gates broadly.
- Require code review for changes to gate policy and fallback behavior.

### Documentation

Update:

- `README.md`: integrity modes and finalization behavior.
- `configs/config.arc.example.yaml`: `integrity` section.
- `docs/`: provenance schema and strict-mode guide.
- CLI help text for draft/submission/strict modes.

### Performance

- Cache claim verification by normalized claim text, evidence IDs, and source snippet hashes.
- Batch LLM alignment checks.
- Verify only changed claims after rewrites.
- Avoid repeated full-text retrieval.

### Scalability

- JSONL artifacts are sufficient initially.
- If registries grow large, split by stage and maintain an index.
- Keep stable evidence IDs so downstream tools can reference claims across runs.

## 10. Deployment and Rollback Plan

### Deployment Sequence

1. Merge models and config with no hard behavior changes.
2. Start writing `evidence_registry.json` and `claim_manifest.json` in draft mode.
3. Add report generation and CLI/API exposure.
4. Enable warning gates in draft mode.
5. Enable submission mode for explicit user opt-in.
6. Enable strict defaults for high-risk domains.
7. Tighten Stage 23 fallback behavior in strict/submission modes.

### Rollback Strategy

Rollback levers:

- Set `integrity.mode: draft`.
- Disable specific verifier rules through config.
- Disable manifest requirement while continuing to write reports.
- Re-enable legacy citation fallback only in draft mode.
- Keep old output artifact names unchanged.

Rollback constraints:

- Do not remove generated integrity artifacts during rollback.
- Do not downgrade strict-mode failures silently.
- Log any downgrade from strict/submission to draft mode.

### Backward Compatibility

Preserve:

- Existing stage numbers.
- Existing artifact names.
- Existing CLI commands.
- Existing tests for `VerifiedRegistry` and `paper_verifier.py`.

Add:

- New optional artifacts.
- New config section with safe defaults.
- New summary fields without removing old fields.

## 11. Post-Implementation Validation Checklist

Before considering the upgrade complete:

- [ ] `evidence_registry.json` is produced for a normal run.
- [ ] `claim_manifest.json` is produced after Stage 17 and updated after revisions.
- [ ] Numeric claims still pass existing `VerifiedRegistry` tests.
- [ ] Fake numeric result in Results fails strict/submission mode.
- [ ] Fake p-value fails strict/submission mode.
- [ ] Fake confidence interval fails strict/submission mode.
- [ ] Fake dataset/database claim fails strict/submission mode.
- [ ] Fake baseline/ablation claim fails strict/submission mode.
- [ ] Real citation with unsupported sentence is flagged.
- [ ] Hallucinated citation is removed or blocks finalization according to mode.
- [ ] Stage 23 does not silently restore unverified bibliography in strict mode.
- [ ] Rewriting cannot change a verified number without detection.
- [ ] Missing figure/table references are detected.
- [ ] Biomedical/clinical/legal/financial/policy topics default to strict mode.
- [ ] Draft mode remains usable and non-blocking.
- [ ] Submission mode blocks critical integrity failures.
- [ ] CLI failure messages identify claim, location, evidence gap, and suggested fix.
- [ ] API exposes integrity report artifacts.
- [ ] Provenance appendix is generated.
- [ ] CI includes deterministic negative regression tests.
- [ ] Documentation explains integrity modes and manual override policy.

## 12. Recommended First Sprint

Sprint objective: ship the foundation without breaking existing runs.

Scope:

1. Add `integrity` config with `draft`, `submission`, and `strict` modes.
2. Add `berb/integrity/evidence.py` and `berb/integrity/registry.py`.
3. Mirror `VerifiedRegistry` numeric values into evidence records.
4. Emit `evidence_registry.json` from Stage 17 or Stage 20 using `from_run_dir`.
5. Add `ClaimManifest` schema and create a best-effort manifest after Stage 17.
6. Add tests for registry load/save and draft-mode non-blocking behavior.

Out of scope for first sprint:

- LLM-backed citation support.
- Full strict-mode enforcement.
- Domain auto-strict defaults.
- Rewrite drift detection.

This first sprint creates the substrate needed for the rest of the anti-fabrication roadmap while keeping behavior backward-compatible.
