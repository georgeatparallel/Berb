# Berb — Production Readiness Audit

**Date:** 2026-07-29
**Commit:** `1e264f5` (branch `main`)
**Scope:** 424 Python modules / 146,776 LOC in `berb/`, 152 test files / 3,848 tests, CI, packaging, security posture.

---

## 1. Verdict

Berb is a **mature prototype**, not a production system. The pipeline works, the test suite is large, and several hardening measures already exist (SSRF guard, sandbox secret redaction, reachability gate, checkpointing). What blocks "professional production-grade" is not missing features — it is that:

1. **The default network posture is unsafe.** A config file with a `server:` block that omits keys yields: bind `0.0.0.0`, CORS `*` with credentials, no authentication.
2. **CI is red right now and partly ceremonial.** Lint fails, format fails, 4 tests fail, and the type-check job checks 8 of 423 modules.
3. **31% of the codebase is unreachable** from any entry point, and 6 of 7 shipped HTTP servers are dead legacy code with no auth.

None of these are hard to fix. Estimated **~7–9 focused dev-weeks** to reach a defensible 1.0.

| Axis | State |
|---|---|
| Security | 🔴 Blocking |
| CI / quality gates | 🔴 Red on `main` |
| Correctness | 🟠 2 latent `NameError`s in prod paths, 4 failing tests |
| Type safety | 🔴 Gate is a no-op |
| Test coverage | 🟠 ~57%, 22.5 min runtime |
| Architecture hygiene | 🟠 31% dead code, 7 duplicate web apps |
| Observability | 🟠 Metrics module exists, not wired |
| Release engineering | 🔴 No lockfile, no CHANGELOG, no supply-chain scanning |
| Documentation | 🟢 README is genuinely good |

---

## 2. Evidence baseline

Everything below was executed against the working tree, not inferred.

```
pytest --collect-only            → 3,848 tests collected
pytest -m "not slow/e2e/llm"     → 4 failed, 3813 passed, 23 skipped  (22m 35s)
ruff check berb/ tests/          → 63 errors
ruff format --check berb/ tests/ → 29 files would be reformatted
mypy berb/                       → Success: no issues found in 422 source files
scripts/check_reachability.py    → 155/423 modules unreachable, 45,994 LOC (31%)
```

The CI workflow (`.github/workflows/ci.yml`) runs exactly `ruff check`, `ruff format --check`, `mypy berb/`, and the unit subset. **Two of those four gates fail on `main` today.**

---

## 3. P0 — Security blockers

### 3.1 Insecure-by-default server binding and CORS

`berb/config.py` declares secure dataclass defaults but the **YAML parser overrides them with insecure ones**:

```python
# berb/config.py:713-717  — the documented default
host: str = "127.0.0.1"          # "Secure default"
cors_origins: tuple[str, ...] = ()  # "Empty = deny all cross-origin"
auth_token: str = ""             # empty = no authentication

# berb/config.py:1555-1574 — what actually runs when a config file is loaded
def _parse_server_config(data):
    if not data:
        return ServerConfig()
    cors = data.get("cors_origins")
    ...
    elif cors is None:
        cors = ("*",)                       # ← wildcard, not deny-all
    return ServerConfig(
        host=data.get("host", "0.0.0.0"),   # ← all interfaces, not loopback
        auth_token=data.get("auth_token", ""),
        ...
    )
```

Then `berb/server/app.py:51-57` turns that wildcard into a credentialed wildcard:

```python
allow_origins=_origins,
allow_credentials=bool(_origins),  # True, because _origins == ("*",)
```

**Net effect:** any `config.yaml` containing a `server:` key without explicit `host`, `cors_origins`, and `auth_token` starts an unauthenticated pipeline-control API on all network interfaces, accepting credentialed cross-origin requests from any website. The `RCConfig()` no-config path is safe; the documented path is not.

**Fix:** make the parser defaults identical to the dataclass defaults; reject `allow_credentials` with wildcard origins; refuse to start when `host` is non-loopback and `auth_token` is empty (explicit `--insecure` opt-out only).

### 3.2 WebSocket endpoint bypasses authentication entirely

`berb/server/middleware/auth.py` extends `BaseHTTPMiddleware`, which Starlette only applies to `scope["type"] == "http"`. WebSocket connections are passed straight through. The token branch at lines 40-41 is unreachable dead code:

