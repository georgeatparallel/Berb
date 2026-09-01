---
name: repo-configs
description: Map of configs/ — example and preset YAML run configurations (arc/berb templates, physics presets, CPU test run). Use when creating a run config, checking config schema examples, or setting up domain presets.
---

# configs/

Example and preset YAML configurations for pipeline runs. `berb setup` / `berb init` generates a working `config.arc.yaml` at repo root from the example template here; the CLI auto-detects `config.arc.yaml` or `config.yaml` at the root (override with `--config <path>`). Live configs (`config.yaml`, `config.berb.yaml`) sit at the repo root, not in this folder.

## Contents

| File/Dir | Purpose |
|------|---------|
| `config.arc.example.yaml` | Canonical template for the ARC-style config — copied/filled by `berb setup` |
| `config.berb.example.yaml` | Template for the berb-native config variant |
| `config_test_run.yaml` | CPU-only smoke-run preset (gradient-free optimization topic, full-auto mode, small budgets) |
| `physics_chaos.yaml` | Domain preset: chaotic-dynamics physics research run |
| `physics_hamiltonian.yaml` | Domain preset: Hamiltonian-systems physics research run |

## Notes

- Key sections across configs: `project` (name/mode), `research` (topic, domains, quality_threshold), `runtime` (parallelism, timeouts, retries), `notifications`, plus `llm.*` and `experiment.mode` in the full templates.
- `experiment.mode` options: `sandbox | docker | ssh_remote | colab_drive`.
- Never commit secrets into these files — API keys belong in `.env`; examples use placeholders.
- Use `config_test_run.yaml` for cheap end-to-end verification (no GPU needed): `berb run --config configs/config_test_run.yaml`.
