# Dead-Code Research & Wiring Plan

**Status:** IN PROGRESS — W0 complete; W1, W2 and W3 triaged (2026-09-02). Approved — disposal default, W0 scope and wave order settled 2026-09-02 (§8). Ready to execute from W0.
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

### 0.1 The instrument was wrong in both directions — W0 fixed it

`check_reachability.py` is pure-AST static import reachability. Five
false-verdict mechanisms were tested; four were real and are now fixed.

| Mechanism | Finding | Effect |
|---|---|---|
| Parent-package `__init__.py` not credited when a submodule is reachable | **Real.** Python executes `berb/experiment/__init__.py` whenever `berb.experiment.factory` is imported, but no import statement names it. | reclaimed as live |
| Literal `importlib.import_module("...")` | **Real.** `berb.quality` (185 loc) is imported from reachable `berb/pipeline/summary.py:78`. | reclaimed as live |
| `if TYPE_CHECKING:` imports counted as real edges | **Real, and the big one.** Five package `__init__.py` files list their PEP 562 lazy exports a second time under `TYPE_CHECKING` so type checkers can see them. Those imports never execute. Crediting them made lazily-exported submodules look live merely because the parent package was imported — the exact inverse of how `berb/_lazy.py` works. | exposed as dead |
| PEP 562 lazy re-exports (`berb/_lazy.py`) | **Real but currently empty.** Now modelled: `from berb.llm import X` resolves through the package's export map to the submodule. No module is currently reached only this way, but with `TYPE_CHECKING` credit removed this became load-bearing and had to be modelled rather than spot-checked. | no change today |
| Plugin-registry dynamic loading (`berb/plugins/__init__.py:314`) | **Not real.** The loader scans runtime-supplied directories for `plugin.json`; no such manifest exists in-repo, so it cannot reach any `berb.*` module. | none |

Net effect of the corrections:

- **+37 modules / 4,611 loc** were never dead (ancestor packages, literal `import_module`)
- **−10 modules / 9,455 loc** were never live (`TYPE_CHECKING`-only credit) — led by
  `berb.llm.openrouter_models_data` (3,528), `berb.literature.citation_graph` (1,076),
  `structured_notes` (897), `section_analysis` (865), `evidence_map` (790)
- **Net: 4,844 loc more dead code than `main` reported**, not less

A sixth bug, in the allowlist rather than the graph: `load_allowlist` matched
exact module names, so the three parked package entries covered only their
`__init__` — 156 loc of the ~4.6k intended. Entries now cover a module and
everything beneath it, which is what the file's own comments describe.

**Corrected figures (2026-09-02):**

| | modules | loc |
|---|---:|---:|
| Unreachable | 92 | 35,212 (24%) |
| — allowlisted (parked) | 13 | 4,554 |
| **Decision surface** | **79** | **30,658** |

The instrument's entry set is generous — 17 package prefixes (`berb.mcp`,
`berb.dashboard`, `berb.copilot`, `berb.plugins`, `berb.skills`, …) plus 6
exact modules — so unreachability is a *strong* signal, not a coverage gap.

### 0.2 Git archaeology is unusable here — do not plan around it

58 commits total. History begins 2026-07-20 and every dead module's
`--diff-filter=A` date is that same day (squashed/imported history).
`2026-08-21 84d72c4 style: run black and ruff --fix across berb/ and tests/`
touched nearly every file, so last-modified dates carry no signal either.

**Consequence:** "was this ever called?" and "is this abandoned?" cannot be
answered from history. Triage must be answered from *capability analysis*, which
is the expensive path. Plan the budget accordingly.

### 0.3 The dead code is half tested, half not

| Bucket | Modules | LOC |
|---|---:|---:|
| Allowlisted (parked) | 13 | 4,554 |
| Decision surface, **has test references** | 50 | 15,204 |
| Decision surface, **no test references** | 29 | 15,454 |

Before W0 this read 81 tested / 25 untested; the `TYPE_CHECKING` correction
moved several large, untested modules into the dead set (`openrouter_models_data`
alone is 3,528 loc). Tests prove *intent*, not value: they raise the cost of
deleting but are not an argument for wiring.

### 0.4 Per-package decision surface (non-allowlisted)

```
  7257  berb.literature
  7174  berb.llm
  5484  berb.experiment
  1664  berb.pipeline
  1497  berb.writing
  1125  berb.memory
   736  berb.knowledge
   672  berb.self_evolve
```

