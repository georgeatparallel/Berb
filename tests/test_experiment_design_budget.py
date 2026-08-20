"""Unit tests for _trim_plan_to_condition_budget (P1-04, stage 9).

BUG-R41-09's time-budget trim used to slice plan["baselines"] purely by
count, which could silently drop benchmark-agent-selected reference
baselines under a tight budget — the paper would then ship with no SOTA
comparison. required_baseline_count guarantees those survive.
"""

from __future__ import annotations

from berb.pipeline.stage_impls._experiment_design import _trim_plan_to_condition_budget


def test_trim_preserves_required_baselines_under_tight_budget() -> None:
    # 25 conditions total, budget caps at 8 (default, time_budget_sec <= 3600)
    plan = {
        "baselines": [
            "resnet50",
            "vit_b16",
            "efficientnet",
        ],  # first 3 = benchmark-required
        "proposed_methods": [f"variant_{i}" for i in range(15)],
        "ablations": [f"ablation_{i}" for i in range(7)],
    }

    result = _trim_plan_to_condition_budget(
        plan, time_budget_sec=3000, required_baseline_count=3
    )

    assert set(result["baselines"]) >= {"resnet50", "vit_b16", "efficientnet"}
    assert len(result["proposed_methods"]) < 15
    assert (
        len(result["baselines"])
        + len(result["proposed_methods"])
        + len(result["ablations"])
        <= 8
    )


def test_trim_expands_budget_when_required_baselines_alone_exceed_it() -> None:
    plan = {
        "baselines": [f"required_baseline_{i}" for i in range(10)],
        "proposed_methods": ["ours"],
        "ablations": [],
    }

    result = _trim_plan_to_condition_budget(
        plan, time_budget_sec=3000, required_baseline_count=10
    )

    # All 10 required baselines survive even though the nominal budget is 8.
    assert len(result["baselines"]) == 10


def test_trim_no_op_when_under_budget() -> None:
    plan = {"baselines": ["a"], "proposed_methods": ["b"], "ablations": ["c"]}

    result = _trim_plan_to_condition_budget(
        plan, time_budget_sec=3000, required_baseline_count=1
    )

    assert result["baselines"] == ["a"]
    assert result["proposed_methods"] == ["b"]
    assert result["ablations"] == ["c"]


def test_trim_defaults_required_baseline_count_to_zero() -> None:
    """When no benchmark agent ran, behavior matches the pre-P1-04 trim
    (baselines get a floor of 1, not preferential treatment)."""
    plan = {
        "baselines": [f"b{i}" for i in range(10)],
        "proposed_methods": [f"p{i}" for i in range(10)],
        "ablations": [f"a{i}" for i in range(10)],
    }

    result = _trim_plan_to_condition_budget(plan, time_budget_sec=3000)

    total = (
        len(result["baselines"])
        + len(result["proposed_methods"])
        + len(result["ablations"])
    )
    assert total <= 8
    assert len(result["baselines"]) >= 1


def test_trim_handles_dict_shaped_baselines() -> None:
    """LLM sometimes emits baselines as a dict rather than a list (BUG-35)."""
    plan = {
        "baselines": {"resnet50": {}, "vit": {}},
        "proposed_methods": [f"p{i}" for i in range(10)],
        "ablations": [],
    }

    result = _trim_plan_to_condition_budget(
        plan, time_budget_sec=3000, required_baseline_count=2
    )

    assert len(result["baselines"]) == 2
