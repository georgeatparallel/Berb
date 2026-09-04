"""berb/integrity/causal_overclaim.py — association-vs-causation overclaim.

Every case tested in both directions: a colocated causal+correlational
sentence fires, either signal alone stays silent (that's the precision
trade the module docstring explains).
"""

from __future__ import annotations

from berb.integrity.causal_overclaim import check_causal_overclaim, is_causal_overclaim
from berb.integrity.uncited import split_sentences


def test_causal_claim_over_correlational_evidence_fires() -> None:
    assert is_causal_overclaim("Screen time causes lower grades (r = 0.42, p < 0.01).")


def test_causal_claim_over_association_wording_fires() -> None:
    assert is_causal_overclaim("These results show that X causes Y, which is strongly associated with Z.")


def test_causal_language_alone_is_silent() -> None:
    """No correlational marker in the sentence — nothing to overclaim from."""
    assert not is_causal_overclaim("This design choice leads to a simpler implementation.")


def test_correlational_language_alone_is_silent() -> None:
    """No causal verb — a plain correlational claim is exactly correct usage."""
    assert not is_causal_overclaim("Screen time is associated with lower grades (r = 0.42).")


def test_unrelated_sentence_is_silent() -> None:
    assert not is_causal_overclaim("We evaluate the model on three benchmark datasets.")


def test_due_to_is_deliberately_not_a_causal_marker() -> None:
    """'due to' is common in non-empirical prose; including it would swamp
    the check with false positives (see module docstring)."""
    assert not is_causal_overclaim(
        "Due to time constraints, we limited the correlation analysis to two variables."
    )


def test_check_causal_overclaim_reports_locator_and_evidence() -> None:
    sentences = split_sentences(
        "Prior work found no link. Screen time causes lower grades (r = 0.42).",
        source_label="paper_draft.md",
    )
    findings = check_causal_overclaim(sentences)
    assert len(findings) == 1
    assert findings[0].check.value == "causal_overclaim"
    assert findings[0].severity.value == "advisory"
    assert "causes lower grades" in findings[0].evidence[0]
    assert findings[0].locator.startswith("paper_draft.md:")


def test_check_causal_overclaim_silent_on_clean_draft() -> None:
    sentences = split_sentences(
        "Screen time is associated with lower grades. We report r = 0.42.",
        source_label="paper_draft.md",
    )
    assert check_causal_overclaim(sentences) == ()
