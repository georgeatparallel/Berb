# Dead-Code Research & Wiring Plan

**Status:** APPROVED — disposal default, W0 scope and wave order settled 2026-09-02 (§8). Ready to execute from W0.
**Date:** 2026-09-02
**Scope:** the 119 modules / 30,763 loc that `scripts/check_reachability.py` reports
as unreachable from `berb run` / `berb serve`.
**Goal:** for every dead module, reach one of three defensible end states —
WIRED, DELETED, or PARKED-with-an-ID — and leave behind an instrument that keeps
the number from silently growing again.

---

## 0. Pre-work already done (VERIFIED, 2026-09-02)

This plan is not starting from zero. The following was measured before drafting,
because a plan built on an unvalidated instrument is a plan to chase artifacts.

### 0.1 The instrument is ~97% trustworthy

`check_reachability.py` is pure-AST static import reachability. Four
false-positive mechanisms were tested:

| Mechanism | Result | Impact |
|---|---|---|
| Lazy `__getattr__` + `importlib` re-exports (`berb/_lazy.py`) | **0 false-dead.** Parsed all 5 `lazy_exports` maps, resolved every `from <pkg> import Name` in reachable code — none resolved to an unreachable submodule. | 0 loc |
| Parent-package `__init__.py` not credited when a submodule is reachable | **20 packages affected.** Python executes `berb/experiment/__init__.py` whenever `berb.experiment.factory` is imported, but the tool never adds that edge. | **723 loc** false-dead |
| Literal-string `importlib.import_module("...")` | **1 confirmed false-dead:** `berb.quality` (187 loc) is imported from reachable `berb/pipeline/summary.py:78`. 4 other sites resolve to already-reachable modules. | **187 loc** false-dead |
| Plugin-registry dynamic loading (`berb/plugins/__init__.py:314`, computed name) | Not yet checked — genuinely dynamic, needs a registry-manifest cross-check. | UNKNOWN |

**Corrected figure: ~29,853 loc genuinely unreachable** (30,763 − 910), of which
4,614 loc across 13 modules is already allowlisted as parked.
**Decision surface: ~25,239 loc / 106 modules.**

The instrument's entry set is generous — 17 package prefixes (`berb.mcp`,
`berb.dashboard`, `berb.copilot`, `berb.plugins`, `berb.skills`, …) plus 6 exact
modules — so unreachability is a *strong* signal, not a coverage gap.

### 0.2 Git archaeology is unusable here — do not plan around it

58 commits total. History begins 2026-07-20 and every dead module's
`--diff-filter=A` date is that same day (squashed/imported history).
`2026-08-21 84d72c4 style: run black and ruff --fix across berb/ and tests/`
touched nearly every file, so last-modified dates carry no signal either.

**Consequence:** "was this ever called?" and "is this abandoned?" cannot be
answered from history. Triage must be answered from *capability analysis*, which
is the expensive path. Plan the budget accordingly.

### 0.3 The dead code is mostly tested, which changes the triage

| Bucket | Modules | LOC |
|---|---:|---:|
| Allowlisted (parked) | 13 | 4,614 |
| Not allowlisted, **has test references** | 81 | 19,232 |
| Not allowlisted, **no test references** | 25 | 6,917 |

81 tested-but-unwired modules means this is not accumulated sloppiness — it is
capability built to spec and never connected. Tests prove *intent*, not *value*:
they raise the cost of deletion but are not an argument for wiring.

### 0.4 Per-package decision surface (non-allowlisted)

```
  5718  13 mods (2 untested, 1290 loc)  berb.experiment
  2838   9 mods (3 untested,  537 loc)  berb.llm
  2188   5 mods (0 untested)            berb.reasoning
  2181   5 mods (0 untested)            berb.literature
  1783   9 mods (3 untested,  589 loc)  berb.pipeline
  1532   4 mods (2 untested, 1366 loc)  berb.writing
  1147   5 mods (0 untested)            berb.memory
   765   7 mods (0 untested)            berb.knowledge
   753   2 mods (0 untested)            berb.modes
   687   1 mods                         berb.self_evolve
   638   2 mods (2 untested,  638 loc)  berb.integrations
   612 · 611 · 603 · 571 · 514 · 452 · 404 …  (bridges, integrity, optimization,
                                               learning, audit, assessor, mnemo)
```

