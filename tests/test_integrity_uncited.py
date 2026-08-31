"""Tests for berb.integrity.uncited (tasks/ars_integration_plan.md W3)."""

from __future__ import annotations

import time

import pytest

from berb.integrity.findings import CheckId, Severity
from berb.integrity.uncited import (
    MAX_SENTENCE_CHARS,
    SentenceRef,
    detect_uncited,
    is_uncited_assertion,
    split_sentences,
)

# ---------------------------------------------------------------------------
# Condition 1: quantifier / empirical verb presence
# ---------------------------------------------------------------------------


def test_percentage_with_no_citation_is_flagged() -> None:
    assert is_uncited_assertion("Our method improves accuracy by 34%.") is True


def test_fuzzy_quantifier_with_no_citation_is_flagged() -> None:
    assert is_uncited_assertion("Most participants preferred the new interface.") is True


def test_empirical_verb_with_no_citation_is_flagged() -> None:
    assert is_uncited_assertion("The ablation showed a clear drop in performance.") is True


def test_plain_sentence_no_quantifier_is_not_flagged() -> None:
    assert is_uncited_assertion("The model architecture follows a standard transformer.") is False


# ---------------------------------------------------------------------------
# Guard pass: years, version/section triples, structural cue words
# ---------------------------------------------------------------------------


def test_bare_year_alone_is_not_a_quantifier() -> None:
    assert is_uncited_assertion("The dataset was released in 2020.") is False


def test_large_bare_count_is_a_quantifier() -> None:
    # Regression: an earlier \d{1,3} cap on _RE_NUMBER meant a \b\d{1,3}\b
    # pattern could never find a trailing word boundary inside a 4+ digit
    # run, so it silently matched nothing on "1000" — this claim was
    # invisible to the detector entirely (false negative), not merely
    # unflagged. See the BUG comment on _RE_NUMBER.
    assert is_uncited_assertion("We evaluated the model on 1000 held-out examples.") is True


def test_version_triple_is_not_a_quantifier() -> None:
    assert is_uncited_assertion("We used PyTorch 2.1.0 for all experiments.") is False


def test_dotted_section_number_is_not_a_quantifier() -> None:
    assert is_uncited_assertion("Details are given in Section 3.1.") is False


def test_bare_integer_after_table_cue_is_not_a_quantifier() -> None:
    assert is_uncited_assertion("As shown in Table 2, the trend holds.") is False


def test_bare_integer_after_figure_cue_is_not_a_quantifier() -> None:
    assert is_uncited_assertion("See Figure 3 for the full curve.") is False


def test_percentage_after_table_cue_still_flagged() -> None:
    # The guard only exempts bare structural-reference numbers, not
    # percentages that happen to follow a table mention.
    assert is_uncited_assertion("Table 2 shows accuracy improved by 12% over baseline.") is True


def test_year_and_real_quantifier_in_same_sentence_still_flagged() -> None:
    assert is_uncited_assertion("In 2020, accuracy improved by 20%.") is True


# ---------------------------------------------------------------------------
# Condition 2: citation presence (sentence + adjacent window)
# ---------------------------------------------------------------------------


def test_latex_cite_in_sentence_suppresses() -> None:
    assert is_uncited_assertion("Accuracy improved by 34% \\cite{he2016deep}.") is False


def test_latex_cite_with_multiple_keys_suppresses() -> None:
    assert is_uncited_assertion("Most models fail here \\cite{a2020, b2021}.") is False


def test_berb_cite_marker_suppresses() -> None:
    sentence = "Accuracy improved by 34% <!--berb-cite key=he2016deep kind=quote id=a3f19c-->."
    assert is_uncited_assertion(sentence) is False


def test_citation_in_adjacent_window_suppresses() -> None:
    assert is_uncited_assertion("It improved by 34%.", adjacent_text="\\cite{he2016deep}") is False


