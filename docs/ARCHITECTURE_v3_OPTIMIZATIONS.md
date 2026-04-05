# Berb Architecture Update — Optimization Upgrades

**Version:** 3.0 (Optimization Edition)  
**Date:** 2026-04-01  
**Status:** Phase 1 Complete (6/12 upgrades implemented)  
**Based on:** AIRA2, CAID, Microsoft Copilot, PRBench, HorizonMath research

---

## Executive Summary

This document updates the architecture defined in `ARCHITECTURE_v2.md` with 12 research-backed optimizations from cutting-edge AI research (March 2026). The architecture now includes:

1. **Async Parallel Execution** (AIRA2 + CAID) — 2-4× speedup
2. **Hidden Consistent Evaluation** (AIRA2) — Eliminates evaluation gaming
3. **Council Mode** (Microsoft Copilot) — Multi-model consensus
4. **Physics Code Guards** (PRBench) — -50% code failures
5. **FS-Based Literature** (Long-Context Processors) — 200-400 paper handling
6. **Verifiable Math** (HorizonMath) — 100% verified claims
7. **Evolutionary Search** (AIRA2 + Hive) — Better experiment results
8. **Humanitarian Lens** (Tao & Klowden) — Research integrity
9. **Parallel Writing** (CAID) — Faster paper generation
10. **ReAct Agents** (AIRA2) — Interactive debugging
11. **Critique+Council Config** (Microsoft) — Configurable patterns
12. **Benchmark Framework** (PRBench + DRACO) — External validation

---

## Updated System Architecture

### High-Level Architecture (v3.0)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Berb Research System v3.0                        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          PRESENTATION LAYER                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  CLI         │  │  Web         │  │  Programmatic API            │  │
│  │  Interface   │  │  Dashboard   │  │  (Python SDK)                │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Pipeline Orchestrator                          │   │
│  │  (23-stage state machine with checkpoint/resume)                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  Command     │  │  Event       │  │  Multi-Model                 │  │
│  │  Handler     │  │  Bus         │  │  Collaboration               │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              Async Experiment Pool (NEW)                          │   │
│  │  (AIRA2-inspired parallel execution with CAID isolation)          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          DOMAIN LAYER                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Core Business Logic                            │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │   │
│  │  │ Literature │ │ Experiment │ │ Writing    │ │ Knowledge  │    │   │
│  │  │ Domain     │ │ Domain     │ │ Domain     │ │ Domain     │    │   │
│  │  │ FS-Based   │ │ Async Pool │ │ Council    │ │ Hidden     │    │   │
│  │  │ (NEW)      │ │ (NEW)      │ │ (NEW)      │ │ Eval (NEW) │    │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │   │
│  │  │ Validation │ │ Reasoning  │ │ Review     │ │ Benchmarks │    │   │
│  │  │ Domain     │ │ Methods    │ │ Domain     │ │ (NEW)      │    │   │
│  │  │ HCE (NEW)  │ │ 9 Methods  │ │ Jury       │ │            │    │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      INTEGRATION LAYER                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  Mnemo       │  │  Reasoner    │  │  SearXNG                     │  │
│  │  Bridge      │  │  Bridge      │  │  Client                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  LLM         │  │  Council     │  │  Physics                     │  │
│  │  Router      │  │  Mode (NEW)  │  │  Guards (NEW)                │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE LAYER                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  SQLite      │  │  Redis       │  │  External APIs               │  │
│  │  (local DB)  │  │  (cache)     │  │  (OpenAlex, arXiv, etc.)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  Docker      │  │  Git         │  │  File System                 │  │
│  │  (isolation) │  │  (worktree)  │  │  (literature)                │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## New Architectural Components

### 1. Async Experiment Pool (berb/experiment/)

**Source:** AIRA2 (Meta FAIR) + CAID (CMU)  
**Files:** `async_pool.py`, `isolation.py`, `worker.py`

```
┌─────────────────────────────────────────┐
│      AsyncExperimentPool                │
│  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐   │
│  │ W-0 │  │ W-1 │  │ W-2 │  │ W-3 │   │
│  │Docker│ │Docker│ │Docker│ │Docker│  │
│  └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘   │
│     │        │        │        │       │
│     └────────┴────────┴────────┘       │
│              Queue                      │
└─────────────────────────────────────────┘
```