---

## 1. The two questions that actually decide each module

Everything below reduces to answering these, per module. Wiring is the *last*
question, not the first.

**Q1 — Does a wired module already do this job?**
This is the highest-value analytical step and the one most likely to be skipped.
Berb currently carries **at least five coexisting experiment-search/execution
mechanisms**, four of them dead:

| Mechanism | State |
|---|---|
| `berb.experiment.search.SearchRunner` | **wired** (Stage 12, behind `experiment.search.enabled`) |
| `berb.experiment.evolutionary_search.DesignProposalEvolver` | dead |
| `berb.pipeline.code_agent` tree search | dead (self-documented as deprecated) |
| `berb.experiment.self_correcting` | dead |
| `berb.experiment.auto_debugger` | dead |

Wiring all of these would be actively harmful: five overlapping search paths is
worse than one. The de-duplication pass must run **before** any wiring design.
Expected outcome for this cluster: one wins, the rest are DELETE or PARK.

**Q2 — If nothing wired does this job, is the job worth doing?**
A capability with no consumer is not a capability. Answer only in terms of a
named pipeline stage or CLI surface that would call it, and what a user gets
that they do not get today.

---

## 2. Triage taxonomy

Every one of the 106 modules lands in exactly one bucket, with a written
one-line justification.

- **FIX-INSTRUMENT** — not actually dead. Fix the checker, not the code.
  *Pre-identified: 20 phantom packages (723 loc) + `berb.quality` (187 loc).*
- **WIRE** — capability the pipeline demonstrably lacks, a named seam exists, no
  wired duplicate, tests pass.
- **DELETE** — no seam, no consumer, or duplicates a wired module. Deletes the
  module **and its tests** (precedent: allowlist entries D-01, D-04).
- **PARK** — plausible future value but no roadmap. Gets an allowlist ID, a
  justification, and a revisit date, matching the existing `D-NN` convention.

**Default is PARK on a short horizon** (decision, 2026-09-02). A module with no
seam and no consumer is parked, not deleted, unless it fails the import smoke
test or duplicates a wired module — those two are DELETE regardless.

To keep PARK from becoming an indefinite holding pen, it carries a ratchet:

- **Horizon is 90 days, not two quarters.** New entries read
  `Parked — 2026-09-02; revisit 2026-12-01`. The existing `revisit Q1 2027`
  entries (`berb.hyperagent`, `berb.i18n`, `berb.experimental`, 4,614 loc) are
  re-dated to the same 2026-12-01 review so the whole list moves together.
- **Two strikes and it goes.** A module that reaches its second review still
  with no consumer and no seam is DELETED at that review. PARK buys one cycle
  of benefit-of-the-doubt, not tenure.
- **Every PARK names what would un-park it** — the stage, CLI surface or
  config flag whose arrival would make it live. "Might be useful" is not a
  trigger and does not qualify for PARK; that is a DELETE.

Trade-off accepted with this choice: the ~25,239 loc decision surface will not
shrink much in this pass — most of it moves from *undocumented* dead code to
*documented, dated* dead code. That is a real gain in legibility and a deferred
gain in size; the 2026-12-01 review is where the size gain lands.

---

## 3. Research method, per module

Mechanical, so it can be batched and parallelised across packages.

1. **Capability statement** — one sentence: what it does, what calls it *inside*
   its own package, what it would need from a caller.
2. **Duplicate scan** — grep the *reachable* set for the same capability.
   Record the wired competitor by `file:line` or record "none".
3. **Seam identification** — name the exact call site that would invoke it:
   stage number, function, config flag. "It could be useful in Phase D" is not a
   seam. No seam → DELETE or PARK, never WIRE.