Note the reordering: `berb.literature` and `berb.llm` are now the two largest
surfaces, ahead of `berb.experiment`, because the `TYPE_CHECKING` correction
exposed their lazily-exported modules. The wave order below still leads with
`berb.experiment` — that is a deliberate choice about unblocking downstream
work, not a claim that it is the biggest pile.

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
| `berb.experiment.evolutionary_search.DesignProposalEvolver` | dead (confirmed after W0) |
| `berb.pipeline.code_agent` tree search | module reachable, but its tree-search and evaluation methods are self-documented deprecated stubs that raise |
| `berb.experiment.self_correcting` | dead (confirmed after W0) |
| `berb.experiment.auto_debugger` | dead (confirmed after W0) |

Also still dead after W0, and named here because they are the strongest WIRE
candidates in the repo: `berb.experiment.split_policy` (selection-bias
correction), `berb.integrity.eval.hidden_eval` (HCE), `berb.experiment.react_agent`,
`berb.experiment.compute_guard`, and all five
`berb.pipeline.optimization_integration.*` modules.

Wiring all of these would be actively harmful: five overlapping search paths is
worse than one. The de-duplication pass must run **before** any wiring design.
Expected outcome for this cluster: one wins, the rest are DELETE or PARK.

**Q2 — If nothing wired does this job, is the job worth doing?**
A capability with no consumer is not a capability. Answer only in terms of a
named pipeline stage or CLI surface that would call it, and what a user gets
that they do not get today.

---

## 2. Triage taxonomy

Every one of the 79 modules lands in exactly one bucket, with a written
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

Trade-off accepted with this choice: the 30,658 loc decision surface will not
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

Estimated ~15 min/module → **~20h across 79 modules**, batched by package.

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

**W0 — Instrument. ✅ DONE 2026-09-02.** Everything downstream reads these outputs.
- [x] Credit ancestor packages in `check_reachability.py`
- [x] Resolve literal `import_module("...")` calls (unblocks `berb.quality`)
- [x] **Ignore `if TYPE_CHECKING:` imports** — not in the original plan; found
      while verifying the first two fixes, and the single largest correction
- [x] **Model PEP 562 lazy re-exports** — also unplanned; became load-bearing
      once `TYPE_CHECKING` credit was removed
- [x] **Fix allowlist prefix matching** — entries now cover submodules
- [x] Cross-check the plugin registry — no in-repo manifests, no false dead
- [x] Runtime trace: `scripts/runtime_trace.py` (coverage.py) plus
      `configs/config.trace.yaml` (CPU-only `experiment.mode: sandbox`).
      Classifies every module EXECUTED / EXECUTED-BUT-UNREACHABLE /
      IMPORTED-NOT-RUN / UNREACHABLE. **IMPORTED-NOT-RUN is the second dead
      set** static analysis cannot see; EXECUTED-BUT-UNREACHABLE flags a
      missed edge or a test-only caller. Smoke-tested against
      `tests/test_experiment_search.py`: 11 executed, 1
      executed-but-unreachable (`berb.experiment.plot_verdict`, imported by
      that test — a test caller, so the static verdict stands), 308
      imported-not-run.
- [x] `check_reachability.py` wired into `.github/workflows/ci.yml` as a
      ratchet at `--max-unreachable-loc 30658`, verified exact: passes at
      30658, fails at 30657

**Caveat on the trace:** a single run exercises one path, so *absence of
execution is weaker evidence than absence of an import*. Run several configs
before deleting anything on the trace's say-so alone.

**W1 — De-duplicate the experiment cluster. ✅ TRIAGED 2026-09-02**
(`tasks/w1_experiment_cluster_triage.md`). 19 modules / 7,240 loc.

Outcome: the "five competing search mechanisms" framing was mis-drawn. There are
**two occupied seams with three dead challengers**, not a five-way search
overlap — post-failure repair (occupied by wired `experiment_diagnosis` +
`experiment_repair`) and Stage-10 code generation (occupied twice, by
`pipeline/code_agent` for the LLM path and `opencode_bridge` for external CLI).

Two findings are defects rather than debt:

- **`is_buggy_plots` is gated on but never set.** `search/scoring.py:104-108`
  zeroes a candidate whose figures are invalid; nothing anywhere sets the field,
  so a wired quality gate is permanently inert. `plot_verdict.verify_plots` is
  the missing producer. → WIRE.
- **The three-way split contract has no producer.** `contracts.SplitEvidence` is
  wired and declares metric_select/rank/report; `admit()` and `GateConfig` have
  zero callers outside `split_policy`. Nothing separates selection from
  reporting, so no selection-bias correction is applied to reported metrics. →
  WIRE, after a producer is built.

