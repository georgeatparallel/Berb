# Research: can `create_agentic_sandbox` be wired safely?

**Date:** 2026-09-02
**Trigger:** Pass 1 of `tasks/defect_hunt_plan.md` (finding D2) triaged
`berb/experiment/agentic_sandbox.py` + `factory.create_agentic_sandbox` as DEAD
and deferred the wire/park/delete decision. This is that decision's evidence.

**Scope:** whether this specific factory can be given a caller without
regressing the sandbox trust boundary that Pass 1 just repaired. Not a general
review of agentic experiment execution as a capability.

Epistemic tags: `[VF]` verified by reading the code or executing it, `[INF]`
inference from verified facts, `[HYP]` hypothesis, `[UNK]` insufficient
evidence.

---

## 1. What is actually there

`[VF]` `berb/experiment/agentic_sandbox.py` (360 loc) defines `AgenticSandbox`,
which starts a long-lived Docker container, `docker exec`s a coding-agent CLI
(`claude -p …` by default) inside it with the run workspace bind-mounted
read-write, then collects output files and metrics.

`[VF]` `berb/experiment/factory.py::create_agentic_sandbox` (lines 114-134)
checks Docker availability and returns that object.

`[VF]` `AgenticConfig` (`berb/config.py:471-488`) is parsed and reachable:
`_parse_agentic_config` is called from the config parser at line 1457, and
`"agentic"` is an accepted value in `EXPERIMENT_MODES` (`config.py:96-103`).

`[VF]` `create_agentic_sandbox` has **never had a caller**.
`git log -S "create_agentic_sandbox"` returns exactly two commits: `39e5b82`
(the commit that added the file) and `895777e` (Pass 1's report, which only
names it in prose). It was born dead.

`[VF]` There is no test file for it (`ls tests/ | grep -i agentic` → empty) and
no entry for it in `.reachability-allowlist`.

---

## 2. Three defects found while answering the question

### A1 — `experiment.mode: agentic` is an accepted config value that crashes the run

**Severity: HIGH (availability). Confirmed by execution.**

`"agentic"` passes config validation (`config.py:1314` checks membership in
`EXPERIMENT_MODES`, which contains it). Stage 12 (`_execution.py:150`) reads
`config.experiment.mode`, does not match `"sandbox"`/`"docker"`/`"simulated"`,
and falls into the `else:` branch at line 369, which constructs
`ExperimentRunner`, whose `__init__` (`experiment/runner.py:113`) calls
`create_sandbox(config, …)` unconditionally. `create_sandbox` has no `agentic`
branch and reaches its terminal raise at `factory.py:109`.

Reproduced directly:

```
$ python -c "import dataclasses; from berb.config import ExperimentConfig; \
  from berb.experiment.factory import create_sandbox; from pathlib import Path; \
  create_sandbox(dataclasses.replace(ExperimentConfig(), mode='agentic'), Path('/tmp/x'))"
RuntimeError: Unsupported experiment mode for create_sandbox(): agentic
```

`[INF]` A user who sets the documented-looking `mode: agentic` gets a clean
config load, eleven stages of successful work (scoping, literature, synthesis,
design, code generation), and *then* an unhandled `RuntimeError` at Stage 12 —
after the expensive part of the pipeline has already been paid for. This is
strictly worse than rejecting the mode at load time.

This defect exists **independently of the wiring decision** and should be fixed
either way (see §5).

### A2 — the container is unhardened relative to `DockerSandbox`

**Severity: HIGH if wired, N/A while dead.**

`_start_container` (`agentic_sandbox.py:178-215`) builds the `docker run`
argv. Comparing against `DockerSandbox._build_command`
(`docker_sandbox.py:485-568`), which is the in-repo reference for how this
project runs untrusted code in a container:

