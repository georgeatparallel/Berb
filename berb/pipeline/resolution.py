"""DAG-based stage resolution — replaces the implicit STAGE_SEQUENCE list.

Given each stage's declared dependencies (via StageContract.depends_on),
computes a topological execution order at runtime.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from collections import defaultdict

from berb.pipeline.contracts import CONTRACTS
from berb.pipeline.stages import Stage


def resolve_stage_order(
    start_from: Stage | None = None,
) -> tuple[Stage, ...]:
    """Compute a topological execution order for all pipeline stages.

    Args:
        start_from: If given, only return stages at or after this stage
                     (the graph is traversed from the start stage onward).

    Returns:
        Tuple of Stage values in valid execution order (dependencies first).
    """
    # Build adjacency: which stages does each stage block?
    #   blocked[k] = set of stages that depend_on k
    in_degree: dict[Stage, int] = {}
    dependents: dict[Stage, set[Stage]] = defaultdict(set)

    all_stages = list(CONTRACTS.keys())
    for stage in all_stages:
        if stage not in in_degree:
            in_degree[stage] = 0

    for stage in all_stages:
        contract = CONTRACTS[stage]
        for dep in contract.depends_on:
            if dep not in in_degree:
                in_degree[dep] = 0
            in_degree[stage] = in_degree.get(stage, 0) + 1
            dependents[dep].add(stage)

    # Kahn's algorithm: start with stages that have zero in-degree.
    # Ties (multiple stages simultaneously eligible) are broken by ascending
    # stage number so the result is deterministic and matches the intended
    # numeric stage ordering whenever the dependency graph allows more than
    # one valid topological order (e.g. sibling stages that both depend on
    # the same upstream stage but not on each other).
    queue: list[Stage] = sorted(
        (stage for stage, degree in in_degree.items() if degree == 0),
        key=int,
    )

    result: list[Stage] = []
    while queue:
        stage = queue.pop(0)
        result.append(stage)
        newly_ready: list[Stage] = []
        for dependent in dependents.get(stage, set()):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                newly_ready.append(dependent)
        if newly_ready:
            queue.extend(newly_ready)
            queue.sort(key=int)

    # If start_from is given, skip everything before it
    if start_from is not None:
        try:
            idx = result.index(start_from)
            return tuple(result[idx:])
        except ValueError:
            # start_from not in result — return all
            return tuple(result)

    return tuple(result)


def eligible_stages(
    completed: set[Stage],
    queue: set[Stage],
) -> set[Stage]:
    """Return stages from *queue* whose dependencies are all satisfied.

    Args:
        completed: Set of stages already finished.
        queue: Set of stages waiting to execute.

    Returns:
        Subset of *queue* where every dep is in *completed*.
    """
    return {s for s in queue if CONTRACTS[s].depends_on.issubset(completed)}


def verify_acyclic() -> bool:
    """Verify the dependency graph has no cycles.

    Returns True if the graph is a valid DAG.
    """
    result = resolve_stage_order()
    # If Kahn's algorithm produced fewer stages than exist, there's a cycle
    return len(result) == len(CONTRACTS)
