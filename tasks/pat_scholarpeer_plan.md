# Berb — PAT + ScholarPeer Integration Plan

Generated: 2026-08-09
Sources:
- *Towards Automating Scientific Review with Google's Paper Assistant Tool* (Jayaram et al., arXiv:2606.28277)
- *ScholarPeer: A Multi-Agent Framework for Automated Peer Review* (Goyal et al., arXiv:2601.22638v2)

Every code claim below carries a `file:line` reference. Items marked
**[verified]** were read directly during planning; items marked **[reported]**
come from subagent code reads and should be re-confirmed at implementation time
(they were consistent across independent agents, but line numbers drift).

---

## STATUS LEGEND
- [ ] Not started
- [~] In progress
- [x] Complete

**Implementation status (2026-08-10): all 15 in-scope items complete** (P0-01
through P3-05). P3-02 (extended-thinking passthrough) was deliberately
skipped per its own stated condition — "do not start before P3-01 proves the
need" — P3-01 shipped as a `max_tokens`-only budget approximation and no
ceiling has yet been observed. §8's open questions were resolved during
implementation:
1. **P1-03 weighting** — implemented as an independent veto: ensemble
   REJECT/STRONG_REJECT consensus vetoes the quality gate, capped at one
   veto per run (`ensemble_veto_used.json`), score-only path untouched.
2. **P0-03 threshold** — implemented as stated: `hallucinated > 0` blocks
   export, zero tolerance.
3. **P2-01 scope** — kept the LLM-invented-candidates fallback path (P0-04's
   stage-5 gate already catches it before publication); no
   `--allow-synthetic-corpus` flag was added — not needed since the gate
   already provides the escape valve for offline dev (run just fails
   clearly instead of silently degrading).
4. **P3-01 dimension** — reused `TECHNICAL_QUALITY`, did not extend
   `ReviewDimension`.
5. **Stage 20 criticality** — left `QUALITY_GATE` in `NONCRITICAL_STAGES` as
   found; the P1-03 veto is a separate, additive check that fires
   regardless of that flag.

~90 new tests added across 12 new test files plus additions to 6 existing
ones. Full unit suite (`pytest tests/ -m "not slow and not e2e and not llm"`)
green throughout — see commit history for exact counts per wave.

---

## 0. Framing — why these two papers, and why the naive port is wrong

### 0.1 What each paper actually contributes

**PAT** is an inference-scaling pipeline for *internal* rigor: segment the
manuscript, allocate compute per segment complexity (Light/Medium/High thinking
tracks), run deep review agents that each focus on one segment but see the whole
paper, then synthesize with dedup, severity ranking, and search grounding.
Headline result: 55.2% → 89.7% recall on math/proof errors (SPOT benchmark
Math/CS equation-and-proof subset, 26 papers / 29 errors). Deployed
pre-submission at STOC and ICML across 4,700+ submissions; 31% of ICML
respondents ran *new experiments* because of its feedback.

**ScholarPeer** is a multi-agent pipeline for *external* contextualization:
a summary agent compresses the paper into a structured (claims, method,
evidence) triple; a literature expansion agent does k=3 gap-driven search rounds
constrained to top-tier venues with a publication cutoff; a historian compresses
retrieved work into a chronological domain narrative; a baseline scout
adversarially hunts omitted SOTA competitors; a multi-aspect Q&A engine
interrogates the paper; a generator synthesizes conditioned on venue guidelines.
Ablations: **Q&A −26%**, summary −10%, baseline scout −9%, literature −6%,
historian −4%. Saturation points: k=3 expansion rounds, N_QA=10 questions
(15 is *worse* — context dilution).

**They are complementary, not competing.** ScholarPeer explicitly concedes it
"prioritizes external verification over internal logic checks" and loses to
AI Scientist v2 on catching internal inconsistencies such as mathematically
impossible probability ratios (ScholarPeer Fig. 4). PAT is precisely that
missing internal-rigor capability. Berb currently has neither.

### 0.2 The inversion that governs this entire plan

Both papers **review manuscripts humans already wrote**. Berb **generates**
them. Every signal these papers produce as a *critique* is a signal Berb can act
on *while it is still cheap to fix*.

| Signal | Paper's use (post-hoc) | Berb's opportunity (in-flight) |
|---|---|---|
| Omitted SOTA baselines | Tell the author, after the paper is written | Stage 9 `EXPERIMENT_DESIGN` — just **include** the baseline before running anything |
| Unsupported numeric claim | Flag it in the review | Stage 17 — the run data is on disk; check the number against it |
| Hallucinated citation | Detect and warn | Never emit one: constrain drafting to the retrieved corpus |
| Weak hypothesis | Reviewer weakness bullet | Stage 8 — repair the hypothesis before designing an experiment for it |

**Design rule for this plan:** prefer moving a mechanism upstream to where its
output changes behaviour over bolting it on as a terminal reviewer. A critique
produced at stage 22 changes nothing — see §1.1.

### 0.3 Roles taxonomy (PAT §4) — where Berb sits

PAT proposes four roles: Tool for Authors → Tool for Reviewers → Supporting
Reviewer → Total Automation. Berb is not on this ladder: it is the *author*, and
its internal review ensemble is a self-check. The useful transfer is not the
taxonomy itself but its underlying warning — **AI-generated review text that
nobody validates and nothing acts on is worse than no review**, because it
manufactures false assurance. §1.1 shows Berb currently does exactly that.

---

## 1. Ground truth — corrections to the documented architecture

Documentation in `CLAUDE.md` and `docs/CODEBASE_MIND_MAP.md` overstates what is
wired. Confirm these before building on top of them.

### 1.1 The "5-reviewer + Area Chair peer review ensemble" is not a gate **[verified]**

`CLAUDE.md` lists `berb/review/` as wired, and the mind map (§13) presents it as
the peer-review subsystem. In reality `AutomatedReviewerEnsemble` has exactly
one call site: `berb/pipeline/stage_impls/_review_publish.py:2772-2801`, inside
`_execute_export_publish` (stage **22**, `_review_publish.py:1825`). It is:

- guarded by `if _pdf_path.exists() and llm is not None` — skipped with no PDF;
- wrapped in a bare `except` logged at **debug** level (`:2800-2801`);
- run on the already-exported paper;
- written to `ensemble_review.md` and **read by nothing**.

Stage 18 `PEER_REVIEW` (`_review_publish.py:147-224`) is a *separate* inline LLM
call ("simulate ≥2 reviewer perspectives", `prompts.default.yaml:281`,
`max_tokens: 8192`) that has nothing to do with the ensemble.

**Consequence:** Berb's flagship review subsystem is a decorative artifact
generator. Any PAT/ScholarPeer improvement to the ensemble is worthless until
its output is consumed by something. **P1-03 fixes this and gates most of the
rest of the plan.**

### 1.2 `claim_manifest.json` is write-only **[reported]**

