# Berb — Dead Code Analysis: What It Does, How to Wire It

**Date:** 2026-07-29
**Commit:** `1e264f5` (branch `main`)
**Companion to:** [PRODUCTION_READINESS_AUDIT.md](PRODUCTION_READINESS_AUDIT.md) §5.1

---

## 1. Headline

The CI reachability gate reports **31% dead code**. Measured from the actual product entry point — `berb run` — it is **42%**.

```
total                       423 modules   146,632 LOC
reachable (CI's 16 roots)   268 modules   100,638 LOC    dead 45,994 (31%)
reachable from berb.cli     197 modules    84,679 LOC    dead 61,953 (42%)
```

The gap is `check_reachability.py:86-95`, which declares **16 package prefixes as entry roots** — including `berb.server`, `berb.api`, `berb.ui`, `berb.plugins`, `berb.skills`, `berb.hooks`, `berb.servers`, `berb.collaboration`. Any subsystem that gets its own top-level package is reachable *by declaration*. That covers 71 modules / 15,959 LOC which nothing outside those packages imports.

**The method is otherwise sound.** The checker walks nested and function-level imports via `ast.walk`, and the codebase contains **zero** `importlib.import_module` or `__import__` calls — so there are no dynamic-import false positives. When this document says a module is unreachable, it means no import path exists.

One trap worth naming: several modules' *only* apparent references are `>>>` lines inside their own docstrings. `berb/llm/model_cascade.py:13` "imports" itself in a usage example. Grep says "used"; the import graph says otherwise.

### The signature pattern: tested, never called

| Test files | Lines | Exercise |
|---|---|---|
| 33 | 10,691 | **only** modules unreachable from `berb run` |
| 33 | 18,116 | a mix of live and unreachable |
| 78 | 26,961 | live modules only |

Roughly **19% of the test suite tests code that can never execute in production.** This is why coverage reads 57% while 42% of the code never runs. The suite is what keeps the dead code green, and therefore invisible.

Largest examples: `test_memory_system.py` (767 lines), `test_skills_library.py` (584), `test_phase7_hooks.py` (474), `test_berb_hyperagent.py` (470), `test_knowledge_graph.py` (268).

---

## 2. Two structural causes

Before the per-package inventory, two root causes explain most of the 62k LOC. Fixing them is what makes wiring cheap.

### 2.1 The adapter bundle is 90% test doubles in production

`berb/adapters.py:261-286` defines `AdapterBundle` — described in its own docstring as the "hexagonal boundary for stage implementations". Every one of its 10 ports defaults to a `Recording*` stub:

```python
memory:    MemoryAdapter    = field(default_factory=RecordingMemoryAdapter)
message:   MessageAdapter   = field(default_factory=RecordingMessageAdapter)
web_fetch: WebFetchAdapter  = field(default_factory=RecordingWebFetchAdapter)
lit:       LiteratureSource = field(default_factory=RecordingLiteratureSource)
sandbox:   ExperimentSandbox= field(default_factory=RecordingExperimentSandbox)
store:     ArtifactStore    = field(default_factory=RecordingArtifactStore)
...
```

`berb/cli.py:366` constructs a bare `AdapterBundle()`. The **only** port ever replaced with a real implementation is `llm` (`berb/pipeline/executor.py:196`). The rest run as stubs in production.

Three of them are actually called:

| Call site | Port | Real behaviour today |
|---|---|---|
| `executor.py:179, 323, 341` | `memory.append` | appends to a Python list, discarded at process exit |
| `executor.py:173, 334` | `message.notify` | appends to a list — **notifications are silently dropped** despite `NotificationsConfig` existing at `config.py:153` |
| `_literature.py:191` | `web_fetch.fetch` | returns `FetchResponse(status_code=200, text=f"stub fetch for {url}")` — **unconditionally** |

That last one is a live defect, not just dead weight. When `config.openclaw_bridge.use_web_fetch` is on, stage 3 marks every literature source `"verified"` and writes that into `search_plan.yaml`:

```python
# berb/pipeline/stage_impls/_literature.py:188-196
if config.openclaw_bridge.use_web_fetch:
    for src in sources:
        response = adapters.web_fetch.fetch(str(src.get("url", "")))
        src["status"] = "verified" if response.status_code in (200, 301, 302, 405) else "unreachable"
```

