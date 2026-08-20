"""23-stage Berb pipeline state machine with Event Sourcing.

Defines the stage sequence, status transitions, gate logic, and rollback rules.
Migrated from arc/state_machine.py (19 stages) with the following changes:
  - SEARCH_PLAN + SOURCE_CONNECT -> SEARCH_STRATEGY
  - RELEVANCE_SCREEN + QUALITY_SCREEN -> LITERATURE_SCREEN
  - CLUSTER_TOPICS + GAP_ANALYSIS -> SYNTHESIS
  - EXPERIMENT_DESIGN split -> EXPERIMENT_DESIGN + CODE_GENERATION
  - EXECUTE split -> EXPERIMENT_RUN + ITERATIVE_REFINE
  - WRITE_DRAFT split -> PAPER_OUTLINE + PAPER_DRAFT
  - Added PAPER_REVISION, QUALITY_GATE, EXPORT_PUBLISH
  - RETROSPECTIVE_ARCHIVE split -> KNOWLEDGE_ARCHIVE (+ QUALITY_GATE + EXPORT_PUBLISH)

P0 2026-04-02: Added Event Sourcing for debugging, audit trails, and state recovery.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any


class Stage(IntEnum):
    """23-stage research pipeline."""

    # Phase A: Research Scoping
    TOPIC_INIT = 1
    PROBLEM_DECOMPOSE = 2

    # Phase B: Literature Discovery
    SEARCH_STRATEGY = 3
    LITERATURE_COLLECT = 4
    LITERATURE_SCREEN = 5  # GATE
    KNOWLEDGE_EXTRACT = 6

    # Phase C: Knowledge Synthesis
    SYNTHESIS = 7
    HYPOTHESIS_GEN = 8

    # Phase D: Experiment Design
    EXPERIMENT_DESIGN = 9  # GATE
    CODE_GENERATION = 10  # NEW
    RESOURCE_PLANNING = 11

    # Phase E: Experiment Execution
    EXPERIMENT_RUN = 12
    ITERATIVE_REFINE = 13  # NEW

    # Phase F: Analysis & Decision
    RESULT_ANALYSIS = 14
    RESEARCH_DECISION = 15

    # Phase G: Paper Writing
    PAPER_OUTLINE = 16
    PAPER_DRAFT = 17
    PEER_REVIEW = 18
    PAPER_REVISION = 19  # NEW

    # Phase H: Finalization
    QUALITY_GATE = 20  # GATE
    KNOWLEDGE_ARCHIVE = 21
    EXPORT_PUBLISH = 22
    CITATION_VERIFY = 23


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED_APPROVAL = "blocked_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAUSED = "paused"
    RETRYING = "retrying"
    FAILED = "failed"
    DONE = "done"


class TransitionEvent(StrEnum):
    START = "start"
    SUCCEED = "succeed"
    APPROVE = "approve"
    REJECT = "reject"
    TIMEOUT = "timeout"
    FAIL = "fail"
    RETRY = "retry"
    RESUME = "resume"
    PAUSE = "pause"


# ---------------------------------------------------------------------------
# Stage navigation
# ---------------------------------------------------------------------------

# STAGE_SEQUENCE, NEXT_STAGE, PREVIOUS_STAGE removed in Phase 3.
# Stage order is now computed dynamically from StageContract.depends_on
# via berb.pipeline.resolution.resolve_stage_order().

# ---------------------------------------------------------------------------
# Gate stages — require approval before proceeding
# ---------------------------------------------------------------------------

GATE_STAGES: frozenset[Stage] = frozenset(
    {
        Stage.LITERATURE_SCREEN,
        Stage.EXPERIMENT_DESIGN,
        Stage.QUALITY_GATE,
    }
)

# Gate rollback targets: when a gate rejects, where to roll back
GATE_ROLLBACK: dict[Stage, Stage] = {
    Stage.LITERATURE_SCREEN: Stage.LITERATURE_COLLECT,  # reject -> re-collect
    Stage.EXPERIMENT_DESIGN: Stage.HYPOTHESIS_GEN,  # reject -> re-hypothesize
    Stage.QUALITY_GATE: Stage.PAPER_OUTLINE,  # reject -> rewrite paper
}

# ---------------------------------------------------------------------------
# Research decision rollback targets (PIVOT/REFINE from Stage 15)
# ---------------------------------------------------------------------------

DECISION_ROLLBACK: dict[str, Stage] = {
    "pivot": Stage.HYPOTHESIS_GEN,  # Discard hypotheses, re-generate
    "refine": Stage.ITERATIVE_REFINE,  # Keep hypotheses, re-run experiments
}

MAX_DECISION_PIVOTS: int = 2  # Prevent infinite loops

# ---------------------------------------------------------------------------
# Noncritical stages — can be skipped on failure without aborting pipeline
# ---------------------------------------------------------------------------

NONCRITICAL_STAGES: frozenset[Stage] = frozenset(
    {
        Stage.QUALITY_GATE,  # 20: low quality should warn, not block deliverables
        Stage.KNOWLEDGE_ARCHIVE,  # 21: archival doesn't affect paper output
        # T3.4: CITATION_VERIFY removed — hallucinated citations MUST block export
    }
)

# ---------------------------------------------------------------------------
# Phase groupings (for UI and reporting)
# ---------------------------------------------------------------------------

PHASE_MAP: dict[str, tuple[Stage, ...]] = {
    "A: Research Scoping": (Stage.TOPIC_INIT, Stage.PROBLEM_DECOMPOSE),
    "B: Literature Discovery": (
        Stage.SEARCH_STRATEGY,
        Stage.LITERATURE_COLLECT,
        Stage.LITERATURE_SCREEN,
        Stage.KNOWLEDGE_EXTRACT,
    ),
    "C: Knowledge Synthesis": (Stage.SYNTHESIS, Stage.HYPOTHESIS_GEN),
    "D: Experiment Design": (
        Stage.EXPERIMENT_DESIGN,
        Stage.CODE_GENERATION,
        Stage.RESOURCE_PLANNING,
    ),
    "E: Experiment Execution": (Stage.EXPERIMENT_RUN, Stage.ITERATIVE_REFINE),
    "F: Analysis & Decision": (Stage.RESULT_ANALYSIS, Stage.RESEARCH_DECISION),
    "G: Paper Writing": (
        Stage.PAPER_OUTLINE,
        Stage.PAPER_DRAFT,
        Stage.PEER_REVIEW,
        Stage.PAPER_REVISION,
    ),
    "H: Finalization": (
        Stage.QUALITY_GATE,
        Stage.KNOWLEDGE_ARCHIVE,
        Stage.EXPORT_PUBLISH,
        Stage.CITATION_VERIFY,
    ),
}

# Reverse index of PHASE_MAP, built once at import.
_STAGE_TO_PHASE: dict[Stage, str] = {
    stage: phase for phase, stages in PHASE_MAP.items() for stage in stages
}


def phase_of(stage: Stage) -> str:
    """Return the phase label containing *stage* (e.g. ``"F: Analysis & Decision"``)."""
    return _STAGE_TO_PHASE[stage]


# ---------------------------------------------------------------------------
# Transition logic
# ---------------------------------------------------------------------------

TRANSITION_MAP: dict[StageStatus, frozenset[StageStatus]] = {
    StageStatus.PENDING: frozenset({StageStatus.RUNNING}),
    StageStatus.RUNNING: frozenset(
        {StageStatus.DONE, StageStatus.BLOCKED_APPROVAL, StageStatus.FAILED}
    ),
    StageStatus.BLOCKED_APPROVAL: frozenset(
        {StageStatus.APPROVED, StageStatus.REJECTED, StageStatus.PAUSED}
    ),
    StageStatus.APPROVED: frozenset({StageStatus.DONE}),
    StageStatus.REJECTED: frozenset({StageStatus.PENDING}),
    StageStatus.PAUSED: frozenset({StageStatus.RUNNING}),
    StageStatus.RETRYING: frozenset({StageStatus.RUNNING}),
    StageStatus.FAILED: frozenset({StageStatus.RETRYING, StageStatus.PAUSED}),
    StageStatus.DONE: frozenset(),
}


@dataclass(frozen=True)
class TransitionOutcome:
    stage: Stage
    status: StageStatus
    next_stage: Stage | None
    rollback_stage: Stage | None = None
    checkpoint_required: bool = False
    decision: str = "proceed"


def gate_required(
    stage: Stage,
    hitl_required_stages: Iterable[int] | None = None,
) -> bool:
    """Check whether a stage requires human-in-the-loop approval."""
    if stage not in GATE_STAGES:
        return False
    if hitl_required_stages is not None:
        return int(stage) in frozenset(hitl_required_stages)
    return True  # Default: all gate stages require approval


def default_rollback_stage(stage: Stage) -> Stage:
    """Return the configured rollback target, or the previous stage."""
    prev = Stage(int(stage) - 1) if int(stage) > 1 else stage
    return GATE_ROLLBACK.get(stage) or prev


def advance(
    stage: Stage,
    status: StageStatus,
    event: TransitionEvent | str,
    *,
    hitl_required_stages: Iterable[int] | None = None,
    rollback_stage: Stage | None = None,
) -> TransitionOutcome:
    """Compute the next state given current stage, status, and event.

    Raises ValueError on unsupported transitions.
    """
    event = TransitionEvent(event)
    target_rollback = rollback_stage or default_rollback_stage(stage)

    # START -> RUNNING
    if event is TransitionEvent.START and status in {
        StageStatus.PENDING,
        StageStatus.RETRYING,
        StageStatus.PAUSED,
    }:
        return TransitionOutcome(
            stage=stage, status=StageStatus.RUNNING, next_stage=stage
        )

    # SUCCEED while RUNNING
    if event is TransitionEvent.SUCCEED and status is StageStatus.RUNNING:
        if gate_required(stage, hitl_required_stages):
            return TransitionOutcome(
                stage=stage,
                status=StageStatus.BLOCKED_APPROVAL,
                next_stage=stage,
                checkpoint_required=False,
                decision="block",
            )
        next_s = Stage(int(stage) + 1) if int(stage) < 23 else None
        return TransitionOutcome(
            stage=stage,
            status=StageStatus.DONE,
            next_stage=next_s,
            checkpoint_required=True,
        )

    # APPROVE while BLOCKED
    if event is TransitionEvent.APPROVE and status is StageStatus.BLOCKED_APPROVAL:
        next_s = Stage(int(stage) + 1) if int(stage) < 23 else None
        return TransitionOutcome(
            stage=stage,
            status=StageStatus.DONE,
            next_stage=next_s,
            checkpoint_required=True,
        )

    # REJECT while BLOCKED -> rollback
    if event is TransitionEvent.REJECT and status is StageStatus.BLOCKED_APPROVAL:
        return TransitionOutcome(
            stage=target_rollback,
            status=StageStatus.PENDING,
            next_stage=target_rollback,
            rollback_stage=target_rollback,
            checkpoint_required=True,
            decision="pivot",
        )

    # TIMEOUT while BLOCKED -> pause
    if event is TransitionEvent.TIMEOUT and status is StageStatus.BLOCKED_APPROVAL:
        return TransitionOutcome(
            stage=stage,
            status=StageStatus.PAUSED,
            next_stage=stage,
            checkpoint_required=True,
            decision="block",
        )

    # FAIL while RUNNING
    if event is TransitionEvent.FAIL and status is StageStatus.RUNNING:
        return TransitionOutcome(
            stage=stage,
            status=StageStatus.FAILED,
            next_stage=stage,
            checkpoint_required=True,
            decision="retry",
        )

    # RETRY while FAILED
    if event is TransitionEvent.RETRY and status is StageStatus.FAILED:
        return TransitionOutcome(
            stage=stage,
            status=StageStatus.RETRYING,
            next_stage=stage,
            decision="retry",
        )

    # RESUME while PAUSED
    if event is TransitionEvent.RESUME and status is StageStatus.PAUSED:
        return TransitionOutcome(
            stage=stage, status=StageStatus.RUNNING, next_stage=stage
        )

    # PAUSE while FAILED
    if event is TransitionEvent.PAUSE and status is StageStatus.FAILED:
        return TransitionOutcome(
            stage=stage,
            status=StageStatus.PAUSED,
            next_stage=stage,
            checkpoint_required=True,
            decision="block",
        )

    raise ValueError(f"Unsupported transition: {event} from {status}")


# ============================================================================
# P0 2026-04-02: Event Sourcing Implementation
# ============================================================================


@dataclass(frozen=True)
class StageTransitionEvent:
    """Immutable event representing a stage transition.

    P0 2026-04-02: Event Sourcing for debugging, audit trails, and state recovery.

    Attributes:
        run_id: Unique run identifier
        from_stage: Stage before transition
        to_stage: Stage after transition
        from_status: Status before transition
        to_status: Status after transition
        event: Transition event that triggered this
        timestamp: When the transition occurred
        metadata: Additional context (error messages, decisions, etc.)
    """

    run_id: str
    from_stage: Stage
    to_stage: Stage
    from_status: StageStatus
    to_status: StageStatus
    event: TransitionEvent
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "from_stage": int(self.from_stage),
            "from_stage_name": self.from_stage.name,
            "to_stage": int(self.to_stage),
            "to_stage_name": self.to_stage.name,
            "from_status": self.from_status.value,
            "to_status": self.to_status.value,
            "event": self.event.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageTransitionEvent:
        """Reconstruct event from dictionary."""
        return cls(
            run_id=data["run_id"],
            from_stage=Stage(data["from_stage"]),
            to_stage=Stage(data["to_stage"]),
            from_status=StageStatus(data["from_status"]),
            to_status=StageStatus(data["to_status"]),
            event=TransitionEvent(data["event"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PipelineState:
    """Current state of the pipeline reconstructed from events.

    P0 2026-04-02: State derived from event log.
    """

    current_stage: Stage = Stage.TOPIC_INIT
    current_status: StageStatus = StageStatus.PENDING
    pivot_count: int = 0
    retry_count: int = 0
    last_error: str | None = None
    artifacts: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)

    def apply(self, event: StageTransitionEvent) -> None:
        """Apply event to update state."""
        self.current_stage = event.to_stage
        self.current_status = event.to_status

        if event.metadata.get("decision") == "pivot":
            self.pivot_count += 1
        elif event.metadata.get("decision") == "retry":
            self.retry_count += 1

        if event.metadata.get("error"):
            self.last_error = event.metadata["error"]

        if event.metadata.get("artifacts"):
            self.artifacts.extend(event.metadata["artifacts"])

        if event.metadata.get("decision"):
            self.decisions.append(event.metadata["decision"])


class EventStore:
    """Append-only event store for pipeline transitions.

    P0 2026-04-02: Enables debugging, audit trails, and state recovery.

    Features:
    - Append-only event log (immutable events)
    - State reconstruction via replay
    - Persistent storage to disk
    - Event filtering and querying

    Usage:
        store = EventStore(run_id="rc-123")
        store.append(StageTransitionEvent(...))
        state = store.replay()  # Rebuild current state
    """

    def __init__(self, run_id: str, storage_path: str | None = None):
        """Initialize event store.

        Args:
            run_id: Unique run identifier
            storage_path: Path for persistent storage (optional)
        """
        self.run_id = run_id
        self.storage_path = storage_path
        self._events: list[StageTransitionEvent] = []

        # Load existing events from disk if available
        if storage_path:
            self._load_from_disk()

    def append(self, event: StageTransitionEvent) -> None:
        """Append event to the log (immutable).

        Args:
            event: Transition event to append
        """
        self._events.append(event)

        # Persist to disk after each append (could batch for performance)
        if self.storage_path:
            self._save_to_disk()

    def replay(self) -> PipelineState:
        """Rebuild current state from all events.

        Returns:
            Current pipeline state
        """
        state = PipelineState()
        for event in self._events:
            state.apply(event)
        return state

    def get_events(
        self,
        from_stage: Stage | None = None,
        to_stage: Stage | None = None,
        event_type: TransitionEvent | None = None,
    ) -> list[StageTransitionEvent]:
        """Query events with optional filters.

        Args:
            from_stage: Filter by source stage
            to_stage: Filter by target stage
            event_type: Filter by event type

        Returns:
            Matching events
        """
        events = self._events

        if from_stage is not None:
            events = [e for e in events if e.from_stage == from_stage]
        if to_stage is not None:
            events = [e for e in events if e.to_stage == to_stage]
        if event_type is not None:
            events = [e for e in events if e.event == event_type]

        return events

    def get_last_n_events(self, n: int) -> list[StageTransitionEvent]:
        """Get last N events.

        Args:
            n: Number of events

        Returns:
            Last N events
        """
        return self._events[-n:] if n < len(self._events) else self._events

    def _save_to_disk(self) -> None:
        """Persist events to disk."""
        import json
        from pathlib import Path

        self_path = self.storage_path
        path = Path(self_path) if self_path else Path("event_log.json")
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "run_id": self.run_id,
            "event_count": len(self._events),
            "events": [e.to_dict() for e in self._events],
        }

        # Write atomically via temp file
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        # Windows: remove existing file before rename
        if path.exists():
            path.unlink()
        temp_path.rename(path)

    def _load_from_disk(self) -> None:
        """Load events from disk."""
        import json
        from pathlib import Path

        self_path = self.storage_path
        path = Path(self_path) if self_path else Path("event_log.json")
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._events = [
                StageTransitionEvent.from_dict(e) for e in data.get("events", [])
            ]
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupted file - start fresh
            self._events = []


def _raise_unsupported_transition(
    status: StageStatus, event: TransitionEvent, stage: Stage
) -> None:
    """Raise error for unsupported transition."""
    raise ValueError(
        f"Unsupported transition: {status.value} + {event.value} for stage {int(stage)}"
    )
