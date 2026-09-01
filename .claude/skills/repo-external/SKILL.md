---
name: repo-external
description: Map of the vendored/external dirs — external/ (SearXNG settings), mnemix/ (Mnemo Cortex memory server), searxng/ (SearXNG config), and "Github Projects/" (5 reference repos: AI-Scientist-v2, claude-scholar, DeepScientist, feynman, Vane). Use when touching integrations, memory server, web-search config, or consulting reference implementations.
---

# external/, mnemix/, searxng/, Github Projects/

Four top-level directories holding vendored or external material that supports Berb but is not part of the `berb/` package: SearXNG search-engine configuration (two locations), the Mnemo Cortex memory server (the service behind `berb/mnemo_bridge/`), and a collection of reference open-source projects that inspired Berb's design. None of this code is imported by the pipeline directly — integration happens via HTTP services and bridges.

## Contents

| File/Dir | Purpose |
|------|---------|
| `external/searxng/settings.yml` | Alternate/older SearXNG settings copy (smaller than the root `searxng/` one) |
| `searxng/settings.yml` | SearXNG instance config "Berb Search" — academic-tuned, JSON output enabled, port 8080; used by `docker-compose.searxng.yml` at repo root |
| `mnemix/` | **Mnemo Cortex** — standalone drop-in memory server for AI agents (port 50001). Endpoints: `POST /context`, `/preflight`, `/writeback`; verdicts PASS/ENRICH/WARN/BLOCK. Key files: `server.py`, `cli.py`, `providers.py`, `sessions.py`, `cache.py`, `config.py`, `adapters/watcher.py`, `agentb/` (+ `agentb.yaml.example`), own `pyproject.toml`, `Dockerfile`, `install.sh`, `test_agentb.py` |
| `Github Projects/AI-Scientist-v2-main/` | Sakana AI-Scientist v2 — autonomous paper-writing pipeline (reference for experiment tree search) |
| `Github Projects/claude-scholar-main/` | claude-scholar — Claude Code research plugin (agents/commands/skills/rules); a legacy copy also sits in `docs/archive/legacy/` |
| `Github Projects/DeepScientist-main/` | DeepScientist — autonomous research system (reference) |
| `Github Projects/feynman-main/` | feynman — Astro-based research/experiment notebook project (reference) |
| `Github Projects/Vane-master/` | Vane — TypeScript/Drizzle web app with its own searxng integration (reference) |

## Notes

- Start SearXNG with `docker compose -f docker-compose.searxng.yml up` (repo root); it mounts `searxng/settings.yml`. Change the placeholder `secret_key` before any production use.
- SearXNG client code exists (`berb/literature/searxng_client.py`) but is currently **unwired** from the pipeline (see CLAUDE.md).
- Mnemo Cortex is consumed through `berb/mnemo_bridge/` over HTTP (port 50001) — mnemix is its own package with its own tests (`mnemix/test_agentb.py`), not part of the berb pytest suite.
- "Github Projects/" repos are read-only reference material — never import from them, and mind the space in the path when scripting (quote it).
- Do not lint/format/refactor vendored code; exclude these dirs from repo-wide sweeps.
