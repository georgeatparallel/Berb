"""Tests for experiment search subsystems (E1, E2, F2, E3, E10)."""

from __future__ import annotations

import asyncio

from berb.experiment.journal import ExperimentJournal, JournalNode
from berb.experiment.plot_verdict import verify_plots
from berb.experiment.search.policy import (
    BestFirstDiversePolicy,
    SearchConfig,
    _debug_depth,
)
from berb.experiment.search.scoring import score_node
from berb.llm.cost_tracker import CostTracker

# ---------------------------------------------------------------------------
# ExperimentJournal Topology & Serialization Tests (E1)
# ---------------------------------------------------------------------------


def test_journal_topology() -> None:
    journal = ExperimentJournal()

    # Root node
    root = JournalNode(
        node_id="root-1",
        parent_id=None,
        depth=1,
        phase="baseline",
        origin="draft",
        returncode=0,  # successful execution
        metrics={"accuracy": 0.8},
    )
    journal.append(root)

    # Child of root-1
    child_1 = JournalNode(
        node_id="child-1",
        parent_id="root-1",
        depth=2,
        phase="tuning",
        origin="debug",
        returncode=0,
        metrics={"accuracy": 0.85},
    )
    journal.append(child_1)

    # Another root
    root_2 = JournalNode(
        node_id="root-2",
        parent_id=None,
        depth=1,
        phase="baseline",
        origin="draft",
        returncode=1,  # crashed
    )
    journal.append(root_2)

    # Roots check
    roots = journal.roots()
    assert len(roots) == 2
    assert {r.node_id for r in roots} == {"root-1", "root-2"}

    # Leaves check
    leaves = journal.leaves()
    assert len(leaves) == 2
    assert {l.node_id for l in leaves} == {"child-1", "root-2"}

    # Children check
    children = journal.children_of("root-1")
    assert len(children) == 1
    assert children[0].node_id == "child-1"

    # Single lookup
    node = journal.get_node("child-1")
    assert node is not None
    assert node.phase == "tuning"


def test_journal_serialization() -> None:
    journal = ExperimentJournal()
    node = JournalNode(
        node_id="n-1",
        parent_id=None,
        depth=1,
        phase="baseline",
        origin="draft",
        returncode=0,
        metrics={"metric": 0.99},
        is_buggy=False,
        is_buggy_plots=False,
        cost_usd=0.015,
    )
    journal.append(node)

    # Convert to JSON and back
    json_text = journal.to_json()
    reconstructed = ExperimentJournal.from_json(json_text)

    assert reconstructed.node_count() == 1
    rec_node = reconstructed.get_node("n-1")
    assert rec_node is not None
    assert rec_node.metrics == {"metric": 0.99}
    assert rec_node.is_buggy is False
    assert rec_node.is_buggy_plots is False
    assert rec_node.cost_usd == 0.015


# ---------------------------------------------------------------------------
# Grounded Metric Scoring Tests (F2)
# ---------------------------------------------------------------------------


def test_score_node_maximize() -> None:
    node = JournalNode(
        node_id="node-1",
        returncode=0,
        metrics={"loss": 0.1, "accuracy": 0.85},
    )

    # Absolute metric (neutral default when no cohort/baseline)
    breakdown = score_node(node, "accuracy", maximize=True)
    assert breakdown.runs_ok is True
    assert breakdown.buggy_plots is None
    # No cohort/baseline -> normalized defaults to 0.5 -> score = 0.5 * 5.0 + 0.5 completeness bonus = 3.0
    assert breakdown.total == 3.0

    # With cohort min-max normalization
    cohort = [
        node,
        JournalNode(node_id="node-2", returncode=0, metrics={"accuracy": 0.7}),
        JournalNode(node_id="node-3", returncode=0, metrics={"accuracy": 0.9}),
    ]
    breakdown_norm = score_node(node, "accuracy", cohort=cohort, maximize=True)
    # accuracy=0.85 normalized between 0.7 and 0.9: (0.85 - 0.7) / (0.9 - 0.7) = 0.15 / 0.20 = 0.75
    # total score: 0.75 * 5.0 + 0.5 (completeness bonus for >=2 metrics) = 4.25
    assert abs(breakdown_norm.total - 4.25) < 1e-5


