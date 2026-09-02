# W3 — Capability packages

**Wave:** W3 of `tasks/dead_code_wiring_plan.md`
**Scope as planned:** `reasoning` (2,188), `literature` (2,181), `memory` (1,147), `knowledge` (765),
`modes` (753), `self_evolve` (687) — sized before W0 corrected the instrument.
**Scope as found:** 16 modules / 2,975 loc.
**Disposal default:** PARK, 90-day horizon (2026-12-01), two strikes.

---

## 1. Two thirds of the planned wave does not exist

The plan budgeted ~10h for W3 on pre-W0 numbers. Re-measured:

| Package | Planned as dead | Actual |
|---|---:|---|
| `berb.reasoning` | 2,188 loc | **12/12 modules live** |
| `berb.modes` | 753 loc | **3/3 modules live** |

**2,941 loc of the wave was never dead.** Both packages became reachable the moment W0 credited
ancestor packages: `berb/reasoning/__init__.py` eagerly imports `base`, `multi_perspective`,
`registry` and the rest, so any reachable importer of *any* `berb.reasoning.*` module pulls the
whole package in. The old checker could not see that edge and reported all twelve dead.

`berb.literature` is not in this wave either — its unreachable modules are the exported-public-API
group held pending the `__all__` decision (`tasks/w2_untested_triage.md` §4).

What remains is four packages, all tested, none with a consumer.

---

## 2. Three of the four sit beside an occupied seam

This is what makes them PARK rather than WIRE: the pipeline already does the adjacent job.

| Dead package | LOC | Adjacent wired occupant |
|---|---:|---|
| `self_evolve` | 672 | `berb/evolution.py` (601) — records lessons per run and injects them as prompt overlays; imported at `pipeline/runner.py:20` |
| `knowledge.graph.*` | 736 | `berb/knowledge/base.py` (285) — writes stage artifacts to a Markdown/Obsidian KB; imported at `pipeline/runner.py:21` |
| `assessor.*` | 442 | `berb/review/ensemble.py` — the 5-reviewer + Area Chair ensemble is the wired paper-judgment seam |
| `memory.*` (4 modules) | 1,125 | none — but no seam either (see §3) |

Two of these are *adjacent*, not identical, and I do not want to overstate the overlap:

- `knowledge.graph` builds an entity/relation graph; `knowledge/base.py` persists Markdown. Same
  package, genuinely different capabilities. It is dead for want of a consumer, not because
  something else does its job.
- `assessor` scores papers on multiple dimensions and additionally recommends a venue and compares
  candidates. `review/ensemble.py` occupies paper *judgment*, but nothing occupies venue
  recommendation. I checked: **no pipeline stage references a venue or an assessor**, so the
  capability has no caller and no stage that would plausibly acquire one.

`self_evolve` is the closest to a true duplicate — both it and `evolution.py` exist to make later
runs better from earlier ones. It is parked rather than deleted because it is the SelfEvolve half
of the Hyperagents paper (arXiv:2603.19461) whose other half, `berb.hyperagent`, is already parked
under D-03. Splitting them would be incoherent: they should un-park or go together.

---

## 3. `memory` — dead imported by dead

`berb.memory` is 5/9 live. The wired half is real: `review/ensemble.py:722-723` imports
`memory.embeddings` and `memory.retriever` for review-diversity scoring.

The dead half is four modules:

- `shared_memory` (688) — its only importer anywhere is `experiment/self_correcting.py`, which W1
  parked. Dead code reachable only from dead code.
- `experiment_memory` (165), `ideation_memory` (144), `writing_memory` (128) — per-stage memory
  stores with no importer at all.

No wired module competes with these. They are simply unconsumed, and no stage is currently shaped
to consume them.

---

## 4. Verdicts

All 16 PARK, revisit 2026-12-01, two strikes. This is the outcome the plan anticipated for this
wave ("expect a high PARK/WIRE ratio"), and on the evidence it is the honest one: every module here
is a working capability with no caller, and in three of four cases the pipeline already has
something occupying the neighbouring seam.

Nothing here qualified for DELETE. None failed the import smoke test, and none is a strict
duplicate of a wired module — `self_evolve` is the closest and is held with its Hyperagents sibling
instead.

| Group | Modules | LOC | Un-park trigger |
|---|---:|---:|---|
| `memory.shared_memory` | 1 | 688 | A wired consumer for cross-agent shared memory. Its only importer, `experiment/self_correcting.py`, is itself parked — un-park them together or not at all |
| `memory.{experiment,ideation,writing}_memory` | 3 | 437 | A stage retaining state across runs beyond what `berb/evolution.py` records |
| `knowledge.graph.*` | 6 | 736 | A synthesis stage wanting an entity/relation graph rather than the Markdown KB `knowledge/base.py` writes |
| `self_evolve` | 1 | 672 | Hyperagents adopted. Tied to `berb.hyperagent` (D-03) — same paper, same decision |
| `assessor.*` | 5 | 442 | A venue-recommendation or paper-comparison stage. Multi-dimensional scoring alone is occupied by `review/ensemble.py` |

---

## 5. Applied

All 16 PARK entries as allowlist group D-07. Ratchet tightened 20,378 → 17,403.
