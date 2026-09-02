"""Seeded-defect evaluation, deterministic and LLM tiers (tasks/ars_integration_plan.md W7).

See tests/fixtures/seeded_defects.py's module docstring for the corrected
design (the plan's original pointer at berb.integrity.eval.hidden_eval was
based on a mistaken premise about what that module does).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from berb.integrity.anchors import verify_anchors
from berb.integrity.findings import CheckId, Severity
from berb.integrity.uncited import SentenceRef, detect_uncited
from tests.fixtures.seeded_defects import (
    ANCHOR_FIXTURES,
    LLM_TIER_FIXTURES,
    SENTENCE_FIXTURES,
)

# ---------------------------------------------------------------------------
# Deterministic tier — no LLM, no marker, runs in normal CI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", ANCHOR_FIXTURES, ids=lambda f: f.id)
def test_anchor_fixture_recall(fixture) -> None:  # noqa: ANN001
    findings = verify_anchors(
        {fixture.anchor.anchor_id: fixture.anchor},
        fixture.bib_keys,
        fixture.draft_text,
        fixture.source_texts,
    )
    quote_mismatches = [f for f in findings if f.check == CheckId.ANCHOR_QUOTE_MISMATCH]
    if fixture.is_defective:
        assert len(quote_mismatches) == 1, f"{fixture.id}: fabricated quote not caught"
        assert quote_mismatches[0].severity is Severity.BLOCK
    else:
        assert quote_mismatches == [], f"{fixture.id}: false positive on a genuine quote"


@pytest.mark.parametrize("fixture", SENTENCE_FIXTURES, ids=lambda f: f.id)
def test_sentence_fixture_recall(fixture) -> None:  # noqa: ANN001
    ref = SentenceRef(
        index=0,
        text=fixture.sentence,
        adjacent_text=fixture.adjacent_text,
        locator=fixture.id,
    )
    findings = detect_uncited((ref,))
    if fixture.is_defective:
        assert len(findings) == 1, f"{fixture.id}: uncited claim not caught"
        assert findings[0].check == CheckId.UNCITED_ASSERTION
    else:
        assert findings == (), f"{fixture.id}: false positive on a cited claim"


# ---------------------------------------------------------------------------
# LLM tier — real reviewer ensemble, requires a live API key
# ---------------------------------------------------------------------------


@pytest.mark.llm
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
async def test_llm_tier_recall_on_seeded_defect(tmp_path: Path) -> None:
    """Not a pass/fail oracle — LLM judgment is not deterministic. Runs
    the real 5-persona ensemble against one seeded defect and reports
    per-persona recall; a recall number that moves over time is the
    signal (tasks/ars_integration_plan.md W7's explicit design note).
    Skipped without a live Anthropic key, same pattern as every other
    ``@pytest.mark.llm`` test in this suite (see
    tests/test_minimax_provider.py).
    """
    from berb.config import RCConfig
    from berb.llm.client import LLMClient
    from berb.review.ensemble import AutomatedReviewerEnsemble

    data = {
        "project": {"name": "w7-eval", "mode": "docs-first"},
        "research": {
            "topic": "seeded-defect eval",
            "domains": ["ml"],
            "quality_threshold": 8.0,
        },
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "local"},
        "openclaw_bridge": {"use_memory": True, "use_message": True},
        "security": {"hitl_required_stages": [5, 9, 20]},
        "experiment": {"mode": "sandbox"},
        "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
        "llm": {
            "provider": "anthropic",
            "api_key_env": "ANTHROPIC_API_KEY",
            "primary_model": "claude-haiku-4-5-20251001",
        },
    }
    rc_config = RCConfig.from_dict(
        data, project_root=tmp_path, check_paths=False, check_security=False
    )
    llm_client = LLMClient.from_rc_config(rc_config)
    ensemble = AutomatedReviewerEnsemble(llm_client=llm_client)

    fixture = LLM_TIER_FIXTURES[0]
    reviews = await ensemble.review_paper(
        Path("synthetic_widgetnet.md"), paper_text=fixture.paper_text
    )

    assert len(reviews) == 5

    recall_count = 0
    for review in reviews:
        haystack = " ".join(
            [*review.weaknesses, *review.questions_for_authors, review.detailed_feedback]
        ).lower()
        if any(keyword in haystack for keyword in fixture.defect_keywords):
            recall_count += 1

    print(f"W7 LLM-tier recall for {fixture.id}: {recall_count}/{len(reviews)} personas")
