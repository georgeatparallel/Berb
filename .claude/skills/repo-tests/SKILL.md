---
name: repo-tests
description: Map of tests/ — 157 pytest files mirroring berb/ modules, plus e2e_*.py suites needing real API keys. Use when running tests, locating the test for a module, or adding coverage.
---

# tests/

Flat pytest suite (~157 files) covering the `berb/` package. Test files mirror module names (`test_berb_literature.py` → `berb/literature/`). Shared fixtures live in `tests/conftest.py`. Markers `@pytest.mark.slow`, `@pytest.mark.e2e`, `@pytest.mark.llm` gate expensive tests; `e2e_*.py` files (not `test_`-prefixed) require real LLM API keys and are excluded from default collection.

## Contents

| File/Group | Covers (berb module) |
|------|---------|
| `conftest.py`, `__init__.py` | Shared fixtures, package marker |
| `test_berb_stages.py`, `test_berb_runner.py`, `test_e2e_pipeline.py`, `test_berb_e2e_regression.py`, `test_phase3_knowledge.py`, `test_phase4_writing.py`, `test_phase7_hooks.py`, `test_synthesis_fix.py`, `test_synthesis_regression.py`, `test_berb_checkpoint.py`, `test_checkpoint.py`, `test_dependency_context.py` | `berb/pipeline/` — stages, runner, executor, checkpoints |
| `test_berb_llm.py`, `test_anthropic.py`, `test_anthropic_adapter_caching.py`, `test_openrouter_adapter.py`, `test_minimax_provider.py`, `test_llm_provider_utils.py`, `test_provider_presets.py`, `test_extended_router.py`, `test_batch_api.py`, `test_prompt_cache.py`, `test_speculative_gen.py`, `test_adaptive_temp.py`, `test_token_tracker.py`, `test_structured_outputs.py`, `test_perplexity_embeddings_smoke.py` | `berb/llm/` — providers, routing, caching, batching, cost |
| `test_berb_literature.py`, `test_berb_novelty.py`, `test_berb_pdf_ingestor.py`, `test_web_scholar.py`, `test_web_pdf_extractor.py`, `test_web_search.py`, `test_web_crawler.py`, `test_grey_search.py`, `test_searxng_client.py`, `test_firecrawl_and_fulltext.py`, `test_literature_expansion.py`, `test_deep_query_clients.py`, `test_trends.py`, `test_cmd_survey.py` | `berb/literature/` — arXiv/OpenAlex/S2 search, PDF ingestion, novelty |
| `test_berb_citation_resolve.py`, `test_berb_citation_verify.py`, `test_citation_verification_web_ground.py` | Citation resolution and verification |
| `test_berb_docker_sandbox.py`, `test_ssh_and_colab_sandbox.py`, `test_external_runners.py`, `test_sandbox_security_gate.py`, `test_experiment_schema.py`, `test_experiment_search.py`, `test_experiment_repair.py`, `test_experiment_diagnosis.py`, `test_experiment_design_budget.py`, `test_universal_codegen_integration.py`, `test_code_generation_repair_context.py` | `berb/experiment/` — sandboxes, tree search, validation, repair |
| `test_benchmark_agent.py`, `test_benchmark_omissions.py`, `test_code_agent.py`, `test_code_agent_repair_context.py`, `test_code_searcher.py`, `test_figure_agent.py`, `test_decision_agent.py` | `berb/agents/` — benchmark, code, figure, decision agents |
| `test_review_and_improvement.py`, `test_ensemble_caching.py`, `test_ensemble_batch.py`, `test_ensemble_concurrency.py`, `test_proof_reviewer_persona.py`, `test_convergence_evaluator.py`, `test_assessor.py` | `berb/review/` — 5-reviewer + AC ensemble |
| `test_integrity.py`, `test_claim_adjudication.py`, `test_paper_verifier.py`, `test_audit_findings.py` | `berb/integrity/` — claim manifests, evidence |
| `test_memory_system.py` | `berb/memory/` — embeddings, retrieval |
| `test_reasoning_base.py`, `test_reasoning_methods.py`, `test_reasoning_registry_regression.py`, `test_reasoning_integration.py` | `berb/reasoner_bridge/` — ARA reasoning patterns |
| `test_mcp.py`, `test_opencode_bridge.py`, `test_copilot.py`, `test_collaboration.py` | `berb/mcp/` and bridges |
| `test_math_expr_safety.py`, `test_security_fixes.py`, `test_berb_sanitization.py`, `test_sanitize.py`, `test_full_text_ssrf.py`, `test_output_limits.py` | Security — eval/exec guards, SSRF, sanitization |
| `test_cli.py`, `test_berb_cli.py`, `test_berb_config.py`, `test_presets.py`, `test_berb_health.py`, `test_berb_preflight.py`, `test_entry_point_validation.py`, `test_operation_mode.py` | CLI, config loading, `berb doctor` health checks |
| `test_berb_templates.py`, `test_berb_report.py`, `test_results_table_builder.py`, `test_metric_parser.py`, `test_overleaf.py`, `test_anti_ai.py`, `test_domain_narrative.py`, `test_i18n.py` | Writing/output — templates, reports, LaTeX, style |
| `test_domain_detector.py`, `test_robotics_adapter.py`, `test_neuroscience_domain.py`, `test_berb_adapters.py`, `test_prompt_adapter.py` | Domain adapters and detection |
| `test_berb_cache.py`, `test_berb_kb.py`, `test_berb_prompts.py`, `test_berb_contracts.py`, `test_berb_quality.py`, `test_berb_validator.py`, `test_berb_sentinel.py`, `test_berb_evolution.py`, `test_self_evolve.py`, `test_berb_hyperagent.py`, `test_berb_hardware.py`, `test_skills_library.py`, `test_registry.py`, `test_verified_registry.py`, `test_project_manager.py`, `test_calendar.py`, `test_eval_dataset.py`, `test_compiler.py`, `test_asyncio_utils.py`, `test_logging_setup.py`, `test_split_policy.py`, `test_resolution.py` | Supporting subsystems — cache, KB, prompts, quality, evolution |
| `test_servers.py`, `test_web_platform.py`, `test_web_integration.py` | Server / web platform (`berb serve`) |
| `test_bugfix_regression.py`, `test_datetime_timezone_regression.py`, `test_rate_limiter_regression.py`, `test_sre_fixes.py`, `test_sre_fixes_2.py`, `test_critical_components.py`, `test_v6_improvements.py`, `test_p0_p1_implementations.py`, `test_p2_specification.py` | Regression suites pinned to past bugs/audits |
| `test_integration.py` | Cross-module integration |
| `e2e_real_llm.py`, `e2e_docker_sandbox.py` | Real-API e2e — need live LLM keys / Docker; not collected by default |

## Notes

- Run all: `pytest tests/`; unit only: `pytest -m "not slow and not e2e and not llm"`; coverage: `pytest --cov=berb tests/` (80% gate).
- Single file: `pytest tests/test_berb_executor.py`.
- `e2e_*.py` files need real API keys (`.env`) and, for the docker one, a running Docker daemon.
- Marker meanings: `slow` = long-running, `e2e` = full pipeline, `llm` = hits a live LLM.
- The suite is flat — no subdirectories; find a module's tests by name substring (e.g. `pytest tests/ -k literature`).