**Key Features:**
- Decouples decision-making from execution
- 4 workers run in parallel (CAID optimal)
- No synchronization barriers
- Linear throughput scaling
- Isolation modes: docker, worktree, sandbox

**Integration Points:**
- Stage 12 (EXPERIMENT_RUN)
- Stage 13 (ITERATIVE_REFINE)

---

### 2. Hidden Consistent Evaluation (berb/validation/)

**Source:** AIRA2 (Meta FAIR)  
**Files:** `hidden_eval.py`

```
┌─────────────────────────────────────────┐
│   Hidden Consistent Evaluation          │
│                                         │
│  ┌─────────────┐  ┌──────────────┐     │
│  │   Search    │  │  Selection   │     │
│  │  Criteria   │  │   Criteria   │     │
│  │  (visible)  │  │  (visible)   │     │
│  └──────┬──────┘  └──────┬───────┘     │
│         │                │              │
│         └────┬───────┬───┘              │
│              │       │                  │
│         ┌────▼───────▼───┐              │
│         │  Test Criteria │              │
│         │    (HIDDEN)    │              │
│         └────────────────┘              │
└─────────────────────────────────────────┘
```

**Key Features:**
- Three-way criteria split
- Search criteria: visible to agents (improvement loop)
- Selection criteria: visible to agents (final choice)
- Test criteria: NEVER shown (true quality measure)
- Prevents evaluation gaming

**Integration Points:**
- M2 Improvement Loop
- Stage 15 (RESEARCH_DECISION)
- Stage 20 (QUALITY_GATE)

---

### 3. Council Mode (berb/review/)

**Source:** Microsoft Copilot Researcher  
**Files:** `council_mode.py`

```
┌─────────────────────────────────────────┐
│            Council Mode                 │
│                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────┐  │
│  │ Model 1  │  │ Model 2  │  │ModelN│  │
│  │ Report   │  │ Report   │  │Report│  │
│  └────┬─────┘  └────┬─────┘  └──┬───┘  │
│       │             │            │      │
│       └─────────────┴────────────┘      │
│                   │                     │
│            ┌──────▼──────┐              │
│            │ Judge Model │              │
│            │  Synthesis  │              │
│            └─────────────┘              │
└─────────────────────────────────────────┘
```

**Key Features:**
- Parallel multi-model analysis
- Independent report generation
- Agreement/divergence detection
- Consensus scoring (0-1)
- Unique insight extraction

**Integration Points:**
- Stage 7 (SYNTHESIS)
- Stage 8 (HYPOTHESIS_GEN)
- Stage 15 (RESEARCH_DECISION)

---

### 4. Physics Code Guards (berb/experiment/)

**Source:** PRBench (Peking U)  
**Files:** `physics_guards.py`

**Key Features:**
- AST-based static analysis
- 6 anti-pattern detections:
  1. dense_matrix_for_sparse
  2. unvectorized_loops
  3. explicit_kronecker_product
  4. missing_numerical_precision
  5. no_convergence_test
  6. loose_variable_organization
- LLM-based fix suggestions
- Severity levels (critical/warning/info)

**Integration Points:**
- Stage 9 (EXPERIMENT_DESIGN)
- Stage 10 (CODE_GENERATION)
- Stage 12 (EXPERIMENT_RUN)

---

### 5. File-System Literature Processor (berb/literature/)

**Source:** Coding Agents as Long-Context Processors  
**Files:** `fs_processor.py`, `fs_query.py`

**Key Features:**
- Externalizes long-context from attention to filesystem
- Organizes 200-400 papers efficiently
- Query via grep/search tools
- Clustering by topic/year/relevance
- Automated summarization

**File Structure:**
```
workspace/
├── by_topic/           # Clustered by theme
├── by_year/            # Chronological
├── by_relevance/       # Ranked by relevance
├── summaries/          # One-paragraph per paper
├── claims/             # Extracted claims
├── contradictions/     # Identified contradictions
├── methods/            # Method descriptions
└── index.json          # Searchable metadata
```

**Integration Points:**
- Stage 4 (LITERATURE_COLLECT)
- Stage 5 (LITERATURE_SCREEN)
- Stage 6 (KNOWLEDGE_EXTRACT)

---

### 6. Verifiable Math Content (berb/math/)

**Source:** HorizonMath + PRBench  
**Files:** `verification.py`