4. **Import smoke test** — `python -c "import <mod>"`, then run its tests. A
   module that no longer imports is DELETE regardless of everything else.
5. **Cost & failure semantics** — new API calls? new dependency? what happens on
   failure — INFO / ADVISORY / WARN / BLOCK? (matches `integrity/findings.gates()`
   vocabulary already in the repo). Undefined failure semantics → not WIRE-ready.
6. **Verdict + one-line justification**, appended to a triage table.

Estimated ~15 min/module → **~26h across 106 modules**, batched by package.

---

## 4. What "wired properly" means

A module is not wired because an `import` exists. All five must hold:

- [ ] Reachable from an entry point per `check_reachability.py` with **no new
      allowlist entry**
- [ ] Actually *invoked* on a default or explicitly config-gated path — proven by
      the runtime trace (§5, W0), not by the import graph
- [ ] Config flag exists, defaults chosen deliberately, documented in
      `config.arc.example.yaml` and CLAUDE.md's subsystem table
- [ ] An integration test drives it **through the pipeline**, not by direct import
- [ ] Cost accounted to `cost_tracker` and, where it runs inside search, to
      `BudgetGovernor`; failure semantics documented

---

## 5. Execution waves

**W0 — Instrument (do first, ~4h).** Everything downstream reads these outputs.
- [ ] Fix parent-package edges in `check_reachability.py` (−723 loc of noise)
- [ ] Resolve literal-string `import_module("...")` calls (−187 loc; unblocks `berb.quality`)
- [ ] Cross-check the plugin registry for dynamically loaded modules
- [ ] **Add a runtime trace**: `coverage.py` over `berb run`, emitting
      *executed* modules. Confirmed available (decision, 2026-09-02). No
      dedicated CPU config exists in `configs/` today — use a copy of
      `configs/config.berb.example.yaml` with `experiment.mode: sandbox`
      (CPU-local, no Docker/GPU) and a narrow topic, and commit it as
      `configs/config.trace.yaml` so the trace is reproducible. API keys come
      from the operator's environment, not the repo. Static reachability cannot
      see reachable-but-never-invoked code — expect this to reveal a *second*
      dead set hiding inside the 292 "reachable" modules
- [ ] Wire `check_reachability.py` into `.github/workflows/ci.yml` with the
      corrected LOC ceiling — **it is not in CI today**, which is why this grew

**W1 — De-duplicate the experiment cluster (~6h).** *Promoted ahead of the
free wins by decision, 2026-09-02.* `berb.experiment` is the largest surface
(5,718 loc / 13 mods) *and* the one with the known five-way overlap. Pick one
winner, dispose of the rest. This wave also decides `split_policy` and
`hidden_eval`, which the separate RPM analysis flags as correctness-relevant —
those are the strongest WIRE candidates in the repo, and the reason this wave
goes first: it unblocks the downstream search work.

Note the interaction with default-PARK: the losers of the five-way overlap are
duplicates of a wired module, which is an explicit DELETE case, not a PARK. This
wave should therefore still shrink the surface.

**W2 — Free wins (~2h).** The 25 untested + unreachable modules (6,917 loc).
Highest confidence, lowest analysis cost. Under default-PARK most will park with
a 2026-12-01 revisit; the ones that fail the import smoke test are DELETE now.
Biggest: `compute_guard` (728), `traceable_citations` (693), `citation_engine`
(673), `scite_mcp` (606), `cost_quality` (581), `progress` (562),
`cross_project_learning` (542), `reproducibility` (498).

**W3 — Capability packages (~10h).** `reasoning` (2,188), `literature` (2,181),
`memory` (1,147), `knowledge` (765), `modes` (753), `self_evolve` (687).
All fully tested, zero untested modules — expect a high PARK/WIRE ratio and
argue each one on Q2, hard.

**W4 — Infrastructure (~4h).** `llm` (2,838), `pipeline` (1,783),
`optimization`, `learning`, `audit`, bridges. Mostly cost/routing machinery;
`extended_router` is already documented in CLAUDE.md as a `_MockProvider` stub →
DELETE candidate.

