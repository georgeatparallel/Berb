# Berb Architecture Audit — v2 Protocol

**Date:** 2026-08-10 · **Scope:** `E:\Documents\Vibe-Coding\Berb` (`berb/` package, 23-stage pipeline)
**Method:** 3 parallel read-only research passes (fingerprinting/deps, AI-orchestrator deep-dive, anti-pattern sweep) + synthesis. EGFV labels applied per claim.

---

## Step 0 — Input Gate

| Input | Status |
|---|---|
| Full codebase (folder tree + source) | ✅ present |
| Primary entry points | ✅ `berb/cli.py`, `berb/server/app.py` |
| ADRs | ❌ none found → `[UNKNOWN — ADRs not provided]` applied to all "was this intentional?" judgments below |
| README / design docs | ⚠️ partial — `CLAUDE.md` + `docs/CODEBASE_MIND_MAP.md` exist and are treated as high-value input |
| Dependency manifests | ✅ `pyproject.toml` |
| Deployment manifests | `[UNKNOWN — not checked this pass]` |
| CI/CD configs | `[UNKNOWN — not checked this pass]` |

---

## Phase 1 — Architectural Fingerprinting

**DETECTED ARCHITECTURE: Pipeline architecture with a decorator-based stage registry, wrapped by an async DAG orchestrator, with an incompletely-adopted hexagonal-ports layer.**

Evidence:
1. `[VERIFIED]` `berb/pipeline/registry.py:52-82` — `register_stage()` is a decorator that populates a module-level `_registry` dict; `executor.py:198-204` dispatches purely via `get_registration(stage)` (no hardcoded switch table — a prior `_STAGE_EXECUTORS` dispatch table was removed).
2. `[VERIFIED]` `berb/pipeline/contracts.py:140-148` — `StageContract` (frozen dataclass): `stage`, `input_files`, `output_files`, `dod`, `error_code`, `max_retries`, `depends_on: frozenset[Stage]`. `berb/pipeline/_helpers.py:72-81` — `StageResult` (frozen dataclass): `stage`, `status`, `artifacts`, `error`, `decision`, `evidence_refs`.
3. `[VERIFIED]` `berb/pipeline/runner.py:99-137` builds DAG execution levels from `depends_on`; `execute_pipeline` (runner.py:301-340) runs same-level stages concurrently via `asyncio.gather` — e.g. `CODE_GENERATION` and `RESOURCE_PLANNING` both depend only on `EXPERIMENT_DESIGN` and co-execute. **This is not a strictly sequential pipeline** — it's a DAG scheduler.
4. `[VERIFIED]` `berb/pipeline/executor.py:141` — `execute_stage()` itself is synchronous; `runner.py` bridges sync↔async via `asyncio.to_thread` (`runner.py:445-448`).
5. `[VERIFIED]` `berb/adapters.py:58-109` declares four `Protocol` ports (`LLMProvider`, `LiteratureSource`, `ExperimentSandbox`, `ArtifactStore`) — a hexagonal/ports-and-adapters aspiration layered on top of the pipeline. As shown in Phase 5, this layer is largely unused in practice.

---

## Phase 2 — Compliance Matrix