def test_score_node_minimize() -> None:
    node = JournalNode(
        node_id="node-1",
        returncode=0,
        metrics={"loss": 0.2, "accuracy": 0.8},
    )
    cohort = [
        node,
        JournalNode(node_id="node-2", returncode=0, metrics={"loss": 0.1}),
        JournalNode(node_id="node-3", returncode=0, metrics={"loss": 0.5}),
    ]
    breakdown_norm = score_node(node, "loss", cohort=cohort, maximize=False)
    # loss=0.2 normalized minimize between 0.1 and 0.5: (0.5 - 0.2) / (0.5 - 0.1) = 0.3 / 0.4 = 0.75
    # total score: 0.75 * 5.0 + 0.5 bonus = 4.25
    assert abs(breakdown_norm.total - 4.25) < 1e-5


def test_score_node_hard_gates() -> None:
    # Gate 1: Crashed
    crashed_node = JournalNode(node_id="crashed", returncode=1)
    assert score_node(crashed_node, "accuracy").total == 0.0

    # Gate 2: Buggy plots
    buggy_plots_node = JournalNode(node_id="buggy-plots", returncode=0, is_buggy_plots=True)
    assert score_node(buggy_plots_node, "accuracy").total == 0.0


# ---------------------------------------------------------------------------
# Search Policy & Debug Depth Tests (E2)
# ---------------------------------------------------------------------------


def test_debug_depth_calculation() -> None:
    journal = ExperimentJournal()

    # Root node
    n0 = JournalNode(node_id="n0", parent_id=None, origin="draft")
    journal.append(n0)

    # Repair cycle 1
    n1 = JournalNode(node_id="n1", parent_id="n0", origin="debug")
    journal.append(n1)

    # Normal edit cycle
    n2 = JournalNode(node_id="n2", parent_id="n1", origin="improve")
    journal.append(n2)

    # Repair cycle 2
    n3 = JournalNode(node_id="n3", parent_id="n2", origin="debug")
    journal.append(n3)

    assert _debug_depth(n0, journal) == 0
    assert _debug_depth(n1, journal) == 1
    assert _debug_depth(n2, journal) == 1
    assert _debug_depth(n3, journal) == 2


def test_best_first_diverse_policy() -> None:
    policy = BestFirstDiversePolicy(seed=42)
    journal = ExperimentJournal()
    config = SearchConfig(num_roots=2, debug_probability=1.0, max_debug_depth=2)

    # 1. Bootstrap: empty journal -> returns [None] to create a new root
    assert policy.select(journal, 1, config) == [None]

    # Add first root
    r1 = JournalNode(node_id="r1", parent_id=None, returncode=0)
    journal.append(r1)

    # Bootstrap: 1 root < num_roots=2 -> returns [None] to create second root
    assert policy.select(journal, 1, config) == [None]

    # Add second root
    r2 = JournalNode(
        node_id="r2", parent_id=None, returncode=1, is_buggy=True
    )  # buggy root (exit status 1)
    journal.append(r2)

    # 2. Repair: debug_probability=1.0 -> chooses buggy root r2
    selected = policy.select(journal, 1, config)
    assert len(selected) == 1
    assert selected[0] is not None
    assert selected[0].node_id == "r2"


# ---------------------------------------------------------------------------
# CostTracker thread-safe price accumulation (E10)
# ---------------------------------------------------------------------------


def test_cost_tracker_accumulation() -> None:
    tracker = CostTracker()
    tracker.reset()

    # Add baseline cost using record_from_llm_response helper
    tracker.record_from_llm_response(
        model="openai/gpt-4o",
        prompt_tokens=1000,
        completion_tokens=500,
        stage=12,
        phase="search",
        node_id="node-1",
        purpose="generation",
    )

    # Assert accumulated cost matches pricing table rates
    # openai/gpt-4o rate: $2.50 per 1M input, $10.00 per 1M output
    # Input cost: 1000 * 2.5e-6 = $0.0025
    # Output cost: 500 * 10e-6 = $0.0050
    # Expected cost: $0.0075
    assert abs(tracker.total_usd() - 0.0075) < 1e-7

    # Stage-wise cost check
    stage_cost = tracker.by_stage().get(12, 0.0)
    assert abs(stage_cost - 0.0075) < 1e-7


# ---------------------------------------------------------------------------
# Figure Critic Plot Verdict Tests (E3)
# ---------------------------------------------------------------------------


def test_plot_verdict_fail_open() -> None:
    # verify_plots must fail-open (return verdict.is_buggy=None) if critic is None
    verdict = asyncio.run(
        verify_plots(
            plot_paths=[],
            critic=None,
        )
    )
    assert verdict.is_buggy is None
    assert verdict.confidence == 0.0
