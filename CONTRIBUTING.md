# Contributing to Berb

## Setup

1. Fork and clone the repo
2. Create a venv and install with dev extras:
   ```
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   ```
3. Generate your local config:
   ```
   berb init
   ```
4. Edit `config.arc.yaml` with your LLM settings

## Config Convention

- `config.berb.example.yaml` — tracked template (do not add secrets)
- `config.arc.yaml` — your local config (gitignored, created by `berb init`)
- `config.yaml` — also gitignored, supported as fallback

## Running Tests

```
pytest tests/
```

## Checking Your Environment

```
berb doctor
```

## CI

GitHub Actions runs on every push and PR to `main`:
- Unit tests (`pytest -m "not slow and not e2e and not llm"`)
- Ruff lint + format check
- Pyright type check (advisory)

The workflow is at `.github/workflows/ci.yml`.

## PR Guidelines

- Branch from `main`
- One concern per PR
- Ensure `pytest tests/ -m "not slow and not e2e and not llm"` passes locally
- Include tests for new functionality
- Do not commit secrets or config files (`config.arc.yaml` is gitignored)
