"""berb/integrity/hypothesis_lock.py — did the analysis test the hypothesis?

The check is deliberately coarse (shared-vocabulary, not semantic
similarity) — see the module docstring for why. Tested in both
directions plus the "too sparse to judge" silence cases.
"""

from __future__ import annotations

from berb.integrity.hypothesis_lock import check_hypothesis_lock

_HYPOTHESIS = "We hypothesize that increasing batch size improves throughput on the accelerator."


def test_shared_vocabulary_is_silent() -> None:
    analysis = "Batch size increases correlate with higher throughput across all runs."
    assert check_hypothesis_lock(_HYPOTHESIS, analysis) == ()


def test_shared_vocabulary_via_metric_keys_is_silent() -> None:
    analysis = "Results were inconclusive across conditions."
    assert check_hypothesis_lock(_HYPOTHESIS, analysis, ("throughput_tokens_per_sec",)) == ()


def test_no_shared_vocabulary_fires() -> None:
    analysis = "The model's memory footprint stayed flat across all seeds."
    findings = check_hypothesis_lock(_HYPOTHESIS, analysis)
    assert len(findings) == 1
    assert findings[0].check.value == "hypothesis_lock"
    assert findings[0].severity.value == "advisory"
    assert "batch size" in findings[0].evidence[0].lower()


def test_empty_hypothesis_is_silent() -> None:
    """Nothing to compare against — silence, not a false accusation."""
    assert check_hypothesis_lock("", "Completely unrelated analysis text here.") == ()


def test_empty_analysis_is_silent() -> None:
    assert check_hypothesis_lock(_HYPOTHESIS, "") == ()


def test_finding_locator_defaults_to_stage_14() -> None:
    analysis = "Nothing relevant was measured in this run."
    findings = check_hypothesis_lock(_HYPOTHESIS, analysis)
    assert findings[0].locator == "stage-14/analysis.md"