Built by `_build_draft_claim_manifest` (`_paper_writing.py:2285,2305-2339`),
written to `stage-17/claim_manifest.json`. Repo-wide grep for
`claim_manifest|ClaimManifest` hits 6 files; `ClaimManifest.load()` is **never
called** anywhere in `berb/`. It is also not listed in the stage's
`StageResult.artifacts`.

Berb already produces ScholarPeer's summary-agent output (Ŝ) and throws it away.

### 1.3 `evidence_registry.json` has an inverted producer/consumer **[reported]**

- **Written** at `_review_publish.py:647`, inside `_execute_quality_gate` — stage **20**.
- **Read** at `_paper_writing.py:2322` — stage **17**.

Stage 17 runs before stage 20. On any first pass the file does not exist,
`VerifiedEvidenceRegistry.load()` silently returns an empty registry, and
**every numeric claim in the manifest is recorded as unsupported/not_checked**.
It only populates on a re-run or `--from-stage` restart into a run dir that
already reached stage 20. This is a genuine bug, not a design choice —
`from_run_dir` only reads `experiment_summary.json` (stage 14), so nothing
forces it to be built at stage 20.

### 1.4 Citations are generate-then-verify, with an institutionalised escape hatch **[reported]**

Three hallucination surfaces:

1. `_literature.py:498-514` — when API search returns nothing, the LLM
   **invents the entire candidate set**; `_literature.py:599-643` synthesizes
   BibTeX for it. `search_meta.json` records `"real_search": false`
   (`_literature.py:661`) and **nothing downstream gates on that flag**.
2. `_paper_writing.py:2147-2171` — drafting is constrained by prompt text only
   ("Do NOT invent any references"). No constrained decoding, no key masking;
   and `citation_instruction = ""` (`:2093`) when `candidates.jsonl` is missing,
   leaving the model entirely unconstrained.
3. `_review_publish.py:1488,2311-2316` — `_resolve_missing_citations` takes
   LLM-invented cite keys, searches for a plausible match, and **appends the
   match to `references.bib`**. Hallucination is not merely tolerated, it is
   repaired into legitimacy.

ScholarPeer's design is the inverse: retrieve-only, never generate. Berb cannot
adopt that wholesale (it must write prose containing citations) but it can close
surfaces 1 and 3 — see **P2-01**.

### 1.5 Dead-work bug in draft pre-verification **[reported]**

`_paper_writing.py:2097-2119` runs `filter_verified_bibtex` and produces a
hallucination-filtered `bib_text` — which is then **never used again in that
function**. The citation list handed to the drafting prompt is built from
*unfiltered* `candidates.jsonl` at `:2121`. The pre-verification pass is pure
cost with zero effect.

### 1.6 Stage-graph mechanics — three landmines **[reported]**

- **`@register_stage(depends_on=...)` is dead data.** `registry.py:44-82`
  stores it; nothing outside `tests/test_registry.py` reads it. `CONTRACTS`
  (`contracts.py:151`) is the sole source of truth. The
  `depends_on=frozenset({Stage.EXPORT_PUBLISH})` at `_review_publish.py:3148` is
  decorative.
- **`rebuild_from_registry()` (`contracts.py:356-375`) is a landmine.** Zero
  callers. Every decorator's `StageContract` omits `depends_on`, so calling it
  would default them all to `frozenset()` and flatten the 23-stage DAG into one
  concurrent level. Do not wire it up.
- **`_io_helpers.py:40-57` resolves prior artifacts by
  `sorted(run_dir.glob("stage-*/" + filename), reverse=True)`** — highest stage
  number wins. Every `input_files` check and every `_read_prior_artifact` call
  routes through it. Any reordering that creates `stage-23/` before `stage-22/`
  silently shadows same-named files.

Also: `resolve_stage_order(start_from=…)` slices the flattened list
**positionally** (`resolution.py:73-75`), so reordering changes what
`--from-stage` includes. And Kahn's algorithm there **does not detect cycles** —
it silently emits a short list; `verify_acyclic()` (`resolution.py:99-106`) is
called only from tests.

### 1.7 Cost tracking is entirely unwired **[reported]**

`CostTracker.record_from_llm_response` (`cost_tracker.py:108`) has **zero
production callers** (only `tests/test_experiment_search.py:232`), and
`client.py` never imports `cost_tracker` or `pricing`. Its docstring claims it
is "populated at the lowest choke point in LLMClient" — false.

Every agent this plan adds is invisible to budget accounting until **P0-05**
lands.

### 1.8 Extended thinking is not supported **[reported]**

`anthropic_adapter.py:112` `_build_message_body` emits only
`{model, messages, max_tokens, temperature}`. No `thinking`, no `budget_tokens`,
no `reasoning_effort` anywhere in `berb/llm/`. There is a guard at `:104-109`
forcing `temperature=1.0` for `_THINKING_MODELS = ("claude-3-7", "claude-4")`
that never enables thinking (and does not match `claude-sonnet-4.6`-style ids).

**Consequence:** PAT's Light/Medium/High *thinking tracks* cannot be implemented
faithfully. They must be approximated with `max_tokens` + model choice, or the
adapter must gain a `thinking` passthrough first (**P3-02**).

### 1.9 The NadirClaw complexity router is half-broken **[reported]**

`ComplexityClassifier.analyze()` (`nadirclaw_router.py:184-203`) only ever emits
tier `"complex"` or `"simple"`; `select_model()`'s `elif tier == "mid"` branch
(`:515`) is **unreachable** and `mid_model` is dead. `tier_thresholds`
(`:470`) is stored and never read.

**Consequence:** do not build PAT-style adaptive budgeting on this classifier
without fixing it first. Its "complexity" measure is a length threshold plus a
keyword bag regardless.

---

## 2. Design paradigms adopted per module

The repo's own rules (`~/.claude/rules/common/coding-style.md`,
`rules/python/*.md`) mandate immutability, `Protocol`-based duck typing, small
files, and explicit error handling. This plan adds no new architectural style —
it follows what each module already does well.

