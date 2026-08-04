# Berb — Open Decisions

**Date:** 2026-08-02
**Branch:** `fix/lazy-imports-atomic-replace` (PR #9, green, mergeable)
**Scope:** the four open threads — dead code, audit Phases 1–5, unread config, PR #9

Everything below was re-verified against the current tree today. Where it contradicts
[PRODUCTION_READINESS_AUDIT.md](PRODUCTION_READINESS_AUDIT.md) or
[DEAD_CODE_ANALYSIS.md](DEAD_CODE_ANALYSIS.md), those documents are stale and this one wins.

---

## Recommendation in one line

**Merge PR #9 now. Then do §4 (config) — it is four hours and removes a whole class of lie from the
codebase. Then §2 items 1–3 (real gates). Leave the dead code until last**, because the gate that is
supposed to protect against it is currently configured to pass.

---

## 1. PR #9 — merge it

| | |
|---|---|
| State | `OPEN`, `MERGEABLE`, 7 commits, all 4 CI checks green |
| Unpushed | 1 commit on the local branch (`39ce359`, flaky-test fixes) — push before merging |

Two deliberate backward-incompatible edges. Both are correct, and both need a line in the release
notes rather than softening:

1. **A non-loopback `server.host` with an empty `auth_token` now refuses to start.** The escape hatch
   is `server.insecure: true`. Anyone currently relying on the old behaviour was running an
   unauthenticated pipeline-control API on all interfaces — breaking them is the point.
2. **Six legacy server entry points are gone.** `python -m berb.api.server` and siblings. Blast radius
   is bounded: nothing inside the repo imported them except their own package `__init__`, and the
   docs that pointed at them were updated in the same commit. External blast radius is unknowable
   from here — if this package has downstream consumers, that is the one thing to check before merge.

**Do:** push `39ce359`, merge. Do not split the PR — the security fixes are not independently useful
(the config fix without the middleware fix still leaves `/ws/events` open).

---

## 2. Audit Phases 1–5 — status re-verified

I re-checked every item. **Nothing from Phases 1–5 has been done.** One item I reported as fixed
earlier today is *not* fixed — see the correction below.

| Item | Audit § | Verified state |
|---|---|---|
| mypy scope inverted | 4.3 | **Open.** `ignore_errors = true` for `berb.*`, `false` for 8 named modules. Still reports on ~2% of the package. |
| Lockfile | 4.5 | **Open.** No `uv.lock`, `poetry.lock`, or `requirements.txt`. |
| Dependabot / CodeQL / bandit / pip-audit | 3.5 | **Open.** `.github/workflows/` contains only `ci.yml`. |
| `eval`/`exec` → sandbox | 3.4 | **Open.** `berb/math/verification.py:463` `eval(expr, {"__builtins__": {}}, namespace)`, `:500` `exec(instrumented_code, exec_globals)`. |
| Rate limiting | 3.5, 6 | **Open.** Zero hits for slowapi/limiter/rate_limit under `berb/server/` or `berb/api/`. |
| Application Dockerfile | 6 | **Open.** None at repo root. |
| CHANGELOG / SECURITY / CODE_OF_CONDUCT | 6 | **Open.** Only `CONTRIBUTING.md` exists. |
| Coverage floor | 4.4 | Still `--cov-fail-under=55` in `ci.yml`. |

> **Correction.** Earlier today I said no `eval`/`exec` remained anywhere in `berb/`. That was wrong.
> The shell mangled my regex into an unclosed group, the search returned zero matches, and I read
> that as a clean result instead of a failed command. Both calls are still there. `{"__builtins__": {}}`
> is not a sandbox — it is bypassable by attribute traversal on any object in `namespace`, and numpy
> is injected into that namespace.

### Suggested order

**First — the two that are cheap and stop future bleeding:**

1. **Pin the toolchain / add a lockfile.** PR #9 already had to pin `ruff` because an unpinned range
   let CI break with zero code change. That is the same failure mode as every other unpinned dep
   here. Adopt `uv`, commit `uv.lock`, install from it in CI. ~half a day.
2. **Add `pip-audit` + `bandit` + Dependabot to CI.** Three workflow steps and one config file.
   ~2 hours. CodeQL is a fourth if you want it.

**Second — the one real vulnerability:**

3. **Route `verification.py` through the existing sandbox.** `berb/experiment/docker_sandbox.py`
   already exists and is what every *other* generated-code path uses; this one just never got wired
   to it. Alternative if you want it cheaper: replace `_safe_eval` with an `ast.parse` + node-allowlist
   evaluator, which is ~80 lines and has no Docker dependency. Note this path is currently reachable
   only via non-CLI entry prefixes (`berb.benchmarks`), so the practical exposure is lower than the
   audit implied — but it is still `exec()` on model-generated code.

**Third — the gate that is lying:**

4. **Invert the mypy policy.** Swap the allowlist for a shrinking denylist. Expect a large initial
   error count; ratchet it down per sprint. This is the single most misleading signal in the repo —
   "Success: no issues found in 422 source files" currently means mypy *parsed* 422 and *reported on* 8.

**Defer:** Dockerfile, rate limiting, CHANGELOG/SECURITY, release workflow. All real, none urgent
until there is a deployment story.

---

## 3. Dead code — 32%, and the gate is configured to pass

```
modules 417 | reachable 261 | UNREACHED 156
loc 147516  | UNREACHABLE 46885 (32%)
[OK] Reachability check passed.
```

That `[OK]` is the problem. The check passes because `.reachability-allowlist` parks eight entries:

```
berb.domains.physics    # Deprecated — scheduled for removal
berb.domains.chaos      # Deprecated — scheduled for removal
berb.hyperagent         # Parked — revisit Q1 2027
berb.i18n               # Parked — revisit Q1 2027
berb.experimental       # Parked — revisit Q1 2027
berb.integrity.eval.finding_reproduction
berb.hardware
berb.writing_guide
```

Two of those say **"scheduled for removal"** and have said so since 2026-07-19. They are still here.

### The honest first move

Before touching any package: **delete the two entries that are already marked for deletion**
(`berb.domains.physics`, `berb.domains.chaos` — 4,838 LOC plus ~1,285 lines of tests). They emit
`DeprecationWarning` on import, nothing calls them, and the allowlist itself says to remove them.
That is a decision that was already made and never executed. ~2 hours.

### Then, by class

| Class | LOC | Action |
|---|---|---|
| **Already-decided deletes** | ~4,838 | `domains.physics`, `domains.chaos`. Just do it. |
| **Zero-importer subsystems** | ~1,900 | `berb.skills`, `berb.hooks`, `berb.plugins`, `knowledge.graph` — literally no importer anywhere. Wire at a real call site or delete; shipping an inert extension point is worse than shipping neither. |
| **Superseded duplicates** | ~7,500 | The `berb/llm` alternative stack (`model_router` vs `model_cascade` vs `extended_router`; two code agents; two memory systems). Pick one of each. `prompt_cache` + `batch_api` + `structured_outputs` are genuinely additive — wire those. |
| **Ready seam** | ~2,500 | `pipeline/tracing.py`, `utils/time.py`, `quality.py`, `assessor/`, `audit/reproducibility.py`, `metrics/`. Each closes an audit finding with code that already exists and is already tested. Best value per hour in the whole list. |
| **Documented but unwired** | ~9,000 | SearXNG, grey literature, multimodal extraction, self-correcting sim, auto-debugger. **Fix the docs today** (one hour) whether or not you wire the code — CLAUDE.md currently describes capabilities that do not run. |

**Do not** start here. The reachability gate has to be made honest first (shrink `ENTRY_PREFIX` to what
`berb run` and `berb serve` actually reach), or you will be measuring progress against the wrong
denominator.

---

## 4. Unread config — the highest-value four hours available

Eight config sections are defined, documented, defaulted, and **read by nothing**:

| Section | Consumers |
|---|---|
| `config.memory` | 0 |
| `config.skills` | 0 |
| `config.knowledge_graph` | 0 |
| `config.quality_assessor` | 0 |
| `config.calendar` | 0 |
| `config.copilot` | 0 |
| `config.mcp` | 0 |
| `config.compute_servers` | 0 |

(For contrast, `config.dashboard`, `config.overleaf`, and `config.trends` have 3 consumers each, and
`config.multi_project` has 1 — the pattern works when someone finishes it.)

This is worse than dead code. Dead code is inert. **A config option that does nothing is a false
promise**: a user sets `memory.enabled: true`, the pipeline reports success, and nothing was ever
stored. `MemoryConfig` even ships `inject_at_stages = (1, 9, 10, 17)` — a fully-specified integration
contract naming the exact stages, that no code reads.

### Recommendation — do this first, it is the cheapest credibility win

**Step 1 (2 hours, do it regardless):** make every unread section fail loudly. Either delete the
dataclass, or have `validate_config()` emit a warning when a user sets a non-default value on a
section nothing consumes. A config that silently ignores you is a bug report waiting to happen.

**Step 2 (judgement call, per section):**

- **`memory` — wire it.** `berb/memory/` is 1,867 LOC of working, tested implementation
  (`MemoryStore`, `MemoryRetriever`, embeddings, time-decay). `berb/adapters.py` declares a
  `MemoryAdapter` Protocol whose production implementation is a `Recording*` stub that appends to a
  list and discards it. One is an implementation with no consumer; the other is a consumer with no
  implementation. Connecting them is a constructor change, and it is the difference between a
  pipeline that runs and one that improves. **~1 week, highest product value in this document.**
- **`skills` — decide.** `SkillsConfig.enabled = True` by default, `max_skills_per_stage = 3`,
  documented in CLAUDE.md, and zero importers. Wire at prompt-build time or delete the package.
- **`quality_assessor`, `knowledge_graph`, `calendar`, `copilot`, `mcp`, `compute_servers` — delete
  the config sections** unless there is a concrete plan. Re-adding a dataclass later is trivial;
  leaving a live-looking switch that does nothing is not.

---

## 5. What I would actually do, in order

| # | Work | Effort | Why first |
|---|---|---|---|
| 1 | Push `39ce359`, merge PR #9 | minutes | Unblocks everything; already green |
| 2 | Fix CLAUDE.md / README capability claims | 1 hr | Free honesty; docs currently describe code that does not run |
| 3 | Make unread config fail loudly (§4 step 1) | 2 hrs | Removes a class of silent lie |
| 4 | Delete `domains.physics` + `domains.chaos` | 2 hrs | Decision already made, never executed |
| 5 | Lockfile + `pip-audit`/`bandit`/Dependabot | 1 day | Stops CI breaking with no code change |
| 6 | Shrink `ENTRY_PREFIX`, make the gate honest | ½ day | Gates the whole dead-code effort |
| 7 | Sandbox `verification.py` eval/exec | 1–2 days | The one real vulnerability left |
| 8 | Wire memory (§4) | 1 week | Highest product value |
| 9 | Invert mypy policy | ongoing | Biggest lying signal, but a long ratchet |

Items 1–4 are **one working day total** and each removes something actively misleading. That is where
I would start.
