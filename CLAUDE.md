# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable)
pip install -e .
pip install -e ".[all]"        # all optional deps
pip install -e ".[dev]"        # dev/test deps only

# CLI
berb setup                     # interactive config
berb run --topic "..." --auto-approve
berb run --topic "..." --from-stage PAPER_OUTLINE
berb doctor                    # health check

# Tests
pytest tests/                              # all tests
pytest tests/test_berb_executor.py         # single file
pytest -m "not slow"                       # skip slow
pytest -m "not slow and not e2e and not llm"  # unit only
pytest --cov=berb tests/                   # with coverage
```

## Architecture

Berb is a **23-stage autonomous research pipeline** that turns a single research idea into a publication-ready paper. The pipeline runs as a Python package (`berb/`) with a CLI entry point at `berb/cli.py`.

### Pipeline Phases

```
Phase A: Scoping (1-2)       Phase E: Execution (12-13)
Phase B: Literature (3-6)    Phase F: Analysis (14-15)
Phase C: Synthesis (7-8)     Phase G: Writing (16-19)
Phase D: Design (9-11)       Phase H: Finalization (20-23)
```

Stage definitions live in `berb/pipeline/stages.py`; implementations in `berb/pipeline/stage_impls/` (one file per phase). `berb/pipeline/runner.py` orchestrates stage sequencing; `berb/pipeline/executor.py` handles individual stage execution.

### Key Subsystems

Wired = reachable from `berb run` / `berb serve`. Verify with
`python scripts/check_reachability.py`.

| Module | Responsibility | Wired |
|--------|---------------|-------|
| `berb/llm/` | LLM providers, model routing, cost optimization, image input | partial, plus a public API surface (`berb.llm.__all__`) that is a supported contract — `client`, `smart_client`, `nadirclaw_router`, `cost_tracker`, `prompt_cache`, `vision` and `model_cascade` are live. Batching (`batch_api`), speculative execution (`speculative_gen`), `adaptive_temp`, `structured_outputs` and `eval_dataset` are parked (D-08) |
| `berb/literature/` | arXiv, OpenAlex, Semantic Scholar, novelty scoring, PDF ingestion, Zotero | yes — plus a public API surface (`berb.literature.__all__`) that is a supported contract, covered by `tests/test_public_api_contract.py` rather than by internal callers |
| `berb/experiment/` | Sandboxed code execution (local, Docker, SSH, Colab), tree search, validation | partial — sandboxes, `search/` (Stage 12) and `validator` are live, and `plot_verdict` now feeds the figure gate. `compute_guard`, `progress`, `evolutionary_search`, `self_correcting`, `harness_template` and `evaluators/` are parked (D-05); `react_agent` and `split_policy` await wiring |
| `berb/agents/` | Benchmark agent, code searcher, figure critique agent | yes |
| `berb/review/` | 5-reviewer + Area Chair peer review ensemble | yes |
| `berb/integrity/` | Claim manifests, evidence tracking, citation anchors, revision guards | partial — those are live; `integrity/eval/hidden_eval.py` (HCE) is parked (D-05) |
| `berb/research/` | Research-direction state (`world_model`) and the cyclic discovery loop over stages 7-15 | yes — behind `research.discovery.enabled` (default off). Pipeline-facing half is `berb/pipeline/discovery.py` |
| `berb/memory/` | Embeddings, retrieval, shared memory coordination | partial — `embeddings`/`retriever` are used by `review/ensemble.py` for review-diversity scoring. `shared_memory` and the three per-stage memories are parked (D-07); `shared_memory`'s only importer was the parked `experiment/self_correcting.py` |

**Dead-code accounting.** `scripts/check_reachability.py` runs in CI as a
ratchet (`.github/workflows/ci.yml`, Lint job). Modules that are intentionally
unreachable live in `.reachability-allowlist`, split into EXEMPT (correctly not
pipeline-reachable) and PARK (debt on a 90-day clock, two strikes then delete).
Never raise the ceiling to make a build pass. Method and per-module verdicts:
`tasks/dead_code_wiring_plan.md` and the `tasks/w*_triage.md` docs.

**`from berb.literature import ...` is a supported public API** (decided
2026-09-02). `scripts/check_reachability.py` treats the modules behind that
package's `__all__` as entry points, so a published-but-internally-unused module
is not reported dead. `tests/test_public_api_contract.py` asserts every exported
name resolves — the contract is exempt from the dead-code gate, so that test is
what stops it rotting. Adding a package to `PUBLIC_API_PACKAGES` is a product
decision, not a way to quieten the gate.

`from berb.llm import ...` is a supported contract on the same terms (decided
2026-09-02). Both packages are in `PUBLIC_API_PACKAGES` and both are covered by
the contract test.

**Image input** lives in `berb/llm/vision.py` (added 2026-09-02). Build a
multimodal message with `image_message(text, [path])`; it produces a
provider-neutral part list that `LLMClient` encodes per wire format —
`image_url` for chat-completions, `input_image` for the Responses API, a
base64 `source` block for the Anthropic adapter. Only inline base64 is
supported; remote image URLs are deliberately out of scope.
`model_supports_vision()` is the first and only reader of the
`supports_vision` flag that `openrouter_models_data.py` declares on 173 of its
335 models, and `LLMClient.chat` refuses an image for any model the catalogue
marks text-only (uncatalogued models fail open). This unblocked
`experiment/plot_verdict.VLMPlotCritic`, which is selected over the pixel-only
critic when `experiment.figure_agent.vision_model` is set. Refresh the
catalogue with `scripts/refresh_openrouter_models.py --diff`; the model list
should be fetched, not hand-edited.

**LLM cost cascading** is `berb/llm/model_cascade.py`, behind `cascade.enabled`
(default off). It tries a cheap model and escalates only when a quality
evaluator scores the answer below that rung's threshold. Restored from
`9d026a1` on 2026-09-02 without its in-process response cache (the same
mechanism `prompt_cache.py` had already removed for having no repeat calls),
without `MODEL_COSTS`/`cost_saved_estimate` (a duplicate table and a savings
figure that was never computed), and synchronous rather than async. The
cascade's value rests entirely on its evaluator: read
`CascadingLLMClient.get_stats()["cascade_exits"]` before trusting it.

**The research-direction loop** is `berb/research/discovery_loop.py` plus
`berb/pipeline/discovery.py`, behind `research.discovery.enabled` (default
off). `pipeline/iterative.py` loops stages 16-22 — how a result is written up;
this loops stages 7-15 — *which* result to pursue. Restored from `24eefec` on
2026-09-02 with its task-execution stub replaced by an injected `TaskExecutor`;
the pipeline supplies one that re-runs the slice per candidate direction and
promotes the winner's artifacts. Cost scales as `max_cycles x width` slice runs.

Unwired capabilities that the docs used to claim as live: SearXNG
(`literature/searxng_client.py`), grey literature (`literature/grey_search.py`),
multimodal figure extraction (`literature/multimodal_search.py`) and
self-correcting simulation (`experiment/self_correcting.py`). All are present
and tested but have no importer on any pipeline path — they do not run, and are
parked in `.reachability-allowlist` with a revisit date.

`experiment/code_agent.py` and its `config.experiment.cli_agent` section were
deleted (2026-09-02, D-09): 836 loc with no importer on any pipeline path, and
the sole reader of that config. The occupied seam is `pipeline/code_agent.py`,
which reads `config.experiment.code_agent` — a different, live object. Its S0-8
env-stripping test now asserts against `sandbox.safe_subprocess_env` directly.

`experiment/auto_debugger.py`, `config/wizard.py`, `llm/retry_utils.py`,
`llm/extended_router.py` and `pipeline/asyncio_utils.py` were deleted
(2026-09-02, W1/W2/W4): each duplicated a seam already occupied by wired code —
respectively `pipeline/experiment_repair.py`, `wizard/quickstart.py`,
`LLMClient._call_with_retry`, `llm/nadirclaw_router.py`, and `runner.py`'s own
`asyncio.gather`/`to_thread` handling. `experiment/plot_verdict.py` is now wired:
it produces the `is_buggy_plots` verdict that `experiment/search/scoring.py`
gates on, which nothing had been setting.

### Bridges (External Integrations)

- `berb/metaclaw_bridge/` — MetaClaw skill injection (wired)
- `berb/mcp/` — MCP server interface (wired)
- `berb/mnemo_bridge/` — Mnemo Cortex memory — **parked** (D-08), no in-repo consumer
- `berb/reasoner_bridge/` — ARA reasoning patterns — **parked** (D-08), no in-repo consumer

### Configuration

Run `berb setup` (or `berb init`) to generate `config.arc.yaml` from the example template. The CLI auto-detects `config.arc.yaml` or `config.yaml`; pass `--config <path>` to override. Key sections:
- `llm.provider` / `llm.primary_model` — LLM backend selection
- `experiment.mode` — `sandbox | docker | ssh_remote | colab_drive`
- `metaclaw_bridge.enabled` — Enable/disable MetaClaw integration

LLM prompts are centralized in `prompts.default.yaml` (~150 KB).

### LLM Routing

`berb/llm/nadirclaw_router.py` (used by `berb/llm/smart_client.py` when `config.nadirclaw.enabled`) optimizes model selection and context by cost — it is the only live router. `berb/llm/extended_router.py` was deleted on 2026-09-02 (W4): its `_create_provider` returned a `_MockProvider` ("In production, this would create the actual provider instance"), nothing under `berb/pipeline/` imported it, and its only real consumer was a test mocking against it. Supported providers, via `berb.llm.create_llm_client()`: OpenAI, Anthropic, DeepSeek, Perplexity, xAI, OpenRouter, MiniMax.

### Testing Conventions

- Test files mirror module names: `test_berb_literature.py` → `berb/literature/`
- Markers: `@pytest.mark.slow`, `@pytest.mark.e2e`, `@pytest.mark.llm`
- `e2e_*.py` files require real LLM API keys
- `tests/conftest.py` contains shared fixtures

## Workflow Orchestration

### 1. Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately – don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes – don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management
1. **+*Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **+*Verify Plan**: Check in before starting implementation
3. **+*Track Progress**: Mark items complete as you go
4. **+*Explain Changes**: High-level summary at each step
5. **+*Document Results**: Add review section to `tasks/todo.md`
6. **+*Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles
- **+*Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **+*Root Causes**: Find root causes. No temporary fixes. Senior developer standards.
- **+*Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
