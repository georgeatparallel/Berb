"""Synthetic seeded-defect corpus (tasks/ars_integration_plan.md W7).

Measures recall of Berb's own integrity checks and, for the LLM tier, the
reviewer ensemble (``berb/review/ensemble.py``) against paper drafts with
known, deliberately injected defects. Every fixture here is invented —
no real unpublished manuscript, real author name, or real institutional
data enters this file. ``"he2016deep"``/``"smith2020"``-style cite keys
are the same placeholder convention already used across this test suite
(e.g. ``tests/test_integrity.py``), not real bibliographic lookups.

Design note, corrected from the plan's original sketch: the plan pointed
at wiring this corpus into ``berb/integrity/eval/hidden_eval.py``'s
"test tier" (Hidden Consistent Evaluation, AIRA2-style). Reading that
module's actual implementation shows it scores a *single* paper's overall
quality across three visibility-tiered LLM dimensions for the pipeline's
own search/selection optimization loop — an unrelated mechanism, and
partly a stub itself (``claim_validity``/``citation_correctness`` are
hardcoded ``0.5``, pending a "TODO(E8)" integration that never landed).
It has nothing to do with measuring ``berb/review/ensemble.py``'s
5-persona recall on seeded defects, which is what this problem statement
asks for (same class of mistake as the ``ExtendedRouter`` finding
documented for W5 — a plan section written without reading the target
module's internals closely enough). This corpus instead exercises
Berb's own existing deterministic checks directly (``verify_anchors``,
``detect_uncited``) for the no-LLM tier, and the real reviewer ensemble
for the LLM tier.

Two tiers, per the plan's Method spec:

- Deterministic tier: defects catchable by an existing, already-shipped
  Berb check with no LLM call. Covers ``FABRICATED_CITATION`` (via
  ``berb.integrity.anchors.verify_anchors``, ``ANCHOR_QUOTE_MISMATCH`` /
  ``BLOCK``) and ``UNCITED_EMPIRICAL_CLAIM`` (via
  ``berb.integrity.uncited.detect_uncited``, ``UNCITED_ASSERTION`` /
  ``WARN``). Each defect fixture is paired with a matching clean control
  fixture so the same test run also checks for false positives, not just
  recall.
- LLM tier: defects that need judgment (``UNSUPPORTED_COMPARATIVE_CLAIM``
  here). Reports recall per persona rather than asserting pass/fail — an
  LLM's judgment is not deterministic and should not gate CI, per the
  plan's explicit design note.

The plan's original Method spec also names "a number that contradicts
the results table," "a dropped ablation," and "a p-value with no test
behind it." None of the three has an existing deterministic checker in
this codebase, and building one for each was out of scope for this pass
— left as a named, open gap (see tasks/ars_integration_plan.md's W7
progress-log entry) rather than forced in under time pressure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from berb.integrity.anchors import Anchor, make_anchor


class DefectType(StrEnum):
    FABRICATED_CITATION = "fabricated_citation"
    UNCITED_EMPIRICAL_CLAIM = "uncited_empirical_claim"
    UNSUPPORTED_COMPARATIVE_CLAIM = "unsupported_comparative_claim"


@dataclass(frozen=True)
class AnchorFixture:
    """Deterministic-tier fixture for ``verify_anchors``: one ``berb-cite``
    marker, the anchor it resolves to, the bibliography keys it is
    checked against, and the (possibly doctored) stored source text for
    that key."""

    id: str
    defect_type: DefectType
    draft_text: str
    anchor: Anchor
    bib_keys: frozenset[str]
    source_texts: dict[str, str]
    is_defective: bool
    """True: this fixture should be flagged. False: a clean control used
    to check for false positives on the same defect type."""


@dataclass(frozen=True)
class SentenceFixture:
    """Deterministic-tier fixture for ``detect_uncited`` — shaped to
    match ``SentenceRef``'s ``(text, adjacent_text)`` pair."""

    id: str
    defect_type: DefectType
    sentence: str
    adjacent_text: str
    is_defective: bool


