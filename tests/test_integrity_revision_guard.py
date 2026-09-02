"""Tests for berb.integrity.revision_guard (tasks/ars_integration_plan.md W6)."""

from __future__ import annotations

import json
import time

from berb.integrity.findings import CheckId, Severity, gates
from berb.integrity.revision_guard import (
    conserved_tokens,
    find_claim_drift_candidates,
    strength_advisory,
)


def test_no_change_is_clean() -> None:
    text = "Accuracy improved by 62% \\cite{he2016deep}."
    assert conserved_tokens(text, text) == ()


def test_dropped_number_is_flagged() -> None:
    before = "Accuracy improved by 62%."
    after = "Accuracy improved significantly."
    findings = conserved_tokens(before, after)
    assert len(findings) == 1
    assert findings[0].check is CheckId.TOKEN_CONSERVATION
    assert findings[0].severity is Severity.WARN
    assert findings[0].locator == "62%"


def test_changed_number_is_flagged() -> None:
    # 62% silently became 74% — this is exactly the failure shape the
    # check exists to catch.
    before = "Accuracy improved by 62%."
    after = "Accuracy improved by 74%."
    findings = conserved_tokens(before, after)
    assert len(findings) == 1
    assert findings[0].locator == "62%"


def test_dropped_citation_key_is_flagged() -> None:
    before = "Prior work showed this \\cite{he2016deep}."
    after = "Prior work showed this."
    findings = conserved_tokens(before, after)
    assert len(findings) == 1
    assert findings[0].locator == "he2016deep"
    assert "citation key" in findings[0].message


def test_multi_key_cite_all_tracked() -> None:
    before = "See \\cite{a2020, b2021, c2022}."
    after = "See \\cite{a2020}."
    findings = conserved_tokens(before, after)
    assert {f.locator for f in findings} == {"b2021", "c2022"}


def test_pure_reordering_is_clean() -> None:
    before = "First, accuracy improved by 62%. Second, latency dropped by 10%."
    after = "Latency dropped by 10%. Accuracy also improved by 62%."
    assert conserved_tokens(before, after) == ()


def test_whitespace_only_change_is_clean() -> None:
    before = "Accuracy improved by 62%."
    after = "Accuracy   improved by   62%."
    assert conserved_tokens(before, after) == ()


def test_rounding_reformat_is_tolerated() -> None:
    # 62 -> 62.0 is a reformat, not a dropped number.
    before = "Accuracy was 62."
    after = "Accuracy was 62.0."
    assert conserved_tokens(before, after) == ()


def test_rounding_reformat_with_percent_is_tolerated() -> None:
    before = "Accuracy was 62%."
    after = "Accuracy was 62.00%."
    assert conserved_tokens(before, after) == ()


def test_genuinely_different_decimal_is_still_flagged() -> None:
    before = "Accuracy was 62.34."
    after = "Accuracy was 62.3."
    findings = conserved_tokens(before, after)
    assert len(findings) == 1
    assert findings[0].locator == "62.34"


def test_new_number_added_is_not_flagged() -> None:
    # Conservation only cares about what disappeared, not what was added.
    before = "Accuracy was 62%."
    after = "Accuracy was 62%, and latency was 10ms."
    assert conserved_tokens(before, after) == ()


def test_empty_before_is_clean() -> None:
    assert conserved_tokens("", "Accuracy was 62%.") == ()


def test_empty_after_flags_everything_in_before() -> None:
    before = "Accuracy was 62% \\cite{a2020}."
    findings = conserved_tokens(before, "")
    assert len(findings) == 2


def test_both_empty_is_clean() -> None:
    assert conserved_tokens("", "") == ()


def test_advisory_never_gates_below_submission() -> None:
    findings = conserved_tokens("Accuracy was 62%.", "Accuracy improved.")
    assert gates(findings, "draft") == ()
    assert gates(findings, "submission") == findings
    assert gates(findings, "strict") == findings


def test_findings_are_deterministic() -> None:
    before = "See \\cite{z2020, a2021}. Also 90% and 10%."
    assert conserved_tokens(before, "") == conserved_tokens(before, "")


def test_number_findings_sorted_before_citation_findings_each_group_sorted() -> None:
    before = "See \\cite{z2020, a2021}. Also 90% and 10%."
    findings = conserved_tokens(before, "")
    locators = [f.locator for f in findings]
    # Two numbers first (sorted lexicographically), then two citation keys
    # (also sorted) — matches conserved_tokens' own construction order.
    assert locators == ["10%", "90%", "a2021", "z2020"]


def test_percent_suffix_is_not_dropped_by_trailing_word_boundary() -> None:
    # Regression for the \b-after-optional-% bug: "62%" must be extracted
    # as "62%", not silently truncated to "62".
    before = "Accuracy was 62%."
    after = "Accuracy was different."
    findings = conserved_tokens(before, after)
    assert findings[0].locator == "62%"


def test_bounded_runtime_on_large_input() -> None:
    huge_before = ("word " * 50000) + "62%"
    huge_after = "word " * 50000
    start = time.monotonic()
    conserved_tokens(huge_before, huge_after)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# Layer B — find_claim_drift_candidates
