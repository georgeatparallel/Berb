"""Unit tests for P3-01's 6th reviewer persona (Proof & Derivation Checker).

PAT's headline result — 55.2% -> 89.7% recall on math/proof errors — comes
from a dedicated high-budget rigor reviewer. Berb had zero mathematical or
logical verification anywhere before this persona existed.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from berb.review.ensemble import REVIEWER_PERSONAS, AutomatedReviewerEnsemble, ReviewDimension

_VALID_REVIEW_JSON = json.dumps(
    {
        "scores": {
            "novelty": 7,
            "significance": 7,
            "technical_quality": 7,
            "experimental_rigor": 7,
            "clarity": 7,
            "reproducibility": 7,
        },
        "overall_score": 7.0,
        "decision": "accept",
        "strengths": ["clear"],
        "weaknesses": ["none"],
        "questions_for_authors": [],
        "confidence": 4,
        "detailed_feedback": "Solid work.",
    }
)


def test_six_personas_registered() -> None:
    assert len(REVIEWER_PERSONAS) == 6
    assert len({p.id for p in REVIEWER_PERSONAS}) == 6


def test_proof_persona_present_and_distinct_from_experimental_rigor() -> None:
    proof_persona = next(p for p in REVIEWER_PERSONAS if p.id == "reviewer_6")
    rigor_persona = next(p for p in REVIEWER_PERSONAS if p.id == "reviewer_3")
    assert proof_persona.name != rigor_persona.name
    assert "proof" in proof_persona.name.lower() or "derivation" in proof_persona.name.lower()


def test_proof_persona_reuses_technical_quality_dimension() -> None:
    # Reusing an existing dimension (not adding a 7th) keeps the weighted
    # score average and the JSON schema in _build_review_prompt unchanged.
    proof_persona = next(p for p in REVIEWER_PERSONAS if p.id == "reviewer_6")
    assert proof_persona.focus_areas == [ReviewDimension.TECHNICAL_QUALITY]


def test_proof_persona_has_larger_max_tokens_than_others() -> None:
    proof_persona = next(p for p in REVIEWER_PERSONAS if p.id == "reviewer_6")
    others = [p for p in REVIEWER_PERSONAS if p.id != "reviewer_6"]
    assert proof_persona.max_tokens is not None
    assert all(
        other.max_tokens is None or proof_persona.max_tokens > other.max_tokens
        for other in others
    )


def test_other_personas_have_no_max_tokens_override() -> None:
    for persona in REVIEWER_PERSONAS:
        if persona.id != "reviewer_6":
            assert persona.max_tokens is None


def test_sync_path_passes_proof_persona_max_tokens() -> None:
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content=_VALID_REVIEW_JSON)
    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)

    asyncio.run(ensemble.review_paper("paper.md", paper_text="text", use_batch=False))

    proof_calls = [
        c for c in mock_llm.chat.call_args_list if c.kwargs.get("max_tokens") == 8192
    ]
    assert len(proof_calls) == 1


def test_meta_review_text_reports_actual_reviewer_count() -> None:
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content=_VALID_REVIEW_JSON)
    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)

    reviews = asyncio.run(
        ensemble.review_paper("paper.md", paper_text="text", use_batch=False)
    )
    meta = ensemble.area_chair_decision(reviews)

    assert f"from {len(REVIEWER_PERSONAS)} reviewers" in meta.meta_review_text
    assert "from 5 reviewers" not in meta.meta_review_text
