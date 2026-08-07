"""Unit tests for AutomatedReviewerEnsemble's caching wiring (tasks/todo.md #2/#3).

Verifies `_generate_review` passes the paper text via `cached_prefix`
(ttl="1h", since it's reused across all 5 personas in a round) instead of
embedding it in the user message, and that persona.system_prompt is no
longer duplicated between the user message and the `system` param
(tasks/todo.md #3).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from berb.review.ensemble import REVIEWER_PERSONAS, AutomatedReviewerEnsemble

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


def test_paper_text_sent_via_cached_prefix_not_duplicated_in_user_message() -> None:
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content=_VALID_REVIEW_JSON)
    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)
    persona = REVIEWER_PERSONAS[0]
    paper_text = "UNIQUE_PAPER_MARKER " * 50

    asyncio.run(ensemble._generate_review(persona, paper_text))

    mock_llm.chat.assert_called_once()
    _, kwargs = mock_llm.chat.call_args
    assert kwargs["cached_prefix"] == f"PAPER TEXT:\n{paper_text}"
    assert kwargs["cache_ttl"] == "1h"
    assert kwargs["system"] == persona.system_prompt

    user_message = kwargs["messages"][0]["content"]
    assert "UNIQUE_PAPER_MARKER" not in user_message
    assert persona.system_prompt not in user_message


def test_review_still_parses_correctly_with_restructured_prompt() -> None:
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content=_VALID_REVIEW_JSON)
    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)
    persona = REVIEWER_PERSONAS[0]

    review = asyncio.run(ensemble._generate_review(persona, "short paper"))

    assert review.overall_score == 7.0
    assert review.reviewer_id == persona.id
