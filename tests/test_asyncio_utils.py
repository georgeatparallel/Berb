"""Tests for async pipeline utilities — concurrency logging and checkpoint wiring."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from berb.pipeline.asyncio_utils import CheckpointManager
from berb.pipeline.stages import Stage


@pytest.mark.asyncio
async def test_checkpoint_manager_write_does_not_block_event_loop() -> None:
    """CheckpointManager.write can be called from async context without blocking."""
    import tempfile

    cm = CheckpointManager()

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)

        # Calling the sync write from async context should not raise
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, cm.write, run_dir, Stage.TOPIC_INIT, "test-cm")

        assert (run_dir / "checkpoint.json").exists()


@pytest.mark.asyncio
async def test_gather_stages_empty_returns_empty() -> None:
    """Gathering zero stages returns empty list."""
    from unittest.mock import MagicMock

    from berb.pipeline.asyncio_utils import gather_stages

    config = MagicMock()
    adapters = MagicMock()

    results = await gather_stages(
        [],
        run_dir=Path("/tmp"),
        run_id="empty-test",
        config=config,
        adapters=adapters,
    )
    assert results == []


@pytest.mark.asyncio
async def test_checkpoint_manager_read_serialization() -> None:
    """Concurrent reads from CheckpointManager don't raise."""
    import json
    import tempfile

    cm = CheckpointManager()

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cm.write(run_dir, Stage.SEARCH_STRATEGY, "read-test")

        async def reader() -> bool:
            data = json.loads((run_dir / "checkpoint.json").read_text())
            return data["last_completed_stage"] == 3  # SEARCH_STRATEGY = 3

        results = await asyncio.gather(*[reader() for _ in range(5)])
        assert all(results)