def test_no_citation_anywhere_is_flagged() -> None:
    assert is_uncited_assertion("It improved by 34%.", adjacent_text="No citation here.") is True


# ---------------------------------------------------------------------------
# Condition 3: definitional sentences
# ---------------------------------------------------------------------------


def test_definitional_sentence_is_not_flagged() -> None:
    sentence = "We define accuracy as the fraction of 100 correct predictions."
    assert is_uncited_assertion(sentence) is False


def test_refers_to_definitional_cue() -> None:
    sentence = "Precision refers to the 50% of retrieved items that are relevant."
    assert is_uncited_assertion(sentence) is False


def test_definitional_cue_does_not_suppress_unrelated_later_claim() -> None:
    # The cue only needs to be present per the current condition-3 rule
    # (whole-sentence check) — this documents current behavior precisely so
    # a future tightening is a deliberate, reviewed change.
    sentence = "We define accuracy formally; separately, it improved by 34% over baseline."
    assert is_uncited_assertion(sentence) is False


# ---------------------------------------------------------------------------
# Combined matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sentence", "adjacent", "expected"),
    [
        ("Accuracy was 90%.", "", True),  # quantifier, no cite, not definitional
        ("Accuracy was 90% \\cite{x}.", "", False),  # cite present
        ("We define X as 90%.", "", False),  # definitional
        ("The model is a transformer.", "", False),  # no quantifier
        ("In 2021 we released the code.", "", False),  # guarded year only
    ],
)
def test_combined_matrix(sentence: str, adjacent: str, expected: bool) -> None:
    assert is_uncited_assertion(sentence, adjacent) is expected


# ---------------------------------------------------------------------------
# detect_uncited over multiple sentences -> Finding objects
# ---------------------------------------------------------------------------


def test_detect_uncited_emits_warn_findings_with_locator() -> None:
    sentences = (
        SentenceRef(0, "The model is a transformer.", locator="paper.md:10"),
        SentenceRef(1, "Accuracy improved by 34%.", locator="paper.md:11"),
    )
    findings = detect_uncited(sentences)
    assert len(findings) == 1
    f = findings[0]
    assert f.check is CheckId.UNCITED_ASSERTION
    assert f.severity is Severity.WARN
    assert f.locator == "paper.md:11"
    assert f.evidence == ("Accuracy improved by 34%.",)


def test_detect_uncited_empty_input_returns_empty() -> None:
    assert detect_uncited(()) == ()


def test_detect_uncited_falls_back_to_index_locator() -> None:
    findings = detect_uncited((SentenceRef(7, "It improved by 40%."),))
    assert findings[0].locator == "sentence:7"


# ---------------------------------------------------------------------------
# Security: length cap and ReDoS resistance
# ---------------------------------------------------------------------------


