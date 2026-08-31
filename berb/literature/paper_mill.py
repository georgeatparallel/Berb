"""Paper-mill / tortured-phrase risk screening (tasks/ars_integration_plan.md W4).

A curated-phrase hit is a risk MARKER, never an authorship judgment or a
plagiarism verdict — legitimate text sometimes quotes or critiques a
tortured phrase. This is why every finding here is ``Severity.ADVISORY``
(see berb/integrity/findings.py): it never gates below ``strict`` mode and
is meant to prompt a human look, not to auto-reject a source.

Corpus provenance: berb/data/tortured_phrases.yaml. The corpus is data,
not code — the loader never evaluates, compiles, or imports anything from
it, and entries are matched as literal strings, never as regex.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

from berb.integrity.findings import CheckId, Finding, Severity

logger = logging.getLogger(__name__)

_DEFAULT_CORPUS_PATH: Final = (
    Path(__file__).resolve().parent.parent / "data" / "tortured_phrases.yaml"
)

# Defensive caps on corpus load. The corpus is external data — even the
# shipped file could be tampered with on a compromised install — so these
# bound how much a malformed or hostile corpus can make this module do.
_MAX_CORPUS_BYTES: Final = 1_000_000
_MAX_ENTRIES: Final = 20_000
_MAX_PHRASE_CHARS: Final = 200
_MIN_NGRAM: Final = 2
_MAX_NGRAM: Final = 4

# Caller-supplied text to scan is also untrusted (paper/PDF-derived). This
# bounds work done regardless of input size — screens an abstract or a
# full-text extraction without unbounded cost on a pathological input.
_MAX_SCAN_CHARS: Final = 50_000

_RE_NON_WORD: Final = re.compile(r"[^\w\s-]", re.UNICODE)
_RE_WHITESPACE: Final = re.compile(r"\s+")


@dataclass(frozen=True)
class PhraseCorpus:
    """Normalized phrase set, indexed by word-count for O(1) membership
    checks during the sliding n-gram window scan."""

    by_length: dict[int, frozenset[str]] = field(default_factory=dict)
    size: int = 0


def _normalize(text: str) -> str:
    """NFKC + casefold + punctuation-as-space + whitespace-collapse.

    Chosen so a confusable/homoglyph or punctuation-adjacency evasion
    attempt ("counterfeit consciousness," right before a comma) folds away
    instead of creating a bypass — same discipline as
    berb/integrity/uncited.py's normalization.
    """
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = _RE_NON_WORD.sub(" ", normalized)
    return _RE_WHITESPACE.sub(" ", normalized).strip()


def _has_control_chars(s: str) -> bool:
    return any(ord(ch) < 0x20 and ch != "\t" for ch in s)


def load_corpus(path: str | Path | None = None) -> PhraseCorpus:
    """Load and validate the phrase corpus.

    Never raises — a missing, oversized, or malformed corpus degrades to an
    empty ``PhraseCorpus`` (``screen_text`` is then a guaranteed no-op).
    A working no-op is safer than letting an import-time exception three
    stages upstream take down a run over an advisory-only check.
    """
    corpus_path = Path(path) if path else _DEFAULT_CORPUS_PATH
    try:
        if not corpus_path.is_file():
            logger.warning("Tortured-phrase corpus not found: %s", corpus_path)
            return PhraseCorpus()
        if corpus_path.stat().st_size > _MAX_CORPUS_BYTES:
            logger.warning(
                "Tortured-phrase corpus exceeds size cap (%d bytes), skipping: %s",
                _MAX_CORPUS_BYTES,
                corpus_path,
            )
            return PhraseCorpus()
        raw: Any = yaml.safe_load(corpus_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        logger.warning("Failed to load tortured-phrase corpus %s: %s", corpus_path, exc)
        return PhraseCorpus()

    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return PhraseCorpus()

    by_length: dict[int, set[str]] = {}
    count = 0
    for entry in entries[:_MAX_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        phrase = entry.get("phrase")
        if not isinstance(phrase, str) or not phrase.strip():
            continue
        if len(phrase) > _MAX_PHRASE_CHARS or _has_control_chars(phrase):
            continue
        normalized = _normalize(phrase)
        if not normalized:
            continue
        tokens = normalized.split(" ")
        n = len(tokens)
        if n < _MIN_NGRAM or n > _MAX_NGRAM:
            continue
        by_length.setdefault(n, set()).add(normalized)
        count += 1

    return PhraseCorpus(by_length={n: frozenset(s) for n, s in by_length.items()}, size=count)


def screen_text(text: str, corpus: PhraseCorpus, *, locator: str = "") -> tuple[Finding, ...]:
    """Slide an n-gram window (sized to the corpus's own phrase lengths)
    over *text* and report any literal hit.

    Entries are matched as LITERALS ONLY, never compiled as regex — a
    corpus file is external data, and interpreting it as a pattern language
    would be a code-injection surface for no benefit. Returns ``()`` for an
    empty corpus (never a false "clean" claim to build on — an empty
    corpus load is logged separately by ``load_corpus``) and for empty text.
    """
    if not corpus.by_length or not text:
        return ()

    normalized = _normalize(text[:_MAX_SCAN_CHARS])
    tokens = normalized.split(" ") if normalized else []
    if not tokens:
        return ()

    hits: list[str] = []
    seen: set[str] = set()
    for n, phrases in corpus.by_length.items():
        if n > len(tokens):
            continue
        for i in range(len(tokens) - n + 1):
            window = " ".join(tokens[i : i + n])
            if window in phrases and window not in seen:
                seen.add(window)
                hits.append(window)

    if not hits:
        return ()

    return (
        Finding(
            check=CheckId.PAPER_MILL_RISK,
            severity=Severity.ADVISORY,
            message=f"{len(hits)} tortured-phrase risk marker(s) found",
            locator=locator,
            evidence=tuple(sorted(hits)),
            remediation=(
                "Risk marker only — a hit does not itself establish "
                "paper-mill origin or plagiarism. Review the source "
                "manually before acting on it."
            ),
        ),
    )
