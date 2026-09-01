"""Tests for berb.integrity.revision_guard (tasks/ars_integration_plan.md W6, Layer A)."""

from __future__ import annotations

import time

from berb.integrity.findings import CheckId, Severity, gates
from berb.integrity.revision_guard import conserved_tokens


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
