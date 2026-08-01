"""Per-run cost and token accounting for Berb.

Thread-safe, process-safe accumulator that attributes LLM cost per run,
per stage, per phase, and per node. Populated at the single lowest choke
point in LLMClient where every provider response is normalized.

Usage:
    tracker = CostTracker()
    tracker.record(CostEvent(
        stage=12,
        phase="baseline",
        node_id="abc-123",
        model="openai/gpt-4o-mini",
        provider="openai",
        prompt_tokens=500,
        completion_tokens=200,
        cost_usd=0.0015,
        purpose="codegen",
    ))
    print(tracker.total_usd())
    print(tracker.by_stage())
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .pricing import PricingTable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CostEvent:
    """A single cost-tracking event.

    Attributes:
        timestamp: When the event occurred
        stage: Pipeline stage (None if not stage-attributable)
        phase: Research phase ("baseline", "tuning", "creative", "ablation")
        node_id: Journal node ID this cost is attributed to
        model: Full model identifier (e.g. "openai/gpt-4o-mini")
        provider: Provider name (e.g. "openai", "anthropic")
        prompt_tokens: Input token count
        completion_tokens: Output token count
        cost_usd: Calculated cost in USD
        purpose: Purpose category ("codegen", "feedback", "vlm", "review", "writeup", "other")
    """

    timestamp: datetime
    stage: int | None = None
    phase: str | None = None
    node_id: str | None = None
    model: str = "unknown"
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    purpose: str = "other"


class CostTracker:
    """Thread-safe, process-safe accumulator for per-run LLM cost accounting.

    Thread-safety is provided by a reentrant lock. Process-safety is NOT
    provided by default — use a shared file or database for multi-process
    scenarios (future work).

    Populated at the lowest choke point in LLMClient so every provider
    response is captured exactly once.
    """

    def __init__(self, pricing_path: Path | str | None = None) -> None:
        """Initialize cost tracker.

        Args:
            pricing_path: Optional path to pricing.yaml. Uses built-in
                pricing table if None.
        """
        self._lock = threading.RLock()
        self._events: list[CostEvent] = []
        self._pricing = PricingTable(pricing_path)
        self._closed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Recording
    # ─────────────────────────────────────────────────────────────────────────

    def record(self, event: CostEvent) -> None:
        """Record a cost event.

        Thread-safe.

        Args:
            event: The cost event to record.
        """
        with self._lock:
            if self._closed:
                logger.warning("Attempted to record cost event on closed tracker")
                return
            self._events.append(event)

    def record_from_llm_response(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        stage: int | None = None,
        phase: str | None = None,
        node_id: str | None = None,
        purpose: str = "other",
    ) -> CostEvent:
        """Convenience: build and record a CostEvent from LLM usage stats.

        Computes cost from the pricing table. Unknown models are recorded
        with cost_usd=0.0 and a warning is emitted.

        Args:
            model: Full model identifier
            prompt_tokens: Input token count
            completion_tokens: Output token count
            stage: Optional pipeline stage
            phase: Optional research phase
            node_id: Optional journal node ID
            purpose: Purpose category

        Returns:
            The recorded CostEvent.
        """
        cost_usd = self._pricing.compute_cost(model, prompt_tokens, completion_tokens)

        if cost_usd is None:
            logger.warning(
                "pricing_unknown: model=%r has no pricing entry; cost set to 0.0",
                model,
            )
            cost_usd = 0.0

        event = CostEvent(
            timestamp=datetime.now(UTC),
            stage=stage,
            phase=phase,
            node_id=node_id,
            model=model,
            provider=model.split("/")[0] if "/" in model else "unknown",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            purpose=purpose,
        )
        self.record(event)
        return event

    # ─────────────────────────────────────────────────────────────────────────
    # Aggregation
    # ─────────────────────────────────────────────────────────────────────────

    def total_usd(self) -> float:
        """Total cost across all events."""
        with self._lock:
            return sum(e.cost_usd for e in self._events)

    def total_tokens(self) -> int:
        """Total tokens across all events."""
        with self._lock:
            return sum(e.prompt_tokens + e.completion_tokens for e in self._events)

    def by_stage(self) -> dict[int, float]:
        """Cost breakdown by pipeline stage."""
        with self._lock:
            result: dict[int, float] = {}
            for e in self._events:
                if e.stage is not None:
                    result[e.stage] = result.get(e.stage, 0.0) + e.cost_usd
            return result

    def by_purpose(self) -> dict[str, float]:
        """Cost breakdown by purpose category."""
        with self._lock:
            result: dict[str, float] = {}
            for e in self._events:
                result[e.purpose] = result.get(e.purpose, 0.0) + e.cost_usd
            return result

    def by_phase(self) -> dict[str, float]:
        """Cost breakdown by research phase."""
        with self._lock:
            result: dict[str, float] = {}
            for e in self._events:
                if e.phase is not None:
                    result[e.phase] = result.get(e.phase, 0.0) + e.cost_usd
            return result

    def by_node(self) -> dict[str, float]:
        """Cost breakdown by journal node."""
        with self._lock:
            result: dict[str, float] = {}
            for e in self._events:
                if e.node_id is not None:
                    result[e.node_id] = result.get(e.node_id, 0.0) + e.cost_usd
            return result

    def events_by_stage(self, stage: int) -> list[CostEvent]:
        """All events for a given stage."""
        with self._lock:
            return [e for e in self._events if e.stage == stage]

    # ─────────────────────────────────────────────────────────────────────────
    # Reporting
    # ─────────────────────────────────────────────────────────────────────────

    def to_report(self) -> dict[str, Any]:
        """Serialize all cost data to a dictionary for cost_report.json."""
        with self._lock:
            return {
                "total_cost_usd": round(self.total_usd(), 6),
                "total_tokens": self.total_tokens(),
                "by_stage": {str(k): round(v, 6) for k, v in self.by_stage().items()},
                "by_purpose": {k: round(v, 6) for k, v in self.by_purpose().items()},
                "by_phase": {k: round(v, 6) for k, v in self.by_phase().items()},
                "num_events": len(self._events),
                "pricing_version": self._pricing.version,
            }

    def reset(self) -> None:
        """Clear all recorded events."""
        with self._lock:
            self._events.clear()

    def close(self) -> dict[str, Any]:
        """Close the tracker and return the final report.

        After close(), further record() calls are silently dropped.

        Returns:
            The final cost report dictionary.
        """
        with self._lock:
            self._closed = True
            return self.to_report()

    def __enter__(self) -> CostTracker:
        """Context manager support."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Close on context exit."""
        self.close()


# Module-level global tracker
_tracker: CostTracker | None = None
_tracker_lock = threading.RLock()


def get_cost_tracker(pricing_path: Path | str | None = None) -> CostTracker:
    """Get or create the module-level singleton cost tracker.

    Args:
        pricing_path: Optional path to pricing.yaml.

    Returns:
        A shared CostTracker instance.
    """
    global _tracker
    with _tracker_lock:
        if _tracker is None or _tracker._closed:  # noqa: SLF001
            _tracker = CostTracker(pricing_path=pricing_path)
        return _tracker