# ---------------------------------------------------------------------------


def test_identical_text_yields_no_candidates() -> None:
    text = "The treatment is associated with improved outcomes."
    assert find_claim_drift_candidates(text, text) == ()


def test_pure_reordering_yields_no_candidates() -> None:
    # Same two sentences, swapped order, verb/hedges unchanged -- not a move.
    before = "First, accuracy improved. Second, latency is associated with load."
    after = "Second, latency is associated with load. First, accuracy improved."
    assert find_claim_drift_candidates(before, after) == ()


def test_changed_sentence_yields_one_candidate() -> None:
    before = "The treatment is associated with improved outcomes."
    after = "The treatment causes improved outcomes."
    candidates = find_claim_drift_candidates(before, after)
    assert len(candidates) == 1
    assert "associated with" in candidates[0].before_text
    assert "causes" in candidates[0].after_text


def test_unrelated_new_sentence_is_not_a_candidate() -> None:
    # A wholly new, unrelated sentence has no similar match above the
    # similarity floor -- it's an addition, not a drifted claim.
    before = "The treatment is associated with improved outcomes."
    after = (
        "The treatment is associated with improved outcomes. "
        "Unrelated: funding was provided by a private foundation."
    )
    assert find_claim_drift_candidates(before, after) == ()


def test_empty_inputs_yield_no_candidates() -> None:
    assert find_claim_drift_candidates("", "") == ()
    assert find_claim_drift_candidates("Some claim.", "") == ()
    assert find_claim_drift_candidates("", "Some claim.") == ()


def test_candidates_bounded_and_most_changed_first() -> None:
    before = " ".join(f"Sentence {i} is associated with outcome {i}." for i in range(30))
    after = " ".join(f"Sentence {i} absolutely causes outcome {i} without question." for i in range(30))
    candidates = find_claim_drift_candidates(before, after)
    assert len(candidates) <= 20


# ---------------------------------------------------------------------------
# Layer B — strength_advisory
# ---------------------------------------------------------------------------


def test_llm_none_returns_empty_and_never_calls() -> None:
    candidates = find_claim_drift_candidates(
        "X is associated with Y.", "X causes Y."
    )
    assert strength_advisory(candidates, None) == ()


def test_drifted_verdict_produces_advisory_finding() -> None:
    candidates = find_claim_drift_candidates(
        "X is associated with Y.", "X causes Y."
    )

    def fake_llm(prompt: str) -> str:
        return json.dumps(
            {"drifted": True, "direction": "strengthened", "rationale": "correlation became causal"}
        )

    findings = strength_advisory(candidates, fake_llm)
    assert len(findings) == 1
    assert findings[0].check is CheckId.CLAIM_STRENGTH_DRIFT
    assert findings[0].severity is Severity.ADVISORY
    assert "strengthened" in findings[0].message


def test_not_drifted_verdict_produces_no_finding() -> None:
    candidates = find_claim_drift_candidates(
        "X is associated with Y.", "X correlates with Y."
    )

    def fake_llm(prompt: str) -> str:
        return json.dumps({"drifted": False, "direction": "none", "rationale": "same strength"})

    assert strength_advisory(candidates, fake_llm) == ()


def test_unparseable_response_is_skipped_not_raised() -> None:
    candidates = find_claim_drift_candidates(
        "X is associated with Y.", "X causes Y."
    )
    assert strength_advisory(candidates, lambda prompt: "not json at all") == ()


def test_llm_exception_is_skipped_not_raised() -> None:
    candidates = find_claim_drift_candidates(
        "X is associated with Y.", "X causes Y."
    )

    def raising_llm(prompt: str) -> str:
        raise RuntimeError("simulated provider failure")

    assert strength_advisory(candidates, raising_llm) == ()


def test_injection_payload_in_response_is_inert_data() -> None:
    # Same class of regression as berb.llm.cross_model's verdict parsing --
    # JSON-only, never eval/exec (commit 334c7a0).
    candidates = find_claim_drift_candidates(
        "X is associated with Y.", "X causes Y."
    )

    def malicious_llm(prompt: str) -> str:
        return '{"drifted": true, "direction": "__import__(\'os\').system(\'echo pwned\')", "rationale": "x"}'

    findings = strength_advisory(candidates, malicious_llm)
    assert len(findings) == 1
    # The malicious "direction" value is not one of the two known values,
    # so it is replaced with the generic label, not executed or echoed raw.
    assert "changed strength" in findings[0].message
    assert "__import__" not in findings[0].message


def test_advisory_finding_never_gates_below_strict() -> None:
    candidates = find_claim_drift_candidates(
        "X is associated with Y.", "X causes Y."
    )

    def fake_llm(prompt: str) -> str:
        return json.dumps({"drifted": True, "direction": "strengthened", "rationale": "x"})

    findings = strength_advisory(candidates, fake_llm)
    assert gates(findings, "draft") == ()
    assert gates(findings, "submission") == ()
    assert gates(findings, "strict") == findings
