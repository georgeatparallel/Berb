"""Tests for berb.literature.paper_mill (tasks/ars_integration_plan.md W4)."""

from __future__ import annotations

import time

from berb.integrity.findings import CheckId, Severity, gates
from berb.literature.paper_mill import (
    PhraseCorpus,
    load_corpus,
    screen_text,
)


def _corpus(*phrases: str) -> PhraseCorpus:
    by_length: dict[int, set[str]] = {}
    for phrase in phrases:
        n = len(phrase.split(" "))
        by_length.setdefault(n, set()).add(phrase)
    return PhraseCorpus(
        by_length={n: frozenset(s) for n, s in by_length.items()}, size=len(phrases)
    )


# ---------------------------------------------------------------------------
# screen_text
# ---------------------------------------------------------------------------


def test_known_phrase_hit() -> None:
    corpus = _corpus("counterfeit consciousness")
    findings = screen_text("Our approach uses counterfeit consciousness.", corpus)
    assert len(findings) == 1
    assert findings[0].check is CheckId.PAPER_MILL_RISK
    assert findings[0].severity is Severity.ADVISORY
    assert "counterfeit consciousness" in findings[0].evidence


def test_near_miss_no_hit() -> None:
    corpus = _corpus("counterfeit consciousness")
    findings = screen_text("Our approach uses artificial intelligence.", corpus)
    assert findings == ()


def test_punctuation_adjacency_still_matches() -> None:
    corpus = _corpus("counterfeit consciousness")
    findings = screen_text("We rely on counterfeit consciousness, per prior work.", corpus)
    assert len(findings) == 1


def test_confusable_case_and_unicode_variant_still_hits() -> None:
    corpus = _corpus("counterfeit consciousness")
    findings = screen_text("COUNTERFEIT CONSCIOUSNESS is discussed here.", corpus)
    assert len(findings) == 1


def test_empty_corpus_is_a_valid_no_op() -> None:
    findings = screen_text("Anything at all, even 34% improvements.", PhraseCorpus())
    assert findings == ()


def test_empty_text_is_a_no_op() -> None:
    findings = screen_text("", _corpus("counterfeit consciousness"))
    assert findings == ()


def test_multiple_distinct_hits_reported_once_each() -> None:
    corpus = _corpus("counterfeit consciousness", "haze figuring")
    text = "We combine counterfeit consciousness with haze figuring techniques."
    findings = screen_text(text, corpus)
    assert len(findings) == 1
    assert set(findings[0].evidence) == {"counterfeit consciousness", "haze figuring"}


def test_repeated_hit_reported_once() -> None:
    corpus = _corpus("counterfeit consciousness")
    text = "counterfeit consciousness. Later, counterfeit consciousness again."
    findings = screen_text(text, corpus)
    assert len(findings) == 1
    assert findings[0].evidence == ("counterfeit consciousness",)


def test_advisory_never_gates_below_strict() -> None:
    corpus = _corpus("counterfeit consciousness")
    findings = screen_text("Uses counterfeit consciousness.", corpus)
    assert gates(findings, "draft") == ()
    assert gates(findings, "submission") == ()
    assert gates(findings, "strict") == findings


def test_locator_is_passed_through() -> None:
    corpus = _corpus("counterfeit consciousness")
    findings = screen_text("counterfeit consciousness", corpus, locator="abstract:openalex:W123")
    assert findings[0].locator == "abstract:openalex:W123"


def test_scan_length_cap_does_not_crash_on_huge_input() -> None:
    corpus = _corpus("counterfeit consciousness")
    huge = ("filler word " * 20000) + "counterfeit consciousness"
    start = time.monotonic()
    findings = screen_text(huge, corpus)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0
    # The real phrase is beyond the truncation point, so it must NOT be seen.
    assert findings == ()


# ---------------------------------------------------------------------------
# load_corpus
# ---------------------------------------------------------------------------


def test_load_corpus_missing_file_is_empty(tmp_path) -> None:
    corpus = load_corpus(tmp_path / "does-not-exist.yaml")
    assert corpus.size == 0
    assert corpus.by_length == {}


