---
name: repo-docs
description: Map of docs/ — architecture references (CODEBASE_MIND_MAP.md is master), guides, plans, translated READMEs, showcase papers, and a large archive. Use when looking up architecture, docs to update, or generated showcase artifacts.
---

# docs/

All project documentation: current architecture references, how-it-works and integration guides, optimization/upgrade plans, audits, translated READMEs, generated knowledge-base output, and a deep `archive/` of superseded docs. **`docs/CODEBASE_MIND_MAP.md` is the master architecture reference** for the whole codebase — start there for any structural question.

## Contents

| File/Dir | Purpose |
|------|---------|
| `CODEBASE_MIND_MAP.md` | **Master architecture reference** — full module/pipeline map |
| `INDEX.md` | Docs index / table of contents |
| `HOW_BERB_WORKS.md` | Narrative walkthrough of the 23-stage pipeline |
| `ARCHITECTURE_v2.md`, `ARCHITECTURE_v3_OPTIMIZATIONS.md`, `ARCHITECTURE_UPGRADE_PLAN.md`, `POST_UPGRADE_REMEDIATION.md` | Architecture evolution and upgrade planning |
| `MODELS.md`, `OPENROUTER_MODEL_SELECTION.md`, `COST_OPTIMIZATION_GUIDE.md` | LLM model catalog, routing choices, cost tactics |
| `PIPELINE_INTEGRATION_GUIDE.md`, `integration-guide.md`, `COMPREHENSIVE_INTEGRATION_SUMMARY.md`, `INTEGRATION_SUMMARY.md` | How subsystems/bridges plug into the pipeline |
| `memory-model.md` | Memory subsystem design (embeddings/retrieval/shared memory) |
| `SEARXNG_FIRECRAWL_INTEGRATION.md`, `SEARXNG_INTEGRATION_PLAN.md`, `GREY_LITERATURE_SEARCH.md` | Web-search integrations (note: SearXNG/grey-lit are currently unwired) |
| `REASONER_*`, `REASONING_METHODS_FOR_BERB.md` | ARA reasoner bridge plans and methods |
| `PRODUCTION_READINESS_AUDIT.md`, `DEAD_CODE_ANALYSIS.md`, `OPEN_DECISIONS.md`, `BUG_TRACKER.md`, `BUGFIXES_COMPLETE.md`, `SECURITY_FIXES_MIGRATION.md`, `FIX_DOCTOR_ERRORS.md` | Audits, bug tracking, open decisions |
| `TESTER_GUIDE.md` (+ `_JA`) | Guide for human testers |
| `README_{AR,CN,DE,ES,FR,JA,KO,PT,RU}.md` | Translated project READMEs |
| `PHYSICS_DOMAIN_OPTIMIZATIONS.md`, `MANAGEMENT_CAPABILITIES.md`, `NAMING_CONVENTION.md`, `CLAUDE_SCHOLAR_ENHANCEMENTS.md` | Domain- and topic-specific notes |
| Plan/phase docs (`P4_OPTIMIZATION_PLAN.md`, `P5_ENHANCEMENT_PLAN.md`, `PHASE1_COMPLETE.md`, `PHASE_2_COMPLETION_SUMMARY.md`, `TODO_V6.md`, `OPTIMIZATION_SUMMARY.md`, `IMPLEMENTATION.md`, `next_phase_showcase_plan.md`, `agent_figure_and_benchmark_plan.md`) | Historical iteration plans and completion summaries |
| `showcase/` | `SHOWCASE.md` + 8 generated papers (`papers/*.pdf`) with `thumbnails/` — pipeline output demos |
| `figures/`, `figure_prompts/` | Showcase figures and the prompts that produced case-study figures |
| `kb/` | Generated knowledge-base output from a pipeline run (questions/decisions/literature markdown) |
| `archive/` | Superseded docs: `old/` (bug fixes, integration plans), `legacy/claude-scholar-main/` (vendored predecessor project), analysis PDFs |

## Notes

- Always check `CODEBASE_MIND_MAP.md` first; treat `archive/` content as historical, not current truth.
- Many top-level docs are point-in-time plans/summaries — cross-check against code before trusting claims about what is "live" (CLAUDE.md lists unwired modules).
- `showcase/papers/` PDFs are pipeline-generated artifacts, linked from `website/papers.html`.
- `kb/` is machine-generated per run — do not hand-edit.
