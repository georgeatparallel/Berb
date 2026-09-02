"""Unit tests for AutomatedReviewerEnsemble's batch review path
(tasks/todo.md #5 — the 5-persona review fan-out as the first batch unit).

No network calls — the fake Anthropic adapter below stands in for
AnthropicAdapter.submit_batch/get_batch_status/fetch_batch_results.
Every failure mode must resolve to None (never raise), since the caller's
contract is "fall back to the synchronous per-persona path".
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
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


def _fake_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


class _FakeAnthropicAdapter:
    def __init__(self, *, statuses=None, results=None, fail_submit=False, fail_status=False):
        self.fail_submit = fail_submit
        self.fail_status = fail_status
        self._statuses = list(statuses or [])
        self._results = results or {}
        self.submitted_requests: list[dict] = []

    def submit_batch(self, requests):
        if self.fail_submit:
            raise RuntimeError("submit failed")
        self.submitted_requests = requests
        return "batch_123"

    def get_batch_status(self, batch_id):
        if self.fail_status:
            raise RuntimeError("status failed")
        if self._statuses:
            return self._statuses.pop(0)
        return {"processing_status": "in_progress"}

    def fetch_batch_results(self, results_url):
        return self._results


def _make_llm_client(anthropic=None, primary_model="claude-sonnet-4-5"):
    return SimpleNamespace(
        _anthropic=anthropic,
        config=SimpleNamespace(primary_model=primary_model, max_tokens=4096, temperature=0.7),
    )


class TestReviewPaperBatch:
    def test_returns_none_without_anthropic_adapter(self) -> None:
        # llm client with no _anthropic attribute at all (e.g. OpenRouter-
        # backed LLMClient) — batch mode is Anthropic-direct only.
        ensemble = AutomatedReviewerEnsemble(llm_client=SimpleNamespace())
        result = asyncio.run(ensemble._review_paper_batch("paper text"))
        assert result is None

    def test_returns_none_when_primary_model_missing(self) -> None:
        adapter = _FakeAnthropicAdapter()
        client = _make_llm_client(anthropic=adapter, primary_model="")
        ensemble = AutomatedReviewerEnsemble(llm_client=client)
        result = asyncio.run(ensemble._review_paper_batch("paper text"))
        assert result is None

    def test_submits_one_request_per_persona(self) -> None:
        adapter = _FakeAnthropicAdapter(
            statuses=[{"processing_status": "ended", "results_url": "https://x/results"}],
            results={
                persona.id: _fake_response(_VALID_REVIEW_JSON) for persona in REVIEWER_PERSONAS
            },
        )
        client = _make_llm_client(anthropic=adapter)
        ensemble = AutomatedReviewerEnsemble(llm_client=client)

        reviews = asyncio.run(
            ensemble._review_paper_batch("paper text", poll_interval_sec=0.01, max_wait_sec=0.5)
        )

        assert reviews is not None
        assert len(adapter.submitted_requests) == len(REVIEWER_PERSONAS)
        assert {r["custom_id"] for r in adapter.submitted_requests} == {
            p.id for p in REVIEWER_PERSONAS
        }
        assert len(reviews) == len(REVIEWER_PERSONAS)
        assert all(r.overall_score == 7.0 for r in reviews)

    def test_applies_cached_prefix_and_system_per_persona(self) -> None:
        adapter = _FakeAnthropicAdapter(
            statuses=[{"processing_status": "ended", "results_url": "https://x/results"}],
            results={
                persona.id: _fake_response(_VALID_REVIEW_JSON) for persona in REVIEWER_PERSONAS
            },
        )
        client = _make_llm_client(anthropic=adapter)
        ensemble = AutomatedReviewerEnsemble(llm_client=client)

        asyncio.run(
            ensemble._review_paper_batch(
                "UNIQUE_MARKER paper text", poll_interval_sec=0.01, max_wait_sec=0.5
            )
        )

        req = adapter.submitted_requests[0]
        assert req["cached_prefix"] == "PAPER TEXT:\nUNIQUE_MARKER paper text"
        assert req["cache_ttl"] == "1h"
        system_messages = [m for m in req["messages"] if m["role"] == "system"]
        assert len(system_messages) == 1

    def test_returns_none_on_submit_failure(self) -> None:
        adapter = _FakeAnthropicAdapter(fail_submit=True)
        client = _make_llm_client(anthropic=adapter)
        ensemble = AutomatedReviewerEnsemble(llm_client=client)

        result = asyncio.run(ensemble._review_paper_batch("paper text"))
        assert result is None

    def test_returns_none_on_status_poll_failure(self) -> None:
        adapter = _FakeAnthropicAdapter(fail_status=True)
        client = _make_llm_client(anthropic=adapter)
        ensemble = AutomatedReviewerEnsemble(llm_client=client)

        result = asyncio.run(
            ensemble._review_paper_batch("paper text", poll_interval_sec=0.01, max_wait_sec=0.5)
        )
        assert result is None

    def test_returns_none_when_batch_never_ends_within_max_wait(self) -> None:
        # No "ended" status ever queued — every poll comes back in_progress.
        adapter = _FakeAnthropicAdapter()
        client = _make_llm_client(anthropic=adapter)
        ensemble = AutomatedReviewerEnsemble(llm_client=client)

        result = asyncio.run(
            ensemble._review_paper_batch("paper text", poll_interval_sec=0.02, max_wait_sec=0.05)
        )
        assert result is None

    def test_missing_persona_result_falls_back_to_unavailable_review(self) -> None:
        # Batch ends but one persona's entry is missing from the results
        # (e.g. it errored server-side) — that persona gets the honest
        # "unavailable" placeholder instead of the whole batch failing.
        partial_results = {
            persona.id: _fake_response(_VALID_REVIEW_JSON) for persona in REVIEWER_PERSONAS[:-1]
        }
        adapter = _FakeAnthropicAdapter(
            statuses=[{"processing_status": "ended", "results_url": "https://x/results"}],
            results=partial_results,
        )
        client = _make_llm_client(anthropic=adapter)
        ensemble = AutomatedReviewerEnsemble(llm_client=client)

        reviews = asyncio.run(
            ensemble._review_paper_batch("paper text", poll_interval_sec=0.01, max_wait_sec=0.5)
        )

        assert reviews is not None
        assert len(reviews) == len(REVIEWER_PERSONAS)
        missing_persona_id = REVIEWER_PERSONAS[-1].id
        missing_review = next(r for r in reviews if r.reviewer_id == missing_persona_id)
        assert "could not be generated" in missing_review.detailed_feedback.lower()


class TestReviewPaperUsesBatchFlag:
    def test_use_batch_false_never_calls_batch_path(self) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = MagicMock(content=_VALID_REVIEW_JSON)
        ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)
        ensemble._review_paper_batch = MagicMock()  # would fail the test if called

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            paper_path = Path(tmp) / "paper.md"
            paper_path.write_text("# Paper", encoding="utf-8")
            asyncio.run(ensemble.review_paper(paper_path, paper_text="text", use_batch=False))

        ensemble._review_paper_batch.assert_not_called()

    def test_use_batch_true_falls_back_when_batch_returns_none(self) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = MagicMock(content=_VALID_REVIEW_JSON)
        ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)

        async def _fake_batch(paper_text):
            return None

        ensemble._review_paper_batch = _fake_batch

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            paper_path = Path(tmp) / "paper.md"
            paper_path.write_text("# Paper", encoding="utf-8")
            reviews = asyncio.run(
                ensemble.review_paper(paper_path, paper_text="text", use_batch=True)
            )

        assert len(reviews) == len(REVIEWER_PERSONAS)
        assert mock_llm.chat.call_count == len(REVIEWER_PERSONAS)
