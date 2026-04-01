# Berb — Codebase Mind Map

> Auto-generated architecture reference. Read this file to understand the full project before making changes.
> Last updated: 2026-04-01

---

## 1. What Berb Does

Berb is a **23-stage autonomous research pipeline** that takes a single research idea and produces a publication-ready paper. It runs as a Python CLI package with full LLM integration, multi-source literature search, sandboxed experiment execution, and self-correction loops.

```
berb run --topic "Prompt Caching in LLMs" --auto-approve
```

---

## 2. Top-Level Module Map

```
berb/
├── cli.py                     ← Entry point: parse args, load config, start pipeline
├── config.py                  ← Load config.arc.yaml → RCConfig dataclass hierarchy
├── hardware.py                ← GPU/hardware detection
├── health.py                  ← System health checks (berb doctor)
├── prompts.py                 ← Prompt management (loads prompts.default.yaml)
├── quality.py                 ← Quality metric computation
├── evolution.py               ← Self-evolution tracking
│
├── pipeline/                  ← Core execution engine
│   ├── stages.py              ← Stage enum + STAGE_SEQUENCE (23 stages)
│   ├── runner.py              ← execute_pipeline() — stage loop, pivots, checkpoints
│   ├── executor.py            ← execute_stage() — dispatcher + contract validation
│   ├── contracts.py           ← I/O file contracts per stage
│   ├── tracing.py             ← Span infrastructure (observability)
│   ├── tdd_generation.py      ← TDD-style test generation for code stages
│   ├── opencode_bridge.py     ← OpenCode agent integration
│   ├── experiment_diagnosis.py← Diagnose experiment failures
│   └── stage_impls/           ← One file per phase:
│       ├── _topic.py          ← Stages 1-2
│       ├── _literature.py     ← Stages 3-6
│       ├── _synthesis.py      ← Stages 7-8
│       ├── _experiment_design.py ← Stage 9
│       ├── _code_generation.py   ← Stage 10
│       ├── _execution.py      ← Stages 11-13
│       ├── _analysis.py       ← Stages 14-15
│       ├── _paper_writing.py  ← Stages 16-17
│       └── _review_publish.py ← Stages 18-23
│
├── llm/                       ← LLM client + cost routing
│   ├── client.py              ← Base LLMClient
│   ├── model_router.py        ← Route by cost/latency
│   ├── model_cascade.py       ← Cascade: try cheap → escalate to premium
│   ├── nadirclaw_router.py    ← NadirClaw 3-tier routing
│   ├── acp_client.py          ← Anthropic API
│   ├── batch_api.py           ← Batch API support
│   └── adaptive_temp.py       ← Dynamic temperature adjustment
│
├── literature/                ← Academic paper search
│   ├── search.py              ← search_papers() — unified dedup, caching
│   ├── models.py              ← Paper, Author (frozen dataclasses)
│   ├── arxiv_client.py        ← arXiv API (1 req/3s)
│   ├── openalex_client.py     ← OpenAlex API (10K/day)
│   ├── semantic_scholar.py    ← Semantic Scholar (1K/5min)
│   ├── grey_search.py         ← bioRxiv, medRxiv, Zenodo, ClinicalTrials, SSRN
│   ├── citation_graph.py      ← Build citation network + PageRank
│   ├── novelty.py             ← Novelty scoring
│   ├── verify.py              ← Citation verification
│   ├── cache.py               ← Search result cache (TTL-based)
│   ├── searxng_client.py      ← SearXNG integration (literature module)
│   ├── multimodal_search.py   ← Figure/table extraction via VLM
│   ├── trends.py              ← Research trend analysis
│   └── _rate_limiter.py       ← Shared rate limiter for all clients
│
├── experiment/                ← Code execution + debugging
│   ├── sandbox.py             ← Local subprocess
│   ├── docker_sandbox.py      ← Docker container (Windows-safe paths)
│   ├── ssh_sandbox.py         ← Remote SSH
│   ├── colab_sandbox.py       ← Google Colab
│   ├── agentic_sandbox.py     ← OpenCode multi-file agent
│   ├── code_agent.py          ← Code generation + process management
│   ├── self_correcting.py     ← Detect error → LLM fix → re-run
│   ├── auto_debugger.py       ← Automated debugging loop
│   ├── validator.py           ← Code validation (imports, syntax, runtime)
│   ├── metrics.py             ← Parse metrics from stdout/files
│   ├── visualize.py           ← Result plotting
│   ├── git_manager.py         ← Git operations for experiment code
│   └── progress.py            ← Experiment progress tracking
│
├── web/                       ← General web search + crawling
│   ├── search.py              ← WebSearchClient (Tavily → SearXNG → DDG)
│   ├── searxng_client.py      ← SearXNG metasearch (100+ engines)
│   ├── scholar.py             ← Google Scholar (scholarly + proxy rotation)
│   ├── agent.py               ← Autonomous web browsing agent
│   ├── crawler.py             ← HTML crawling + link following
│   ├── pdf_extractor.py       ← PDF → text extraction
│   └── _ssrf.py               ← SSRF protection (safe URL validation)
│
├── agents/                    ← Specialized agents
│   ├── base.py                ← BaseAgent (plan/act/observe/reflect)
│   ├── benchmark_agent/       ← Orchestrator→Acquirer→Selector→Surveyor→Validator
│   ├── code_searcher/         ← GitHub code search + pattern extraction
│   └── figure_agent/          ← Figure generation (Matplotlib/TikZ) + critique
│
├── review/
│   └── ensemble.py            ← ReviewEnsemble: 4 reviewer personas → aggregated scores
│
├── memory/
│   └── shared_memory.py       ← SharedResearchMemory: multi-agent coordination, error→fix store
│
├── presets/                   ← Pipeline templates
│   ├── base.py                ← PipelinePreset (Pydantic v2)
│   ├── registry.py            ← PresetRegistry + load_preset() + list_presets()
│   └── catalog/               ← YAML presets:
│       ├── ml-conference.yaml ← NeurIPS/ICML/ICLR
│       ├── biomedical.yaml    ← Clinical/translational
│       ├── rapid-draft.yaml   ← Speed-optimised, 16 stages
│       ├── nutrition-bioactive.yaml ← PIPA LEAP platform
│       ├── food-ai-innovation.yaml  ← PIPA FIOS
│       ├── life-sciences-kg.yaml    ← DEUS drug discovery
│       └── process-optimization-dt.yaml ← DEUS digital twins
│
├── mnemo_bridge/              ← Mnemo Cortex memory integration
├── metaclaw_bridge/           ← MetaClaw PRM gate + skill injection
│   ├── prm_gate.py            ← Process Reward Model quality gating
│   ├── lesson_to_skill.py     ← Extract skills from learnings
│   └── stage_skill_map.py     ← Stage → skill mapping
├── reasoner_bridge/           ← Multi-perspective reasoning (ARA)
├── mcp/                       ← Model Context Protocol server
│
├── knowledge/                 ← Knowledge base + graph
├── domains/                   ← Domain profiles (YAML) + adapters
├── validation/                ← Finding reproduction + verification
├── research/                  ← Agentic tree search, idea scoring
├── vision/                    ← VLM figure critique + generation
├── assessment/                ← Paper quality assessment
├── reasoning/                 ← Multi-perspective reasoning implementations
├── skills/builtin/            ← Stage-specific built-in skills
├── templates/styles/          ← LaTeX templates (NeurIPS, ICML, ICLR, ACL…)
├── optimization/              ← Cost-quality optimization loop
├── hyperagent/                ← Meta-agent stubs (NotImplementedError — P1 TODO)
├── hooks/                     ← CLI lifecycle hooks
├── wizard/                    ← Interactive setup wizard
└── overleaf/                  ← Overleaf LaTeX sync
```