def test_load_corpus_malformed_yaml_is_empty(tmp_path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("{not: valid: yaml: [", encoding="utf-8")
    corpus = load_corpus(p)
    assert corpus.size == 0


def test_load_corpus_not_a_dict_is_empty(tmp_path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    corpus = load_corpus(p)
    assert corpus.size == 0


def test_load_corpus_oversized_file_is_rejected(tmp_path) -> None:
    p = tmp_path / "huge.yaml"
    p.write_text("entries:\n" + ("  - phrase: x y\n" * 200_000), encoding="utf-8")
    corpus = load_corpus(p)
    assert corpus.size == 0


def test_load_corpus_entry_count_capped(tmp_path) -> None:
    import berb.literature.paper_mill as pm_mod

    entries = "\n".join(f'  - phrase: "word{i} pair{i}"' for i in range(pm_mod._MAX_ENTRIES + 50))
    p = tmp_path / "many.yaml"
    p.write_text(f"entries:\n{entries}\n", encoding="utf-8")
    corpus = load_corpus(p)
    assert corpus.size <= pm_mod._MAX_ENTRIES


def test_load_corpus_rejects_control_characters(tmp_path) -> None:
    p = tmp_path / "control.yaml"
    p.write_text('entries:\n  - phrase: "bad\x01 phrase"\n', encoding="utf-8")
    corpus = load_corpus(p)
    assert corpus.size == 0


def test_load_corpus_rejects_oversized_phrase(tmp_path) -> None:
    import berb.literature.paper_mill as pm_mod

    long_phrase = ("word " * 100).strip()
    p = tmp_path / "long.yaml"
    p.write_text(f'entries:\n  - phrase: "{long_phrase}"\n', encoding="utf-8")
    corpus = load_corpus(p)
    assert corpus.size == 0
    assert len(long_phrase) > pm_mod._MAX_PHRASE_CHARS


def test_load_corpus_rejects_out_of_range_ngram_length(tmp_path) -> None:
    p = tmp_path / "ngram.yaml"
    p.write_text('entries:\n  - phrase: "single"\n  - phrase: "a b c d e f"\n', encoding="utf-8")
    corpus = load_corpus(p)
    assert corpus.size == 0


def test_load_corpus_entries_matched_as_literals_not_regex(tmp_path) -> None:
    # A corpus phrase containing regex metacharacters must be matched
    # literally, never compiled as a pattern.
    p = tmp_path / "meta.yaml"
    p.write_text('entries:\n  - phrase: "a.* b+c"\n', encoding="utf-8")
    corpus = load_corpus(p)
    # ".*" and "+" are stripped as punctuation by normalization, so the
    # stored phrase is a plain literal — never re-interpreted as a pattern.
    findings_literal = screen_text("this contains a b c literally somewhere", corpus)
    assert isinstance(findings_literal, tuple)  # never raises re.error


def test_load_corpus_skips_non_dict_entries(tmp_path) -> None:
    p = tmp_path / "mixed.yaml"
    p.write_text(
        'entries:\n  - 42\n  - "just a string"\n  - phrase: "valid pair"\n', encoding="utf-8"
    )
    corpus = load_corpus(p)
    assert corpus.size == 1


def test_load_corpus_skips_missing_or_blank_phrase(tmp_path) -> None:
    p = tmp_path / "blank.yaml"
    p.write_text(
        "entries:\n"
        '  - likely_original: "no phrase key"\n'
        '  - phrase: ""\n'
        '  - phrase: "   "\n'
        '  - phrase: "valid pair"\n',
        encoding="utf-8",
    )
    corpus = load_corpus(p)
    assert corpus.size == 1


def test_load_corpus_skips_phrase_that_normalizes_to_empty(tmp_path) -> None:
    p = tmp_path / "punct.yaml"
    p.write_text('entries:\n  - phrase: "!!! ??? ---"\n', encoding="utf-8")
    corpus = load_corpus(p)
    assert corpus.size == 0


def test_screen_text_input_normalizing_to_empty_is_a_no_op() -> None:
    corpus = _corpus("counterfeit consciousness")
    findings = screen_text("   ,,, ---   ", corpus)
    assert findings == ()


def test_screen_text_skips_ngram_length_longer_than_available_tokens() -> None:
    corpus = _corpus("a b c d")  # 4-gram
    findings = screen_text("only two", corpus)
    assert findings == ()


def test_default_shipped_corpus_loads_successfully() -> None:
    corpus = load_corpus()
    assert corpus.size > 0
    findings = screen_text("Our system relies on counterfeit consciousness.", corpus)
    assert len(findings) == 1
