# berb-arch — Berb Architecture Reference

## Description

Instantly load the full Berb codebase architecture so you can answer questions
about the project or make changes without guessing at structure.

## Trigger Conditions

Activate this skill when:
- The user asks "how does [X] work in Berb?"
- You are about to modify any Berb module and need to understand dependencies
- The user asks where something is implemented
- The user asks about the pipeline, stages, LLM routing, literature search, etc.
- You're starting a new session on the Berb project

## Instructions

Read the architecture file immediately:

```
Read file: docs/CODEBASE_MIND_MAP.md
(Full path: E:\Documents\Vibe-Coding\Berb\.claude\worktrees\adoring-shirley\docs\CODEBASE_MIND_MAP.md)
```

Use the file contents to:

1. **Locate the right module** — Check Section 2 (module map) to find the exact file
2. **Understand stage flow** — Check Section 3 (23 stages table) and Section 4 (data flow)
3. **Trace connections** — Understand how the module fits into the pipeline
4. **Check current TODO state** — Section 15 lists what's done vs. planned
5. **Find entry points** — Section 16 has common `from berb.X import Y` patterns

## Key Facts (Quick Reference)

- Entry point: `berb/cli.py:main()` → `berb/pipeline/runner.py:execute_pipeline()`
- 23 stages across phases A–H; 3 gate stages (5, 9, 20)
- Stage impls: `berb/pipeline/stage_impls/_*.py` (one file per phase)
- LLM cascade: NadirClaw (simple→mid→complex)
- Literature: OpenAlex → Semantic Scholar → arXiv → grey search
- Experiment modes: sandbox / docker / ssh_remote / colab / agentic
- Presets: `berb/presets/catalog/*.yaml` loaded via `load_preset("name")`
- Full architecture: `docs/CODEBASE_MIND_MAP.md`