| Control | `DockerSandbox` | `AgenticSandbox` |
|---|---|---|
| `--user UID:GID` | yes, on every network policy | **absent** |
| `--memory` | yes | yes |
| `--cpus` | yes when `cpu_limit > 0` | **absent** (no such config field) |
| `--shm-size` | yes | absent |
| `--network none` | when policy `none` | when policy `none` |
| `setup_only` / `pip_only` staged egress (iptables) | yes | **absent** — only `none` or unrestricted |
| default network policy | `setup_only` (see config) | **`full`** |
| `--cap-drop` / `--security-opt=no-new-privileges` / `--pids-limit` / `--read-only` | absent in both | absent in both |

`[VF]` `grep -- "--user\|--cap-drop\|--security-opt\|--pids-limit\|--cpus\|--read-only\|--tmpfs" berb/experiment/agentic_sandbox.py` → no matches.

`[INF]` Two concrete consequences of the missing `--user`, beyond the security
framing: (a) the agent runs as the image's default user, which is root for
most images, and (b) every artifact it writes into the bind-mounted workspace
is **root-owned on the host**, so the host-side pipeline that later reads,
copies, or cleans that run directory can fail with `PermissionError`.
`DockerSandbox` carries `--user` specifically to avoid this, and has an
accompanying bug-fix comment (`BUG-R52-03`) about the `HOME` fallout — evidence
that this failure mode was already hit once in this repo.

### A3 — the agent has no credentials, so the happy path cannot work

**Severity: HIGH (functional). Confirmed by reading argv construction.**

`[VF]` `_start_container` passes **no** `-e` flags, and `_docker_exec`
(lines 217-234) runs `docker exec <container> bash -c <cmd>` with no `-e`
either. Docker does not forward the host environment into a container unless
explicitly told to.

`[VF]` The default `agent_cli` is `"claude"` and the default
`agent_install_cmd` is `"npm install -g @anthropic-ai/claude-code"`.

`[INF]` That CLI needs an API credential to do anything. With no `-e` and no
credential-file mount, the very first `docker exec` of the agent would fail to
authenticate. So `AgenticSandbox` as written is not merely unwired — its
primary code path has never been able to succeed. That is consistent with it
having no tests and no caller: nothing has ever exercised it.

`[INF]` This is also the crux of the safety question, because the obvious fix
(`-e ANTHROPIC_API_KEY=…`) is the single most dangerous change available here.
See §3.

---

## 3. Threat model, if it were wired

**Assumption stated up front:** the code the experiment runs is *not* trusted.
That is the premise the whole `berb/experiment/` boundary is built on —
`check_code_security` exists because generated experiment code is treated as
adversarial input, and Pass 1 was filed precisely because two backends skipped
it.

`[VF]` The agent's prompt in an agentic Stage 12 would be derived from upstream
pipeline artifacts. Stages 3-6 ingest arXiv/OpenAlex/Semantic Scholar abstracts
and PDF text; those flow into synthesis and design artifacts.

`[INF]` Therefore the prompt handed to a shell-capable agent contains text
authored by third parties. Prompt injection is not a hypothetical channel here;
it is the normal data flow. An injected instruction reaching an agent that has
(a) a shell, (b) unrestricted network by default, and (c) the workspace mounted
read-write, is an exfiltration primitive.

`[VF] + [INF]` Crucially, `check_code_security` **cannot** be the mitigation.
It is an AST scan of a Python source string. An agent with `bash` has no source
string to scan — it types commands interactively. The documented "single
enforcement point for every sandbox backend" invariant in `sandbox.py` simply
does not extend to this backend, and any wiring must say so explicitly rather
than leave a reader assuming the Pass 1 guarantee still holds.

`[INF]` So the container *is* the entire trust boundary, and A2 says that
boundary is currently weaker than the one used for merely-generated code — an
inversion, since the agentic backend is strictly more capable.

`[INF]` Adding `-e ANTHROPIC_API_KEY` to fix A3 puts a long-lived, account-wide
credential inside that boundary. An injected agent could exfiltrate it in one
`curl`. This is a materially different exposure from anything else in
`berb/experiment/`: the other backends never hold a credential at all.