---

## 3. The 23 Stages

| # | Stage Name | Phase | Type | Key Output |
|---|-----------|-------|------|-----------|
| 1 | TOPIC_INIT | A: Scoping | normal | `topic.json` (keywords) |
| 2 | PROBLEM_DECOMPOSE | A | normal | `decomposition.json` (sub-questions) |
| 3 | SEARCH_STRATEGY | B: Literature | normal | `search_strategy.json` (queries) |
| 4 | LITERATURE_COLLECT | B | normal | `papers.jsonl`, `papers.bibtex` |
| 5 | LITERATURE_SCREEN | B | **GATE** | `screened_papers.jsonl` |
| 6 | KNOWLEDGE_EXTRACT | B | normal | `knowledge_base.jsonl` |
| 7 | SYNTHESIS | C: Knowledge | normal | `synthesis.md` |
| 8 | HYPOTHESIS_GEN | C | normal | `hypotheses.json` |
| 9 | EXPERIMENT_DESIGN | D: Design | **GATE** | `exp_plan.yaml` |
| 10 | CODE_GENERATION | D | normal | `experiment/*.py` |
| 11 | RESOURCE_PLANNING | D | normal | `resource_estimate.json` |
| 12 | EXPERIMENT_RUN | E: Execution | normal | `runs/*.json`, `metrics_aggregated.json` |
| 13 | ITERATIVE_REFINE | E | normal | `experiment_final/`, `refinement_log.json` |
| 14 | RESULT_ANALYSIS | F: Analysis | normal | `experiment_summary.json`, figures |
| 15 | RESEARCH_DECISION | F | normal | `decision.json` (PROCEED/PIVOT/REFINE) |
| 16 | PAPER_OUTLINE | G: Writing | normal | `paper_outline.md` |
| 17 | PAPER_DRAFT | G | normal | `paper_draft.md`, figures, `bibliography.bibtex` |
| 18 | PEER_REVIEW | G | normal | `review_ensemble.json` |
| 19 | PAPER_REVISION | G | normal | `paper_revised.md` |
| 20 | QUALITY_GATE | H: Finalization | **GATE** (non-critical) | `quality_report.json` |
| 21 | KNOWLEDGE_ARCHIVE | H | normal | `archive_log.json` |
| 22 | EXPORT_PUBLISH | H | normal | `paper_final.pdf`, `.tex`, `.md` |
| 23 | CITATION_VERIFY | H | normal | `verification_report.json` |

