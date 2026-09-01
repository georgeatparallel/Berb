---
name: berb-integrations
description: Map of berb/integrations/ — external service integrations, currently only the scite.ai citation-intelligence client. Use when working on scite.ai smart citations, citation classification via external APIs, or adding new third-party integrations.
---

# berb/integrations

External-service integrations; today it contains only the optional scite.ai client for pre-classified "smart citations" (supporting / contrasting / mentioning), citation profiles with scite index scores, and reference-check reports — a paid alternative to the LLM citation classifier in `berb/literature/citation_classifier.py`. **Unwired/dormant** — nothing outside `berb/integrations/` imports it; not reachable from `berb run` or `berb serve`. Entry points are `SciteClient` and `SciteIntegration`.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | package exports: `SciteClient`, `SciteConfig`, `SciteIntegration`, `SciteIntegrationConfig`, `SciteCitationType` |
| `scite_mcp.py` | scite.ai API/MCP client: `SciteCitationType` enum, citation/profile/reference-check pydantic models, `SciteMCPClient` Protocol, `SciteClient` (HTTP calls to api.scite.ai: search citations, get profile, reference check, scite index), `SciteIntegration` wrapper with `prefer_over_llm` option |

## Wiring & entry points

- **No importers outside the package** — dormant; only tests exercise it.
- Public API: `SciteClient(api_key=...)` → `search_citations()`, `get_citation_profile(doi)`, `check_references()`, `get_scite_index(doi)`.
- Config: `SciteConfig(enabled, api_key, api_url="https://api.scite.ai", prefer_over_llm)` — requires a paid scite subscription; no `config.arc.yaml` section wires it in.
