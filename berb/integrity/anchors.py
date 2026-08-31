"""Citation locator anchors — the three-layer citation gap (tasks/ars_integration_plan.md W1).

Berb verifies that a cited work *exists* (``berb/literature/verify.py``,
``berb/pipeline/citation_verification.py``) but has no concept of *where in
that work* a claim is supported. A real paper cited for a claim it does not
make passes every existing gate. This module closes that gap.

Marker syntax (chosen independently for Berb, not copied from any external
tool): ``<!--berb-cite key=<cite_key> kind=<quote|page|section|paragraph>
id=<6-hex>-->``. The marker carries an anchor **id**, not the quote itself —
the quote lives in the claim manifest (``claim_manifest.json``) so the draft
stays readable and the payload stays bounded. ``berb/integrity/uncited.py``
already recognizes this same marker as a citation for its own purposes.

Design (parse-don't-validate, plan §4):

- ``make_anchor`` is a smart constructor: it returns ``None`` on any
  invariant failure rather than raising, so no unvalidated ``Anchor`` can
  exist anywhere downstream. The LLM never supplies the anchor id — Berb
  derives it deterministically as
  ``sha256(f"{cite_key}|{kind}|{normalized_value}")[:6]``, which removes a
  whole class of forged-marker failure.
- ``verify_anchors`` is pure and total: given a claim manifest, draft text,
  and a mapping of stored source texts, it returns findings and never
  raises. Absence of stored source text is reported as
  ``ANCHOR_UNVERIFIABLE`` (``INFO``) — never rendered as "verified".
  Absence of evidence is not evidence of support.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from berb.integrity.findings import CheckId, Finding, Severity

# Quoted anchor values are untrusted, paper-derived text. Capping bounds the
# size of persisted findings/manifests and how much untrusted text could be
# re-injected into a future prompt.
MAX_ANCHOR_VALUE_CHARS: Final = 300

# Same bound as BibTeX-style cite keys elsewhere in this codebase (see
# berb/pipeline/stage_impls/_citations.py's cite_key handling). Anchored,
# every character class bounded — no ReDoS risk.
_RE_CITE_KEY: Final = re.compile(r"^[A-Za-z0-9_:.\-]{1,64}$")

_RE_WHITESPACE: Final = re.compile(r"\s+")


class AnchorKind(StrEnum):
    QUOTE = "quote"
    PAGE = "page"
    SECTION = "section"
    PARAGRAPH = "paragraph"


@dataclass(frozen=True)
class Anchor:
    """A single locator anchor. Build only via ``make_anchor`` — the
    private-constructor discipline that keeps every ``Anchor`` in memory
    valid by construction."""

    anchor_id: str
    cite_key: str
    kind: AnchorKind
    value: str

    def to_dict(self) -> dict[str, str]:
        return {
            "anchor_id": self.anchor_id,
            "cite_key": self.cite_key,
            "kind": self.kind.value,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Anchor | None:
        """Tolerant deserialization for manifest loading. Returns ``None``
        (never raises) on any malformed record — a v1 manifest with no
        ``anchors`` key never reaches this function at all; a corrupted or
        hand-edited v2 record degrades to "this anchor doesn't exist"
        rather than crashing the whole load."""
        try:
            kind = AnchorKind(str(data.get("kind", "")))
        except ValueError:
            return None
        cite_key = str(data.get("cite_key", ""))
        anchor_id = str(data.get("anchor_id", ""))
        value = str(data.get("value", ""))
        if not _RE_CITE_KEY.match(cite_key):
            return None
        if not anchor_id or not value:
            return None
        return cls(
            anchor_id=anchor_id,
            cite_key=cite_key,
            kind=kind,
            value=value[:MAX_ANCHOR_VALUE_CHARS],
        )


def _normalize_value(value: str) -> str:
    """NFKC + casefold + whitespace-collapse — used both to derive the
    anchor id and to compare a quote against stored source text, so
    "Foo  bar" and "foo bar" hash/match identically."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _RE_WHITESPACE.sub(" ", normalized).strip()


def _derive_anchor_id(cite_key: str, kind: AnchorKind, normalized_value: str) -> str:
    digest = hashlib.sha256(f"{cite_key}|{kind.value}|{normalized_value}".encode()).hexdigest()
    return digest[:6]


def make_anchor(cite_key: str, kind: str, value: str) -> Anchor | None:
    """Smart constructor. Returns ``None`` if any invariant fails:
    ``cite_key`` doesn't match the bounded key pattern, ``kind`` isn't a
    known ``AnchorKind``, or ``value`` is empty or over-length after strip.

    The caller (the drafting stage) supplies ``key``/``kind``/``value`` from
    LLM output; the anchor id is always derived here, never accepted from
    the caller — an LLM cannot forge an anchor id that doesn't match its
    own (cite_key, kind, value).
    """
    if not _RE_CITE_KEY.match(cite_key):
        return None
    try:
        kind_enum = AnchorKind(kind)
    except ValueError:
        return None
    stripped = value.strip()
    if not stripped or len(stripped) > MAX_ANCHOR_VALUE_CHARS:
        return None
    anchor_id = _derive_anchor_id(cite_key, kind_enum, _normalize_value(stripped))
    return Anchor(anchor_id=anchor_id, cite_key=cite_key, kind=kind_enum, value=stripped)