@dataclass(frozen=True)
class LLMTierFixture:
    """LLM-tier fixture: a short synthetic paper run through the real
    reviewer ensemble. ``defect_keywords`` is a reporting heuristic for
    recall (did any persona's feedback mention one of these), not a
    precise oracle — LLM wording varies."""

    id: str
    defect_type: DefectType
    paper_text: str
    defect_keywords: tuple[str, ...]


def _quote_anchor_fixture(
    *,
    fixture_id: str,
    cite_key: str,
    quoted_value: str,
    stored_source: str,
    is_defective: bool,
) -> AnchorFixture:
    anchor = make_anchor(cite_key, "quote", quoted_value)
    if anchor is None:  # pragma: no cover - fixture-authoring bug, not runtime data
        raise ValueError(f"invalid seeded-defect fixture {fixture_id!r}: bad anchor inputs")
    draft = (
        "Prior work established this result "
        f"<!--berb-cite key={cite_key} kind=quote id={anchor.anchor_id}-->.\n"
    )
    return AnchorFixture(
        id=fixture_id,
        defect_type=DefectType.FABRICATED_CITATION,
        draft_text=draft,
        anchor=anchor,
        bib_keys=frozenset({cite_key}),
        source_texts={cite_key: stored_source},
        is_defective=is_defective,
    )


ANCHOR_FIXTURES: tuple[AnchorFixture, ...] = (
    _quote_anchor_fixture(
        fixture_id="fabricated-quote-01",
        cite_key="he2016deep",
        quoted_value="widgets self-assemble without external energy input",
        stored_source=(
            "This synthetic reference discusses convolutional layers "
            "for image classification and says nothing about "
            "self-assembling widgets."
        ),
        is_defective=True,
    ),
    _quote_anchor_fixture(
        fixture_id="genuine-quote-01",
        cite_key="he2016deep",
        quoted_value="residual connections ease the training of deeper models",
        stored_source=(
            "This synthetic reference proposes residual connections. "
            "Residual connections ease the training of deeper models "
            "than plain stacked layers."
        ),
        is_defective=False,
    ),
)


SENTENCE_FIXTURES: tuple[SentenceFixture, ...] = (
    SentenceFixture(
        id="uncited-comparative-01",
        defect_type=DefectType.UNCITED_EMPIRICAL_CLAIM,
        sentence="Our method improves accuracy by 15% over the baseline.",
        adjacent_text="",
        is_defective=True,
    ),
    SentenceFixture(
        id="cited-comparative-01",
        defect_type=DefectType.UNCITED_EMPIRICAL_CLAIM,
        sentence="Our method improves accuracy by 15% over the baseline \\cite{smith2020}.",
        adjacent_text="",
        is_defective=False,
    ),
)


LLM_TIER_FIXTURES: tuple[LLMTierFixture, ...] = (
    LLMTierFixture(
        id="unsupported-comparative-claim-01",
        defect_type=DefectType.UNSUPPORTED_COMPARATIVE_CLAIM,
        paper_text=(
            "# A Study of Synthetic Widget Classification\n\n"
            "## Abstract\n"
            "We propose WidgetNet, a synthetic neural architecture for "
            "widget classification, evaluated on an invented benchmark.\n\n"
            "## Method\n"
            "WidgetNet stacks three convolutional layers followed by a "
            "linear classifier.\n\n"
            "## Results\n"
            "WidgetNet dramatically outperforms every prior method on "
            "every benchmark, achieving perfect accuracy in all cases. "
            "No comparison table, baseline numbers, or ablation is "
            "provided, and no prior method is named or cited.\n\n"
            "## Conclusion\n"
            "WidgetNet is the best possible solution to widget "
            "classification.\n"
        ),
        defect_keywords=(
            "ablation",
            "comparison",
            "baseline",
            "prior method",
            "evidence",
            "unsupported",
            "no comparison",
            "citation",
            "table",
        ),
    ),
)
