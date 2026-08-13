"""A1-1 (tasks/hardening_plan_2026-08-13.md): the review fan-out must be
genuinely concurrent.

`_generate_review` was `async def` but called `self._llm_client.chat(...)`
synchronously — no `await`, no `to_thread` — so `asyncio.gather()` over the
persona list provided zero real parallelism; N personas ran back-to-back.
This is the wall-clock regression test the fix didn't originally ship with.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

from berb.review.ensemble import REVIEWER_PERSONAS, AutomatedReviewerEnsemble

_SLEEP_SEC = 0.1


def _slow_chat(**kwargs):
    time.sleep(_SLEEP_SEC)
    return MagicMock(content="not valid json, falls back to parse-failure path")


def test_two_persona_fan_out_runs_concurrently_not_serially() -> None:
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = _slow_chat

    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)
    ensemble._personas = REVIEWER_PERSONAS[:2]

    start = time.monotonic()
    asyncio.run(ensemble.review_paper(paper_path="fake.pdf", paper_text="some paper text"))
    elapsed = time.monotonic() - start

    # Serial would take >= 2 * _SLEEP_SEC (0.2s). Concurrent should land
    # close to one _SLEEP_SEC plus overhead — generous margin for CI jitter.
    assert elapsed < _SLEEP_SEC * 1.5, (
        f"fan-out took {elapsed:.3f}s for 2 personas each sleeping {_SLEEP_SEC}s — "
        f"looks serial, not concurrent"
    )
    assert mock_llm.chat.call_count == 2


def test_synthesize_critiques_does_not_block_event_loop() -> None:
    """Same blocking-in-async defect, single-call site — proves the review
    task and this call can genuinely run concurrently with something else."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = _slow_chat
    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)

    async def _run_alongside():
        marker = {"ticked": False}

        async def _ticker():
            await asyncio.sleep(_SLEEP_SEC / 2)
            marker["ticked"] = True

        results = await asyncio.gather(
            ensemble.synthesize_critiques([]),
            _ticker(),
        )
        return results, marker["ticked"]

    (_, ticked_) = asyncio.run(_run_alongside())
    assert ticked_ is True