| Module | Existing paradigm | What this plan adds | Rationale |
|---|---|---|---|
| `berb/review/` | **Data-driven strategy**: `REVIEWER_PERSONAS` is a `list[ReviewerPersona]` (`ensemble.py:116`); behaviour varies by data, not subclass | Extend the dataclass with a budget field; add personas as *data* | Adding a reviewer must stay a data edit, never a new class. Resist the urge to introduce a `Reviewer` ABC for one dimension of variation |
| `berb/reasoning/socratic.py` | **Constrained-action interrogator**: `FalsificationCritic.ALLOWED_ACTIONS` is a closed tuple; the critic is *forbidden* from proposing fixes (`socratic.py:384-513`) | Mirror it with a constrained-verdict answerer | Symmetry. The query half's discipline (closed action set) is why it works; the answer half needs the same closed verdict set to stay auditable |
| Q&A engine (new) | — | **`Protocol`-based ports**: `ClaimProber` and `ClaimAnswerer` protocols, two answerer implementations (search-backed for novelty, evidence-backed for soundness) | Two genuinely different implementations exist → a protocol is earned, not speculative. `rules/python/patterns.md` prescribes `Protocol` over ABC |
| `berb/integrity/` | **Immutable records + content-hashed registry** (`evidence.py`, `registry.py`) | Consume it; add no new record types | The data model is already right. The defect is wiring, not design |
| Baseline scout (new) | — | **Pure function returning a frozen result**: `find_omitted_baselines(planned, corpus) -> OmittedBaselines` | No state, no I/O, trivially testable. A class here would be ceremony |
| RDS metric (new) | — | **Pure function** over existing `cosine_similarity` (`memory/retriever.py:20`) | ~15 lines. No dependency, no abstraction |
| `berb/pipeline/contracts.py` | **Declarative DAG, single source of truth** | Use `input_files` as the gate mechanism rather than reordering edges | `executor.py:157-169` already fails a stage on a missing declared input. Cheapest real gate; zero runner changes |
| `berb/llm/client.py` | Single `chat()` choke point (`client.py:556`) | One cost-recording line at the choke point (`:716`) | One insertion covers every present and future call site. Per-call-site bookkeeping would rot immediately |

**Anti-patterns explicitly avoided:**
- No segmenter agent (PAT stage 1) — see §5.
- No new `Reviewer`/`Agent` base class hierarchy. Berb has 11 reasoning modules
  behind a `ReasoningMethod` ABC (`reasoning/base.py`) of which the pipeline
  calls **two**; that abstraction has not paid for itself and will not pay for
  itself a second time.
- No revival of `berb/research/` (5 modules, zero importers) or
  `experiment/self_correcting.py` / `auto_debugger.py`. See §5.

---

## P0 — BUGS. Fix regardless of whether any feature below ships.

These are defects found while researching, not enhancements. Each is small and
independently shippable.

---

### [x] P0-01 · `evidence_registry.json` is read one stage before it is written
**Severity:** HIGH — silently degrades every claim verdict on every first-pass run.
**Verification status:** [reported] — confirm both line refs before editing.

**Files:**
- `berb/pipeline/stage_impls/_review_publish.py:647` (writer, stage 20)
- `berb/pipeline/stage_impls/_paper_writing.py:2322` (reader, stage 17)

**Change:** move the `VerifiedEvidenceRegistry.from_run_dir(run_dir)` build and
its `save()` from stage 20 into stage 14 `RESULT_ANALYSIS` (or 15). Justified
because `from_run_dir` only reads `experiment_summary.json`, a stage-14 output —
there is no dependency forcing it to stage 20. Keep stage 20's write as an
idempotent refresh if anything else depends on it being current at that point.

**Why it matters here:** every downstream idea in this plan that grounds claims
against evidence (P1-01, P2-02) is worthless while the registry is empty.

**Acceptance test:**
```python
def test_evidence_registry_populated_before_claim_manifest(tmp_path):
    # run stages 14 -> 17 on a fixture run_dir containing experiment_summary.json
    # assert (run_dir / "evidence_registry.json").exists() before stage 17 runs
    # assert at least one ClaimRecord in stage-17/claim_manifest.json has
    #        verdict == ClaimVerdict.SUPPORTED
```

---

### [x] P0-02 · Draft pre-verification result is computed and discarded
**Severity:** MEDIUM — wasted network + wall-clock every run; the filtering the
code intends to apply never applies.
**Verification status:** [reported]

**Files:** `berb/pipeline/stage_impls/_paper_writing.py:2097-2121`

**Change:** either use the filtered `bib_text` to build the drafting citation
list (replacing the unfiltered `candidates.jsonl` read at `:2121`), or delete
the `filter_verified_bibtex` call. **Prefer using it** — it is the cheapest
possible step toward retrieve-only citations (P2-01) and the verification cost
is already being paid.

Note `verify_citations` is fully synchronous and network-bound
(`literature/verify.py:659`), with a 300 s global cap (`:693`) and a title-keyed
on-disk cache at `~/.cache/berb/citation_verify/` — so re-runs are near-free but
the first run on ~60 refs costs roughly 30–90 s.

**Acceptance test:**
```python
def test_draft_citation_list_excludes_hallucinated_entries():
    # candidates.jsonl contains one entry whose verification status is HALLUCINATED
    # assert its cite_key does not appear in the citation_instruction block
```

---

### [x] P0-03 · `CITATION_VERIFY` cannot block export, contradicting its own contract
**Severity:** HIGH — a stated invariant is false.
**Verification status:** [verified]

`stages.py:139` states: `# T3.4: CITATION_VERIFY removed — hallucinated citations
MUST block export`, and stage 23 is deliberately excluded from
`NONCRITICAL_STAGES` so that its failure aborts the run. But
`contracts.py:345-352` declares `CITATION_VERIFY.depends_on = {EXPORT_PUBLISH}`,
so it aborts *after* the paper, PDF, LaTeX, and code bundle are already written.

**Do NOT fix this by swapping the DAG edge.** Three reasons:

1. **Correctness.** Stage 22 *mutates the citation key-space*:
   `_resolve_missing_citations` (`_review_publish.py:2311-2316`) adds entries for
   LLM-invented keys, and IMP-1 (`:2401-2421`) prunes uncited ones. Final key set
   = `(stage4 ∪ resolved_invented) − uncited`. Verifying before stage 22 misses
   precisely the invented keys, which are the hallucination-prone ones.
2. **Blast radius.** Reordering breaks five assertions
   (`test_resolution.py:16,22-26`; `test_berb_checkpoint.py:86`;
   `test_berb_citation_verify.py:580,589`) plus `test_berb_stages.py:40,97`.
3. **Latent hazards.** It changes what `--from-stage` includes (positional slice,
   `resolution.py:73-75`) and risks the reverse-glob artifact shadowing in
   `_io_helpers.py:40-57`.

**Change (preferred):** move the *verification call* inside stage 22, between key
resolution and export. Concretely, in `_execute_export_publish`:
- after the final `references.bib` write (`_review_publish.py:2423-2429`),
- and before the LaTeX/template block (`:2431`),

run `verify_citations(bib_text, s2_api_key=…)`, apply
`filter_verified_bibtex`, and **return `StageStatus.FAILED` with
`E22_EXPORT_FAIL` if `report.hallucinated > 0`** (threshold configurable).
Stage 23 then keeps only the reporting/annotation role it already performs, and
the DAG is untouched.

**Alternative (if a hard stage boundary is wanted):** split stage 22 into
"assemble references" and "export artifacts", and use the contract input gate —
give the export half `input_files=("verification_report.json",)`. Per
`executor.py:157-169` a missing declared input fails the stage with
`Missing input: … (required by …)`, giving a real gate with zero runner changes.
This is more invasive; take it only if P0-03's in-stage fix proves awkward.

**Acceptance test:**
```python
def test_export_fails_when_hallucinated_citation_present(tmp_path):
    # references.bib contains one fabricated entry; mock verify to return HALLUCINATED
    result = _execute_export_publish(...)
    assert result.status is StageStatus.FAILED
    assert not (stage_dir / "paper.tex").exists()   # nothing exported

def test_export_succeeds_when_all_citations_verified(tmp_path): ...
```

