# Memory Model — Berb

Three memory systems coexist in Berb, each with a different lifecycle and scope.

---

## Tier 1: Ephemeral Stage Memory (`berb/memory/`)

**Purpose:** Cross-stage coordination within a single pipeline run. Stores embeddings, confidence scores, and retrieval indexes for ideation, experiment results, and writing feedback.

**Lifecycle:** Cleared after each pipeline run. `berb/memory/store.py` stores entries in memory-backed structures. No filesystem persistence between runs.

**Contents:**
- `ideation_memory.py` — Research topics, hypotheses, outcomes
- `experiment_memory.py` — Hyperparameters, architectures, training tricks
- `writing_memory.py` — Review feedback, paper structure patterns
- `retriever.py` — Semantic retrieval via embeddings
- `decay.py` — Time-decay weighting and confidence scoring

**Key fact:** Uses `run_dir`-scoped directories. Each pipeline invocation gets its own memory space. No cross-run contamination.

---

## Tier 2: Persistent Knowledge Graph (`berb/knowledge/`)

**Purpose:** Cross-run knowledge accumulation. Stores structured research findings, paper relations, and Obsidian-exportable notes that persist across pipeline invocations.

**Lifecycle:** Persistent across pipeline runs. Written during pipeline finalization (Stage 21: KNOWLEDGE_ARCHIVE, via `runner.py` calling `write_stage_to_kb()`). Survives between sessions.

**Contents:**
- `graph/` — Neo4j-compatible property graph of papers, findings, relations
- `base.py` — `write_stage_to_kb()` writes stage artifacts into the KB
- `obsidian_export.py` — Exports to Obsidian markdown vault format

**Key fact:** Controlled by `config.knowledge_base.backend`. Currently supports `"local"` filesystem and `"obsidian"` export. Future: Neo4j adapter.

---

## Tier 3: In-Memory Session Store (`berb/memory_vault/`)

**Status:** ⚠️ DEAD CODE — `__init__.py` defines the module but no other file imports it. Zero references across the codebase.

**Recommendation:** Remove `berb/memory_vault/` entirely in a cleanup pass. Its stated purpose (cross-session memory persistence) overlaps with `berb/knowledge/` (Tier 2), which already persists across runs via the knowledge graph.

---

## Lifecycle Summary

| Tier | System | Scope | Persistence | Active? |
|------|--------|-------|-------------|---------|
| 1 | `berb/memory/` | Single run | In-memory, cleared post-run | ✅ Yes |
| 2 | `berb/knowledge/` | Cross-run | Filesystem (JSON files + graph) | ✅ Yes |
| 3 | `berb/memory_vault/` | Cross-run | Filesystem | ❌ Dead code |

## Data Flow

```
Pipeline stage output
    │
    ├──> run_dir/stage-NN/ (filesystem artifacts)
    │
    ├──> berb/memory/ (ephemeral: embeddings, retrievers)
    │       │
    │       └── cleared on pipeline exit
    │
    └──> berb/knowledge/ (persistent: graph, Obsidian export)
            │
            └── survives across pipeline runs
```

## Migration Plan

1. Remove `berb/memory_vault/` directory (dead code, no callers)
2. If cross-run memory is needed beyond what `berb/knowledge/` provides, extend the knowledge graph schema — don't reintroduce a parallel memory system
