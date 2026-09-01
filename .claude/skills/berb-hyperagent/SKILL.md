---
name: berb-hyperagent
description: Map of berb/hyperagent/ — self-referential self-improving agent framework (Hyperagents paper, arXiv:2603.19461). Use when working on self-improvement loops, meta-agents, task-agent code mutation, or hyperagent memory.
---

# berb/hyperagent

Implementation of "Hyperagents: Self-Referential Self-Improving Agents" (Facebook AI Research, arXiv:2603.19461): a Task Agent solves research tasks via an editable Python program, a Meta Agent rewrites both the task agent's code AND its own modification procedure, and an ImprovementLoop evaluates variants and keeps the best. **Unwired/dormant** — nothing outside `berb/hyperagent/` imports it (not reachable from `berb run` or `berb serve`; `berb/self_evolve/` only cites the same paper). Entry point is `Hyperagent` from the package root.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | package exports: `Hyperagent`, `HyperagentState`, `ImprovementResult`, `TaskAgent`, `MetaAgent`, `PersistentMemory`, `ImprovementLoop` |
| `base.py` | Core abstractions: `Hyperagent`, `HyperagentState`, `AgentPhase` enum, `TaskResult`, `Improvement`, `ImprovementResult` dataclasses |
| `task_agent.py` | `TaskAgent` — executes an editable code file to solve tasks; Docker-based sandboxing (`TaskAgentConfig` with docker_* resource limits, `DOCKER_AVAILABLE` gate) for meta-generated code |
| `meta_agent.py` | `MetaAgent` — LLM-driven code modification of the task agent and of its own modification procedure (metacognition); produces `ModificationResult` diffs; lazily uses `berb.llm.client.LLMClient` |
| `improvement_loop.py` | `ImprovementLoop` — execute → track performance → generate modifications → create `Variant`s → evaluate → select best → store |
| `memory.py` | `PersistentMemory` — JSON-persisted store of `Improvement`s and `PerformanceRecord`s across runs, enabling cross-domain transfer |

## Wiring & entry points

- **No importers outside the package** — dormant capability; exercised only by tests.
- Public API: `from berb.hyperagent import Hyperagent` → `await agent.run_task(...)`, `await agent.self_improve()`.
- `MetaAgent` and `TaskAgent` take `berb.config.RCConfig`; `MetaAgent` lazily imports `berb.llm.client.LLMClient` for code generation.
- Security note: task-agent code executes in a resource-constrained Docker container when available (`sandbox_enabled=True` default).