**Key Features:**
- Computational theorem verification
- Numerical equation testing
- Convergence claim validation
- Boundary condition checking
- Automated proof verification

**Integration Points:**
- Stage 8 (HYPOTHESIS_GEN)
- Stage 9 (EXPERIMENT_DESIGN)
- Stage 17 (PAPER_DRAFT)

---

### 7. Evolutionary Experiment Search (berb/experiment/)

**Source:** AIRA2 + Hive  
**Files:** `evolutionary_search.py`

**Key Features:**
- Population-based experiment search
- Temperature-scaled rank selection
- Mutation and crossover
- Multi-generation evolution
- HCE-guided selection

**Integration Points:**
- Stage 12 (EXPERIMENT_RUN)
- Stage 13 (ITERATIVE_REFINE)
- M2 Improvement Loop

---

### 8. ReAct Experiment Agents (berb/experiment/)

**Source:** AIRA2  
**Files:** `react_agent.py`

**Key Features:**
- Reason→Act→Observe cycles
- Dynamic scoping
- Interactive debugging
- Self-correction within trajectory

**Integration Points:**
- Stage 12 (EXPERIMENT_RUN)
- Stage 13 (ITERATIVE_REFINE)

---

### 9. Parallel Section Writing (berb/writing/)

**Source:** CAID  
**Files:** `parallel_writer.py`

**Key Features:**
- Git-like branch-and-merge
- Dependency-aware section planning
- Parallel independent sections
- Coherence verification

**Integration Points:**
- Stage 17 (PAPER_DRAFT)

---

### 10. Humanitarian Impact Assessment (berb/writing/)

**Source:** Tao & Klowden  
**Files:** `impact_assessment.py`

**Key Features:**
- Contribution type classification
- Broader impact generation
- Understanding advancement check
- Risk assessment

**Integration Points:**
- Stage 21 (KNOWLEDGE_ARCHIVE)
- Stage 22 (EXPORT_PUBLISH)

---

### 11. Benchmark Framework (berb/benchmarks/)

**Source:** PRBench + HorizonMath + DRACO  
**Files:** `evaluation_framework.py`

**Key Features:**
- PRBench physics reproduction
- DRACO evaluation framework
- HorizonMath verification
- External benchmark comparison

**Integration Points:**
- Post-pipeline quality assessment
- Continuous improvement tracking

---

## Updated Module Structure

```
berb/
├── experiment/              # ✅ Enhanced
│   ├── async_pool.py       # NEW: AIRA2 parallel pool
│   ├── isolation.py        # NEW: CAID isolation
│   ├── worker.py           # NEW: Worker implementation
│   ├── physics_guards.py   # NEW: PRBench guards
│   ├── evolutionary_search.py  # NEW: Evolutionary search
│   ├── react_agent.py      # NEW: ReAct agents
│   ├── runner.py           # Updated: Pool integration
│   └── ...
├── validation/              # ✅ Enhanced
│   ├── hidden_eval.py      # NEW: HCE (AIRA2)
│   ├── claim_verification.py
│   └── ...
├── review/                  # ✅ Enhanced
│   ├── council_mode.py     # NEW: Council (Microsoft)
│   ├── ensemble.py
│   └── ...
├── literature/              # ✅ Enhanced
│   ├── fs_processor.py     # NEW: FS-based processing
│   ├── fs_query.py         # NEW: Query engine
│   └── ...
├── math/                    # ✅ Enhanced
│   ├── verification.py     # NEW: Computational verification
│   └── ...
├── writing/                 # ✅ Enhanced
│   ├── parallel_writer.py  # NEW: CAID parallel writing
│   ├── impact_assessment.py# NEW: Humanitarian lens
│   └── ...
├── benchmarks/              # ✅ Enhanced
│   ├── evaluation_framework.py # NEW: External benchmarks
│   └── ...
└── ...
```

---

## Updated Design Patterns

### New Patterns Introduced:

| Pattern | Upgrade | Usage |
|---------|---------|-------|
| **Worker Pool** | Async Pool | Parallel experiment execution |
| **Isolation** | Async Pool | Docker/worktree/sandbox isolation |
| **Three-Way Split** | HCE | Search/selection/test criteria |
| **Council** | Council Mode | Multi-model synthesis |
| **Static Analysis** | Physics Guards | AST-based code quality |
| **External Context** | FS Literature | Filesystem vs attention |
| **Evolutionary** | Evo Search | Population-based optimization |
| **ReAct** | ReAct Agents | Reason-act-observe cycles |
| **Branch-and-Merge** | Parallel Writing | Git-like section writing |