```python
if path.startswith("/ws"):
    token = request.query_params.get("token", "")   # never executed
```

So `/ws/events` (`berb/server/app.py:119`) is unauthenticated **even when `auth_token` is set**. Same file, line 46: `if token != self._token` is a non-constant-time comparison — replace with `hmac.compare_digest`. Line 19 exempts `/docs` and `/openapi.json`, publishing the full API surface pre-auth.

**Fix:** pure-ASGI middleware handling both `http` and `websocket` scopes, or an explicit `Depends` guard on the WS route; constant-time compare; drop the `/docs` exemption in production mode.

### 3.3 Six unauthenticated legacy HTTP servers ship in the wheel

| Module | Auth | CORS |
|---|---|---|
| `berb/server/app.py` | opt-in token | configurable | ← the one the CLI uses |
| `berb/api/server.py` | none | localhost:3000 |
| `berb/server/api.py` | none | localhost list |
| `berb/server/web_api_real.py` | none | `["*"]` **+ `allow_credentials=True`** |
| `berb/server/standalone_api.py` | none | localhost:3000 |
| `berb/server/web_api.py` | none | localhost:3000 |
| `berb/server/server_with_cors.py` | none | localhost list |

`web_api_real.py` is the worst: on top of the invalid wildcard+credentials combination, a custom middleware (lines 51-58) force-stamps `Access-Control-Allow-Origin: *` onto **every** response, and the OPTIONS handler adds `Access-Control-Allow-Credentials: true`. `berb/api/__init__.py:8` imports the unauthenticated app at package-import time, and `berb/ui/QUICK_START.md`, `INDEX.md`, and `UI_IMPLEMENTATION_GUIDE.md` all instruct users to run `python -m berb.api.server`.

**Fix:** delete all six. One app, one factory, one documented entry point. If any are still needed for local dev, move them out of the distributed package.

### 3.4 In-process execution of model-generated code

`berb/math/verification.py`:

```python
463:  return eval(expr, {"__builtins__": {}}, namespace)
500:  exec(instrumented_code, exec_globals)
```

`{"__builtins__": {}}` is not a sandbox — it is bypassable via attribute traversal on any object in `namespace` (numpy is injected there). Everywhere else in the codebase generated code goes through `berb/experiment/docker_sandbox.py`; this path does not.

**Fix:** route `_run_algorithm` through the existing Docker/subprocess sandbox, or restrict `_safe_eval` to an AST-whitelist evaluator (`ast.parse` + node allowlist) rather than `eval`.

### 3.5 Other

- `berb/mcp/transport.py:99` — `host: str = "0.0.0.0"` default bind.
- **No rate limiting anywhere.** `grep -rn 'ratelimit|slowapi|limiter' berb/server berb/api` → zero hits. Endpoints that trigger LLM calls are unmetered and cost real money.
- **No supply-chain scanning.** `.github/` contains only `workflows/` and PR templates — no `dependabot.yml`, no CodeQL, no `bandit`, no `pip-audit`, no secret scanning.
- `.env` is correctly gitignored (`.gitignore:104`) and no hardcoded credentials were found in tracked files. ✅

---

## 4. P1 — Make the quality gates real

### 4.1 CI is failing on `main`

| Gate | Result |
|---|---|
| `ruff check` | **63 errors** → job fails |
| `ruff format --check` | **29 files** → job fails |
| `pytest` (unit subset) | **4 failures** → job fails |
| `mypy` | passes (see 4.3) |

### 4.2 Two latent `NameError`s in production code paths

These are runtime calls, not annotations, on symbols that are never imported in their module:

```
berb/pipeline/stage_impls/_paper_writing.py:2293   manifest = ClaimManifest(paper_stage="draft")
berb/research/gap_analysis.py:515                  return PerspectiveResult(...)
```

Verified: `grep -n 'ClaimManifest' _paper_writing.py` returns only lines 2293/2345/2456 — no import. Same for `PerspectiveResult` in `gap_analysis.py`. Both functions raise `NameError` the moment they are called. The remaining `F821`s (`Path` in `berb/integrity/claims.py:209,217`) are annotation-only and harmless at runtime, but break `typing.get_type_hints()`.

