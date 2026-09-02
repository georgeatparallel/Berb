# Pass 1 — Sandbox & subprocess boundary

Protocol: AUTONOMOUS DEFECT-HUNT PROTOCOL — V7 (PROACTIVE), per `tasks/defect_hunt_plan.md`.
Run date: 2026-09-02.
`budget_spent`: 3 of 12 candidates investigated to a verdict.
`hunt_iterations`: 1.

Phase 0 census is `tasks/defect_hunt_plan.md` §1 verbatim, reused unchanged.

═══════════════════════════════════════════
PHASE 1: DEFECT-SURFACE MAP
═══════════════════════════════════════════

**In scope:** `berb/experiment/sandbox.py`, `docker_sandbox.py`, `ssh_sandbox.py`,
`colab_sandbox.py`, `agentic_sandbox.py`, `factory.py`, `validator.py`.

| Region | Defect classes | Reachability | Blast radius | Invariant density |
|---|---|---|---|---|
| R1: `ExperimentSandbox.run`/`run_project` (sandbox.py) | Trust-boundary | REACHABLE — default `experiment.mode: sandbox` | SYSTEM (local subprocess) | High — `check_code_security` gate, `safe_subprocess_env`, entry-point checks |
| R2: `DockerSandbox.run`/`run_project` (docker_sandbox.py) | Trust-boundary | REACHABLE via `experiment.mode: docker` | SYSTEM (container) | High — same gate, plus image/network policy |
| R3: `SshRemoteSandbox.run`/`run_project` (ssh_sandbox.py) | Trust-boundary | REACHABLE via `experiment.mode: ssh_remote` — a documented, non-experimental mode (CLAUDE.md) | **EXTERNALLY-VISIBLE** — a real remote host with real SSH credentials | **Low before this pass** — only path-traversal checks, no code-content scan |
| R4: `ColabDriveSandbox.run`/`run_project` (colab_sandbox.py) | Trust-boundary | REACHABLE via `experiment.mode: colab_drive` | **EXTERNALLY-VISIBLE** — executes via an unattended worker notebook with **no isolation at all** (bare `subprocess.run`, no container, no `safe_subprocess_env`) | **Low before this pass** — same gap as R3, plus weaker runtime isolation |
| R5: `create_agentic_sandbox` / `AgenticSandbox` (agentic_sandbox.py, factory.py) | Trust-boundary | **DEAD** — zero callers of `create_agentic_sandbox` anywhere in `berb/` | N/A while dead | Unknown — not audited (see residual set) |
| R6: `validator.py` AST scanner (`check_code_security`'s implementation) | Trust-boundary, Contract | REACHABLE — shared by R1-R4 | SYSTEM | High — explicitly hardened against `__import__`/`getattr`/`importlib` bypass per S-2/S-3 (spot-checked, not re-derived) |

**Atomic assertions about the map:**
- A1: "`check_code_security` is documented as the single enforcement point every `run()`/`run_project()` must call before spawning a subprocess." → **[VF]** — direct quote from `sandbox.py`'s own docstring.
- A2: "All four sandbox backends actually call it." → **[FALSE]** — R3 and R4 did not, until this pass's fix (see D1).
- A3: "`create_agentic_sandbox` is reachable from any pipeline entry point." → **[FALSE]** — zero callers found by repo-wide grep; DEAD, not merely GUARDED.
- A4: "`validator.py`'s AST scanner is immune to every `__import__`/`getattr`-based bypass." → **[HYP]** — spot-checked (bypass patterns are named in the source), not independently re-derived or fuzzed this pass.

**Coverage note:** this pass covered R1-R4 for the Trust-boundary class to a CONFIRMED/CLEARED verdict. R5 was triaged as DEAD (not fixed — see routing below). R6 was spot-checked, not exhaustively hunted; it is the top item in the residual set.

═══════════════════════════════════════════
PHASE 2 + 3: CANDIDATES AND PROOF
═══════════════════════════════════════════

### D1 — SSH and Colab sandboxes execute code with no security scan

**Claim:** Under `experiment.mode: ssh_remote` or `colab_drive`, `SshRemoteSandbox.run`/
`run_project` and `ColabDriveSandbox.run`/`run_project` (ssh_sandbox.py:55-141,
colab_sandbox.py:141-206, pre-fix) staged and executed/uploaded arbitrary code
without ever calling `check_code_security` or `_scan_project_inputs`, violating
the invariant `sandbox.py` itself states in `check_code_security`'s docstring.

- **Defect class:** Trust-boundary.
- **Violated property:** "each run()/run_project() implementation calls
  check_code_security before spawning a subprocess" (sandbox.py docstring,
  verbatim).
