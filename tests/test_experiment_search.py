"""Tests for experiment search subsystems (E1, E2, F2, E3, E10)."""

from __future__ import annotations

import asyncio

import pytest

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


# ---------------------------------------------------------------------------
# Figure gate (E2): is_buggy_plots producer
# ---------------------------------------------------------------------------
#
# search/scoring.py hard-gates on JournalNode.is_buggy_plots, but nothing set
# the field, so the gate was inert. These cover the producer wired into
# SearchRunner._verify_node_plots.


class _StubCritic:
    """Critic matching the analyze_figure protocol verify_plots expects."""

    def __init__(self, acceptable: bool) -> None:
        self._acceptable = acceptable
        self.calls: list[str] = []

    async def analyze_figure(self, figure_path, paper_context: str = ""):
        from berb.experiment.plot_verdict import _PixelCritique

        self.calls.append(str(figure_path))
        return _PixelCritique(
            is_acceptable=self._acceptable,
            overall_score=8.0 if self._acceptable else 2.0,
            issues=() if self._acceptable else ("blank chart",),
            confidence=0.9,
        )


class _StubSandbox:
    def __init__(self, workdir) -> None:
        self.workdir = workdir


def _runner_with_critic(tmp_path, critic):
    from berb.experiment.search.policy import BestFirstDiversePolicy
    from berb.experiment.search.runner import SearchRunner

    return SearchRunner(
        config=SearchConfig(enabled=True),
        policy=BestFirstDiversePolicy(seed=0),
        sandbox_factory=lambda: _StubSandbox(tmp_path),
        generator=lambda **_: [],
        cost_tracker=CostTracker(),
        metric_key="acc",
        figure_critic=critic,
    )


def _node() -> JournalNode:
    return JournalNode(node_id="n1", plan="study the thing")


def test_figure_gate_marks_node_buggy_when_critic_rejects(tmp_path) -> None:
    (tmp_path / "fig1.png").write_bytes(b"not-a-real-png")
    critic = _StubCritic(acceptable=False)
    runner = _runner_with_critic(tmp_path, critic)
    node = _node()

    asyncio.run(runner._verify_node_plots(node, _StubSandbox(tmp_path)))

    assert node.is_buggy_plots is True
    assert node.plot_paths and node.plot_paths[0].name == "fig1.png"
    assert critic.calls, "critic should have been consulted"


def test_figure_gate_passes_valid_figures(tmp_path) -> None:
    (tmp_path / "fig1.png").write_bytes(b"not-a-real-png")
    runner = _runner_with_critic(tmp_path, _StubCritic(acceptable=True))
    node = _node()

    asyncio.run(runner._verify_node_plots(node, _StubSandbox(tmp_path)))

    assert node.is_buggy_plots is False


def test_figure_gate_fails_open_without_critic(tmp_path) -> None:
    """No critic configured must leave the verdict unset, not guess."""
    (tmp_path / "fig1.png").write_bytes(b"not-a-real-png")
    runner = _runner_with_critic(tmp_path, None)
    node = _node()

    asyncio.run(runner._verify_node_plots(node, _StubSandbox(tmp_path)))

    assert node.is_buggy_plots is None
    assert node.plot_paths == ()


def test_figure_gate_fails_open_with_no_images(tmp_path) -> None:
    runner = _runner_with_critic(tmp_path, _StubCritic(acceptable=False))
    node = _node()

    asyncio.run(runner._verify_node_plots(node, _StubSandbox(tmp_path)))

    assert node.is_buggy_plots is None


def test_figure_gate_fails_open_when_critic_raises(tmp_path) -> None:
    """A broken critic must never fail the candidate's evaluation."""

    class _Exploding:
        async def analyze_figure(self, figure_path, paper_context: str = ""):
            raise RuntimeError("critic exploded")

    (tmp_path / "fig1.png").write_bytes(b"not-a-real-png")
    runner = _runner_with_critic(tmp_path, _Exploding())
    node = _node()

    asyncio.run(runner._verify_node_plots(node, _StubSandbox(tmp_path)))

    assert node.is_buggy_plots is None


def test_buggy_plots_verdict_zeroes_the_score() -> None:
    """The gate the producer feeds: an invalid figure costs the candidate."""
    node = JournalNode(node_id="n2", metrics={"acc": 0.99}, returncode=0)
    node.is_buggy_plots = True

    breakdown = score_node(node, "acc", maximize=True)

    assert breakdown.total == 0.0
    assert "figures" in breakdown.reason.lower()


def test_pixel_critic_rejects_a_blank_chart(tmp_path) -> None:
    """End-to-end through the real critic — requires Pillow (ships with [all])."""
    pytest.importorskip("PIL")
    from PIL import Image

    from berb.experiment.plot_verdict import PixelPlotCritic

    blank = tmp_path / "blank.png"
    Image.new("RGB", (64, 64), (255, 255, 255)).save(blank)

    critique = asyncio.run(PixelPlotCritic().analyze_figure(blank))

    assert critique.is_acceptable is False
    assert any("white" in issue for issue in critique.issues)


def test_pixel_critic_accepts_a_drawn_chart(tmp_path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    from berb.experiment.plot_verdict import PixelPlotCritic

    drawn = tmp_path / "drawn.png"
    img = Image.new("RGB", (64, 64), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([10, 10, 54, 54], fill=(10, 10, 200))
    img.save(drawn)

    critique = asyncio.run(PixelPlotCritic().analyze_figure(drawn))

    assert critique.is_acceptable is True
