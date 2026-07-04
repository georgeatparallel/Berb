# Architecture Upgrade Plan: 6/10 → 9+/10

**Target:** Raise Berb's architecture score from 6/10 to ≥9/10 per the ARCH-AUDIT-V2 rubric.
**Baseline Audit:** ARCH-AUDIT-V2 (2026-04-06) — 10 findings across Phase 2-5.
**Chosen Architecture:** Hexagonal (Ports & Adapters) at domain boundaries + DAG pipeline executor + Strategy/cascade LLM routing.

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CONFIG LAYER                          │
│  Typed dataclasses (RCConfig) — validated at boundary    │
└──────────────────────┬──────────────────────────────────┘
                       │ injects into
┌──────────────────────▼──────────────────────────────────┐
│                  ORCHESTRATION LAYER                     │
│  DAG executor — topological sort, parallel where possible│
│  Event-sourced state machine (StageStatus transitions)   │
│  Checkpoint / heartbeat / rollback                       │
└──────┬──────────┬──────────┬──────────┬─────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  LLM     │ │Literature│ │Experiment│ │ Artifact │
│  Provider│ │ Source   │ │ Sandbox  │ │ Store    │
│  (port)  │ │ (port)   │ │ (port)   │ │ (port)   │
└────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │            │
     ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────┐