---

### [x] P0-04 · Nothing gates on `real_search: false`
**Severity:** HIGH — a run whose entire literature corpus was hallucinated
proceeds to publication indistinguishably from a real one.
**Verification status:** [reported]

**Files:**
- `berb/pipeline/stage_impls/_literature.py:498-514` (LLM invents candidates)
- `berb/pipeline/stage_impls/_literature.py:661` (records the flag)

**Change:** read `search_meta.json` in stage 5 `LITERATURE_SCREEN` (already a
GATE stage, `stages.py:107`) and fail — or at minimum force
`degradation_signal.json` — when `real_search` is false. The degradation path
already exists and already injects a notice into the paper
(`_review_publish.py:1876-1917`); reuse it rather than inventing a new signal.

**Acceptance test:**
```python
def test_literature_screen_flags_run_when_search_was_synthetic(tmp_path):
    # write search_meta.json with {"real_search": false}
    # assert stage 5 result is FAILED or degradation_signal.json is written
```

---

### [x] P0-05 · Cost tracking records nothing
**Severity:** MEDIUM — no budget signal; every agent this plan adds is invisible.
**Verification status:** [reported]

**Files:** `berb/llm/client.py:716` (`_call_with_retry`), `berb/llm/cost_tracker.py:108`

**Change:** one call to
`get_cost_tracker().record_from_llm_response(...)` at the `_call_with_retry`
choke point. This is the lazy fix *and* the correct one — every present and
future call site is covered, including everything below.

Two adjacent landmines, out of scope but worth a `# ponytail:` note or a
separate ticket: `SmartLLMClient.complete()` calls `LLMClient.complete()` which
does not exist, and `smart_client.py:257` divides per-token rates by 1e6 a
second time (~1e6× undercount). Do not build budgeting on `SmartLLMClient`.

**Acceptance test:**
```python
def test_chat_records_cost_event():
    # FakeLLMClient path won't exercise this; use LLMClient with a mocked adapter
    # assert get_cost_tracker() has exactly one CostEvent after one chat()
```

---

## P1 — WIRE WHAT ALREADY EXISTS (highest value per unit effort)

Nothing in this tier requires new subsystems. It connects code that is already
written, tested, and dead.

---

### [x] P1-01 · Feed the ClaimManifest into the review ensemble
**Maps to:** ScholarPeer Summary Agent (ablation −10%)
**Effort:** S · **Value:** L
**Depends on:** P0-01 (registry must be populated or every claim reads `unsupported`)
**Verification status:** [reported]

Berb already computes ScholarPeer's Ŝ triple and discards it:
- **H_core** ≈ `ClaimManifest` / `ClaimRecord` (`integrity/claims.py:80,149`)
- **M** ≈ `exp_plan.yaml` (`_experiment_design.py:492`)
- **E** ≈ `VerifiedEvidenceRegistry` (`integrity/registry.py`)

The ensemble receives raw extracted text only (`ensemble.py:235-277`), hard
truncated at 50,000 chars (`:462-464`).

**Change:** at the ensemble call site (`_review_publish.py:2772`), load
`stage-17/claim_manifest.json` via `ClaimManifest.load()` and `exp_plan.yaml`
via `_read_prior_artifact`, and prepend a structured block to the review context.
`run_dir` is already a parameter of `_execute_export_publish`
(`_review_publish.py:1827`) and `_read_prior_artifact(run_dir, "candidates.jsonl")`
is already called ~55 lines below (`:2856`) — no plumbing needed.

Keep the raw text too; the point is to add the high-fidelity signal, not to
replace the paper. Prefer passing it through the existing `cached_prefix`
mechanism (`ensemble.py:479`) so all personas share one cached copy.

**Design note:** add an optional `structured_context: str | None = None` keyword
to `review_paper()`. Do not introduce a context object — one optional string
keeps the two existing tests (`test_ensemble_batch.py`,
`test_ensemble_caching.py`) passing unchanged.

**Acceptance test:**
```python
def test_review_paper_includes_claim_manifest_when_present(tmp_path):
    # assert cached_prefix (or user message) contains a claim_id from the manifest
def test_review_paper_works_without_manifest(tmp_path):
    # backwards compatibility: absent manifest must not raise
```

---

### [x] P1-02 · Review Diversity Score
**Maps to:** ScholarPeer RDS (detects "artificial hivemind" mode collapse)
**Effort:** S · **Value:** M
**Verification status:** [reported]

`MetaReview` (`ensemble.py:98-112`) already measures diversity in *score* space
(`score_std`, `confidence = max(0, 1 - score_std/5)` at `:566-570`, conflict
flags at `:574-582`) but never in *text* space. Five reviewers can emit near
identical prose and still look healthy on score spread.

Everything needed exists with **zero new dependencies**:
- `EmbeddingProvider` (`memory/embeddings.py:36`) with a pure-stdlib TF-IDF
  backend (`:166-182`, `_TFIDF_DIM = 256`) that needs no model download
- `cosine_similarity` (`memory/retriever.py:20`), pure `math`, guards zero norms

**Change:** add `review_diversity: float` to `MetaReview`; compute in
`area_chair_decision` as
`1 - mean(cosine_similarity(e_i, e_j) for i<j)` over
`EmbeddingProvider().embed_batch([r.detailed_feedback for r in reviews])`.
Log a warning below a threshold (ScholarPeer reference points: fine-tuned models
0.01–0.02 = severe collapse, ScholarPeer 0.31, human committees 0.43 — Berb's
5 distinct personas should land well above 0.1; treat <0.1 as a prompt bug).

**Caveat to record in the code:** `berb/memory/` is itself unwired
(`config.py:112` says so explicitly) and `sentence-transformers` is an
undeclared soft import absent from `pyproject.toml`. Import only
`EmbeddingProvider` and `cosine_similarity`; do not pull in `MemoryStore`. The
TF-IDF backend must remain the tested path.

**Acceptance test:**
```python
def test_review_diversity_low_for_identical_reviews():
    # 5 Review objects with identical detailed_feedback -> score near 0.0
def test_review_diversity_high_for_distinct_reviews():
    # 5 clearly different texts -> score materially above 0.0
def test_review_diversity_uses_tfidf_backend_without_optional_deps(monkeypatch):
    # force ImportError on sentence_transformers; assert it still computes
```

---

### [x] P1-03 · Make the ensemble verdict *do something* — move it to stage 20
**Maps to:** PAT §4 (a review nobody acts on is false assurance) + the §0.2 inversion
**Effort:** M · **Value:** L
**Depends on:** nothing, but unlocks the value of P1-01, P1-02, P3-01
**Verification status:** [verified]

Currently the ensemble runs at stage 22 on the exported paper, inside a
debug-swallowed `try/except`, and its `MetaReview` is discarded (§1.1).

