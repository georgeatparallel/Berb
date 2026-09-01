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
| `berb/llm/` | LLM providers, model routing, cost optimization (caching, batching, cascading) | yes |
| `berb/literature/` | arXiv, OpenAlex, Semantic Scholar, novelty scoring, PDF ingestion, Zotero | yes |
| `berb/experiment/` | Sandboxed code execution (local, Docker, SSH, Colab), tree search, validation | yes |
| `berb/agents/` | Benchmark agent, code searcher, figure critique agent | yes |
| `berb/review/` | 5-reviewer + Area Chair peer review ensemble | yes |
| `berb/integrity/` | Claim manifests, evidence tracking, finding reproduction | partial — `integrity.eval.finding_reproduction` is unwired |
| `berb/memory/` | Embeddings, retrieval, shared memory coordination | partial — `memory.embeddings`/`memory.retriever` are used by `review/ensemble.py` (review-diversity scoring); `memory.shared_memory` has no wired caller |

Unwired capabilities that the docs used to claim as live: SearXNG
(`literature/searxng_client.py`), grey literature (`literature/grey_search.py`),
multimodal figure extraction (`literature/multimodal_search.py`),
self-correcting simulation (`experiment/self_correcting.py`), and the
auto-debugger (`experiment/auto_debugger.py`). All are present and tested but
have no importer on any pipeline path — they do not run.

### Bridges (External Integrations)

- `berb/mnemo_bridge/` — Mnemo Cortex memory
- `berb/metaclaw_bridge/` — MetaClaw skill injection
- `berb/reasoner_bridge/` — ARA reasoning patterns
- `berb/mcp/` — MCP server interface

### Configuration

Run `berb setup` (or `berb init`) to generate `config.arc.yaml` from the example template. The CLI auto-detects `config.arc.yaml` or `config.yaml`; pass `--config <path>` to override. Key sections:
- `llm.provider` / `llm.primary_model` — LLM backend selection
- `experiment.mode` — `sandbox | docker | ssh_remote | colab_drive`
- `metaclaw_bridge.enabled` — Enable/disable MetaClaw integration

LLM prompts are centralized in `prompts.default.yaml` (~150 KB).

### LLM Routing

`berb/llm/nadirclaw_router.py` (used by `berb/llm/smart_client.py` when `config.nadirclaw.enabled`) optimizes model selection and context by cost. `berb/llm/extended_router.py` defines a role-based `ExtendedRouter`, but its provider creation is a stub (`_MockProvider`, per its own docstring) and it is not imported anywhere under `berb/pipeline/` — it is not live infrastructure (verified via `python scripts/check_reachability.py`; see `tasks/ars_integration_plan.md` W5 for the finding that motivated this correction). Supported providers, via `berb.llm.create_llm_client()`: OpenAI, Anthropic, DeepSeek, Perplexity, xAI, OpenRouter, MiniMax.

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
