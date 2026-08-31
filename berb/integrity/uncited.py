"""Uncited-assertion detector (tasks/ars_integration_plan.md W3).

A sentence becomes an uncited-assertion candidate iff ALL THREE hold:

  1. It contains a quantifier or empirical-result verb (a number, a
     percentage, a fuzzy quantifier like "most"/"several", or a verb like
     "showed"/"demonstrated"/"observed"/"confirmed"). A guard pass rejects
     bare numbers that are actually years, version strings, or section /
     figure / table references.
  2. It carries no citation — neither a LaTeX ``\\cite{...}`` (Berb's paper
     drafts use LaTeX-style citations; see berb/pipeline/packaging.py) nor a
     ``berb-cite`` locator-anchor marker (tasks/ars_integration_plan.md W1)
     — checked on the sentence itself and a bounded adjacent-clause window.
  3. It is not definitional ("refers to", "is defined as", "we define",
     "for the purposes of").

This is a deterministic, offline, LLM-free check: table-driven predicates,
no class hierarchy — see plan §6 for why a Strategy/Rule hierarchy would
make the one genuinely tricky part (the numeric guard pass) harder to read,
not easier.

Security note: every regex here runs over LLM-generated and PDF-extracted
text of attacker-influenceable origin (anyone can post to arXiv). Patterns
are written with bounded quantifiers and no nested/ambiguous repetition,
and ``MAX_SENTENCE_CHARS`` caps the match target regardless — see
``tests/test_integrity_uncited.py::test_no_catastrophic_backtracking``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from berb.integrity.findings import CheckId, Finding, Severity

# Sentences longer than this are truncated before matching. Longer than any
# reasonable single sentence, short enough to keep worst-case regex work
# bounded regardless of input size.
MAX_SENTENCE_CHARS: Final = 4000

# Left-context window (chars) scanned for a structural cue word before a
# bare number, e.g. "as shown in Figure 3". Wide enough to cover "cf.
# Section ", narrow enough not to reach across a clause boundary.
_GUARD_LEFT_WINDOW: Final = 24

_FUZZY_QUANTIFIERS: Final = frozenset(
    {
        "most",
        "many",
        "several",
        "few",
        "some",
        "majority",
        "minority",
        "half",
        "third",
        "quarter",
        "twice",
        "thrice",
    }
)

_EMPIRICAL_VERBS: Final = frozenset(
    {
        "showed",
        "shows",
        "demonstrated",
        "demonstrates",
        "observed",
        "observes",
        "proved",
        "proves",
        "confirmed",
        "confirms",
        "found",
        "reveals",
        "revealed",
        "indicates",
        "indicated",
        "outperforms",
        "outperformed",
    }
)

_DEFINITION_CUES: Final = (
    "refers to",
    "is defined as",
    "are defined as",
    "we define",
    "for the purposes of",
    "defined as",
)

# Bare-number matches: percentages, decimals, integers, and fuzzy words.
# Deliberately simple character classes, no nested quantifiers.
#
# BUG: an earlier \d{1,3} cap here meant this could never match a 4+ digit
# span at all (a \b\d{1,3}\b pattern can't find a trailing word boundary
# inside a longer digit run, so it silently matches nothing on "2020" or
# "1000"). That made the year-guard in _is_guarded_number dead code AND
# made large bare counts ("we tested on 1000 samples") invisible to
# _has_quantifier. \d{1,6} covers any realistic sample size / year / count
# while staying a simple, non-nested, linear pattern.
_RE_PERCENT: Final = re.compile(r"\b\d{1,3}(?:\.\d{1,2})?\s?%")
_RE_NUMBER: Final = re.compile(r"\b\d{1,6}(?:\.\d{1,4})?\b")
_RE_YEAR: Final = re.compile(r"\b(19|20)\d{2}\b")
_RE_VERSION_OR_SECTION_NUMBER: Final = re.compile(r"\b\d{1,4}(?:\.\d{1,4}){1,4}\b")
_RE_WORD: Final = re.compile(r"[A-Za-z][A-Za-z-]{0,30}")

_STRUCTURAL_CUES: Final = (
    "section",
    "figure",
    "fig.",
    "table",
    "tbl.",
    "chapter",
    "step",
    "appendix",
    "\u00a7",  # section sign
)

# Berb paper drafts cite with LaTeX \cite{key1, key2}. The `berb-cite`
# marker is the locator-anchor form from tasks/ars_integration_plan.md W1;
# recognised here too so this check does not regress once anchors ship.
_RE_LATEX_CITE: Final = re.compile(r"\\cite[a-zA-Z]*\{[^}]{1,500}\}")
_RE_BERB_CITE_MARKER: Final = re.compile(
    r"<!--berb-cite\s+key=[A-Za-z0-9_:.\-]{1,64}\s+"
    r"kind=(?:quote|page|section|paragraph)\s+id=[0-9a-f]{6}-->"
)


@dataclass(frozen=True)
class SentenceRef:
    """One sentence plus enough context to detect and to report a finding
    without this module touching the filesystem."""

    index: int
    text: str
    adjacent_text: str = ""
    """A bounded window of surrounding text (e.g. the previous clause),
    scanned for a citation the sentence itself lacks."""
    locator: str = ""
    """Caller-supplied report locator, e.g. "paper.md:412"."""


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_SENTENCE_CHARS else text[:MAX_SENTENCE_CHARS]


def _is_guarded_number(sentence: str, start: int, end: int) -> bool:
    """True when the bare-number match at [start, end) is NOT a quantifier:
    a year, part of a version/section triple, or preceded by a structural
    cue word."""
    matched = sentence[start:end]
    if _RE_YEAR.fullmatch(matched):
        return True

    # Dotted deeper form (version triple or nested section number) — check
    # whether this exact span is part of a longer X.Y(.Z...) run.
    for m in _RE_VERSION_OR_SECTION_NUMBER.finditer(sentence):
        if m.start() <= start and end <= m.end() and (m.end() - m.start()) > (end - start):
            return True

    left = sentence[max(0, start - _GUARD_LEFT_WINDOW) : start].lower()
    return any(cue in left for cue in _STRUCTURAL_CUES)


def _has_quantifier(sentence: str) -> bool:
    if _RE_PERCENT.search(sentence):
        return True

    for m in _RE_NUMBER.finditer(sentence):
        if not _is_guarded_number(sentence, m.start(), m.end()):
            return True

    words = {w.lower() for w in _RE_WORD.findall(sentence)}
    if words & _FUZZY_QUANTIFIERS:
        return True
    return bool(words & _EMPIRICAL_VERBS)


def _has_citation(sentence: str, adjacent_text: str) -> bool:
    combined = f"{adjacent_text} {sentence}"
    return bool(_RE_LATEX_CITE.search(combined) or _RE_BERB_CITE_MARKER.search(combined))


def _is_definitional(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(cue in lowered for cue in _DEFINITION_CUES)


def is_uncited_assertion(sentence: str, adjacent_text: str = "") -> bool:
    """Pure predicate: does this single sentence look like an uncited
    empirical assertion? NFKC-normalized and length-capped before matching
    so full-width/confusable digits and pathological lengths don't evade or
    stall the guard pass."""
    normalized = unicodedata.normalize("NFKC", sentence)
    normalized = _truncate(normalized)
    if not _has_quantifier(normalized):
        return False
    if _has_citation(normalized, adjacent_text):
        return False
    return not _is_definitional(normalized)


# Fenced code blocks are not prose — a numeric literal in example code
# ("accuracy = 0.34  # 34%") is not an unsourced empirical claim, and
# scanning it would just be noise. Non-greedy single group, DOTALL — no
# nested quantifiers, so this stays linear even on an unclosed/pathological
# ``` run (worst case: no match, block passes through unstripped).
_RE_FENCED_CODE_BLOCK: Final = re.compile(r"```.*?```", re.DOTALL)

# Sentence boundary: punctuation followed by whitespace followed by an
# uppercase letter, digit, quote, or paren. Abbreviations like "e.g." and
# "et al." usually don't trigger a false split because the word right after
# the period starts lowercase. Both lookaround groups are fixed-width
# single-character classes, so this stays linear.
_RE_SENTENCE_BOUNDARY: Final = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(“])')

# ponytail: building adjacent_text as "every OTHER fragment on this line,
# joined" is O(n) per fragment, so O(n^2) for a line with n fragments. Real
# prose lines rarely carry more than a handful of sentences; beyond this
# cap, skip cross-fragment adjacency rather than let a pathological
# single-line input (thousands of fragments) go quadratic. Upgrade to a
# prefix/suffix-sum join if a real draft ever legitimately exceeds this.
_MAX_FRAGMENTS_FOR_ADJACENCY: Final = 30


def split_sentences(text: str, *, source_label: str = "draft") -> tuple[SentenceRef, ...]:
    """Pure, deterministic sentence splitter for a markdown paper draft.

    No NLP dependency — this repo's stdlib-only convention (see
    tasks/ars_integration_plan.md §6) and the boundary heuristic above are
    sufficient for a WARN-severity advisory check; it doesn't need to be a
    linguistically perfect tokenizer.

    ``adjacent_text`` for each fragment is the rest of its source line —
    a citation trailing at the end of a multi-sentence line (a common
    academic-writing pattern: "X improved. Y improved. Both are documented
    \\cite{a2020}.") is visible to every fragment sharing that line.

    ``locator`` is ``"{source_label}:{line_no}"`` (1-indexed), matching the
    ``path:line`` convention findings use elsewhere in this codebase.
    """
    no_code = _RE_FENCED_CODE_BLOCK.sub("", text)
    refs: list[SentenceRef] = []
    idx = 0
    for line_no, line in enumerate(no_code.split("\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        fragments = [f.strip() for f in _RE_SENTENCE_BOUNDARY.split(stripped) if f.strip()]
        many_fragments = len(fragments) > _MAX_FRAGMENTS_FOR_ADJACENCY
        for i, fragment in enumerate(fragments):
            adjacent = (
                "" if many_fragments else " ".join(f for j, f in enumerate(fragments) if j != i)
            )
            refs.append(
                SentenceRef(
                    index=idx,
                    text=fragment,
                    adjacent_text=adjacent,
                    locator=f"{source_label}:{line_no}",
                )
            )
            idx += 1
    return tuple(refs)


def detect_uncited(sentences: tuple[SentenceRef, ...]) -> tuple[Finding, ...]:
    """Scan sentences, returning one WARN finding per uncited assertion.

    Deterministic and total — never raises on malformed/adversarial text.
    """
    findings: list[Finding] = []
    for ref in sentences:
        if is_uncited_assertion(ref.text, ref.adjacent_text):
            findings.append(
                Finding(
                    check=CheckId.UNCITED_ASSERTION,
                    severity=Severity.WARN,
                    message="Empirical assertion with no citation",
                    locator=ref.locator or f"sentence:{ref.index}",
                    evidence=(ref.text,),
                    remediation="Add a \\cite{} or remove the quantified claim.",
                )
            )
    return tuple(findings)