**W5 — Governance (~2h).** Rewrite `.reachability-allowlist` with the surviving
PARK set, fresh `D-NN` IDs and revisit dates; update CLAUDE.md's subsystem table
and `docs/CODEBASE_MIND_MAP.md`; record the new CI ceiling.

**Total: ~28h.** Waves W1–W4 are independent after W0 and can run in parallel.

---

## 6. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Wiring things because they exist, not because they're needed** | **high** | **high** | Q1 duplicate scan is mandatory and precedes seam design; default verdict is DELETE |
| Deleting a module a user imports directly as a library | med | med | `git rm` in a single reviewable commit per wave; MIT-licensed and recoverable from history |
| Tests give false confidence (81 tested dead modules) | high | med | Tests are evidence of intent only; W0's runtime trace is the evidence of *use* |
| Triage stalls into a permanent PARK list | **high** (raised by the default-PARK decision) | med | 90-day horizon, not two quarters; two-strikes auto-DELETE at the second review; every PARK must name its un-park trigger; existing Q1 2027 entries re-dated to 2026-12-01 so nothing hides behind a longer clock |
| W0 runtime trace needs API keys / a working run | med | med | Use the CPU test config in `configs/`; if unavailable, W0 ships static fixes only and the trace moves to its own task |
| Churn collides with the in-flight RPM/search work | med | med | W2 sequenced to decide the experiment cluster *before* any RPM code lands |

---

## 7. Definition of done

- [ ] Every one of the 106 modules has a verdict + one-line justification in a
      triage table committed to `tasks/`
- [ ] `check_reachability.py` corrected, running in CI, ceiling set to the new
      measured value
- [ ] Runtime-trace tooling committed and documented
- [ ] Allowlist contains only entries with an ID, justification and revisit date
- [ ] CLAUDE.md subsystem table and `docs/CODEBASE_MIND_MAP.md` reflect reality
- [ ] `ruff`, `mypy berb/`, `bandit` and the full test suite green after each wave

---

## 8. Decisions taken (2026-09-02)

1. **Disposal default: PARK on a short horizon**, not DELETE. Encoded in §2 with
   a 90-day revisit, a two-strikes auto-DELETE at the second review, and a
   mandatory un-park trigger per entry. DELETE still applies unconditionally to
   modules that fail the import smoke test and to duplicates of a wired module.
2. **W0 runtime trace is in scope** — a runnable cheap config is available. W0
   commits `configs/config.trace.yaml` (`experiment.mode: sandbox`, CPU-local)
   so the trace is reproducible; credentials come from the operator's
   environment.
3. **Wave order: W1 is the experiment-cluster de-duplication**, promoted ahead
   of the untested-module sweep (now W2), because it unblocks the downstream
   search work and decides `split_policy` / `hidden_eval`.

## 9. Prerequisite: CI is red on `main`

Independent of this plan, `main` @ `9233e61` fails two CI checks (run
[33582937415](https://github.com/georgehadji/Berb/actions/runs/33582937415)):

- **Lint** — `ruff format --check` wants 353 of 596 files reformatted. The tree
  was formatted by a ruff older than 0.15.8; the `ruff>=0.15,<0.16` pin at
  `pyproject.toml:82` was not tight enough. The list includes `berb/cli.py`,
  `berb/pipeline/runner.py` and `berb/pipeline/executor.py`, so this is the
  whole tree, not neglected corners.
- **Type Check** — `types-PyYAML` is missing from the `dev` extra
  (`pyproject.toml:72-84`), producing 3 `Library stubs not installed for "yaml"`
  errors. Nothing in `berb/` is wrong.

W0 adds `scripts/check_reachability.py` to `ci.yml`. Adding a gate to a pipeline
that is already failing produces a signal nobody reads, so **both fixes should
land before W0** — each as its own PR (the reformat is mechanical but touches
353 files; the stub package is a one-line change).
