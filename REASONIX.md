# REASONIX.md — Berb

## Stack

- **Language:** Python 3.11+
- **Build:** hatchling (`pyproject.toml`)
- **CLI:** `berb` → `berb.cli:main`
- **Test:** pytest with `asyncio_mode=auto`; markers: `slow`, `e2e`, `llm`
- **Lint:** ruff (line-length=100, rules: E,F,W,I,N,UP,B,C4; ignores: E501,B008)
- **Type check:** mypy (py311, `warn_return_any`)
- **Pre-commit:** API key scanning hook (`.githooks/pre-commit`)

## Layout

| Path | Purpose |
|------|---------|
| `berb/` | Main package (CLI, pipeline, LLM, experiment, literature, agents, review, memory, vision, etc.) |
| `berb/pipeline/` | 23-stage pipeline state machine (`stages.py`), runner, executor, stage implementations |
| `berb/llm/` | LLM providers, model routing (`model_router.py`, `nadirclaw_router.py`), cascade (`model_cascade.py`), caching |
| `berb/literature/` | arXiv, OpenAlex, Semantic Scholar, SearXNG clients, citation graph, evidence mapping |
| `berb/experiment/` | Sandboxed code execution (local, Docker, SSH, Colab), self-correcting simulation, auto-debugger |
| `berb/agents/` | Benchmark agent, code searcher, figure critique agent |
| `berb/review/` | 5-reviewer + Area Chair peer review ensemble |
| `berb/memory/` | Shared memory coordination across pipeline stages |
| `berb/vision/` | VLM figure critique and generation (Matplotlib/TikZ) |
| `berb/validation/` | Finding reproduction and verification |
| `berb/mcp/` | MCP server interface |
| `berb/metaclaw_bridge/` | MetaClaw skill injection |
| `berb/mnemo_bridge/` | Mnemo Cortex memory |
| `berb/reasoner_bridge/` | ARA reasoning patterns |
| `tests/` | Test files mirroring module names (`test_berb_literature.py` → `berb/literature/`) |
| `configs/` | Example configs; primary config auto-detected from `config.arc.yaml` or `config.yaml` |
| `external/` | Vendor configs (e.g. SearXNG settings) |
| `.berb_cache/` | Literature search cache (auto-generated) |

## Commands

```bash
pip install -e .                     # editable install
pip install -e ".[all]"              # all optional deps
pip install -e ".[dev]"              # dev/test deps

berb setup                           # interactive config
berb run --topic "..." --auto-approve  # run full pipeline
berb run --topic "..." --from-stage PAPER_OUTLINE  # resume from stage
berb doctor                          # health check

pytest tests/                        # all tests
pytest -m "not slow and not e2e and not llm"  # unit only
pytest --cov=berb tests/             # with coverage
```

## Conventions

- **`from __future__ import annotations`** at the top of most module files.
- **N806 disabled per-file** in domain/experiment/pipeline/literature/llm modules for scientific notation (e.g. `D2`, `C_m`, `q_matrix`).
- **Test files** named `test_<module_name>.py`, colocated under `tests/`.
- **`e2e_*.py`** test files require real LLM API keys.
- **Stage enum** defined in `berb/pipeline/stages.py` as `IntEnum` (Stage 1–23).
- **LLM prompts** centralized in `prompts.default.yaml` (~150 KB), not scattered in code.
- **Config** in YAML; auto-detects `config.arc.yaml` or `config.yaml`.

## Watch out for

- **`config.yaml` and `config.arc.yaml` are gitignored** — use one of the example files in `configs/` as a template.
- **`.berb_cache/` and `.researchclaw_cache/` are auto-generated literature caches** — delete them to force re-fetch.
- **Docker sandbox** requires the images from `berb/docker/Dockerfile.*`.
- **`prompts.default.yaml` is ~150 KB** — avoid reading it whole unless needed; search for specific prompt keys instead.