**Gate logic:**
- Stage 5 → rollback target: Stage 4
- Stage 9 → rollback target: Stage 8
- Stage 20 → rollback target: Stage 16 (non-critical: can skip)

**Decision rollbacks (Stage 15):**
- `PIVOT` → restart from Stage 8 (new hypotheses)
- `REFINE` → restart from Stage 13 (re-run experiments)
- `PROCEED` → advance to Stage 16
- Max 2 recursive pivots (`_pivot_depth` guard)

---

## 4. Data Flow: Full Run

```
CLI (cli.py)
 └─ execute_pipeline(runner.py)
     └─ for stage in STAGE_SEQUENCE:
         └─ execute_stage(executor.py)
             ├─ validate input contracts
             ├─ call stage_impl function
             ├─ validate output contracts
             ├─ MetaClaw PRM gate (if gate stage)
             └─ write stage_health.json + checkpoint.json
```

**Artifact directory per run:**
```
artifacts/rc-{timestamp}-{hash}/
├── checkpoint.json              ← Last completed stage
├── heartbeat.json               ← Watchdog sentinel
├── pipeline_summary.json        ← All stage results
└── stage-{01..23}/
    ├── stage_meta.json
    ├── stage_health.json
    └── [stage-specific files]
```

---

## 5. LLM Routing