**Change:** move the ensemble invocation from `_execute_export_publish`
(`_review_publish.py:2772-2801`) into `_execute_quality_gate`
(`_review_publish.py:434`, stage 20). Stage 20 already:
- scores `paper_revised.md` against `config.quality_threshold`,
- writes `quality_report.json` / `fabrication_flags.json`,
- **fails the stage when the score is below threshold** (unless
  `graceful_degradation`),
- is the designated GATE with rollback target `PAPER_OUTLINE`
  (`stages.py:117`) — i.e. reject sends the pipeline back to rewrite the paper.

That is exactly the consumer the ensemble needs. Feed `MetaReview.average_score`
and `consensus_decision` into the gate decision alongside the existing score.

**Two decisions to make explicitly** (do not let them default silently):
1. **Weighting.** Does the ensemble score replace the existing quality score,
   average with it, or act as an independent veto? Recommend: independent veto
   on `consensus_decision == REJECT` only, leaving the numeric gate as-is, so the
   change cannot lower quality relative to today.
2. **Cost.** Stage 20 runs before export, so a rejection now costs a full paper
   rewrite loop. Bound it with the existing `MAX_DECISION_PIVOTS`-style guard, or
   accept at most one ensemble-triggered rollback per run.

Keep a thin stage-22 artifact write if `ensemble_review.md` is referenced by
packaging (`pipeline/packaging.py`) — check before removing.

**Also fix while here:** stage 20 is in `NONCRITICAL_STAGES` (`stages.py:137`,
"low quality should warn, not block deliverables"). That is defensible for the
numeric score but means a REJECT consensus is skippable when
`skip_noncritical=True`. Decide deliberately and document the choice inline.

**Acceptance test:**
```python
def test_quality_gate_blocks_on_ensemble_reject_consensus(tmp_path): ...
def test_quality_gate_passes_when_ensemble_unavailable(tmp_path):
    # no llm / no ensemble -> gate behaves exactly as today (no regression)
def test_ensemble_rollback_bounded(tmp_path):
    # at most one ensemble-triggered rollback per run
```

---

### [x] P1-04 · Stop discarding baselines in the stage-9 time-budget trim
**Maps to:** ScholarPeer Baseline Scout (prerequisite for P2-03)
**Effort:** S · **Value:** M
**Verification status:** [reported]

`_experiment_design.py:392-413` prepends benchmark-agent baselines, then
`:437-460` trims the combined condition list to 8/12/20 by time budget — which
can silently drop the very baselines the benchmark agent just added.

**Change:** partition before trimming. Trim *variants and ablations*; never trim
reference baselines. If the budget cannot fit the baselines alone, fail loudly
rather than quietly shipping an uncompared paper.

**Acceptance test:**
```python
def test_time_budget_trim_preserves_baselines():
    # 25 conditions incl. 3 baselines, budget caps at 8
    # assert all 3 baselines survive; only variants are dropped
```

---

## P2 — NEW CAPABILITY (build, but on existing seams)

---

### [x] P2-01 · Close the citation hallucination surfaces (retrieve-only, pragmatically)
**Maps to:** ScholarPeer's retrieve-only architecture; PAT's search grounding
**Effort:** M · **Value:** L
**Depends on:** P0-02, P0-04
**Verification status:** [reported]

Full retrieve-only is not achievable — Berb must write prose containing
citations, and no constrained-decoding layer exists. But two of the three
surfaces in §1.4 close cleanly:

1. **Delete the LLM-invented-candidates path** (`_literature.py:498-514`) or
   make it hard-fail the run. A corpus of fabricated papers is not a degraded
   run, it is a void one. (P0-04 gates on the flag; this removes the source.)
2. **Demote `_resolve_missing_citations` from repair to detection.** Keep the
   search (it is genuinely useful for diagnosing *what* the model meant), but
   stop appending results to `references.bib` (`_review_publish.py:2315`).
   Instead write `invalid_citations.json` — which already exists (`:2352-2355`) —
   and feed its non-emptiness into the P0-03 export gate.

**Why not go further:** adding a cite-key masking / constrained-decoding layer to
drafting is a large change against three separate section-writing call sites
(`_paper_writing.py:484,560,619`) for uncertain marginal gain over a hard export
gate. Revisit only if the gate proves to fire often.

**Acceptance test:**
```python
def test_literature_collect_fails_when_all_sources_down(monkeypatch):
    # no fabricated candidates.jsonl is produced
def test_invented_cite_key_is_reported_not_repaired():
    # references.bib is unchanged; invalid_citations.json lists the key
```

---

### [x] P2-02 · Claim-vs-evidence adjudicator (the answer half of the Q&A engine)
**Maps to:** ScholarPeer Multi-Aspect Q&A Engine (ablation **−26%**, the largest)
**Effort:** M · **Value:** L
**Depends on:** P0-01, P1-01
**Verification status:** [reported]

**Half of this already exists and runs.** `FalsificationCritic`
(`reasoning/socratic.py:384-513`) is a disciplined skeptic — a closed
`ALLOWED_ACTIONS = (clarify, expose_assumption, check_constraint,
counterexample, demand_falsification)`, explicitly forbidden from proposing
alternatives — already invoked in a 2-round loop per hypothesis at
`_synthesis.py:293-334`. But there is **no answer agent anywhere**:
`_synthesis.py:326` is literally
`_current_text = _ht  # would be repaired by LLM in production`.

Berb has an advantage neither paper has: for technical-soundness questions it
**owns the ground-truth run data**. ScholarPeer must infer whether a number is
plausible; Berb can look it up in `experiment_summary.json`. This is precisely
ScholarPeer's admitted weak spot (internal logic checks) and PAT's strength.

**Build, in two independently shippable pieces:**

**(a) Hypothesis repair at stage 8** — close the loop the stub admits is open.
Answer the critic's hard-severity issues and revise the hypothesis text *before*
an experiment gets designed for it. This is the §0.2 inversion at its purest.

**(b) Soundness adjudication at stage 20** (alongside P1-03) — for each
`ClaimRecord` of type EMPIRICAL/COMPARATIVE, cross-reference `ClaimRecord.text`
against `EvidenceRecord.value` in the registry and emit a verdict. Much of the
numeric machinery exists (`_paper_writing.py:2369-2468`,
`_value_matches_evidence` at `:2554-2564`, 1% relative tolerance) but it is
heuristic regex matching; the LLM adjudicator handles comparative and causal
claims the regex cannot.

**Cap at N_QA = 10.** ScholarPeer shows 15 performs *worse* — context dilution,
not a budget concern. Encode the cap as a named constant, not a magic number.

**Design:**
```python
# berb/review/interrogation.py  (new, ~150 lines)
from typing import Protocol

MAX_QUESTIONS = 10          # ScholarPeer: gains saturate at 10, degrade at 15

class ClaimAnswerer(Protocol):
    async def adjudicate(self, question: str, claim: ClaimRecord) -> Verdict: ...

@dataclass(frozen=True)
class Verdict:
    claim_id: str
    question: str
    status: ClaimVerdict          # reuse the existing enum, do not invent one
    evidence_ids: tuple[str, ...]
    reasoning: str
```
Two implementations: `EvidenceBackedAnswerer` (registry lookup + LLM) and
`SearchBackedAnswerer` (novelty questions, uses `literature.search_papers`).
Two real implementations justify the `Protocol`; a single one would not.