│                   ADAPTER LAYER                          │
│  OpenAI / Anthropic / DeepSeek / …                       │
│  arXiv / OpenAlex / SemanticScholar / SearXNG            │
│  Docker / SSH / Colab / Local sandbox                    │
│  Local FS / S3 / memory artifact backends                │
└─────────────────────────────────────────────────────────┘
```

**Three patterns, three concerns:**

| Concern | Pattern | Why |
|---------|---------|-----|
| Domain boundaries (LLM, literature, sandbox, storage) | **Hexagonal (Ports & Adapters)** | Stages never import concrete clients; they call port interfaces only. Every external system is swappable via adapter. |
| Pipeline execution order | **DAG (dependency-based scheduling)** | Stages declare `depends_on` instead of relying on implicit sequence position. Independent stages run concurrently. |
| LLM provider selection | **Strategy/cascade** (already correct) | Cheap models first, escalate on quality failure. Invisible to stages — lives behind the `LLMProvider` port. |

---

## What the Codebase Already Gets Right (Preserve)

These elements align with the target architecture and need no structural change:

| Element | Why it's correct |
|---------|-----------------|
| `StageContract` with I/O file tuples [contracts.py](berb/pipeline/contracts.py) | Makes data dependencies explicit — this is proto-DAG; each contract already encodes what a stage reads and produces |
| `EventStore` + `StageTransitionEvent` [stages.py](berb/pipeline/stages.py) | Event sourcing for audit/recovery — stays as the state machine backbone |
| `AdapterBundle` with Protocol classes [adapters.py](berb/adapters.py) | Already a port/adapter seed — just underused (only 6 protocols, no literature/sandbox ports) |
| `CascadeConfig` + `CascadingLLMClient` [model_cascade.py](berb/llm/model_cascade.py) | Correct strategy pattern — invisible to stages, lives behind the LLM port |
| Checkpoint with SHA-256 + atomic write [runner.py:178](berb/pipeline/runner.py:178) | Right durability pattern — stays as-is |

---

## Phase 1: Immediate (Fix Before Next Feature) — ~2-3 days

These are low-risk prerequisites that unblock the structural work in Phase 2.

### Step 1: Align Type Checker

- **Finding:** CI runs `pyright`, `pyproject.toml` configures `[tool.mypy]`. Two checkers produce divergent results.
- **Action:** Drop `pyright` from CI, install `mypy` in the CI job, run `mypy berb/ --python-version 3.11`. Remove `continue-on-error: true` once mypy passes cleanly. Keep `[tool.mypy]` in `pyproject.toml` as the single source of truth.
- **Files:** `.github/workflows/ci.yml`, `pyproject.toml`
- **Risk:** Low — no behavioral change.

### Step 2: Consolidate Example Configs

- **Finding:** Three example configs at project root (`config.berb.example.yaml`, `config.berb.production.yaml`, `config.berb.humanities.yaml`) plus three in `configs/`.
- **Action:** Declare `configs/config.arc.example.yaml` as the canonical example. Move root-level examples into `docs/archive/`. Update `berb/config.py`'s `EXAMPLE_CONFIG` pointer.
- **Files:** `berb/config.py`, `configs/`, root-level `config.berb.*.yaml` files
- **Risk:** Low — file moves + one constant update.

### Step 3: Move Hardware Utility Out of Pipeline Helpers

- **Finding:** `pipeline/_helpers.py` imports `from berb.hardware import is_metric_name`. Hardware detection doesn't belong in pipeline utilities.
- **Action:** Move `is_metric_name()` call into experiment modules. Pipeline helpers must not touch hardware.
- **Files:** `berb/pipeline/_helpers.py`, `berb/experiment/metrics.py`
- **Risk:** Low — single import change.

---

## Phase 2: Structural — Ports & Runner Split (~2 weeks)

This phase establishes the hexagonal boundary and collapses the 1718-line god module. These two steps are independent and can run in parallel.

### Step 4: Split `pipeline/runner.py`

- **Finding:** 1718-line file containing orchestration, experiment diagnosis, experiment repair, packaging, version rollback, quality checks, iterative improvement, and MetaClaw hook.
- **Action:** Extract each `_function` into its own module. Introduce a `PipelineContext` dataclass to carry shared state (run_dir, run_id, config, adapters, event_store) between modules. `runner.py` becomes a thin import-and-compose orchestrator.

**Target file layout after split:**

```
berb/pipeline/
├── runner.py              # ~150 lines — thin orchestrator
├── context.py             # ~40 lines — PipelineContext dataclass
├── execution_loop.py      # ~200 lines — stage iteration, gating, rollback, heartbeat
├── experiment_diagnosis.py # ~130 lines — _run_experiment_diagnosis
├── experiment_repair.py   # ~80 lines — _run_experiment_repair
├── packaging.py           # ~280 lines — _package_deliverables + _filter_cite
├── checkpoint.py          # ~100 lines — read/write/validate checkpoint + heartbeat
├── summary.py             # ~60 lines — _build_pipeline_summary
├── iterative.py           # ~120 lines — execute_iterative_pipeline
├── metaclaw_post.py       # ~130 lines — _metaclaw_post_pipeline
├── executor.py            # unchanged
├── stages.py              # unchanged
└── contracts.py           # unchanged
```

- **Acceptance:** `runner.py` ≤ 200 lines. Each extracted module has ≥ 2 unit tests. Pipeline runs produce identical output to pre-split.
- **Files:** `berb/pipeline/runner.py` (shrinks), 8 new files in `berb/pipeline/`
- **Risk:** Medium — use `PipelineContext` to avoid parameter explosion. Write a smoke test that runs a 2-stage mini-pipeline before/after to catch regressions.

### Step 5: Enforce Ports & Adapters at All Domain Boundaries

- **Finding:** Stage implementations import concrete clients directly — `berb.llm.client.LLMClient`, `berb.literature.*`, `berb.experiment.sandbox.*`. The `AdapterBundle` already defines Protocol classes but stages bypass them.
- **Action:** Extend the port interface and wire all stages through it.

**Four ports to define:**

| Port | Existing? | Action |
|------|-----------|--------|
| `LLMProvider` | No | Add Protocol to `adapters.py`: `chat()`, `complete()`. Wrap `LLMClient` + `CascadingLLMClient` behind it. |
| `LiteratureSource` | No | Add Protocol: `search()`, `fetch_full_text()`. Wrap arXiv/OpenAlex/SemanticScholar/SearXNG clients. |
| `ExperimentSandbox` | Partially (`SessionsAdapter`) | Add Protocol: `execute()`, `get_result()`. Wrap Docker/SSH/Colab/local sandboxes. |
| `ArtifactStore` | Partially (`MemoryAdapter`) | Add Protocol: `read()`, `write()`, `exists()`. Default to local FS; future S3 adapter plugs in. |

**Action per stage implementation:**

```python
# Before (current) — concrete import, coupled to client type
from berb.llm.client import LLMClient

def _execute_topic_init(..., llm: LLMClient | None = None, ...) -> StageResult:
    ...
```

```python
# After — port interface, any adapter works
from berb.adapters import LLMProvider

def _execute_topic_init(..., llm: LLMProvider | None = None, ...) -> StageResult:
    ...