- **Reachability:** REACHABLE from `berb run` via `experiment.mode: ssh_remote`
  / `colab_drive` — both documented, non-experimental modes.
- **Severity if real:** CRITICAL — remote code execution with real credentials
  (SSH) / execution with zero isolation (Colab worker notebook).
- **Prior:** HIGH — confirmed by direct code reading before any test was
  written; both call chains for `run()`/`run_project()` were read in full.
- **Innocence path checked:** searched every caller of `sandbox.run`/
  `run_project` in `berb/pipeline/` and `berb/experiment/runner.py` for an
  upstream `check_code_security` call — none exists; the pipeline calls the
  `SandboxProtocol` polymorphically and trusts each backend to gate itself.
  No guard, no unreachability. **NO-DEFENSE-FOUND.**

**Trigger test:** `tests/test_remote_sandbox_security_gate.py`. Before the fix,
6 of 12 tests **FIRED**: malicious code reached the mocked network-touching
step (`_execute`/`_submit_and_wait`) in both `run()` and `run_project()`,
including a malicious *non-entry-point* file inside a project. Confirmed by
`git stash` of the fix and re-running the suite (recorded in the session log).

**Verdict: CONFIRMED DEFECT.** Fixed — see Phase 5.

### D2 — `create_agentic_sandbox` / `AgenticSandbox` is dead code

**Claim:** `berb/experiment/factory.py::create_agentic_sandbox` and the
`AgenticSandbox` class it returns have no caller anywhere in `berb/`.

- **Defect class:** none (not a bug) — a reachability finding, recorded per
  the plan's instruction to deprioritize-not-discard DEAD regions.
- **Reachability:** DEAD. `grep -rn "create_agentic_sandbox"` returns only its
  own definition.
- **Innocence path:** N/A — dead code cannot violate a runtime property.
- **Trigger test:** none written — nothing to trigger.

**Verdict: FALSE (not a defect), but a genuine reachability gap** not yet
represented in `.reachability-allowlist`. Whether `agentic_sandbox.py` itself
also has the D1-shaped gap (no `check_code_security` call — confirmed absent
by grep) is real but LOW severity while unreachable, per the plan's
`hunt_priority ∝ reachability` rule. **Routed to the residual set (§ below),
not fixed this pass** — fixing an unreachable code path's security gate
without evidence anyone will wire it up would be scope creep on a security
pass, and `.reachability-allowlist` accounting is a W-series concern, not
this pass's.

### D3 — Import-obfuscation bypass coverage in `validator.py`

**Claim (candidate, not promoted):** the AST scanner might miss a
dynamically-constructed dangerous call it doesn't already name.

- **Defect class:** Trust-boundary.
- **Investigation:** grepped `validator.py` for the bypass patterns V7 would
  expect an attacker to try first — `__import__`, `getattr`-based dispatch,
  `importlib.*` — and found all three explicitly named and defended, with
  inline comments citing the specific bypass they close (e.g.
  `getattr(os, 'sys'+'tem')('id')`).
- **Trigger test:** none written this pass — no falsifiable single candidate
  was identified beyond what the source already documents defending against.
- **Verdict: UNKNOWN.** Routed to Pass 9 (runtime instrumentation / fuzzing)
  rather than closed as CLEARED — a grep confirming named defenses exist is
  much weaker evidence than an executed adversarial-input suite, and this
  pass's budget was better spent on D1's confirmed, unguarded gap.