@dataclass(frozen=True)
class MarkerRef:
    """One ``berb-cite`` marker found in draft text — a reference to an
    ``Anchor`` that must live in the claim manifest, not the anchor itself."""

    cite_key: str
    kind: AnchorKind
    anchor_id: str


# Anchored on both sides, every character class bounded ({1,64}, {6}) — no
# nested/ambiguous quantifiers, so this is ReDoS-safe by construction.
MARKER_RE: Final = re.compile(
    r"<!--berb-cite\s+key=([A-Za-z0-9_:.\-]{1,64})\s+"
    r"kind=(quote|page|section|paragraph)\s+id=([0-9a-f]{6})-->"
)


def parse_markers(text: str) -> tuple[MarkerRef, ...]:
    """Extract every well-formed marker from *text*. Malformed-looking
    marker text that doesn't fully match ``MARKER_RE`` is silently not a
    marker — never raises."""
    refs: list[MarkerRef] = []
    for m in MARKER_RE.finditer(text):
        cite_key, kind_str, anchor_id = m.groups()
        try:
            kind = AnchorKind(kind_str)
        except ValueError:
            continue
        refs.append(MarkerRef(cite_key=cite_key, kind=kind, anchor_id=anchor_id))
    return tuple(refs)


def strip_markers(text: str) -> str:
    """Remove every marker from *text*. Idempotent and total — safe to call
    on text with no markers, and safe to call more than once. MUST run on
    every exported artifact (PDF/LaTeX/DOCX/markdown) before it leaves the
    pipeline; see berb/pipeline/stage_impls/_export.py."""
    return MARKER_RE.sub("", text)


def verify_anchors(
    anchors_by_id: Mapping[str, Anchor],
    bib_keys: frozenset[str],
    draft_text: str,
    source_texts: Mapping[str, str],
) -> tuple[Finding, ...]:
    """Verify every marker found in *draft_text* against the manifest and
    stored source texts. Pure — no I/O, never raises.

    Per marker:
      1. ``cite_key`` must resolve to a known bibliography key, else
         ``ANCHOR_UNRESOLVED`` (``WARN``).
      2. ``anchor_id`` must resolve to an ``Anchor`` in *anchors_by_id*,
         else ``ANCHOR_UNRESOLVED`` (``WARN``).
      3. For ``kind=quote``: the anchor's value must appear (normalized) in
         the cited work's stored source text, else
         ``ANCHOR_QUOTE_MISMATCH`` (``BLOCK`` — a fabricated quote is the
         strongest available signal of a fabricated claim). If no source
         text is stored for that key at all, the result is
         ``ANCHOR_UNVERIFIABLE`` (``INFO``) — never a silent pass.
      4. For ``page``/``section``/``paragraph``: this runtime does not
         track a cited work's internal structure, so these always report
         ``ANCHOR_UNVERIFIABLE`` (``INFO``) rather than claiming a check
         that wasn't performed.
    """
    findings: list[Finding] = []
    for ref in parse_markers(draft_text):
        if ref.cite_key not in bib_keys:
            findings.append(
                Finding(
                    check=CheckId.ANCHOR_UNRESOLVED,
                    severity=Severity.WARN,
                    message=f"anchor references unknown cite_key {ref.cite_key!r}",
                    locator=ref.cite_key,
                )
            )
            continue

        anchor = anchors_by_id.get(ref.anchor_id)
        if anchor is None:
            findings.append(
                Finding(
                    check=CheckId.ANCHOR_UNRESOLVED,
                    severity=Severity.WARN,
                    message=f"anchor id {ref.anchor_id!r} not found in claim manifest",
                    locator=ref.cite_key,
                )
            )
            continue

        if anchor.kind is not AnchorKind.QUOTE:
            findings.append(
                Finding(
                    check=CheckId.ANCHOR_UNVERIFIABLE,
                    severity=Severity.INFO,
                    message=f"anchor kind={anchor.kind.value} unverifiable "
                    "(source structure not tracked)",
                    locator=ref.cite_key,
                )
            )
            continue

        source_text = source_texts.get(ref.cite_key)
        if source_text is None:
            findings.append(
                Finding(
                    check=CheckId.ANCHOR_UNVERIFIABLE,
                    severity=Severity.INFO,
                    message="anchor unverifiable (no stored full text for this source)",
                    locator=ref.cite_key,
                )
            )
            continue

        if _normalize_value(anchor.value) not in _normalize_value(source_text):
            findings.append(
                Finding(
                    check=CheckId.ANCHOR_QUOTE_MISMATCH,
                    severity=Severity.BLOCK,
                    message="quoted anchor text does not appear in the cited source",
                    locator=ref.cite_key,
                    evidence=(anchor.value,),
                    remediation=(
                        "Fix the quote to match the source, or drop the "
                        "anchor if the claim isn't actually a direct quote."
                    ),
                )
            )
    return tuple(findings)
