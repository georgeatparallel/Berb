"""Hypothesis-lock check: did the analysis test what the pipeline hypothesized?

Stage 8 (HYPOTHESIS_GEN) and Stage 14 (RESULT_ANALYSIS) share no structured
schema — a hypothesis is free-text prose (``hypotheses.md``) and an analysis
is free-text prose plus a metrics dict keyed by metric name
(``experiment_summary.json``). There's no "outcome variable" field on either
side to compare directly.

What can be checked without inventing a schema neither stage has: whether
the two texts share ANY substantive vocabulary at all. If Stage 14's
analysis and metric names have no lexical overlap whatsoever with the
Stage 8 hypothesis, the pipeline likely drifted onto a different question
than the one it set out to test — this is a coarse, pipeline-level signal,
not a per-hypothesis one, and stays silent (no finding) the moment a single
shared substantive word exists. That's a deliberate precision bias: this
check is only meant to catch total drift, not to judge paraphrase quality.
"""

from __future__ import annotations

import re
from typing import Final

from berb.integrity.findings import CheckId, Finding, Severity

_RE_WORD: Final = re.compile(r"[A-Za-z][A-Za-z-]{2,30}")

# Generic academic filler that would otherwise "connect" any hypothesis to
# any analysis and defeat the check. Not an attempt at general stopwording.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "will",
        "have",
        "been",
        "should",
        "would",
        "could",
        "their",
        "there",
        "which",
        "where",
        "when",
        "study",
        "paper",
        "result",
        "results",
        "using",
        "based",
        "hypothesis",
        "hypothesize",
        "hypothesized",
        "hypothesizes",
        "expect",
        "expected",
        "predict",
        "predicted",
        "analysis",
        "analyses",
        "experiment",
        "experiments",
        "condition",
        "conditions",
        "compared",
        "compare",
        "significant",
        "significantly",
    }
)

_MIN_TOKEN_LEN: Final = 4


def _tokens(text: str) -> frozenset[str]:
    words = (w.lower() for w in _RE_WORD.findall(text))
    return frozenset(w for w in words if len(w) >= _MIN_TOKEN_LEN and w not in _STOPWORDS)


def check_hypothesis_lock(
    hypothesis_text: str,
    analysis_text: str,
    metric_keys: tuple[str, ...] = (),
    *,
    locator: str = "stage-14/analysis.md",
) -> tuple[Finding, ...]:
    """Return an ADVISORY finding if ``analysis_text`` (plus ``metric_keys``)
    shares no substantive vocabulary with ``hypothesis_text``.

    Silent whenever either side is too sparse to judge — an empty or
    near-empty hypothesis or analysis carries no evidence either way, and a
    false positive here costs a human reviewer's attention on nothing.
    Deterministic and total — never raises.
    """
    hyp_tokens = _tokens(hypothesis_text)
    if not hyp_tokens:
        return ()

    analysis_tokens = _tokens(analysis_text) | _tokens(" ".join(metric_keys))
    if not analysis_tokens:
        return ()

    if hyp_tokens & analysis_tokens:
        return ()

    hyp_excerpt = hypothesis_text.strip()[:200]
    return (
        Finding(
            check=CheckId.HYPOTHESIS_LOCK,
            severity=Severity.ADVISORY,
            message=(
                "The analysis shares no vocabulary with the stated hypothesis — "
                "the pipeline may have drifted onto a different question than "
                "the one it set out to test"
            ),
            locator=locator,
            evidence=(hyp_excerpt,) if hyp_excerpt else (),
            remediation=(
                "Check that the analysis addresses the hypothesis's predicted "
                "outcome; if the research direction changed deliberately, "
                "update or replace the recorded hypothesis."
            ),
        ),
    )