**Cost cascade (cheap → premium):**
```
NadirClaw tiers:
  simple_model:  gemini-2.5-flash  ($0.0002/1K)
  mid_model:     gpt-4o-mini       ($0.015/1K)
  complex_model: claude-sonnet-4-6 ($0.03/1K)

Flow per request:
  1. Try simple_model
  2. Quick-eval output quality (0–1 score)
  3. If score >= tier_threshold[0]: accept
  4. Else: try mid_model, eval again
  5. If score >= tier_threshold[1]: accept
  6. Else: use complex_model
```

**Context optimization:** `"safe"` / `"aggressive"` modes strip redundant context (30–70% token savings).

---

## 6. Literature Search

```
search_papers(query, limit, sources)
  ├─ OpenAlex (10K/day)        → list[Paper]
  ├─ Semantic Scholar (1K/5m)  → list[Paper]
  └─ arXiv (1 req/3s)          → list[Paper]
      │
      └─ Deduplicate: DOI → arXiv ID → fuzzy title match
          └─ Sort by citation_count desc → return top-N

Grey literature (grey_search.py):
  bioRxiv, medRxiv, ClinicalTrials.gov, Zenodo, SSRN, DART-Europe

Citation graph (citation_graph.py):
  S2 citations API (primary) → Scholar citedby (fallback)
  + Pure-Python PageRank → most_influential(top_n)
```

**Paper model:**
```python
@dataclass(frozen=True)
class Paper:
    paper_id, title, authors, year, abstract
    venue, citation_count, doi, arxiv_id, url, source
    # Properties: cite_key, to_bibtex(), to_dict()
```

---

## 7. Experiment Execution

```
Modes (config experiment.mode):
  sandbox       → local subprocess (fast)
  docker        → isolated container (reproducible, Windows-safe)
  ssh_remote    → GPU cluster
  colab_drive   → Google Colab
  agentic       → OpenCode multi-file agent

Self-correction loop (self_correcting.py + auto_debugger.py):
  run code → capture stderr → detect error type →
  LLM generates fix → apply → re-run (up to 3 retries)
  ↑ repeated in Stage 13 up to 10 cycles

Windows fixes applied:
  - Process kill: proc.terminate() + proc.kill() (no os.killpg)
  - Docker volumes: _to_docker_path() (backslash → forward slash)
  - --user flag: omitted on Windows (no os.getuid)
  - subprocess: encoding="utf-8" on all 15+ call sites
```

---

## 8. Google Scholar Integration

```
GoogleScholarClient (berb/web/scholar.py):
  - scholarly library (web scraping — no official API)
  - Proxy priority: ScraperAPI > Bright Data > FreeProxies
  - Retry: exponential backoff (2s → 64s) + jitter
  - Auto-disable: 3 consecutive failures → .available = False
  - .reset() to re-enable manually

WebSearchClient.search_scholar() (berb/web/search.py):
  1. GoogleScholarClient (scholarly)
  2. SearXNG engines=["google_scholar","arxiv"]  ← fallback
  3. Generic web search (Tavily/DDG)             ← last resort
```

---

## 9. Bridges & External Integrations

| Bridge | Location | Purpose |
|--------|----------|---------|
| **MnemoMemoryBridge** | `berb/mnemo_bridge/` | Long-horizon memory across runs; stores error→fix mappings |
| **MetaClawBridge** | `berb/metaclaw_bridge/` | PRM quality gating on gate stages; lesson→skill extraction |
| **ReasonerBridge** | `berb/reasoner_bridge/` | Multi-perspective hypothesis evaluation (debate, jury, iterative) |
| **MCP Server** | `berb/mcp/` | Model Context Protocol interface |
| **OpenCode** | `berb/pipeline/opencode_bridge.py` | Multi-file code agent for Stage 10 |
| **Overleaf** | `berb/overleaf/` | LaTeX sync with Overleaf |

---

## 10. Key Config Sections (`config.arc.yaml`)