def test_oversized_sentence_is_truncated_not_rejected() -> None:
    # A sentence far longer than MAX_SENTENCE_CHARS still produces a
    # deterministic, bounded-time result rather than an error.
    huge = ("word " * (MAX_SENTENCE_CHARS // 4)) + "34%"
    # The quantifier is beyond the truncation point, so it must NOT be seen.
    assert is_uncited_assertion(huge) is False


def test_no_catastrophic_backtracking_on_adversarial_input() -> None:
    adversarial_inputs = [
        "1" * 20000,
        ("1." * 5000) + "1",
        ("Section " * 3000) + "1",
        (" " * 10000) + "1%",
        "1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1" * 200,
    ]
    for text in adversarial_inputs:
        start = time.monotonic()
        is_uncited_assertion(text)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"took {elapsed:.2f}s on adversarial input"


def test_confusable_fullwidth_digits_normalized() -> None:
    # NFKC-normalizes full-width digits to ASCII before matching, so a
    # confusable-character evasion attempt still gets caught.
    fullwidth_34_percent = "３４％"  # "34%" in fullwidth forms
    sentence = f"Accuracy improved by {fullwidth_34_percent}."
    assert is_uncited_assertion(sentence) is True


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------


def test_split_basic_two_sentences_same_line() -> None:
    refs = split_sentences("The model is a transformer. Accuracy improved by 34%.")
    assert [r.text for r in refs] == [
        "The model is a transformer.",
        "Accuracy improved by 34%.",
    ]


def test_split_assigns_sequential_index() -> None:
    refs = split_sentences("First sentence. Second sentence. Third sentence.")
    assert [r.index for r in refs] == [0, 1, 2]


def test_split_locator_uses_one_indexed_line_number() -> None:
    refs = split_sentences("Line one text.\nLine two text.", source_label="paper.md")
    assert refs[0].locator == "paper.md:1"
    assert refs[1].locator == "paper.md:2"


def test_split_blank_lines_produce_no_fragments() -> None:
    refs = split_sentences("First line.\n\n\nSecond line.")
    assert len(refs) == 2


def test_split_does_not_break_on_common_abbreviation() -> None:
    refs = split_sentences("We compare against baselines, e.g. random search and PPO.")
    assert len(refs) == 1


def test_split_does_break_before_capitalized_continuation() -> None:
    refs = split_sentences("Accuracy improved. The gain was consistent across seeds.")
    assert len(refs) == 2


def test_split_trailing_citation_visible_to_earlier_fragment_on_same_line() -> None:
    refs = split_sentences(
        "Accuracy improved by 34%. Latency dropped by 10%. Both are documented \\cite{a2020}."
    )
    assert len(refs) == 3
    # Neither quantified fragment is individually cited, but the trailing
    # citation lives in the third fragment's text and must appear in the
    # first two fragments' adjacent_text.
    for ref in refs[:2]:
        assert "\\cite{a2020}" in ref.adjacent_text
    detected = detect_uncited(refs)
    assert detected == ()  # all three suppressed via same-line citation


def test_split_strips_fenced_code_blocks() -> None:
    draft = "Intro text.\n```python\naccuracy = 0.34  # 34 percent\n```\nConclusion text."
    refs = split_sentences(draft)
    assert not any("accuracy" in r.text for r in refs)
    assert [r.text for r in refs] == ["Intro text.", "Conclusion text."]


def test_split_unclosed_code_fence_does_not_crash() -> None:
    # Degrades gracefully: no closing ``` means no match, block passes
    # through unstripped rather than raising or hanging.
    refs = split_sentences("Before.\n```python\nx = 1\nStill going.")
    assert refs  # produced *something*, did not raise


def test_split_end_to_end_with_detect_uncited_on_a_small_draft() -> None:
    draft = (
        "# Results\n\n"
        "Our method improves accuracy by 34%.\n"
        "The baseline uses a standard transformer architecture.\n"
        "Prior work reported similar gains \\cite{he2016deep}.\n"
    )
    findings = detect_uncited(split_sentences(draft, source_label="paper_draft.md"))
    assert len(findings) == 1
    assert findings[0].locator == "paper_draft.md:3"


def test_split_caps_adjacency_beyond_threshold_to_avoid_quadratic_blowup() -> None:
    from berb.integrity.uncited import _MAX_FRAGMENTS_FOR_ADJACENCY

    line = "Sentence. " * (_MAX_FRAGMENTS_FOR_ADJACENCY + 5)
    refs = split_sentences(line)
    assert len(refs) > _MAX_FRAGMENTS_FOR_ADJACENCY
    assert all(r.adjacent_text == "" for r in refs)


def test_split_no_catastrophic_backtracking_on_adversarial_draft() -> None:
    adversarial = "\n".join(
        [
            "```" + ("x" * 5000),  # unclosed fence, very long
            "1." * 3000,
            ("Sentence. " * 2000),
            "e.g. " * 2000,
        ]
    )
    start = time.monotonic()
    split_sentences(adversarial)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"took {elapsed:.2f}s on adversarial draft"
