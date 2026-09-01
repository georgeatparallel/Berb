---
name: repo-scripts
description: Map of scripts/ — dev/ops helper scripts: reachability checker, live smoke tests, git push/merge batch files, plotting. Use when verifying wiring, running live agent smoke tests, or doing repo maintenance.
---

# scripts/

Ad-hoc developer and operations scripts that live outside the `berb/` package. The most important is `check_reachability.py`, which verifies which modules are actually reachable from `berb run` / `berb serve` (referenced by CLAUDE.md and the `.reachability-allowlist` at repo root). The rest are live smoke tests, git convenience wrappers, and one-off maintenance tools.

## Contents

| File/Dir | Purpose |
|------|---------|
| `check_reachability.py` | Import-graph walk from CLI entry points; flags unwired modules (pairs with `.reachability-allowlist`) |
| `test_beast_mode_e2e.py`, `test_code_agent_live.py`, `test_code_agent_sandbox.py`, `test_codegen_v2.py` | Manual live smoke tests for the code agent / codegen (real API keys; not part of pytest suite) |
| `verify_all_models.py` | Pings every configured LLM provider/model to verify credentials and availability |
| `plot_iteration_showcase.py` | Generates the iteration-improvement showcase figure in `docs/figures/` |
| `add_author_attribution.py` | One-off script to stamp author attribution |
| `sentinel.sh` | Sentinel/watchdog runner |
| `metaclaw_start.sh` | Starts the MetaClaw bridge service |
| `push_to_github.sh` / `.bat`, `merge_to_main.bat`, `merge_to_main_FIXED.bat` | Git push/merge convenience wrappers (Windows-first) |
| `reorganize_project.bat`, `cleanup_docs.bat` | One-off repo reorganization / docs cleanup batch jobs |
| `rename.txt` | Notes for a past rename operation |

## Notes

- Run reachability check with `python scripts/check_reachability.py` — do this after wiring/unwiring modules.
- The `test_*.py` files here are NOT pytest tests; they are manual scripts that hit real LLMs/sandboxes.
- Batch files assume Windows; shell scripts assume Git Bash / WSL.
- One-off scripts (`reorganize_project.bat`, `rename.txt`, `add_author_attribution.py`) are historical — do not rerun casually.
