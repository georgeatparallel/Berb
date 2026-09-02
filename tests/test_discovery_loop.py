"""Tests for the research-direction loop: world model, cycle logic, and the
pipeline executor that drives it over the stage 7-15 slice.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from berb.research.discovery_loop import (
    BudgetGovernor,
    DiscoveryConfig,
    DiscoveryLoop,
    TaskOutcome,
    reflect,
)
from berb.research.world_model import (
    Contradiction,
    DeadEnd,
    Finding,
    FindingVerdict,
    Guidance,
    Question,
    WorldModel,
)


def _finding(fid: str, statement: str = "s", effect: float = 1.0) -> Finding:
    return Finding(
        id=fid,
        statement=statement,
        verdict=FindingVerdict.SUPPORTED,
        effect_size=effect,
    )


# ---------------------------------------------------------------------------
# WorldModel
# ---------------------------------------------------------------------------


def test_proposes_a_generic_task_from_a_bare_objective() -> None:
    wm = WorldModel(objective="Find the best optimiser")
    tasks = wm.propose_tasks(k=3)
    assert len(tasks) == 1
    assert "Find the best optimiser" in tasks[0]


def test_contradictions_and_questions_become_tasks() -> None:
    wm = WorldModel(objective="obj")
    wm.contradictions.append(Contradiction("a", "b", "A and B disagree"))
    wm.open_questions.append(Question(id="q1", text="Does X hold?", priority=0.9))

    tasks = wm.propose_tasks(k=5)
    assert any("A and B disagree" in t for t in tasks)
    assert any("Does X hold?" in t for t in tasks)


def test_questions_are_proposed_in_priority_order() -> None:
    wm = WorldModel(objective="obj")
    wm.open_questions.append(Question(id="low", text="low", priority=0.1))
    wm.open_questions.append(Question(id="high", text="high", priority=0.9))
    assert "high" in wm.propose_tasks(k=1)[0]


def test_dead_ends_are_recognised_by_substring() -> None:
    wm = WorldModel(objective="obj")
    wm.dead_ends.append(DeadEnd(description="try bigger batches", reason="no effect"))
    assert wm.is_dead_end("Investigate: try bigger batches on CIFAR")
    assert not wm.is_dead_end("Investigate: learning-rate warmup")


def test_convergence_requires_enough_findings() -> None:
    wm = WorldModel(objective="obj")
    wm.established.extend(_finding(f"f{i}") for i in range(2))
    assert not wm.converged(min_established=3)
    wm.established.append(_finding("f2"))
    assert wm.converged(min_established=3)


def test_an_unresolved_contradiction_blocks_convergence() -> None:
    wm = WorldModel(objective="obj")
    wm.established.extend(_finding(f"f{i}") for i in range(3))
    wm.contradictions.append(Contradiction("f0", "f1", "conflict"))
    assert not wm.converged(min_established=3)


def test_a_high_priority_question_blocks_convergence() -> None:
    wm = WorldModel(objective="obj")
    wm.established.extend(_finding(f"f{i}") for i in range(3))
    wm.open_questions.append(Question(id="q", text="still open", priority=0.9))
    assert not wm.converged(min_established=3)


def test_world_model_round_trips_through_json() -> None:
    wm = WorldModel(objective="obj", current_best_explanation="best so far")
    wm.established.append(_finding("f0", "established thing"))
    wm.refuted.append(Finding(id="r0", statement="refuted thing", verdict=FindingVerdict.REFUTED))
    wm.open_questions.append(Question(id="q0", text="open"))
    wm.contradictions.append(Contradiction("f0", "r0", "conflict"))
    wm.dead_ends.append(DeadEnd(description="dead", reason="because"))
    wm.guidance = Guidance(gaps=["g"], confounds=["c"], compound_hypotheses=["h"])

    restored = WorldModel.from_dict(json.loads(json.dumps(wm.to_dict())))

    assert restored.objective == "obj"
    assert restored.established[0].statement == "established thing"
    assert restored.refuted[0].verdict == FindingVerdict.REFUTED
    assert restored.dead_ends[0].reason == "because"
    assert restored.guidance is not None
    assert restored.guidance.gaps == ["g"]


# ---------------------------------------------------------------------------
# REFLECT
# ---------------------------------------------------------------------------


def test_reflect_surfaces_questions_contradictions_and_pairs() -> None:
    wm = WorldModel(objective="obj")
    wm.open_questions.append(Question(id="q", text="why?", priority=0.9))
    wm.contradictions.append(Contradiction("a", "b", "conflict"))
    wm.established.extend([_finding("f0", "alpha"), _finding("f1", "beta")])

    guidance = reflect(wm)

    assert any("why?" in g for g in guidance.gaps)
    assert any("conflict" in c for c in guidance.confounds)
    assert guidance.compound_hypotheses


def test_reflect_on_an_empty_model_is_empty_not_an_error() -> None:
    guidance = reflect(WorldModel(objective="obj"))
    assert guidance.gaps == []
    assert guidance.compound_hypotheses == []


def test_reflect_with_a_single_finding_produces_no_pair() -> None:
    wm = WorldModel(objective="obj")
    wm.established.append(_finding("f0"))
    assert reflect(wm).compound_hypotheses == []


# ---------------------------------------------------------------------------
# BudgetGovernor
# ---------------------------------------------------------------------------


def test_zero_budget_means_unlimited() -> None:
    gov = BudgetGovernor(0.0)
    assert gov.spend(1_000_000.0) is True
    assert gov.exhausted is False
    assert gov.remaining == float("inf")


def test_budget_exhausts_at_the_cap() -> None:
    gov = BudgetGovernor(1.0)
    assert gov.spend(0.5) is True
    assert gov.spend(0.5) is False
    assert gov.exhausted is True
    assert gov.remaining == 0.0


# ---------------------------------------------------------------------------
# DiscoveryLoop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_loop_does_nothing() -> None:
    calls: list[str] = []

    async def _exec(task: str, cycle: int) -> TaskOutcome:
        calls.append(task)
        return TaskOutcome()

    result = await DiscoveryLoop(
        WorldModel(objective="obj"), DiscoveryConfig(enabled=False), executor=_exec
    ).run()

    assert result.stop_reason == "disabled"
    assert not calls


@pytest.mark.asyncio
async def test_enabled_loop_without_an_executor_says_so_instead_of_spinning() -> None:
    """The deleted version produced stub dead ends for max_cycles instead."""
    result = await DiscoveryLoop(
        WorldModel(objective="obj"), DiscoveryConfig(enabled=True, max_cycles=3)
    ).run()

    assert result.stop_reason == "no_executor"
    assert result.total_cycles == 0


@pytest.mark.asyncio
async def test_findings_accumulate_and_the_loop_converges() -> None:
    counter = {"n": 0}

    async def _exec(task: str, cycle: int) -> TaskOutcome:
        counter["n"] += 1
        return TaskOutcome(findings=(_finding(f"f{counter['n']}", task),))

    wm = WorldModel(objective="obj")
    result = await DiscoveryLoop(
        wm,
        DiscoveryConfig(enabled=True, max_cycles=5, width=3, min_established_for_convergence=3),
        executor=_exec,
    ).run()

    assert result.stop_reason == "converged"
    assert len(result.admitted_findings) >= 3
    assert result.converged is True


@pytest.mark.asyncio
async def test_max_cycles_bounds_the_loop() -> None:
    async def _exec(task: str, cycle: int) -> TaskOutcome:
        # Never admits anything, so convergence can never fire.
        return TaskOutcome(questions=(Question(id=f"q{cycle}", text=f"open {cycle}"),))

    result = await DiscoveryLoop(
        WorldModel(objective="obj"),
        DiscoveryConfig(enabled=True, max_cycles=2, width=1),
        executor=_exec,
    ).run()

    assert result.stop_reason == "max_cycles_reached"
    assert result.total_cycles == 2


@pytest.mark.asyncio
async def test_a_failing_task_becomes_a_dead_end_not_a_crash() -> None:
    async def _exec(task: str, cycle: int) -> TaskOutcome:
        raise RuntimeError("sandbox exploded")

    wm = WorldModel(objective="obj")
    result = await DiscoveryLoop(
        wm, DiscoveryConfig(enabled=True, max_cycles=1, width=1), executor=_exec
    ).run()

    assert result.total_cycles == 1
    assert any("sandbox exploded" in d.reason for d in wm.dead_ends)


@pytest.mark.asyncio
async def test_an_empty_outcome_becomes_a_dead_end() -> None:
    """Otherwise the same fruitless direction is proposed every cycle."""

    async def _exec(task: str, cycle: int) -> TaskOutcome:
        return TaskOutcome()

    wm = WorldModel(objective="obj")
    await DiscoveryLoop(
        wm, DiscoveryConfig(enabled=True, max_cycles=1, width=1), executor=_exec
    ).run()

    assert wm.dead_ends


@pytest.mark.asyncio
async def test_the_loop_stops_when_every_direction_is_a_dead_end() -> None:
    async def _exec(task: str, cycle: int) -> TaskOutcome:
        return TaskOutcome()

    result = await DiscoveryLoop(
        WorldModel(objective="obj"),
        DiscoveryConfig(enabled=True, max_cycles=5, width=1),
        executor=_exec,
    ).run()

    assert result.stop_reason == "no_tasks_remaining"
    assert result.total_cycles < 5


@pytest.mark.asyncio
async def test_the_budget_stops_the_loop() -> None:
    async def _exec(task: str, cycle: int) -> TaskOutcome:
        return TaskOutcome(
            questions=(Question(id=f"q{cycle}", text=f"open {cycle}"),), cost_usd=1.0
        )

    result = await DiscoveryLoop(
        WorldModel(objective="obj"),
        DiscoveryConfig(enabled=True, max_cycles=10, width=1, budget_usd=1.5),
        executor=_exec,
    ).run()

    assert result.stop_reason == "budget_exhausted"
    assert result.total_cost_usd >= 1.5


@pytest.mark.asyncio
async def test_tasks_in_a_cycle_run_concurrently() -> None:
    import asyncio

    started = asyncio.Event()
    both_running = []

    async def _exec(task: str, cycle: int) -> TaskOutcome:
        both_running.append(task)
        if len(both_running) >= 2:
            started.set()
        await asyncio.wait_for(started.wait(), timeout=2)
        return TaskOutcome(findings=(_finding(task, task),))

    wm = WorldModel(objective="obj")
    wm.open_questions.extend(
        [Question(id="q1", text="one", priority=0.9), Question(id="q2", text="two", priority=0.8)]
    )

    await DiscoveryLoop(
        wm, DiscoveryConfig(enabled=True, max_cycles=1, width=2), executor=_exec
    ).run()

    assert len(both_running) == 2


@pytest.mark.asyncio
async def test_reflect_runs_on_its_cadence_and_sets_guidance() -> None:
    async def _exec(task: str, cycle: int) -> TaskOutcome:
        return TaskOutcome(questions=(Question(id=f"q{cycle}", text=f"open {cycle}"),))

    wm = WorldModel(objective="obj")
    result = await DiscoveryLoop(
        wm,
        DiscoveryConfig(enabled=True, max_cycles=2, width=1, reflect_every=2),
        executor=_exec,
    ).run()

    assert result.cycles[0].reflect_output is None
    assert result.cycles[1].reflect_output is not None
    assert wm.guidance is not None


@pytest.mark.asyncio
async def test_reflect_every_zero_disables_reflection() -> None:
    async def _exec(task: str, cycle: int) -> TaskOutcome:
        return TaskOutcome(questions=(Question(id=f"q{cycle}", text=f"open {cycle}"),))

    result = await DiscoveryLoop(
        WorldModel(objective="obj"),
        DiscoveryConfig(enabled=True, max_cycles=2, width=1, reflect_every=0),
        executor=_exec,
    ).run()

    assert all(c.reflect_output is None for c in result.cycles)


@pytest.mark.asyncio
async def test_world_model_is_saved_as_json(tmp_path: Path) -> None:
    wm = WorldModel(objective="obj")
    wm.established.append(_finding("f0"))
    loop = DiscoveryLoop(wm, DiscoveryConfig(enabled=True))

    path = loop.save_world_model(tmp_path / "nested" / "world_model.json")

    assert json.loads(path.read_text(encoding="utf-8"))["objective"] == "obj"


# ---------------------------------------------------------------------------
# The pipeline executor
# ---------------------------------------------------------------------------


def _write_slice(task_dir: Path, decision: str, metric: float | None = 0.87) -> None:
    (task_dir / "stage-15").mkdir(parents=True, exist_ok=True)
    (task_dir / "stage-15" / "decision_structured.json").write_text(
        json.dumps({"decision": decision}), encoding="utf-8"
    )
    if metric is not None:
        (task_dir / "stage-14").mkdir(parents=True, exist_ok=True)
        (task_dir / "stage-14" / "metrics.json").write_text(
            json.dumps({"accuracy": metric}), encoding="utf-8"
        )


def test_proceed_becomes_an_established_finding(tmp_path: Path) -> None:
    from berb.pipeline.discovery import _outcome_from_slice

    _write_slice(tmp_path, "PROCEED")
    outcome = _outcome_from_slice("investigate X", 1, tmp_path, [])

    assert len(outcome.findings) == 1
    assert outcome.findings[0].verdict == FindingVerdict.SUPPORTED
    assert outcome.findings[0].metric_key == "accuracy"
    assert outcome.findings[0].effect_size == pytest.approx(0.87)


def test_pivot_becomes_a_refutation_plus_a_question(tmp_path: Path) -> None:
    from berb.pipeline.discovery import _outcome_from_slice

    _write_slice(tmp_path, "PIVOT")
    outcome = _outcome_from_slice("investigate X", 1, tmp_path, [])

    assert not outcome.findings
    assert outcome.rejected[0].verdict == FindingVerdict.REFUTED
    assert outcome.questions


def test_a_slice_with_no_decision_settles_nothing(tmp_path: Path) -> None:
    from berb.pipeline.discovery import _outcome_from_slice

    outcome = _outcome_from_slice("investigate X", 1, tmp_path, [])
    assert outcome.is_empty()


def test_a_malformed_decision_file_settles_nothing(tmp_path: Path) -> None:
    from berb.pipeline.discovery import _outcome_from_slice

    (tmp_path / "stage-15").mkdir(parents=True)
    (tmp_path / "stage-15" / "decision_structured.json").write_text("not json", encoding="utf-8")

    assert _outcome_from_slice("x", 1, tmp_path, []).is_empty()


def test_metrics_are_optional(tmp_path: Path) -> None:
    from berb.pipeline.discovery import _outcome_from_slice

    _write_slice(tmp_path, "PROCEED", metric=None)
    finding = _outcome_from_slice("x", 1, tmp_path, []).findings[0]

    assert finding.metric_key == ""
    assert finding.effect_size == 0.0


def test_slice_cost_sums_stage_results(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from berb.pipeline.discovery import _outcome_from_slice

    _write_slice(tmp_path, "PROCEED")
    results = [SimpleNamespace(cost_usd=1.5), SimpleNamespace(cost_usd=0.5), SimpleNamespace()]

    assert _outcome_from_slice("x", 1, tmp_path, results).cost_usd == pytest.approx(2.0)


def test_promote_picks_the_largest_effect(tmp_path: Path) -> None:
    from berb.pipeline.discovery import promote_best_task

    index = tmp_path / "discovery" / "index.jsonl"
    index.parent.mkdir(parents=True)
    for name, effect in (("weak", 0.1), ("strong", 0.9)):
        task_dir = tmp_path / "discovery" / name / "stage-14"
        task_dir.mkdir(parents=True)
        (task_dir / "metrics.json").write_text(json.dumps({"accuracy": effect}), encoding="utf-8")
    index.write_text(
        "\n".join(
            json.dumps(
                {
                    "cycle": 1,
                    "task": n,
                    "task_dir": f"discovery/{n}",
                    "admitted": True,
                    "effect_size": e,
                }
            )
            for n, e in (("weak", 0.1), ("strong", 0.9))
        ),
        encoding="utf-8",
    )

    assert promote_best_task(tmp_path) == "strong"
    promoted = json.loads((tmp_path / "stage-14" / "metrics.json").read_text(encoding="utf-8"))
    assert promoted["accuracy"] == pytest.approx(0.9)


def test_promote_respects_a_minimised_metric(tmp_path: Path) -> None:
    from berb.pipeline.discovery import promote_best_task

    index = tmp_path / "discovery" / "index.jsonl"
    index.parent.mkdir(parents=True)
    index.write_text(
        "\n".join(
            json.dumps(
                {
                    "cycle": 1,
                    "task": n,
                    "task_dir": f"discovery/{n}",
                    "admitted": True,
                    "effect_size": e,
                }
            )
            for n, e in (("low", 0.1), ("high", 0.9))
        ),
        encoding="utf-8",
    )
    assert promote_best_task(tmp_path, maximize=False) == "low"


def test_promote_returns_empty_when_nothing_was_admitted(tmp_path: Path) -> None:
    from berb.pipeline.discovery import promote_best_task

    index = tmp_path / "discovery" / "index.jsonl"
    index.parent.mkdir(parents=True)
    index.write_text(
        json.dumps({"cycle": 1, "task": "t", "task_dir": "discovery/t", "admitted": False}),
        encoding="utf-8",
    )
    assert promote_best_task(tmp_path) == ""


def test_promote_returns_empty_without_an_index(tmp_path: Path) -> None:
    from berb.pipeline.discovery import promote_best_task

    assert promote_best_task(tmp_path) == ""


def test_world_model_resumes_from_disk(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from berb.pipeline.discovery import build_world_model

    wm = WorldModel(objective="saved objective")
    wm.established.append(_finding("f0"))
    (tmp_path / "world_model.json").write_text(json.dumps(wm.to_dict()), encoding="utf-8")

    config: Any = SimpleNamespace(research=SimpleNamespace(topic="fresh topic"))
    restored = build_world_model(config, tmp_path)

    assert restored.objective == "saved objective"
    assert len(restored.established) == 1


def test_a_corrupt_saved_model_starts_fresh(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from berb.pipeline.discovery import build_world_model

    (tmp_path / "world_model.json").write_text("{{{", encoding="utf-8")
    config: Any = SimpleNamespace(research=SimpleNamespace(topic="fresh topic"))

    assert build_world_model(config, tmp_path).objective == "fresh topic"


# ---------------------------------------------------------------------------
# The runner seam
# ---------------------------------------------------------------------------


def test_to_stage_bounds_the_dag_levels() -> None:
    """The slice run is not expressible with from_stage alone."""
    from berb.pipeline.resolution import resolve_stage_order
    from berb.pipeline.runner import _build_dag_levels
    from berb.pipeline.stages import Stage

    levels = _build_dag_levels(resolve_stage_order(Stage.SYNTHESIS))
    bounded = [
        kept
        for kept in (
            {s for s in level if int(s) <= int(Stage.RESEARCH_DECISION)} for level in levels
        )
        if kept
    ]
    stages = {s for level in bounded for s in level}

    assert Stage.SYNTHESIS in stages
    assert Stage.RESEARCH_DECISION in stages
    assert Stage.PAPER_OUTLINE not in stages


@pytest.mark.asyncio
async def test_runner_skips_discovery_when_disabled(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from berb.pipeline.runner import _maybe_run_discovery
    from berb.pipeline.stages import Stage

    config: Any = SimpleNamespace(
        research=SimpleNamespace(discovery=SimpleNamespace(enabled=False))
    )
    promoted = await _maybe_run_discovery(
        run_dir=tmp_path,
        run_id="r",
        config=config,
        adapters=None,
        from_stage=Stage.TOPIC_INIT,
        auto_approve_gates=False,
        kb_root=None,
    )
    assert promoted == ""


@pytest.mark.asyncio
async def test_runner_skips_discovery_when_resuming_past_the_slice(tmp_path: Path) -> None:
    """--from-stage PAPER_OUTLINE is resuming a decided run, not choosing one."""
    from types import SimpleNamespace

    from berb.pipeline.runner import _maybe_run_discovery
    from berb.pipeline.stages import Stage

    config: Any = SimpleNamespace(research=SimpleNamespace(discovery=SimpleNamespace(enabled=True)))
    promoted = await _maybe_run_discovery(
        run_dir=tmp_path,
        run_id="r",
        config=config,
        adapters=None,
        from_stage=Stage.PAPER_OUTLINE,
        auto_approve_gates=False,
        kb_root=None,
    )
    assert promoted == ""


@pytest.mark.asyncio
async def test_a_discovery_failure_degrades_to_a_single_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Losing the whole run to a discovery bug would be a bad trade."""
    from types import SimpleNamespace

    import berb.pipeline.discovery as discovery_mod
    from berb.pipeline.runner import _maybe_run_discovery
    from berb.pipeline.stages import Stage

    async def _boom(**kwargs: Any) -> Any:
        raise RuntimeError("loop exploded")

    monkeypatch.setattr(discovery_mod, "run_discovery", _boom)

    config: Any = SimpleNamespace(research=SimpleNamespace(discovery=SimpleNamespace(enabled=True)))
    promoted = await _maybe_run_discovery(
        run_dir=tmp_path,
        run_id="r",
        config=config,
        adapters=None,
        from_stage=Stage.TOPIC_INIT,
        auto_approve_gates=False,
        kb_root=None,
    )
    assert promoted == ""