```yaml
project.mode:     "full-auto" | "semi-auto" | "docs-first"
research.topic:   string
llm.provider:     "anthropic" | "openai" | "openrouter" | "deepseek"
llm.primary_model: string
nadirclaw.enabled: bool
nadirclaw.simple/mid/complex_model: strings
experiment.mode:  "sandbox" | "docker" | "ssh_remote" | "colab_drive"
experiment.repair.enabled: bool
knowledge_base.root: path
security.hitl_required_stages: [5, 9, 20]
```

---

## 11. Presets System

```python
from berb.presets import load_preset, list_presets

preset = load_preset("ml-conference")
# PipelinePreset with: primary_model, sources, experiment_mode,
# paper_format, min_quality_score, max_budget_usd, stage_overrides, ...

list_presets()
# ["biomedical", "food-ai-innovation", "life-sciences-kg",
#  "ml-conference", "nutrition-bioactive", "process-optimization-dt",
#  "rapid-draft"]
```

CLI flag `--preset <name>` is **planned (not yet wired)** — see TODO.md.

---

## 12. SharedResearchMemory

```python
# berb/memory/shared_memory.py
class SharedResearchMemory:
    store(key, value, agent_id, entry_type)
    get_trajectory() → list[MemoryEntry]
    send_message(from_agent, to_agent, content)
    record_code_snapshot(agent_id, code_text, context)
    record_error_fix(agent_id, error, fix, root_cause)
    record_execution_trace(agent_id, trace_event)
```

Used by: executor.py, code_agent.py, self_correcting.py, agents/*.

---

## 13. Review Ensemble

```python
# berb/review/ensemble.py
ReviewEnsemble:
  personas: domain_expert, clarity_reviewer, reproducibility, novelty
  → each scores: novelty, significance, quality, clarity (1-5)
  → aggregate: mean + std + structured feedback items
  → feeds Stage 19 (PAPER_REVISION)
```

---

## 14. Testing

```
tests/
├── conftest.py                  ← Shared fixtures
├── test_berb_executor.py        ← Stage execution (127KB, most comprehensive)
├── test_berb_runner.py          ← Pipeline logic + PIVOT/REFINE
├── test_berb_literature.py      ← Search, dedup, caching
├── test_berb_docker_sandbox.py  ← Docker execution
├── test_figure_agent.py         ← Figure generation
├── test_decision_agent.py       ← PIVOT/REFINE logic
├── test_berb_citation_verify.py ← Citation verification
└── e2e_*.py                     ← Full runs (require API keys)

Markers: @pytest.mark.slow | .e2e | .llm
Run: pytest -m "not slow and not e2e and not llm"
```

---

## 15. Current TODO Priorities

| Group | Status | Key Tasks |
|-------|--------|-----------|
| Windows compatibility | ✅ Done | Process kill, Docker paths, encoding, --user |
| Google Scholar hardening | ✅ Done | Proxy rotation, backoff, health-check, citation graph |
| Preset system (7/17 YAMLs) | 🔄 In Progress | Remaining 10 YAMLs + CLI `--preset` flag |
| HyperAgent implementation | ⏳ P1 | 4 modules with NotImplementedError stubs |
| Citation graph (Group B) | ✅ Done | S2 primary + Scholar fallback + PageRank |
| SearXNG + Firecrawl | ⏳ P0 | Full integration planned |
| Style Fingerprinting | ⏳ P2 | `berb/writing/style_fingerprint.py` |
| Reasoning methods | ⏳ P1 | Counterfactual, pre-mortem, multi-perspective |

Full plan: **TODO.md**

---

## 16. Common Entry Points for Development

```python
# Run pipeline
from berb.pipeline.runner import execute_pipeline

# Search literature
from berb.literature.search import search_papers

# Execute a stage
from berb.pipeline.executor import execute_stage

# Load config
from berb.config import load_config

# Load a preset
from berb.presets import load_preset

# Build citation graph
from berb.literature.citation_graph import get_citation_graph

# Search scholar with fallback
from berb.web.search import WebSearchClient
client = WebSearchClient()
results = client.search_scholar("attention is all you need")
```
