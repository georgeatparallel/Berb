# Open Science Desktop — research findings and what Berb should take from it

**Subject:** `github.com/ai4s-research/open-science` (v0.5.1, MIT, 1.5k stars,
187 forks, DOI 10.5281/zenodo.22136307). Read at commit fetched 2026-09-02
via shallow clone.

**Question asked:** understand its methodology, philosophy, capabilities and
functioning; propose what Berb should adopt.

**Short answer:** it is a *different kind of system* from Berb, and the naive
read ("a competitor, copy its features") is wrong. It is a desktop **workbench**
— a human sits in it and drives an agent. Berb is an unattended **pipeline**.
Berb is ahead on almost everything that makes a paper trustworthy, and behind
on exactly one thing that matters a lot: **checking whether the analysis code is
scientifically wrong, as opposed to merely broken.** Four concrete proposals at
the end, ranked. Two of them are wiring code that already exists in this repo.

---

## 1. What it actually is

Tauri 2 + React + TypeScript desktop app, Rust core (`crates/osd-core`),
bundling a pinned **OpenCode** binary as an agent sidecar. Ships macOS/Windows/
Linux installers, plus `osd` — a headless server + CLI that serves the same web
UI with no display.

| Layer | Reality |
|---|---|
| Orchestration | **None.** No stage machine, no DAG, no workflow schema. |
| Agent runtime | Bundled OpenCode sidecar, XDG-isolated, password-authed on localhost. |
| Research method | 7 "skills" = `SKILL.md` (YAML frontmatter: `name`, `description`) + optional Python helper. |
| The research loop | 4 stage-skills (`research-explorer` → `literature-survey` → `experiment-suite` → `paper-writer`) that **are not in this repo** — build-fetched from `ai4s-research/ai4s-skills` at a pinned commit. |
| Provenance | `.openscience/provenance.jsonl`, `runs.jsonl`, SQLite read-model, shadow-ref git snapshots. Real Rust, tested. |
| Verification | One `reviewer` agent + 3 deterministic gate scripts. Advisory only. |
| Export / publication | **Absent.** No manuscript build, no bundle, no archive path. |

### The orchestration finding, which is the important one

Their multi-step research is **prompt + skill-selection-by-description**. A
skill's `description` field is written as a trigger sentence ("Use whenever you
write or run scientific analysis code…") and the model decides when to invoke
it. The only automated hop in the whole app is `apps/desktop/src/lib/autoReview.ts`,
which forks a finished turn into one read-only `reviewer` turn.

`AGENTS.md:44` says "Keep the artifact schema and workflow templates stable and
versioned." Neither exists. "Workflow templates" resolves to
`apps/desktop/src/components/thread/WorkflowStarters.tsx` — four hardcoded
prompt strings.

**Berb's 23-stage pipeline with typed contracts, per-stage artifacts, gates and
resumability is a categorically stronger architecture.** Nothing in
open-science should tempt a move toward theirs.

### Six of thirteen core skills are empty directories

`.gitkeep` only, no `SKILL.md`, silently skipped at deploy: `citation-reviewer`,
`figure-provenance`, `reproducible-research`, `literature-review`,
`bibliometric-analysis`, `paper-to-report`. Their `reviewer` agent instructs the
model to use an `integrity-auditor` skill that is not in the repo. Both example
projects (`examples/bci-trends/`, `examples/climate-trends/`) are empty
directory skeletons — bci-trends is `.gitkeep` in every content folder.

So: the literature and paper-writing half of their claimed pipeline is either
vendored out or unbuilt. **Berb's `berb/literature/` alone (citation_graph 35.7K,
evidence_map 25.8K, verify 32.2K, novelty, section_analysis, structured_notes,
retraction, paper_mill) has no counterpart there at all.**

---

## 2. Their philosophy — the part worth stealing

This is where the repo earns its stars. Three ideas, stated crisply.

### 2.1 "Runs" ≠ "right"

`docs/REQUIREMENTS.md:146-148` frames it as the largest gap in their own spec:

> Every field's top pain is code that **executes cleanly but is scientifically
> wrong** — quoting a chemist: *"in science, you can't have that 1%"*; a
> neuroscientist: *"It makes it possible to produce wrong results faster than
> ever before"*.

Their claimed moat is not the model (`REQUIREMENTS.md:35-45`): it is a research
agent runtime, a reproducible artifact system, domain connectors, and
**domain-correctness gates**.