### 4.3 The type-check job checks 2% of the codebase

`pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["berb.pipeline.registry", "berb.pipeline.resolution", "berb.pipeline.checkpoint",
          "berb.pipeline.asyncio_utils", "berb.pipeline.contracts", "berb.pipeline.stages",
          "berb.adapters", "berb.config"]
ignore_errors = false

[[tool.mypy.overrides]]
module = ["berb.*"]
ignore_errors = true          # ← everything else
```

"Success: no issues found in 422 source files" means mypy *parsed* 422 files and *reported* on 8. This is the single most misleading signal in the repo.

**Fix:** invert the policy. Keep a shrinking `ignore_errors` denylist instead of a growing allowlist, and ratchet it down each sprint. Same pattern applies to the ~60 blanket `per-file-ignores` entries in `[tool.ruff.lint.per-file-ignores]`.

### 4.4 Test suite: slow, mismarked, unevenly covered

- **22m 35s** for the "fast" subset. CI runs it twice (3.11 + 3.12) → ~45 min of billable runner time per push. Needs `pytest-xdist` (`-n auto`) and a fast/slow split.
- **4 failures are mismarked.** `tests/test_e2e_pipeline.py` and `tests/test_e2e_full_pipeline.py` are named e2e but carry no `@pytest.mark.e2e`, so they run inside the "no e2e" job. Reproduced:
  ```
  test_stage_13_iterative_refine → Stage failed: Missing or empty output: selection_bias.json
  test_stage_14_result_analysis  → same root cause
  ```
  Either the stage-13 contract is wrong or `selection_bias.json` is no longer produced — a real pipeline regression, not a flaky test.
- **Coverage ~57%** against a floor of 55 (the CI comment admits the 70% gate "had been silently failing"). `berb/writing/` is at 0%.
- No property-based, mutation, or contract testing despite the pipeline being a chain of JSON-artifact contracts — the ideal target for schema-driven testing.

### 4.5 Dependency management

`pyproject.toml` pins nothing: every dependency is `>=X` with no upper bound, and there is **no lockfile** (`requirements.txt`, `uv.lock`, `poetry.lock` all absent). Builds are not reproducible; a breaking minor release of any of ~15 transitive LLM SDKs breaks `main` with no code change.

**Fix:** adopt `uv` (or `pip-tools`), commit `uv.lock`, install from the lock in CI, and add Dependabot/Renovate with grouped updates.

---

## 5. P2 — Architecture and maintainability

### 5.1 31% of the codebase is unreachable

`scripts/check_reachability.py` — a genuinely good tool the project already owns — reports:

```
modules 423 | reachable 268 | UNREACHED 155
loc 146632  | UNREACHABLE 45994 (31%)
```

Including entire scientific-capability packages: `berb.reasoning` (2,757 LOC), `berb.research` (2,616), `berb.memory` (1,867), `berb.integrity` (1,073), `berb.vision` (816), `berb.knowledge` (751), `berb.self_evolve` (672), `berb.learning` (557), `berb.audit` (512), `berb.assessor` (442). The check **passes** because `.reachability-allowlist` parks it all as "revisit Q1 2027".

This is 46k LOC that is tested, linted, shipped, and maintained but never executed. Every one is either (a) a feature that was built and never wired into the pipeline, or (b) dead code. Both need resolution before 1.0 — the difference between "23-stage pipeline with deep reasoning" and "23-stage pipeline plus 46k LOC of unwired ambition" is a product-honesty question, not just a cleanup task.

**Fix:** for each parked package, decide *wire it or delete it*. No third option. Deleted code lives in git history.

### 5.2 Module sprawl

Web/API code is spread across five packages: `berb/api/`, `berb/server/`, `berb/servers/`, `berb/web/`, `berb/ui/web/`. Seven FastAPI apps (§3.3). Consolidate to one.

### 5.3 Oversized modules

| File | Lines |
|---|---|
| `berb/pipeline/stage_impls/_review_publish.py` | 3,353 |
| `berb/prompts.py` | 2,536 |
| `berb/pipeline/stage_impls/_paper_writing.py` | 2,513 |
| `berb/templates/converter.py` | 1,947 |
| `berb/config.py` | 1,659 |
| `berb/pipeline/code_agent.py` | 1,505 |
| `berb/llm/openrouter_adapter.py` | 1,498 |
| `berb/cli.py` | 1,481 |

