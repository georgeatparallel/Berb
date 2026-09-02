# Sequential defect-hunt plan — running V7 over the Berb codebase

**Status:** plan only. No hunt has been run against this plan yet.
**Protocol:** AUTONOMOUS DEFECT-HUNT PROTOCOL — V7 (PROACTIVE).
**Written:** 2026-09-02.

The V7 protocol bounds a single hunt. Berb is 411 modules / ~144k LOC, which is
far past what one hunt can triage honestly. This document turns the protocol
into a **sequence of bounded hunts**: it fixes the Phase 0 census once, splits
the codebase into ordered passes each of which is a legal V7 in-scope surface,
and defines how findings and coverage accumulate across passes.

---

## 0. Why sequential, and what the sequence buys

A single V7 over 144k LOC would exhaust its audit budget inside the first
subsystem and emit a coverage statement that is technically honest and
practically useless ("we audited 6% of the surface"). Splitting the hunt gives
three things a single pass cannot:

1. **A per-pass clean-claim that is actually scoped to something meaningful** —
   "`berb/llm/` was audited for trust-boundary and resource-lifecycle defects"
   is a claim a reviewer can act on.
2. **Ordering by expected yield.** Passes are ordered by MRADO priority, so a
   run that stops early stops having covered the highest-risk surface, not an
   alphabetical prefix.
3. **A carry-forward residual set.** Each pass's UNKNOWN candidates feed the
   runtime-instrumentation pass rather than being written off.

The cost is real and should be stated: cross-pass defects (a contract violation
between `berb/llm/` and `berb/pipeline/`) are systematically harder to find when
the two live in different passes. Pass 8 exists specifically to hunt those, and
is the pass most likely to be cut for budget.

---

## 1. Phase 0 census — fixed once, reused by every pass

Every pass inherits this block verbatim. Re-deriving it per pass wastes budget
and risks drift.

```
Language:       Python
Runtime:        Python 3.11 (CI matrix: 3.11, 3.12)
Framework(s):   stdlib-first; FastAPI/Starlette + uvicorn (berb/server/),
                httpx (Anthropic adapter), urllib (core LLM client),
                pytest 9.x, ruff 0.15.22 (exact pin), mypy 2.3.1
Test framework: pytest, with markers: slow, e2e, llm, asyncio
Entry point(s): berb/cli.py (`berb run`, `berb serve`, `berb doctor`,
                `berb setup`), berb/server/ (HTTP + WebSocket),
                berb/mcp/ (MCP server)
Invariants:     Partially documented. Authoritative sources:
                  - berb/pipeline/contracts.py — per-stage input/output files,
                    depends_on, and DoD. This is the strongest invariant
                    source in the repo and should anchor Phase 2 candidates.
                  - .reachability-allowlist — what is intentionally dead.
                  - CLAUDE.md — the wired/unwired table.
                Anything not in those three is [HYP], and must be tagged so.
Build/lockfile: pyproject.toml; no lockfile (uv/pip resolve at install time)
```

**Threat model.** Berb spends real money on LLM calls and executes
model-generated code. Ranked by what actually costs the user:

| Rank | Class | Why it matters here |
|---|---|---|
| 1 | **Sandbox escape / credential exfiltration** | Stage 12 runs LLM-written code. `safe_subprocess_env`, `check_code_security` and the Docker/SSH sandboxes are the whole defence. |
| 2 | **Silent wrong result** | A pipeline that emits a confident paper from a broken experiment is worse than one that crashes. Metric parsing, the figure gate, and the claim/evidence manifests. |
| 3 | **Unbounded spend** | Budget governors, retry loops, cascade escalation, the search runner's node budget. A loop that retries forever bills forever. |
| 4 | **Resource lifecycle** | httpx pools, sqlite connections, sandbox temp dirs, subprocess handles across a 23-stage async run. |
| 5 | **Concurrency** | DAG levels run stages via `asyncio.gather`; stages themselves run in worker threads. Shared mutable state crossing that boundary. |
| 6 | **Config-shaped dead ends** | A section that parses into a dataclass nothing reads. `UNWIRED_CONFIG_SECTIONS` documents the known ones; the hunt should look for undocumented ones. |
| 7 | Parse robustness | External JSON: arXiv/OpenAlex/S2 responses, LLM JSON output, artifact files. |

**Defect taxonomy, pruned for this system.** From the V7 default catalogue,
keep all eight classes but re-rank: Trust-boundary, Error/exception paths,
Contract/dependency and Resource lifecycle rank above Boundary/arithmetic here,
because this codebase is I/O- and orchestration-shaped rather than numeric.
Add one system-specific class:

