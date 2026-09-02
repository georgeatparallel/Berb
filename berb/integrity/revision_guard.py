"""Revision guard — token conservation and claim-strength drift (tasks/ars_integration_plan.md W6).

``PAPER_REVISION`` (stage 19) can silently change what a paper claims: a
number quietly becomes a different number, a citation quietly disappears,
or "is associated with" quietly becomes "causes". Two distinct failure
shapes need two distinct mechanisms.

Layer A — ``conserved_tokens`` — is deterministic, no LLM, high precision:
numeric literals and citation keys present in the pre-revision text must
still be present after, unless the change is an intentional
rounding/reformat. Severity ``WARN``. The known false-positive shape is
legitimate reformatting (``62%`` -> ``62.0%``), which is why numbers are
compared after stripping trailing zeros; a finding's remediation names
this explicitly rather than pretending the check is infallible.

Layer B — ``find_claim_drift_candidates`` + ``strength_advisory`` — is
LLM-advisory only, severity ``ADVISORY``, and never blocks. The
deterministic runtime does not infer a claim's epistemic strength from
prose — that would be a keyword matcher pretending to be semantics. The
LLM is injected as a plain ``Callable[[str], str]``, never imported, so
this module stays dependency-free of ``berb.pipeline``/``berb.llm`` and
Layer A callers keep working with ``llm=None`` and zero mocking ceremony.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from berb.integrity.findings import CheckId, Finding, Severity
from berb.integrity.uncited import SentenceRef, split_sentences
from berb.utils.sanitize import wrap_untrusted

# Caller-supplied text (draft/revision) is untrusted, paper-derived content
# of unbounded size. Bounds work done regardless of input size — a full
# paper draft is well under this.
_MAX_SCAN_CHARS: Final = 200_000

# Bounded, simple character classes — no nested quantifiers, linear scan.
#
# BUG (caught by its own test suite): a trailing \b after the optional %
# backtracks the % away. '%' isn't a word character, so \b\d+%?\b on "62%."
# fails to match with the % included (no word-boundary transition exists
# right after '%' when followed by '.'), and backtracking drops the '%' to
# satisfy \b against the digit run instead — silently matching "62" not
# "62%". \d+ is already self-terminating at the first non-digit, so the
# trailing \b was both unnecessary and actively wrong here.
_RE_NUMBER_TOKEN: Final = re.compile(r"\b\d+(?:\.\d+)?%?")
_RE_CITE_KEYS: Final = re.compile(r"\\cite[a-zA-Z]*\{([^}]{1,500})\}")


def _normalize_number(token: str) -> str:
    """Strip a trailing '%' for comparison, then strip trailing zeros after
    a decimal point — "62.0" and "62" are the same conserved value, and a
    revision reformatting one as the other is not a dropped number."""
    has_percent = token.endswith("%")
    core = token[:-1] if has_percent else token
    if "." in core:
        core = core.rstrip("0").rstrip(".")
    return core + ("%" if has_percent else "")


def _extract_numbers(text: str) -> set[str]:
    return {_normalize_number(tok) for tok in _RE_NUMBER_TOKEN.findall(text[:_MAX_SCAN_CHARS])}


def _extract_citation_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for m in _RE_CITE_KEYS.finditer(text[:_MAX_SCAN_CHARS]):
        for key in m.group(1).split(","):
            stripped = key.strip()
            if stripped:
                keys.add(stripped)
    return keys


def conserved_tokens(before: str, after: str) -> tuple[Finding, ...]:
    """Numeric literals and citation keys present in *before* but missing
    from *after*. Pure, total, never raises. One finding per dropped token
    — this is deliberately granular (matches the per-item locator style
    used by ``berb.literature.retraction.screen_bibliography``) rather than
    one aggregate finding, so each drop can be independently reviewed or
    acknowledged.
    """
    findings: list[Finding] = []

    dropped_numbers = sorted(_extract_numbers(before) - _extract_numbers(after))
    for number in dropped_numbers:
        findings.append(
            Finding(
                check=CheckId.TOKEN_CONSERVATION,
                severity=Severity.WARN,
                message=f"numeric literal {number!r} present before revision is missing after",
                locator=number,
                remediation=(
                    "Confirm this was an intentional edit (or a rounding/"
                    "reformat already tolerated by normalization) rather "
                    "than a silently altered result."
                ),
            )
        )

    dropped_keys = sorted(_extract_citation_keys(before) - _extract_citation_keys(after))
    for key in dropped_keys:
        findings.append(
            Finding(
                check=CheckId.TOKEN_CONSERVATION,
                severity=Severity.WARN,
                message=f"citation key {key!r} present before revision is missing after",
                locator=key,
                remediation="Confirm this citation was intentionally removed, or restore it.",
            )
        )

    return tuple(findings)


# ---------------------------------------------------------------------------
# Layer B — claim-strength drift (LLM-advisory)
# ---------------------------------------------------------------------------

# Below this similarity ratio, a before/after sentence pair is treated as an
# unrelated addition/removal (a different claim), not a drifted claim -- out
# of this layer's scope.
_MIN_DRIFT_SIMILARITY: Final = 0.4

# Bounds LLM calls per run regardless of how many sentences a revision
# touches -- same shape as berb.llm.cross_model._MAX_CROSS_MODEL_CHECKS.
# Most-changed pairs (lowest similarity) are kept when a run exceeds this.
_MAX_DRIFT_CANDIDATES: Final = 20

# O(n*m) sentence-pair scoring below is bounded work only if the sentence
# counts themselves are bounded -- a revision touching more sentences than
# this is truncated rather than let the alignment step blow up.
_MAX_SENTENCES_FOR_ALIGNMENT: Final = 200

# Untrusted, paper-derived sentence text sent to an LLM prompt -- capped
# independently of split_sentences' own MAX_SENTENCE_CHARS, matching
# berb.llm.cross_model.MAX_CLAIM_CHARS's defense-in-depth cap.
_MAX_DRIFT_PROMPT_CHARS: Final = 2000

_STRENGTH_ADVISORY_PROMPT: Final = (
    "Two versions of one sentence from an academic paper are shown below, "
    "before and after a revision pass. Judge only whether the epistemic "
    'strength of the claim moved -- e.g. "is associated with" becoming '
    '"causes", or a hedge like "may improve" being dropped to "improves" '
    "-- in EITHER direction (weakening counts too). Do not flag pure "
    "rewording, reordering, or grammar changes that keep the same "
    "certainty. Respond with strict JSON only: "
    '{{"drifted": true|false, "direction": "strengthened"|"weakened"|"none", '
    '"rationale": "<one sentence>"}}.\n\n'
    "Before: {before}\n"
    "After: {after}\n"
)


@dataclass(frozen=True)
class ClaimDriftCandidate:
    """A before/after sentence pair whose text changed enough to be worth
    an epistemic-strength check, but not so much it looks like an
    unrelated addition or removal."""

    before_text: str
    after_text: str
    locator: str


def _normalize_sentence(text: str) -> str:
    return " ".join(text.split())


def find_claim_drift_candidates(
    before: str, after: str, *, source_label: str = "revision"
) -> tuple[ClaimDriftCandidate, ...]:
    """Sentence-level alignment between before/after revision text.

    Two passes, so pure reordering is never a candidate: sentences with
    identical normalized text in both versions are matched and dropped
    first, *regardless of position*. Remaining before-sentences are then
    greedily paired with the most similar remaining after-sentence
    (``difflib.SequenceMatcher`` ratio); a pair below
    ``_MIN_DRIFT_SIMILARITY`` is an unrelated addition/removal, not a
    drift candidate, and is left unpaired. Returns at most
    ``_MAX_DRIFT_CANDIDATES`` pairs, most-changed (lowest similarity)
    first.
    """
    before_sentences = split_sentences(before, source_label=source_label)[
        :_MAX_SENTENCES_FOR_ALIGNMENT
    ]
    after_sentences = split_sentences(after, source_label=source_label)[
        :_MAX_SENTENCES_FOR_ALIGNMENT
    ]

    after_by_norm: dict[str, list[SentenceRef]] = {}
    for s in after_sentences:
        after_by_norm.setdefault(_normalize_sentence(s.text), []).append(s)

    remaining_before: list[SentenceRef] = []
    matched_after_ids: set[int] = set()
    for b in before_sentences:
        bucket = after_by_norm.get(_normalize_sentence(b.text))
        if bucket:
            matched_after_ids.add(id(bucket.pop(0)))
        else:
            remaining_before.append(b)

    remaining_after = [s for s in after_sentences if id(s) not in matched_after_ids]

    scored: list[tuple[float, SentenceRef, SentenceRef]] = []
    used_after: set[int] = set()
    for b in remaining_before:
        best_ratio = 0.0
        best_after: SentenceRef | None = None
        for a in remaining_after:
            if id(a) in used_after:
                continue
            ratio = difflib.SequenceMatcher(None, b.text, a.text).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_after = a
        if best_after is not None and best_ratio >= _MIN_DRIFT_SIMILARITY:
            used_after.add(id(best_after))
            scored.append((best_ratio, b, best_after))

    scored.sort(key=lambda item: item[0])
    return tuple(
        ClaimDriftCandidate(before_text=b.text, after_text=a.text, locator=b.locator)
        for _, b, a in scored[:_MAX_DRIFT_CANDIDATES]
    )


def strength_advisory(
    candidates: Sequence[ClaimDriftCandidate],
    llm: Callable[[str], str] | None,
) -> tuple[Finding, ...]:
    """LLM-advisory claim-strength drift check.

    ``llm=None`` returns ``()`` immediately, no calls -- this is how
    Layer B stays fully skippable by configuration/injection. Never
    blocks (``Severity.ADVISORY``): a call exception or an unparseable/
    malformed response for one candidate is skipped, never raised or
    escalated -- matching this module's must-never-fail-the-stage
    discipline. JSON-only parse, never ``eval``/``exec`` (see commit
    334c7a0 for why that class of bug is taken seriously here).
    """
    if llm is None:
        return ()

    findings: list[Finding] = []
    for candidate in candidates:
        prompt = _STRENGTH_ADVISORY_PROMPT.format(
            before=wrap_untrusted(
                candidate.before_text[:_MAX_DRIFT_PROMPT_CHARS], "before sentence"
            ),
            after=wrap_untrusted(candidate.after_text[:_MAX_DRIFT_PROMPT_CHARS], "after sentence"),
        )
        try:
            raw = llm(prompt)
        except Exception:  # noqa: BLE001 - advisory check must never fail the stage
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict) or not data.get("drifted"):
            continue

        direction = str(data.get("direction", "")).strip().lower()
        if direction not in ("strengthened", "weakened"):
            direction = "changed strength"
        rationale = str(data.get("rationale", ""))[:300]

        findings.append(
            Finding(
                check=CheckId.CLAIM_STRENGTH_DRIFT,
                severity=Severity.ADVISORY,
                message=f"claim may have {direction} during revision: {rationale}",
                locator=candidate.locator,
                evidence=(candidate.before_text, candidate.after_text),
                remediation=(
                    "Confirm the certainty of this claim was not "
                    "unintentionally changed during revision."
                ),
            )
        )
    return tuple(findings)