The stub always returns 200, so the check always passes. In a tool whose purpose is research integrity, that is fabricated provenance.

`lit`, `sandbox`, and `store` are never read at all — `executor.py:217-218` is a comment saying they are "available".

**This is the single highest-leverage seam in the codebase.** `berb/memory/` (1,867 LOC) is a complete implementation of exactly what `MemoryAdapter` promises. Wiring it is a constructor change, not a rewrite.

### 2.2 Nine config sections that nothing reads

Config is where the original design intent survived. These sections are defined, documented, defaulted — and never consumed:

| Section | `config.py` | Default | Read by |
|---|---|---|---|
| `MemoryConfig` | 671 | `enabled = True`, `inject_at_stages = (1, 9, 10, 17)` | **nothing** |
| `SkillsConfig` | 684 | `enabled = True`, `max_skills_per_stage = 3` | **nothing** |
| `KnowledgeGraphConfig` | 697 | `enabled = False` | **nothing** |
| `QualityAssessorConfig` | 823 | `enabled = True`, `venue_recommendation = True` | **nothing** |
| `CalendarConfig` | 839 | — | **nothing** (the calendar *modules* are used by a CLI command) |

`MemoryConfig.inject_at_stages = (1, 9, 10, 17)` is the most valuable line in this analysis: it is a written integration contract naming exactly where memory was meant to plug in — TOPIC_INIT, EXPERIMENT_DESIGN, CODE_GENERATION, PAPER_DRAFT.

For contrast, the *nested* experiment configs **are** consumed correctly — `config.experiment.code_agent.enabled` at `_code_generation.py:515`, `config.experiment.figure_agent.enabled` at `_analysis.py:651`. The pattern works when someone completes it.

### 2.3 The reasoning adapter that was never promoted

`berb/pipeline/stage_impls/_synthesis.py:39-60` hand-rolls two private classes:

```python
class _SimpleRouter:          # adapts LLMClient -> get_provider_for_role(role)
class _LLMProviderWrapper:    # adapts LLMClient -> async complete(prompt)
```

The `berb.reasoning` methods expect a router exposing `get_provider_for_role()` (the protocol of `extended_router.ExtendedNadirClawRouter` — itself dead). The pipeline has `LLMClient`. `_synthesis.py` bridged the gap privately, for one stage.

That is why exactly one reasoning method (`MultiPerspectiveMethod`) is wired and the other five are not: **every additional stage would have to re-implement the same shim.** Meanwhile `berb/reasoning/registry.py:308` already provides the intended public seam:

```python
def get_reasoner(method_type: MethodType | str, llm_client: Any = None, **kwargs) -> ReasoningMethod
```

`llm_client: Any` is the tell — the type was widened instead of the adapter being built.

**Fix once, unlock five methods:** promote the shim to `berb/reasoning/adapters.py`, have `get_reasoner` apply it, and each additional wiring becomes a ~5-line stage change.

---

## 3. Inventory by remediation class

Different dead code needs different treatment. Wiring a superseded duplicate is worse than deleting it.

### Class A — Superseded duplicates: **delete or consolidate, do not wire** (~7,500 LOC)

The live LLM path is `executor.py:184` → `create_llm_client()` → `berb/llm/__init__.py:143` → `SmartLLMClient` wrapping `NadirClawRouter`. Routing and token tracking **are** active. What is dead is a parallel stack of alternatives:

