"""Revision guard — deterministic token conservation (tasks/ars_integration_plan.md W6, Layer A).

``PAPER_REVISION`` (stage 19) can silently change what a paper claims: a
number quietly becomes a different number, a citation quietly disappears.
This is Layer A only — deterministic, no LLM, high precision: numeric
literals and citation keys present in the pre-revision text must still be
present after, unless the change is an intentional rounding/reformat.

Layer B (claim-strength drift — "associated with" silently becoming
"causes") is LLM-advisory by design and is not implemented here; see the
plan's design note on why a deterministic token check and a semantic
claim-strength check are necessary-but-not-sufficient complements, not
substitutes for each other.

Severity is ``WARN`` — high precision, not certainty. The known
false-positive shape is legitimate reformatting (``62%`` -> ``62.0%``),
which is why numbers are compared after stripping trailing zeros; a
finding's remediation names this explicitly rather than pretending the
check is infallible.
"""

from __future__ import annotations

import re
from typing import Final

from berb.integrity.findings import CheckId, Finding, Severity

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
