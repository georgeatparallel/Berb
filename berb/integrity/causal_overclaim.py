"""Association-vs-causation overclaim detector.

A sentence is flagged iff it carries BOTH an unambiguous causal connective
("causes", "leads to", "results in", ...) AND a correlational-evidence
marker ("correlat-", "associat-", "r = ", "pearson", ...) — the same
sentence claims causation while naming the kind of evidence (a
correlation/association) that cannot establish it. That colocation
requirement is deliberate: either signal alone is common in ordinary
prose ("this leads to a design choice", "these results are associated
with prior work"), so pairing them in one sentence is what keeps the
false-positive rate low, the same precision-first trade the domain checks
in ``experiment/science_check.py`` make.

Deterministic, offline, no LLM call — same convention as
``berb/integrity/uncited.py``, which this module is designed to run
alongside (see the Stage 17 call site in
``berb/pipeline/stage_impls/_paper_writing.py``).
"""

from __future__ import annotations

from typing import Final

from berb.integrity.findings import CheckId, Finding, Severity
from berb.integrity.uncited import SentenceRef

# Unambiguous causal connectives naming the studied relationship. Deliberately
# excludes "due to" / "because of" — both are common in ordinary
# non-empirical prose ("due to time constraints") and would dominate the
# false-positive rate.
_CAUSAL_MARKERS: Final[tuple[str, ...]] = (
    "causes",
    "cause of",
    "caused by",
    "causing",
    "leads to",
    "led to",
    "results in",
    "resulted in",
    "is responsible for",
    "drives",
    "driving",
)

# Evidence markers for a correlational/associational study design.
_CORRELATIONAL_MARKERS: Final[tuple[str, ...]] = (
    "correlat",
    "associat",
    "covari",
    "pearson",
    "spearman",
    "r = ",
    "r=",
    "regression coefficient",
)


def is_causal_overclaim(sentence: str) -> bool:
    """Pure predicate: does this sentence assert causation while naming
    correlational evidence for it?"""
    lowered = sentence.lower()
    has_causal = any(marker in lowered for marker in _CAUSAL_MARKERS)
    if not has_causal:
        return False
    return any(marker in lowered for marker in _CORRELATIONAL_MARKERS)


def check_causal_overclaim(sentences: tuple[SentenceRef, ...]) -> tuple[Finding, ...]:
    """Scan sentences, returning one ADVISORY finding per causal overclaim.

    ADVISORY, not WARN or BLOCK: this is a heuristic keyword colocation, not
    a certain detection (a sentence can legitimately report both a causal
    identification strategy, e.g. an RCT, and a correlation as a robustness
    check). Deterministic and total — never raises on malformed text.
    """
    findings: list[Finding] = []
    for ref in sentences:
        if is_causal_overclaim(ref.text):
            findings.append(
                Finding(
                    check=CheckId.CAUSAL_OVERCLAIM,
                    severity=Severity.ADVISORY,
                    message=(
                        "Causal language ('causes', 'leads to', ...) describing what "
                        "the same sentence names as correlational evidence"
                    ),
                    locator=ref.locator or f"sentence:{ref.index}",
                    evidence=(ref.text,),
                    remediation=(
                        "Rephrase with associational language (e.g. 'is associated "
                        "with') unless a controlled or causal-identification method "
                        "backs the causal claim — and cite it if so."
                    ),
                )
            )
    return tuple(findings)
