---
name: berb-copilot
description: Map of berb/copilot/ — interactive Co-Pilot mode (pause/feedback/branch) for pipeline runs. Use when working on research modes, stage pause gates, user feedback handling, or exploration branches.
---

# berb/copilot

Implements an interactive "Co-Pilot" layer for pipeline execution: three research modes (co-pilot, auto-pilot, zero-touch), pause-at-stage gating, file-based user feedback (approve/modify/retry/skip/branch/rollback), and exploration branches that copy stage state under `run_dir/branches/`. **Unwired/dormant**: no module outside `berb/copilot/` imports it — `berb/config.py` itself documents "berb/copilot/ has no importer". Its config section (`CoPilotConfig`) is parsed from `config.arc.yaml` but never consumed by the runner.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | package exports: `CoPilotController`, `BranchManager`, `FeedbackHandler`, `ResearchMode` |
| `modes.py` | `ResearchMode` enum: `CO_PILOT` (pause every stage), `AUTO_PILOT` (pause at gates), `ZERO_TOUCH` (never pause) |
| `controller.py` | `CoPilotController` — decides `should_pause(stage, is_gate)` per mode/config; formats stage-result summaries with available actions |
| `feedback.py` | `Feedback` frozen dataclass + `FeedbackHandler` — writes feedback requests / reads user responses as JSON in the run dir; `FEEDBACK_ACTIONS` set |
| `branching.py` | `BranchManager` — creates/lists/deletes exploration branches by copying `stage-NN/` dirs, enforces `max_branches`, writes branch metadata JSON |

## Wiring & entry points

- Importers: none outside the package (verified by grep; also stated in `berb/config.py` line ~119). Not reachable from `berb run` or `berb serve`.
- Config: `CoPilotConfig` in `berb/config.py` (`copilot.mode` with `COPILOT_MODES = ("co-pilot", "auto-pilot", "zero-touch")`, `pause_at_gates`, `pause_at_every_stage`, `max_branches`) — parsed but unused.
- Entry point if reactivated: `CoPilotController(config, run_dir)` wrapped around the pipeline runner's stage loop.