═══════════════════════════════════════════
PHASE 4: INVENTORY
═══════════════════════════════════════════

| Candidate | Trigger | Innocence | Evidence Basis | Status |
|---|---|---|---|---|
| D1 | FIRED (6/12 sub-tests) | NO-DEFENSE-FOUND | VERIFIED | **VERIFIED DEFECT** |
| D2 | — | N/A (dead code) | VERIFIED (reachability) | FALSE (not a defect); reachability gap noted |
| D3 | not attempted | partial (named defenses exist) | HYP | UNKNOWN — routed to Pass 9 |

Inventory ranking for fixes: D1 only (CRITICAL × REACHABLE × EXTERNALLY-VISIBLE).

═══════════════════════════════════════════
PHASE 5: FIX DESIGN — D1
═══════════════════════════════════════════

**Files touched:** `berb/experiment/ssh_sandbox.py`, `berb/experiment/colab_sandbox.py`.

**Ssh_sandbox.py:**
```diff
+ from berb.experiment.sandbox import _scan_project_inputs, check_code_security
```
`run()`: added a `check_code_security(code, label="experiment code")` call at
the top, returning a rejecting `SandboxResult` (with `rejected_reason` set)
before any file is written, mirroring `ExperimentSandbox.run`'s own opening
lines.
`run_project()`: added a `_scan_project_inputs(project_dir)` call immediately
after the pre-copy `validate_entry_point` check and before the harness
injection / file-copy loop, mirroring `DockerSandbox.run_project`'s ordering
exactly (source-dir scan, before staging).

**Colab_sandbox.py:** the same two additions, at the equivalent points in
`run()` and `run_project()`.

This is 2 functions × 2 files = 4 call sites, each a ~10-15 line insertion
that calls an existing, already-tested function — no new security logic was
written, only wired to two call sites that were missing it. Constraint note:
the plan's "≤1 function modified per defect" cap is exceeded by construction
(D1 is one defect present at 4 call sites); each site is fixed identically by
delegating to the shared, already-verified `check_code_security`/
`_scan_project_inputs`, so **[CONSTRAINT-FORCED ESCALATION]** — the fix is
mechanical repetition of a pattern already proven correct at R1/R2, not new
risk surface, and splitting it into four separate "defects" would be a
policy artifact, not four independent bugs.

**Causal justification:** the verified mechanism is "R3/R4 skip the shared
AST scan that R1/R2 apply." The fix breaks it by calling that scan at the
same point in the control flow R1/R2 already call it, before any I/O that
would put attacker-controlled code on a remote host or in a synced folder.
No lower-side-effect fix exists: the alternative (validating once at the
`SandboxProtocol` call site in the pipeline) would still need per-backend
`import_policy`/`allowed_imports` plumbing that `SshRemoteConfig`/
`ColabDriveConfig` don't have, and would move the check away from the
point-of-use every other backend already uses, increasing the chance a
future fifth backend repeats this exact defect.

**Risk:** Scope MODULE (2 files) · Side effects: legitimate SSH/Colab runs
now pay one extra AST parse per file before upload — negligible, and strictly
smaller than the network I/O it precedes · Regression risk LOW (verified by
the no-regression tests below) · Reversibility TRIVIAL (revert the 4 call
sites).

═══════════════════════════════════════════
PHASE 6: SELF-REVIEW (RAR)
═══════════════════════════════════════════

- **Boundary** — empty code string / empty project dir: `check_code_security("")`
  and `_scan_project_inputs(<empty dir>)` both pass through cleanly (no `.py`
  files to scan is not a security violation) — same behavior as R1/R2, which
  share the exact function. **FIX HOLDS [VF]** (not independently re-tested
  here; inherited from the already-tested shared helper).
- **Invalid input** — a malicious file that is *not* the entry point:
  `test_run_project_scans_every_file_not_just_the_entry_point` — **FIX HOLDS [VF]**.
