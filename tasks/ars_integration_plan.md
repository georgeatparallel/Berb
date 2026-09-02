# ARS Integration Plan — Research-Integrity Capabilities for Berb

**Status:** W0–W7 all done (W1 fully including producer; W5 fully including stage 22 wiring; W6 fully, both layers, wired into stage 19; W7 as a scoped slice — see its entry). W8.2 (AI disclosure) done and wired. W8.1 (reporting checklists) mechanism done; stage-20 auto-selection **permanently deferred by explicit user decision** (2026-09-02) — not "pending," closed. Remaining open items: the dual-license email (needs the user to send it) and the two named, out-of-scope gaps noted in W7's own entry.
**Author:** planning pass, 2026-08-31
**Source of ideas:** [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) (ARS) v3.21.1 by Cheng-I Wu
**Supersedes:** nothing. Complements `tasks/hardening_plan_2026-08-13.md` and `tasks/arch_hardening_plan.md`.

**Progress log**

- 2026-08-31 — W0 (`berb/integrity/findings.py`: `Severity`, `CheckId`,
  `Finding`, `gates()`) landed. 19 tests, 100% coverage, mypy/ruff clean,
  added to the mypy ratchet.
- 2026-08-31 — W2 (`berb/literature/retraction.py`) landed **and wired**:
  - `parse_retraction`/`screen_bibliography` (pure) plus `resolve_retraction`
    (cache-first network shell: `_fetch_crossref_message`,
    `_fetch_openalex_work`, both mocked in tests — no real network in CI).
  - **Stage 5** (`LITERATURE_SCREEN`, advisory): rows with a `doi` get
    screened; writes `retraction_findings.json` when non-empty; never fails
    the stage. Wired in `berb/pipeline/stage_impls/_literature.py`.
  - **Stage 23** (`CITATION_VERIFY`, enforcing): verified citations with a
    resolved DOI get screened; `findings.gates(mode)` decides
    `StageStatus.FAILED` vs `DONE` — `draft` mode never fails (matches
    `IntegrityConfig`'s documented "warn only" contract), `submission`/
    `strict` fail on a `RETRACTED`/`CONCERN` finding. Wired in
    `berb/pipeline/stage_impls/_citations.py`.
  - New `IntegrityConfig.retraction_ack: tuple[str, ...]` field (additive,
    default `()`) — an explicit, audited override for citations kept
    despite an adverse event; downgrades severity to `INFO` without hiding
    the finding.
  - 44 tests total (31 unit + 3 stage-5 wiring + 7 stage-23 wiring + 3
    pre-existing regression checks), 96%+ coverage, mypy/ruff clean.
  - `python scripts/check_reachability.py --allowlist .reachability-allowlist`
    now shows `berb.literature` unreachable LOC dropped from 8072/15 modules
    to 2181/5 as a side effect of the new import edges — no allowlist
    changes needed, and the drop is real (not threshold tolerance).
- 2026-08-31 — W3 (`berb/integrity/uncited.py`: `is_uncited_assertion`,
  `detect_uncited`, `SentenceRef`) landed **and wired**:
  - Added `split_sentences(text, source_label=...)`: a pure, stdlib-only
    sentence splitter (punctuation+case boundary heuristic, strips fenced
    code blocks first, `"{label}:{line_no}"` locators). No NLP dependency.
  - Found and fixed a real bug while adding coverage for it: `_RE_NUMBER`
    was `\d{1,3}`, which structurally can never match a 4+ digit span (a
    `\b\d{1,3}\b` pattern can't find a trailing boundary mid-run) — so the
    year-guard in `_is_guarded_number` was dead code AND any real
    quantifier like "1000 samples" was silently invisible to the detector.
    Widened to `\d{1,6}`; both now work, both now covered by a test.
  - Found and fixed a real O(n²) bug in `split_sentences` itself: building
    `adjacent_text` as "every other fragment on the line, joined" is
    quadratic in fragments-per-line. Capped at
    `_MAX_FRAGMENTS_FOR_ADJACENCY = 30` (marked `# ponytail:`) — realistic
    prose never approaches this; a caught-by-its-own-ReDoS-regression-test
    adversarial 2000-fragment line went from 2.03s to sub-millisecond.
  - **Stage 17** (`PAPER_DRAFT`, advisory): after the existing best-effort
    claim-manifest build, screens the finished draft and writes
    `uncited_findings.json` when non-empty; never fails the stage. Wired in
    `berb/pipeline/stage_impls/_paper_writing.py`, right beside the
    pre-existing `_build_draft_claim_manifest` call (same
    try/except-and-log-debug pattern).
  - 46 tests total (43 unit incl. 12 new split_sentences tests + 3 stage-17
    wiring tests), 98%+ coverage, mypy/ruff clean.
- 2026-08-31 — W4 (`berb/literature/paper_mill.py`: `load_corpus`,
  `screen_text`, `PhraseCorpus`) landed **and wired**:
  - New `berb/data/tortured_phrases.yaml` — a small (6-entry) starter
    corpus, explicitly attributed to the primary academic source (Cabanac,
    Labbé & Ionescu 2021, arXiv:2107.06751), not vendored from ARS. File
    header documents this is illustrative-only and points to the
    Problematic Paper Screener's own dataset for real coverage; loader
    accepts a `path` override for that.
  - Matcher: NFKC + casefold + punctuation-as-space normalization, sliding
    n-gram window (2-4 words) over a frozenset per n — literal string
    matching only, corpus entries never compiled as regex.
  - Loader validates corpus size (1 MB cap), entry count (20k cap),
    per-phrase length (200 chars) and rejects control characters; degrades
    to an empty `PhraseCorpus` (guaranteed no-op) on any load failure
    rather than raising.
  - Every finding is `Severity.ADVISORY` — never gates below `strict` mode,
    matching the plan's "risk marker, not an authorship judgment" design.
  - **Stage 5** (`LITERATURE_SCREEN`, advisory): corpus loaded once per
    stage call, each shortlisted candidate's title+abstract screened;
    writes `paper_mill_findings.json` when non-empty; never fails the
    stage. Wired in `berb/pipeline/stage_impls/_literature.py`, right
    beside the W2 retraction check.
  - 29 tests total (26 unit + 3 stage-5 wiring), 97.6% coverage, mypy/ruff/
    bandit clean (bandit: zero findings, not just filtered-Low).
- 2026-09-01 — W1 (`berb/integrity/anchors.py`: `Anchor`, `AnchorKind`,
  `make_anchor`, `MarkerRef`, `parse_markers`, `strip_markers`,
  `verify_anchors`) — **core + schema + export safety landed; consumer
  (stage 23) and producer (LLM prompt-side generation) deliberately not
  wired this pass** — the largest, most architecturally sensitive item in
  the plan, split rather than rushed:
  - Marker syntax `<!--berb-cite key=... kind=quote|page|section|paragraph
    id=...-->`. Anchor id is a derived `sha256(key|kind|normalized_value)`
    hash, never accepted from a caller — `make_anchor`'s signature has no
    id parameter at all, so an LLM cannot forge a mismatched id (asserted
    via `inspect.signature` in the test suite, not just by convention).
  - `verify_anchors` never renders "no stored source text" as "verified" —
    that case is `ANCHOR_UNVERIFIABLE` (`INFO`), matching W2's UNKNOWN
    discipline. `page`/`section`/`paragraph` anchors always report
    `ANCHOR_UNVERIFIABLE` too, since this runtime doesn't track a cited
    work's internal structure — never claims a check that wasn't performed.
  - Schema: `ClaimRecord.anchors: tuple[Anchor, ...] = ()` and
    `ClaimManifest.schema_version: int` (both additive; a v1 manifest with
    neither key loads unchanged — regression-tested directly).
  - **Stage 22** (`EXPORT_PUBLISH`) safety wiring: `strip_markers()` applied
    once, at the single earliest point `final_paper` stabilizes — traced
    the data flow through all 4 `paper_final.md` write sites plus the
    `final_paper_latex` → `tex_source` → `paper.tex` derivation to confirm
    one early strip covers every exported artifact rather than patching
    N write sites individually. Regression-tested: a marker embedded in
    `paper_revised.md` does not survive into `paper_final.md`.
  - 36 anchors unit tests (100% DoD checklist: marker round-trip, all
    `make_anchor`/`Anchor.from_dict` rejects, quote match under
    NFKC/whitespace/case, quote mismatch → BLOCK, missing source text →
    INFO not pass, path-traversal cite_key rejected, ReDoS-bounded on
    adversarial marker text AND on a 2.4M-char source-text haystack) + 5
    schema tests + 2 export-safety regression tests = 43 new tests, 97.9%
    coverage on anchors.py, mypy/ruff/bandit clean (bandit: zero findings).
  - **Stage 23** (`CITATION_VERIFY`) consumer wiring landed: aggregates
    `anchors_by_id` from the best-effort claim manifest built at stage 17
    (empty until the producer ships), derives `bib_keys` from
    `references.bib`, calls `verify_anchors` against `paper_final.md` with
    an empty `source_texts` map (Berb has no per-citation full-text store
    wired into the pipeline yet, so every `quote` anchor correctly reports
    `ANCHOR_UNVERIFIABLE` rather than a false "verified" — documented as a
    real limitation, not silently accepted). `findings.gates(mode)` decides
    `StageStatus.FAILED` vs `DONE`, same pattern as the W2 retraction gate;
    `ANCHOR_UNVERIFIABLE` is `INFO` so it never gates in any mode.
    7 new wiring tests (no-markers no-op, unresolved-marker fails in
    strict/passes in draft, resolved-quote-no-source-text is INFO-never-
    fails, empty-keys-and-no-manifest skips computation entirely via the
    wiring's own guard, verification-exception doesn't crash the stage,
    corrupt-manifest doesn't crash the stage), mypy/ruff/bandit clean.
  - **Still explicitly not done at that point**: prompt-side changes so
    the drafting LLM actually emits `key`/`kind`/`value` for empirical/
    comparative claims (the producer side). Landed in a later pass below,
    without touching `prompts.default.yaml`.
- 2026-09-01 (later) — W1 producer landed. The drafting LLM emits an
  inline pseudo-marker while writing prose: `[[berb-anchor: cite_key |
  kind | quote]]`. Chosen because it does not collide with the existing
  `\cite{}`/`[key]` citation syntax, and because it is easy for an LLM to
  produce reliably inside prose without JSON mode.
  - Injected via the same `citation_instruction` string
    `_write_paper_sections` already interpolates three times for its
    section prompts. No new template variable, no `prompts.default.yaml`
    edit: appended to the same Python-built instruction string right
    after the existing citation rules, only when real references exist.
  - `_resolve_draft_anchors()` in `_paper_writing.py`: finds every
    pseudo-marker with a bounded regex matching `anchors.py`'s existing
    `MARKER_RE` discipline (same character-class bounds, no nesting,
    ReDoS-safe by construction), calls `make_anchor()` for each (so the
    anchor id is always the real hash-derived one, never LLM-supplied),
    and replaces the pseudo-marker with the final `<!--berb-cite...-->`
    marker. Runs before `paper_draft.md` is ever written to disk, so the
    same file stage 23 later parses and stage 22's `strip_markers`
    strips already carries only real markers.
  - A pseudo-marker whose cite_key/kind/value fails validation is dropped
    entirely, both the literal text and any anchor. A pseudo-marker the
    regex never matches at all (disallowed character in the key, or an
    unrecognized kind) passes through as literal text unchanged, so a
    near-miss the LLM might have meant as a real anchor is visible rather
    than silently vanishing.
  - `_build_draft_claim_manifest()` gained an `anchors` keyword parameter
    (additive; existing callers unaffected). Each resolved anchor is
    recorded as its own `ClaimType.CITATION` claim rather than force-
    matched onto one of the separately, heuristically extracted numeric
    claims, which have no reliable correspondence to where the LLM chose
    to place a citation anchor.
  - Caught one real test-authoring mistake while writing this: a test
    assumed a path-traversal-shaped cite_key (`../evil`) would be
    regex-matched then rejected by `make_anchor`. It never matches the
    regex at all, since `/` is outside the cite_key character class, the
    same "not matched, passes through literally" behavior already
    verified for an unrecognized `kind`. Fixed the test to check that
    actual behavior, and added a separate test that does exercise the
    regex-matches-then-`make_anchor`-rejects path with a whitespace-only
    value.
  - 15 new tests in `tests/test_integrity.py` (`TestResolveDraftAnchors`,
    `TestPaperDraftAnchorProducerWiring`) plus the 8 pre-existing
    `paper_draft` tests in `tests/test_berb_executor.py`, all passing
    (`pytest tests/test_integrity.py -q` -> 60 passed;
    `pytest tests/test_berb_executor.py -k "paper_draft or PaperDraft" -q`
    -> 8 passed). `mypy berb/pipeline/stage_impls/_paper_writing.py` ->
    no issues found. `ruff check`/`ruff format --check` clean.
    `scripts/check_reachability.py` still passes.
  - This mechanism depends on the LLM actually following the instruction,
    which is marked optional in the prompt. Not yet verified against a
    real LLM call end to end, only against the deterministic parsing/
    resolution logic and the template-fallback (no-LLM) path. Whether the
    instruction reliably produces real, non-fabricated quotes from an
    actual model has not been measured.
- 2026-09-01 — W6 Layer A (`berb/integrity/revision_guard.py`:
  `conserved_tokens`) landed **and wired**:
  - Deterministic, no LLM: numeric literals and citation keys present
    before a revision must still be present after. Numbers compared after
    stripping trailing zeros (`"62.0"` == `"62"`) so a legitimate
    rounding/reformat isn't flagged — the plan's own named false-positive
    shape, handled rather than just documented as a caveat.
  - Found and fixed a real regex bug caught by the test suite itself: the
    number-token pattern's trailing `\b` after an optional `%` backtracked
    the `%` away on inputs like `"62%."` (no word-boundary transition
    exists right after `%` when followed by `.`, since neither is a word
    character) — silently extracting `"62"` instead of `"62%"`. The
    trailing `\b` was redundant anyway (`\d+` is already self-terminating
    at the first non-digit) and actively wrong here; removed.
  - Layer B (semantic claim-strength drift, LLM-advisory) is **not
    implemented** — explicitly out of scope for this pass per the plan's
    own two-layer split; `revision_guard.py`'s module docstring records why
    a deterministic and a semantic check are necessary-but-not-sufficient
    complements, not substitutes.
  - **Stage 19** (`PAPER_REVISION`, advisory): diffs `draft` against
    `revised` right before the final write; writes `revision_findings.json`
    when non-empty; never fails the stage — matches W3's stage-17 advisory
    pattern (this plan does not gate PAPER_REVISION anywhere; a future
    stage-20 enforcement point, if wanted, is a separate decision).
  - 19 unit tests (incl. the regex-bug regression, rounding-tolerance,
    pure-reordering-is-clean, and a bounded-runtime check on a 50k-word
    input) + 5 stage-19 wiring tests = 24 new tests, 100% coverage on
    `revision_guard.py`, mypy/ruff/bandit clean.
- 2026-09-01 — W5 (`berb/llm/cross_model.py`) landed as a **policy layer
  only**; no stage wiring:
  - **Significant finding, not just an implementation note**: the plan
    originally pointed at extending `berb/llm/extended_router.py`'s
    `ExtendedRouter.get_provider_for_role`. Investigation found
    `ExtendedRouter._create_provider` returns a `_MockProvider` (its own
    docstring: "In production, this would create the actual provider
    instance") and `ExtendedRouter` is imported nowhere under
    `berb/pipeline/` — confirmed via
    `python scripts/check_reachability.py`. It is not live infrastructure;
    building on it would have produced code that looks wired but isn't.
    Built against `berb.llm.create_llm_client(RCConfig)` /
    `berb.llm.client.LLMClient(LlmConfig)` instead — the real, reachable
    factory — resolving a second provider as a standalone `LlmConfig` from
    env vars (`BERB_CROSS_MODEL_PROVIDER`/`_MODEL`/`_API_KEY_ENV`), the
    same shape as Berb's existing optional-provider switches.
  - `provider_family()` — handles both bare provider names (Berb's native
    `LlmConfig.provider` values) and `"family/model"` OpenRouter-style ids.
  - `resolve_adversarial_llm_config()` — never a same-family fallback:
    returns `None` (not the primary provider) when nothing is configured,
    the resolved family matches the primary, or the named API-key env var
    isn't actually set.
  - New `SecurityConfig` fields, all off/zero by default:
    `cross_model_verification`, `cross_model_consent_granted` (both must
    be true — enabling one alone is a configuration intent, not consent),
    `cross_model_max_usd_per_run` (zero = no budget granted = treated as
    already exceeded, fail closed).
  - `build_cross_model_payload()` — allowlist (claim text, anchor quotes,
    reference metadata only), every field length-capped; a metadata key
    like `api_key` or `file_path` is silently dropped, not merely
    discouraged — regression-tested directly.
  - `parse_cross_model_verdict()` — JSON-only typed parse; an
    eval/exec-injection-shaped payload (`"__import__('os').system(...)"`)
    is inert data that fails to parse as a known verdict, never executed
    — regression-tested, referencing the same class of bug fixed in
    commit 334c7a0.
  - `cross_model_unverified_finding()` — the explicit, visible `INFO`
    result when verification can't run; never reads as "verified".
  - **Explicitly not done**: no pipeline stage actually calls any of this
    yet (`berb/pipeline/paper_verifier.py`, `hallucination_detector.py`,
    `berb/review/ensemble.py` are the plan's named consumers). That wiring
    needs its own prompt design and stage-specific integration this
    module deliberately doesn't decide — same honesty pattern as W1's
    producer side. `cross_model.py` shows up in
    `check_reachability.py`'s unreachable count as a result; that is
    correct and expected, not a check failure to paper over.
  - 35 tests (family resolution incl. same-family-never-falls-back,
    consent-gate truth table, cost-ceiling boundary cases, payload
    allowlist enforcement, verdict parsing incl. the injection-payload
    test), mypy/ruff/bandit clean.
- 2026-09-01 — W5 stage wiring completed: `_run_cross_model_double_check()`
  wired into **stage 22** (`EXPORT_PUBLISH`), called right after the
  existing hallucination check when `cross_model_enabled(config.security)`;
  writes `cross_model_findings.json` (only when non-empty) alongside the
  stage's other artifacts.
  - **Real bug found and fixed during wiring, not just a missing test**:
    `berb.llm.client.LLMClient.__init__` reads `config.rate_limit_enabled`
    unconditionally — it needs its own runtime `LLMConfig`
    (`berb/llm/client.py`), not `berb.config.LlmConfig`'s declarative
    YAML-section type that `resolve_adversarial_llm_config()` originally
    returned. Passing the declarative type raised
    `AttributeError: 'LlmConfig' object has no attribute 'rate_limit_enabled'`
    — caught by the first real test run against `LLMClient`, not by
    reasoning about the types in isolation.
  - First fix attempt changed `resolve_adversarial_llm_config()` to return
    the client's `LLMConfig` directly, resolving the real API key value
    into it. That broke an existing security-property test,
    `test_resolved_config_never_carries_the_key_value_itself` — the
    declarative return type was deliberately kept secret-free so a
    resolved config could be logged/passed around without leaking the key.
    Correct fix: `resolve_adversarial_llm_config()` keeps its original
    contract and return type (declarative, `api_key_env` only); a new
    `build_adversarial_client_config()` resolves the real key into a
    client `LLMConfig` *only* at the point `LLMClient` is actually
    constructed in `_export.py`, never stored or logged.
  - `_MAX_CROSS_MODEL_CHECKS = 5` bounds calls per run regardless of how
    many issues the primary model flagged; cost-ceiling check happens
    before every call, not just once.
  - 8 new tests (`tests/test_stage_export_cross_model.py`): success path,
    unparseable/failed adversarial-provider response, cost-ceiling cutoff,
    the `_MAX_CROSS_MODEL_CHECKS` bound, same-family env rejection.
    `python -m pytest tests/test_llm_cross_model.py
    tests/test_stage_export_cross_model.py -q` → `43 passed`;
    `python -m pytest tests/ -k "export or cross_model" -q` (broader
    regression sweep) → `96 passed`; mypy and ruff clean on both changed
    files.
- 2026-09-01 — W6 Layer B (`berb/integrity/revision_guard.py`:
  `ClaimDriftCandidate`, `find_claim_drift_candidates`,
  `strength_advisory`) landed **and wired into stage 19**:
  - LLM-advisory only (`Severity.ADVISORY`, never blocks); the LLM is
    injected as a plain `Callable[[str], str]`, never imported — keeps
    `revision_guard.py` dependency-free of `berb.pipeline`/`berb.llm` and
    fully skippable via `llm=None`, exactly per the plan's design note.
  - `find_claim_drift_candidates()`: two-pass sentence alignment (reuses
    W3's `split_sentences`). Pass 1 matches identical-normalized-text
    sentences regardless of position and drops them — this is what makes
    pure reordering never a candidate, per the plan's explicit
    requirement. Pass 2 greedily pairs the remainder by `difflib`
    similarity, discarding pairs below `_MIN_DRIFT_SIMILARITY = 0.4`
    (unrelated additions/removals, not drift). Bounded to
    `_MAX_DRIFT_CANDIDATES = 20` and `_MAX_SENTENCES_FOR_ALIGNMENT = 200`
    so the O(n·m) pairing step can't blow up on a large revision.
  - `strength_advisory()`: JSON-only verdict parse, same
    never-`eval`/`exec` discipline as `berb.llm.cross_model`'s verdict
    parsing (commit 334c7a0); a call exception or unparseable response
    for one candidate is skipped, never raised — matches this module's
    must-never-fail-the-stage discipline.
  - **Stage 19** (`_review.py`, `_execute_paper_revision`): wired
    alongside the existing Layer A check, reusing the *same* `llm` client
    already used to generate the revision. Deliberately no new consent
    gate here (unlike W5): Layer B sends the paper's own before/after
    sentences to the already-authorized primary provider, not a second
    vendor — the plan's design note calls this "skippable by
    configuration" via the `llm=None` injection, not a new attack
    surface requiring its own opt-in.
  - 19 new unit tests (incl. an injection-payload-is-inert-data
    regression, mirroring the cross-model verdict-parsing test) + 3 new
    stage-19 wiring tests (`tests/test_stage_paper_revision_guard.py`,
    using a `_SequencedFakeLLMClient` so the shared llm instance can
    return revision prose on the first call and a JSON verdict on
    later calls). `python -m pytest tests/test_integrity_revision_guard.py
    tests/test_stage_paper_revision_guard.py -q` → `40 passed`;
    `python -m pytest tests/ -k "revision or integrity or review" -q`
    (broader regression sweep) → `277 passed`; mypy/ruff clean on all
    four changed files.
- 2026-09-01 — W7 (`tests/fixtures/seeded_defects.py`,
  `tests/test_eval_seeded_defects.py`) landed **as a scoped slice**, plus
  the parked-module disposition this workstream's definition of done
  requires:
  - **Design correction, found the same way as W5's `ExtendedRouter`
    finding**: this plan's original W7 section pointed at wiring the
    seeded corpus into `berb/integrity/eval/hidden_eval.py`'s "test
    tier". Reading that module's actual implementation shows it scores a
    *single* paper's overall quality across three visibility-tiered LLM
    dimensions for the pipeline's own search/selection optimization loop
    — unrelated to measuring `berb/review/ensemble.py`'s reviewer
    recall, and partly a stub itself (`claim_validity`/
    `citation_correctness` are hardcoded `0.5`, pending a "TODO(E8)"
    integration that never landed). The plan section was written without
    reading `hidden_eval.py` closely enough. Corrected design instead
    exercises Berb's own existing deterministic checks directly
    (`verify_anchors`, `detect_uncited`) for the no-LLM tier, and the
    real `AutomatedReviewerEnsemble` for the LLM tier — see
    `tests/fixtures/seeded_defects.py`'s module docstring for the full
    correction.
  - **`finding_reproduction.py` disposition, resolved per this
    workstream's own rule ("wire it or delete it, do not leave it parked
    for a third quarter")**: deleted. Its `_run_reproduction` was a
    `random.random()` coin flip against a hardcoded per-difficulty
    success-probability table — never real experiment execution — and
    its known-finding corpus (KRAS mutations, Huntington's CAG repeats,
    ResNet, "Attention Is All You Need") measured reproduction of
    historical results, not recall on injected paper-draft defects. Not
    W7's corpus. `.reachability-allowlist`'s D-04 entry closed with a
    note (matching the existing D-01 closure pattern); doc mentions
    corrected in `berb/integrity/__init__.py`, `berb/integrity/eval/
    __init__.py`, `.claude/skills/berb-integrity/SKILL.md`, and
    `CLAUDE.md`'s module table (`berb/integrity/` moved from "partial" to
    "yes" — deletion was the only remaining unwired reason cited).
  - **Scoped, not the full 5-defect-type corpus** the plan originally
    sketched. Deterministic tier covers two defect types that map onto
    an *existing* Berb check with zero new detection logic:
    `FABRICATED_CITATION` (`verify_anchors`, `ANCHOR_QUOTE_MISMATCH` /
    `BLOCK`) and `UNCITED_EMPIRICAL_CLAIM` (`detect_uncited`,
    `UNCITED_ASSERTION` / `WARN`); each paired with a clean control
    fixture so the same run also checks for false positives. LLM tier
    covers one fixture (`UNSUPPORTED_COMPARATIVE_CLAIM`) run through the
    real `AutomatedReviewerEnsemble`, `@pytest.mark.llm` +
    `skipif(not os.environ.get("ANTHROPIC_API_KEY"))` (same pattern as
    `tests/test_minimax_provider.py`), reporting per-persona recall
    rather than asserting pass/fail — the plan's own design note says an
    LLM's judgment should not gate CI. **Explicitly not covered**: "a
    number that contradicts the results table," "a dropped ablation,"
    and "a p-value with no test behind it" — none has an existing
    deterministic checker in this codebase, and building three new ones
    was out of scope for this pass. Named here rather than silently
    dropped.
  - `python -m pytest tests/test_eval_seeded_defects.py -v -rs` (via
    `rtk proxy` to see the real skip line, not the token-saving summary)
    → `4 passed, 1 skipped` — `SKIPPED [1]
    tests\test_eval_seeded_defects.py:66: ANTHROPIC_API_KEY not set`, the
    LLM-tier test correctly self-skipping with no key present, never
    executed against a real provider in this pass.
    `python -m pytest tests/test_integrity.py tests/test_eval_seeded_defects.py
    tests/optimization/ -q` → `144 passed`. `python scripts/
    check_reachability.py` → `[OK] Reachability check passed.` after the
    deletion. mypy/ruff clean on all changed files.
  - Spawned a separate follow-up task (not part of this commit) for an
    unrelated, pre-existing finding surfaced while updating docs:
    `docs/CODEBASE_MIND_MAP.md` (and `TODO.md`) describe an entire
    `berb/validation/` package (`claim_tracker.py`,
    `manuscript_self_check.py`, etc.) that does not exist anywhere in
    the repo — the real code lives in `berb/integrity/` with a different
    file list. Out of scope for W7 itself; flagged because the mind map
    is read every turn by the `berb-arch` hook.
- 2026-09-01 — W8.2 (`berb/writing/disclosure.py`: `DisclosureFacts`,
  `generate_disclosure_statement`) landed **and wired**:
  - Generic, factual AI-usage disclosure statement built from what the
    run's own config can actually attest to (`config.llm.provider`/
    `primary_model`, whether W5 cross-model verification ran) — not a
    specific venue's required wording. Matches the plan's `format_profile`
    precedent: mechanism shipped, venue-specific policy *content* stays
    out-of-tree; the scholar adapts the generated generic statement.
  - **Stage 22** (`EXPORT_PUBLISH`): writes `ai_disclosure.md` right
    before the stage's single final return; best-effort — a generation
    failure is caught and logged, never blocks export of the paper
    itself. Wired in `berb/pipeline/stage_impls/_export.py`.
  - W8.1 (PRISMA/CONSORT/STROBE reporting-guideline checklists) is **not
    implemented** — lower-priority "Tier 3 domain pack" per the plan's own
    ranking, deferred rather than rushed alongside everything else this
    session.
  - 8 tests (6 unit + 2 stage-22 wiring incl. a generation-failure-does-
    not-block-export regression), mypy/ruff/bandit clean.
- 2026-09-01 — W8.1 (`berb/writing/reporting_guidelines.py`:
  `ChecklistItem`, `Checklist`, `load_checklist`, `evaluate_checklist`)
  landed as **mechanism only; deliberately NOT wired into stage 20**:
  - Checklist-as-data + one generic evaluator, exactly per plan §12 —
    PRISMA/CONSORT/STROBE differ in items, not evaluation logic, so
    adding a guideline is a new YAML file, not new code.
  - Three small starter checklists (`berb/data/reporting_guidelines/
    {prisma,consort,strobe}.yaml`, 8 items each), paraphrased in plain
    language describing well-known public reporting-guideline concepts —
    NOT verbatim EQUATOR Network checklist text — each attributed to its
    primary source (Page et al. 2021 BMJ; Schulz et al. 2010 BMJ;
    von Elm et al. 2007 Lancet).
  - **Why not wired**: the plan's own risk register names "false-positive
    fatigue" as the single **highest-likelihood** risk in this entire
    integration. Auto-applying a CONSORT (randomized-trial) or STROBE
    (observational-study) checklist to the common case — an ML/CS paper —
    would generate irrelevant advisory noise on every run, which is
    precisely that risk materializing, not a hypothetical. Domain-aware
    guideline selection needs validated accuracy before it's safe to wire
    unattended; that validation didn't happen this pass, so the mechanism
    ships and the auto-selection decision is left for a follow-up rather
    than guessed at.
  - Loader shares `berb.literature.paper_mill.load_corpus`'s fail-safe
    discipline: size cap, entry-count cap, malformed-entry skip, any
    failure degrades to an empty (no-op) checklist rather than raising.
  - New `CheckId.REPORTING_GUIDELINE` enum member (additive).
  - 19 tests (evaluator behavior, loader validation/caps, all 3 default
    checklists load and produce findings on a thin paper), mypy/ruff/
    bandit clean.
- Two housekeeping items resolved 2026-09-01 (separate commit): the stale
  `pyproject.toml:160` `cross_model_reviewer.py` ruff entry (file
  confirmed not to exist, removed), and CLAUDE.md's LLM Routing section
  (named two files that never existed, `model_router.py`/
  `model_cascade.py`; corrected to name the real routers and record that
  `extended_router.py` is not live infrastructure per the W5 finding).
- 2026-09-02 — **W8.1 stage-20 wiring: closed, permanently deferred, by
  explicit user decision.** Before attempting it, checked whether
  "validated domain detection" (the condition this deferral was waiting
  on) actually exists anywhere in Berb. It does not, in a way that
  matters: `berb/pipeline/_domain.py`'s `_detect_domain` classifies
  *academic subject* (ml/physics/chemistry/economics/mathematics/
  engineering/biology) from the topic string, not *study design*
  (randomized trial vs. observational vs. systematic review) — the axis
  PRISMA/CONSORT/STROBE actually need. A "biology"-domain paper about
  CRISPR editing in mice is not a CONSORT trial; there is no domain in
  that classifier that reliably signals "this is a human clinical
  trial". Also checked `IntegrityConfig.auto_strict_domains`
  (`("biomedical", "clinical", "legal", "finance", "policy")`) as a
  possible existing hook — it has no consumer anywhere under
  `berb/pipeline/` and its values don't even match `_detect_domain`'s
  domain IDs. Both are dead ends, not partial infrastructure to build
  on. Making W8.1 safe would mean building a new study-design classifier
  from scratch and then validating its precision — itself a W7-shaped
  measurement problem — which is out of proportion to a "wire an
  existing flag" task. Presented this finding and two options (build the
  narrow opt-in classifier now, or close the deferral as final) to the
  user; the user chose to close it. `berb/writing/reporting_guidelines.py`
  stays exactly as W8.1 shipped it: mechanism-only, not called from any
  stage. Revisit only if a concrete need for auto-selection (not just
  "the plan mentions it") comes up.
- Remaining: dual-license email (needs the user to send it, not
  something an agent can dispatch), plus the two gaps W7's own entry
  names as explicitly out of scope (three of the plan's five original
  seeded-defect types have no existing deterministic checker; the LLM
  tier's fixture has never been run against a real provider), and the
  plan's original stage-20 (`QUALITY_GATE`) blocking touchpoint for
  uncited-assertion (stage 17 only ships advisory, as asked).

---

## 0. Summary

ARS is a research-integrity toolkit with roughly 200 deterministic verification
scripts, a contract/schema layer, and a large prompt corpus. Berb already
overlaps it on citation existence verification, reviewer ensembles, claim
manifests, evidence registries, and hidden-consistent evaluation. What Berb
lacks is the *screening* layer: checks that ask whether a source is fit to cite,
whether a claim is anchored to a specific passage, and whether a revision moved
a claim without permission.

This plan adds nine workstreams (W0–W8). Seven produce code; W0 is a legal gate
that blocks all of them; W8 is data, not code.

**Two constraints govern everything below.**

### Constraint 1 — License (hard blocker)

ARS is **CC BY-NC 4.0**. Berb is **MIT** (`pyproject.toml:20`,
`LICENSE`). These are incompatible in both directions:

- CC BY-NC's ShareAlike-free but NonCommercial term propagates to adapted
  material. Vendoring any ARS file — Python source, JSON schema, prompt
  markdown, reference doc, curated phrase list — makes the derived Berb file a
  CC BY-NC adaptation, which is not MIT-licensable and forbids commercial use
  downstream.
- CC licenses are also not designed for software; the author states the NC term
  is deliberate ("restricts commercial use by design", `POSITIONING.md`).

**Rule for this entire plan: zero ARS bytes enter this repository.** Not
copied, not "adapted", not pasted into a prompt file. What transfers is the
*method* — algorithms, rule shapes, taxonomy names that are facts about the
domain — which is not copyrightable. Expression is. See W0 for the process.

### Constraint 2 — Positioning inversion

ARS's `POSITIONING.md` explicitly rejects three mechanisms as anti-patterns:
end-to-end autonomous research pipelines, autonomous idea generation, and
autonomous experiment execution. Berb is all three by design.

Consequence: **take the verification machinery, leave the copilot
positioning.** The integrity checks are agnostic about who drives. The
mandatory-human-checkpoint protocol, the 27-mode system, the Socratic
non-generation boundary, and the "Material Passport as reset boundary" are
guardrails for a tool that refuses to act alone — grafting them onto Berb
fights `--auto-approve` and duplicates the event-sourced state machine in
`berb/pipeline/stages.py`.

### What this plan explicitly does not do

| Rejected | Why |
|---|---|
| Material Passport state carrier | `stages.py` event sourcing already does this |
| Ground-truth isolation pattern | `berb/integrity/eval/hidden_eval.py` (HCE) already implements it |
| 27-mode system / Socratic non-generation | anti-fit with autonomous operation |
| ARS's ~200 `check_*.py` CI guards | that is ARS's own repo discipline, not a research capability |
| Chinese-literature client, HEI/QA glossaries | out of Berb's scope |
| Zotero / folder adapters | `berb/literature/zotero_integration.py` exists |
| Human-subjects / IRB pathway resolution | Berb has no human-subjects surface; revisit only if a clinical domain preset lands |

---

## 1. Architecture fit rules

Every workstream below obeys these. They are derived from what the codebase
already does, not invented.

**R1 — Frozen dataclasses + `StrEnum`, `to_dict`/`from_dict`.**
`berb/integrity/claims.py`, `evidence.py`, and `berb/pipeline/contracts.py` all
use `@dataclass(frozen=True)`, `StrEnum` taxonomies, and tuple-typed collection
fields (`SeedValidity.conditions_affected: tuple[str, ...]`). New models match.
No Pydantic in the integrity layer — it isn't used there today, and adding it
for four modules is a dependency for nothing.

**R2 — Checks return findings, they do not raise.**
A screening check that raises kills a 23-stage run over an advisory. Every
check returns a `Finding` list. Gate semantics are applied once, centrally, by
severity — not by each check deciding to blow up.

**R3 — One severity ladder, mapped onto the existing `IntegrityConfig.mode`.**
`berb/config.py:303` already defines `mode: draft | submission | strict` plus
`fail_on_*` switches. New checks feed that machinery; they do not invent a
parallel strictness system.

**R4 — Every new module must be import-reachable from `berb run`.**
`scripts/check_reachability.py` is CI-visible and `.reachability-allowlist`
already carries four parked modules. Nothing in this plan may be added to the
allowlist. A check that ships unwired is a check that does not exist —
CLAUDE.md documents five prior capabilities in exactly that state.

**R5 — Pure core, thin shell.**
All screening logic is pure and offline: no network, no LLM, no filesystem
except through an injected loader. Network already happens in
`berb/literature/*_client.py`; screening consumes what those already returned.
This is what makes the modules cheap to test to 95% and safe to run inside a
gate.

**R6 — Untrusted text stays untrusted.**
Paper text, abstracts, PDF extractions and quotes are attacker-influenceable
(anyone can post to arXiv). Any of it re-entering an LLM prompt goes through
`berb.utils.sanitize.wrap_untrusted`. Any of it reaching a URL goes through
`berb.web._ssrf.check_url_ssrf`.

**R7 — Additive schema evolution only.**
`claim_manifest.json` and `evidence_registry.json` persist across runs and are
re-read by `berb run --from-stage`. New fields are optional with defaults;
`from_dict` tolerates their absence. No field is renamed or removed.

**R8 — New modules join the mypy ratchet.**
`pyproject.toml:215` lists modules with `ignore_errors = false`. New code is
written clean from the start, so every module in this plan is added to that
list in the same PR that creates it. Never removed to make a build pass.

---

## 2. Package layout

```
berb/integrity/
  claims.py           (existing — extended in W1)
  evidence.py         (existing — untouched)
  registry.py         (existing — untouched)
  findings.py         NEW  shared Finding/Severity types           (W0)
  anchors.py          NEW  citation locator anchors                (W1)
  uncited.py          NEW  uncited-assertion detector              (W3)
  revision_guard.py   NEW  token conservation + claim-strength     (W6)
  screening.py        NEW  facade: composes all checks             (W1-W6)
berb/literature/
  retraction.py       NEW  retraction / EoC status                 (W2)
  paper_mill.py       NEW  tortured-phrase risk screening          (W4)
berb/data/
  tortured_phrases.yaml   NEW  provenance-stamped phrase corpus    (W4)
  reporting_guidelines/   NEW  PRISMA/CONSORT/STROBE checklists    (W8)
berb/llm/
  extended_router.py  (existing — extended in W5)
```

**One deliberate abstraction: the facade.** `berb/integrity/screening.py`
exposes a single `screen(...) -> ScreeningReport` that composes every check.
Stages call the facade, not the individual modules. This is the one pattern in
this plan that earns its keep: without it, five checks wire into three separate
`stage_impls/` files and the coupling multiplies. With it, adding a sixth check
touches one file.

Everything else stays as module-level functions. Specifically **do not** build:
a `Checker` abstract base class, a plugin registry for checks (the pipeline
already has one and screening is not a pipeline stage), a Strategy hierarchy
for detection rules, or a config class per check.

---

## 3. W0 — License clearance and shared types (BLOCKING)

Nothing else starts until W0 lands.

### W0.1 — Provenance discipline

Create `docs/legal/ars-provenance.md` recording:

- ARS is CC BY-NC 4.0; Berb is MIT; no ARS file is present in this repository.
- For each borrowed idea: a one-paragraph *method statement* in this plan's own
  words, the ARS concept name it corresponds to, and the primary literature
  source where one exists.
- Attribution: ARS credited in `README.md` and `docs/` as prior art whose
  approach informed Berb's screening layer, with the Zenodo DOI
  (`10.5281/zenodo.20696614`). Attribution is courtesy here, not a license
  obligation, since no licensed material is used.

**Implementation rule.** Write the method spec first (in this document), then
implement from the spec without ARS source open. Never transcribe: regex
literals, phrase-list entries, JSON schema field names, docstrings, error
strings, or file/function names. Where a name is genuinely the domain's term
("tortured phrase", "expression of concern", "retraction"), it is a fact and
may be used.

**Preferred escape hatch:** email the ARS author asking for an MIT or Apache-2.0
dual license on `scripts/`. It costs one message and, if granted, collapses this
constraint entirely. Do this on day one; it does not block starting W0.2.

### W0.2 — Shared finding types

`berb/integrity/findings.py`. Pure data, no logic beyond severity mapping.

```python
class Severity(StrEnum):
    INFO = "info"        # observation, never gates
    ADVISORY = "advisory"  # gates only in strict mode
    WARN = "warn"        # gates in submission and strict
    BLOCK = "block"      # gates in every mode above draft

class CheckId(StrEnum):
    RETRACTION = "retraction"
    UNCITED_ASSERTION = "uncited_assertion"
    PAPER_MILL_RISK = "paper_mill_risk"
    ANCHOR_UNRESOLVED = "anchor_unresolved"
    ANCHOR_QUOTE_MISMATCH = "anchor_quote_mismatch"
    TOKEN_CONSERVATION = "token_conservation"
    CLAIM_STRENGTH_DRIFT = "claim_strength_drift"
    CROSS_MODEL_UNVERIFIED = "cross_model_unverified"

@dataclass(frozen=True)
class Finding:
    check: CheckId
    severity: Severity
    message: str
    locator: str = ""            # "paper.md:412" or a cite_key — never a raw path
    evidence: tuple[str, ...] = ()   # short quoted spans, each length-capped
    remediation: str = ""

def gates(findings, mode: str, cfg: IntegrityConfig) -> tuple[Finding, ...]:
    """Return the subset that must fail the current stage under `mode`."""
```

**Paradigm:** data-oriented. **Pattern:** none beyond value objects — a
`Finding` is a record, and a record with a class hierarchy is a bug waiting to
happen.

`gates()` is the single place gate semantics live (R3). Every stage that
enforces screening calls it. It is ~15 lines and is the highest-value function
in the plan, because it is the only thing standing between "advisory noise" and
"a 23-stage run dies on a false positive".

**Tests:** `tests/test_integrity_findings.py` — the severity×mode truth table,
exhaustively. 12 cases, no mocks.

**Effort:** ~120 LOC + tests. Half a day.

---

## 4. W1 — Citation locator anchors (three-layer citation)

### Problem

Berb verifies that a cited work *exists* (`berb/literature/verify.py`,
`berb/pipeline/citation_verification.py`, four resolvers, three
classifications). It has no concept of *where in that work* a claim is
supported. `grep -i 'anchor|locator'` over `berb/integrity/` returns nothing.

A real paper cited for a claim it does not make passes every current gate. This
is the highest-value gap in the plan, and also the one with the largest blast
radius, which is why it ships fourth rather than first.

### Method spec

A claim carries zero or more **anchors**. An anchor is `(cite_key, kind,
value)` where `kind ∈ {quote, page, section, paragraph}`. The draft text
carries an inline marker adjacent to each anchored claim; markers are HTML
comments so they survive Markdown and are strippable before LaTeX export.

Berb's marker syntax (chosen independently, not ARS's):

```
<!--berb-cite key=he2016deep kind=quote id=a3f19c-->
```

The marker carries an anchor **id**, not the quote itself. The quote lives in
`claim_manifest.json` so the draft stays readable and the payload stays
size-bounded.

Verification, in `CITATION_VERIFY` (stage 23):

1. Every marker's `key` resolves to a BibTeX entry — else
   `ANCHOR_UNRESOLVED`, severity `WARN`.
2. Every marker's `id` resolves to an anchor in the manifest — else
   `ANCHOR_UNRESOLVED`, `WARN`.
3. For `kind=quote`: the quote appears in stored source text for that key,
   compared after Unicode NFKC normalization, whitespace collapse, and
   casefold — else `ANCHOR_QUOTE_MISMATCH`, severity `BLOCK`. A fabricated
   quote is the strongest available signal of a fabricated claim.
4. For `kind ∈ {page, section, paragraph}`: existence checked only if the
   source's structure is known; otherwise `INFO` ("unverifiable locator kind"),
   never a silent pass.

If no source text is stored for a key, the result is
`INFO: anchor unverifiable (no stored full text)` — never "verified". Absence
of evidence is not evidence of support. This mirrors the `SKIPPED` class
`verify.py` already uses.

### Design

**Paradigm:** parse-don't-validate. **Patterns:** Value Object + smart
constructor + tolerant deserialization.

```python
class AnchorKind(StrEnum):
    QUOTE = "quote"; PAGE = "page"; SECTION = "section"; PARAGRAPH = "paragraph"

@dataclass(frozen=True)
class Anchor:
    anchor_id: str          # 6 hex chars, derived, not LLM-supplied
    cite_key: str
    kind: AnchorKind
    value: str              # the quote, page no., or section id
    # private ctor discipline: build only via make_anchor()

def make_anchor(cite_key: str, kind: str, value: str) -> Anchor | None:
    """Smart constructor. Returns None if any invariant fails.

    Invariants: cite_key matches BIBTEX_KEY_RE; kind is a known AnchorKind;
    value is non-empty and <= MAX_ANCHOR_VALUE_CHARS after strip.
    """

MARKER_RE: Final = re.compile(
    r"<!--berb-cite\s+key=([A-Za-z0-9_:.\-]{1,64})\s+"
    r"kind=(quote|page|section|paragraph)\s+id=([0-9a-f]{6})-->"
)

def parse_markers(text: str) -> tuple[MarkerRef, ...]: ...
def strip_markers(text: str) -> str: ...   # called before LaTeX/PDF export
def verify_anchors(
    manifest: ClaimManifest,
    draft_text: str,
    source_texts: Mapping[str, str],
) -> tuple[Finding, ...]: ...              # pure; no I/O
```

Why a smart constructor rather than `__post_init__` validation: the anchor's
inputs come from LLM output. `make_anchor` returning `None` forces the caller
to handle the reject at the parse boundary, so no unvalidated `Anchor` can
exist anywhere downstream. `__post_init__` raising would propagate an exception
into the middle of paper generation instead.

`MAX_ANCHOR_VALUE_CHARS = 300` — named constant, not a magic number, and it is
doing three jobs at once: bounding prompt re-injection size, bounding the
manifest, and keeping quoted extraction well short of anything resembling a
substantial reproduction of a copyrighted source.

### Schema change (R7)

`ClaimRecord` gains `anchors: tuple[Anchor, ...] = ()`.
`ClaimManifest` gains `schema_version: int = 2`.
`ClaimManifest.from_dict` reads v1 manifests (no `anchors` key) as
`anchors=()`. A v1 manifest resumed via `--from-stage PAPER_DRAFT` must load
without error — this is an explicit regression test, not an assumption.

### Wiring

- **Producer** — `berb/pipeline/stage_impls/_paper_writing.py`: the drafting
  prompt requests markers for empirical and comparative claims. Post-generation,
  parse markers, build anchors through `make_anchor`, drop rejects with a
  logged `INFO`. **The LLM never writes the anchor id**; it emits
  `key`/`kind`/`value`, and Berb derives the id as
  `sha256(f"{cite_key}|{kind}|{normalized_value}")[:6]`. This removes a whole
  class of forged-marker failure.
- **Consumer** — `berb/pipeline/stage_impls/_citations.py` (stage 23) calls
  `screening.screen(...)`.
- **Export** — `berb/pipeline/stage_impls/_export.py` calls `strip_markers`
  before any PDF/LaTeX/DOCX artifact is written. Regression test: no
  `berb-cite` substring in any exported artifact.

### Security

- Quotes are untrusted source text. Re-injection into any prompt goes through
  `wrap_untrusted` (R6).
- `cite_key` is never used to build a filesystem path. Source text is fetched
  from the evidence registry by key lookup, never `Path(dir) / cite_key`.
  Explicit negative test with `cite_key="../../etc/passwd"`.
- `MARKER_RE` is anchored, has no nested quantifiers, and every character class
  is bounded (`{1,64}`, `{6}`). ReDoS-safe by construction, with a test asserting
  bounded runtime on a 1 MB adversarial input.

### Tests — `tests/test_integrity_anchors.py`

Marker round-trip; `make_anchor` rejects (bad key, unknown kind, empty value,
over-length value); quote match under NFKC/whitespace/case variation; quote
mismatch → `BLOCK`; missing source text → `INFO` not pass; v1 manifest loads;
`strip_markers` idempotent and total; path-traversal cite_key rejected; ReDoS
bound. Target ≥95% on the module.

**Effort:** ~450 LOC + ~400 test LOC. 3–4 days. Largest item in the plan.

---

## 5. W2 — Retraction and expression-of-concern status

### Problem

Berb can cite a retracted paper with full confidence. Zero coverage today.

### Method spec

Crossref and OpenAlex both return relation/update metadata that names
retraction, expression-of-concern, correction, and reinstatement events.
Berb's clients already fetch these payloads (`berb/literature/openalex_client.py`,
the Crossref path inside `verify.py`). The check is a **pure parse of already-
returned data** — no new endpoint, no new dependency, no new network budget.

Tri-state plus unknown:

```python
class RetractionState(StrEnum):
    NONE = "none"                       # metadata present, no adverse event
    CONCERN = "expression_of_concern"
    RETRACTED = "retracted"
    UNKNOWN = "unknown"                 # no usable metadata
```

`UNKNOWN` is load-bearing. Index coverage of retractions is incomplete, so
"we found nothing" must never render as "clean". `UNKNOWN` maps to `INFO`;
`CONCERN` to `WARN`; `RETRACTED` to `BLOCK`.

Citing a retracted work is sometimes legitimate (a paper *about* the
retraction). The gate is overridable per cite_key via an explicit
`retraction_ack` list in config, which is recorded in the run artifact — an
audit trail, not a silent bypass.

### Design

**Paradigm:** functional core, imperative shell.
**Patterns:** pure mapper. Deliberately **no** `RetractionChecker` class — it
would hold no state and have one method.

```python
def parse_retraction(
    crossref: Mapping[str, Any] | None,
    openalex: Mapping[str, Any] | None,
) -> RetractionRecord: ...    # pure, total, never raises

def screen_bibliography(
    records: Mapping[str, RetractionRecord],
    acknowledged: frozenset[str],
) -> tuple[Finding, ...]: ...  # pure
```

**Caching:** reuse `berb/literature/cache.py`. Retraction status is a different
volatility class from search results — a paper retracted today was clean
yesterday — so it gets its own TTL constant (`RETRACTION_TTL_SEC = 30 days`)
in the same cache, not a second cache implementation.

### Wiring

- `LITERATURE_SCREEN` (stage 5): advisory. Retracted sources surface at
  screening so they can be dropped before they reach the draft.
- `QUALITY_GATE` (stage 20) and `CITATION_VERIFY` (stage 23): enforcing.

Stage 5 is already a `GATE_STAGES` member (`stages.py`), so the plumbing exists.

### Security

Parse-only. All fields treated as untrusted strings; list fields length-capped
before iteration (a hostile or malformed OpenAlex record should not be able to
allocate unbounded memory). No DOI is ever interpolated into a URL by this
module; if a future revision needs one, it uses `urllib.parse.quote` and
`check_url_ssrf`.

### Tests — `tests/test_literature_retraction.py`

Fixture payloads for each state; malformed/missing payload → `UNKNOWN`;
`UNKNOWN` does not gate as clean; acknowledgement override recorded; TTL
expiry. All offline, no network. ≥95%.

**Effort:** ~200 LOC + ~250 test LOC. 1–2 days. **Ship this first** (with W3).

---

## 6. W3 — Uncited-assertion detector

### Method spec

A sentence is flagged when **all three** hold:

1. It contains a quantifier or empirical verb — a number, a percentage, a fuzzy
   quantifier (`most`, `several`, `two-thirds`), or a result verb (`showed`,
   `demonstrated`, `observed`, `confirmed`).
2. It carries no citation — neither a BibTeX `\cite`/`[@key]` form nor a
   `berb-cite` marker (W1), checked on the sentence and a bounded adjacent-
   clause window.
3. It is not definitional (`refers to`, `is defined as`, `we define`, `for the
   purposes of`).

Condition 1's bare-number arm needs a **guard pass**, or the false-positive rate
makes the check unusable. Numbers that are not quantifiers:

- 4-digit years in 1900–2099
- dotted `X.Y.Z` and deeper — version strings and section numbers
- any integer or `X.Y` preceded within a short left window by a structural cue
  (`Section`, `Figure`, `Table`, `Chapter`, `Step`, `Appendix`, `§`)

`GUARD_LEFT_WINDOW_CHARS = 24` — wide enough for `as shown in Figure `, narrow
enough not to reach across a clause boundary.

Severity `WARN`. This check has real false positives and must not block a draft
run; it gates at `submission` and above.

### Design

**Paradigm:** table-driven pure functions.
**Patterns:** predicate composition over a rule table.

Explicitly **not** used: Strategy, Chain of Responsibility, a `Rule` base class.
Three boolean predicates AND'd together do not need a class hierarchy; a
hierarchy here makes the guard pass — the only genuinely tricky part — harder
to read, not easier.

```python
_RE_NUMERIC_QUANTIFIER: Final = re.compile(...)   # module-level, precompiled
_FUZZY_QUANTIFIERS: Final = frozenset({...})
_EMPIRICAL_VERBS: Final = frozenset({...})
_DEFINITION_CUES: Final = tuple([...])

def _has_quantifier(sentence: str) -> bool: ...
def _is_guarded_number(sentence: str, span: tuple[int, int]) -> bool: ...
def _has_citation(sentence: str, adjacent: str) -> bool: ...
def _is_definitional(sentence: str) -> bool: ...

def detect_uncited(
    sentences: Sequence[SentenceRef],
) -> tuple[Finding, ...]: ...   # pure, deterministic, no LLM, no network
```

`SentenceRef` carries `(index, text, adjacent_text, line_no)` so findings can
report `paper.md:412` without the detector touching the filesystem.

### Security — this is the one workstream with a real security bug waiting

**ReDoS.** These regexes run over LLM-generated and PDF-extracted text of
unbounded length, which is exactly the input class an attacker controls.
Requirements, enforced by test:

- No nested quantifiers (`(a+)+`), no ambiguous alternation with overlapping
  prefixes.
- Every quantifier bounded where possible; unbounded `\s*` only against
  single-character classes.
- Per-sentence input length cap (`MAX_SENTENCE_CHARS = 4000`); longer sentences
  are truncated for matching and flagged `INFO: sentence exceeded scan length`.
- `tests/test_integrity_uncited.py::test_no_catastrophic_backtracking` asserts
  a wall-clock bound on pathological inputs (long runs of digits, dots,
  whitespace, and repeated cue words).

### Tests

Positive/negative per condition; each guard shape (year, version triple,
`Section 3.1`, `Table 2`); adjacent-window hit suppresses; definitional
suppresses; combined-condition matrix; ReDoS bound. ≥95%.

**Effort:** ~250 LOC + ~300 test LOC. 2 days. **Ship first, with W2.**

---

## 7. W4 — Paper-mill / tortured-phrase screening

### Method spec

"Tortured phrases" are thesaurus-substituted technical terms characteristic of
paper-mill and plagiarism-laundering output ("artificial neural network" →
"counterfeit consciousness"). A curated phrase list, matched against ingested
literature, is a **risk marker only** — never an authorship judgment, never
blocking. Legitimate papers quote tortured phrases when critiquing them.

Severity `ADVISORY`. Surfaces at `LITERATURE_SCREEN` so a human or the screening
LLM can decide; never gates.

### Data sourcing — do not copy ARS's list

Take the corpus from its actual upstream, the Problematic Paper Screener work
(Cabanac, Labbé, Magazinov), which is the published primary source. This is
both the licensing-clean path and the better-sourced one. Ship as
`berb/data/tortured_phrases.yaml` with a provenance header: source, URL,
snapshot date, upstream license, and entry count. `berb/data/` is already
force-included in the wheel (`pyproject.toml:103`) and excluded from ruff
formatting (`:122`), so it is the right home.

If no adequately-licensed corpus is available, **ship the mechanism with an
empty list and a documented loader**, and let users supply their own. A working
loader with no data is honest; a copied list is a license violation.

### Design

**Paradigm:** data-driven. The logic is trivial; the data is the asset.
**Pattern:** normalized n-gram set membership.

```python
def load_corpus(path: Path | None = None) -> PhraseCorpus: ...
def screen_text(text: str, corpus: PhraseCorpus) -> tuple[Finding, ...]: ...
```

Matching: NFKC-normalize, casefold, collapse whitespace, strip punctuation,
then slide an n-gram window (n = 2..4, the observed phrase lengths) over the
token stream and test set membership. O(n) with stdlib only.

```python
# ponytail: n-gram set membership, O(n·k) for k window sizes. If the corpus
# grows past ~10k phrases or k past 4, switch to Aho-Corasick (pyahocorasick).
```

Entries are matched as **literals, never compiled as regex** — a corpus file is
data from outside the repo, and interpreting it as a pattern language is a
code-injection surface for no benefit.

### Security

Corpus load is validated: file size cap, entry count cap, per-entry length cap,
entries rejected if they contain control characters. Unicode normalization is
NFKC + casefold — deliberately chosen so confusable-character evasion is
folded away rather than creating a bypass. The loader never evaluates, never
compiles, never imports from the data file.

### Tests — `tests/test_literature_paper_mill.py`

Known-phrase hit; near-miss no-hit; confusable/homoglyph variant still hits;
empty corpus is a valid no-op; oversized corpus rejected; entry with regex
metacharacters is matched literally, not as a pattern; advisory severity never
gates in `submission`. ≥95%.

**Effort:** ~180 LOC + ~200 test LOC + data. 1–2 days.

---

## 8. W5 — Cross-model verification

### Problem

Berb self-checks with the same model family that generated the text. Same
training distribution, same blind spots. ARS cites a stress test where 31% of
68 AI-generated citations had problems and *all* passed three rounds of
same-model integrity checking. Berb's `hallucination_detector.py` and
`paper_verifier.py` are structurally exposed to this.

### What already exists

More than expected. `berb/llm/extended_router.py` has
`get_provider_for_role(role, ...)`, `_apply_provider_diversity(model, role)`,
and a `use_diversity` flag, plus a fallback chain. Seven providers are
supported. **Extend this; do not build a second router.**

Cleanup in scope: `pyproject.toml:160` lists
`berb/review/cross_model_reviewer.py` in ruff per-file-ignores, and that file
does not exist. Remove the stale entry. Likewise CLAUDE.md names
`berb/llm/model_router.py`, which does not exist — the real routers are
`extended_router.py` and `nadirclaw_router.py`. Fix the doc.

### Method spec

Add a **verifier role** whose resolution asserts provider-family disjointness
from whichever provider produced the artifact under check.

```python
def get_adversarial_provider(
    self,
    role: str,
    *,
    exclude_family: str,
) -> Any | None:
    """Resolve a provider whose family differs from `exclude_family`.

    Returns None when no configured provider satisfies the constraint —
    the caller MUST then emit CROSS_MODEL_UNVERIFIED. Never silently
    falls back to the same family.
    """
```

**The failure mode is the design.** When no second family is available, the
result is `Finding(CROSS_MODEL_UNVERIFIED, INFO)` — explicit, in the artifact,
visible in the report. It never reads as "verified". This is the single most
important behavioural detail in W5.

Consumers: `berb/pipeline/paper_verifier.py`,
`berb/pipeline/hallucination_detector.py`, and optionally
`berb/review/ensemble.py` (one of the five reviewer personas resolved on a
different family).

### Design

**Paradigm:** policy object with dependency injection.
**Patterns:** the existing ports/adapters provider layer is reused as-is. The
only new thing is a *policy* — "the verifier must not share a family with the
generator" — expressed as a method on the router that already owns provider
selection. No new layer, no wrapper class.

### Security — largest new attack surface in this plan

This workstream creates a **new data egress path**: unpublished manuscript text
leaving for a second vendor. Treat it as such.

1. **Off by default.** New `SecurityConfig` fields
   (`berb/config.py:296` — the natural home, alongside
   `redact_sensitive_logs`):

   ```python
   cross_model_verification: bool = False
   cross_model_consent_granted: bool = False
   cross_model_max_usd_per_run: float = 0.0
   ```

   Both booleans must be true. `cross_model_verification=True` alone is a
   configuration intent; consent is a separate, explicit act.

2. **Disclosure at runtime.** Before the first cross-model call of a run, log
   and record in the run artifact: provider, model id, and content class
   ("claim text + quoted source spans + reference metadata"). A user must be
   able to answer "what left this machine and where did it go" from the run
   directory alone.

3. **Minimal payload.** Send the bounded claim, its anchors' quoted spans, and
   reference metadata. Never: the full manuscript, the run directory listing,
   file paths, environment, config, or any API key. An allowlist of fields, not
   a denylist.

4. **Cost ceiling.** An adversarial pass over every claim multiplies cost.
   `cross_model_max_usd_per_run` is enforced against the existing
   `berb/llm/cost_tracker.py`; exceeding it downgrades to
   `CROSS_MODEL_UNVERIFIED` rather than continuing to spend.

5. **Untrusted in both directions.** The manuscript going out is untrusted
   (it contains paper-derived text) and the verdict coming back is untrusted
   input to Berb. Both sides go through `wrap_untrusted` when re-entering a
   prompt; the verdict is parsed into a typed record, never `eval`'d or
   executed — the repo already learned this lesson in commit `334c7a0`.

6. **Redaction.** `redact_sensitive_logs` extends to cover egress payload
   logging.

### Tests — `tests/test_llm_cross_model.py`

Family-disjointness enforced; single-family config → `None` → `UNVERIFIED`,
never same-family fallback; consent gate blocks when either flag is false;
payload allowlist asserted field-by-field (a test that fails if someone adds a
field); cost ceiling downgrades rather than overspends; disclosure record
written. All with fake providers, no network, no `llm` marker.

**Effort:** ~300 LOC + ~350 test LOC. 3 days. Sequence after W1 (it wants
anchors to have something bounded to send).

---

## 9. W6 — Revision guard: token conservation and claim-strength drift

### Problem

`PAPER_REVISION` (stage 19) can silently change what the paper claims. Two
distinct failure shapes, and they need two distinct mechanisms.

### Layer A — deterministic token conservation (ships first, high precision)

Numbers and citation keys present in the pre-revision text must be present
after, unless an authorized roadmap item says otherwise. A revision that
silently turns 62% into 74%, or drops a citation key, is caught with certainty
and no LLM.

```python
def conserved_tokens(before: str, after: str) -> tuple[Finding, ...]:
    """Numeric literals and citation keys that vanished or changed."""
```

Severity `WARN`. Precision is near-perfect; the false-positive shape is
legitimate rounding changes, which the message should name.

### Layer B — claim-strength drift (advisory only)

Epistemic claims sit on an ordered strength scale:

```
is consistent with / may suggest
  < is associated with / correlates with
    < predicts
      < contributes to
        < affects / influences / leads to
          < causes / determines / demonstrates
```

The exact ordering is field-relative — a clinical "predicts" and an
econometric "predicts" are not the same rung — so the operative rule is
**"no silent move"**, in either direction, not one universal ordering.
Weakening misrepresents the author as much as strengthening. Dropping a modal
hedge (`may improve` → `improves`) is a move. Deleting a design caveat, a scope
hedge, or a null result is a move. Reordering a sentence while preserving the
verb and hedges is not.

This layer is **LLM-advisory and never blocking** (severity `ADVISORY`). The
deterministic runtime does not infer a rung from prose — that would be a
keyword matcher pretending to be semantics, and it would be wrong often enough
to poison the whole screening report's credibility.

### Design

**Paradigm:** invariant checking over a before/after pair.
**Patterns:** content-addressed surface registry; two-layer separation with
explicitly different epistemic status.

```python
@dataclass(frozen=True)
class ClaimSurface:
    claim_id: str
    text: str
    digest: str        # sha256(normalized text), full-strength hash

def register_surfaces(manifest: ClaimManifest, draft: str) -> tuple[ClaimSurface, ...]
def diff_surfaces(before, after) -> tuple[SurfaceDelta, ...]
def conserved_tokens(before: str, after: str) -> tuple[Finding, ...]
def strength_advisory(deltas, llm) -> tuple[Finding, ...]   # optional, injected
```

The LLM is injected, not imported — so Layer A tests run with `llm=None` and no
mocking ceremony, and Layer B is skippable by configuration.

**Hashing:** `hashlib.sha256`, used for integrity anchoring, so it is *not*
marked `usedforsecurity=False`. (The repo has one digest correctly marked that
way; this is not that case, and conflating them would be a real weakening.)

### Wiring

`berb/pipeline/stage_impls/_paper_writing.py`, revision path. Surfaces
registered before the revision LLM call, diffed after.

### Tests — `tests/test_integrity_revision_guard.py`

Number changed → caught; citation key dropped → caught; pure reordering →
clean; whitespace/markup-only change → clean; rounding change → caught with
the rounding-specific message; Layer B absent when `llm=None`; Layer B findings
never gate. ≥95% on Layer A.

**Effort:** ~280 LOC + ~300 test LOC. 2–3 days.

---

## 10. W7 — Seeded-defect evaluation of the reviewer ensemble

### Problem

`berb/review/ensemble.py` runs five reviewer personas plus an Area Chair.
Nobody has measured whether it catches anything. An unmeasured reviewer is a
confidence generator, which is worse than no reviewer.

### Method spec

Build a corpus of synthetic drafts with **known injected defects**: a
fabricated citation, an unsupported comparative claim, a number that
contradicts the results table, a dropped ablation, a p-value with no test
behind it. Measure per-persona and ensemble recall.

The defect key is **test criteria** in the HCE sense — it must never reach any
reviewer agent's context. `berb/integrity/eval/hidden_eval.py` already
implements exactly this three-way split (search / selection / test); wire the
seeded corpus into its test tier rather than building a parallel mechanism.

### Design

**Paradigm:** fixture-driven measurement.
**Patterns:** golden-file comparison; test doubles for the LLM tier.

Two tiers:

- **Deterministic tier** — defects catchable without an LLM (broken citation
  key, number/table contradiction, missing statistical test record). Runs in
  normal CI, no marker, no cost.
- **LLM tier** — defects requiring judgment. Marked `@pytest.mark.llm`,
  excluded from default CI per `pyproject.toml:113`, run manually or on a
  schedule. Reports recall per persona, not pass/fail — a recall number that
  moves is the signal.

### Disposition of the parked module

`.reachability-allowlist` parks
`berb.integrity.eval.finding_reproduction` as "needs curated known-findings
corpus". W7 either **is** that corpus — in which case wire the module and
remove the allowlist entry — or it is not, in which case delete the module and
close the entry. Do not leave it parked for a third quarter. That decision is
part of W7's definition of done.

### Security

Fixtures are **synthetic**. No real unpublished manuscript, no real author
name, no real institutional data enters `tests/fixtures/`. A seeded-defect
corpus built from a real draft is a leak waiting for a public repo.

**Effort:** ~200 LOC + fixture corpus. 2–3 days, mostly corpus authoring.

---

## 11. W8 — Reporting guidelines and AI-disclosure (data, not code)

Lowest coupling, ship last, ship as data.

### W8.1 — Reporting-guideline checklists

PRISMA (systematic reviews), CONSORT (trials), STROBE (observational). Berb
currently has `berb/presets/catalog/systematic-review.yaml` and a SKILL.md stub
and nothing else.

**Pattern: checklist-as-data with one generic evaluator.** A class per
guideline is the obvious wrong move — the guidelines differ in items, not in
logic.

```
berb/data/reporting_guidelines/prisma.yaml
berb/data/reporting_guidelines/consort.yaml
berb/data/reporting_guidelines/strobe.yaml
```

Each item: `id`, `section`, `requirement`, `detect` (a substring/heading cue),
`severity`. One evaluator walks the checklist against the draft's section map
and emits `Finding`s at `QUALITY_GATE`. Adding a guideline is a YAML file, zero
code.

Checklist *text* is regenerated from the primary EQUATOR-network sources, not
from ARS.

### W8.2 — AI-usage disclosure at export

Berb writes papers with LLMs and emits no disclosure statement. Most venues now
require one; this is a submission blocker, not a nicety.

`EXPORT_PUBLISH` (stage 22) generates a disclosure statement from a template
plus a venue profile. **Venue policy content is user-supplied and out of tree** —
same boundary ARS draws for format profiles, and it is the right one: shipping
a specific journal's policy text means shipping stale legal-ish content that
someone will trust. Berb ships the schema, the template, and one synthetic
example.

The statement is generated from *facts Berb already has*: which stages used an
LLM, which models, whether cross-model verification ran. That is honest
provenance, not boilerplate.

**Effort:** ~150 LOC + data. 2 days.

---

## 12. Sequencing

| Wave | Contents | Rationale | Est. |
|---|---|---|---|
| **0** | W0 license clearance + `findings.py` | blocks everything; also send the dual-license email | 0.5 d |
| **1** | W2 retraction + W3 uncited | pure, offline, no schema change, no new deps — proves the facade and gate wiring on low-risk code | 3–4 d |
| **2** | W4 paper-mill | same shape as wave 1, plus a data-loading pattern | 1–2 d |
| **3** | W1 anchors | schema migration + three stage touchpoints; do it once the gate plumbing is proven | 3–4 d |
| **4** | W6 revision guard | depends on W1's claim surfaces | 2–3 d |
| **5** | W5 cross-model | new egress surface; wants W1's bounded payloads; needs the consent design reviewed on its own | 3 d |
| **6** | W7 seeded-defect eval | measures everything above | 2–3 d |
| **7** | W8 guideline + disclosure data | independent, lowest risk, ship whenever | 2 d |

Total ≈ 18–22 working days. Waves 1 and 2 are independently shippable and
independently valuable; if the plan stalls, it should stall after wave 2 with
real capability landed, not before.

---

## 13. Cross-cutting security review

| Surface | Risk | Control |
|---|---|---|
| Regex over paper text (W1, W3, W4) | ReDoS on attacker-authored arXiv content | bounded quantifiers, no nesting, input length caps, wall-clock regression test |
| Data file loading (W4, W8) | code injection via corpus/checklist entries | literal matching only, never compile/eval/import; size, count, and control-char validation on load |
| Cite keys and source ids (W1) | path traversal into the run directory | registry key lookup only, never path construction; explicit `../` negative test |
| Cross-model calls (W5) | unpublished manuscript egress to a second vendor | off by default, two-flag consent, field allowlist, runtime disclosure record, cost ceiling |
| LLM verdicts (W5, W6) | untrusted model output treated as instructions or code | `wrap_untrusted` on re-injection; typed parse only; never `eval`/`exec` — see `334c7a0` |
| Findings payloads (all) | quoted source spans over-collected in artifacts | `MAX_ANCHOR_VALUE_CHARS`, evidence spans length-capped in `Finding` |
| New hashes (W1, W6) | weak digest used for integrity | `hashlib.sha256`, not marked `usedforsecurity=False` |
| Any new URL (none planned) | SSRF | `berb.web._ssrf.check_url_ssrf` — mandatory if a future revision adds one |

**Bandit is blocking** (`ci.yml`, `pyproject.toml:275`). No new `# nosec`, and
no new entry in `[tool.bandit] skips`, without a written justification in the
same comment block that documents B310/B108/B608/B314. If a new finding
appears, triage it — do not silence it.

---

## 14. Testing and CI

- **Coverage floor is 62 and ratchets** (`ci.yml`). Every module in this plan is
  pure and offline, so ≥95% is achievable and expected. New code must *raise*
  measured coverage, not dilute it. Bump the floor in the same PR that lands
  wave 2, once the actual number is known.
- **Test naming:** `tests/test_integrity_*.py`, `tests/test_literature_*.py`,
  `tests/test_llm_cross_model.py`. Mirrors module names per CLAUDE.md.
- **Markers:** nothing in waves 1–4 needs a marker — all offline. W5's tests use
  fake providers and stay unmarked. Only W7's judgment tier is `@pytest.mark.llm`.
- **mypy:** every new module joins the `[[tool.mypy.overrides]]` allowlist at
  `pyproject.toml:215` in its own PR. Written clean from the start.
- **Reachability:** `python scripts/check_reachability.py` must stay green with
  no new allowlist entries (R4).
- **Regression tests that must exist:**
  - v1 `claim_manifest.json` loads under the v2 schema (W1)
  - no `berb-cite` marker survives into any exported artifact (W1)
  - `UNKNOWN` retraction state never gates as clean (W2)
  - single-family config yields `UNVERIFIED`, never same-family fallback (W5)
  - advisory-severity findings never gate below `strict` (W0/W6)

---

## 15. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| License: an ARS idea is expressed too closely | med | high | W0 method-spec-then-implement discipline; provenance doc; dual-license request |
| Claim manifest v1→v2 breaks `--from-stage` resume | med | high | tolerant `from_dict`, explicit v1-loads regression test, additive-only |
| False-positive fatigue makes screening ignored | **high** | high | advisory-by-default; promotion to blocking requires a measured precision number from W7, not a hunch |
| Cross-model cost blowup | med | med | per-run USD ceiling enforced against `cost_tracker.py`; degrade to `UNVERIFIED` |
| Tortured-phrase corpus unavailable under a usable license | med | low | ship the mechanism with an empty list; document the loader; users supply their own |
| W1 anchor markers leak into a published PDF | low | **high** | `strip_markers` at export + a regression test asserting absence in every artifact type |
| Scope creep toward ARS's 200-script CI layer | med | med | explicitly out of scope, §0 |

**Rollback:** every check is behind `IntegrityConfig`. Setting
`mode: draft` reduces the entire layer to advisory output with no gating.
Waves 1–4 add no dependencies and no network calls, so reverting a wave is a
clean `git revert` with no data migration — except W1, whose manifest v2 is
forward-compatible by construction (v2 readers handle v1; v1 readers ignore the
unknown `anchors` key rather than failing, which is why it is an additive
field and not a restructure).

---

## 16. Definition of done

Per workstream:

- [ ] Module is import-reachable from `berb run`; `check_reachability.py` green with no new allowlist entry
- [ ] Module added to the mypy ratchet; `mypy berb/` clean
- [ ] `ruff check` and `ruff format --check` clean
- [ ] `bandit -r berb/ -ll -c pyproject.toml` clean with no new skip
- [ ] Module coverage ≥95%; overall coverage not reduced
- [ ] Findings flow through `findings.gates()`, not bespoke gate logic
- [ ] Failure semantics documented: what is `INFO` vs `ADVISORY` vs `WARN` vs `BLOCK`, and why
- [ ] Method statement recorded in `docs/legal/ars-provenance.md`
- [ ] `docs/CODEBASE_MIND_MAP.md` and CLAUDE.md's subsystem table updated

Plan-level:

- [ ] Dual-license request sent to the ARS author (day 1, regardless of answer)
  — **not sent**: this requires the user to actually send an email; an
  agent cannot dispatch outbound correspondence on the user's behalf
  without explicit per-message authorization. Draft on request.
- [x] `pyproject.toml:160` stale `berb/review/cross_model_reviewer.py` ruff
  entry removed (2026-09-01) — confirmed the file doesn't exist,
  `ruff check berb/` clean after removal.
- [x] CLAUDE.md corrected (2026-09-01): `berb/llm/model_router.py` and
  `model_cascade.py` don't exist (neither ever existed under those
  names). Real routers: `nadirclaw_router.py` (live, used by
  `smart_client.py`) and `extended_router.py` (NOT live — provider
  creation is a `_MockProvider` stub, unimported under `berb/pipeline/`,
  per the W5 finding).
- [ ] `berb.integrity.eval.finding_reproduction` either wired (W7) or
  deleted; allowlist entry closed either way — **still open**: W7 (the
  seeded-defect eval that would need this corpus) wasn't done this
  session, so touching this module now would be a scope decision made
  without doing the work it depends on. Left parked, as-is.
- [ ] Coverage floor in `ci.yml` raised to the new measured value minus ~2 points

---

## Appendix A — Attribution

The screening layer's design was informed by Academic Research Skills (ARS),
Cheng-I Wu, 2026, https://doi.org/10.5281/zenodo.20696614 — specifically its
treatment of citation locator anchors, uncited-assertion detection, retraction
status as a citation-integrity signal, cross-model verification as a defense
against shared-model blind spots, and the claim-strength ladder. No ARS source,
schema, prompt, or data file is used in Berb; the mechanisms here were
implemented independently from method descriptions. ARS is CC BY-NC 4.0; Berb
is MIT.

Where ARS itself credits upstream work, the upstream is the source Berb should
use: tortured-phrase screening derives from the Problematic Paper Screener line
of work (Cabanac, Labbé, Magazinov); reporting checklists from the
EQUATOR network; hidden consistent evaluation from AIRA2
(arXiv:2603.26499), which `berb/integrity/eval/hidden_eval.py` already cites.
