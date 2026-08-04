"""Search configuration and policies for experiment search.

Defines the SearchConfig dataclass and SearchPolicy protocol,
plus the default BestFirstDiversePolicy implementation.

This is the control plane for E2: it determines WHICH nodes to
expand next during tree-diverse search.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Protocol

from berb.experiment.journal import ExperimentJournal, JournalNode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchConfig:
    """Configuration for tree-diverse experiment search.

    Attributes:
        enabled: Master switch. When False, the legacy single-run path is used.
        num_workers: Number of concurrent sandbox evaluations.
        num_roots: Number of independent solution trees to grow.
        max_nodes: Hard cap on total evaluations across all trees.
        max_depth: Maximum tree depth from any root.
        debug_probability: Probability of selecting a buggy leaf for repair.
        max_debug_depth: Maximum repair attempts on any single buggy leaf.
        eval_timeout_sec: Per-node evaluation timeout.
        budget_usd: Hard cost stop (USD). Search stops when exceeded.
        budget_wallclock_sec: Hard wall-clock stop (seconds).
    """

    enabled: bool = False
    num_workers: int = 3
    num_roots: int = 3
    max_nodes: int = 12
    max_depth: int = 3
    debug_probability: float = 0.5
    max_debug_depth: int = 3
    eval_timeout_sec: int = 300
    budget_usd: float = 5.0
    budget_wallclock_sec: int = 3600


class SearchPolicy(Protocol):
    """Protocol for search node-selection policies.

    A policy determines which nodes to expand next, given the current
    state of the journal.
    """

    def select(
        self,
        journal: ExperimentJournal,
        n: int,
        config: SearchConfig,
    ) -> list[JournalNode | None]:
        """Return n nodes to expand.

        Args:
            journal: Current experiment journal.
            n: Number of nodes to select.
            config: Search configuration.

        Returns:
            List of n nodes. `None` means "create a new root".
            Order matters: the first element is the highest-priority node.
        """
        ...


class BestFirstDiversePolicy:
    """Default search policy: best-first with tree-diversity constraint.

    Three rules, in order:

    1. BOOTSTRAP: While `len(journal.roots()) < num_roots`, emit `None`
       — grow independent trees before deepening any one.

    2. REPAIR: With probability `debug_probability`, select a random buggy
       leaf whose `debug_depth <= max_debug_depth`.

    3. EXPLOIT WITH DIVERSITY: Otherwise select the best node — subject to
       a tree-diversity constraint: no two workers in the same batch expand
       nodes sharing a root, unless every root is already claimed.

    The diversity constraint (Rule 3) prevents N workers from converging
    on the same frontier, ensuring parallelism buys exploration, not just
    faster hill-climbing.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def select(
        self,
        journal: ExperimentJournal,
        n: int,
        config: SearchConfig,
    ) -> list[JournalNode | None]:
        selections: list[JournalNode | None] = []
        roots = journal.roots()
        leaves = journal.leaves()

        # Track which roots are already "claimed" by a selection
        claimed_roots: set[str] = set()

        for _ in range(n):
            selected = self._select_one(
                journal=journal,
                roots=roots,
                leaves=leaves,
                config=config,
                claimed_roots=claimed_roots,
            )

            # Track the root of the selected node for diversity
            if selected is not None:
                root_id = self._find_root(journal, selected.node_id)
                if root_id is not None:
                    claimed_roots.add(root_id)

            selections.append(selected)

        return selections

    def _select_one(
        self,
        journal: ExperimentJournal,
        roots: list[JournalNode],
        leaves: list[JournalNode],
        config: SearchConfig,
        claimed_roots: set[str],
    ) -> JournalNode | None:
        """Select a single node for expansion.

        Returns None to signal "create a new root".
        """

        # Rule 1: Bootstrap — grow independent trees
        if len(roots) < config.num_roots:
            logger.debug(
                "Policy: bootstrap — creating root %d/%d", len(roots) + 1, config.num_roots
            )
            return None

        # Rule 2: Repair — fix buggy leaves with some probability
        if self._rng.random() < config.debug_probability:
            # Find buggy leaves that haven't been debugged too much
            buggy_leaves = [
                leaf
                for leaf in leaves
                if leaf.is_buggy is True and _debug_depth(leaf, journal) < config.max_debug_depth
            ]
            if buggy_leaves:
                selected = self._rng.choice(buggy_leaves)
                logger.debug("Policy: repair — selected buggy leaf %s", selected.node_id[:8])
                return selected

        # Rule 3: Exploit with diversity
        good_leaves = [leaf for leaf in leaves if leaf.is_buggy is not True]

        # Filter out leaves whose root is already claimed (diversity constraint)
        candidate_leaves = []
        for leaf in good_leaves:
            leaf_root = self._find_root(journal, leaf.node_id)
            if (
                leaf_root is None
                or leaf_root not in claimed_roots
                or len(claimed_roots) >= len(roots)
            ):
                # Either no root constraint, or all roots are claimed anyway
                candidate_leaves.append(leaf)

        if not candidate_leaves:
            # Fallback: any leaf
            candidate_leaves = good_leaves

        if not candidate_leaves:
            # No leaves at all — create a new root
            return None

        # Score-sort candidates: prefer nodes with higher metrics
        def _candidate_quality(leaf: JournalNode) -> float:
            if leaf.score is not None:
                return leaf.score.total
            if leaf.metrics:
                # Use the first metric value as a proxy
                first_val = next(iter(leaf.metrics.values()), 0.0)
                return float(first_val)
            return 0.0

        candidate_leaves.sort(key=_candidate_quality, reverse=True)
        selected = candidate_leaves[0]
        logger.debug(
            "Policy: exploit — selected %s (score=%.2f)",
            selected.node_id[:8],
            _candidate_quality(selected),
        )
        return selected

    def _find_root(self, journal: ExperimentJournal, node_id: str) -> str | None:
        """Find the root node_id for a given node."""
        node = journal.get_node(node_id)
        if node is None:
            return None
        while node is not None and node.parent_id is not None:
            parent = journal.get_node(node.parent_id)
            if parent is None:
                break
            node = parent
        return node.node_id


def _debug_depth(node: JournalNode, journal: ExperimentJournal) -> int:
    """Count how many times this node or its ancestors have been repaired."""
    debug_count = 0
    current: JournalNode | None = node
    while current is not None:
        if current.origin == "debug":
            debug_count += 1
        if current.parent_id is not None:
            current = journal.get_node(current.parent_id)
        else:
            current = None
    return debug_count