`prompts.py` at 2,536 lines duplicates the role of `prompts.default.yaml` — prompts should live in one place, versioned as data.

### 5.4 Error handling

465 `except Exception` blocks across 170 files; 20 of them swallow silently (`pass`/`continue`) — notably `berb/server/routes/pipeline.py` (3) and `berb/dashboard/collector.py` (4). For a long-running autonomous pipeline, silent swallowing at the route layer is how a run appears to succeed while producing nothing.

### 5.5 Version drift

| Source | Version |
|---|---|
| `berb/__init__.py:9` | `1.0.0` |
| `pyproject.toml` | `1.0.0` |
| `berb/api/server.py:109` | `1.0.0` |
| `berb/server/app.py:40` | **`0.5.0`** |
| git tag | `v3.0.0` |
| `pyproject.toml` classifier | `Development Status :: 4 - Beta` |
| `README.md:14` | "Beta" |

Four different answers to "what version is this?". Pick one, derive the rest from `importlib.metadata`.

### 5.6 Repository hygiene

~25 markdown planning documents at the repo root (`BERB_IMPLEMENTATION_PROMPT_v7_FINAL.md` 112 KB, `v8_FINAL` 134 KB, `TODO.md` 71 KB, `scientist_implementation_plan.md` 96 KB, five `implementation_audit_report*.md`, …), plus a 13 MB PDF, plus duplicate scripts (`merge_to_main.bat` / `merge_to_main_FIXED.bat`, `launch-topic-approval.bat` / `-fixed.bat`, `start-webui.bat` / `.sh` / `start-api-server.py`). Move history to `docs/archive/`, keep the root to README / LICENSE / CONTRIBUTING / CHANGELOG / SECURITY / pyproject.

---

## 6. P3 — Operations and release engineering

**Deployment.** No application Dockerfile. `berb/docker/Dockerfile*` are experiment-sandbox images; `docker-compose.*.yml` are for SearXNG and Firecrawl. There is no supported way to deploy the service itself — no container, no Helm chart, no systemd unit, no deployment section in the README beyond "run `berb doctor`".

**State.** `berb/server/web_api_real.py:37` keeps jobs in a module-level `_jobs: dict`. Any real deployment (multi-worker uvicorn, restart, horizontal scale) loses all in-flight runs. The pipeline's own checkpointing is solid; the HTTP layer's is nonexistent.

**Observability.** `berb/metrics/prometheus.py` exists and `PrometheusExporter` is exported from `berb/metrics/__init__.py`, but no app mounts a `/metrics` endpoint. No OpenTelemetry, no Sentry, no structured/JSON logging. `logging.basicConfig` is called from library code — hijacking the root logger of any embedding application — in exactly three modules: `berb/server/standalone_api.py`, `berb/server/web_api.py`, `berb/server/web_api_real.py:23`. All three are legacy apps slated for deletion in Phase 0, so no separate remediation is needed. `/healthz` returns a static `{"status": "ok"}` and never checks LLM reachability, disk, or the config it was loaded with.

**Cost control.** The cascade/router machinery exists, but there is no enforced per-run budget ceiling reachable from the HTTP layer and no rate limiting (§3.5). An unauthenticated `0.0.0.0` server (§3.1) that spends money on every request is the compound risk.

**Deprecations.** `berb/server/app.py:144` uses `@app.on_event("startup")` — removed in future FastAPI. Migrate to `lifespan`. Pydantic v1-style `class Config` at `berb/llm/structured_outputs.py:178` — removed in Pydantic v3.

**Release process.** No `CHANGELOG.md` (though `pyproject.toml` advertises a Changelog URL), no `SECURITY.md`, no `CODE_OF_CONDUCT.md`, no release workflow, no PyPI publish job, no signed tags, no SBOM.

---

## 7. What is already good

Worth stating plainly, because these are the parts not to disturb:

