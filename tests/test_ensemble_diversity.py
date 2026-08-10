"""Unit tests for AutomatedReviewerEnsemble.area_chair_decision's Review
Diversity Score (P1-02, ScholarPeer's RDS metric).

RDS = 1 - mean pairwise cosine similarity of reviewer detailed_feedback in
embedding space. Detects "artificial hivemind" mode collapse where reviewers
converge on near-identical prose despite different score-space stats.
Uses the zero-dependency TF-IDF embedding backend — no network, no
optional deps required.
"""

from __future__ import annotations

from berb.review.ensemble import (
    REVIEWER_PERSONAS,
    AutomatedReviewerEnsemble,
    Decision,
    Review,
    ReviewDimension,
)

_DIMS = {d: 7 for d in ReviewDimension}


def _review(reviewer_id: str, feedback: str) -> Review:
    persona = next(p for p in REVIEWER_PERSONAS if p.id == reviewer_id)
    return Review(
        reviewer_id=reviewer_id,
        reviewer_name=persona.name,
        scores=dict(_DIMS),
        overall_score=7.0,
        decision=Decision.ACCEPT,
        strengths=["clear"],
        weaknesses=["minor issues"],
        questions_for_authors=[],
        confidence=4,
        detailed_feedback=feedback,
    )


def test_review_diversity_low_for_identical_reviews() -> None:
    ensemble = AutomatedReviewerEnsemble()
    reviews = [
        _review(p.id, "This paper presents a novel method with strong experimental results.")
        for p in REVIEWER_PERSONAS
    ]

    meta = ensemble.area_chair_decision(reviews)

    assert meta.review_diversity < 0.05


def test_review_diversity_high_for_distinct_reviews() -> None:
    ensemble = AutomatedReviewerEnsemble()
    feedbacks = [
        "The novelty claim is overstated given prior work on transformers.",
        "Experimental rigor is lacking — no error bars, no ablation of the key component.",
        "Clarity is poor; Section 3 notation is inconsistent with Section 4.",
        "Reproducibility concerns: hyperparameters for the baseline are never specified.",
        "Significant contribution to few-shot learning benchmarks with strong gains.",
        "Theorem 2's proof has a sign error in the third inequality step.",
    ]
    reviews = [_review(p.id, fb) for p, fb in zip(REVIEWER_PERSONAS, feedbacks, strict=True)]

    meta = ensemble.area_chair_decision(reviews)

    assert meta.review_diversity > 0.1


def test_review_diversity_defaults_to_zero_on_embedding_failure(monkeypatch) -> None:
    def _broken_embedding_provider(*args: object, **kwargs: object) -> None:
        raise RuntimeError("embedding backend unavailable")

    monkeypatch.setattr(
        "berb.memory.embeddings.EmbeddingProvider", _broken_embedding_provider
    )
    ensemble = AutomatedReviewerEnsemble()
    reviews = [_review(p.id, f"Feedback from {p.id}.") for p in REVIEWER_PERSONAS]

    meta = ensemble.area_chair_decision(reviews)

    assert meta.review_diversity == 0.0
    # A broken embedding backend must not break the rest of the decision.
    assert meta.average_score > 0


def test_meta_review_construction_without_review_diversity_kwarg_still_works() -> None:
    """Backwards compat: review_diversity has a default, so existing
    construction call sites (e.g. test doubles built before P1-02) don't
    need updating."""
    from berb.review.ensemble import MetaReview

    meta = MetaReview(
        reviews=[],
        average_score=7.0,
        score_std=0.0,
        max_score=7.0,
        min_score=7.0,
        score_distribution={},
        consensus_decision=Decision.ACCEPT,
        confidence=1.0,
        meta_review_text="",
        acceptance_recommendation="accept",
        reviewer_conflicts=[],
    )
    assert meta.review_diversity == 0.0
