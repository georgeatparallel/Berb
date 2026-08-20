"""Unit tests for berb.agents.benchmark_agent.omissions (P2-03).

No omitted-baseline detector existed before this: reviewer prompt text
asked for "missing baselines" but the review ensemble only sees paper
text, never the literature corpus; experiment_diagnosis's
MISSING_BASELINE detects zero-baseline *runs*, not omitted competitors.
Nothing cross-referenced planned baselines against what was actually
retrieved.
"""

from __future__ import annotations

from berb.agents.benchmark_agent.omissions import (
    extract_corpus_method_names,
    find_omitted_baselines,
)


def test_omitted_baselines_detected() -> None:
    result = find_omitted_baselines(["ResNet-50"], ["ResNet-50", "ViT-B/16"])
    assert result.missing == ("ViT-B/16",)
    assert result.corpus_size == 2


def test_no_omissions_when_corpus_empty() -> None:
    result = find_omitted_baselines(["ResNet-50"], [])
    assert result.missing == ()
    assert result.corpus_size == 0


def test_no_omissions_when_all_covered() -> None:
    result = find_omitted_baselines(
        ["ResNet-50", "ViT-B/16"], ["ResNet-50", "ViT-B/16"]
    )
    assert result.missing == ()


def test_matching_is_substring_case_insensitive() -> None:
    # A plan baseline of "resnet50_v2" should still cover a corpus method
    # named "ResNet50" (case-insensitive substring, not exact match).
    result = find_omitted_baselines(["resnet50_v2 finetuned"], ["ResNet50"])
    assert result.missing == ()


def test_to_dict_shape() -> None:
    result = find_omitted_baselines([], ["GPT-4"])
    d = result.to_dict()
    assert d == {"missing": ["GPT-4"], "corpus_size": 1}


class TestExtractCorpusMethodNames:
    def test_extracts_colon_prefixed_names(self) -> None:
        titles = [
            "BERT: Pre-training of Deep Bidirectional Transformers",
            "ResNet-50: Deep Residual Learning for Image Recognition",
        ]
        names = extract_corpus_method_names(titles)
        assert names == ("BERT", "ResNet-50")

    def test_skips_titles_without_colon_prefix(self) -> None:
        titles = ["A survey of deep learning methods", "Understanding neural networks"]
        assert extract_corpus_method_names(titles) == ()

    def test_deduplicates_case_insensitively(self) -> None:
        titles = [
            "BERT: Pre-training of Deep Bidirectional Transformers",
            "bert: A follow-up analysis",
        ]
        names = extract_corpus_method_names(titles)
        assert names == ("BERT",)

    def test_skips_stopword_leading_tokens(self) -> None:
        titles = ["Towards: A Better Understanding of Transformers"]
        assert extract_corpus_method_names(titles) == ()

    def test_empty_input(self) -> None:
        assert extract_corpus_method_names([]) == ()