### 2.2 Traceability, never truth

`runtime/opencode-profile/agent/reviewer.md:21-22`:

> You verify **traceability and internal consistency**, never truth. Never state
> or imply that the work is correct, sound, or error-free.

Every gate's output block carries a mandatory note: *"Absence of findings is not
a guarantee of correctness."* `traceability-review/SKILL.md:85` forbids the
model from ever claiming the document has no errors. Marketing guidance
(`REQUIREMENTS.md:713-716`) bans the phrases "zero hallucination" and "replaces
your specialized tools".

### 2.3 Execute, don't interpret

`stats-integrity/SKILL.md:14-15` quotes Pepinsky verbatim:

> use the agent for tasks that follow rules; do not use it for tasks that
> generate answers, arguments, or interpretations.

Concretely: *"Say 'X is associated with Y', not 'X causes / drives / leads to /
increases Y', unless the design (RCT, IV, DiD, RDD, panel FE…) supports it —
and then name the design."*

### The honest-documentation ethic

Worth noting because it is rare: `REQUIREMENTS.md` P0-7 keeps a self-audit
recording that they shipped an approval *UI* while the bundled OpenCode binary's
embedded default was `{"*":"allow"}`, so bash and dependency installs ran
unprompted. They left the contradiction in the doc with a strikethrough and a
dated fix rather than editing it away.

---

## 3. Their four deterministic gates (the actual transferable artifacts)

All stdlib-only, offline, fast, and — critically — **they analyse the code the
agent actually wrote, not the model's recollection of rules.**

| Gate | Size | What it catches |
|---|---|---|
| `domain-check` | 732 loc | units/dimensions, lat-lon Euclidean distance, genomic coord off-by-one and strand, impossible SMILES valence, uncorrected multiple comparisons, `.mean()` on a categorical code |
| `stats-integrity` | 309 loc | causal language over associational design, HARKing (a predictor the code runs that the preregistration never named), missing seed |
| `large-file` | 617 loc | probes a big data file to a compact schema/shape/sample "memory pointer" instead of loading it |
| `traceability-review` | + `pdf_extract.py` | DOI/arXiv/PMID resolution, untraceable numbers, figure-vs-code staleness from `provenance.jsonl` timestamps |

`domain-check`'s architecture is clean and directly portable:

```python
# domain_check.py:622
VALIDATORS = [check_physics, check_earth, check_biology, check_chemistry, check_social]
```

Each is `check_<field>(ctx) -> list[Finding]`, walking a Python AST (regex for
R). Adding a discipline is one function plus one list append. RDKit is used as
the authoritative judge for SMILES when installed, with a stdlib bond-counter
fallback. Rules deliberately favour precision — an unrecognized unit, a single
significance test, or a `groupby('gender')` key stays silent.

`large-file` carries a measured justification (`REQUIREMENTS.md:212-214`): the
raw approach consumed 20M+ tokens and **failed**; the memory-pointer approach
used 1,234 tokens and **succeeded**.

### Where their gates are weak

Findings render as **dismissible cards**. Nothing blocks. Auto-review is off by
default and excludes `bash` from its mutating-tool set, so *a run that writes a
report never triggers a review at all*. Their citation resolution is a `curl`
the **LLM** issues — there is no HTTP client in the app for it — and findings
are never persisted to any store.

---

## 4. Honest scorecard

### Berb is ahead

| Axis | Berb | Open Science Desktop |
|---|---|---|
| Orchestration | 23 typed stages, contracts, gates, resume | none — prompt + skill descriptions |
| Numeric anti-fabrication | `pipeline/verified_registry.py` whitelists every paper number against `experiment_summary.json`; wired into Stage 17 + 22 | LLM warns about "untraceable numbers" |
| Claim → evidence | `integrity/{claims,evidence,anchors,registry}.py` — real schema, `content_hash`, quote/page/section anchors | **a prompt.** No claim manifest, no evidence graph, no persisted state |
| Citation verification | `literature/verify.py` (32K), `citation_verification.py`, Crossref client in code | model-issued `curl` |
| Retraction / paper-mill | `literature/retraction.py`, `paper_mill.py`, `tortured_phrases.yaml` | absent |
| Literature depth | 29 modules incl. citation graph, evidence map, novelty | 5 MCP connectors |
| Peer review | 5 reviewers + Area Chair ensemble | 1 reviewer agent, ≤8 findings |
| Enforcement | `Severity.BLOCK` + `gates(findings, mode)` can fail a stage | advisory cards only |
| Export | `export/multi_format.py`, Overleaf | **none** |

