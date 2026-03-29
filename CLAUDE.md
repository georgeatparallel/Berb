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

| Module | Responsibility |
|--------|---------------|
| `berb/llm/` | LLM providers, model routing, cost optimization (caching, batching, cascading) |
| `berb/literature/` | arXiv, OpenAlex, Semantic Scholar, SearXNG, grey literature, multimodal figure extraction |
| `berb/experiment/` | Sandboxed code execution (local, Docker, SSH, Colab); self-correcting simulation; auto-debugger |
| `berb/agents/` | Benchmark agent, code searcher, figure critique agent |
| `berb/review/` | 5-reviewer + Area Chair peer review ensemble |
| `berb/memory/` | Shared memory coordination across pipeline stages |
| `berb/research/` | Agentic tree search, idea scoring, open-ended discovery |
| `berb/vision/` | VLM figure critique and generation (Matplotlib/TikZ) |
| `berb/validation/` | Finding reproduction and verification |

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

`berb/llm/model_router.py` and `berb/llm/nadirclaw_router.py` route requests by cost/latency. The cascade pattern (`model_cascade.py`) tries cheap models first, escalating to premium only when needed. Supported providers: OpenAI, Anthropic, DeepSeek, Perplexity, xAI, OpenRouter, MiniMax.

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
