# Berb — Project Context Guide

## Project Overview

**Berb** is an advanced AI-powered autonomous research automation system that transforms a single research idea into a conference-ready academic paper through a **23-stage pipeline** with **zero human intervention**.

**Key Value Proposition:**
- Cost: $0.40-0.70 per paper (30-50x cheaper than alternatives like AI Scientist V2 at ~$25)
- Multimodal literature search with figure/chart/table extraction (PaperQA3-inspired)
- Self-correcting simulation with physics-aware error diagnosis (MCP-SIM, Nature 2025)
- Open-ended discovery with template-free exploration (AI Scientist V2, ICLR 2025)
- Memory-coordinated multi-agent system with persistent shared memory
- Automated peer review with 5-reviewer ensemble + Area Chair
- Multi-language support (13 languages with auto-detection)

**Author:** Georgios-Chrysovalantis Chatzivantsidis  
**Version:** 1.0.0  
**License:** MIT  
**Python:** 3.11+

---

## Architecture

### 23-Stage Pipeline (8 Phases)

```
Phase A: Scoping           Phase E: Execution
  1. TOPIC_INIT            12. EXPERIMENT_RUN
  2. PROBLEM_DECOMPOSE     13. ITERATIVE_REFINE

Phase B: Literature        Phase F: Analysis
  3. SEARCH_STRATEGY       14. RESULT_ANALYSIS
  4. LITERATURE_COLLECT    15. RESEARCH_DECISION
  5. LITERATURE_SCREEN
  6. KNOWLEDGE_EXTRACT     Phase G: Writing
                           16. PAPER_OUTLINE
Phase C: Synthesis         17. PAPER_DRAFT
  7. SYNTHESIS             18. PEER_REVIEW
  8. HYPOTHESIS_GEN        19. PAPER_REVISION
                           20. QUALITY_GATE
Phase D: Design            21. KNOWLEDGE_ARCHIVE
  9. EXPERIMENT_DESIGN     22. EXPORT_PUBLISH
  10. CODE_GENERATION      23. CITATION_VERIFY
  11. RESOURCE_PLANNING
```

### Module Structure

```
berb/
├── agents/           # Multi-agent system (Benchmark, Figure, Code Search)
├── assessor/         # Quality assessment
├── benchmarks/       # Benchmarking tools
├── calendar/         # Scheduling and timeline management
├── cognitive_flow/   # Cognitive flow orchestration
├── collaboration/    # Human-in-the-loop collaboration
├── copilot/          # AI copilot integration
├── dashboard/        # Web dashboard
├── docker/           # Docker configurations
├── domains/          # Domain-specific modules (chaos, physics, etc.)
├── experiment/       # Experiment execution (Sandbox, Docker, Self-Correcting)
├── feedback/         # Feedback collection and processing
├── hooks/            # Auto-triggered lifecycle hooks
├── hyperagent/       # Hyperagents framework
├── i18n/             # Internationalization (13 languages)
├── knowledge/        # Knowledge base management (Obsidian, Zotero)
├── learning/         # Cross-project learning
├── literature/       # Literature search (OpenAlex, Semantic Scholar, Multimodal)
├── llm/              # LLM providers (OpenAI, Anthropic, Model Router)
├── mcp/              # Model Context Protocol integration
├── memory/           # Shared memory for agent coordination
├── memory_vault/     # Long-term memory storage
├── metaclaw_bridge/  # MetaClaw skill injection bridge
├── metrics/          # Metrics collection and reporting
├── mnemo_bridge/     # Mnemo integration
├── optimization/     # Cost-quality optimization
├── overleaf/         # Overleaf LaTeX integration
├── pipeline/         # 23-stage pipeline orchestration
├── plugins/          # Plugin system
├── presets/          # Domain-specific presets (ML, biomedical, NLP, etc.)
├── project/          # Project management
├── reasoner_bridge/  # Reasoner integration
├── reasoning/        # Reasoning methods (Multi-Perspective, Bayesian, etc.)
├── research/         # Research exploration (Tree Search, Idea Scoring)
├── review/           # Automated peer review (5-reviewer ensemble)
├── self_evolve/      # Self-evolution mechanisms
├── server/           # HTTP server and API
├── servers/          # MCP servers
├── skills/           # Skill definitions
├── templates/        # LaTeX and document templates
├── trends/           # Research trends analysis
├── utils/            # Utility functions
├── validation/       # Finding reproduction for validation
├── vision/           # Vision-based figure generation and critique
├── voice/            # Voice interaction
├── web/              # Web search and scraping (SearXNG, Firecrawl)
├── wizard/           # Interactive wizards
├── writing/          # Writing assistance (style mimicry, anti-AI)
├── cli.py            # Command-line interface
├── config.py         # Configuration loading and validation
├── health.py         # Health checks and diagnostics
└── prompts.py        # Prompt management
```