`[UNK]` Whether the `--allowedTools 'Bash(*)' 'Read' 'Write' 'Edit' 'Glob'
'Grep'` string at `agentic_sandbox.py:251` actually constrains anything. I have
not verified that CLI's flag semantics against its documentation, and I will
not assert them from memory. `Bash(*)` reads as "all shell commands permitted"
regardless.

---

## 4. Options

### Option 1 — Delete `agentic_sandbox.py` + `create_agentic_sandbox`; reject `agentic` at config load

- **Assumptions:** the capability is not currently needed; the seam is occupied.
- **Cost:** ~380 loc deleted, one config mode removed. Loses a capability that
  has never worked.
- **Risk:** low. Nothing calls it; nothing can regress.
- **Precedent:** this is exactly the D-09 disposition of
  `experiment/code_agent.py` on 2026-09-02 — 836 loc, no importer, seam already
  occupied by `pipeline/code_agent.py`. Same three criteria hold here.
- **Seam check `[VF]`:** the "iteratively write and repair experiment code"
  seam is already occupied by `pipeline/code_agent.py` (blueprint → sequential
  generation → hard validation → execution-in-the-loop) and
  `pipeline/experiment_repair.py`; the "try several candidate solutions" seam is
  occupied by `experiment/search/` (Stage 12, live). The marginal capability
  `AgenticSandbox` adds over those is "the agent gets a real shell" — which is
  precisely the part that breaks the trust boundary.

### Option 2 — Park it in `.reachability-allowlist`, fix only A1

- **Assumptions:** the capability may be wanted later; the decision is worth
  deferring but the crash is not.
