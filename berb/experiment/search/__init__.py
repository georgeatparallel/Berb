"""Experiment search package.

Contains:
    - scoring: Metric-grounded candidate scoring
    - policy: Search policies (tree-diverse, best-first)
    - runner: Search runner orchestrating evaluation and selection

Substrate for E2: Promoted search into the execution stage.
"""

from __future__ import annotations

from berb.experiment.search.policy import (
    BestFirstDiversePolicy,
    SearchConfig,
    SearchPolicy,
)
from berb.experiment.search.runner import (
    BudgetGovernor,
    SearchResult,
    SearchRunner,
)
from berb.experiment.search.scoring import (
    ScoreBreakdown,
    normalize_cohort,
    score_node,
)

__all__ = [
    "SearchConfig",
    "SearchPolicy",
    "BestFirstDiversePolicy",
    "BudgetGovernor",
    "SearchResult",
    "SearchRunner",
    "ScoreBreakdown",
    "score_node",
    "normalize_cohort",
]