> **Class 9 — Seam mismatch.** A caller and callee that agree in name but not
> in interface: a wrapper missing a method its callers use, an `await` on a
> synchronous function, a config field nothing reads, a mocked method the real
> object does not have. This class is *not* in the V7 catalogue and is the
> highest-yield class in this repository — see §5.

---

## 2. Global budget and stopping rules

| Counter | Scope | Cap |
|---|---|---|
| `budget_spent` | per pass | 12 candidates investigated to a verdict |
| `hunt_iterations` | per region tier, per pass | 3 |
| `fix_revisions` | per fix | 1 |
| `passes_completed` | whole sequence | 9 |

A pass ends when its budget is spent **or** its surface map is fully triaged.
The sequence ends when all nine passes are done or the operator stops it. A
partial sequence is a valid result; §6 defines what may then be claimed.

**Per-pass exit artifact.** Every pass writes
`tasks/defect_hunt/pass-NN-<name>.md` containing: the Phase 1 surface map, the
Phase 4 inventory table, the Phase 8 coverage statement, and its carry-forward
UNKNOWN set. A pass without that file did not happen.

---

## 3. The pass sequence

Ordered by `likelihood × blast_radius × reachability`. Each row is one complete
V7 run.

### Pass 1 — Sandbox & subprocess boundary
- **In scope:** `berb/experiment/sandbox.py`, `docker_sandbox.py`,
  `ssh_sandbox.py`, `colab_*`, `factory.py`, `validator.py`,
  `berb/security/` (if present), and every `subprocess`/`os.exec*` call site.
- **Classes:** Trust-boundary, Resource lifecycle, Error paths, Seam mismatch.
- **Why first:** rank-1 threat, smallest surface, highest blast radius
  (EXTERNALLY-VISIBLE — it is the only thing between model output and the host).
- **Known anchor:** `safe_subprocess_env` is allow-list shaped. Verify that
  *every* spawn site uses it — the hunt should enumerate spawn sites and check
  each, not trust the helper's existence.

### Pass 2 — The LLM client seam
- **In scope:** `berb/llm/client.py`, `smart_client.py`, `model_cascade.py`,
  `anthropic_adapter.py`, `openrouter_adapter.py`, `acp_client.py`,
  `nadirclaw_router.py`, `vision.py`, `__init__.py` (the factory).
- **Classes:** Seam mismatch (primary), Contract/dependency, Error paths,
  Unbounded spend.
- **Why second:** every stage depends on it; a defect here is SYSTEM blast
  radius. This pass has already yielded confirmed defects (§5) — treat that as
  evidence the region is under-covered, not as evidence it is now clean.
- **Specific candidates to open with:**
  - Does `RCConfig` actually carry `nadirclaw` / `token_tracking`? (§5, D-3.)
  - Does every client the factory can return expose `.chat` and `.config`?
  - Does `_call_with_retry`'s backoff have a total-time bound, or only an
    attempt bound?

### Pass 3 — Pipeline orchestration
- **In scope:** `berb/pipeline/runner.py`, `executor.py`, `iterative.py`,
  `discovery.py`, `resolution.py`, `contracts.py`, `checkpoints`, `events`.
- **Classes:** Concurrency, State machine, Error paths, Resource lifecycle.
- **Why here:** `contracts.py` gives this pass real named invariants, which is
  what makes Phase 2 candidates falsifiable rather than vibes.
- **Anchor invariants:** every stage's declared `output_files` exist on DONE;
  `depends_on` is acyclic and respected by `_build_dag_levels`; a PIVOT
  recursion terminates at `MAX_DECISION_PIVOTS`.

### Pass 4 — Stage implementations (7-15: the experiment half)
- **In scope:** `berb/pipeline/stage_impls/_synthesis.py`, `_design.py`,
  `_code_generation.py`, `_execution.py`, `_analysis.py`.
- **Classes:** Parse robustness, Silent wrong result, Type/serialization.
- **Anchor:** each stage's contract in `contracts.py`. A stage returning DONE
  without its declared artifacts is a CONFIRMED defect with a named violated
  property — the cleanest candidate shape available in this repo.

### Pass 5 — Stage implementations (16-23: the writing half)
- **In scope:** `_paper_writing.py`, `_finalization.py`, `berb/review/`,
  `berb/integrity/`.
- **Classes:** Silent wrong result, Contract, Trust-boundary (citation
  fabrication is the trust boundary here).
