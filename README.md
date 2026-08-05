# Berb

**Autonomous research pipeline that turns a research idea into a publication-ready paper.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/georgehadji/berb/actions/workflows/ci.yml/badge.svg)](https://github.com/georgehadji/berb/actions/workflows/ci.yml)
[![Development Status](https://img.shields.io/badge/status-beta-orange.svg)]()

Berb is a Python framework for automating end-to-end academic research. It orchestrates a 23-stage pipeline spanning literature search, synthesis, experiment design, code execution, paper writing, automated peer review, and citation verification.

The system is built around a modular, event-driven architecture with explicit pipeline state, checkpoint/resume support, sandboxed experiment execution, multi-provider LLM routing, and a CLI-first interface.

> **Status:** Beta — core pipeline is functional and under active development. Production deployments should review the [security](#security-and-production-hardening) and [configuration](#configuration) sections carefully.

---

## Table of Contents

- [What is Berb?](#what-is-berb)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Running as an Autonomous Agent](#running-as-an-autonomous-agent)
- [Architecture](#architecture)
- [Pipeline Stages](#pipeline-stages)
- [Key Subsystems](#key-subsystems)
- [Testing](#testing)
- [Security and Production Hardening](#security-and-production-hardening)
- [Project Status and Roadmap](#project-status-and-roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)
- [Support](#support)

---

## What is Berb?

Berb automates the research workflow from topic to paper:

1. **Scope** — decomposes a research topic into tractable sub-problems.
2. **Discover** — searches arXiv, OpenAlex, and Semantic Scholar.
3. **Synthesize** — extracts knowledge, scores novelty, and generates hypotheses.
4. **Design** — produces reproducible experiment code and execution plans.
5. **Execute** — runs experiments in sandbox, Docker, SSH remote, or Colab environments.
6. **Write** — drafts a structured academic paper with figures, citations, and revisions.
7. **Review** — applies an automated reviewer ensemble and revises against feedback.
8. **Finalize** — verifies citations, runs quality gates, and exports artifacts.

The pipeline is configurable, resumable, and observable. Each run produces a directory with checkpoints, logs, generated code, figures, and the final paper.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/georgehadji/berb.git
cd berb
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[all,dev]"

# 2. Create a configuration file
berb init
# Alternatively: cp configs/config.arc.example.yaml config.arc.yaml
# Edit config.arc.yaml and set your LLM API key

# 3. Validate the configuration
berb validate

# 4. Run the full pipeline
berb run --topic "Your research topic" --auto-approve

# 5. Check system health
berb doctor
```

By default, outputs are written to `artifacts/rc-<timestamp>-<hash>/`.

---

## Installation

### Requirements

- Python 3.11 or 3.12
- (Optional) Docker for containerized experiment execution
- (Optional) Node.js/npm for OpenCode-powered experiment generation

### Install options

```bash
# Core package
pip install -e .

# With all optional runtime dependencies
pip install -e ".[all]"

# Development dependencies (tests, linting, type checking)
pip install -e ".[dev]"

# Specific provider only
pip install -e ".[openai,anthropic]"
```

---

## Configuration

Berb uses a YAML configuration file. The CLI auto-detects `config.arc.yaml` or `config.yaml` in the working directory, or accepts an explicit path via `--config`.

Generate a starter config with:

```bash
berb init           # creates config.arc.yaml from the example template
```

If you prefer to copy manually:

```bash
cp configs/config.arc.example.yaml config.arc.yaml
# or: cp configs/config.arc.example.yaml config.yaml
```

### Minimal configuration

```yaml
project:
  name: "my-research"
  mode: "full-auto"        # "full-auto" | "semi-auto" | "docs-first"

research:
  topic: "Your research topic"

llm:
  provider: "openrouter"   # "openrouter" | "openai" | "anthropic" | "deepseek" | ...
  base_url: "https://openrouter.ai/api/v1"
  api_key_env: "OPENROUTER_API_KEY"
  primary_model: "qwen/qwen3.5-flash-02-23"
  fallback_models:
    - "minimax/minimax-m2.5:free"

experiment:
  mode: "sandbox"          # "sandbox" | "docker" | "ssh_remote" | "colab_drive"
  time_budget_sec: 300
  max_iterations: 10
```

See `configs/config.arc.example.yaml` (or `configs/config.berb.example.yaml`) for complete, annotated templates including provider-specific model routing, security settings, reasoning-method configuration, Docker/SSH/Colab backends, and integrations.

### Environment variables

API keys are read from environment variables referenced by `api_key_env` in the config. Set them before running, for example:

```bash
export OPENROUTER_API_KEY="sk-..."
```

Berb strips `*_API_KEY` and `*_TOKEN` variables from subprocess environments to reduce accidental secret leakage.

---

## Usage

### CLI commands

```bash
# Interactive setup wizard
berb setup

# Initialize a config file from the example template
berb init

# Run the pipeline
berb run --topic "Your research topic"

# Run fully automatically (no human-in-the-loop gates)
berb run --topic "Your research topic" --auto-approve

# Resume a previous run from its checkpoint
berb run --topic "Your research topic" --resume

# Start from a specific pipeline stage
berb run --topic "Your research topic" --from-stage EXPERIMENT_DESIGN

# Validate configuration
berb validate

# System health check
berb doctor

# Start the REST API server
berb serve --host 127.0.0.1 --port 8000

# Start the dashboard
berb dashboard --host 127.0.0.1 --port 8000

# MCP server and tools
berb mcp --start
berb mcp

# Multi-project management
berb project list
berb project create --name "my-project" --topic "..."

# Overleaf sync
berb overleaf --sync --run-dir artifacts/rc-...
```

Run `berb --help` for the full list of commands and options.

### Running as an autonomous agent

Berb is designed for fully unattended execution by AI coding agents, CI/CD pipelines, and shell scripts. Every stage in the pipeline can run without human interaction when `--auto-approve` is set.

#### Pre-flight checklist for agents

Before launching a run, verify the environment with these one-liners:

```bash
# 1. Confirm berb is reachable and environment is healthy
berb doctor           # exits 0 = ready; prints health report

# 2. Confirm config is valid and API credentials work
berb validate         # exits 0 = valid config + API credentials

# 3. Check available disk space (runs can produce large artifacts)
berb doctor 2>&1 | grep disk_space
```

If `berb` is not on PATH, use the fallback:

```bash
python -m berb doctor
python -m berb validate
```

#### Canonical invocation

The single command an agent needs to run the full 23-stage pipeline:

```bash
berb run --topic "Your research topic" --auto-approve
```

| Flag | Purpose |
|------|---------|
| `--topic "…"` / `-t` | Research question or hypothesis |
| `--auto-approve` | Skip all human-in-the-loop gate stages |
| `--skip-preflight` | Skip LLM connectivity check (use when environment is known-good) |
| `--resume` | Resume from last checkpoint if a previous run was interrupted |
| `--from-stage STAGE` | Start from a specific pipeline stage (e.g. `EXPERIMENT_DESIGN`) |
| `--output DIR` / `-o` | Override the default output directory |
| `--config PATH` / `-c` | Explicit config file path (default: auto-detects `config.arc.yaml` or `config.yaml`) |
| `--skip-noncritical-stage` | Continue on noncritical stage failures instead of aborting |

#### Checking results after a run

```bash
# Generate a human-readable report from the run artifacts
berb report --run-dir artifacts/rc-<timestamp>-<hash>

# List all past runs
ls artifacts/
```

Outputs live under `artifacts/rc-<timestamp>-<hash>/` and include:

- `paper/` — generated LaTeX/PDF manuscript
- `figures/` — generated figures and plots
- `experiments/` — experiment code and raw results
- `checkpoints/` — pipeline state for resume
- `logs/` — per-stage logs
- `report.json` — machine-readable run summary

#### Focused workflows (single-phase runs)

Agents can run individual phases instead of the full pipeline:

```bash
# Literature search and synthesis only
berb literature --topic "Your research topic"

# Experiment design and execution only
berb experiment --hypothesis "Your hypothesis"

# Paper writing from existing results
berb write --topic "Your research topic" --data results/*.json

# Review an existing manuscript
berb review --manuscript paper.pdf --venue neurips
```

#### Agent integration patterns

**Python subprocess (recommended):**

```python
import subprocess, sys

result = subprocess.run(
    ["berb", "run", "--topic", "Deep learning for protein folding", "--auto-approve"],
    capture_output=True, text=True, timeout=3600,
)
if result.returncode != 0:
    print(f"Pipeline failed:\n{result.stderr}")
    sys.exit(1)
print(result.stdout)
```

**Shell script (CI/CD):**

```bash
#!/usr/bin/env bash
set -euo pipefail

berb doctor
berb validate
berb run --topic "$RESEARCH_TOPIC" --auto-approve --skip-preflight

# Generate report from the run
RUN_DIR=$(ls -dt artifacts/rc-* | head -1)
berb report --run-dir "$RUN_DIR"
```

**Reasonix / Claude Code agent note:**

```bash
# berb is already installed and on PATH in this environment.
# Verify with:
berb doctor

# Then run:
berb run --topic "..." --auto-approve
```

#### Troubleshooting for agents

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `berb: command not found` | Package not installed | `pip install -e .` or use `python -m berb` |
| `Config validation failed` | Missing or invalid config | Run `berb init`, edit `config.arc.yaml` |
| `API key rejected` | Missing or wrong credentials | Set the env var referenced by `api_key_env` in config |
| Run hangs at a gate stage | Missing `--auto-approve` | Add `--auto-approve` to skip human gates |
| `disk_space` warning | Not enough free space | Free up space or set `--output` to a larger volume |
| Pipeline aborts on noncritical stage | Stage failure | Add `--skip-noncritical-stage` |

### Programmatic API

```python
from berb.config import RCConfig
from berb.pipeline.runner import execute_pipeline
from berb.adapters import AdapterBundle

config = RCConfig.load("config.arc.yaml")  # or "config.yaml"
adapters = AdapterBundle()

results = await execute_pipeline(
    run_dir=Path("artifacts/my-run"),
    run_id="my-run",
    config=config,
    adapters=adapters,
    auto_approve_gates=True,
)
```

---

## Architecture

Berb is organized as a hybrid modular monolith with clear layer boundaries:

```
┌─────────────────────────────────────────────────────────────┐
│  Presentation: CLI · Web Dashboard · Programmatic API       │
├─────────────────────────────────────────────────────────────┤
│  Application:  Pipeline Orchestrator · Command Bus · Events │
├─────────────────────────────────────────────────────────────┤
│  Domain:       Literature · Experiment · Writing · Review   │
├─────────────────────────────────────────────────────────────┤
│  Integration:  LLM Providers · Scholarly APIs · MCP · Bridges│
├─────────────────────────────────────────────────────────────┤
│  Infrastructure: SQLite · File Cache · External APIs        │
└─────────────────────────────────────────────────────────────┘
```

Key architectural properties:

- **State-machine pipeline** — 23 explicit stages with checkpointing and resume.
- **Event-driven orchestration** — loose coupling between stages and observers.
- **Adapter bridges** — Mnemo Cortex, MetaClaw, Reasoner, and MCP integrations are isolated behind adapter interfaces.
- **Pluggable experiment backends** — sandbox, Docker, SSH remote, and Google Colab via Drive.
- **Multi-provider LLM routing** — cost/latency-aware model selection with fallback chains and token tracking.

A detailed architecture overview is available in [docs/ARCHITECTURE_v2.md](docs/ARCHITECTURE_v2.md).

---

## Pipeline Stages

The pipeline is divided into eight phases:

| Phase | Stages |
|-------|--------|
| A. Scoping | `TOPIC_INIT`, `PROBLEM_DECOMPOSE` |
| B. Literature | `SEARCH_STRATEGY`, `LITERATURE_COLLECT`, `LITERATURE_SCREEN`, `KNOWLEDGE_EXTRACT` |
| C. Synthesis | `SYNTHESIS`, `HYPOTHESIS_GEN` |
| D. Design | `EXPERIMENT_DESIGN`, `CODE_GENERATION`, `RESOURCE_PLANNING` |
| E. Execution | `EXPERIMENT_RUN`, `ITERATIVE_REFINE` |
| F. Analysis | `RESULT_ANALYSIS`, `RESEARCH_DECISION` |
| G. Writing | `PAPER_OUTLINE`, `PAPER_DRAFT`, `PEER_REVIEW`, `PAPER_REVISION` |
| H. Finalization | `QUALITY_GATE`, `KNOWLEDGE_ARCHIVE`, `EXPORT_PUBLISH`, `CITATION_VERIFY` |

Stage definitions live in `berb/pipeline/stages.py`; implementations are in `berb/pipeline/stage_impls/`.

---

## Key Subsystems

| Module | Responsibility | Wired |
|--------|---------------|-------|
| `berb/pipeline/` | Stage definitions, orchestration, checkpointing, execution | yes |
| `berb/llm/` | Provider clients, model routing, cascading fallbacks, cost tracking, retry logic | yes |
| `berb/literature/` | arXiv, OpenAlex, Semantic Scholar, novelty scoring, PDF ingestion, Zotero | yes |
| `berb/experiment/` | Sandboxed code execution, Docker/SSH/Colab backends, tree search | yes |
| `berb/agents/` | Benchmark agent, code-search agent, figure critique agent | yes |
| `berb/review/` | Multi-reviewer ensemble and automated revision | yes |
| `berb/writing/` | Paper drafting, citation engine, style polishers, anti-AI editing | yes |
| `berb/integrity/` | Claim manifests, evidence tracking, finding reproduction | partial |
| `berb/mcp/` | MCP server interface and tool registry | yes |
| `berb/memory/` | Shared memory coordination across stages | **no** — no caller |
| `berb/research/` | Idea scoring, gap analysis, open-ended discovery | **no** — no caller |
| `berb/vision/` | VLM-based figure generation | **no** — critique runs via `agents/figure_agent/` |

"Wired" means reachable from `berb run` / `berb serve`; check with
`python scripts/check_reachability.py`. Unwired modules are implemented and
tested but have no importer on any pipeline path, so they do not run: SearXNG
search, grey literature, multimodal figure extraction, self-correcting
simulation, and the auto-debugger are all in this category.

---

## Testing

```bash
# Run the full test suite
pytest tests/

# Run unit tests only (no slow, e2e, or LLM-dependent tests)
pytest -m "not slow and not e2e and not llm"

# Run a specific test file
pytest tests/test_berb_executor.py

# With coverage
pytest --cov=berb tests/

# Lint and format
ruff check berb tests
ruff format --check berb tests

# Type check the modules that are currently annotated
mypy berb/pipeline/registry berb/pipeline/resolution berb/pipeline/checkpoint \
     berb/pipeline/asyncio_utils berb/pipeline/contracts berb/pipeline/stages \
     berb/adapters berb/config
```

Test markers:

- `@pytest.mark.slow` — long-running tests
- `@pytest.mark.e2e` — end-to-end integration tests
- `@pytest.mark.llm` — tests requiring live LLM API access and credentials

---

## Security and Production Hardening

Berb includes several production-oriented safeguards:

| Control | Description |
|---------|-------------|
| Subprocess env isolation | Strips `*_API_KEY` / `*_TOKEN` variables from child processes |
| Default bind address | Server binds `127.0.0.1` by default (not `0.0.0.0`) |
| CORS credentials | Disabled unless an explicit allowlist is configured |
| SSRF guard | Validates redirect URLs in DuckDuckGo search paths |
| Default experiment mode | `sandbox` or `docker` rather than silent simulated execution |
| SQLite schema versioning | Forward-migration support in `token_tracker` |
| Shared-memory locking | Read paths in `SharedResearchMemory` are lock-protected |
| Naive timestamp cleanup | All `datetime.now()` usage moved to timezone-aware UTC |
| Rate limiting | Shared `RateLimiter` across literature API clients |
| Health endpoint | `/healthz` liveness probe for container orchestration |
| Span-level tracing | JSONL trace output in `berb/pipeline/tracing.py` |

Before deploying in production, review `configs/config.berb.example.yaml`, set explicit allowlists, enable Docker/SSH sandboxing as appropriate, and run `berb doctor`.

---

## Project Status and Roadmap

- **Current release:** `1.0.0-beta`
- **Primary interface:** CLI with FastAPI server and dashboard
- **Active work areas:** extended LLM routing, reasoning-method optimization, benchmark agent hardening, and evaluation harnesses

Completed major workstreams:

- P4 optimizations: reviewer ensemble, parallelized tree search, figure critique, citation verification, cost-quality optimization
- Production hardening: security fixes, concurrency controls, observability, CI/CD, and expanded test coverage

Built but not yet wired into the pipeline (see the Wired column above):
multimodal literature search, SearXNG and grey-literature search,
self-correcting simulation, the auto-debugger, open-ended discovery, idea
scoring, finding reproduction, and memory-centric coordination. These ship as
libraries with tests; they are not part of a `berb run`.

See [docs/P4_OPTIMIZATION_PLAN.md](docs/P4_OPTIMIZATION_PLAN.md) and [docs/P5_ENHANCEMENT_PLAN.md](docs/P5_ENHANCEMENT_PLAN.md) for detailed plans.

---

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Short version:

1. Fork the repository.
2. Create a feature branch.
3. Make focused changes with tests where applicable.
4. Run `pytest tests/` and `ruff check .`.
5. Open a pull request with a clear description.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

Copyright (c) 2026 Aiming Lab.

---

## Acknowledgments

Berb integrates ideas and techniques from:

- **AI Scientist V2** (Sakana AI, ICLR 2025 Workshop)
- **MCP-SIM** (KAIST, Nature Computational Science 2025)
- **PaperQA3** (Edison Scientific)
- **Hyperagents** (FAIR, arXiv:2603.19461)

---

## Support

- **Issues:** https://github.com/georgehadji/berb/issues
- **Documentation:** https://github.com/georgehadji/berb/tree/main/docs
- **Repository:** https://github.com/georgehadji/berb

---

**Berb — Research, Refined.**
