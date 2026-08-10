"""Unit tests for P3-03's critique dedup/synthesis pass (PAT's Global
Synthesis stage). Purely additive — must never touch area_chair_decision's
score aggregation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from berb.review.ensemble import (
    REVIEWER_PERSONAS,
    AutomatedReviewerEnsemble,
    Decision,
    Review,
    ReviewDimension,
)

_DIMS = {d: 7 for d in ReviewDimension}


def _review(reviewer_id: str) -> Review:
    persona = next(p for p in REVIEWER_PERSONAS if p.id == reviewer_id)
    return Review(
        reviewer_id=reviewer_id,
        reviewer_name=persona.name,
        scores=dict(_DIMS),
        overall_score=7.0,
        decision=Decision.ACCEPT,
        strengths=["clear writing"],
        weaknesses=["missing ablation"],
        questions_for_authors=[],
        confidence=4,
        detailed_feedback="ok",
    )


def test_synthesize_critiques_returns_empty_without_llm() -> None:
    ensemble = AutomatedReviewerEnsemble()
    result = asyncio.run(ensemble.synthesize_critiques([_review(p.id) for p in REVIEWER_PERSONAS]))
    assert result == ""


def test_synthesize_critiques_calls_llm_with_review_content() -> None:
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="Clustered: missing ablation (3 reviewers)")
    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)
    reviews = [_review(p.id) for p in REVIEWER_PERSONAS]

    result = asyncio.run(ensemble.synthesize_critiques(reviews))

    assert result == "Clustered: missing ablation (3 reviewers)"
    prompt = mock_llm.chat.call_args.kwargs["messages"][0]["content"]
    assert "missing ablation" in prompt


def test_synthesize_critiques_swallows_llm_failure() -> None:
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("unavailable")
    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)

    result = asyncio.run(ensemble.synthesize_critiques([_review(REVIEWER_PERSONAS[0].id)]))

    assert result == ""


def test_area_chair_decision_score_unaffected_by_synthesis() -> None:
    """Regression guard: critique_synthesis must be settable without
    changing any score computed by area_chair_decision."""
    ensemble = AutomatedReviewerEnsemble()
    reviews = [_review(p.id) for p in REVIEWER_PERSONAS]

    meta_before = ensemble.area_chair_decision(reviews)
    meta_before.critique_synthesis = "some synthesis text"

    meta_after = ensemble.area_chair_decision(reviews)

    assert meta_before.average_score == meta_after.average_score
    assert meta_before.consensus_decision == meta_after.consensus_decision
    assert meta_after.critique_synthesis == ""  # unset until the caller sets it


def test_generate_review_report_includes_synthesis_section_when_present() -> None:
    ensemble = AutomatedReviewerEnsemble()
    reviews = [_review(p.id) for p in REVIEWER_PERSONAS]
    meta = ensemble.area_chair_decision(reviews)
    meta.critique_synthesis = "Multiple reviewers flagged the missing ablation."

    report = ensemble.generate_review_report(reviews, meta)

    assert "Cross-Reviewer Critique Synthesis" in report
    assert "Multiple reviewers flagged the missing ablation." in report


def test_generate_review_report_omits_synthesis_section_when_empty() -> None:
    ensemble = AutomatedReviewerEnsemble()
    reviews = [_review(p.id) for p in REVIEWER_PERSONAS]
    meta = ensemble.area_chair_decision(reviews)

    report = ensemble.generate_review_report(reviews, meta)

    assert "Cross-Reviewer Critique Synthesis" not in report