| Module | LOC | What it does | Verdict |
|---|---|---|---|
| `llm/model_router.py` | 341 | Model cascading, cheap→premium | Superseded by `model_cascade.py` — **identical opening docstring**. Delete. |
| `llm/model_cascade.py` | 511 | Same, plus LRU cache | Competes with the live `nadirclaw_router`. Pick one. |
| `llm/extended_router.py` | 585 | Extends `NadirClawRouter`: 27 role-based routes, provider diversity, budget enforcement | The live router's intended successor. Either finish or delete. |
| `llm/prompt_cache.py` | 407 | Provider prompt caching, claims 80-90% input-token reduction | **Genuinely additive.** Wire. |
| `llm/batch_api.py` | 404 | Batch submission, claims 50% off non-urgent calls | **Genuinely additive.** Wire for eval/condense/enhance calls. |
| `llm/speculative_gen.py` + `speculative_router.py` | 788 | Run cheap+premium in parallel, take cheap if good enough | Overlaps cascading. Decide against cascade. |
| `llm/adaptive_temp.py` | 275 | Raise temperature on retries | Small, additive. Wire into `retry_utils`. |
| `llm/retry_utils.py` | 115 | Retry decorator with backoff | Dead despite a "SECURITY FIX #7" header. Check against the live retry path, then wire or delete. |
| `llm/eval_dataset.py` | 310 | Builds eval datasets from production failures | Wire — feeds the missing regression story. |
| `llm/structured_outputs.py` | 299 | Pydantic schemas for stage outputs | Wire — directly reduces JSON parse failures. |

> **Documentation impact:** `pyproject.toml` advertises "85% cost reduction". That number rests on the live NadirClaw routing path alone. Caching, batching, cascading, and speculative execution — the four features that would justify a figure that high — are all unwired. Either wire them or restate the claim.

Also duplicated: `berb/experiment/code_agent.py` (832 LOC, dead) vs `berb/pipeline/code_agent.py` (1,505 LOC, live). Two code agents; one is reached.

And `berb/memory/` (dead, embeddings + decay + retrieval) vs `adapters.memory` (live, a no-op recorder). Two memory systems; the real one is unreached and the reached one does nothing.

### Class B — Orphaned capability with a ready seam: **wire, cheap** (~2,500 LOC, ~1 week total)

These need no new abstraction. Each has an obvious call site.

| Module | LOC | What it does | Seam | Effort |
|---|---|---|---|---|
| `pipeline/tracing.py` | 219 | `Span`, `start_span`, `new_trace` — structured tracing. Only importer is a test. | `executor.py` stage dispatch. **This is the observability the audit called missing — it already exists.** | 1 day |
| `utils/time.py` | 181 | `utcnow`, `utcnow_iso`, `ensure_utc`. Only live importer is a dead module. | Replace the **6 private `_utcnow_iso` copies** in `knowledge/base.py`, `pipeline/checkpoint.py`, `iterative.py`, `packaging.py`, `summary.py`, `_helpers.py`. `tests/test_datetime_timezone_regression.py:148` already asserts the convention the code doesn't follow. | 2 hrs |
| `quality.py` | 185 | `detect_template_content`, `compute_template_ratio`, `check_strict_quality` | Stage 20 QUALITY_GATE in `_review_publish.py` — the stage exists and does not use it. | ½ day |
| `assessor/` | 442 | `PaperScorer`, `VenueRecommender`, `HistoryComparator`, rubrics | Stage 20/22. `QualityAssessorConfig.enabled = True` already. | 1 day |
| `audit/reproducibility.py` | 496 | `generate_reproducibility_package` | Stage 21 KNOWLEDGE_ARCHIVE or 22 EXPORT_PUBLISH. | ½ day |
| `metrics/` | 364 | `MetricsCollector`, `PrometheusExporter` | Executor + a `/metrics` route on `server/app.py`. | ½ day |
| `literature/specification.py` | 466 | Composable filter predicates (year, citations, venue, author) — pure, no LLM | Stage 5 LITERATURE_SCREEN. | ½ day |
| `literature/recency_filter.py` | 359 | Recency-weighted ranking — pure, no LLM | Stage 5 LITERATURE_SCREEN. | ½ day |
| `experiment/split_policy.py` | 300 | `partition`, `selection_penalty`, `admit`, `selection_bias_report` | `_execution.py:1273-1284` **hand-writes `selection_bias.json` inline** instead of calling this module. Replace the inline block. | ½ day |

### Class C — Orphaned capability blocked by the adapter: **wire, medium** (~7,000 LOC, ~3 weeks)

Do §2.3 first; then each of these is small.

**`berb/reasoning/` — 2,596 LOC across 5 methods**