- **README.md** — genuinely well-written, with a real "Security and Production Hardening" section and honest Beta framing.
- **`scripts/check_reachability.py`** — a dead-code gate most projects never build. It just needs teeth.
- **`berb/web/_ssrf.py`** — explicit SSRF guard for outbound fetches.
- **`berb/experiment/sandbox.py:53` / `isolation.py:477`** — secret-pattern redaction before code execution.
- **3,848 tests** with a marker taxonomy (`slow`/`e2e`/`llm`) and shared fixtures.
- **Config defaults in the dataclasses are correct** — the bug is in the parser, which makes §3.1 a small fix with large impact.
- **Pipeline checkpointing and resume** work and are tested.
- CI already runs a 2-version matrix with lint, format, and type jobs — the skeleton is right, the gates are just hollow.

---

## 8. Sequenced roadmap

### Phase 0 — Stop the bleeding (3–5 days)

1. Fix `_parse_server_config` defaults: `127.0.0.1`, `()`, and refuse non-loopback bind without `auth_token`. (§3.1)
2. Rewrite `TokenAuthMiddleware` as pure ASGI covering websocket scope; `hmac.compare_digest`; gate `/docs`. (§3.2)
3. Delete the six legacy FastAPI apps and the docs pointing at them. (§3.3)
4. Import `ClaimManifest` and `PerspectiveResult`; add regression tests that call both functions. (§4.2)
5. `ruff check --fix` + `ruff format`; get CI green.

**Exit:** `ruff`, `ruff format`, and `pytest` all pass on `main`.

### Phase 1 — Real gates (1.5 weeks)

6. Invert the mypy policy to a shrinking denylist; add `--strict` for `berb/pipeline/`, `berb/config.py`, `berb/llm/`. (§4.3)
7. Mark the e2e tests correctly and fix the stage-13 `selection_bias.json` regression. (§4.4)
8. `pytest-xdist`, split fast/slow CI jobs, target <8 min for the PR gate.
9. Adopt `uv` + commit `uv.lock`; install from lock in CI; add Dependabot. (§4.5)
10. Add `bandit`, `pip-audit`, CodeQL, and GitHub secret scanning to CI. (§3.5)

**Exit:** every CI job tells the truth about what it checked.

### Phase 2 — Sandbox and rate limits (1 week)

11. Route `berb/math/verification.py` code execution through the existing Docker sandbox or an AST-allowlist evaluator. (§3.4)
12. Add `slowapi` (or equivalent) rate limiting + per-run cost ceiling enforced at the route layer. (§6)
13. Fix `berb/mcp/transport.py` default bind. (§3.5)

### Phase 3 — Dead code decision (2 weeks)

14. For each of the 12 parked scientific packages: wire into the pipeline with an integration test, or delete. Shrink `.reachability-allowlist` to near-empty and make the gate fail on regression. (§5.1)
15. Split the four modules over 2,000 lines. Consolidate `prompts.py` into `prompts.default.yaml`. (§5.3)

**Exit:** unreachable LOC under 5%.

### Phase 4 — Operability (1.5 weeks)

16. Application `Dockerfile` + `docker-compose.yml` + documented deployment path. (§6)
17. Persist job state (SQLite or the existing checkpoint store); make the HTTP layer restart-safe and multi-worker-safe. (§6)
18. Mount `/metrics`; add OpenTelemetry tracing spans per pipeline stage; JSON structured logging. (§6) — the `basicConfig`-in-library-code problem is already resolved by Phase 0 step 3.
19. Deep `/healthz` — config validity, LLM reachability, disk headroom.
20. Migrate `on_event` → `lifespan`; migrate Pydantic `class Config` → `ConfigDict`. (§6)

### Phase 5 — Release engineering (1 week)

21. Single source of version truth via `importlib.metadata`; fix the four-way drift. (§5.5)
22. `CHANGELOG.md`, `SECURITY.md` with a disclosure policy, `CODE_OF_CONDUCT.md`.
23. Tagged-release workflow: build → test → SBOM → sign → publish to PyPI.
24. Archive the ~25 root planning docs into `docs/archive/`. (§5.6)
25. Raise the coverage floor to 70% with `berb/writing/` covered; add contract tests over the stage-artifact JSON schemas. (§4.4)

**Total: ~7–9 weeks of focused work.**

---

## 9. The one-line summary

The engineering is far ahead of the operational discipline. Berb's problem is not capability — it is that the gates meant to protect the capability (auth defaults, mypy scope, reachability allowlist, coverage floor) have each been configured to pass rather than to check.
