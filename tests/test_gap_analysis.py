"""Regression test for berb/research/gap_analysis.py (audit §4.2).

ResearchGapAnalyzer._run_perspective() referenced PerspectiveResult without
it ever being defined anywhere in the codebase, raising NameError on every
call. This module has no other test coverage today (it is currently
unreachable from any entry point — see docs/DEAD_CODE_ANALYSIS.md); this
test exists solely to prove the NameError is fixed.
"""

from __future__ import annotations

import pytest

from berb.reasoning.multi_perspective import PerspectiveType
from berb.research.gap_analysis import (
    GapAnalysisConfig,
    PerspectiveResult,
    ResearchGapAnalyzer,
)


class _FakeReasoningResult:
    def __init__(self, output: dict) -> None:
        self.output = output


class _FakeMultiPerspectiveMethod:
    async def execute(self, context: object) -> _FakeReasoningResult:
        return _FakeReasoningResult(
            {"content": "1. Gap in method coverage.", "reasoning": "Because X."}
        )


@pytest.mark.asyncio
async def test_run_perspective_returns_perspective_result() -> None:
    analyzer = ResearchGapAnalyzer(config=GapAnalysisConfig(use_multi_perspective=False))
    # Bypass real LLM construction — swap in a stub that mimics the
    # MultiPerspectiveMethod.execute() contract _run_perspective() relies on.
    analyzer.multi_perspective_method = _FakeMultiPerspectiveMethod()

    result = await analyzer._run_perspective("test problem", "novelty_seeker")

    assert isinstance(result, PerspectiveResult)
    assert result.perspective_type == PerspectiveType.CONSTRUCTIVE
    assert "Gap in method coverage" in result.content
    assert result.reasoning == "Because X."
    assert result.confidence == 0.7


@pytest.mark.asyncio
async def test_extract_gaps_from_perspective_consumes_perspective_result() -> None:
    from berb.research.gap_analysis import GapType

    analyzer = ResearchGapAnalyzer(config=GapAnalysisConfig(use_multi_perspective=False))
    perspective_result = PerspectiveResult(
        perspective_type=PerspectiveType.CONSTRUCTIVE,
        content="1. Gap: no cross-lingual evaluation exists.",
        reasoning="",
        confidence=0.7,
    )

    gaps = analyzer._extract_gaps_from_perspective(
        perspective_result,
        "novelty_seeker",
        [GapType.LITERATURE, GapType.THEORETICAL],
        "nlp",
    )

    assert isinstance(gaps, list)