| Method | LOC | Suggested stage |
|---|---|---|
| `pre_mortem.py` | 622 | Stage 9 EXPERIMENT_DESIGN — already imported by `experiment/compute_guard.py:326`, itself dead |
| `bayesian.py` | 626 | Stage 14 RESULT_ANALYSIS; also `literature/evidence_map.py:22` |
| `jury.py` | 481 | Stage 18 PEER_REVIEW — **check for overlap first**, that stage already runs a 5-reviewer + Area Chair ensemble |
| `dialectical.py` | 444 | Stage 15 RESEARCH_DECISION |
| `debate.py` | 423 | Stage 15 RESEARCH_DECISION |

**`berb/memory/` — 1,867 LOC.** `MemoryStore`, `MemoryRetriever`, embeddings, time-decay, confidence scoring; three categories (ideation / experiment / writing). Wiring is prescribed by config: implement `MemoryAdapter` with `MemoryStore`, inject retrieved context into prompts at stages 1/9/10/17, write outcomes back at stage end. **~1 week, highest product value of anything in this document** — it is the difference between a pipeline that runs and one that improves.

**`berb/research/` — 2,616 LOC.** `world_model.py` + `discovery_loop.py` (cyclic discovery with a `BudgetGovernor`), `open_ended_discovery.py`, `idea_scorer.py`, `gap_analysis.py`. Seam: a pre-stage-1 hook or a new `berb discover` CLI command. Note `gap_analysis.py:515` contains the `PerspectiveResult` `NameError` from the audit — **proof this code has never executed**.

**`berb/learning/` (528) + `berb/self_evolve/` (672).** Consume run traces to improve model/stage affinity over time. Blocked on memory landing first — do not attempt before.

### Class D — Product features that are documented but not wired (~9,000 LOC)

This class is not a maintenance issue, it is an **accuracy issue**. `README.md` and `CLAUDE.md` describe these as capabilities of the system.

**`berb/literature/` — 7,578 LOC dead.** Live: arXiv, OpenAlex, Semantic Scholar, `search`, `novelty`, `verify`, `pdf_ingestor`. Dead:

| Module | LOC | What it does | Documented as shipped? |
|---|---|---|---|
| `citation_graph.py` | 1,062 | Citation-network clustering, contradiction detection, journal quality | yes |
| `structured_notes.py` | 897 | Per-paper claim+evidence reading notes | — |
| `section_analysis.py` | 858 | Section-aware citation placement | — |
| `evidence_map.py` | 790 | Bayesian evidence-consensus mapping | — |
| `multimodal_search.py` | 605 | PDF figure extraction, chart digitizing, table parsing | **yes — CLAUDE.md** |
| `grey_search.py` | 599 | bioRxiv, medRxiv, ClinicalTrials, Zenodo, SSRN, DART-Europe | **yes — CLAUDE.md** |
| `full_text.py` | 504 | Full-text extraction from web pages | — |
| `citation_classifier.py` | 497 | Citation intent classification | — |
| `searxng_client.py` | 466 | SearXNG metasearch | **yes — CLAUDE.md** |

The SearXNG case is the sharpest: the repo ships `docker-compose.searxng.yml` and a `searxng/` directory, so a user can stand the service up — and the pipeline will never query it. Seam for all nine: stages 4-6 in `_literature.py`.

**`berb/experiment/` — 5,578 LOC dead.** `factory.py::create_sandbox` is the live seam and it branches only on `sandbox | docker`.

| Module | LOC | What it does | Documented? |
|---|---|---|---|
| `self_correcting.py` | 835 | 7-agent self-correcting simulation loop | **yes — CLAUDE.md** |
| ~~`auto_debugger.py`~~ | 775 | Error categorization + fix suggestion | **DELETED 2026-09-02 (W1)** — superseded by the wired `pipeline/experiment_diagnosis.py` + `experiment_repair.py` |
| `compute_guard.py` | 718 | Cost estimation, affordability gate, monitoring | — |
| `progress.py` | 547 | Structured multi-stage experiment runner | — |
| `evolutionary_search.py` | 540 | Design-proposal evolution | — |
| `react_agent.py` | 389 | ReAct trajectory agent | — |
| `plot_verdict.py` | 250 | VLM figure verdict as a gating control signal | — |

`compute_guard.py` deserves attention independent of the rest: it is the cost ceiling the audit found missing, already written.

