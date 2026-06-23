"""Shared context for pipeline execution modules.

Carries the common state that every runner sub-module needs,
replacing ad-hoc parameter tuples across function boundaries.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from berb.adapters import AdapterBundle
from berb.config import RCConfig
from berb.pipeline.stages import EventStore


@dataclass(frozen=True)
class PipelineContext:
    """Immutable shared state for pipeline execution.

    Created once per `execute_pipeline()` call and passed to every
    extracted sub-module instead of individual (run_dir, run_id,
    config, adapters, event_store) arguments.
    """

    run_dir: Path
    run_id: str
    config: RCConfig
    adapters: AdapterBundle
    event_store: EventStore | None = None