---

## Updated Architecture Principles

### Original Principles (v2.0):
1. Hexagonal Architecture
2. Functional Core / Imperative Shell
3. Clean Layer Boundaries
4. Config-Driven Behavior
5. Toggleable Features

### New Principles (v3.0):
6. **Parallel-First Execution** — Async where possible
7. **Hidden Evaluation** — Decouple optimization from selection
8. **Multi-Model Consensus** — Critical decisions via council
9. **Domain-Specific Guards** — Physics-aware, math-aware, etc.
10. **Externalized Context** — Filesystem over attention for large contexts
11. **Evolutionary Improvement** — Population-based search
12. **Verification-First** — Computational verification before acceptance

---

## Performance Metrics

### Expected Improvements:

| Metric | Baseline (v2.0) | Target (v3.0) | Improvement |
|--------|-----------------|---------------|-------------|
| **Experiment throughput** | 1× | 2-4× | +100-300% |
| **Literature capacity** | 70-100 papers | 200-400 papers | +233% |
| **Code failure rate** | Baseline | -50% | -50% |
| **Math accuracy** | Unverified | 100% verified | +100% |
| **Decision quality** | Single-model | Multi-model consensus | +35-45% |
| **Evaluation gaming** | Possible | Eliminated | -100% |
| **Cost per paper** | $0.40-0.70 | $0.40-0.70 | Maintain |

---

## Configuration Updates

### New Configuration Sections:

```yaml
# config.berb.yaml

# Multi-Model Collaboration
multi_model:
  critique:
    enabled: true
    stages: [17, 19]
    generator: "claude-3-sonnet"
    evaluator: "gpt-4o"
  
  council:
    enabled: true
    stages: [7, 8, 15]
    models: ["claude-opus", "gpt-4o", "deepseek-v3.2"]
    judge: "claude-sonnet"

# Hidden Consistent Evaluation
hidden_eval:
  enabled: true
  use_in_improvement_loop: true
  use_for_selection: true

# Async Experiment Pool
experiment_pool:
  enabled: true
  max_workers: 4  # CAID optimal
  isolation: "docker"
  gpu_enabled: true
```

---

## Integration Roadmap

### Phase 1: Foundation (✅ Complete)
- [x] Async Parallel Pool
- [x] Hidden Consistent Evaluation
- [x] Council Mode
- [x] Physics Code Guards
- [x] Configuration Updates

### Phase 2: Advanced Features (In Progress)
- [ ] FS-Based Literature Processor
- [ ] Verifiable Math Content
- [ ] ReAct Experiment Agents
- [ ] Evolutionary Search
- [ ] Parallel Section Writing
- [ ] Humanitarian Impact
- [ ] Benchmark Framework

### Phase 3: Integration & Testing (Planned)
- [ ] Full pipeline integration
- [ ] Performance benchmarks
- [ ] Documentation updates
- [ ] Migration guide

---

## References

### Research Papers:
1. **AIRA2** (Meta FAIR — arXiv:2603.26499) — Async pool, HCE, ReAct
2. **CAID** (CMU — arXiv:2603.21489) — Isolation, parallel writing
3. **Microsoft Copilot** — Council mode, critique pattern
4. **PRBench** (Peking U — arXiv:2603.27646) — Physics guards
5. **HorizonMath** (arXiv:2603.15617) — Math verification
6. **Long-Context Processors** (arXiv:2603.20432) — FS literature
7. **Hive** (arXiv:2603.26359) — Evolutionary search
8. **Tao & Klowden** — Humanitarian lens

### Related Documentation:
- `ARCHITECTURE_v2.md` — Base architecture
- `BERB_OPTIMIZATION_PLAN_v1.md` — Optimization specification
- `IMPLEMENTATION_STATUS.md` — Implementation tracking
- `TODO_OPTIMIZATION.md` — Detailed implementation tasks

---

**Berb v3.0 — Research, Refined.** 🧪✨

**Author:** Georgios-Chrysovalantis Chatzivantsidis  
**Last Updated:** 2026-04-01
