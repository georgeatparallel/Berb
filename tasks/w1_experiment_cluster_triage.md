# W1 — Experiment-cluster triage

**Wave:** W1 of `tasks/dead_code_wiring_plan.md` (promoted ahead of W2 by decision, 2026-09-02)
**Scope:** the 19 unreachable modules under `berb.experiment`, `berb.pipeline.optimization_integration`
and `berb.integrity.eval` — 7,240 loc. (`berb.experimental.*` is already allowlisted and excluded.)
**Method:** §3 of the plan — capability, duplicate scan, seam, import smoke test, verdict.
**Disposal default:** PARK on a 90-day horizon (revisit 2026-12-01), two-strikes auto-DELETE.

---

## 0. Import smoke test

All 19 modules import cleanly under the CI-equivalent environment. **No module qualifies
for the automatic import-failure DELETE**, so every verdict below rests on capability
analysis rather than rot.

---

## 1. The five-way overlap, resolved

The plan's premise was that `berb.experiment` carries five competing
search/execution mechanisms. That was roughly right but mis-drawn. There are two
distinct seams, and each already has a wired occupant:

| Seam | Wired occupant | Dead challengers |
|---|---|---|
| Post-failure repair | `pipeline/experiment_diagnosis.py` (905) + `pipeline/experiment_repair.py` (923), driven from `pipeline/runner.py:624-658` | `experiment/auto_debugger.py` (775), `experiment/self_correcting.py` (835) |
| Stage-10 code generation | `pipeline/code_agent.py` (1,585, LLM path, dispatched at `stage_impls/_code_generation.py:576-584`) **and** `pipeline/opencode_bridge.py` (external-CLI path, `:529`) | `experiment/code_agent.py` (836) |

`experiment/search/SearchRunner` is not a competitor to either — it is the wired
Stage-12 search, and `evolutionary_search` operates on a different object entirely
(design proposals, not code), so it is not a duplicate of it.

**Correction to my earlier framing:** "five coexisting search mechanisms, four dead"
overstated the overlap. `pipeline/code_agent.py` is reachable and live for generation;
only its *tree-search* methods are deprecated stubs. The real finding is two occupied
seams with three dead challengers, which is a smaller but sharper problem.

---

## 2. Two live seams found — dead code that is actually a wiring bug

These are the wave's most valuable findings, because they are defects rather than debt.

### 2.1 `is_buggy_plots` is gated on but never set — `plot_verdict` is the missing producer

`experiment/search/scoring.py:104-108` implements a **hard gate**: a candidate whose
figures are judged invalid scores 0.

```python
if is_buggy_plots is True:  # None = not evaluated, skip gate
    return ScoreBreakdown(total=0.0, ..., reason="Candidate produced invalid figures")
```

Nothing in the codebase ever sets that field to `True`. `journal.py:207,298` only pass
it through from a dict or from `record_evaluation`, and `SearchRunner._evaluate_node`
never computes it. The producer is `experiment/plot_verdict.verify_plots` — which is
unreachable.

**Consequence:** a wired quality gate is permanently inert. Search cannot currently
reject a candidate for producing broken figures, and every node carries
`is_buggy_plots=None`.

**Seam:** `SearchRunner._evaluate_node`, alongside the existing metric parsing.

### 2.2 The three-way split contract is declared but has no producer

`pipeline/contracts.py:59-81` is **wired** and defines `SplitEvidence` with
`metric_select` / `metric_rank` / `metric_report` — the train/validation/test separation
that makes a best-of-N result honest. `experiment/split_policy.py` imports that contract
and implements `partition()`, `selection_penalty()` and `admit()` against it.

Nothing constructs a `SplitEvidence`. `admit()` and `GateConfig` have **zero callers**
outside `split_policy` itself.

**Consequence:** the contract is declarative only. Nothing in the pipeline separates
selection from reporting, and no selection-bias correction is applied to reported
metrics. This matters directly for any best-of-N work: raising N inflates the reported
metric, and the correction exists but is not connected.

**Seam:** requires *building the producer* (partition a dataset spec, populate
`SplitEvidence`, call `admit()` at the claim gate) — larger than a wiring change, so it
is scheduled, not done here.

---

## 3. Verdicts

### WIRE — live seam identified

| Module | LOC | Seam | Note |
|---|---:|---|---|
| `experiment.plot_verdict` | 249 | `SearchRunner._evaluate_node` → populate `is_buggy_plots` | Closes §2.1. Smallest, highest-value wiring in the wave. |
| `experiment.split_policy` | 297 | Producer for `contracts.SplitEvidence`, then `admit()` at the claim gate | Closes §2.2. Needs a producer built first — scheduled, not a drop-in. |
| `experiment.react_agent` | 389 | `SearchRunner`'s candidate generator, for `improve`/`debug` operators | Depends on the generator work (the wired generator is currently a stub returning one static file). Sequenced with that, not before it. |

### DELETE — duplicates an occupied wired seam

| Module | LOC | Occupant | Blast radius |
|---|---:|---|---|
| `experiment.auto_debugger` | 775 | `experiment_diagnosis` + `experiment_repair` do classification, fix generation, re-run and re-assess — strictly more | Module + `tests/` references |
| `experiment.code_agent` | 836 | `pipeline/code_agent` (LLM) and `opencode_bridge` (external CLI) both occupy Stage-10 generation | **Not self-contained** — see §4 |

### PARK — revisit 2026-12-01, two strikes

| Module | LOC | Un-park trigger |
|---|---:|---|
| `experiment.self_correcting` | 835 | A domain needing plan-act-reflect-revise beyond `experiment_repair` + the wired `physics_guards` |
| `experiment.compute_guard` | 720 | A paid-compute or GPU mode needing pre-flight affordability checks; `BudgetGovernor` + `cost_tracker` cover the wired path today |
| `integrity.eval.hidden_eval` | 591 | HCE adopted for Stage-12 selection; today its only importers are themselves dead |
| `experiment.progress` | 547 | Stage-level progress UI beyond `dashboard/collector` |
| `experiment.evolutionary_search` | 538 | Stage 9 wanting multi-candidate *design* evolution (distinct object from `SearchRunner`'s code search) |
| `pipeline.optimization_integration.*` (6 mods) | 1,140 | The AIRA2 shims — they exist to wire modules that are themselves parked, so they park as a group and un-park with whichever they serve |
| `experiment.evaluators.convergence` | 176 | A search policy needing a convergence stop beyond `BudgetGovernor` |
| `experiment.harness_template` | 121 | Template used only by the parked cluster |

---

## 4. The one deletion that is not self-contained

`experiment/code_agent.py` is the **sole reader of `config.experiment.cli_agent`**
(`code_agent.py:797-798`). `CliAgentConfig` is declared and parsed in `berb/config.py`
and reaches nothing else — dangling user-facing configuration that silently does nothing
today.

Deleting the module therefore means also removing `CliAgentConfig`, its field on
`ExperimentConfig` and its parser branch, or the config keeps advertising a backend that
no longer exists. That touches wired config-parsing code, so it is **proposed, not
applied** here.

Leaving the config in place while deleting its only consumer would be worse than either
option: it would look supported and do nothing.

---

## 5. Applied in this pass

Only the PARK entries, which are additive and reversible. The two DELETEs and the three
WIREs are proposals — the deletions because one is not self-contained (§4), the wirings
because two of the three depend on work sequenced elsewhere.