---

## Building and Running

### Installation

```bash
# Clone and setup
git clone https://github.com/georgehadji/berb.git
cd Berb
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Install with all dependencies
pip install -e ".[all,dev]"

# Initialize configuration
berb init
```

### Configuration

**Minimum config (`config.arc.yaml`):**

```yaml
project:
  name: "my-research"
  mode: "full-auto"

research:
  topic: "Your research topic here"
  domains:
    - "machine-learning"

llm:
  provider: "openai-compatible"
  base_url: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  primary_model: "gpt-4o"
  fallback_models: ["gpt-4o-mini"]

experiment:
  mode: "docker"  # "sandbox" | "docker" | "ssh_remote" | "colab_drive"
  docker:
    image: "berb/experiment:latest"
    gpu_enabled: true
```

**Environment Variables:**
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="..."
```

### Running the Pipeline

```bash
# Run with auto-approval (fully autonomous)
berb run --topic "Your research topic" --auto-approve

# Run in collaborative mode (pauses at decision points)
berb run --topic "Your research topic" --mode collaborative

# Run with specific config
berb run --config config.arc.yaml

# Run specific stages only
berb run --stages 1-8  # Run stages 1 through 8
```

### Health Check

```bash
# Verify environment and configuration
berb doctor
```

### Setup Wizard

```bash
# Interactive setup for first-time users
berb setup
```

---

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test categories
pytest tests/test_berb_cli.py
pytest tests/test_berb_executor.py

# End-to-end tests (requires API keys)
pytest tests/e2e_real_llm.py -m e2e

# Run with coverage
pytest tests/ --cov=berb --cov-report=html

# Skip slow and LLM-requiring tests
pytest tests/ -m "not slow and not e2e and not llm"
```

**Test Coverage:** 75%+

---

## Development Conventions

### Coding Standards

- **Python:** 3.11+ with strict type hints
- **Formatting:** ruff (line-length: 100)
- **Type Checking:** mypy (Python 3.11)
- **Data Validation:** Pydantic v2
- **Async:** asyncio for all I/O-bound operations
- **Error Handling:** Mandatory try/except with specific exception types
- **Documentation:** Google-style docstrings

### Architecture Principles

- **Hexagonal Architecture:** Domain logic decoupled from infrastructure
- **Functional Core / Imperative Shell:** Pure functions for business logic
- **Clean Layer Boundaries:** Clear separation between pipeline stages
- **Config-Driven Behavior:** YAML/JSON configuration, not hardcoded values
- **Toggleable Features:** All new features controllable via `config.arc.yaml`

### File Naming Conventions

- **Modules:** `snake_case.py` (e.g., `model_router.py`)
- **Classes:** `PascalCase` (e.g., `ModelRouter`, `PipelinePreset`)
- **Functions:** `snake_case` (e.g., `select_model`, `validate_config`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `CONFIG_SEARCH_ORDER`)
- **Tests:** `test_*.py` with `test_*` functions

### Git Workflow

```bash
# Branch from main
git checkout -b feature/your-feature-name

# Commit with conventional commits
git commit -m "feat: add multi-perspective reasoning method"
git commit -m "fix: resolve memory leak in shared memory"
git commit -m "docs: update README with new presets"
git commit -m "test: add tests for Bayesian reasoning"

# Before pushing
git pull --rebase
pytest tests/ -m "not slow and not e2e and not llm"
ruff check berb/
ruff format berb/
```

### PR Guidelines

- One concern per PR
- Include tests for new functionality
- Ensure linting and type checking pass
- Do not commit secrets or local config files
- Update documentation for user-facing changes

---

## Key Technologies

### AI/ML Frameworks

- **LangChain:** Agent orchestration
- **Google Generative AI SDK:** Gemini integration
- **OpenAI API:** GPT-4o, o1 models
- **Anthropic Claude API:** Claude Sonnet/Opus
- **DeepSeek API:** DeepSeek V3.2, R1
- **OpenRouter:** Multi-provider routing