**Do not reuse** `debate.py` / `jury.py` / `dialectical.py`. They are generic
reasoning wrappers whose `execute()` is never called from the pipeline, and they
are not claim-grounded. `FalsificationCritic` is the right seam.

**Acceptance test:**
```python
def test_adjudicator_marks_claim_unsupported_when_no_evidence(): ...
def test_adjudicator_marks_claim_supported_on_value_match(): ...
def test_question_count_capped_at_ten(): ...
def test_hypothesis_repaired_after_hard_severity_issue(): ...
```

---

### [x] P2-03 · Baseline scout at stage 9 (design time), not stage 22 (review time)
**Maps to:** ScholarPeer Baseline Scout (ablation −9%) + PAT's "31% ran new experiments"
**Effort:** M · **Value:** L
**Depends on:** P1-04
**Verification status:** [reported]

This is the plan's clearest instance of the §0.2 inversion. PAT reports that 31%
of ICML authors **ran entirely new experiments** because the tool identified
missing comparisons. For Berb that same signal, delivered at stage 9, costs one
extra condition in a config file instead of a re-run.

**Current state:** stage 9 picks baselines from LLM parametric memory. The
prompt (`prompts.py:1687-1689`) instructs the model to "check recent
NeurIPS/ICML/ICLR papers" while retrieving **nothing** — the model answers from
memory. `_inject_required_baselines` (`benchmark_agent/selector.py:225-269`)
force-adds a static hardcoded list from `benchmark_knowledge.yaml:21-23`
covering only 5 domains. Critically, the stage-9 context preamble loads **only
`goal.md` and `hypotheses.md`** (`_prompt_helpers.py:227-233`) — `candidates.jsonl`,
the corpus Berb itself retrieved, sits unused on disk.

**Change, in two steps:**

1. **Feed the corpus in.** At `_experiment_design.py:350`, read
   `candidates.jsonl` and extract method/benchmark names from titles and
   abstracts. Present them as "competitors named in your own retrieved corpus."
   Cheap, no new API calls, and strictly better grounded than parametric recall.
2. **Add the omitted-baseline check.** A pure function diffing planned baselines
   against corpus-extracted methods:
   ```python
   # berb/agents/benchmark_agent/omissions.py  (new, ~60 lines)
   @dataclass(frozen=True)
   class OmittedBaselines:
       missing: tuple[str, ...]
       corpus_size: int

   def find_omitted_baselines(
       planned: Sequence[str], corpus_methods: Sequence[str]
   ) -> OmittedBaselines: ...
   ```
   Write `omitted_baselines.json`; surface it in stage 20's gate.

**No omitted-baseline detector exists today** — the nearest things are reviewer
prompt text (`ensemble.py:152,169`), `MISSING_BASELINE = "no_baseline"`
(`experiment_diagnosis.py:32`, detects zero-baseline *runs*), and a keyword
check for the literal word "baseline" (`_analysis.py:950-951`). Nothing asks
"did we compare against what we cited?"

**Also available for reuse:** `enable_web_search` / `max_web_results` /
`web_search_min_local` (`benchmark_agent/orchestrator.py:40-42`) are declared and
**never passed to `SurveyorAgent`** (`:181-185`) — dead config for a feature
that was never connected.

**Acceptance test:**
```python
def test_omitted_baselines_detected():
    # corpus mentions ResNet-50 and ViT-B/16; plan has only ResNet-50
    assert find_omitted_baselines(["ResNet-50"], [...]).missing == ("ViT-B/16",)
def test_stage9_prompt_contains_corpus_methods(tmp_path): ...
def test_no_omissions_when_corpus_empty():
    # empty corpus must not produce spurious "missing" entries
```

---

### [x] P2-04 · Iterative literature expansion (k=3)
**Maps to:** ScholarPeer Literature Review & Expansion Agent (ablation −6%)
**Effort:** M · **Value:** M
**Verification status:** [reported]

`_expand_search_queries` (`_literature.py:44-81`) is a pure string template
computed *before* any search runs: first-5-words, last-5-words, plus
`"survey"/"benchmark"/"comparison"` suffixes. Nothing feeds screening results
(stage 5) or related-work gaps back into a second round. Ranking is
`sort(key=(citation_count, year))` (`search.py:224`) — that is the entire
relevance model.

**Change:** loop stage 4 up to **three** times, seeding round *n+1* from round
*n*'s screened abstracts. **Stop at 3** — ScholarPeer's Fig. 5 shows quality
*declining* past k=3 as tangential papers dilute context. Encode as a named
constant with the citation in a comment.

**Two cheap constraints, both S, both worth doing:**
- **(a) Venue quality.** `Paper.venue` is captured (`literature/models.py:45`)
  and used only to choose `@inproceedings` vs `@article`
  (`models.py:105-131`). Add a top-tier allowlist as a *ranking boost*, not a
  hard filter — Berb's domains are broader than ScholarPeer's ML-only scope, and
  a hard filter would silently empty non-ML corpora.
- **(b) Upper date cutoff.** Only `year_min` exists (`_literature.py:161,390`).
  `RecencyFilter` (`literature/recency_filter.py`) is fully built and unwired.
  For Berb the rationale differs from ScholarPeer's (which needs it for review
  fairness): here it prevents citing work published *after* the experiments ran,
  which is a reproducibility property.

**Note on dedup:** `_deduplicate` (`search.py:346`) documents "fuzzy title
match" but `_normalise_title` (`:339`) lowercases, strips punctuation, and does
an **exact dict-key match** — no edit distance. Not in scope here, but tripling
the query volume will surface more near-duplicates. Consider a follow-up ticket.

**Acceptance test:**
```python
def test_expansion_stops_at_three_rounds(): ...
def test_round_two_queries_derived_from_round_one_results(): ...
def test_venue_boost_does_not_empty_non_ml_corpus(): ...
```

---

## P3 — RIGOR & OBSERVABILITY

---

### [x] P3-01 · Proof/rigor reviewer persona
**Maps to:** PAT's headline result (55.2% → 89.7% recall on math/proof errors)
**Effort:** S/M · **Value:** L (M for non-mathematical domains)
**Depends on:** P1-03 (otherwise the finding goes nowhere)
**Verification status:** [reported]

Berb has **zero** mathematical or logical verification anywhere — confirmed
across `berb/integrity/` (everything is empirical evidence-linking) and
acknowledged in-code at `_paper_writing.py:1787`, which explicitly disclaims
"math proofs, theoretical economics". The 5 existing personas
(`ensemble.py:116-220`) are all empirical/presentational.