- [x] 8 PARK entries applied to `.reachability-allowlist` as D-05, each naming
      its un-park trigger; the three pre-existing D-03 entries re-dated to the
      same 2026-12-01 review
- [x] CI ratchet tightened 30,658 → **25,990** (parking tightens, never loosens)
- [ ] 2 DELETEs proposed, not applied — `auto_debugger` (775) and
      `experiment/code_agent` (836). The second is **not self-contained**: it is
      the sole reader of `config.experiment.cli_agent`, so deleting it also
      means removing `CliAgentConfig` from `berb/config.py` or the config keeps
      advertising a backend that no longer exists.
- [ ] 3 WIREs identified with seams; `plot_verdict` is a drop-in, `split_policy`
      needs a producer, `react_agent` waits on the candidate-generator work

**W2 — Untested + unreachable. ✅ TRIAGED 2026-09-02**
(`tasks/w2_untested_triage.md`). 24 modules / 13,608 loc.

The "free wins" framing held for about half. Two findings cut against it:

- **A quarter of the whole decision surface is exported public API.** Ten
  modules / 6,316 loc sit behind names in `berb.literature.__all__` or
  `berb.llm.__all__`; all 83 exported names across both packages resolve.
  Unreachable from the *pipeline*, live from the *package's published surface* —
  a distinction this taxonomy lacked. `README.md:352-368` documents only three
  programmatic symbols, all already reachable, so the surface is maintained but
  unadvertised. Left untouched pending a product decision (see that doc, §4).
- `llm.openrouter_models_data` (3,528, the largest module in the surface) is
  transitively public through the exported `openrouter_adapter`.

- [x] 9 PARK entries applied as allowlist group D-06
- [x] 2 DELETEs applied: `config/wizard.py` (344) duplicates
      `berb/wizard/quickstart.py`, which `cli.py:657` actually calls, and
      `llm/retry_utils.py` (118) duplicates `LLMClient._call_with_retry`
      (`client.py:721`). Neither had a single reference in `berb/` or `tests/`.
- [x] CI ratchet tightened 24,966 → **20,378**
- [ ] Public-API group (10 mods / 6,316 loc) awaiting the `__all__` decision

**W3 — Capability packages. ✅ TRIAGED 2026-09-02**
(`tasks/w3_capability_triage.md`). 16 modules / 2,975 loc.

**Two thirds of this wave did not exist.** It was budgeted at ~10h on pre-W0
numbers; re-measured, `berb.reasoning` is 12/12 modules live and `berb.modes` is
3/3 live — **2,941 loc that was never dead.** Both became reachable the moment W0
credited ancestor packages: `berb/reasoning/__init__.py` eagerly imports its
submodules, so any reachable importer of one pulls in all twelve. `literature`
is not in this wave either; its unreachable modules are the exported-public-API
group held pending the `__all__` decision.

What remained is four packages, all tested, none with a consumer — and three of
the four sit beside a seam the pipeline already occupies: `evolution.py` for
self-improvement (`runner.py:20`), `knowledge/base.py` for knowledge persistence
(`runner.py:21`), `review/ensemble.py` for paper judgment.

- [x] 16 PARK entries applied as allowlist group D-07
- [x] CI ratchet tightened 20,378 → **17,403**
- [x] No DELETEs: none failed the import smoke test, and none is a strict
      duplicate of a wired module. `self_evolve` is closest, and is held with
      its Hyperagents sibling `berb.hyperagent` (D-03) rather than split from it.

**W4 — Infrastructure (~4h).** `llm` (2,838), `pipeline` (1,783),
`optimization`, `learning`, `audit`, bridges. Mostly cost/routing machinery;
`extended_router` is already documented in CLAUDE.md as a `_MockProvider` stub →
DELETE candidate.

**W5 — Governance (~2h).** Rewrite `.reachability-allowlist` with the surviving
PARK set, fresh `D-NN` IDs and revisit dates; update CLAUDE.md's subsystem table
and `docs/CODEBASE_MIND_MAP.md`; record the new CI ceiling.

**Total: ~22h remaining** (W0 done). Waves W1–W4 are independent and can run in parallel.

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

- [ ] Every one of the 79 modules has a verdict + one-line justification in a
      triage table committed to `tasks/`
- [x] `check_reachability.py` corrected, running in CI, ceiling set to the new
      measured value (30,658)
- [x] Runtime-trace tooling committed and documented
      (`scripts/runtime_trace.py`, `configs/config.trace.yaml`)
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