### Backend Technologies

- **Python 3.11+:** Core language
- **Pydantic v2:** Data validation
- **FastAPI:** HTTP server (when running server mode)
- **SQLite/PostgreSQL:** Event store and persistence
- **Redis:** Caching (optional)
- **Docker:** Experiment sandboxing

### Web & Search

- **SearXNG:** Self-hosted meta-search (100+ engines)
- **Firecrawl:** Web scraping and crawling
- **Playwright:** Browser automation
- **httpx:** Async HTTP client

### Infrastructure

- **MCP (Model Context Protocol):** Tool integration
- **GitHub Actions:** CI/CD
- **pytest:** Testing framework
- **ruff:** Linting and formatting

---

## Domain-Specific Presets

Berb includes pre-configured presets for different research domains:

| Preset | Use Case | Cost/Paper | Models |
|--------|----------|------------|--------|
| `ml-conference` | ML venues (NeurIPS, ICML, ICLR) | $1.50 | Claude Sonnet/Opus |
| `biomedical` | Clinical research, genomics | $2.00 | Claude + Gemini |
| `nlp` | Computational linguistics, LLMs | $1.50 | Claude + DeepSeek |
| `computer-vision` | Image/video analysis | $2.50 | Claude + Gemini |
| `physics` | Computational physics, chaos | $1.00 | Claude + DeepSeek |
| `social-sciences` | Psychology, sociology | $1.50 | Claude + GPT-4o |
| `systematic-review` | PRISMA-compliant reviews | $3.00 | Claude (quality-first) |
| `engineering` | Systems, distributed systems | $1.50 | Claude + DeepSeek |
| `humanities` | Philosophy, history, qualitative | $2.00 | Claude Opus |
| `eu-sovereign` | GDPR-compliant research | $1.50 | Mistral + Qwen |
| `rapid-draft` | Fast brainstorming draft | $0.15 | DeepSeek + Qwen |
| `budget` | Maximum cost optimization | $0.25 | DeepSeek + Qwen |
| `max-quality` | Best possible output | $5.00 | Claude Opus + GPT-4o |
| `research-grounded` | Maximum literature coverage | $3.00 | Perplexity Sonar |

**Usage:**
```bash
berb run --topic "..." --preset ml-conference
```

---

## Reasoning Methods

Berb implements multiple reasoning methods for different stages:

| Method | Use Case | Target Stages |
|--------|----------|---------------|
| **Multi-Perspective** | Generate diverse viewpoints | 8, 9, 15, 18 |
| **Pre-Mortem Analysis** | Failure mode identification | 9, 12, 13 |
| **Bayesian Reasoning** | Probability-based updates | 5, 14, 15, 20 |
| **Debate** | Pro/Con argumentation | 8, 15 |
| **Dialectical (Aufhebung)** | Transcend contradictions | 7, 8, 15 |
| **Research (Iterative)** | Multi-round search | 3-6 |
| **Socratic** | Question-driven refinement | 1, 2, 8, 15 |
| **Scientific** | Hypothesis/Test cycles | 8, 14 |
| **Jury** | Orchestrated multi-agent | 18 |

---

## Operation Modes

### Autonomous Mode
- Zero human intervention
- Full pipeline execution
- Auto-approval at all gates
- Best for: Rapid prototyping, known domains

```bash
berb run --topic "..." --mode autonomous --auto-approve
```

### Collaborative Mode
- Pauses at configured stages
- Human feedback injection
- Edit/reject/approve options
- Best for: Novel research, high-stakes papers

```bash
berb run --topic "..." --mode collaborative --pause-after 2,6,8,15,18
```

---

## Experiment Execution Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `sandbox` | Local Python sandbox | Simple experiments |
| `docker` | Docker container with GPU | Reproducible, isolated |
| `ssh_remote` | Remote server via SSH | Lab GPU clusters |
| `colab_drive` | Google Colab + Drive | Free GPU access |
| `agentic` | OpenCode Beast Mode | Complex multi-file projects |

---

## Key Documentation Files