PAT's error taxonomy is concrete and worth targeting verbatim: missing absolute
value signs, inequalities pointing the wrong way, overloaded notation,
off-by-one errors, invalid proof steps — plus "mathematically significant typos"
that degrade rigor without invalidating results.

**Change:** add a 6th `ReviewerPersona` entry. Three constraints discovered:

1. **`ReviewDimension` is a closed StrEnum** (`NOVELTY, SIGNIFICANCE,
   TECHNICAL_QUALITY, EXPERIMENTAL_RIGOR, CLARITY, REPRODUCIBILITY`) and
   `_parse_review_content` calls `ReviewDimension(k)` on **every** returned key,
   while `_build_review_prompt` hardcodes the six keys in its JSON schema.
   Either reuse `TECHNICAL_QUALITY` or extend the enum *and* both those sites.
   Prefer reuse — a new dimension changes the weighted-average maths.
2. **Name it distinctly.** Reviewer 3 is already "Experimental Rigor Expert";
   call this one a proof/derivation checker.
3. **Three tests hardcode 5 reviewers** — `test_ensemble_batch.py` asserts
   `len(adapter.submitted_requests) == 5`, `len(reviews) == 5` (×3), and
   `mock_llm.chat.call_count == 5`. Also `ensemble.py:520`
   (`if len(reviews) != 5`) and `:655` ("from 5 reviewers" in the meta-review
   text). Update all six sites.

