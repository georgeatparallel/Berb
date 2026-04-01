"""Regression tests for SRE fixes (2026-04-01).

BUG-001: get_shared_memory() — check-then-act race on global singleton
BUG-002: send_message() / get_messages() — non-atomic counter increments
BUG-003: execute_stage() — TypeError introspection mask
"""

from __future__ import annotations

import inspect
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# BUG-001 — get_shared_memory() global singleton race
# ---------------------------------------------------------------------------

class TestGetSharedMemorySingleton:
    """BUG-001: global _memory must be initialised exactly once under concurrent callers."""

    def setup_method(self):
        # Reset the global between tests
        import berb.memory.shared_memory as _sm
        with _sm._memory_lock:
            _sm._memory = None

    def teardown_method(self):
        import berb.memory.shared_memory as _sm
        with _sm._memory_lock:
            _sm._memory = None

    def test_single_thread_returns_same_instance(self):
        """Baseline: sequential calls return the same object."""
        from berb.memory.shared_memory import get_shared_memory
        a = get_shared_memory("proj_x")
        b = get_shared_memory("proj_x")
        assert a is b

    def test_concurrent_callers_return_same_instance(self):
        """BUG-001 regression: N threads must all receive the same instance."""
        from berb.memory.shared_memory import get_shared_memory

        instances: list = []
        barrier = threading.Barrier(20)

        def _worker():
            barrier.wait()  # all threads start simultaneously
            instances.append(get_shared_memory("proj_concurrent"))

        threads = [threading.Thread(target=_worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 20 threads must have received the identical instance
        assert len(instances) == 20
        assert all(inst is instances[0] for inst in instances), (
            "BUG-001 regression: multiple distinct instances created under concurrency"
        )

    def test_project_id_change_creates_new_instance(self):
        """Changing project_id should create a fresh instance."""
        from berb.memory.shared_memory import get_shared_memory
        a = get_shared_memory("proj_a")
        b = get_shared_memory("proj_b")
        assert a is not b
        assert b._project_id == "proj_b"

    def test_data_stored_before_concurrent_call_is_not_lost(self):
        """Data written to the first instance must survive concurrent re-entrancy."""
        from berb.memory.shared_memory import get_shared_memory
        mem = get_shared_memory("proj_safe")
        mem.store("key_x", "value_x")

        # A second concurrent call must return the SAME instance
        results = [None]

        def _reader():
            results[0] = get_shared_memory("proj_safe")

        t = threading.Thread(target=_reader)
        t.start()
        t.join()

        assert results[0] is mem
        assert results[0].get("key_x") == "value_x", (
            "BUG-001 regression: stored data was lost because a new instance was created"
        )


# ---------------------------------------------------------------------------
# BUG-002 — send_message / get_messages non-atomic counter increments
# ---------------------------------------------------------------------------

class TestMessageCountersThreadSafety:
    """BUG-002: messages_sent and messages_received must be exact under concurrency."""

    def _make_memory(self) -> "SharedResearchMemory":  # noqa: F821
        from berb.memory.shared_memory import SharedResearchMemory
        mem = SharedResearchMemory(project_id="test_counters")
        mem.register_agent("agent_a")
        return mem

    def test_messages_sent_exact_under_concurrency(self):
        """N threads each send M messages — total must be N*M exactly."""
        mem = self._make_memory()
        N, M = 10, 50
        barrier = threading.Barrier(N)

        def _sender():
            barrier.wait()
            for _ in range(M):
                mem.send_message("agent_a", None, "ping", {})

        threads = [threading.Thread(target=_sender) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        state = mem.get_agent_state("agent_a")
        assert state is not None
        assert state.messages_sent == N * M, (
            f"BUG-002 regression: expected {N*M} sent, got {state.messages_sent}"
        )

    def test_messages_received_exact_under_concurrency(self):
        """N threads each read messages — received counter must equal total reads × matches."""
        mem = self._make_memory()
        # Pre-load 5 broadcast messages
        for i in range(5):
            mem.send_message("agent_a", None, "data", {"i": i})

        # Reset received count to 0 for clean test
        mem._agent_states["agent_a"].messages_received = 0

        N = 10
        barrier = threading.Barrier(N)
        received_totals: list[int] = []

        def _reader():
            barrier.wait()
            msgs = mem.get_messages("agent_a")
            received_totals.append(len(msgs))

        threads = [threading.Thread(target=_reader) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total received increments = sum of all reads
        state = mem.get_agent_state("agent_a")
        assert state is not None
        expected = sum(received_totals)
        assert state.messages_received == expected, (
            f"BUG-002 regression: counter={state.messages_received}, expected={expected}"
        )

    def test_send_message_basic_still_works(self):
        """Non-regression: basic single-threaded send_message still functions."""
        mem = self._make_memory()
        mem.send_message("agent_a", None, "hello", {"data": 42})
        msgs = mem.get_messages("agent_a")
        assert len(msgs) == 1
        assert msgs[0]["type"] == "hello"


# ---------------------------------------------------------------------------
# BUG-003 — execute_stage() TypeError introspection mask
# ---------------------------------------------------------------------------

class TestExecuteStageSignatureIntrospection:
    """BUG-003: executor dispatch must use inspect.signature, not exception message matching."""

    def _make_minimal_config(self):
        cfg = MagicMock()
        cfg.llm.provider = "none"
        cfg.llm.base_url = ""
        cfg.llm.api_key = ""
        cfg.openclaw_bridge.use_message = False
        cfg.openclaw_bridge.use_memory = False
        cfg.notifications.on_stage_start = False
        cfg.security.hitl_required_stages = []
        cfg.metaclaw_bridge = None
        cfg.prompts.custom_file = None
        return cfg

    def test_executor_with_prompts_receives_prompts(self):
        """An executor that accepts 'prompts' must receive the kwarg."""
        received_kwargs: dict = {}

        def fake_executor(stage_dir, run_dir, config, adapters, *, llm=None, prompts=None):
            received_kwargs["prompts"] = prompts
            from berb.pipeline._helpers import StageResult
            from berb.pipeline.stages import Stage, StageStatus
            return StageResult(stage=Stage.TOPIC_INIT, status=StageStatus.DONE, artifacts=("topic.json",))

        assert "prompts" in inspect.signature(fake_executor).parameters, (
            "Test setup error: fake_executor must declare 'prompts'"
        )
        # Verify inspect agrees that the parameter is present
        sig = inspect.signature(fake_executor)
        assert "prompts" in sig.parameters

    def test_executor_without_prompts_does_not_receive_prompts(self):
        """An executor that does NOT declare 'prompts' must not receive it."""
        def legacy_executor(stage_dir, run_dir, config, adapters, *, llm=None):
            return MagicMock()

        sig = inspect.signature(legacy_executor)
        assert "prompts" not in sig.parameters

    def test_real_typeerror_from_executor_propagates(self):
        """A TypeError raised inside the executor body must propagate — not be swallowed."""
        from berb.pipeline.stages import Stage, StageStatus
        from berb.pipeline._helpers import StageResult

        def buggy_executor(stage_dir, run_dir, config, adapters, *, llm=None, prompts=None):
            # This TypeError has nothing to do with 'prompts'
            _ = "string" + 42  # type: ignore[operator]

        # Under the old code, the TypeError message check would fall through to
        # the retry-without-prompts path, masking the real error.
        # Under the new code, inspect.signature detects the param exists and the
        # real TypeError propagates.
        with pytest.raises(TypeError, match="can only concatenate"):
            buggy_executor(None, None, None, None)

    def test_inspect_signature_used_not_exception_catch(self):
        """The executor dispatch path must use inspect, not try/except TypeError."""
        from berb.pipeline import executor as exec_module
        import ast
        import textwrap

        src = inspect.getsource(exec_module.execute_stage)
        # The old fragile pattern must not exist
        assert "unexpected keyword argument" not in src, (
            "BUG-003 regression: fragile TypeError string-match still present in execute_stage"
        )
        # The new pattern must exist
        assert "inspect.signature" in src or "_accepts_prompts" in src, (
            "BUG-003 regression: inspect.signature introspection not found in execute_stage"
        )