### Open Science Desktop is ahead

| Axis | Gap in Berb |
|---|---|
| **Scientific-correctness gates on analysis code** | `experiment/validator.py` checks syntax, security, imports, style. **Nothing checks whether the science is right.** |
| **Statistical-interpretation discipline** | no association→causation guard, no seed check, no hypothesis lock |
| **Artifact provenance ledger** | `berb/audit/reproducibility.py` writes environment.yml/Dockerfile/run_all.sh — **but it is parked dead code** |
| Large-file context discipline | no memory-pointer probe found in `stage_impls/` |
| Epistemic output contract | Berb's review ensemble scores; it does not disclaim |

### Their reproducibility layer, and its real flaws

Genuinely engineered: append-only JSONL, path-escape rejection, corrupt-line
tolerance, content-addressed `pip freeze` lockfiles, a disposable
watermark-synced SQLite read-model, shadow-ref git that provably never touches
the user's branches or index. But:

- **Outputs are inferred by mtime window**, not traced. A concurrent unrelated
  write is attributed to the run.
- **What counts as a run is a regex allowlist** of 13 interpreter names. A
  compiled binary or a `uv run` leaves no record.
- **Hashing is 64-bit `DefaultHasher`** (non-cryptographic, trivially
  collidable, not guaranteed stable across Rust toolchains) for code version,
  run outputs, logs and env lockfiles.
- **Env capture is Python-only.** No seed, no container digest, and **no git SHA
  cross-linking provenance to the snapshot chain** — the two histories correlate
  only by wall-clock.
- Provenance is written by the desktop client, so `osd server` headless
  **records none of it**.

Do not copy the mechanism. Copy the *idea* — Berb's `EvidenceType` already has
`METRIC`, `STATISTICAL_TEST`, `RUN_CONFIG`, `FIGURE`, `SOURCE_SNIPPET` with
`content_hash`, which is a richer schema than their `ProvenanceRecord`.

---

## 5. Proposals, ranked

### P1 — Domain-correctness checks in the existing validate→repair loop

**The single highest-value item.** Berb generates analysis code and never asks
whether it is scientifically sound.

The seam already exists and is already wired.
`berb/pipeline/stage_impls/_code_generation.py:776` calls `validate_code(code)`,
and on failure runs an LLM repair loop (`:778-800`, `max_repair` attempts,
errors-only sent to the model). `berb/experiment/validator.py` already parses
the AST and already has the finding type:

```python
@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    category: str  # "syntax" | "security" | "import" | "style"
```

**Proposal:** add `category="science"` checks to that module. Port
`domain_check.py`'s validator shape — `check_<field>(tree, ctx) -> list[ValidationIssue]`
behind one `VALIDATORS` list. Start with the two that are domain-agnostic and
hit Berb's actual ML/physics/economics profile hardest:

- **multiple comparisons** — significance test in a loop or ≥3 times with no
  FDR/Bonferroni anywhere
- **units/dimensions** — add/subtract/compare of differently-suffixed quantities
  (`t_seconds + d_meters`), trig on a degree-valued angle

Then `check_earth` (CRS) and `check_biology` (coords/strand) only if a domain
profile needs them. `berb/domains/detector.py` already classifies the subject
domain, so the relevant validator set can be selected rather than run wholesale.

**Why Berb's version is strictly better than theirs:** their finding is a
dismissible card. Berb's would enter an *existing automatic repair loop* — the
LLM gets told to fix scientifically-wrong code before it ever runs. They cannot
do that; they have no pipeline to do it in.

Effort: one file touched, one new module, reuses the wired loop. No new
infrastructure.

### P2 — Un-park `berb/audit/reproducibility.py`

The module is already written. `.reachability-allowlist:114`:

> `berb.audit` — Parked, revisit 2026-12-01 (strike 1). Un-park: a
> reproducibility-package deliverable; `pipeline/packaging.py` collects
> artifacts but emits no environment.yml/Dockerfile.