### Class E — Delete (~12,000 LOC + ~4,000 lines of tests)

| Package | LOC | Test lines | Rationale |
|---|---|---|---|
| `domains/physics` + `domains/chaos` | 4,350 | ~1,285 | Already emit `DeprecationWarning`; allowlisted "scheduled for removal 2026-07-19" |
| `hyperagent/` | 2,096 | 470 | Allowlisted "revisit Q1 2027" |
| `i18n/` | 1,438 | — | 38-language support; no config, no seam, no roadmap |
| `experimental/` | 913 | 257 | `tdd_generation`, `diff_revisions` |
| `knowledge/graph/` | 751 | 268 | Zero importers; `KnowledgeGraphConfig.enabled = False` |
| `hooks/` | 651 | 474 | **Zero importers anywhere** |
| `servers/` | ~700 | 308 | SLURM/SSH/cloud executors; reachable only as a self-declared root |
| `collaboration/` | ~600 | 238 | Same |
| `plugins/` | 506 | — | **Zero importers anywhere** |
| `skills/` | ~500 | 584 | **Zero importers anywhere**, yet `SkillsConfig.enabled = True` and CLAUDE.md documents it |
| legacy servers | ~1,700 | — | Already Phase 0 of the audit |

`skills/` and `hooks/` are judgement calls: both are plausible extension points with real implementations and real tests. But `SkillsConfig` promises `max_skills_per_stage = 3` and nothing assembles skills into a prompt. Either wire at prompt-build time (`_prompt_helpers.py`) or delete — shipping an inert extension point is worse than shipping neither.

---

## 4. Recommended sequence

Ordered by leverage, not by size.

**Step 1 — Make the gate honest (½ day).**
Reduce `check_reachability.py`'s `ENTRY_PREFIX` to what `berb run` and `berb serve` actually reach. The number becomes 42%; that is the number to drive down. Without this, every later step reports progress against the wrong denominator.

**Step 2 — Fix the stub adapters (2 days).** §2.1.
Replace `RecordingWebFetchAdapter` in the production path — it is fabricating literature-source verification, which is a correctness bug in an integrity tool, not dead code. Wire `message` to `NotificationsConfig`. Decide whether `lit`/`sandbox`/`store` are load-bearing or should be deleted from `AdapterBundle`.

**Step 3 — Delete Class E (2 days).**
12,000 LOC of source and ~4,000 lines of tests. Cuts CI time, removes ~19% of the suite's dead weight, and makes coverage percentages mean something. Git history is the archive.

**Step 4 — Class B quick wins (1 week).**
Tracing, `utils/time`, quality gate, assessor, reproducibility, metrics, literature filters, split-policy. Each closes an audit finding with code that already exists and is already tested.

**Step 5 — Promote the reasoning adapter (2 days).** §2.3.
Then wire the five reasoning methods incrementally (~2 days each).

**Step 6 — Wire memory (1 week).**
Follow `MemoryConfig.inject_at_stages = (1, 9, 10, 17)`. Highest product value in this document.

**Step 7 — Resolve Class A duplication (1 week).**
Pick one router, one cascade, one code agent. Wire `prompt_cache` + `batch_api` + `structured_outputs` — genuinely additive. Then either substantiate or restate the "85% cost reduction" claim.

**Step 8 — Class D decision (2-3 weeks, or a docs change in 1 hour).**
For each documented-but-unwired feature — SearXNG, grey literature, multimodal extraction, self-correcting simulation, auto-debugger — either wire it or remove it from README/CLAUDE.md. **Do the docs change immediately regardless**, so the documentation stops describing a system that does not exist while the wiring is scheduled.

---

## 5. Caveats

- Reachability is a static import graph. A module reachable by import may still be behind a config flag that defaults off — reachable ≠ exercised. The 42% figure is an upper bound on *live* code, not a claim that the other 58% all runs.
- Two modules (`_paper_writing.py:2293`, `gap_analysis.py:515`) contain `NameError`s on first call, so parts of the nominally-reachable set have also never executed.
- Effort estimates assume the existing tests for each module are meaningful. They are unverified against real behaviour — several test only construction and serialization. Budget review time per package before committing to the wiring estimates.
