# Implementation Audit Report — Berb Architecture Hardening Plan (Wave 0)

**Audited plan:** [`tasks/arch_hardening_plan.md`](tasks/arch_hardening_plan.md)
**Baseline:** [`tasks/arch_audit_2026-08-10.md`](tasks/arch_audit_2026-08-10.md)
**Code changes reviewed:** uncommitted working-tree diff (`git diff`) against `main`, 17 tracked files + 3 untracked files
**Method:** file-by-file diff review against each plan item's stated acceptance criteria, cross-checked against the plan's own "done" claims; targeted test execution; static confirmation that unrelated files are untouched.
**Architecture reference used:** `docs/CODEBASE_MIND_MAP.md`, `CLAUDE.md`

---

## 1. Executive Summary

The plan defines 5 waves (0–4). **Only Wave 0 (Security) has any corresponding code change.** `git diff --stat` confirms zero modifications to any file cited in Waves 1–4 (`berb/review/ensemble.py`, `berb/pipeline/executor.py`, `berb/adapters.py`, `berb/pipeline/stage_impls/_review_publish.py`, `berb/llm/model_router.py`, `berb/llm/model_cascade.py`, `berb/pipeline/tracing.py`, CI coverage/mypy config). This is not a defect — the plan itself sequences Wave 0 as blocking-and-first and explicitly says "not bundled with refactors" — but it means the two CRITICAL architecture findings from the baseline audit (blocking-in-async ensemble, bypassed LLM factory) are **still live**, and the deliverable should not be read as "the plan was executed," only as "Wave 0 was executed."

