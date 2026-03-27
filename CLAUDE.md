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