- **Cost:** minimal now. A1 fixed by removing `"agentic"` from
  `EXPERIMENT_MODES` (or adding an explicit "mode recognised but not
  implemented" rejection in `create_sandbox`).
- **Risk:** low, but it books 380 loc of debt on the 90-day PARK clock and
  leaves a file whose primary path has never executed.
- **Honest note:** PARK is for code that is correct-but-unreachable. This code
  is unreachable *and* non-functional (A3). Parking it misrepresents its state
  unless the allowlist entry says so.

### Option 3 — Harden and wire it as an explicitly opt-in backend

Preconditions, all of which are load-bearing:

1. **A2:** add `--user`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`,
   `--pids-limit`, `--cpus`; change the default `network_policy` from `full` to
   the egress-restricted policy `DockerSandbox` already implements.
2. **A3, the hard one:** never `-e` a long-lived key. The only defensible shapes
   are a short-lived scoped token, or an egress allowlist that permits the model
   endpoint and nothing else *and* is enforced outside the container (the agent
   has root inside it, so in-container iptables is not a control against the
   agent itself).
3. **Adapter:** `AgenticSandbox` does not satisfy `SandboxProtocol`. Its entry
   point is `run_agent_session(prompt, workspace, *, timeout_sec)`, not
   `run(code)` / `run_project(dir)`. `create_sandbox`'s return type is
   `SandboxProtocol`, so wiring needs either a new dispatch path in Stage 12 or
   a protocol-shaped adapter.
4. **Documentation:** an explicit statement that the `check_code_security`
   invariant does not apply to this backend and why.
5. **Tests:** a security-gate suite equivalent to
   `tests/test_remote_sandbox_security_gate.py`, asserting the hardening flags
   are present in the argv and that no credential env var is passed.

- **Cost:** substantial — new config fields, a new dispatch path, an egress
  control that does not exist in this repo today, and a test suite.
- **Risk:** high. Precondition 2 has no in-repo solution; getting it wrong
  yields a credentialed, networked, root shell driven by partly-third-party text.
- **`[UNK]`:** whether the project wants this capability at all. That is a
  product decision, not a defect fix.

### Option 4 — Replace it with an in-process tool loop over `DockerSandbox`

Keep the *capability* (an agent that iterates against a real execution
environment), drop the *mechanism* (an agent CLI living inside the container).
The LLM client stays on the host, where the credential already is; only its tool
calls execute in a `DockerSandbox` that is already hardened.

- **Advantage:** eliminates A3 entirely — no credential ever crosses the
  boundary — and inherits A2's fixes for free.
- **`[VF]` The obvious donor is not usable.** `berb/experiment/react_agent.py`
  (389 loc) is the right *shape* but is non-functional: `_reason`, `_act` and
  `_analyze_error` all call `get_llm_client` from `berb.llm.client`, which does
  not exist (`grep -n "def get_llm_client" berb/llm/client.py` → no match), and
  `_observe` imports `LocalSandbox` from `berb.experiment.sandbox` and calls
  `sandbox.execute(code, timeout=300)` — neither the class nor the method
  exists. The module imports cleanly only because all four are function-local
  imports; the first ReAct iteration would raise `ImportError`. So Option 4 is a
  greenfield build, not a rewiring.
- **Cost:** highest of the four.
- **Note:** this also means `react_agent.py` is a second dead-and-broken module,
  not merely "awaiting wiring" as `tasks/defect_hunt_plan.md` §7 currently
  records. That entry should be corrected.

---

## 5. Recommendation

**Option 1 (delete), with A1 fixed as a separate, independently-justified
change.**

Reasoning:

1. The three criteria that justified deleting `experiment/code_agent.py` under
   D-09 all hold here, and one more besides: this module's primary path has
   never been able to run (A3), so deletion cannot regress working behaviour.
2. Wiring it (Option 3) requires solving credential-scoping and egress control
   that this repo has no mechanism for. That is a real project, and it should be
   started from a decision that the capability is wanted — not from the fact
   that 380 loc of it already happen to exist.
3. Keeping it (Option 2) preserves a file that would need a near-total rewrite
   before it could be wired, so the sunk code is not actually a head start.
4. A1 must be fixed regardless of 1-3. Even under Option 3, `agentic` should
   fail at config-load time until the backend exists.

**Fallback if the capability is wanted:** Option 3, gated on preconditions 1-5
being met *before* any caller is added, and with precondition 2 designed first,
since it is the one with no existing answer.

**Not recommended:** wiring `create_agentic_sandbox` as-is under any flag. It
would put the weakest container in the repo around the most capable executor in
the repo, and reintroduce, in a form an AST scan cannot reach, exactly the class
of gap Pass 1 closed.

---

## 6. Coverage statement

**Audited:** `agentic_sandbox.py` (all 360 loc), `factory.py`
(`create_sandbox` + `create_agentic_sandbox`), `AgenticConfig` and its parser,
the Stage 12 mode-dispatch path in `_execution.py`, `experiment/runner.py`'s
sandbox construction, `DockerSandbox._build_command`'s hardening flags for
comparison, and `react_agent.py` (as a candidate donor for Option 4).

**Not audited:** the agent-CLI flag semantics referenced in `[UNK]` above;
`AgenticSandbox`'s result-collection helpers (`_collect_outputs`,
`_parse_result_metrics`, `_count_agent_steps`) beyond confirming they are
reachable only from the dead path; whether an egress-allowlist mechanism exists
anywhere else in the deployment environment outside this repo.

**Clean-claim scope:** the three defects A1-A3 are the defects found in the
audited surface under the trust-boundary and functional-correctness classes.
This is not a claim that the audited files are free of defects in other classes.

**Confidence:** A1 high (executed). A2 high (argv read directly, compared
against the in-repo reference). A3 high on the mechanism (no `-e` flag exists),
moderate on the consequence (`[INF]` that the CLI requires a credential —
asserted from the absence of any other credential channel, not from testing that
CLI). The recommendation is a judgement call, not a verified fact, and turns on
a product question (§4 Option 3 `[UNK]`) that has not been put to the user.