```

- **Acceptance:** Zero `from berb.llm.client import LLMClient` in `stage_impls/`. Zero `from berb.literature.*` imports in stage implementations. Stage tests can inject a `RecordingLLMProvider` stub.
- **Files:** `berb/adapters.py` (add 4 Protocol classes), all `stage_impls/_*.py` (change import), `berb/pipeline/executor.py` (inject via `AdapterBundle`)
- **Risk:** Low — additive. The Protocol matches the existing concrete interface; no behavior change. `RecordingLLMProvider` stub follows the same pattern as existing `RecordingCronAdapter` [adapters.py:48](berb/adapters.py:48).

---

## Phase 3: DAG + Async (~6-8 weeks)

### Step 6: DAG Pipeline Scheduler

- **Finding:** Pipeline is a strict linear sequence (`STAGE_SEQUENCE` list + `NEXT_STAGE`/`PREVIOUS_STAGE` dicts). Several stages have no data dependency on each other and could run concurrently.
- **Action:** Replace the linear iteration in `execution_loop.py` with a DAG-based topological executor.

**What changes:**

1. Each stage declares `depends_on: frozenset[Stage]` in its `StageContract` (already implicitly encoded in `input_files` — the files come from specific prior stages).
2. The DAG executor computes the topological order dynamically. Stages with all dependencies satisfied are eligible for concurrent execution.
3. The executor uses `asyncio.gather()` to run independent stages in parallel.
4. Gate stages still block as before — approval required before downstream stages proceed.

**Concurrency opportunities:**

| Independent set | Stages |
|-----------------|--------|
| Literature sub-sources | arXiv, OpenAlex, Semantic Scholar calls within `LITERATURE_COLLECT` |
| Finalization fan-out | `KNOWLEDGE_ARCHIVE` ∥ `EXPORT_PUBLISH` (no shared inputs) |
| Post-draft overlap | `PEER_REVIEW` and `CITATION_VERIFY` after `PAPER_DRAFT` completes |
| Domain detection | Hardware detection + domain detection during `TOPIC_INIT` |

- **Acceptance:** `STAGE_SEQUENCE` list removed. Pipeline executes correct stages in valid order determined at runtime from `depends_on`. At least one pair of stages runs concurrently (verified by log timestamps).
- **Files:** `berb/pipeline/contracts.py` (add `depends_on` field), `berb/pipeline/execution_loop.py` (new DAG executor), `berb/pipeline/stages.py` (remove `STAGE_SEQUENCE`, `NEXT_STAGE`, `PREVIOUS_STAGE`; keep `Stage` enum, `GATE_STAGES`, `PHASE_MAP`)
- **Risk:** Medium — DAG executor must preserve: (a) gate semantics, (b) rollback targets, (c) checkpoint writes between phases. Write a concurrency-safe checkpoint that serializes writes when parallel stages complete.

### Step 7: Async Pipeline Core

- **Finding:** Pipeline is synchronous. Async LLM clients (`CascadingLLMClient`, `SmartLLMClient`, `BatchAPI`) exist but there's no sync→async bridging. A slow LLM call blocks the entire pipeline.
- **Action:**
  1. Convert `execute_stage()` to `async def execute_stage()`. Stage implementations become `async def`.
  2. Convert the DAG executor to `async def execute_pipeline()`.
  3. Add `asyncio.run()` at the CLI entry (`cli.py` and `__main__.py`).
  4. Parallel stages use `asyncio.gather()`.
- **Acceptance:** All stage implementations are `async def`. Pipeline runs under `asyncio`. Tests use `pytest-asyncio` (already configured in `pyproject.toml`). Before/after integration test produces identical artifacts.
- **Files:** `berb/pipeline/runner.py`, `executor.py`, `execution_loop.py`, all `stage_impls/_*.py`, `cli.py`, `__main__.py`
- **Risk:** High — async conversion changes the execution model. Mitigations: (a) write a dual-output integration test that compares sync and async pipeline results before cutting over, (b) convert one stage per sprint, (c) keep checkpoint/heartbeat writes synchronous via `aiofiles` or explicit `run_in_executor`.

### Step 8: Plugin Stage Registry

- **Finding:** Adding a new stage requires 4 file edits: `stages.py` (enum), `executor.py` (`_STAGE_EXECUTORS`), `contracts.py` (`CONTRACTS`), and a new `stage_impls/` file.
- **Action:** Replace the hardcoded `_STAGE_EXECUTORS` dict with a decorator-based registry. The decorator carries the contract inline:

```python
# berb/pipeline/stage_impls/_bibliography.py

