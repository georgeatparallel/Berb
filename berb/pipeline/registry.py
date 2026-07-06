"""Plugin stage registry — decorator-based stage registration.

Replaces the hardcoded ``_STAGE_EXECUTORS`` dict in executor.py and
eliminates the need to edit executor.py or contracts.py when adding
a new pipeline stage.

Usage:
    from berb.pipeline.registry import register_stage, get_all_registrations
    from berb.pipeline.stages import Stage
    from berb.pipeline.contracts import StageContract

    @register_stage(
        stage=Stage.BIBLIOGRAPHY_FORMAT,
        depends_on={Stage.CITATION_VERIFY},
        contract=StageContract(
            input_files=("verified_citations.json",),
            output_files=("bibliography.bib",),
            dod="Formatted bibliography in target venue style",
            error_code="E24_BIBLIOGRAPHY_FAIL",
        ),
    )
    async def execute_bibliography_format(...) -> StageResult:
        ...

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from berb.pipeline.contracts import StageContract
from berb.pipeline.stages import Stage


@dataclass
class StageRegistration:
    """Registration record for a single pipeline stage implementation."""

    stage: Stage
    fn: Callable[..., Any]
    depends_on: frozenset[Stage] = frozenset()
    contract: StageContract | None = None


# Module-level registry — populated by the @register_stage decorator
_registry: dict[Stage, StageRegistration] = {}


def register_stage(
    stage: Stage,
    depends_on: frozenset[Stage] = frozenset(),
    contract: StageContract | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that registers a function as a pipeline stage implementation.

    Args:
        stage: The Stage enum member this function implements.
        depends_on: Stages that must complete before this one runs.
        contract: Optional StageContract (can derive from contracts.py).

    Returns:
        The original function (unchanged — decorator only registers metadata).
    """
    registration = StageRegistration(
        stage=stage,
        fn=None,  # type: ignore[arg-type]
        depends_on=depends_on,
        contract=contract,
    )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        registration.fn = fn
        if stage in _registry:
            # Overwrite existing registration (idempotent for reloading)
            pass
        _registry[stage] = registration
        return fn

    return decorator


def get_all_registrations() -> dict[Stage, StageRegistration]:
    """Return all registered stage implementations."""
    return dict(_registry)


def get_registration(stage: Stage) -> StageRegistration | None:
    """Return the registration for a specific stage, or None."""
    return _registry.get(stage)


def clear_registry() -> None:
    """Clear all registrations (useful for testing)."""
    _registry.clear()
