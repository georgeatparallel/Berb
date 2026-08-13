# Berb Architecture Hardening Plan — 4/10 → 8.5+

**Created:** 2026-08-11 · **Baseline:** [`tasks/arch_audit_2026-08-10.md`](arch_audit_2026-08-10.md)
**Goal:** architecture score >8.5 on the v2 audit rubric, with safety/security as the primary axis.

## Wave 0 status — done except one item found not to apply

- **S0-1** done — `check_code_security()` enforced in `ExperimentSandbox.run/run_project` and `DockerSandbox.run/run_project`, before any subprocess spawns.
- **S0-2** done — `"security"` added to the blocking category tuple in `_code_generation.py`.
- **S0-3** done — alias resolution (`import os as _o`, `from os import system`), attribute-chain escape detection (`__class__`/`__bases__`/etc.), `pickle.load(s)` banned, `open()`-with-escaping-literal-path banned, plus `os.rename/replace/chmod/fork/spawn*` added to `DANGEROUS_CALLS`.
- **S0-4** done — `fallback_to_sandbox` default flipped to `False`; Docker network-policy cutoff failure in `entrypoint.sh` now `exit 1` instead of continuing with network up.
- **S0-5** done — `wrap_untrusted()` added to `berb/utils/sanitize.py` (not `_prompt_helpers.py` as originally sketched — kept it out of `berb.pipeline` so `berb.literature` doesn't have to import the pipeline layer) and applied at all 6 cited sites.
- **S0-6** done for `full_text.py` (SSRF check at `extract()` entry + per-redirect-hop re-validation, `follow_redirects` flipped off). **Zotero sites were a false positive** — both calls go through an `httpx.AsyncClient(base_url="https://api.zotero.org")` with a relative path built from config values; there's no attacker-reachable host to redirect to. No change made there.
- **S0-7** done — added `_safe_paper_id()` (wraps the existing `sanitize_figure_id`) and applied at all 9 real path-construction sites in `fs_processor.py`, plus the `topic`-as-filename site. The `keyword`-as-dirname site the audit flagged turned out to be a hardcoded 5-item constant list, not external data — left alone.
- **S0-8** done — `code_agent.py`'s CLI-agent subprocess now uses `_safe_subprocess_env()` instead of `{**os.environ}`. **Caveat:** if you use `provider="claude_code"`/`"codex"` (off by default) with env-var-based CLI auth, this now strips that too, same as every `*_API_KEY`/`*_TOKEN` — you'll need to switch to a non-env auth method for the CLI agent, or explicitly re-add the specific var to `_SAFE_ENV_KEYS` in `sandbox.py` if you accept the exfiltration-surface tradeoff for it.
- **S0-9 skipped** — re-examined and it's not a fixable bug: `setup_commands` are operator-authored shell command strings *by design* (meant to run with shell semantics — `&&`, pipes, etc.), not single values that leaked into a shell context. `shlex.quote`-ing the whole string would break every legitimate multi-word setup command. The "config injection" the audit flagged is inherent to the feature, not a defect.
- **S0-10** done, but **non-blocking**: added a `security` CI job (bandit + pip-audit) with `continue-on-error: true`. A local bandit run found 40 pre-existing medium-severity findings (mostly `urlopen`-scheme and SQL-string-build warnings, largely false/low-risk positives) that haven't been triaged — hard-gating on them now would fail CI on unrelated debt, not on anything this wave touched. Flip to blocking once triaged.

Regression: 469 tests across the touched areas passed (sandbox/validator/literature/docker/code_agent/prompt_helpers subsets + 2 pre-existing docker-fallback tests updated for the new default + 12 new tests added for S0-1/S0-3). Full unpartitioned suite run pending at time of writing.

---

## 0. Revised baseline — the audit under-scored the system

The 2026-08-10 audit scored **4/10** but did **not** audit security. A dedicated security pass (this document's Wave 0 evidence) found an unmitigated remote-code-execution chain. Scoring security in scope, the honest baseline is **3/10**.

### 0.1 The exploit chain (all four links `[VERIFIED]`)

```
 anyone posts a paper to arXiv
   → abstract fetched by berb/literature/, zero sanitization
   → embedded verbatim as the LAST line of an LLM user message   [L1]
   → injected instructions steer the code-generating LLM          [L2]
   → generated code is NEVER security-validated on the run path   [L3]
   → executed on the HOST via subprocess when Docker is absent    [L4]
```

| Link | Evidence | Why it holds |
|---|---|---|
| **L1** | `_literature.py:816` builds `candidates_text` from raw arXiv/OpenAlex/S2 rows → `:834-836` → lands at `prompts.py:1591` as `"Candidates JSONL:\n{candidates_text}"` | Last-line position is the strongest injection slot. System prompt (`prompts.py:1556-1563`) carries no instruction-hierarchy defense. Repo-wide grep for delimiter/injection defenses: zero hits. Same pattern at `pdf_ingestor.py:224`, `fs_processor.py:491-501,563,638,685`. |
| **L2** | No defense exists to break | — |
| **L3** | `_execution.py:164-183` — **spot-verified by direct read**: reads `main.py` at `:142`, jumps to `create_sandbox()` at `:176` and `run_project()`/`run()` at `:179`/`:183`. No `validate_code` call. `validate_code` *is* imported at `:14-16` but only used in the stage-13 refine loop (`:1073`, `:1091`). | The validator is decorative on the live path. |
| **L3b** | `_code_generation.py:837-840` — **spot-verified**: `issue.category in ("syntax","import")`. `"security"` is absent, so a security-severity error never sets `_has_critical` and never blocks. | Both gates that could stop malicious code are open. |
| **L4** | `config.py:581` `mode = "docker"` (default) + `config.py:404` `fallback_to_sandbox = True` (default) + `factory.py:34-58` — **spot-verified**: returns `ExperimentSandbox` (plain `subprocess.run`, `sandbox.py:382/485`) with only a `logger.warning` when the Docker daemon or image is missing. | Advertised isolation is absent on any Docker-less machine, silently. `SandboxConfig.max_memory_mb` / `allowed_imports` are never applied in `sandbox.py`. |

**Assessment:** each link is individually a defensible engineering shortcut; chained, they are a path from a public upload to code execution on the operator's machine with the operator's filesystem and network. No single fix closes it — the plan below closes all four independently (defense in depth), so that any one holding is sufficient.

### 0.2 Additional confirmed security findings

| ID | Finding | Evidence |
|---|---|---|
| S-a | Validator gaps: attribute-chain escapes (`().__class__.__bases__[0].__subclasses__()`) not caught — `visit_Subscript:283` only fires on `ast.Name`; aliased imports bypass (`import os as _o; _o.system(...)` → resolves `"_o.system"`, not in deny set); `from os import system; system(...)` → `"system"`, unmatched; `open()` for write unblocked; `pickle` in `SAFE_STDLIB:164` (`pickle.loads` = arbitrary code exec) | `berb/experiment/validator.py:67-134, 267-337` |
| S-b | `code_agent.py:427` passes `{**os.environ}` — every host credential — to a subprocess that at `:589` runs `claude -p <llm-prompt> --dangerously-skip-permissions --allowed-tools "Bash Edit Write Read"`. The sandbox path deliberately does the opposite via `_safe_subprocess_env()` (`sandbox.py:56-72`); `code_agent.py` does not use it. Off by default (`config.py:549` `provider="llm"`). | `berb/experiment/code_agent.py:427,438,585-598,691-704` |
| S-c | Path traversal: `paper_id` from external API used unsanitized as a filename — `paper_file = cluster_dir / f"{paper_id}.md"`. An `id` of `../../../../x` escapes the workspace. 10 further sites; `keyword` used as a dir name at `:366/374`; `:642` does `topic.replace('/','_')` which misses `\` and `..`. | `berb/literature/fs_processor.py:327-330,380,390,422,467,511,520,581,692,777,792` |
| S-d | SSRF guard exists (`berb/web/_ssrf.py:10-47`, fail-closed, blocks private/loopback/link-local) but **`berb/literature/` never calls it** — zero hits repo-wide under that path. `full_text.py:363` fetches caller-supplied URLs with `follow_redirects=True` (`:354`), so even an allowlisted host can redirect to `169.254.169.254`. No host allowlist anywhere. | `berb/literature/full_text.py:354,363`; `zotero_integration.py:294,385` |
| S-e | Docker network policy is fail-**open**: `network_policy="setup_only"` (`config.py:397`) enforced by in-container iptables, documented to "gracefully degrade if the user lacks root — network remains available", justified by "the code has already been validated by the pipeline security check" — which per L3 does not run on this path. | `berb/experiment/docker_sandbox.py:487-491` |
| S-f | `ssh_sandbox.py:209` — `f"cd {remote_dir_q} && {setup_cmd}"`; `remote_dir_q` is quoted (`:181`), `setup_cmd` is not. Source is operator config (`config.py:1353`), not LLM output → low severity, but turns any config-injection into remote command execution. | `berb/experiment/ssh_sandbox.py:209,337-341` |

**Verified-clean (no action):** no `shell=True` or `os.system` call sites anywhere in `berb/`; plaintext API keys rejected at config validation (`config.py:283-288`); keys read from env by name (`:246-269`); no `asdict(config)` written to `run_dir`; no logger emits a key value.

### 0.3 Score arithmetic

| Wave | Removes | Score after |
|---|---|---|
| — | baseline (security in scope) | **3.0** |
| **0 — Security** | RCE chain + 6 findings | **5.0** |
| **1 — Critical arch** | 2 CRITICAL (blocking-in-async, resilience bypass) | **6.5** |
| **2 — High arch** | 3 HIGH (god modules, dead ports, layer leak) | **7.5** |
| **3 — Structural** | schema coupling, dead code, orphans | **8.2** |
| **4 — Observability/testability** | the 8→10 rubric delta ("observable, testable") | **8.7** |

Waves 0–1 are non-negotiable. Wave 4 is what separates 8.2 from >8.5 — the rubric's 10-anchor explicitly requires *observable* and *testable*, and both are currently near-zero (Wave 4 evidence below).

---

## 1. Paradigm & pattern selection per module

The governing principle: **reuse what already exists in this repo before writing anything new.** Six of the fixes below are pure wiring of code that is already written, tested, and orphaned. That is deliberate — the cheapest correct fix is the one whose code already passed review.

| Module | Paradigm | Pattern | Why this one |
|---|---|---|---|
| `berb/experiment/` (validation) | Imperative policy enforcement at a choke point | **Guard at the shared boundary**, not per-caller | 4 sandbox modes × N call sites; enforcing in `ExperimentSandbox.run/run_project` means every mode and every future caller inherits it. Patching `_execution.py:164` alone leaves the search path (`:445`) and stage-13 still open. |
| `berb/experiment/validator.py` | Functional AST analysis, **allowlist over denylist** | Visitor (keep) + inverted policy | Current `_SecurityVisitor` is a denylist; S-a proves denylists lose. `SAFE_STDLIB` already exists — make it authoritative and reject unknown imports rather than enumerating dangerous ones forever. |
| `berb/experiment/factory.py` | Fail-closed configuration | **Explicit-consent downgrade** | Silent capability downgrade is the anti-pattern. Fallback should require the operator to have asked for it, not happen by default. |
| `berb/literature/` + prompts | Functional, one pure helper | **Delimited untrusted-data envelope** | Single `wrap_untrusted()` used at 6 sites. No class hierarchy, no per-source strategy — the defense is identical regardless of source. |
| `berb/literature/` (network, paths) | Reuse existing guards | **Adapter reuse** | `check_url_ssrf` and `berb/utils/sanitize.py` already exist and are already used elsewhere in the repo. Zero new logic. |
| `berb/llm/` | Factory | **Abstract Factory (already written — just call it)** | `create_llm_client()` at `llm/__init__.py:139-183` already handles ACP / multi-provider / Smart wrapping. The bug is that `executor.py:183-186` bypasses it. Fix is at the call site. |
| `berb/review/ensemble.py` | Structured concurrency | `asyncio.to_thread` + bounded `gather` | The correct pattern already exists in the same file (`:384,395,412`, batch-API path). Apply it to the non-batch path. |
| `berb/pipeline/stage_impls/` | Module-per-stage | **Existing one-file-per-phase convention** | Not a new architecture — `_review_publish.py` simply violates the convention its siblings follow. |
| Inter-stage artifacts | Data-oriented | **Frozen dataclass + parse-at-boundary** (`from_json` classmethod) | Matches the repo's existing `@dataclass(frozen=True)` idiom (`StageResult`, `StageContract`) and the user's Python rules. Validate on read, not on write — the read site is where a bad shape currently degrades silently. |
| `berb/adapters.py` | YAGNI | **Delete three ports** | Tests already inject via `llm=` kwarg (`test_berb_executor.py:1796-1799`). The port layer is a redundant second DI mechanism that nothing implements. |
| Observability | Structured events | **Wire the orphaned `pipeline/tracing.py`** | 220 lines of working span/trace code with zero importers. Writing a second one would be absurd. |

---

## Wave 0 — Security (blocking; nothing else ships first)

### S0-1 · Enforce validation at the sandbox boundary
**Files:** `berb/experiment/sandbox.py`, `docker_sandbox.py`, `ssh_sandbox.py`, `colab_sandbox.py` (or a shared base)
Move `validate_code` from an optional caller-side courtesy to a mandatory guard inside `run()` / `run_project()`. Reject with a typed error before any subprocess spawns. Root-cause fix per the shared-boundary rule: `_execution.py:164-183`, `:445`, and every future call site are covered by one guard.
**Ceiling:** `# ponytail: AST validation only — no runtime seccomp; container/gVisor if untrusted code ever runs.`
**Test:** malicious snippet (`os.system`) reaches `run()` → raises, subprocess never spawns.

### S0-2 · Make security-category errors blocking
**File:** `berb/pipeline/stage_impls/_code_generation.py:837-840`
Add `"security"` to the critical-category tuple. One-line diff.
**Test:** code with a security-category error → stage returns `FAILED`, not `COMPLETED`.

### S0-3 · Close the validator's known bypasses
**File:** `berb/experiment/validator.py`
- Invert to allowlist: reject imports not in `SAFE_STDLIB` rather than enumerating dangerous ones.
- Remove `pickle` (`:164`) and audit `zipfile` (`:180`) from `SAFE_STDLIB`.
- Resolve import aliases before matching (`import os as _o` → canonical `os.system`); handle `from X import Y` bare-name form.
- Reject attribute-chain escapes: any `__class__` / `__bases__` / `__subclasses__` / `__globals__` / `__mro__` access.
- Add `open()` in write modes, `os.rename/replace/truncate/chmod/fork/spawn*/putenv`.
**Test:** one parametrized test, one case per bypass above, each asserting rejection.

### S0-4 · Fail closed on missing isolation
**Files:** `berb/config.py:404`, `berb/experiment/factory.py:34-58`
Default `fallback_to_sandbox = False`. When `mode="docker"` and Docker is unavailable, raise — do not silently downgrade. Operators who genuinely want host execution set `mode="sandbox"` explicitly, which is honest about what they get.
**Also:** `docker_sandbox.py:487-491` — make network-policy enforcement failure fatal rather than fail-open, and delete the code comment justifying fail-open by a validation step that does not run.
**Test:** `mode="docker"`, Docker unavailable, default config → raises; does not return `ExperimentSandbox`.

### S0-5 · Prompt-injection envelope
**New:** one helper in `berb/pipeline/_prompt_helpers.py` (module already exists, already the shared prompt utility):
```
wrap_untrusted(text: str, label: str) -> str
```
Wraps in an unambiguous fenced delimiter, strips/escapes any occurrence of the delimiter token from the payload, and prefixes an explicit data-not-instructions statement. Pair with a one-line addition to the affected system prompts asserting the hierarchy.
**Apply at all 6 confirmed sites:** `_literature.py:816`, `pdf_ingestor.py:224`, `fs_processor.py:491-501`, `:563`, `:638`, `:685`.
**Ceiling:** `# ponytail: delimiter+hierarchy defense — mitigation, not proof; S0-1..S0-4 are the real containment.`
**Test:** an abstract containing `"Ignore previous instructions and ..."` plus a forged delimiter → payload appears inside the envelope, delimiter is neutralized.

### S0-6 · Reuse the existing SSRF guard in `berb/literature/`
**Files:** `full_text.py:354,363`, `zotero_integration.py:294,385`
Call the existing `check_url_ssrf` (`berb/web/_ssrf.py:10-47`). Set `follow_redirects=False` and re-check each hop, or use a redirect hook — an allowlisted host that redirects to `169.254.169.254` is the concrete bypass.
**Test:** fetch of a `169.254.169.254` URL, and of a URL redirecting there, are both refused.

### S0-7 · Sanitize external identifiers used as paths
**File:** `berb/literature/fs_processor.py` (13 sites listed in §0.2 S-c)
Reuse the existing `berb/utils/sanitize.py` helper (already applied to figure IDs at `renderer.py:177/179`). Extend or add a sibling for path components; apply to `paper_id`, `keyword`, `topic`.
**Test:** `paper_id="../../../etc/x"` writes inside the workspace, not outside.

### S0-8 · Strip the environment for CLI-agent subprocesses
**File:** `berb/experiment/code_agent.py:427`
Replace `{**os.environ}` with the existing `_safe_subprocess_env()` (`sandbox.py:56-72`). Pure reuse. Separately, surface `--dangerously-skip-permissions` (`:589`) as an explicit opt-in config flag with a startup warning rather than a hardcoded argv element.
**Test:** a secret-suffixed env var set in the parent is absent from the child's env.

### S0-9 · `ssh_sandbox` setup-command quoting
**File:** `berb/experiment/ssh_sandbox.py:209`
`shlex.quote` the `setup_cmd` components, matching the treatment `remote_dir_q` already gets at `:181`. Low severity, one line.

### S0-10 · Security in CI
**File:** `.github/workflows/ci.yml`
Add `bandit -r berb/` and a dependency audit (`pip-audit`) as a job. Neither exists today.

---

## Wave 1 — Critical architecture

### A1-1 · Un-block the async review fan-out
**File:** `berb/review/ensemble.py:525`
Wrap `self._llm_client.chat(...)` in `await asyncio.to_thread(...)`. `_generate_review` is `async def` (`:498`) but the call is synchronous and lands in `urllib.request.urlopen` (`client.py:935/955`), so the `asyncio.gather` at `:328` yields zero parallelism — N personas run serially and the event loop is blocked throughout. The correct pattern is already in this file at `:384,395,412`.
**Add:** a bounded `asyncio.Semaphore` around the fan-out so restoring real concurrency doesn't immediately trip provider rate limits.
**Test:** two fake reviewers each sleeping 100 ms complete in <150 ms wall-clock, not >200 ms.

### A1-2 · Stop bypassing the LLM client factory
**File:** `berb/pipeline/executor.py:183-186`
Call `create_llm_client(config)` unconditionally; it already branches on ACP internally (`llm/__init__.py:157-183`) and adds `MultiProviderLLMClient` failover when `fallback_providers` is set, plus `SmartLLMClient` when NadirClaw/tracking is on. Today the non-ACP branch constructs `LLMClient.from_rc_config()` directly, so **configured `fallback_providers` never take effect on the default path**.
**Preserve:** the existing `if candidate.config.base_url and candidate.config.api_key` guard — stage impls rely on `llm=None` when nothing is configured. Do not drop this while refactoring.
**Test:** config with `fallback_providers` set → executor produces a `MultiProviderLLMClient`; config with no key → still yields `None`.

---

## Wave 2 — High-severity architecture

### A2-1 · Split `_review_publish.py` (3617 lines)
Six `@register_stage` decorators in one file. Split along the verified seams into the one-file-per-concern shape its siblings already use:

| New module | Contents | Source lines |
|---|---|---|
| `_review.py` | E18 `_execute_peer_review` :158, E19 `_execute_paper_revision` :243, E20 `_execute_quality_gate` :479, `_build_ensemble_structured_context` :422, `_collect_experiment_evidence` :70 | 53–1006 |
| `_archive.py` | E21 `_execute_knowledge_archive` :932, `_sanitize_fabricated_data` :1007 | 932–2024 |
| `_export.py` | E22 `_execute_export_publish` :2036, `_detect_dependencies` :1916, `_package_code_release` :1938 | 1916–3303 |
| `_citations.py` | E23 `_execute_citation_verify` :3417, `_load_seminal_papers_by_key` :1630, `_seminal_to_bibtex` :1648, `_resolve_missing_citations` :1699, `_check_citation_relevance` :3304, `_remove_bibtex_entries` :3357, `_remove_citations_from_text` :3382 | 1630–1915 + 3304–3617 |

Mechanical move — no logic changes in the same commit, so the existing 196 tests in `test_berb_executor.py` are the regression proof. Registry decorators mean no dispatch table to update, but the new modules must be imported so registration fires.
**Also:** `berb/llm/openrouter_adapter.py` (3951 lines) — same treatment, separate commit.

### A2-2 · Delete the dead port layer
**File:** `berb/adapters.py`
`LiteratureSource` (:76), `ExperimentSandbox` (:92), `ArtifactStore` (:102) each have exactly one implementer — their own `Recording*` stub — and zero read sites in `stage_impls/`. Tests inject fakes via the `llm=` kwarg (`test_berb_executor.py:1796-1799`), which already works. Delete all three; the abstraction advertises swappability that does not exist.
`LLMProvider` has one real consumer (`_literature.py:510`) — either convert that to the kwarg convention and delete it too, or keep it and document that it is the *only* supported seam. **Do not leave both mechanisms half-wired**; that ambiguity is the actual defect.
`AdapterBundle`'s `message`/`memory` members stay — they have real call sites (`executor.py:173,179`).

### A2-3 · Resolve the layer-leak contradiction
Every `stage_impls/*.py` imports `LLMClient` directly, while `adapters.py:59` documents "Stage implementations depend on this, not LLMClient". Once A2-2 picks a single seam, update that docstring to describe what the code actually does. A comment asserting a contract the code violates is worse than no comment.

---

## Wave 3 — Structural

### A3-1 · Typed contracts for cross-stage artifacts
12 artifacts are read by more than one stage module; `_review_publish.py:1049-1053` picks among `stage-14*/experiment_summary.json` candidates by an ad-hoc `_richness` heuristic, and `summary.py:88-99` silently degrades to `None` on shape mismatch. There are also hardcoded cross-stage paths (`"stage-20/quality_report.json"`, `"stage-12/journal.json"`, `"stage-03/sources.json"`) — path coupling on top of schema coupling.

Add a frozen dataclass with a `from_json` classmethod per artifact, raising on shape mismatch at the **read** site. **Start with the three hottest** — `experiment_summary.json`, `evidence_registry.json`, `claim_manifest.json` (each touched by 3 modules) — before generalizing to the remaining 9. Do not attempt all 57 JSON artifact types.

### A3-2 · Delete confirmed dead code
- `berb/llm/model_router.py` — near-duplicate of `model_cascade.py`, zero importers.
- `berb/llm/model_cascade.py` — also zero importers. Either wire it into the factory (Wave 1 makes this reachable) or delete. Two parallel unused cascade implementations is strictly worse than one.

### A3-3 · Decide the orphaned subsystems — **needs a product call, not a refactor**
`berb/memory/`, `berb/research/`, `berb/vision/`, `mnemo_bridge/`, `reasoner_bridge/`, `pipeline/tracing.py`, `berb/metrics/` — all fully implemented, tested, zero production importers. Plus `berb/cognitive_flow/`, `integrations/`, `learning/`, `plugins/`, `api/`, `feedback/`, `ui/`, `docker/` have **no test coverage at all**.

Wire or delete — but that is the owner's decision, not a refactor I should make unilaterally. Note that Wave 4 wires two of these (`tracing.py`, `metrics/`), which resolves them by use.

---

## Wave 4 — Observability & testability (the 8.2 → 8.7 delta)

Current state is the weakest area and the rubric's 10-anchor names it explicitly.

### A4-1 · Structured logging with run correlation
278 `logging.getLogger(__name__)` call sites across 277 files, all printf-style free text. **No `berb/logging_config.py` exists**; no `basicConfig`/`dictConfig`/`structlog` anywhere; zero `extra={...}` payloads in stage code; **no run_id on any log record** — so logs from concurrent DAG-level stages are unattributable.
Lazy fix: one `logging.LoggerAdapter` (or a `Filter`) installed once at runner entry, injecting `run_id` + `stage`. No call-site changes.

### A4-2 · Wire the orphaned tracing
`berb/pipeline/tracing.py` — 220 lines, complete span/trace implementation writing `<run_dir>/<trace_id>/trace.jsonl` (`_flush_span:210`), **zero importers**. Call `new_trace` in `runner.py` and `start_span` around `execute_stage`. Reuse, not rewrite.

### A4-3 · Fix cost attribution
`_record_llm_cost` (`client.py:993`, called at `:990`) writes to a process-local in-memory singleton and **swallows failures** (`:1007-1008`). `CostEvent` (`cost_tracker.py:38`) *has* `stage`/`phase`/`node_id`/`purpose` fields and aggregators `by_stage()`/`by_phase()`/`by_node()` exist (`:174-200`) — but the call site at `:1004-1006` passes **none of them**, so every aggregator returns an empty dict.
Fix: thread stage/phase through to the call site, and persist to `run_dir/cost_report.json` at run end. `berb report` (`cli.py:1280`, handler `:844`) contains zero occurrences of "cost" — add a cost section once the data is real.

### A4-4 · Restore type checking
`pyproject.toml:223` — `[[tool.mypy.overrides]] module = ["berb.*"] → ignore_errors = true`. Only **8 modules** are actually checked. CI's `mypy berb/` (`ci.yml:101`) is therefore near-vacuous.
Remove the blanket override incrementally, security-critical modules first: `experiment/validator.py`, `experiment/factory.py`, `experiment/sandbox.py`, `llm/client.py`, `pipeline/executor.py`. Add each to the checked list as it goes clean.

### A4-5 · Coverage gate
`--cov-fail-under=55` (`ci.yml:48`), with a comment noting the previous aspirational 70 "had been silently failing". No `[tool.coverage]` section anywhere. Raise to 70 once Waves 0–3 land (each ships tests), then 80 per the project's own standard. Ratchet only — never lower it to make a build pass.

---

## Execution order & risk

| Wave | Blocking? | Risk | Regression proof |
|---|---|---|---|
| **0** (S0-1…S0-10) | **Yes — first** | S0-4 will break Docker-less dev machines *by design*; document the `mode: sandbox` opt-out in the release note | New per-fix tests + full suite |
| **1** (A1-1, A1-2) | Yes | A1-2 must preserve the `base_url and api_key` guard or every stage gets a non-`None` misconfigured client | Existing 3900+ suite |
| **2** (A2-1…A2-3) | No | Mechanical moves; highest churn, lowest logical risk | 196 tests in `test_berb_executor.py` |
| **3** (A3-1…A3-3) | No | A3-1 turns silent degradation into loud failure — expect previously-passing runs to start failing honestly | Per-artifact round-trip tests |
| **4** (A4-1…A4-5) | No | A4-4/A4-5 will surface a backlog of pre-existing type/coverage debt | CI |

**Sequencing rule:** Wave 0 ships as its own PR series and is not bundled with refactors. Mixing a security fix into a 3617-line file split makes the security change unreviewable.

**Do not do:** Wave 2's file splits before Wave 0 — moving 3617 lines while the RCE chain is open trades review attention for cosmetics.

---

## Open questions for the owner

1. **A3-3** — wire or delete the orphaned subsystems? `berb/research/` and `berb/vision/` alone are ~3400 lines of tested, unreachable code. This is a product decision.
2. **S0-4** — confirm that failing closed (breaking Docker-less machines by default) is acceptable. The alternative is a loud startup banner plus a required explicit `mode: sandbox`, which is weaker but less disruptive.
3. **S0-8** — should the `--dangerously-skip-permissions` CLI-agent path (`code_agent.py:589`) exist at all, or be removed? It is off by default (`config.py:549`) but is the single highest-privilege code path in the repo.