- **Anchor:** the claim manifest / evidence registry invariants in
  `berb/integrity/`. A claim admitted without an evidence anchor is the
  highest-severity defect this pass can find.

### Pass 6 — Literature ingestion
- **In scope:** `berb/literature/` (arXiv, OpenAlex, Semantic Scholar, PDF
  ingestion, Zotero, novelty).
- **Classes:** Parse robustness, Trust-boundary (remote input), Resource
  lifecycle (HTTP clients), Error paths.
- **Note:** this package is a declared public API
  (`PUBLIC_API_PACKAGES`), so a signature-shaped defect here is a contract
  break for external callers, not only an internal bug. Severity ranks up.

### Pass 7 — Config and persistence
- **In scope:** `berb/config.py`, `berb/utils/token_tracker.py`,
  checkpoint/event storage, artifact readers/writers.
- **Classes:** Config-shaped dead ends, Concurrency (sqlite), Type/serialization.
- **Specific candidate:** enumerate every `*Config` dataclass field and grep
  for a reader. Anything with zero readers is a config-shaped dead end;
  compare against `UNWIRED_CONFIG_SECTIONS` and report the delta. This is
  mechanisable and should be near-total coverage rather than sampled.

### Pass 8 — Cross-boundary contracts *(the pass most likely to be cut)*
- **In scope:** the interfaces *between* passes 1-7, not their interiors.
  Specifically: what the pipeline assumes about the client, what stages assume
  about each other's artifacts, what `berb/agents/` assumes about `berb/llm/`.
- **Classes:** Seam mismatch, Contract/dependency.
- **Method:** for each cross-package call site, name the assumed contract and
  check it against the callee's actual signature and documented behaviour.
- **Honest note:** this is the pass a per-package split makes *harder*, and it
  is where the already-confirmed defects in §5 actually live. If budget forces
  a cut, cut Pass 6 before Pass 8.

### Pass 9 — Runtime instrumentation
- **In scope:** the accumulated UNKNOWN set from passes 1-8.
- **Method:** not static. Use `scripts/runtime_trace.py` and a
  `configs/config.trace.yaml` run to decide candidates that static analysis
  left INDETERMINATE — reachability of guarded branches, actual concurrency
  interleavings, resource-handle counts across a full run.
- **Constraint:** this pass needs a run that makes real LLM calls, so it costs
  money and cannot run in CI. Budget it explicitly or declare it not run.

---

## 4. Per-pass execution checklist

Run the phases in order. The gates are not optional.

1. **Phase 0** — paste the fixed census (§1); write only the pass-specific
   scope, budget and threat-model ranking. `[BLOCKED]` if the in-scope source
   is not actually readable.
2. **Phase 1** — enumerate regions, tag reachability against
   `scripts/check_reachability.py` output (do not guess: the tool is
   authoritative and has itself been wrong before — see W0), score, order.
   State ≥3 classified assertions about the map.
3. **Phase 2** — generate candidates. Every candidate names a violated
   property and a location, and carries an innocence path.
4. **Phase 3** — for each candidate, write the trigger test **and** attempt the
   innocence defence. A candidate with no executable trigger stays UNKNOWN and
   goes to Pass 9; it is never promoted on reasoning.
5. **Phase 4** — inventory table. Route.
6. **Phase 5** — fix, ≤15 lines / ≤1 function, causal not symptomatic. Run the
   fix-interaction check: proactive hunts cluster findings in one region, and
   two fixes touching the same lines must be sequenced deliberately.
7. **Phase 6** — six-vector self-review, including the new-defect vector.
   Anything reasoning-only stays `[HYP]` until Phase 7 promotes it.
8. **Phase 7** — proof-of-defect + ≥2 boundary + ≥1 no-regression test, in
   `tests/`, using the repo's markers.
9. **Phase 8** — process checks, engineering checks, coverage statement.

**Repo-specific gates to add to Phase 8**, on top of V7's own:

- [ ] `ruff check berb/ tests/` and `ruff format --check berb/ tests/` clean
- [ ] `mypy berb/ --python-version 3.11` clean
- [ ] `pytest -m "not slow and not e2e and not llm"` green
- [ ] `python scripts/check_reachability.py --allowlist .reachability-allowlist
      --max-unreachable-loc <current>` passes **without raising the ceiling**
- [ ] `bandit -r berb/ -ll -c pyproject.toml` no new Medium/High

---

## 5. Prior evidence: what a partial hunt already found

