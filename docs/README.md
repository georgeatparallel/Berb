# Berb Documentation

**AI-Powered Research Automation with 97% Cost Optimization**

---

## Quick Start

| I want to... | Go to... |
|--------------|----------|
| Get started | [README.md](../README.md) |
| Configure Berb | [CONFIGURATION.md](CONFIGURATION.md) |
| Use Berb | [USAGE.md](USAGE.md) |
| Understand architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Choose models | [MODELS.md](MODELS.md) |
| Deploy to production | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Contribute | [CONTRIBUTING.md](../CONTRIBUTING.md) |

---

## Documentation Overview

### 📖 User Guides

- **[USAGE.md](USAGE.md)** - How to use Berb reasoning methods
- **[CONFIGURATION.md](CONFIGURATION.md)** - Configuration options and examples
- **[MODELS.md](MODELS.md)** - LLM model selection guide (11 providers, 97% cost savings)

### 🏗️ Technical Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design
- **[IMPLEMENTATION.md](IMPLEMENTATION.md)** - Implementation details and benchmarks
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide

### 🤝 Contributing

- **[CONTRIBUTING.md](../CONTRIBUTING.md)** - How to contribute
- **Development Setup** - (See README.md)
- **Testing Guide** - (See [USAGE.md](USAGE.md)#testing)

---

## Key Features

### 11 LLM Providers Supported

| Provider | Best For | Cost Range |
|----------|----------|------------|
| **MiniMax** | Budget tasks | FREE - $0.40/1M |
| **Qwen** | Best overall value | $0.05 - $1.04/1M |
| **GLM** | Agent workflows | FREE - $1.20/1M |
| **MiMo** | Coding tasks | $0.09 - $1.00/1M |
| **Kimi** | Visual coding | $0.40 - $0.57/1M |
| **Perplexity** | Search integration | $1.00 - $3.00/1M |
| **xAI (Grok)** | Long context (2M) | $0.20 - $3.00/1M |
| **DeepSeek** | Reasoning value | $0.15 - $0.70/1M |
| **Google** | Multimodal | $0.075 - $2.00/1M |
| **Anthropic** | Premium quality | $0.25 - $5.00/1M |
| **OpenAI** | Codex (coding) | $0.05 - $30.00/1M |

### 9 Reasoning Methods

1. **Multi-Perspective** - 4-perspective analysis (constructive, destructive, systemic, minimalist)
2. **Pre-Mortem** - Failure identification via prospective hindsight
3. **Bayesian** - Probability-based belief updates
4. **Debate** - Pro/Con arguments with judge evaluation
5. **Dialectical** - Thesis → Antithesis → Synthesis
6. **Research** - Iterative search and synthesis
7. **Socratic** - Question-driven understanding
8. **Scientific** - Hypothesis generation and testing
9. **Jury** - Orchestrated multi-agent evaluation

### Cost Savings

| Configuration | Cost per Run | Annual (1000/month) |
|---------------|--------------|---------------------|
| Premium (baseline) | $23.00 | $276,000 |
| **Optimized** | **$0.69** | **$8,280** |
| **Savings** | **97%** | **$267,720** |

---

## Project Structure

```
berb/
├── 📄 README.md                    # Project overview
├── 📄 LICENSE                      # MIT License
├── 📄 CONTRIBUTING.md              # Contribution guidelines
├── 📁 configs/                     # Configuration examples
│   ├── config.berb.example.yaml
│   └── config.arc.example.yaml
├── 📁 docs/                        # Documentation
│   ├── MODELS.md                   # Model recommendations
│   ├── IMPLEMENTATION.md           # Implementation summary
│   └── internal/                   # Internal docs (archived)
├── 📁 scripts/                     # Utility scripts
│   ├── verify_all_models.py
│   └── merge_to_main.bat
├── 📁 tests/                       # Test files
│   ├── test_extended_router.py
│   └── test_reasoning_integration.py
├── 📁 berb/                        # Source code
│   ├── llm/                        # LLM clients & router
│   ├── reasoning/                  # Reasoning methods
│   └── metrics/                    # Cost tracking
└── 📁 external/                    # External dependencies
```

---

## Getting Started

### 1. Installation

```bash
pip install -e .
```

### 2. Configuration

```bash
# Copy example config
cp configs/config.berb.example.yaml config.berb.yaml

# Set API key
export OPENROUTER_API_KEY=sk_or_xxxxx...
```

### 3. Run

```bash
berb run --topic "Your research topic"
```

### 4. Verify Models

```bash
python scripts/verify_all_models.py
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific tests
pytest tests/test_extended_router.py -v
pytest tests/test_reasoning_integration.py -v
```

---

## Internal Documentation

Internal/intermediate documentation is archived in [`docs/internal/`](docs/internal/):

- Phase reports
- Implementation plans
- Progress reports
- Legacy documentation

These are preserved for reference but not part of the main documentation.

---

## Support

- **GitHub Issues:** https://github.com/georgehadji/berb/issues
- **Discussions:** https://github.com/georgehadji/berb/discussions
- **Email:** berb-support@example.com

---

## License

MIT License - See [LICENSE](../LICENSE) for details.

---

**Last Updated:** March 29, 2026  
**Version:** 2.0-extended