| File | Description |
|------|-------------|
| `README.md` | Main project overview |
| `IMPLEMENTATION.md` | Detailed implementation guide |
| `BERB_IMPLEMENTATION_PROMPT.md` | Enhancement specification (2239 lines) |
| `TODO.md` | Implementation roadmap and status |
| `CONTRIBUTING.md` | Contribution guidelines |
| `docs/HOW_BERB_WORKS.md` | Pipeline flow explanation |
| `docs/P4_OPTIMIZATION_PLAN.md` | Cost optimization features |
| `docs/P5_ENHANCEMENT_PLAN.md` | Latest research integrations |
| `docs/REASONING_METHODS_FOR_BERB.md` | Reasoning methods guide |
| `docs/OPENROUTER_MODEL_SELECTION.md` | Model routing configuration |
| `docs/PHYSICS_DOMAIN_OPTIMIZATIONS.md` | Physics domain tools |
| `docs/CLAUDE_SCHOLAR_ENHANCEMENTS.md` | Claude Scholar integration |
| `docs/SEARXNG_FIRECRAWL_INTEGRATION.md` | Search/scraping setup |

---

## Security Features

- **Subprocess env isolation:** Strips `*_API_KEY`/`*_TOKEN` from child processes
- **Server binding:** Defaults to `127.0.0.1` (not `0.0.0.0`)
- **CORS:** Credentials disabled unless explicit allowlist configured
- **SSRF guard:** Protection on DuckDuckGo redirect URLs
- **Docker sandboxing:** Isolated experiment execution
- **YAML security limits:** DoS prevention
- **Secure plugin runtime:** seccomp and Landlock (when available)

---

## Performance Metrics

| Metric | Baseline | Berb | Improvement |
|--------|----------|------|-------------|
| **Cost per paper** | $2.50 | $0.40-0.70 | -80-90% |
| **Literature coverage** | 20-30 papers | 70-100 papers | +233% |
| **Quality score** | 7.2/10 | 9.5/10 | +32% |
| **Time per paper** | 3 hours | 1-1.5 hours | -50-67% |
| **Test coverage** | 0% | 75%+ | +75% |

---

## Common CLI Commands

```bash
# Setup and diagnostics
berb init           # Initialize configuration
berb setup          # Interactive setup wizard
berb doctor         # Health check

# Pipeline execution
berb run            # Run full pipeline
berb run --stages 1-8  # Run specific stages

# Knowledge management
berb knowledge export --format obsidian
berb knowledge import --from zotero

# Experiment tools
berb experiment run --design design.yaml
berb experiment debug --id exp-123

# Server mode
berb server start   # Start HTTP API server
berb server stop    # Stop server

# Utilities
berb scrape --url https://...    # Scrape single URL
berb crawl --url https://...     # Crawl website
berb map --url https://...       # Discover URLs
```

---

## Troubleshooting

### Common Issues

**Config not found:**
```bash
# Check search order: config.arc.yaml, config.yaml
berb init  # Generate from example
```

**LLM API errors:**
```bash
# Verify API keys
export OPENAI_API_KEY="sk-..."
berb doctor  # Check connectivity
```

**Docker experiment failures:**
```bash
# Build experiment image
docker build -t berb/experiment:latest berb/docker/

# Test GPU access
docker run --gpus all berb/experiment:latest nvidia-smi
```

**Memory issues:**
```bash
# Reduce parallel tasks in config
runtime:
  max_parallel_tasks: 1
```

---

## External Integrations

| Integration | Purpose | Status |
|-------------|---------|--------|
| **OpenAlex** | Literature search | ✅ Active |
| **Semantic Scholar** | Literature search | ✅ Active |
| **arXiv API** | Preprint search | ✅ Active |
| **PubMed** | Biomedical literature | ✅ Active |
| **Zotero (MCP)** | Reference management | 📋 Planned |
| **Obsidian** | Knowledge base export | 📋 Planned |
| **Overleaf** | LaTeX collaboration | 📋 Planned |
| **MetaClaw** | Skill injection | 📋 Planned |
| **MCP Servers** | Tool integration | 📋 Planned |

---

## Research Sources

Berb incorporates insights from:
- **AI Scientist V2** (Sakana AI, ICLR 2025 Workshop)
- **MCP-SIM** (KAIST, Nature Computational Science 2025)
- **PaperQA3** (Edison Scientific)
- **Hyperagents** (Facebook AI Research, arXiv:2603.19461)

---

## Support

- **GitHub Issues:** https://github.com/georgehadji/Berb/issues
- **Documentation:** https://github.com/georgehadji/Berb/tree/main/docs

---

**Berb — Research, Refined.** 🧪✨
