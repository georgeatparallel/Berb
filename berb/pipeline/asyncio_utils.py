"""Async wrapping infrastructure for the pipeline executor.

Wraps synchronous stage implementations so the async DAG executor can run
them via ``asyncio.to_thread()`` without modifying stage function signatures.
Independent stages can then run concurrently via ``asyncio.gather()``.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from pathlib import Path

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.pipeline.checkpoint import CheckpointManager, write_heartbeat
from berb.pipeline.executor import StageResult, execute_stage
from berb.pipeline.stages import Stage, StageStatus

logger = logging.getLogger(__name__)


async def run_sync_stage(
    stage: Stage,
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    auto_approve_gates: bool = False,
) -> StageResult:
    """Run a synchronous stage implementation in a thread pool.

    Uses ``asyncio.to_thread()`` which runs the function in the default
    executor, preventing the blocking call from stalling the event loop.
    """
    return await asyncio.to_thread(
        execute_stage,
        stage,
        run_dir=run_dir,
        run_id=run_id,
        config=config,
        adapters=adapters,
        auto_approve_gates=auto_approve_gates,
    )


async def gather_stages(
    stages: list[Stage],
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    checkpoint_mgr: CheckpointManager | None = None,
    auto_approve_gates: bool = False,
) -> list[StageResult]:
    """Run multiple independent stages concurrently.

    Args:
        stages: List of stages to run (must have no unmet dependencies).
        checkpoint_mgr: If provided, uses serialized checkpoint writes.

    Returns:
        List of StageResult in the same order as *stages*.
    """
    if len(stages) == 0:
        return []
    if len(stages) == 1:
        # Single stage — no need for gather overhead
        return [
            await _run_and_checkpoint(
                stages[0],
                run_dir=run_dir,
                run_id=run_id,
                config=config,
                adapters=adapters,
                checkpoint_mgr=checkpoint_mgr,
                auto_approve_gates=auto_approve_gates,
            )
        ]

    # Log concurrency for verification (Step 7f acceptance criterion)
    names = ", ".join(s.name for s in stages)
    logger.info(
        "CONCURRENT: running %d stages together: %s",
        len(stages),
        names,
    )

    async def _run_one(stage: Stage) -> StageResult:
        return await _run_and_checkpoint(
            stage,
            run_dir=run_dir,
            run_id=run_id,
            config=config,
            adapters=adapters,
            checkpoint_mgr=checkpoint_mgr,
            auto_approve_gates=auto_approve_gates,
        )

    return await asyncio.gather(*[_run_one(s) for s in stages])


async def _run_and_checkpoint(
    stage: Stage,
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    checkpoint_mgr: CheckpointManager | None = None,
    auto_approve_gates: bool = False,
) -> StageResult:
    """Run a single stage and write checkpoint if it succeeds."""
    t0 = _time.monotonic()
    result = await asyncio.to_thread(
        execute_stage,
        stage,
        run_dir=run_dir,
        run_id=run_id,
        config=config,
        adapters=adapters,
        auto_approve_gates=auto_approve_gates,
    )
    elapsed = _time.monotonic() - t0
    logger.debug("Stage %s finished in %.2fs (status=%s)", stage, elapsed, result.status)

    if result.status == StageStatus.DONE:
        if checkpoint_mgr:
            checkpoint_mgr.write(run_dir, stage, run_id)
        else:
            # Fallback: direct write
            from berb.pipeline.checkpoint import write_checkpoint

            write_checkpoint(run_dir, stage, run_id)

    # Heartbeat is lightweight — always write directly
    write_heartbeat(run_dir, stage, run_id)

    return result
