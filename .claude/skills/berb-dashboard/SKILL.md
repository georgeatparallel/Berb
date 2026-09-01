---
name: berb-dashboard
description: Map of berb/dashboard/ — run-monitoring data layer (artifact scanner, WebSocket broadcaster, metric aggregation) behind `berb serve`. Use when working on run snapshots, dashboard events, or training-curve extraction.
---

# berb/dashboard

Data layer for the live web dashboard: scans the `artifacts/` directory to build point-in-time `RunSnapshot`s of pipeline runs, periodically broadcasts changes (run discovered, stage complete, status changed, metrics updated) over the server's WebSocket, and aggregates overview metrics. **Wired via `berb serve`** — `berb/server/app.py` starts `start_dashboard_loop` and `berb/server/dialog/router.py` uses `DashboardCollector`. Not on the `berb run` path.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | package exports |
| `collector.py` | `RunSnapshot` dataclass + `DashboardCollector` — scans `artifacts/` for run state (stage, status, topic, metrics, log tail) |
| `broadcaster.py` | `DashboardBroadcaster.tick()` diffs snapshots against previous state and broadcasts `Event`s via `ConnectionManager`; `start_dashboard_loop` async polling loop |
| `metrics.py` | pure helpers: `aggregate_metrics(runs)` (totals/active/failed/avg stage) and `extract_training_curve(metrics)` from `training_log` entries |

## Wiring & entry points

- Importers: `berb/server/app.py` (`from berb.dashboard.broadcaster import start_dashboard_loop`), `berb/server/dialog/router.py` (`DashboardCollector`).
- Depends on `berb/server/websocket/` (`Event`, `EventType`, `ConnectionManager`).
- Reads filesystem only (default `artifacts/` dir); no LLM or config keys of its own.