- **State** — a project directory that disappears between the scan and the
  copy loop (TOCTOU): not newly introduced by this fix — the same window
  exists in R1/R2 today via the identical helper, and is out of this
  candidate's scope. **CANNOT DETERMINE**, recorded as pre-existing residual
  risk shared with R1/R2, not created here.
- **Regression** — safe code / safe projects still execute:
  `test_run_allows_safe_code`, `test_run_project_allows_a_safe_project` (both
  backends) — **FIX HOLDS [VF]**. Entry-point path-traversal ordering
  preserved: `test_entry_point_validation_still_runs_before_the_security_scan`
  (both backends) — **FIX HOLDS [VF]**.
- **Concurrency** — `check_code_security`/`_scan_project_inputs` are pure,
  stateless functions; no shared mutable state crosses this change.
  **FIX HOLDS [VF]** (by inspection — no interleaving to test).
- **New-defect introduction** — re-ran the Phase 1 taxonomy against the
  4 changed call sites: no new resource leak (no handle opened), no new
  exception path (the added calls can only return `str | None`, never raise,
  per `check_code_security`'s own contract), no new config coupling
  (`SshRemoteConfig`/`ColabDriveConfig` untouched — the fix uses
  `check_code_security`'s own defaults, same as `docker_sandbox.py` does).
  **FIX HOLDS [VF]**.

No vector produced FIX BREAKS; `fix_revisions` = 0.

═══════════════════════════════════════════
PHASE 7: TESTS
═══════════════════════════════════════════

`tests/test_remote_sandbox_security_gate.py` — 12 tests:
- 6 proof-of-defect (3 per backend: bare malicious code, malicious entry-point
  file, malicious non-entry-point file in a multi-file project) — each
  confirmed to FIRE pre-fix via `git stash` and re-run.
- 4 no-regression (safe code / safe project pass through, per backend).
- 2 boundary/no-regression on ordering (entry-point validation still runs
  first and is distinguishable from a security rejection via
  `rejected_reason`).

Full-suite regression: `pytest -m "not slow and not e2e and not llm"` —
4,419 passed (4,407 baseline + 12 new), 21 skipped, 0 failed.

═══════════════════════════════════════════
PHASE 8: VERDICT + COVERAGE STATEMENT
═══════════════════════════════════════════

**Process checks (D1):**
- [x] Defect is VERIFIED (trigger fired + no defense found)
- [x] Fix ≤15 lines per call site (4 sites; constraint-forced escalation noted
      above for the "≤1 function" cap, not the line cap)
- [x] Proof-of-defect + boundary + no-regression tests included (12 ≥ 3)
- [x] Phase 0 census & scope complete (inherited from the plan)

**Engineering checks (D1):**
- [x] All self-review vectors → FIX HOLDS or CANNOT DETERMINE (one CANNOT
      DETERMINE, pre-existing and out of scope)
- [x] Regression risk LOW
- [x] Fix is causal (calls the actual missing gate), not symptomatic
- [x] No fix-interaction left unresolved (single defect, four identical sites)

**Repo-specific gates:**
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy berb/ --python-version 3.11` — 411 files, no issues
- [x] `pytest -m "not slow and not e2e and not llm"` — 4,419 passed, 0 failed
- [x] `check_reachability.py --max-unreachable-loc 686` passes, **unchanged**
      (no ceiling raised)
- [x] `bandit -r berb/experiment/ssh_sandbox.py berb/experiment/colab_sandbox.py -ll`
      — 0 Medium/High

**Coverage & residual-risk statement:**
- Surface audited: R1-R4 (all four sandbox backends' `run`/`run_project`) for
  Trust-boundary class. R5 (`agentic_sandbox.py`) triaged for reachability
  only. R6 (`validator.py`) spot-checked, not hunted.
- Surface NOT audited: `validator.py`'s AST scanner internals (D3, routed to
  Pass 9); `agentic_sandbox.py`'s own `run`/`run_project` bodies (DEAD, so
  deprioritized, not audited for content); Resource-lifecycle and
  Error-paths classes across R1-R6 (out of this pass's candidate budget);
  every subprocess/`os.exec*` call site *outside* the sandbox family
  (`acp_client.py`, `opencode_bridge.py`, `templates/compiler.py`, etc.) —
  enumerated in the initial grep but not triaged; several of those execute
  LLM-agent output too and are a plausible Pass 8 (cross-boundary) candidate.
- Defect classes covered: Trust-boundary (thoroughly, R1-R4). Not covered
  this pass: Resource lifecycle, Error paths, Concurrency, Seam mismatch —
  all in scope for Pass 1 per the plan but not reached within budget.
- Confirmed defects: **CRITICAL 1** (D1, fixed). HIGH 0. MEDIUM 0. LOW 0.
- Cleared (innocent): 0 — no candidate survived to an innocence attempt and
  was cleared; D1 is the only candidate that reached Phase 3.
- Residual UNKNOWN set: D3 (import-obfuscation bypass coverage); the D1-shaped
  gap's presence-or-absence in dead `agentic_sandbox.py`; the TOCTOU window
  between project scan and file copy shared by all four backends now.
- **Clean-claim scope:** "R1-R4 (`sandbox.py`, `docker_sandbox.py`,
  `ssh_sandbox.py`, `colab_sandbox.py`) were audited for the Trust-boundary
  class — specifically, whether `run()`/`run_project()` invoke the documented
  security scan before any subprocess spawn, SSH upload, or Drive write — and
  after this pass's fix, no VERIFIED defect remains in that specific
  property." This is **not** a claim that these modules are free of defects
  in any other class, nor that `validator.py`'s scanner itself is unbeatable.
- **Highest-value next hunt:** Pass 2 (LLM client seam) per the plan's
  ordering, OR — if security stays the priority — extend Pass 1 to the
  non-sandbox subprocess sites (`acp_client.py`, `opencode_bridge.py`) that
  execute LLM-agent output under a similar trust boundary, which this pass's
  initial grep surfaced but did not triage.

**Final routing: ACCEPT.** D1's fix is committed with its tests; D2 is a
reachability note for the allowlist/W-series process, not this pass's to
resolve; D3 is explicitly UNKNOWN and carried to Pass 9.

═══════════════════════════════════════════
UNCERTAINTY ACKNOWLEDGMENT
═══════════════════════════════════════════

- **Finding most likely to be a false positive:** none of D1's sub-findings —
  each was executed (fired pre-fix, passed post-fix) rather than reasoned.
  If anything is overstated, it is the severity label on the Colab path
  ("weakest isolation of any backend") — asserted from reading
  `COLAB_WORKER_TEMPLATE`'s bare `subprocess.run`, not from operating an
  actual Colab worker.
- **Real defect most likely missed:** the Resource-lifecycle and
  Error-paths classes across all six regions were not hunted at all this
  pass — budget went entirely to Trust-boundary. A leaked SSH connection,
  an un-cleaned remote staging directory on timeout, or a Docker container
  left running after a crash are all plausible and unexamined.
- **What requires runtime validation:** D3 (import-obfuscation bypass) needs
  an adversarial-input fuzzing pass (Pass 9), not more reading of
  `validator.py`. The TOCTOU window noted in Phase 6 also needs a real
  concurrent-filesystem test, not static reasoning.
- **What static analysis cannot determine:** whether the Colab worker
  notebook template (`COLAB_WORKER_TEMPLATE`, a string embedded in
  `colab_sandbox.py` that a human copies into an actual Colab cell) is
  followed as-written in practice — this fix protects what Berb *writes* to
  the synced folder, not what the worker notebook a user is actually running
  does once code lands there. Out of this codebase's static reach by
  construction.
- **What additional input would most increase confidence:** a real (or
  faithfully mocked) SSH/Docker/Colab integration environment, so D1's
  boundary tests could assert against actual `scp`/`ssh` invocations rather
  than a mocked `_execute`/`_submit_and_wait`; and a decision on whether
  `agentic_sandbox.py` (D2) should be wired, allowlisted as PARK, or deleted
  — its current state (present, unreachable, unaudited for D1's own gap) is
  the most likely place for this exact defect class to resurface unnoticed.
