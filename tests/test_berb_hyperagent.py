"""Tests for berb/hyperagent/ — base, memory, task_agent, meta_agent."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from berb.hyperagent.base import (
    AgentPhase,
    Hyperagent,
    Improvement,
    ImprovementResult,
    HyperagentState,
    TaskResult,
)
from berb.hyperagent.memory import PerformanceRecord, PersistentMemory
from berb.hyperagent.task_agent import TaskAgent, TaskAgentConfig, TaskAgentState
from berb.hyperagent.meta_agent import MetaAgent, MetaAgentState, ModificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_path() -> Path:
    td = tempfile.mkdtemp()
    return Path(td)


# ---------------------------------------------------------------------------
# base.py — data model tests
# ---------------------------------------------------------------------------


class TestTaskResult:
    def test_to_dict_success(self):
        result = TaskResult(task_id="t1", success=True, output="done", metrics={"quality": 0.9})
        d = result.to_dict()
        assert d["task_id"] == "t1"
        assert d["success"] is True
        assert d["metrics"]["quality"] == 0.9
        assert d["error"] is None
        assert "timestamp" in d

    def test_to_dict_failure(self):
        result = TaskResult(task_id="t2", success=False, error="boom")
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "boom"


class TestImprovement:
    def test_to_dict_round_trip(self):
        imp = Improvement(
            improvement_id="imp-1",
            description="speed up",
            code_diff="--- a\n+++ b",
            affected_component="task_agent",
            expected_benefit="10% faster",
            confidence=0.8,
        )
        d = imp.to_dict()
        assert d["improvement_id"] == "imp-1"
        assert d["confidence"] == 0.8
        assert "timestamp" in d


class TestImprovementResult:
    def test_to_dict_no_improvements(self):
        r = ImprovementResult(iteration=1)
        d = r.to_dict()
        assert d["iteration"] == 1
        assert d["improvements_made"] == []
        assert d["success"] is True

    def test_to_dict_with_improvement(self):
        imp = Improvement(
            improvement_id="i1",
            description="desc",
            code_diff="diff",
            affected_component="task_agent",
            expected_benefit="better",
        )
        r = ImprovementResult(iteration=2, improvements_made=[imp], performance_delta=0.05)
        d = r.to_dict()
        assert len(d["improvements_made"]) == 1
        assert d["performance_delta"] == 0.05


class TestHyperagentState:
    def test_initial_state(self):
        state = HyperagentState()
        assert state.phase == AgentPhase.INIT
        assert state.iteration == 0
        assert state.total_tasks_executed == 0
        assert state.errors == []

    def test_record_error(self):
        state = HyperagentState()
        state.record_error("oops")
        assert "oops" in state.errors

    def test_record_improvement_updates_counters(self):
        state = HyperagentState()
        imp = Improvement(
            improvement_id="i1", description="d", code_diff="", affected_component="ta",
            expected_benefit="e",
        )
        result = ImprovementResult(iteration=1, improvements_made=[imp], performance_delta=0.1)
        state.record_improvement(result)
        assert state.iteration == 1
        assert state.total_improvements == 1
        assert abs(state.cumulative_performance_gain - 0.1) < 1e-9

    def test_to_dict_serialisation(self):
        state = HyperagentState()
        state.record_error("err1")
        d = state.to_dict()
        assert d["phase"] == "init"
        assert "err1" in d["errors"]


# ---------------------------------------------------------------------------
# base.py — Hyperagent class tests
# ---------------------------------------------------------------------------


class TestHyperagent:
    def test_init_creates_storage_dir(self, tmp_path):
        cfg = MagicMock()
        agent = Hyperagent(cfg, storage_path=tmp_path / "ha")
        assert (tmp_path / "ha").is_dir()

    def test_initial_state_is_init_phase(self, tmp_path):
        cfg = MagicMock()
        agent = Hyperagent(cfg, storage_path=tmp_path / "ha")
        assert agent.state.phase == AgentPhase.INIT

    @pytest.mark.asyncio
    async def test_run_task_no_task_agent(self, tmp_path):
        cfg = MagicMock()
        agent = Hyperagent(cfg, storage_path=tmp_path / "ha")
        result = await agent.run_task("do something")
        assert result.success is False
        assert "not initialized" in (result.error or "")

    @pytest.mark.asyncio
    async def test_run_task_delegates_to_task_agent(self, tmp_path):
        cfg = MagicMock()
        agent = Hyperagent(cfg, storage_path=tmp_path / "ha")
        mock_task_result = TaskResult(task_id="do something", success=True)
        mock_ta = AsyncMock()
        mock_ta.execute.return_value = mock_task_result
        agent.task_agent = mock_ta
        agent.memory = None
        result = await agent.run_task("do something")
        assert result.success is True
        assert agent.state.total_tasks_executed == 1

    @pytest.mark.asyncio
    async def test_run_task_handles_exception(self, tmp_path):
        cfg = MagicMock()
        agent = Hyperagent(cfg, storage_path=tmp_path / "ha")
        mock_ta = AsyncMock()
        mock_ta.execute.side_effect = RuntimeError("exploded")
        agent.task_agent = mock_ta
        result = await agent.run_task("bad task")
        assert result.success is False
        assert "exploded" in (result.error or "")

    @pytest.mark.asyncio
    async def test_self_improve_no_loop(self, tmp_path):
        cfg = MagicMock()
        agent = Hyperagent(cfg, storage_path=tmp_path / "ha")
        results = await agent.self_improve(3)
        assert results == []
        assert len(agent.state.errors) == 1

    def test_get_improvement_history_no_memory(self, tmp_path):
        cfg = MagicMock()
        agent = Hyperagent(cfg, storage_path=tmp_path / "ha")
        assert agent.get_improvement_history() == []

    @pytest.mark.asyncio
    async def test_close_no_memory(self, tmp_path):
        cfg = MagicMock()
        agent = Hyperagent(cfg, storage_path=tmp_path / "ha")
        await agent.close()  # must not raise


# ---------------------------------------------------------------------------
# memory.py — PersistentMemory tests
# ---------------------------------------------------------------------------


class TestPersistentMemory:
    def test_init_creates_storage(self, tmp_path):
        mem = PersistentMemory(tmp_path / "mem")
        assert (tmp_path / "mem").is_dir()

    def test_init_empty(self, tmp_path):
        mem = PersistentMemory(tmp_path / "mem")
        assert mem.improvements == []
        assert mem.performance_history == []

    @pytest.mark.asyncio
    async def test_store_improvement(self, tmp_path):
        mem = PersistentMemory(tmp_path / "mem")
        imp = Improvement(
            improvement_id="i1", description="desc", code_diff="",
            affected_component="task_agent", expected_benefit="better", confidence=0.7,
        )
        await mem.store_improvement(imp)
        history = mem.get_all_improvements()
        assert len(history) == 1
        assert history[0].improvement_id == "i1"

    @pytest.mark.asyncio
    async def test_store_performance(self, tmp_path):
        mem = PersistentMemory(tmp_path / "mem")
        await mem.store_performance(
            variant_id="v1", task_id="task-x", metrics={"score": 0.9}, success=True
        )
        assert len(mem.performance_history) == 1
        record = mem.performance_history[0]
        assert record.variant_id == "v1"
        assert record.success is True

    @pytest.mark.asyncio
    async def test_improvements_persisted_across_instances(self, tmp_path):
        storage = tmp_path / "mem"
        mem1 = PersistentMemory(storage)
        imp = Improvement(
            improvement_id="persist-1", description="test", code_diff="diff",
            affected_component="meta_agent", expected_benefit="better",
        )
        await mem1.store_improvement(imp)

        mem2 = PersistentMemory(storage)
        history = mem2.get_all_improvements()
        assert any(i.improvement_id == "persist-1" for i in history)

    def test_transfer_improvements_filters_by_transferable_flag(self, tmp_path):
        mem = PersistentMemory(tmp_path / "mem")
        imp_transferable = Improvement(
            improvement_id="t1", description="d", code_diff="", affected_component="ta",
            expected_benefit="e", transferable=True, source_domain="ml",
        )
        imp_non_transferable = Improvement(
            improvement_id="t2", description="d", code_diff="", affected_component="ta",
            expected_benefit="e", transferable=False, source_domain="ml",
        )
        mem.improvements = [imp_transferable, imp_non_transferable]
        transferred = mem.transfer_improvements(source_domain="ml", target_domain="biology")
        # Returns copies, so check IDs
        transferred_ids = {i.improvement_id for i in transferred}
        assert any("t1" in tid for tid in transferred_ids)
        assert not any("t2" in tid for tid in transferred_ids)

    def test_calculate_variant_performance_empty(self, tmp_path):
        mem = PersistentMemory(tmp_path / "mem")
        perf = mem.calculate_variant_performance("v-nonexistent")
        assert perf == 0.0


# ---------------------------------------------------------------------------
# task_agent.py — TaskAgentState + TaskAgent
# ---------------------------------------------------------------------------


class TestTaskAgentState:
    def test_success_rate_zero_on_init(self):
        state = TaskAgentState()
        assert state.success_rate == 0.0

    def test_success_rate_calculation(self):
        state = TaskAgentState()
        state.total_tasks_executed = 10
        state.successful_tasks = 7
        assert abs(state.success_rate - 0.7) < 1e-9


class TestTaskAgentConfig:
    def test_defaults(self):
        cfg = TaskAgentConfig()
        assert cfg.max_execution_time == 3600
        assert cfg.sandbox_enabled is True
        assert cfg.gpu_enabled is False


class TestTaskAgent:
    def test_init_with_config(self, tmp_path):
        ta_cfg = TaskAgentConfig(code_path=tmp_path / "agent.py")
        cfg = MagicMock()
        agent = TaskAgent(config=cfg, task_agent_config=ta_cfg)
        assert agent.state.variant_id == "v0"

    @pytest.mark.asyncio
    async def test_execute_raises_not_implemented(self, tmp_path):
        ta_cfg = TaskAgentConfig()
        cfg = MagicMock()
        agent = TaskAgent(config=cfg, task_agent_config=ta_cfg)
        with pytest.raises(NotImplementedError):
            await agent._execute_task_code("some task")

    @pytest.mark.asyncio
    async def test_execute_returns_task_result(self, tmp_path):
        """execute() should return a TaskResult even when _execute_task_code raises."""
        ta_cfg = TaskAgentConfig()
        cfg = MagicMock()
        agent = TaskAgent(config=cfg, task_agent_config=ta_cfg)
        result = await agent.execute("do work")
        # Should fail gracefully since _execute_task_code is NotImplementedError
        assert isinstance(result, TaskResult)
        assert result.success is False


# ---------------------------------------------------------------------------
# meta_agent.py — MetaAgentState + MetaAgent
# ---------------------------------------------------------------------------


class TestMetaAgentState:
    def test_defaults(self):
        state = MetaAgentState()
        assert state.variant_id == "v0"
        assert state.total_modifications == 0
        assert state.metacognitive_improvements == 0


class TestModificationResult:
    def test_to_dict(self):
        result = ModificationResult(
            modification_id="mod-1",
            target="task_agent",
            code_diff="--- a\n+++ b",
            description="Speed up loop",
            expected_benefit="10%",
            confidence=0.75,
        )
        d = result.to_dict()
        assert d["modification_id"] == "mod-1"
        assert d["target"] == "task_agent"
        assert d["confidence"] == 0.75


class TestMetaAgent:
    def test_init(self, tmp_path):
        cfg = MagicMock()
        agent = MetaAgent(config=cfg)
        assert agent.state.variant_id == "v0"

    def test_generate_error_handling_improvement_raises(self, tmp_path):
        cfg = MagicMock()
        agent = MetaAgent(config=cfg)
        with pytest.raises(NotImplementedError):
            agent._generate_error_handling_improvement("some code")

    def test_generate_performance_optimization_raises(self, tmp_path):
        cfg = MagicMock()
        agent = MetaAgent(config=cfg)
        with pytest.raises(NotImplementedError):
            agent._generate_performance_optimization("some code")

    def test_generate_meta_improvement_raises(self, tmp_path):
        cfg = MagicMock()
        agent = MetaAgent(config=cfg)
        with pytest.raises(NotImplementedError):
            agent._generate_meta_improvement()


# ---------------------------------------------------------------------------
# Tracing integration smoke test (pipeline/tracing.py)
# ---------------------------------------------------------------------------


def test_tracing_new_trace_returns_id():
    from berb.pipeline import tracing
    trace_id = tracing.new_trace("run-123")
    assert trace_id == "run-123"


def test_tracing_span_records_duration(tmp_path):
    from berb.pipeline import tracing
    tracing.configure(tmp_path)
    trace_id = tracing.new_trace()
    with tracing.span(trace_id, "test.op", component="test") as s:
        s.set_tag("key", "val")
    records = tracing.get_trace(trace_id)
    assert len(records) == 1
    r = records[0]
    assert r.name == "test.op"
    assert r.status == "ok"
    assert r.duration_ms >= 0
    assert r.tags["component"] == "test"
    assert r.tags["key"] == "val"


def test_tracing_span_captures_error(tmp_path):
    from berb.pipeline import tracing
    tracing.configure(tmp_path)
    trace_id = tracing.new_trace()
    try:
        with tracing.span(trace_id, "failing.op") as s:
            raise ValueError("intentional")
    except ValueError:
        pass
    records = tracing.get_trace(trace_id)
    assert records[0].status == "error"
    assert "ValueError" in (records[0].error or "")


def test_tracing_writes_jsonl(tmp_path):
    import json
    from berb.pipeline import tracing
    tracing.configure(tmp_path)
    trace_id = tracing.new_trace("file-test")
    with tracing.span(trace_id, "write.op"):
        pass
    trace_file = tmp_path / "file-test" / "trace.jsonl"
    assert trace_file.exists()
    lines = trace_file.read_text().strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["name"] == "write.op"


def test_tracing_get_trace_empty():
    from berb.pipeline import tracing
    records = tracing.get_trace("nonexistent-trace-xyz")
    assert records == []
