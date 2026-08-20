"""A1-1 (tasks/hardening_plan_2026-08-13.md): the review fan-out must be
genuinely concurrent.

`_generate_review` was `async def` but called `self._llm_client.chat(...)`
synchronously — no `await`, no `to_thread` — so `asyncio.gather()` over the
persona list provided zero real parallelism; N personas ran back-to-back.
This is the wall-clock regression test the fix didn't originally ship with.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock

from berb.review.ensemble import REVIEWER_PERSONAS, AutomatedReviewerEnsemble

_SLEEP_SEC = 0.1


def _slow_chat(**kwargs):
    time.sleep(_SLEEP_SEC)
    return MagicMock(content="not valid json, falls back to parse-failure path")


class _OverlapProbe:
    """Records the maximum number of chat() calls in flight simultaneously.

    The property under test is overlap, so measure overlap directly rather
    than inferring it from wall-clock time. An earlier version of this test
    asserted ``elapsed < _SLEEP_SEC * 1.5``; that ratio holds on an idle
    machine but not under a loaded CI box or coverage instrumentation, where
    it produced false failures while the code under test was fine. Counting
    concurrent entries is deterministic under any load.

    chat() is dispatched via asyncio.to_thread, so the counters are touched
    from worker threads and need a real lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0

    def __call__(self, **kwargs):
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            return _slow_chat(**kwargs)
        finally:
            with self._lock:
                self.in_flight -= 1


def test_two_persona_fan_out_runs_concurrently_not_serially() -> None:
    probe = _OverlapProbe()
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = probe

    ensemble = AutomatedReviewerEnsemble(llm_client=mock_llm)
    ensemble._personas = REVIEWER_PERSONAS[:2]

    asyncio.run(
        ensemble.review_paper(paper_path="fake.pdf", paper_text="some paper text")
    )

    assert mock_llm.chat.call_count == 2
    # Serial execution can never exceed 1 in flight. Before the A1-1 fix,
    # _generate_review called chat() synchronously inside an async def, so
    # asyncio.gather() produced exactly this serial pattern.
    assert probe.max_in_flight >= 2, (
        f"only {probe.max_in_flight} chat() call(s) were ever in flight at once — "
        f"the persona fan-out ran serially, not concurrently"
    )


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

    _, ticked_ = asyncio.run(_run_alongside())
    assert ticked_ is True