These are `[VF]` — confirmed by execution during the 2026-09-02 wiring work,
before this plan existed. They are recorded here because they calibrate the
expected yield and validate the Class 9 addition.

| # | Defect | Class | Evidence |
|---|---|---|---|
| D-1 | `SmartLLMClient` had no `chat()`, but 36 call sites do `llm.chat(...)` | Seam mismatch | `hasattr(SmartLLMClient, "chat") is False` |
| D-2 | `SmartLLMClient.complete()` awaited `_base_client.complete()`; no base client has one | Seam mismatch | `hasattr(LLMClient, "complete") is False` |
| D-3 | `create_llm_client` gates on `config.nadirclaw` / `config.token_tracking`, neither of which is an `RCConfig` field — so the wrapper is unreachable from config *(still open, see §7)* | Config dead end | `RCConfig.__dataclass_fields__` |
| D-4 | `create_llm_client` passed only `base_client.config` to the wrapper, silently discarding a `MultiProviderLLMClient` or `ACPClient` | Seam mismatch | code read + test |
| D-5 | `anthropic_adapter.py` guarded `import httpx` but annotated `-> httpx.Client` without deferred annotations, so the module could not import at all without httpx | Contract | `NameError` on import |
| D-6 | `TokenTracker`'s sqlite connection was thread-affine while stages run in worker threads | Concurrency | `sqlite3.ProgrammingError` in test |

**What this says about yield.** Six confirmed defects surfaced from *incidental*
reading of one package while doing unrelated work — no hunt, no budget, no
protocol. Four of the six are Class 9. That is the strongest available argument
for ranking Seam mismatch first in Pass 2 and for keeping Pass 8.

**What it does not say.** These were found because that code was being modified
anyway. It is not evidence that `berb/llm/` is worse than other packages — it
is evidence that *looked-at* code yields defects, which is [UNK] about the rest.

---

## 6. What may be claimed, and what may not

Per pass, the clean-claim is exactly:

> Regions `[R...]` of `<package>` were audited for classes `[...]` under a
> budget of 12 candidates. No VERIFIED defect survived the innocence attempt in
> those regions for those classes.

Never: "`<package>` is bug-free", "the codebase is clean", or any percentage.
Absence of found defects is `[UNK]` about the unaudited remainder — including
unaudited *classes* within an audited region.

The sequence-level statement aggregates the per-pass ones and names, explicitly:
passes not run, classes not hunted, and the size of the carried UNKNOWN set.

---

## 7. Open items this plan inherits

Carried in as pre-seeded Phase 2 candidates, not as findings:

1. **D-3 above is still open.** `RCConfig` has no `nadirclaw` or
   `token_tracking` field, while `configs/config.arc.example.yaml` documents
   both with `enabled: true` and advertises "40-70% savings". Either the config
   fields should exist or the example and the factory guards should go. Turning
   the subsystem on is a product decision, so it was left for Pass 2 / Pass 7
   rather than changed silently.
2. **`react_agent.py` (389 loc) and `split_policy.py` (297 loc)** are the whole
   remaining non-allowlisted dead surface. `split_policy` needs a
   `SplitEvidence` producer; `react_agent` waits on candidate-generator work.
   Both are DEAD-reachability regions: low hunt priority, not zero.
3. **`_candidate_generator` in `_execution.py` is a stub** returning one static
   copy of `main.py`, and `SearchRunner._expand_one` takes `candidates[0]`.
   The tree search therefore explores one byte-identical candidate. Not a
   crash, so it is a Pass 4 "silent wrong result" candidate rather than an
   obvious bug — and it is the highest-value single item in this document.
4. **`experiment/self_correcting.py`, `compute_guard`, `evolutionary_search`,
   `harness_template`, `evaluators/`, `memory/shared_memory`** and the other
   PARK entries are out of scope for every pass. They are unreachable, so a
   defect in them is LOW severity by the reachability multiplier. Do not spend
   budget there while reachable surface is untriaged.

---

## 8. Sequencing summary

```
Pass 1  Sandbox & subprocess boundary        ← start here
Pass 2  LLM client seam                      ← highest known yield
Pass 3  Pipeline orchestration
Pass 4  Stage impls 7-15                     ← highest-value single item (§7.3)
Pass 5  Stage impls 16-23 + integrity
Pass 6  Literature ingestion                 ← cut this before Pass 8
Pass 7  Config & persistence                 ← mechanisable, near-total coverage
Pass 8  Cross-boundary contracts             ← where §5's defects actually live
Pass 9  Runtime instrumentation              ← costs money; budget or declare unrun
```
