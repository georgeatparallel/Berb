"""Tests for the DAG resolution module — topological order and eligibility."""

from __future__ import annotations

from berb.pipeline.resolution import (
    eligible_stages,
    resolve_stage_order,
    verify_acyclic,
)
from berb.pipeline.stages import Stage


def test_resolve_stage_order_returns_all_stages() -> None:
    """resolve_stage_order returns all 23 stages in valid topological order."""
    order = resolve_stage_order()
    assert len(order) == 23
    # Verify TOPIC_INIT is first (no dependencies)
    assert order[0] == Stage.TOPIC_INIT
    # Verify CITATION_VERIFY is last (depends on EXPORT_PUBLISH)
    assert order[-1] == Stage.CITATION_VERIFY


def test_resolve_stage_order_from_mid_pipeline() -> None:
    """Resolving from PAPER_OUTLINE returns only stages from that point onward."""
    order = resolve_stage_order(Stage.PAPER_OUTLINE)
    assert len(order) == 8  # 23 - 15 = 8 remaining
    assert order[0] == Stage.PAPER_OUTLINE
    # All stages should be >= PAPER_OUTLINE
    for s in order:
        assert int(s) >= 16, f"{s.name} has value {int(s)}, expected >= 16"


def test_topic_init_has_no_dependencies() -> None:
    """TOPIC_INIT is the root stage — no dependencies."""
    from berb.pipeline.contracts import CONTRACTS

    assert CONTRACTS[Stage.TOPIC_INIT].depends_on == frozenset()


def test_experiment_run_depends_on_both_code_and_resources() -> None:
    """EXPERIMENT_RUN requires both CODE_GENERATION and RESOURCE_PLANNING."""
    from berb.pipeline.contracts import CONTRACTS

    deps = CONTRACTS[Stage.EXPERIMENT_RUN].depends_on
    assert Stage.CODE_GENERATION in deps
    assert Stage.RESOURCE_PLANNING in deps


def test_eligible_stages_returns_correct_subset() -> None:
    """eligible_stages returns only stages whose dependencies are satisfied."""
    queue = {Stage.SEARCH_STRATEGY, Stage.TOPIC_INIT}

    # Only TOPIC_INIT has no deps, SEARCH_STRATEGY depends on PROBLEM_DECOMPOSE
    eligible = eligible_stages(set(), queue)
    assert eligible == {Stage.TOPIC_INIT}
    assert Stage.SEARCH_STRATEGY not in eligible


def test_eligible_stages_concurrent_opportunity() -> None:
    """CODE_GENERATION and RESOURCE_PLANNING are eligible after EXPERIMENT_DESIGN."""
    completed = {
        Stage.TOPIC_INIT,
        Stage.PROBLEM_DECOMPOSE,
        Stage.SEARCH_STRATEGY,
        Stage.LITERATURE_COLLECT,
        Stage.LITERATURE_SCREEN,
        Stage.KNOWLEDGE_EXTRACT,
        Stage.SYNTHESIS,
        Stage.HYPOTHESIS_GEN,
        Stage.EXPERIMENT_DESIGN,
    }
    queue = {Stage.CODE_GENERATION, Stage.RESOURCE_PLANNING}
    eligible = eligible_stages(completed, queue)
    assert eligible == {Stage.CODE_GENERATION, Stage.RESOURCE_PLANNING}


def test_eligible_stages_empty_queue() -> None:
    """eligible_stages with an empty queue returns empty set."""
    assert eligible_stages({Stage.TOPIC_INIT}, set()) == set()


def test_verify_acyclic_returns_true() -> None:
    """The current dependency graph has no cycles."""
    assert verify_acyclic() is True