| Module | Detected Pattern | Intended Pattern (per code's own docstrings/adapters.py) | Drift | Violations | Severity | Evidence |
|---|---|---|---|---|---|---|
| `berb/pipeline/executor.py` + `runner.py` | DAG-scheduled stage registry | Same | None | — | — | Phase 1 |
| `berb/llm/` (client selection) | Direct `LLMClient.from_rc_config()` construction in the default path | Provider abstraction via `create_llm_client()` factory → `MultiProviderLLMClient`/`SmartLLMClient` | **High** | Configured `fallback_providers` and NadirClaw cascade routing never engage outside `provider == "acp"` | CRITICAL | `[VERIFIED]` `executor.py:183-186` |
| `berb/review/ensemble.py` | `async def` review methods that internally block | True concurrent fan-out via `asyncio.gather` | **High** | 5-reviewer ensemble executes serially despite `gather`; event loop blocked during each call | CRITICAL | `[VERIFIED]` `ensemble.py:498,525,328` |
| `berb/adapters.py` ports (`LiteratureSource`, `ExperimentSandbox`, `ArtifactStore`) | Protocol + single "Recording" stub each | Real production adapters swapped in at runtime | **High** | Zero read sites in `stage_impls/`; ports exist but are inert | HIGH | `[VERIFIED]` Phase 5 §5 |
| `berb/pipeline/stage_impls/_review_publish.py`, `openrouter_adapter.py` | 3617 / 3951-line single files | Cohesive, ≤800-line modules (project's own convention) | **High** | God-module | HIGH | `[VERIFIED]` Phase 5 §1 |
| Inter-stage data contract | Filesystem convention (`run_dir.glob("stage-NN*/...")`) | `StageContract.input_files/output_files` presence-checked contract | **Medium** | Content/schema not validated; 15+ ad-hoc glob call sites bypass the contract layer | MEDIUM | `[VERIFIED]` Phase 5 §3 |
| `berb/llm/model_cascade.py` + `model_router.py` | Two parallel, well-built, fully unused cascade implementations | One wired implementation | **Medium** | Dead code, duplicated logic, drift risk between the two copies | MEDIUM | `[VERIFIED]` Phase 4 §2 |
| `berb/memory/`, `berb/research/`, `berb/vision/`, `mnemo_bridge/`, `reasoner_bridge/` | Fully implemented, zero production importers | Wired subsystems (per module docstrings/tests) | **Medium** | Orphaned code (already flagged in `CLAUDE.md`) | MEDIUM (known/accepted) | `[VERIFIED]` Phase 4 §4, Phase 5 §6-7 |
| `berb/experiment/` sandbox execution | Delegated via `factory.create_sandbox()` port, output truncated but not schema-validated before re-prompting LLM | Same, plus content validation | **Low** | No injection/schema check on sandbox stdout fed back into prompts | LOW | `[VERIFIED]` Phase 4 §6 |
| `berb/config.py` | Plain frozen dataclasses, env-var-enforced secrets, plaintext-key rejection | Same | None | — | — | `[VERIFIED]` Phase 1 §6 |
| `berb/metaclaw_bridge/` | Config-gated (`enabled: bool = False`), checked before invocation | Same | None | — | — | `[VERIFIED]` Phase 5 §6 |

*(Cosmetic issues omitted per protocol.)*

---

## Phase 3 — Dependency & Coupling Analysis

- **Circular dependencies:** `[VERIFIED — scoped]` None found for the pairs checked: `pipeline↔llm`, `review↔pipeline`, `integrity↔review`, `llm↔pipeline`. Not an exhaustive whole-repo cycle audit.
- **Layer leak:** `[VERIFIED]` Every `stage_impls/*.py` file imports `LLMClient` directly from `berb.llm.client` (e.g. `_review_publish.py:17`, `_analysis.py:12`) rather than through the `LLMProvider` port `berb/adapters.py:58-62` explicitly says stage implementations should depend on ("Stage implementations depend on this, not LLMClient"). Only one call site (`_literature.py:510` / `_synthesis.py:146`) actually uses the port. This is a direct, self-contradicting layer leak against the codebase's own documented intent.
- **Shared mutable state:** `[VERIFIED]` `run_dir` is the de facto message bus between stages — see Phase 2 row above and Phase 5 §3 citations (`_prompt_helpers.py:132`, `summary.py:88-99`, `_review_publish.py:1049-1053`, `packaging.py:43-143`).
- **Tight coupling hotspots:** `[VERIFIED]` `_review_publish.py` (3617 lines, 62 raw file I/O call sites) is the highest-afferent-coupling file in the pipeline — it pulls from `review`, `integrity`, `literature`, `experiment`, `llm` simultaneously and owns stages 18-23's logic in one file.
- **Boundary violations:** `[VERIFIED]` `berb/experiment/` → `berb/agents/`: 0 matches — this boundary is clean, contrary to what might be assumed from the plan's cross-references.

---

## Phase 4 — AI Orchestrator Deep Review

**ORCHESTRATION MODEL**
- `[VERIFIED]` Routing logic is architecturally separated (`PROVIDER_PRESETS`, `LLMProvider` enum, `create_llm_client()` factory) — but **the default execution path bypasses the factory** (`executor.py:183-186`), so `MultiProviderLLMClient` failover and `SmartLLMClient`/NadirClaw cascade routing only activate when `config.llm.provider == "acp"`. CRITICAL — this silently defeats configured resilience for the vast majority of runs.
- `[VERIFIED]` Provider SDK specifics are cleanly isolated; zero hardcoded provider calls found in `stage_impls/`.

**ASYNC AND CONCURRENCY**
- `[VERIFIED]` CRITICAL: `berb/review/ensemble.py:498-525` — `_generate_review` is `async def` but calls `self._llm_client.chat(...)` synchronously (no `await`, no `to_thread`). The blocking call happens inside `client.py:556/935` (`urllib.request.urlopen`). Result: `asyncio.gather` over 5(-6) reviewer personas (`ensemble.py:328`) provides no real parallelism — reviews execute back-to-back, multiplying wall-clock review latency by persona count.
- `[VERIFIED]` Batch-API path (`ensemble.py:384/395/412`, via Anthropic Message Batches) correctly wraps blocking polls in `asyncio.to_thread` — so the fix pattern already exists in the same file, just not applied to the non-batch path.
- `[VERIFIED]` `berb/experiment/async_pool.py` demonstrates the correct bounded-concurrency pattern (`Semaphore`, `gather(..., return_exceptions=True)`) elsewhere in the codebase — the ensemble bug is a local regression, not a systemic team-wide gap.

**STATE AND CONTEXT**
- `[VERIFIED]` No session/conversation state manager wired into the pipeline. `berb/memory/` (shared research memory) has exactly 2 external importers (`experiment/self_correcting.py`, itself unwired; `review/ensemble.py` for embedding-based dedup only — not session state). Confirms `CLAUDE.md`'s own "no — implemented and tested, but nothing constructs it" claim.
- `[VERIFIED]` Cross-stage context propagation is implicit (filesystem convention), per Phase 3.

**FAILURE SEMANTICS**
- `[VERIFIED]` Retry with exponential backoff (`client.py:716-823`, max_retries=3 default) and a per-client `CircuitBreaker` (`client.py:294-410`, opens at 5 failures) are real and correctly implemented. Positive finding.
- `[VERIFIED]` `runner.py:379-388` halts the pipeline on `StageStatus.FAILED` unless the stage is in `NONCRITICAL_STAGES` and `skip_noncritical` is set — reasonable, explicit policy.
- `[VERIFIED]` Fallback provider routing exists in code (`MultiProviderLLMClient`) but is bypassed by default per the orchestration-model finding above — the failure-semantics *design* is sound, the *wiring* is not.

**TOOL EXECUTION**
- `[VERIFIED]` Sandbox execution (`ExperimentSandbox`-style, actually wired via `factory.create_sandbox()`, not the unused `adapters.py` port) is isolated from LLM orchestration — clean boundary.
- `[VERIFIED]` Output "validation" is truncation only (`_execution.py:718,1128,1134`) — no schema or content-safety check before sandbox stdout/stderr is re-injected into a subsequent LLM prompt. LOW severity here specifically because the executed code is self-authored by the same pipeline (not third-party/untrusted input), but this is the mechanism that would matter if code-search/agent tooling ever pulls in external snippets.

**SCALABILITY BOTTLENECKS**
- `[VERIFIED]` The orchestrator is stateless — no module-level mutable state in `executor.py`/`runner.py`; a fresh `LLMClient` is constructed per stage call. Positive finding, horizontal-scale-friendly.
- `[VERIFIED]` The actual bottleneck under 10x load is the blocking-in-async pattern above (serializes what should be the highest-parallelism part of the system — the review ensemble) plus synchronous, unpooled filesystem writes for checkpoints (`runner.py:282,541,587,601`).

**Stack-specific checks**
- FastAPI: `[UNKNOWN — not audited this pass]` whether `berb/server/routes/*.py` correctly uses background tasks vs. blocking handlers.
- Redis/Docker: `[VERIFIED]` no Redis usage anywhere in `berb/` (grepped). Docker is used only as one of four `ExperimentSandbox` execution modes, not for service boundaries — `[N/A]`, this isn't a microservices deployment.

---

## Phase 5 — Anti-Pattern Detection

| Anti-pattern | Evidence | Severity |
|---|---|---|
| **God module** | `openrouter_adapter.py` (3951 lines), `_review_publish.py` (3617 lines, stages 18-23 fused), `_paper_writing.py` (2578), `prompts.py` (2536), `templates/converter.py` (1947), `review/ensemble.py` (898) — all `[VERIFIED]` over 800-line project convention | HIGH |
| **Premature abstraction** | `berb/adapters.py`'s `LiteratureSource`, `ExperimentSandbox`, `ArtifactStore` Protocols each have exactly one implementer (their own `Recording*` test stub) and zero real production adapter; never read from `stage_impls/`. `[VERIFIED]` | HIGH |
| **Infrastructure leakage / layer violation** | Direct `LLMClient` imports in every stage_impl bypassing the documented `LLMProvider` port. `[VERIFIED]` | HIGH |
| **Hidden monolith (convention-coupling)** | 15+ `run_dir.glob("stage-NN*/...")` call sites reading prior-stage output by filesystem convention, with only existence checks, no schema validation. `[VERIFIED]` | MEDIUM |
| **Dead/duplicated code** | `model_cascade.py` and `model_router.py` — two parallel, unused NadirClaw-style cascade implementations. `[VERIFIED]` | MEDIUM |
| **Orphaned subsystems** | `berb/memory/`, `berb/research/`, `berb/vision/`, `mnemo_bridge/`, `reasoner_bridge/` — zero production importers, confirmed by grep. Already known/documented in `CLAUDE.md`; not a new finding but re-confirmed current. `[VERIFIED]` | MEDIUM (accepted debt) |
| **Blocking-in-async** | `ensemble.py:525` synchronous `chat()` call inside `async def _generate_review`, defeating `asyncio.gather` parallelism. `[VERIFIED]` | CRITICAL |
| **Silent resilience bypass** | `executor.py:186` constructs `LLMClient` directly, skipping the `create_llm_client()` factory that would apply configured multi-provider fallback/cascade routing. `[VERIFIED]` | CRITICAL |

No evidence found for: circular-dependency god-cycles (scoped check only), shared-database coupling (no DB in this system — filesystem-based), anemic domain model (stage_impls carry real logic, not just data holders), overengineering elsewhere (the ports layer is the one overengineered/underused spot, already captured above).

---

## Phase 6 — Executive Summary

**ARCHITECTURE SCORE: 4 / 10**
Rubric anchor: *"Significant structural violations, hidden coupling, weak boundaries."* Two CRITICAL findings (LLM resilience silently bypassed; ensemble concurrency silently defeated) plus three HIGH findings (god modules, premature/unused ports, direct layer-violating imports contradicting the codebase's own documented port contract) push this below the "moderate drift" (6) anchor. The DAG scheduler, contract system, retry/circuit-breaker design, and config/secrets handling are genuinely solid — the score is dragged down by real wiring gaps between well-designed pieces, not by absence of design.

**MATURITY LEVEL: Early Production**
Extensive test suite (3900+ passing per this session's regression runs), working end-to-end 23-stage execution, and hardened secret handling indicate beyond-prototype maturity. But silently-inert resilience code (fallback routing, three of four adapter ports) and a concurrency bug that multiplies review latency indicate the system hasn't yet been load-tested or audited against its own design intent.

**PRIMARY RISKS (ranked by impact):**
1. Review ensemble latency scales linearly with persona count instead of staying flat, because blocking calls defeat `asyncio.gather` (`ensemble.py:525`) — CRITICAL, directly affects every run's cost/latency.
2. Configured multi-provider failover and cascade routing never engage outside the ACP path (`executor.py:186`) — CRITICAL, a provider outage degrades the whole pipeline despite fallback config existing.
3. `_review_publish.py` (3617 lines) concentrates stages 18-23's logic in one file with 62 raw I/O sites — HIGH, single point of review/maintenance friction, was the most-modified file in this session's implementation work.
4. Three of four `adapters.py` ports are dead abstraction — HIGH, creates a false sense of testability/swappability that doesn't actually exist at runtime.
5. Inter-stage contracts are convention-only (filesystem glob + existence check) — MEDIUM, a renamed or reshaped artifact from any stage silently degrades downstream stages rather than failing the contract check.

**CRITICAL VIOLATIONS (from Phase 2/5, CRITICAL severity only):**
- `executor.py:186` bypasses `create_llm_client()` factory — fallback/cascade routing inert by default.
- `ensemble.py:498-525` blocking LLM call inside `async def` — ensemble review fan-out is not actually concurrent.

**REFACTOR URGENCY: Next Sprint**
Not "Immediate" because both CRITICAL items are silent (no crashes, no failing tests — they degrade cost/latency/resilience, not correctness), but they directly undercut resilience and cost work already invested this session (P0-05 cost tracking, batch API adoption). Fixing them is small-diff and high-leverage relative to the god-module and ports cleanup, which are real but larger, `Long-Term` items.

---

## Phase 7 — Refactoring Roadmap

**IMMEDIATE (fix before next feature):**
- [Phase 5: blocking-in-async] → Wrap `self._llm_client.chat(...)` in `ensemble.py:525` with `await asyncio.to_thread(...)`, matching the pattern already used for batch polling in the same file (`ensemble.py:384/395/412`) → restores true concurrent fan-out, cuts ensemble review wall-clock roughly N-fold for N personas.
- [Phase 4/5: resilience bypass] → Change `executor.py:183-186` to call `create_llm_client(config)` unconditionally (it already handles the ACP branch internally) rather than special-casing `LLMClient.from_rc_config()` for the non-ACP path → activates configured `fallback_providers` and NadirClaw cascade for all runs, not just ACP.

**HIGH-IMPACT (next sprint):**
- [Phase 5: dead code] → Delete `berb/llm/model_router.py` (confirmed superseded, zero importers) and keep `model_cascade.py` as the single cascade implementation, after wiring it in per the item above → removes duplication/drift risk.
- [Phase 3/5: layer leak] → Either (a) delete the unused `LiteratureSource`/`ExperimentSandbox`/`ArtifactStore` Protocols in `adapters.py` since nothing implements or reads them beyond their own stubs, or (b) actually wire `stage_impls/` to depend on the `LLMProvider` port instead of importing `LLMClient` directly, matching the port's own docstring intent. Pick one — the current state (port exists, mostly bypassed) is worse than either extreme.
- [Phase 2/5: god module] → Split `_review_publish.py` (3617 lines, stages 18-23) into per-stage files (`_review.py`, `_revision.py`, `_quality_gate.py`, `_archive.py`, `_export.py`, `_citation_verify.py`) mirroring the existing one-file-per-phase convention used elsewhere in `stage_impls/`.

**LONG-TERM (architectural evolution):**
- Introduce a real schema/contract layer for inter-stage artifacts (e.g., a small Pydantic/dataclass model per artifact type, validated at both write and read sites) to replace the current glob-and-hope convention — migrate one high-traffic artifact first (`experiment_summary.json`, already touched by 3+ stages per this session's P0-01/P2-03 work) before generalizing.
- Decide the fate of `berb/memory/`, `berb/research/`, `berb/vision/`, `mnemo_bridge/`, `reasoner_bridge/`: either wire them in with an explicit caller and test coverage, or remove them — carrying fully-implemented, fully-tested, zero-caller code long-term is a maintenance tax with no corresponding benefit. This is a product decision, not a pure refactor — flag to the user rather than deciding unilaterally.

**SWITCHING TRIGGERS (conditions that would force architecture change):**
- If concurrent multi-user pipeline runs become a requirement, the filesystem-convention `run_dir` coupling (Phase 3) would need to become a real content-addressed or schema-validated artifact store before horizontal scaling is safe.
- If the sandbox execution path starts ingesting untrusted external code/output (vs. today's self-generated-only code), the truncation-only output handling (Phase 4 §6) would need real content/injection validation before it's safe to keep feeding sandbox output back into prompts unchecked.