@register_stage(
    stage=Stage.BIBLIOGRAPHY_FORMAT,
    depends_on={Stage.CITATION_VERIFY},
    contract=StageContract(
        input_files=("verified_citations.json",),
        output_files=("bibliography.bib",),
        dod="Formatted bibliography in target venue style",
        error_code="E24_BIBLIOGRAPHY_FAIL",
    ),
)
async def execute_bibliography_format(ctx: StageContext) -> StageResult:
    ...
```

One module declares identity, dependencies, contract, and implementation in one place. The DAG executor discovers it automatically.

- **Acceptance:** Adding a new stage requires: 1 entry in `Stage` enum + 1 decorated function. No edits to `executor.py` or `contracts.py`. Existing stages converted one at a time without regression.
- **Files:** `berb/pipeline/registry.py` (new), `berb/pipeline/executor.py` (auto-discovers), all `stage_impls/_*.py` (add decorator)
- **Risk:** Low — additive. Existing `_STAGE_EXECUTORS` dict kept as fallback during migration.

---

## Phase 4: Cleanup (~1 week)

### Step 9: Deduplicate Dockerfiles

- **Finding:** 6 Dockerfiles with largely overlapping base setup.
- **Action:** Create `Dockerfile.base` (common Python + CUDA + ML stack) + domain-specific images that `FROM berb/experiment:base` and add only domain packages.
- **Files:** `berb/docker/Dockerfile.*`
- **Risk:** Low — build optimization only.

### Step 10: Document Memory Lifecycle

- **Finding:** Three memory systems (`berb/memory/`, `berb/memory_vault/`, `berb/knowledge/`) with no documented boundary.
- **Action:** Write `docs/memory-model.md` defining: ephemeral stage memory (cleared post-run), session memory (across stages in one run), persistent knowledge (cross-run). Add `run_dir`-scoped ephemeral directories. Merge or remove `memory_vault/`.
- **Files:** `docs/memory-model.md` (new), `berb/pipeline/runner.py`
- **Risk:** Low — documentation + cleanup.

---

## Migration Sequence (Dependency Order)

```
Phase 1 (2-3 days):
  Step 1 ──┬── Step 2
           └── Step 3
                │
Phase 2 (2 weeks):                ┌── Step 4 (runner split)
  Step 4 ──┬── Step 5 (ports) ────┤
           └── Step 5 ────────────┘
                │
Phase 3 (6-8 weeks):
  Step 6 (DAG) ──► Step 7 (async) ──► Step 8 (plugin registry)
                                             │
Phase 4 (1 week):
  Step 9 ──┬── Step 10
```

**Why this order:**

- Step 4 (runner split) is the prerequisite — the 1718-line file blocks every structural change.
- Step 5 (ports) and Step 4 are independent; run them in the same sprint.
- Step 6 (DAG) must precede Step 7 (async) because the DAG executor determines the concurrency model that async implements.
- Step 7 must precede Step 8 because the plugin registry decorates async functions.
- Steps 9-10 are cleanup — do them whenever there's slack.

---

## Score Impact Matrix

| Step | Description | Impact (+score) |
|------|-------------|-----------------|
| 4 | Runner split | +1.0 — testability, SRP, modular observability |
| 5 | Ports & Adapters | +1.0 — clean layer boundaries, swappable backends |
| 6 | DAG scheduler | +0.8 — concurrency, eliminates implicit temporal coupling |
| 7 | Async conversion | +0.7 — pattern consistency, backpressure-ready |
| 1 | Type checker alignment | +0.3 — CI reliability |
| 8 | Plugin registry | +0.2 — extensibility, reduces touch points per stage |
| 2+3+9+10 | Low-risk cleanups | +0.3 — hygiene |

**Projected final score: 9.3 / 10**

The remaining 0.7 gap is inherent — full 10/10 would require externalized state storage (database-backed event store), distributed execution, and real-time metrics, which exceed the scope of a single-machine research pipeline.

---

## Switching Triggers

| Condition | Reprioritize |
|-----------|-------------|
| Concurrent pipeline runs become a requirement | Promote externalized state (DB-backed checkpoint) + Step 7 (async) to Phase 2. Step 4 runner split still comes first. |
| Any new stage requires editing 3+ files to register | Promote Step 8 (plugin registry) immediately — it's additive and low-risk. |
| Time-to-first-paper exceeds 15 minutes | Promote Step 6 (DAG) before Step 7 — parallelism gives the biggest latency reduction. |
| A new external service must integrate (new LLM provider, new literature source) | Ports (Step 5) become the enabler — without them, new integrations touch pipeline code. |