**Compute budget (PAT's adaptive budgeting, approximated):** add
`max_tokens: int | None = None` to `ReviewerPersona` (`ensemble.py:71-79`) and
pass `max_tokens=persona.max_tokens` into the existing `chat()` kwarg — the
parameter already exists (`client.py:556-569`) and resolves to
`self.config.max_tokens` when `None`, so the other five personas are unaffected.
In the batch path use `"max_tokens": persona.max_tokens or max_tokens` (the
request dict is already built per-persona). **No call-signature change needed.**

Give the proof persona a materially larger budget than the rest — this is the
faithful-as-possible stand-in for PAT's High Thinking track given §1.8.

**Scope honestly:** PAT's 89.7% comes from an inference-scaling pipeline over
math-heavy TCS papers, not from one persona. A single persona will not reproduce
that number. It is worth doing because Berb's current coverage is *zero*, and
because PAT found that even a **zero-shot single model call reaches 55.2%** —
most of the available win needs no orchestration at all.

**Acceptance test:**
```python
def test_six_personas_registered(): ...
def test_proof_persona_receives_larger_max_tokens(): ...
def test_batch_path_submits_six_requests(): ...   # update existing ==5 asserts
def test_meta_review_text_reports_actual_reviewer_count(): ...
```

---

### [ ] P3-02 · (Optional) Extended-thinking passthrough
**Maps to:** PAT's Light/Medium/High thinking tracks
**Effort:** M · **Value:** M — **do not start before P3-01 proves the need**
**Verification status:** [reported]

Adds `thinking: {"type": "enabled", "budget_tokens": N}` to
`anthropic_adapter._build_message_body` (`:112`) and a `thinking_budget`
parameter to `LLMClient.chat()`. Anthropic requires `max_tokens > budget_tokens`.

While here, fix the adjacent bug: `_THINKING_MODELS = ("claude-3-7", "claude-4")`
(`anthropic_adapter.py:104-109`) forces `temperature=1.0` for models that *could*
think without enabling thinking, and does not match `claude-sonnet-4.6`-style ids.

**Why deferred:** `max_tokens` + model choice already approximates the budget
axis, and P3-01 will reveal whether the ceiling is real. Building the passthrough
first is speculative generality.

---

### [x] P3-03 · Critique dedup / severity synthesis before the AC decision
**Maps to:** PAT Stage 4 (Global Synthesis)
**Effort:** M · **Value:** M
**Depends on:** P1-03
**Verification status:** [reported]

`area_chair_decision` (`ensemble.py:511-613`) is purely statistical — weighted
average, stdev confidence, `max-min > 3` conflict flag. `_generate_meta_review_text`
(`:615-662`) concatenates each reviewer's output verbatim; it never merges,
clusters, or reconciles overlapping critiques.

PAT's synthesis agent exists specifically because naive Pass@k **degrades
precision**: "if a model outputs 10 potential issues per pass, and has a 10%
chance of finding a critical issue per pass, running it 10 times forces a human
to sift through ~100 proposed issues just to find one valid, critical error."
Berb has exactly that shape — six personas × N weaknesses each.

**Change:** one LLM pass clustering the free-text critiques by underlying claim
before AC scoring. Insertion point is the gap between `_ens_reviews` and
`area_chair_decision` at the call site. Add
`async def synthesize_critiques(reviews) -> tuple[Critique, ...]` and store the
result on `MetaReview`; do not touch the scoring maths.

**Acceptance test:**
```python
def test_duplicate_critiques_merged(): ...
def test_synthesis_preserves_unique_critiques(): ...
def test_ac_scores_unchanged_by_synthesis():   # regression guard
```

---

### [x] P3-04 · Sub-domain historian
**Maps to:** ScholarPeer Historian Agent (ablation −4%)
**Effort:** S · **Value:** S
**Verification status:** [reported]

Compress `candidates.jsonl` into a chronological "domain narrative" feeding
stages 7-8 and the related-work section. `literature/fs_processor.py:293-319`
already clusters papers by topic (soft `sentence_transformers` + `sklearn`
import with a keyword fallback). One LLM call.

Lowest ablation impact of the ScholarPeer agents; schedule last.

---

### [x] P3-05 · Venue-guideline-conditioned reviewers
**Maps to:** ScholarPeer Review Generator (guidelines-driven synthesis)
**Effort:** S · **Value:** S
**Verification status:** [reported]

`berb/assessor/venue_recommender.py` already picks a target venue, and
`config.export.target_conference` already drives template selection
(`_review_publish.py:2435`) and NeurIPS-checklist generation (`:2448`). Condition
the reviewer personas on that venue's checklist so the internal review matches
the venue actually being targeted.

---

## 4. Sequencing

Dependency-ordered. Each tier is independently shippable.

```
Wave 1 (bugs, no dependencies, do first)
  P0-01  evidence registry ordering        ← unblocks P1-01, P2-02
  P0-02  dead pre-verification              ← unblocks P2-01
  P0-03  citation gate inside stage 22
  P0-04  gate on real_search
  P0-05  cost tracking choke point          ← makes everything after measurable

Wave 2 (wire existing dead code — best value/effort in the plan)
  P1-01  ClaimManifest -> ensemble          (needs P0-01)
  P1-02  Review Diversity Score
  P1-04  baseline trim fix
  P1-03  ensemble -> stage 20 gate          ← unblocks P2-02b, P3-01, P3-03

Wave 3 (new capability)
  P2-01  close citation surfaces            (needs P0-02, P0-04)
  P2-03  baseline scout at stage 9          (needs P1-04)
  P2-02  claim adjudicator                  (needs P0-01, P1-01)
  P2-04  k=3 literature expansion

Wave 4 (rigor + polish)
  P3-01  proof persona                      (needs P1-03)
  P3-03  critique synthesis                 (needs P1-03)
  P3-04  historian
  P3-05  venue conditioning
  P3-02  thinking passthrough               (only if P3-01 shows a ceiling)
```

**If only one wave ships, ship Wave 1.** Those are defects with small diffs.
**If only two, add Wave 2** — it is almost entirely wiring, not building.

---

## 5. Explicitly rejected, with reasons

Recording these so they are not re-proposed.

| Idea | Source | Why not |
|---|---|---|
| **Document segmentation agent** | PAT stage 1 | PAT segments because it receives arbitrary human manuscripts of unknown shape. Berb *controls* structure at generation time via `PAPER_OUTLINE` (stage 16). A segmenter would re-derive what stage 16 already knows. The 50K-char truncation (`ensemble.py:462`) rarely binds on a pipeline-generated paper |
| **H-Max score** | ScholarPeer §4.1 | Requires human reviews of the same paper as the comparison baseline. Berb's papers have none. Not computable |
| **Spearman correlation vs. accept/reject** | ScholarPeer §4.1 | No human decision ground truth exists for Berb's output |
| **Publication cutoff as a fairness device** | ScholarPeer §3.1 | Berb's papers have no submission date. Keep the *mechanism* (P2-04b) but for reproducibility, not fairness |
| **Reviving `berb/research/`** (5 modules) | — | Zero importers; grep finds only self-references and docstrings. Gap analysis enumerates *literature gaps*, idea scoring ranks *prospective ideas* — neither decomposes a written paper into claims. `integrity/claims.py` is the correct seam |
| **Reviving `self_correcting.py` / `auto_debugger.py`** | — | Both are inferior to the already-wired LLM repair loops in `code_agent.py:688-1390` and `_code_generation.py:772-1498`. `self_correcting.py`'s `_apply_fix` (`:804`) literally appends `f"# Applied fix: {fix}"` to the source. At most, cherry-pick `AutomatedDebugger._classify_error` (`auto_debugger.py:457`) as a cheap regex pre-filter — S effort, S value |
| **Reviving `integrity/eval/finding_reproduction.py`** | — | `_run_reproduction` (`:291-340`) is `random.random() < success_prob` against a hardcoded 5-entry database, commented `# Placeholder: simulate reproduction`. Deliberately parked (`.reachability-allowlist:14`, `docs/OPEN_DECISIONS.md:112-114`) |
| **Routing reviewers through `NadirClawRouter`** | PAT adaptive budgeting | The classifier is half-broken (§1.9): `mid` tier unreachable, `tier_thresholds` never read, complexity = length + keyword bag. Per-persona `max_tokens` (P3-01) achieves the same goal with none of the breakage |
| **`rebuild_from_registry()`** | — | Would flatten the DAG (§1.6). Consider deleting it outright |
| **New `Reviewer`/`Agent` ABC hierarchy** | — | `berb/reasoning/` already has 11 modules behind a `ReasoningMethod` ABC of which the pipeline calls two. That abstraction has not paid for itself |

---

## 6. Cost

ScholarPeer's own overhead is ~20 LLM calls, ~429K input / ~26K output tokens,
~$1.20 and ~10 min per review (~56 s amortized at batch size 20).

For Berb this is noise. A full `berb run` spans 23 stages and hours of
wall-clock; the dominant cost is stage 12-13 experiment execution, not review
tokens. The ensemble already issues 5 persona calls and supports Anthropic
Message Batches (commit `3614317`), and the paper text is shared across personas
via `cached_prefix` with `cache_ttl="1h"` (`ensemble.py:479`).

Marginal cost by item:
- **Zero extra LLM calls:** P0-01, P0-02 (saves calls), P0-04, P0-05, P1-01,
  P1-02 (TF-IDF backend), P1-04, P2-01, P2-03 step 2
- **One call:** P3-03, P3-04, P3-05
- **One extra persona:** P3-01
- **~20 calls (ScholarPeer's own budget):** P2-02 — the expensive one, and the
  one carrying the −26% ablation
- **HTTP only, no LLM:** P2-04 triples literature API volume against free-tier
  endpoints; the paid Perplexity top-up is conditional
  (`search.py:277-297`) and unaffected

Note P0-05 must land first or none of this is measurable.

---

## 7. Test strategy

Repo conventions (confirmed): `tests/conftest.py` is effectively empty — there
are **no shared fixtures**. Every test file defines its own duck-typed
`FakeLLMClient` (canonical version at `test_berb_executor.py:32`; add `.config`
only when the code under test reads it). Stage executors are patched through the
plugin registry via `_patch_stage_executor()` (`test_berb_executor.py:20`) using
`get_registration(stage)` + `monkeypatch.setattr(registration, "fn", fn)`, not a
module dict.

**Existing tests this plan will break** (update deliberately, do not delete):
- `test_ensemble_batch.py` — four `== 5` assertions (P3-01)
- `test_berb_citation_verify.py:580,586,589` — stage 22/23 ordering (only if
  P0-03's alternative DAG path is chosen; the preferred in-stage fix leaves
  these green)
- `test_berb_prompts.py::test_system_prompt_nonempty` — any new prompt entry
  needs a non-empty `system`

**Prompt registration gotcha:** `_load_overrides` (`prompts.py:112-116`) merges
only YAML stages that **already exist** in `_DEFAULT_STAGES`; unknown names log
`"Unknown stage in prompts file: %s"` and are silently dropped. Any new prompt
must be added to `_DEFAULT_STAGES` in `berb/prompts.py` — adding it to
`prompts.default.yaml` alone does nothing. Also `sub_prompt()` drops
`max_tokens`, so a budgeted agent must be a `stages` entry, not a `sub_prompts`
entry.

Coverage target per `rules/common/testing.md`: 80% on new code. Every new pure
function (`find_omitted_baselines`, the RDS computation, `Verdict` construction)
should have a direct unit test; every stage-graph or gate change needs an
integration test that runs the affected stage pair.

---

## 8. Open questions for the maintainer

1. **P1-03 weighting.** Should an ensemble REJECT consensus veto the quality
   gate, average into it, or only warn? (Recommended: veto on REJECT only, so
   the change cannot make outcomes worse than today.)
2. **P0-03 threshold.** Block export on `hallucinated > 0`, or allow a small
   tolerance? (Recommended: 0 — `stages.py:139` already states the intent.)
3. **P2-01 scope.** Delete the LLM-invented-candidates path outright, or keep it
   behind an explicit `--allow-synthetic-corpus` flag for offline development?
4. **P3-01 dimension.** Reuse `TECHNICAL_QUALITY` for the proof persona, or
   extend `ReviewDimension`? (Recommended: reuse — extending changes the
   weighted-average maths and touches the JSON schema and parser.)
5. **Stage 20 criticality.** It is currently in `NONCRITICAL_STAGES`. Should an
   ensemble REJECT be skippable under `skip_noncritical=True`?
