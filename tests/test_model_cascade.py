"""Tests for berb.llm.model_cascade and the client seam it wraps.

The cascade wraps whatever create_llm_client built and delegates through
``chat``. Two things are covered here: the cascade's own escalate/accept logic,
and the SmartLLMClient seam it plugs into — which had no ``chat`` at all, so a
cascade could not have wrapped it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from berb.llm.model_cascade import (
    CascadeConfig,
    CascadeStep,
    CascadingLLMClient,
    get_cascade_for_stage,
)


class _Response:
    def __init__(self, content: str, model: str = "m") -> None:
        self.content = content
        self.model = model


class _RecordingClient:
    """Returns a canned response per model, and records what it was asked for."""

    def __init__(self, by_model: dict[str, Any]) -> None:
        self._by_model = by_model
        self.models: list[str] = []
        self.config = object()

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        model = kwargs["model"]
        self.models.append(model)
        result = self._by_model[model]
        if isinstance(result, Exception):
            raise result
        return result


_GOOD = "This is a complete and adequately long answer to the question asked."
_REFUSAL = "I cannot help with that."


def _two_step(**kw: Any) -> CascadeConfig:
    return CascadeConfig(
        cascade=(
            CascadeStep("cheap", min_score=0.8),
            CascadeStep("premium", min_score=0.0),
        ),
        **kw,
    )


# ---------------------------------------------------------------------------
# Accept / escalate
# ---------------------------------------------------------------------------


def test_accepts_the_cheap_model_when_it_scores_well() -> None:
    client = _RecordingClient({"cheap": _Response(_GOOD), "premium": _Response(_GOOD)})
    cascade = CascadingLLMClient(client, _two_step())

    resp = cascade.chat([{"role": "user", "content": "a short question?"}])

    assert resp.content == _GOOD
    assert client.models == ["cheap"]  # never paid for premium


def test_escalates_when_the_cheap_model_refuses() -> None:
    client = _RecordingClient({"cheap": _Response(_REFUSAL), "premium": _Response(_GOOD)})
    cascade = CascadingLLMClient(client, _two_step())

    resp = cascade.chat([{"role": "user", "content": "a short question?"}])

    assert resp.content == _GOOD
    assert client.models == ["cheap", "premium"]


def test_escalates_past_a_failing_rung() -> None:
    client = _RecordingClient(
        {"cheap": RuntimeError("502"), "premium": _Response(_GOOD)},
    )
    cascade = CascadingLLMClient(client, _two_step())

    assert cascade.chat([{"role": "user", "content": "q?"}]).content == _GOOD
    assert client.models == ["cheap", "premium"]


def test_returns_the_last_response_when_nothing_clears_its_bar() -> None:
    """A last rung with a non-zero threshold still yields its answer, not an error."""
    client = _RecordingClient({"cheap": _Response(_REFUSAL), "premium": _Response(_REFUSAL)})
    cascade = CascadingLLMClient(
        client,
        CascadeConfig(
            cascade=(
                CascadeStep("cheap", min_score=0.8),
                CascadeStep("premium", min_score=0.8),
            )
        ),
    )
    assert cascade.chat([{"role": "user", "content": "q?"}]).content == _REFUSAL


def test_uses_the_fallback_model_when_every_rung_raises() -> None:
    client = _RecordingClient(
        {
            "cheap": RuntimeError("502"),
            "premium": RuntimeError("503"),
            "backstop": _Response(_GOOD),
        }
    )
    cascade = CascadingLLMClient(client, _two_step(fallback_model="backstop"))

    assert cascade.chat([{"role": "user", "content": "q?"}]).content == _GOOD
    assert client.models == ["cheap", "premium", "backstop"]


def test_raises_when_every_rung_raises_and_no_fallback() -> None:
    client = _RecordingClient({"cheap": RuntimeError("502"), "premium": RuntimeError("503")})
    cascade = CascadingLLMClient(client, _two_step())

    with pytest.raises(RuntimeError, match="All cascade steps failed"):
        cascade.chat([{"role": "user", "content": "q?"}])


def test_raises_when_the_fallback_also_fails() -> None:
    client = _RecordingClient(
        {
            "cheap": RuntimeError("502"),
            "premium": RuntimeError("503"),
            "backstop": RuntimeError("504"),
        }
    )
    cascade = CascadingLLMClient(client, _two_step(fallback_model="backstop"))

    with pytest.raises(RuntimeError, match="fallback model"):
        cascade.chat([{"role": "user", "content": "q?"}])


def test_disabling_evaluation_accepts_the_first_rung_unconditionally() -> None:
    client = _RecordingClient({"cheap": _Response(_REFUSAL), "premium": _Response(_GOOD)})
    cascade = CascadingLLMClient(client, _two_step(quick_eval_enabled=False))

    assert cascade.chat([{"role": "user", "content": "q?"}]).content == _REFUSAL
    assert client.models == ["cheap"]


def test_an_empty_cascade_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="empty"):
        CascadingLLMClient(_RecordingClient({}), CascadeConfig())


def test_a_caller_supplied_model_does_not_defeat_the_cascade() -> None:
    client = _RecordingClient({"cheap": _Response(_GOOD)})
    cascade = CascadingLLMClient(client, _two_step())

    cascade.chat([{"role": "user", "content": "q?"}], model="something-else")

    assert client.models == ["cheap"]


def test_per_step_parameters_reach_the_client() -> None:
    seen: dict[str, Any] = {}

    class _C:
        config = object()

        def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
            seen.update(kwargs)
            return _Response(_GOOD)

    cascade = CascadingLLMClient(
        _C(),
        CascadeConfig(
            cascade=(CascadeStep("cheap", min_score=0.0, max_tokens=42, temperature=0.1),)
        ),
    )
    cascade.chat([{"role": "user", "content": "q?"}])
    assert seen["max_tokens"] == 42
    assert seen["temperature"] == pytest.approx(0.1)


def test_config_reaches_through_to_the_wrapped_client() -> None:
    client = _RecordingClient({"cheap": _Response(_GOOD)})
    cascade = CascadingLLMClient(client, _two_step())
    assert cascade.config is client.config


# ---------------------------------------------------------------------------
# Stats — the measurement that tells you whether the cascade is worth it
# ---------------------------------------------------------------------------


def test_stats_record_the_exit_distribution() -> None:
    client = _RecordingClient({"cheap": _Response(_GOOD), "premium": _Response(_GOOD)})
    cascade = CascadingLLMClient(client, _two_step())
    for _ in range(3):
        cascade.chat([{"role": "user", "content": "q?"}])

    stats = cascade.get_stats()
    assert stats["total_requests"] == 3
    assert stats["cascade_exits"] == {0: 3}
    assert stats["average_exit_step"] == pytest.approx(0.0)


def test_stats_average_reflects_escalation() -> None:
    client = _RecordingClient({"cheap": _Response(_REFUSAL), "premium": _Response(_GOOD)})
    cascade = CascadingLLMClient(client, _two_step())
    cascade.chat([{"role": "user", "content": "q?"}])

    assert cascade.get_stats()["cascade_exits"] == {1: 1}
    assert cascade.get_stats()["average_exit_step"] == pytest.approx(1.0)


def test_stats_are_empty_before_any_call() -> None:
    cascade = CascadingLLMClient(_RecordingClient({}), _two_step())
    assert cascade.get_stats() == {
        "total_requests": 0,
        "cascade_exits": {},
        "average_exit_step": 0.0,
    }


# ---------------------------------------------------------------------------
# The default evaluator
# ---------------------------------------------------------------------------


def _score(content: str, messages: list[dict[str, Any]] | None = None) -> float:
    cascade = CascadingLLMClient(_RecordingClient({}), _two_step())
    return cascade._default_evaluator(_Response(content), messages or [])


def test_evaluator_scores_empty_content_zero() -> None:
    assert _score("") == 0.0


def test_evaluator_scores_a_hard_refusal_near_zero() -> None:
    assert _score("I cannot do that.") == pytest.approx(0.05)


def test_evaluator_penalises_truncation() -> None:
    assert _score("A complete sentence ends here.") > _score("A sentence that just stops mid")


def test_evaluator_rewards_valid_json_when_json_was_requested() -> None:
    msgs = [{"role": "user", "content": "Reply in JSON."}]
    assert _score(json.dumps({"a": 1}), msgs) > _score("Not json at all.", msgs)


def test_evaluator_penalises_malformed_json_when_json_was_requested() -> None:
    msgs = [{"role": "user", "content": "Reply in JSON."}]
    assert _score('{"a": ', msgs) < _score(json.dumps({"a": 1}), msgs)


def test_evaluator_handles_multimodal_prompt_content() -> None:
    """Prompt length used len(content); a part list would raise TypeError."""
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe this"},
                {"type": "image", "media_type": "image/png", "data": "AAAA"},
            ],
        }
    ]
    assert 0.0 <= _score(_GOOD, msgs) <= 1.0


# ---------------------------------------------------------------------------
# Stage recommendations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stage",
    ["TOPIC_INIT", "HYPOTHESIS_GEN", "PAPER_DRAFT", "PEER_REVIEW", "SOMETHING_ELSE"],
)
def test_every_stage_recommendation_ends_with_an_always_accept_rung(stage: str) -> None:
    cascade = get_cascade_for_stage(stage).cascade
    assert cascade
    assert cascade[-1].min_score == 0.0


def test_stage_lookup_is_case_insensitive() -> None:
    assert get_cascade_for_stage("peer_review") == get_cascade_for_stage("PEER_REVIEW")


def test_critical_stages_do_not_cascade() -> None:
    assert len(get_cascade_for_stage("PEER_REVIEW").cascade) == 1