`ReproducibilityPackage` already specifies environment.yml, Dockerfile,
`run_all.sh`, `audit_trail.json`, `trace.jsonl`, `cost_report.json`,
`decision_log.md`. That is a **more complete** reproducibility deliverable than
open-science ships, and it is sitting dead.

**Proposal:** call it from `pipeline/packaging.py:package_deliverables()`.
Closes an allowlist strike, delivers the headline capability the comparison
repo is admired for, and writes no new logic.

Add one thing they lack and Berb should not: **the git SHA and the RNG seed** in
the package metadata. Their omission of both is a named flaw above.

### P3 — Statistical-interpretation guards

Two cheap checks, one genuinely novel to Berb.

**(a) Association → causation.** At Stage 14/17, flag causal verbs ("causes",
"drives", "leads to", "increases") applied to a result whose design does not
support them. Berb already has the finding vocabulary — add
`CheckId.CAUSAL_OVERCLAIM` to `berb/integrity/findings.py:55` and it flows
through `gates()` for free. Note this is *adjacent to but not the same as* the
W6 Layer B `CLAIM_STRENGTH_DRIFT` check, which only compares draft-vs-revision;
this catches an overclaim that was there from the first draft.

**(b) Hypothesis lock (HARKing guard) — Berb can do this better than they can.**
Their check hunts for a `preregistration.md` that may not exist. **Berb has
Stage 8 hypothesis generation with a falsification critic already producing the
artifact.** Compare the Stage-8 hypothesis against what Stage 14 actually
reports; flag analyses that appear in the results but were never hypothesised.
Berb's staged artifact chain makes this near-free; a chat workbench cannot do it
at all.

Berb currently has no preregistration concept anywhere (verified: zero matches
for `prereg|analysis_plan|HARK` across `berb/`).

### P4 — Adopt the epistemic output contract

Cheap, zero-risk, and it is the most defensible thing in their repo.

- Every integrity/review artifact Berb emits should carry the equivalent of
  *"Absence of findings is not a guarantee of correctness."*
- Berb's review ensemble should not imply a paper is correct — only that stated
  checks passed.

One string constant in `berb/integrity/findings.py` plus its use at the
artifact-writing sites.

### Considered and rejected

- **Their provenance JSONL / run records.** Berb's `ExperimentJournal`
  (append-only, replayable attempt tree) plus `VerifiedRegistry` already cover
  the load-bearing part, and their mtime-inference and 64-bit hashing are
  weaknesses, not models.
- **Their skill format.** Berb already has `berb/skills/` with an
  agentskills.io-compatible schema and stage mapping. Theirs is strictly less
  capable (two frontmatter fields, no stage binding).
- **MCP connector catalogue.** Berb has native arXiv/OpenAlex/S2/Crossref
  clients. The only genuinely absent ones are *data* sources (Materials Project,
  FRED, Open-Meteo, USGS, ClinicalTrials.gov) — worth revisiting only if a
  domain profile needs real external data for experiments.
- **`large-file` memory-pointer probe.** Real idea, measured 16,000× token
  saving, but I did not find evidence Berb currently loads raw data files into
  LLM context. Worth an audit before building anything.
- **Their desktop/Tauri shell, kernels, ACP, browser control.** Different
  product shape. Berb is a pipeline.

---

## 6. Verification notes

Read directly by me: repo metadata, `README.md`, `AGENTS.md`, `CITATION.cff`,
`runtime/skills/core/` listing, `domain-check/SKILL.md` and its `VALIDATORS`
registry; on the Berb side `experiment/validator.py`, the
`_code_generation.py:770-800` repair loop, `integrity/findings.py`,
`integrity/evidence.py`, `pipeline/verified_registry.py`, `audit/reproducibility.py`,
`experiment/journal.py`, `domains/detector.py`, `.reachability-allowlist`.

Reported by delegated readers (spot-checked, not independently re-read in full):
the Rust provenance/runs/git-snapshot internals, `docs/REQUIREMENTS.md` and
`docs/PRD.md` passages, the SDK surface, and the empty-skill inventory.

Corrections to earlier session claims: none required. `berb/vision/` is an empty
directory with no Python files, so the earlier documentation fix stands (the dir
itself could be deleted). `berb/domains/detector.py` classifies subject domain
and experiment paradigm and contains zero study-design terms, so the earlier
W8.1 conclusion — that PRISMA/CONSORT/STROBE selection has no detector — also
stands.