Within Wave 0, **8 of 10 items are fully done, 1 is correctly and transparently skipped (S0-9), and 1 is partially done with an undisclosed scope cut (S0-3's allowlist inversion).** Two stale/contradictory comments that the plan explicitly said to delete or that describe pre-fix behavior remain in the code. Test coverage is solid for the two items with dedicated new test files (S0-1, S0-3, S0-4) but **absent for four items' own stated acceptance tests** (S0-5, S0-6, S0-7, S0-8) — the code changes for those are real and, on manual read, correct, but nothing in the test suite would catch a regression to any of them.

No architecture regressions were introduced — Wave 0's changes are narrowly scoped to the security/experiment/literature layers and do not touch or violate any documented module boundary.

**Verdict: APPROVED WITH CHANGES** (see §7).

---

## 2. Plan Compliance Matrix

### Wave 0 — Security (the only wave with code changes)

| Plan Item | Status | Evidence | Notes |
|---|---|---|---|
| S0-1 Enforce validation at sandbox boundary | **Complete** | `sandbox.py` +40, `docker_sandbox.py` +22: `check_code_security()` added, called in `ExperimentSandbox.run/run_project` and `DockerSandbox.run/run_project` before any `subprocess.run`. New `tests/test_sandbox_security_gate.py` (5 tests) — **all pass**, verified by direct execution. | Guard is at the shared boundary as specified, not per-caller. |
| S0-2 Security-category errors blocking | **Complete** | `_code_generation.py:838` — `"security"` added to the critical-category tuple, 1-line diff exactly as scoped. | **No dedicated test added** for this item (see §5). |
| S0-3 Close validator bypasses | **Partial — undisclosed scope cut** | `validator.py` +96/-2: alias resolution (`_canonical_call_name`), attribute-chain escape detection (`ESCAPE_ATTRS`, `visit_Attribute`), `pickle.load(s)` moved to `DANGEROUS_CALLS` and removed from `SAFE_STDLIB`, `open()`/`os.open()` literal-escape-path check, `os.rename/replace/truncate/chmod/chown/fork/forkpty/spawn*/putenv` added. All verified in diff and covered by 11 new tests in `test_berb_validator.py` — **all pass**. **BUT** the plan's own S0-3 spec's first bullet — *"Invert to allowlist: reject imports not in SAFE_STDLIB rather than enumerating dangerous ones"* — was **not implemented**. `visit_Import`/`visit_ImportFrom` still gate only on the `BANNED_MODULES` denylist (unchanged), and `validate_imports()` still emits unavailable-module findings as `severity="warning"`, `category="import"` — never blocking, never `category="security"`. | The plan's own "Wave 0 status" write-up for S0-3 lists every sub-item it completed and silently omits the allowlist-inversion bullet, unlike S0-9 and the Zotero case below, which are explicitly flagged as deviations. This is the one place the plan's self-report is not fully honest about scope. **HIGH** — this was the mechanism the plan itself identified as closing the denylist's structural weakness (S-a in the baseline audit: "denylists lose"); a new dangerous stdlib call not yet in `DANGEROUS_CALLS`/`BANNED_MODULES` is still importable and callable today. |
| S0-4 Fail closed on missing isolation | **Complete, with 2 stale-comment defects** | `config.py`: `fallback_to_sandbox` default `True`→`False`, confirmed. `factory.py` (unmodified but re-read): raises `RuntimeError` when Docker unavailable and fallback disabled — confirmed by direct read and by new test `test_factory_raises_by_default_when_docker_unavailable` (pass). `docker/entrypoint.sh`: network-cutoff failure now `exit 1` instead of warn-and-continue, confirmed. | See §4/§6 for the two stale comments (`factory.py:25` docstring, `docker_sandbox.py:509-511`) the plan told itself to fix/delete and didn't. |
| S0-5 Prompt-injection envelope | **Complete** | `berb/utils/sanitize.py` +31: `wrap_untrusted()` added — delimiter fencing + data-not-instruction framing + delimiter-token stripping from payload, matching spec. Applied at all 6 cited sites: `_literature.py:816` (`candidates_text`), `pdf_ingestor.py:224`, `fs_processor.py` abstract (2 sites), papers_text (contradictions), abstract (methods). Verified each site individually in diff. | **No test added** for the delimiter-neutralization acceptance criterion the plan specified (see §5). |
| S0-6 SSRF guard reuse | **Complete for `full_text.py`; Zotero claim slightly incomplete** | `full_text.py` +29: `check_url_ssrf()` called at `extract()` entry and on every redirect hop (5-hop cap, `follow_redirects=False`). Verified by direct read. Zotero: confirmed 2 of 3 `httpx.AsyncClient` construction sites (`zotero_integration.py:279-280, 364-365`) use a hardcoded `base_url="https://api.zotero.org"` — the plan's "no attacker-reachable host" reasoning holds for those. | A **third** `AsyncClient` site exists at `zotero_integration.py:611-612` (`_mcp_call`, `base_url=self.config.mcp_url`) that the plan's write-up did not count ("both calls go through..."). This is operator-supplied config, not attacker-reachable data — same trust class as S0-9's `setup_commands` — so it is **not a live vulnerability**, but the plan's own evidence count ("both calls") undercounts the actual 3 sites. **LOW**, flagged as `HYPOTHESIS` on materiality since it wasn't independently re-derived from a security review, only noted as a factual gap in the plan's count. No test added for the redirect-hop-to-`169.254.169.254` acceptance criterion. |
| S0-7 Sanitize path identifiers | **Complete** | `fs_processor.py` +33/-35: `_safe_paper_id()` added (wraps `sanitize_figure_id`), applied at all cited `paper_id` sites (verified: cluster_dir, keyword_dir/other_dir, year_path, tiers, summaries_dir ×2, claims_dir, methods_dir — 9 sites) plus the `topic`-as-filename site (`sanitize_figure_id(topic, fallback='topic')` replacing the `.replace('/', '_')` that missed `\` and `..`). | The `keyword`-as-dirname site was left alone per the plan's own "hardcoded 5-item constant, not external data" rationale — this report did not independently re-verify that claim against `fs_processor.py`'s keyword source; flagged `HYPOTHESIS`, inherited from the plan, not re-derived. No test added for the path-traversal acceptance criterion (see §5). |
| S0-8 Strip CLI-agent subprocess env | **Complete, 1 style nit** | `code_agent.py` +5/-1: `{**os.environ}` replaced with `_safe_subprocess_env()` at the CLI-agent spawn site. Confirmed the imported helper strips all `_SECRET_PATTERNS`-matching keys plus `AWS_/AZURE_/GOOGLE_/GCP_/GITHUB_`-prefixed vars, keeping only an explicit `_SAFE_ENV_KEYS` allowlist (`PATH`, `HOME`, etc.) — matches the plan's stated caveat about breaking env-based `claude_code`/`codex` auth. | `_safe_subprocess_env` is a `_`-prefixed (module-private) symbol in `sandbox.py`, imported directly across a module boundary by `code_agent.py` — an encapsulation nit, **LOW**, not a functional defect. No test added for the "secret-suffixed env var absent from child env" acceptance criterion (see §5). The `--dangerously-skip-permissions` opt-in-flag part of S0-8 ("surface as an explicit opt-in config flag with a startup warning") was **not done** — it remains a hardcoded argv element at `code_agent.py:589` per the plan's own unresolved Open Question #3. |
| S0-9 ssh_sandbox quoting | **Correctly skipped, as claimed** | `git diff --stat` confirms zero changes to `ssh_sandbox.py`. The plan's re-analysis (`setup_commands` are operator-authored shell strings by design; `shlex.quote`-ing the whole string would break every legitimate multi-word command) is architecturally sound and consistent with the same operator-trust model used to justify the Zotero `mcp_url` case above. | No action needed; correctly and transparently not done. |
| S0-10 Security in CI | **Complete, matches stated scope** | `.github/workflows/ci.yml` +32: new `security` job running `bandit -r berb/ -ll` and `pip-audit --strict`, both `continue-on-error: true`. Matches the plan's explicit "non-blocking, 40 untriaged pre-existing findings" rationale. | Correctly labeled non-blocking; the plan does not claim otherwise. |

### Waves 1–4 (Critical/High architecture, Structural, Observability)

| Plan Item | Status | Evidence |
|---|---|---|
| A1-1, A1-2 (Wave 1 — Critical) | **Missing** | Zero diff on `berb/review/ensemble.py`, `berb/pipeline/executor.py`. |
| A2-1, A2-2, A2-3 (Wave 2 — High) | **Missing** | Zero diff on `berb/pipeline/stage_impls/_review_publish.py`, `berb/llm/openrouter_adapter.py`, `berb/adapters.py`. |
| A3-1, A3-2, A3-3 (Wave 3 — Structural) | **Missing** | Zero diff on artifact contract files, `berb/llm/model_router.py`, `berb/llm/model_cascade.py`. |
| A4-1…A4-5 (Wave 4 — Observability) | **Missing** | No `berb/logging_config.py` created, `pipeline/tracing.py` untouched, `pyproject.toml` mypy overrides untouched, `ci.yml`'s `--cov-fail-under` untouched (the only `ci.yml` change is the new Wave-0 security job). |

---

## 3. Architecture Compliance Assessment

Wave 0's changes are narrowly scoped and **do not violate any documented module boundary**:

- `berb/utils/sanitize.py` gained `wrap_untrusted()` rather than `berb/pipeline/_prompt_helpers.py` (the plan's original sketch) — an explicit, reasoned deviation the plan documents: keeping it out of the pipeline layer so `berb.literature` doesn't have to import `berb.pipeline`. This is a **correct architectural call**, consistent with the layering the baseline audit itself flagged as already-leaky elsewhere (A2-3). `berb/pipeline/_prompt_helpers.py` re-exports it (`# noqa: F401 (re-exported)`) for pipeline call sites — reasonable.
- `berb/experiment/sandbox.py` gaining `check_code_security()` as the shared boundary guard, called identically from both `ExperimentSandbox` and `DockerSandbox`, matches the plan's own stated pattern ("Guard at the shared boundary, not per-caller") and is consistent with the codebase's existing `factory.create_sandbox()` dispatch convention documented in `docs/CODEBASE_MIND_MAP.md`.
- No new circular imports introduced: `sandbox.py` importing `validator.py` (S0-1) and `code_agent.py` importing `_safe_subprocess_env` from `sandbox.py` (S0-8) both flow in the existing dependency direction (`experiment/` submodules depending on each other, not on `pipeline/` or `llm/`).

The **CRITICAL architecture findings from the baseline audit remain fully open**: `executor.py:186` still bypasses `create_llm_client()`, and `ensemble.py:525` still blocks inside `async def`. This report does not treat that as a defect in the reviewed diff (it's out of Wave 0's stated scope) but flags it because the deliverables asked for an architecture compliance assessment against the full plan.

---

## 4. Code Quality Findings

| Severity | File | Finding |
|---|---|---|
| MEDIUM | `berb/experiment/docker_sandbox.py:509-511` | Comment left in place reads *"iptables requires NET_ADMIN but will gracefully degrade if the user lacks root — network remains available but the code has already been validated by the pipeline security check."* This is the exact comment S0-4's own spec says to delete ("delete the code comment justifying fail-open by a validation step that does not run"). It is now doubly stale: (a) the "already been validated" clause is true again post-S0-1, for a different reason than originally written, and (b) "network remains available" now contradicts `entrypoint.sh`'s new `exit 1` behavior for that exact failure mode. A future maintainer reading only this comment would believe the system still fails open. |
| LOW | `berb/experiment/factory.py:24-25` | Docstring still says *"Controlled by `config.docker.fallback_to_sandbox` (default: True)."* The dataclass default is now `False` (S0-4). Functionally correct code, stale doc. |
| LOW | `berb/experiment/code_agent.py:29` | Imports `_safe_subprocess_env` (module-private, `_`-prefixed) directly from `berb.experiment.sandbox`. Works, but crosses an encapsulation boundary the underscore is meant to signal against. Consider re-exporting it as a public name if `sandbox.py` is meant to be a shared security-utility surface (it now serves two modules). |
| LOW | `berb/experiment/validator.py:172-176` | The comment justifying `pickle`'s removal from `SAFE_STDLIB` ("the import itself is harmless, but treating it as unavailable steers the LLM toward json instead") is accurate and well-reasoned — noted as a **positive** finding, not a defect. |

No hardcoded secrets, no new SQL/shell injection surface, no unhandled exceptions introduced in the reviewed diff. Function sizes and file sizes in the diff stay well within the project's own 800-line convention.

---

## 5. Testing & Coverage Assessment

Ran the directly-affected test files:

```
tests/test_sandbox_security_gate.py tests/test_berb_validator.py tests/test_berb_docker_sandbox.py
→ 160 passed
```

| Plan item | Plan's stated "Test:" criterion | Test added? |
|---|---|---|
| S0-1 | malicious snippet reaches `run()` → raises, subprocess never spawns | **Yes** — `test_sandbox_security_gate.py`, 5 tests, pass |
| S0-2 | security-category error → stage returns `FAILED` | **No** — no test targets `_code_generation.py`'s `_has_critical` gate for the `"security"` category specifically |
| S0-3 | one parametrized test per bypass | **Yes** — `test_berb_validator.py`, 11 new tests (9 bypass cases + 1 false-positive-avoidance + parametrization), pass |
| S0-4 | Docker unavailable + default config → raises | **Yes** — `test_factory_raises_by_default_when_docker_unavailable`, pass; existing fallback tests correctly updated to opt-in via explicit config |
| S0-5 | forged delimiter in payload → neutralized | **No** — `wrap_untrusted()` has zero direct test coverage |
| S0-6 | SSRF-blocked fetch + redirect-to-`169.254.169.254` refused | **No** — no test exercises the new redirect-hop loop in `full_text.py` |
| S0-7 | `paper_id="../../../etc/x"` stays inside workspace | **No** — `_safe_paper_id()` has zero direct test coverage |
| S0-8 | secret-suffixed env var absent from child env | **No** — no test exercises `code_agent.py`'s new `_safe_subprocess_env()` call site |

**Gap:** 4 of 8 completed Wave-0 items (S0-5, S0-6, S0-7, S0-8) ship without the regression test their own plan entry specifies. The changes read correctly on manual inspection, but nothing in CI would catch a future regression — e.g., someone "simplifying" `wrap_untrusted()` and dropping the delimiter-stripping line would pass the full suite today.

Full suite: `pytest tests/ -q -m "not slow and not e2e and not llm"` → **3956 passed, exit 0**. This closes the plan's own open item ("Full unpartitioned suite run pending at time of writing") — Wave 0 introduces **no regressions**. Note this proves absence of breakage, not presence of coverage: the four items in the table above still have no test that would fail if their fix were reverted.

---

## 6. Risk & Regression Analysis

- **No architectural regressions.** Confirmed via zero-diff on every Wave 1–4 file.
- **No backward-compatibility break beyond the plan's own documented, intentional ones**: `fallback_to_sandbox: False` will break Docker-less dev/CI machines that relied on silent fallback — the plan flags this explicitly and it is the correct security tradeoff (S0-4's whole point).
- **Security posture genuinely improved** for the RCE chain described in the plan's §0.1: L3 (validator bypassed on the sandbox path) is closed by S0-1; L3b (security errors non-blocking) is closed by S0-2; L4 (silent host-execution fallback) is closed by S0-4. L1/L2 (prompt injection) get a mitigation (S0-5), not a proof, exactly as the plan itself characterizes it.
- **Residual risk from S0-3's undisclosed gap**: the validator is still a denylist for imports. A dangerous stdlib module not yet enumerated in `BANNED_MODULES` (or a dangerous call not yet in `DANGEROUS_CALLS`) remains importable and callable. This is the same structural weakness (S-a in the baseline audit) the plan set out to close and only partially closed.
- **Testing risk**: the 4-item test gap in §5 means a regression in `wrap_untrusted`, the SSRF redirect loop, `_safe_paper_id`, or the CLI-agent env strip would not be caught by CI today.

---

## 7. Required Corrections

| Severity | File | Issue | Recommendation |
|---|---|---|---|
| HIGH | `berb/experiment/validator.py` | S0-3's allowlist-inversion sub-item was not implemented; import validation is still denylist-only and non-blocking. Plan's own status write-up doesn't disclose this cut. | Either implement the allowlist inversion as originally specified, or explicitly amend `tasks/arch_hardening_plan.md`'s S0-3 status line to disclose the cut and its rationale (matching the transparency already given to S0-9 and the Zotero finding). |
| MEDIUM | `berb/experiment/docker_sandbox.py:509-511` | Stale comment describes fail-open behavior the code no longer has. | Delete or rewrite per the plan's own S0-4 instruction. |
| MEDIUM | tests (S0-5, S0-6, S0-7, S0-8) | No regression test for 4 completed Wave-0 items, despite each having a plan-specified "Test:" criterion. | Add the four tests the plan itself specifies: delimiter-neutralization for `wrap_untrusted`, SSRF-redirect-to-metadata-IP for `full_text.py`, path-traversal-`paper_id` for `_safe_paper_id`, secret-env-stripped for `code_agent.py`. |
| LOW | `berb/experiment/factory.py:25` | Docstring says fallback defaults to `True`; actual default is `False`. | Update docstring to match S0-4's new default. |
| LOW | `berb/experiment/code_agent.py:29` | Cross-module import of a private (`_`-prefixed) helper. | Either accept as-is (functionally fine) or promote `_safe_subprocess_env` to a public name in `sandbox.py` since it now serves two call sites in two modules. |
| INFO | `zotero_integration.py:611-612` | Plan's S0-6 evidence count ("both calls") misses a third `AsyncClient` site using a config-supplied `mcp_url`. Not a live vulnerability (operator-trusted input), but the plan's stated evidence is incomplete. | No code change required; optionally amend the plan's S0-6 note for accuracy. |
| INFO | Waves 1–4 | Entirely unimplemented — both CRITICAL findings from the baseline audit (blocking-in-async ensemble, bypassed LLM factory) are still live in production code. | Not a defect in this diff, but should not be conflated with "the plan is done." Sequence Wave 1 next per the plan's own execution-order table. |

---

## 8. Final Verdict

**APPROVED WITH CHANGES**

Wave 0's security work is substantively real, correctly scoped to the shared boundary pattern the plan specifies, and measurably closes 3 of the 4 links in the plan's own documented RCE chain (L3, L3b, L4) plus provides a reasonable mitigation for L1/L2. The two stale comments and the S0-3 scope gap are fixable in under an hour of follow-up work and do not require re-architecting anything already shipped. The missing tests for S0-5/6/7/8 should be added before this is considered done, not as a blocking condition on the code already written, but because "no test exists" is exactly the kind of gap that turns into a silent regression six months from now — the same failure mode this whole plan exists to close.

Waves 1–4 are not evaluated for approval here because no corresponding code exists to review; they remain open work against the plan's own execution-order table.
