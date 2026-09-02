# W2 — Untested + unreachable modules

**Wave:** W2 of `tasks/dead_code_wiring_plan.md`
**Scope:** the 24 modules / 13,608 loc that are unreachable from `berb run`, not allowlisted,
and carry **no test reference at all**. The plan called these "free wins" — the highest-confidence,
lowest-analysis-cost bucket.
**Disposal default:** PARK, 90-day horizon (2026-12-01), two strikes.

---

## 1. They are not all free, and one third are not dead

The wave's premise — untested + unreachable = safe to dispose of — held for about half the set.
Two findings cut against it.

### 1.1 Seven are the package's exported public API

`berb.literature` and `berb.llm` maintain flat public APIs via `berb/_lazy.py` (PEP 562), and
seven of the 24 are the modules behind names listed in a package `__all__`:

| Module | LOC | Exported names |
|---|---:|---:|
| `literature.citation_graph` | 1,076 | 8 |
| `literature.structured_notes` | 897 | 6 |
| `literature.section_analysis` | 865 | 10 |
| `literature.evidence_map` | 790 | 9 |
| `literature.multimodal_search` | 605 | 6 |
| `literature.citation_classifier` | 497 | 6 |
| `literature.recency_filter` | 359 | 5 |
| `llm.presets` | 403 | 11 |

I checked all 83 exported names across both packages: **every one resolves**. `from berb.llm import
get_model` works today and lands in `berb.llm.presets`. These modules are unreachable from the
*pipeline* while being live from the *package's published surface* — a distinction the plan's
taxonomy did not have.

Across the whole 64-module decision surface this is **10 modules / 6,316 loc**, a quarter of it.

**But the API is undocumented.** `README.md:352-368` documents a "Programmatic API" consisting of
exactly three symbols — `RCConfig`, `execute_pipeline`, `AdapterBundle` — all of which are already
reachable. Nothing in the README or `docs/` shows `from berb.literature import ...`.

So (INFERENCE, high confidence) these are a maintained-but-unadvertised surface that no internal
caller uses. That makes them PARK candidates rather than untouchable API — but **not** DELETE
candidates, because deleting one means editing a wired `__init__.py`, narrowing a published
surface with no deprecation, and breaking any external consumer relying on it.

**Open question for the user (§4).**

### 1.2 `openrouter_models_data` is transitively public

At 3,528 loc it is the single largest module in the whole decision surface, and it is untested. It
is not directly exported, but `llm/openrouter_adapter.py` imports it at module level, and that
adapter *is* exported (`ModelVariant`, `OpenRouterProvider`, `strip_variant` are in
`berb.llm.__all__`). It is a generated-looking model/pricing table, so "untested" is close to
meaningless for it — the risk is staleness, not correctness.

Grouped with §1.1: same disposition, same open question.

---

## 2. Verdicts

### DELETE — zero references anywhere, duplicates an occupied wired seam

| Module | LOC | Occupant | Evidence |
|---|---:|---|---|
| `config.wizard` | 344 | `berb/wizard/quickstart.py` | `cli.py:657` imports `QuickStartWizard` from the wired `berb.wizard` package for `berb setup`/`berb init`. Two interactive config wizards; one is called. |
| `llm.retry_utils` | 118 | `LLMClient._call_with_retry` (`client.py:721`, called at `:657`) | Both implement retry-with-backoff for LLM calls. One is wired into every request. |

Neither is referenced by any module or test — grep across `berb/` and `tests/` returns nothing.

### PARK — revisit 2026-12-01, two strikes

| Module | LOC | Un-park trigger |
|---|---:|---|
| `writing.traceable_citations` | 689 | Citation-provenance rendering beyond the wired `integrity/anchors.py` |
| `writing.citation_engine` | 673 | Page-level citation generation reaching a writing stage; `literature/models.py` covers the wired bibtex path |
| `integrations.scite_mcp` | 602 | A scite.ai API key becoming a supported configuration |
| `optimization.cost_quality` | 575 | Cost/quality routing adopted beyond the wired `nadirclaw_router` |
| `learning.cross_project_learning` | 532 | Multi-project runs; today `berb/evolution.py` covers within-project lessons |
| `audit.reproducibility` | 496 | A reproducibility-package deliverable; `pipeline/packaging.py` collects artifacts but emits no `environment.yml`/`Dockerfile` |
| `llm.speculative_router` | 394 | Speculative execution adopted. Note it duplicates the *also dead* `llm/speculative_gen.py` — two modules, one stated purpose, neither wired; at most one should ever be un-parked |
| `voice.synthesizer` | 47 | Voice output becoming a product feature |
| `llm.deepmind_client` | 19 | Referenced from `deep_query_client.py:21`; parked rather than deleted because that reference exists |
| package shims: `integrations`, `learning`, `optimization`, `audit` | 99 | Park with the modules they front |

---

## 3. Applied

The PARK entries (allowlist group D-06) and the two DELETEs above. The public-API group is
**untouched pending §4**.

---

## 4. RESOLVED 2026-09-02 — `berb.literature` is a contract

**Decision: option 1, scoped to `berb.literature`.** Its `__all__` modules are entry
points in `check_reachability.py` (`PUBLIC_API_PACKAGES`), and
`tests/test_public_api_contract.py` asserts every exported name resolves — the
mitigation for the risk option 1 carried, that exempting the API from the gate
leaves nothing watching it. Verified by breaking `__all__` deliberately and
confirming the test fails.

Scoped narrowly on purpose: five packages in this repo declare an `__all__`, and
crediting all of them would have un-parked `compute_guard`, `evolutionary_search`,
`hidden_eval` and `optimization_integration` — modules triaged as dead on their
own merits in W1. `berb.llm` (4,366 loc) remains undecided.

Ratchet: 10,977 → 5,888.

### The original question, for the record

10 modules / 6,316 loc — a quarter of the decision surface — are unreachable from `berb run` but
are the package's exported, working, undocumented public API.

Three options:

1. **Treat `__all__` as an entry point.** Teach `check_reachability.py` that a name in a package's
   `__all__` is a root, the same way `berb.cli` is. Honest if the API is a real contract; it
   removes 6,316 loc from the surface at a stroke and stops the checker flagging published API as
   dead. Risk: it also stops the checker noticing when that API rots.
2. **Park them as a group** (recommended interim). Costs nothing, keeps them visible, and forces
   the question again on 2026-12-01.
3. **Delete them and narrow `__all__`.** Only defensible if the packages are declared
   internal-only. Requires editing wired `__init__.py` files and silently removing a working
   surface — the most expensive and least reversible option.

My recommendation is 2 now and a decision on 1 vs 3 once you say whether `from berb.literature
import ...` is a contract you intend to keep. I did not want to answer that on your behalf: it is a
product decision about what Berb *is*, not a code-health call.
