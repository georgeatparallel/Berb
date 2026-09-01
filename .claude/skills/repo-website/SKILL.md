---
name: repo-website
description: Map of website/ — static hand-written HTML/CSS marketing site for AutoResearchClaw (5 pages + one stylesheet). Use when editing the landing site, pipeline/features/papers pages, or styling.
---

# website/

Static marketing/documentation site for the project under its public name "AutoResearchClaw". Plain hand-authored HTML5 + a single shared CSS file — no framework, no build step, no JS bundler (only tiny inline JS for the nav toggle). Fonts come from Google Fonts (Inter, JetBrains Mono).

## Contents

| File/Dir | Purpose |
|------|---------|
| `index.html` | Landing page — hero ("Chat an Idea. Get a Paper."), pipeline overview, nav to all pages |
| `pipeline.html` | Explains the 23-stage pipeline (phases A–H) |
| `features.html` | Feature grid (multi-provider LLMs, sandboxed experiments, review ensemble, etc.) |
| `papers.html` | Gallery of showcase papers (links to `docs/showcase/papers/` PDFs) |
| `getting-started.html` | Install and quick-start instructions (`pip install`, `berb setup`, `berb run`) |
| `style.css` | Single shared stylesheet — dark theme, gradient accents, responsive navbar |
| `assets/` (referenced) | `logo.png` favicon/brand image referenced by pages |

## Notes

- Stack: pure static HTML/CSS — open `index.html` in a browser or serve the folder with any static server; nothing to build.
- All pages share the same navbar markup — an edit to nav must be copied into all 5 HTML files by hand.
- GitHub link points to `aiming-lab/AutoResearchClaw`; keep branding consistent ("AutoResearchClaw" is the public name of Berb).
- Content duplicates claims from docs/README — when the pipeline changes, this site can go stale; verify stage counts and features against `berb/pipeline/stages.py`.
