"""Operation modes for Berb research pipeline.

This module defines the two fundamental operation modes:
- Autonomous: Zero human intervention, full pipeline execution
- Collaborative: Human-in-the-loop at configurable decision points

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class OperationMode(str, Enum):
    """Operation mode for the research pipeline.

    Attributes:
        AUTONOMOUS: Zero human intervention, full pipeline execution
        COLLABORATIVE: Human-in-the-loop at configurable decision points
    """

    AUTONOMOUS = "autonomous"
    COLLABORATIVE = "collaborative"


class FeedbackAction(str, Enum):
    """Actions available in collaborative mode.

    Attributes:
        APPROVE: Approve current stage output and continue
        EDIT: Provide feedback to modify output
        REJECT: Reject output and request regeneration
        SKIP: Skip this stage entirely
        ADD_HYPOTHESIS: Add additional hypotheses (Stage 8 only)
        OVERRIDE: Override experiment parameters (Stage 9 only)
    """

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    SKIP = "skip"
    ADD_HYPOTHESIS = "add_hypothesis"
    OVERRIDE = "override"


class CollaborativeConfig(BaseModel):
    """Configuration for collaborative mode checkpoints.

    Attributes:
        pause_after_stages: List of stage numbers to pause after (default: [2, 6, 8, 9, 15, 18])
        approval_timeout_minutes: Timeout for human approval in minutes
        feedback_format: Format for presenting feedback options (cli/json/api)
        allow_stage_skip: Whether to allow skipping stages
        allow_hypothesis_edit: Whether to allow editing hypotheses at Stage 8
        allow_experiment_override: Whether to override experiment parameters at Stage 9
    """

    pause_after_stages: list[int] = Field(
        default=[2, 6, 8, 9, 15, 18],
        description="Default pause points: after scoping, literature, hypothesis, experiment design, decision, review",
    )
    approval_timeout_minutes: int = Field(
        default=60,
        description="Timeout for human approval",
    )
    feedback_format: Literal["cli", "json", "api"] = Field(
        default="cli",
        description="Format for presenting feedback options",
    )
    allow_stage_skip: bool = Field(
        default=False,
        description="Whether to allow skipping stages",
    )
    allow_hypothesis_edit: bool = Field(
        default=True,
        description="Whether to allow editing hypotheses at Stage 8",
    )
    allow_experiment_override: bool = Field(
        default=True,
        description="Whether to override experiment parameters at Stage 9",
    )

    def should_pause(self, stage_number: int) -> bool:
        """Check if pipeline should pause after given stage number.

        Args:
            stage_number: The stage number to check

        Returns:
            True if pipeline should pause after this stage
        """
        return stage_number in self.pause_after_stages


class HumanFeedback(BaseModel):
    """Human feedback provided in collaborative mode.

    Attributes:
        stage_number: Stage number this feedback applies to
        action: The action taken (approve/edit/reject/skip)
        feedback_text: Optional feedback text for edits/rejections
        confidence_scores: Optional confidence scores for stage output
        timestamp: When feedback was provided
        metadata: Additional metadata
    """

    stage_number: int
    action: FeedbackAction
    feedback_text: str | None = Field(
        default=None,
        description="Feedback text for edits or rejections",
    )
    confidence_scores: dict[str, float] | None = Field(
        default=None,
        description="Confidence scores for stage output components",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_audit_entry(self) -> dict[str, Any]:
        """Convert to audit trail entry format.

        Returns:
            Dictionary suitable for audit_trail.json
        """
        return {
            "type": "human_feedback",
            "stage_number": self.stage_number,
            "action": self.action.value,
            "feedback_text": self.feedback_text,
            "confidence_scores": self.confidence_scores,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class StageSummary(BaseModel):
    """Summary of stage output for human review.

    Attributes:
        stage_number: Stage number
        stage_name: Human-readable stage name
        status: Stage completion status
        output_summary: Brief summary of what was produced
        key_decisions: Key decisions made during the stage
        alternatives_considered: Alternative approaches considered
        confidence_scores: Confidence scores per output component
        warnings: Any warnings or issues encountered
    """

    stage_number: int
    stage_name: str
    status: Literal["completed", "partial", "failed"]
    output_summary: str
    key_decisions: list[str] = Field(default_factory=list)
    alternatives_considered: list[str] = Field(default_factory=list)
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def format_for_cli(self) -> str:
        """Format summary for CLI display.

        Returns:
            Formatted string for terminal display
        """
        lines = [
            f"\n{'='*60}",
            f"Stage {self.stage_number}: {self.stage_name}",
            f"{'='*60}",
            f"Status: {self.status.upper()}",
            f"\n📋 Output Summary:",
            f"   {self.output_summary}",
        ]

        if self.key_decisions:
            lines.append(f"\n🔑 Key Decisions:")
            for decision in self.key_decisions:
                lines.append(f"   • {decision}")

        if self.alternatives_considered:
            lines.append(f"\n🔄 Alternatives Considered:")
            for alt in self.alternatives_considered:
                lines.append(f"   • {alt}")

        if self.confidence_scores:
            lines.append(f"\n📊 Confidence Scores:")
            for key, score in self.confidence_scores.items():
                bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
                lines.append(f"   {key}: [{bar}] {score:.0%}")

        if self.warnings:
            lines.append(f"\n⚠️  Warnings:")
            for warning in self.warnings:
                lines.append(f"   ⚠️  {warning}")

        lines.append(f"\n{'='*60}")
        return "\n".join(lines)

    def format_for_json(self) -> str:
        """Format summary as JSON.

        Returns:
            JSON string representation
        """
        return json.dumps(self.model_dump(), indent=2, default=str)


class AuditTrail:
    """Persistent audit trail for collaborative mode decisions.

    Records all human decisions, feedback, and stage approvals/rejections
    to audit_trail.json for traceability and reproducibility.

    Attributes:
        filepath: Path to audit_trail.json file
        entries: List of audit trail entries
    """

    def __init__(self, filepath: Path | str | None = None):
        """Initialize audit trail.

        Args:
            filepath: Path to audit trail file (default: audit_trail.json in current dir)
        """
        self.filepath = Path(filepath) if filepath else Path("audit_trail.json")
        self.entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Load existing audit trail from file."""
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.entries = data.get("entries", [])
                    logger.info(f"Loaded {len(self.entries)} audit trail entries")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load audit trail: {e}")
                self.entries = []

    def _save(self) -> None:
        """Save audit trail to file."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(
                    {"entries": self.entries, "updated_at": datetime.now(timezone.utc).isoformat()},
                    f,
                    indent=2,
                )
            logger.debug(f"Saved audit trail with {len(self.entries)} entries")
        except IOError as e:
            logger.error(f"Failed to save audit trail: {e}")

    def record_feedback(self, feedback: HumanFeedback) -> None:
        """Record human feedback entry.

        Args:
            feedback: HumanFeedback object to record
        """
        entry = feedback.to_audit_entry()
        entry["id"] = f"feedback_{len(self.entries) + 1}"
        self.entries.append(entry)
        self._save()

    def record_stage_completion(
        self,
        stage_number: int,
        stage_name: str,
        output_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record stage completion entry.

        Args:
            stage_number: Completed stage number
            stage_name: Stage name
            output_path: Optional path to stage output
            metadata: Optional additional metadata
        """
        entry = {
            "id": f"stage_{len(self.entries) + 1}",
            "type": "stage_completion",
            "stage_number": stage_number,
            "stage_name": stage_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_path": output_path,
            "metadata": metadata or {},
        }
        self.entries.append(entry)
        self._save()

    def record_approval(
        self,
        stage_number: int,
        approved_by: str = "human",
        feedback: str | None = None,
    ) -> None:
        """Record stage approval entry.

        Args:
            stage_number: Approved stage number
            approved_by: Who approved (human/auto)
            feedback: Optional approval feedback
        """
        entry = {
            "id": f"approval_{len(self.entries) + 1}",
            "type": "stage_approval",
            "stage_number": stage_number,
            "approved_by": approved_by,
            "feedback": feedback,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.entries.append(entry)
        self._save()

    def record_rejection(
        self,
        stage_number: int,
        reason: str,
        requested_action: str,
    ) -> None:
        """Record stage rejection entry.

        Args:
            stage_number: Rejected stage number
            reason: Reason for rejection
            requested_action: What should be done instead
        """
        entry = {
            "id": f"rejection_{len(self.entries) + 1}",
            "type": "stage_rejection",
            "stage_number": stage_number,
            "reason": reason,
            "requested_action": requested_action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.entries.append(entry)
        self._save()

    def get_stage_history(self, stage_number: int) -> list[dict[str, Any]]:
        """Get all audit entries for a specific stage.

        Args:
            stage_number: Stage number to query

        Returns:
            List of audit entries for the stage
        """
        return [
            entry
            for entry in self.entries
            if entry.get("stage_number") == stage_number
        ]

    def get_full_report(self) -> dict[str, Any]:
        """Get full audit trail report.

        Returns:
            Complete audit trail report with metadata
        """
        return {
            "total_entries": len(self.entries),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "entries": self.entries,
            "summary": {
                "stage_completions": sum(
                    1 for e in self.entries if e["type"] == "stage_completion"
                ),
                "approvals": sum(
                    1 for e in self.entries if e["type"] == "stage_approval"
                ),
                "rejections": sum(
                    1 for e in self.entries if e["type"] == "stage_rejection"
                ),
                "feedback_entries": sum(
                    1 for e in self.entries if e["type"] == "human_feedback"
                ),
            },
        }


class OperationModeManager:
    """Manager for operation mode transitions and collaborative workflows.

    This class handles:
    - Mode selection and configuration
    - Collaborative mode pause/resume
    - Human feedback collection (CLI/JSON/API)
    - Audit trail integration
    - Timeout handling

    Attributes:
        mode: Current operation mode
        collaborative_config: Configuration for collaborative mode
        audit_trail: Audit trail instance
    """

    def __init__(
        self,
        mode: OperationMode = OperationMode.AUTONOMOUS,
        collaborative_config: CollaborativeConfig | None = None,
        audit_trail_path: Path | str | None = None,
    ):
        """Initialize operation mode manager.

        Args:
            mode: Operation mode (autonomous/collaborative)
            collaborative_config: Configuration for collaborative mode
            audit_trail_path: Path to audit trail file
        """
        self.mode = mode
        self.collaborative_config = collaborative_config or CollaborativeConfig()
        self.audit_trail = AuditTrail(audit_trail_path)
        self._pending_approval: dict[int, StageSummary] = {}

    def is_collaborative(self) -> bool:
        """Check if running in collaborative mode.

        Returns:
            True if in collaborative mode
        """
        return self.mode == OperationMode.COLLABORATIVE

    def should_pause_after_stage(self, stage_number: int) -> bool:
        """Check if pipeline should pause after given stage.

        Args:
            stage_number: Stage number to check

        Returns:
            True if should pause (collaborative mode + stage in list)
        """
        if not self.is_collaborative():
            return False
        return self.collaborative_config.should_pause(stage_number)

    async def present_for_approval(
        self,
        summary: StageSummary,
    ) -> HumanFeedback | None:
        """Present stage output for human approval.

        Args:
            summary: Stage summary to present

        Returns:
            HumanFeedback if provided, None if timeout/approved

        Raises:
            TimeoutError: If approval timeout exceeded
        """
        self._pending_approval[summary.stage_number] = summary

        if self.collaborative_config.feedback_format == "cli":
            return await self._collect_cli_feedback(summary)
        elif self.collaborative_config.feedback_format == "json":
            return await self._collect_json_feedback(summary)
        else:  # api
            # API mode: feedback submitted via POST /research/{id}/feedback
            logger.info(
                f"Stage {summary.stage_number} awaiting approval via API..."
            )
            return None  # Will be provided via API

    async def _collect_cli_feedback(
        self, summary: StageSummary
    ) -> HumanFeedback:
        """Collect feedback via CLI interaction.

        Args:
            summary: Stage summary to present

        Returns:
            HumanFeedback from user
        """
        import asyncio

        # Display summary
        print(summary.format_for_cli())

        # Present options
        print("\nAvailable Actions:")
        print("  [A] Approve and continue")
        if self.collaborative_config.allow_stage_skip:
            print("  [S] Skip this stage")
        print("  [E] Edit (provide feedback)")
        print("  [R] Reject and regenerate")
        if summary.stage_number == 8 and self.collaborative_config.allow_hypothesis_edit:
            print("  [H] Add additional hypothesis")
        if summary.stage_number == 9 and self.collaborative_config.allow_experiment_override:
            print("  [O] Override experiment parameters")
        print()

        # Get user input with timeout
        try:
            loop = asyncio.get_event_loop()
            action = await asyncio.wait_for(
                loop.run_in_executor(None, input, "Your choice [A]: "),
                timeout=self.collaborative_config.approval_timeout_minutes * 60,
            )
            action = action.strip().upper() or "A"
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Approval timeout after {self.collaborative_config.approval_timeout_minutes} minutes"
            )

        # Process action
        if action == "A":
            feedback = HumanFeedback(
                stage_number=summary.stage_number,
                action=FeedbackAction.APPROVE,
            )
            self.audit_trail.record_approval(summary.stage_number)
        elif action == "S" and self.collaborative_config.allow_stage_skip:
            feedback = HumanFeedback(
                stage_number=summary.stage_number,
                action=FeedbackAction.SKIP,
            )
        elif action == "E":
            feedback_text = input("Enter your feedback: ").strip()
            feedback = HumanFeedback(
                stage_number=summary.stage_number,
                action=FeedbackAction.EDIT,
                feedback_text=feedback_text,
            )
        elif action == "R":
            feedback_text = input("Enter rejection reason: ").strip()
            feedback = HumanFeedback(
                stage_number=summary.stage_number,
                action=FeedbackAction.REJECT,
                feedback_text=feedback_text,
            )
            self.audit_trail.record_rejection(
                summary.stage_number, feedback_text, "regenerate"
            )
        elif action == "H" and summary.stage_number == 8:
            hypothesis = input("Enter additional hypothesis: ").strip()
            feedback = HumanFeedback(
                stage_number=summary.stage_number,
                action=FeedbackAction.ADD_HYPOTHESIS,
                feedback_text=hypothesis,
                metadata={"hypothesis": hypothesis},
            )
        elif action == "O" and summary.stage_number == 9:
            override = input("Enter experiment parameter overrides (JSON): ").strip()
            try:
                override_data = json.loads(override)
                feedback = HumanFeedback(
                    stage_number=summary.stage_number,
                    action=FeedbackAction.OVERRIDE,
                    metadata={"overrides": override_data},
                )
            except json.JSONDecodeError:
                print("Invalid JSON, using default parameters...")
                feedback = HumanFeedback(
                    stage_number=summary.stage_number,
                    action=FeedbackAction.APPROVE,
                )
        else:
            feedback = HumanFeedback(
                stage_number=summary.stage_number,
                action=FeedbackAction.APPROVE,
            )

        # Record feedback
        self.audit_trail.record_feedback(feedback)
        return feedback

    async def _collect_json_feedback(
        self, summary: StageSummary
    ) -> HumanFeedback:
        """Collect feedback via JSON input.

        Args:
            summary: Stage summary to present

        Returns:
            HumanFeedback from parsed JSON
        """
        import asyncio

        # Output JSON summary
        print(summary.format_for_json())
        print("\nSubmit feedback as JSON via stdin:")
        print('{"action": "approve|edit|reject|skip", "feedback_text": "..."}')
        print()

        try:
            loop = asyncio.get_event_loop()
            json_input = await asyncio.wait_for(
                loop.run_in_executor(None, input),
                timeout=self.collaborative_config.approval_timeout_minutes * 60,
            )
            data = json.loads(json_input)

            feedback = HumanFeedback(
                stage_number=summary.stage_number,
                action=FeedbackAction(data.get("action", "approve")),
                feedback_text=data.get("feedback_text"),
                confidence_scores=data.get("confidence_scores"),
                metadata=data.get("metadata", {}),
            )
            self.audit_trail.record_feedback(feedback)
            return feedback

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Approval timeout after {self.collaborative_config.approval_timeout_minutes} minutes"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON feedback: {e}")
            return HumanFeedback(
                stage_number=summary.stage_number,
                action=FeedbackAction.APPROVE,
            )

    def inject_feedback_into_context(
        self,
        feedback: HumanFeedback,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Inject human feedback into pipeline context.

        Args:
            feedback: Human feedback to inject
            context: Current pipeline context

        Returns:
            Updated context with feedback injected
        """
        context["human_feedback"] = context.get("human_feedback", {})
        context["human_feedback"][feedback.stage_number] = {
            "action": feedback.action.value,
            "feedback_text": feedback.feedback_text,
            "timestamp": feedback.timestamp.isoformat(),
            **feedback.metadata,
        }

        # Special handling for specific stages
        if feedback.action == FeedbackAction.ADD_HYPOTHESIS:
            # Add to hypotheses list
            hypotheses = context.get("hypotheses", [])
            if feedback.feedback_text:
                hypotheses.append(feedback.feedback_text)
                context["hypotheses"] = hypotheses

        elif feedback.action == FeedbackAction.OVERRIDE:
            # Override experiment parameters
            if "overrides" in feedback.metadata:
                context["experiment_overrides"] = feedback.metadata["overrides"]

        logger.info(
            f"Injected human feedback for stage {feedback.stage_number}: {feedback.action.value}"
        )
        return context

    def get_audit_report(self) -> dict[str, Any]:
        """Get full audit trail report.

        Returns:
            Complete audit trail report
        """
        return self.audit_trail.get_full_report()


# Convenience function for CLI
def create_mode_manager(
    mode: str = "autonomous",
    pause_after: list[int] | None = None,
    timeout_minutes: int = 60,
    audit_path: str | None = None,
) -> OperationModeManager:
    """Create operation mode manager from CLI arguments.

    Args:
        mode: Mode string ("autonomous" or "collaborative")
        pause_after: List of stages to pause after
        timeout_minutes: Approval timeout in minutes
        audit_path: Path to audit trail file

    Returns:
        Configured OperationModeManager instance
    """
    op_mode = OperationMode(mode.lower())

    config = None
    if op_mode == OperationMode.COLLABORATIVE:
        config = CollaborativeConfig(
            pause_after_stages=pause_after or [2, 6, 8, 9, 15, 18],
            approval_timeout_minutes=timeout_minutes,
        )

    return OperationModeManager(
        mode=op_mode,
        collaborative_config=config,
        audit_trail_path=Path(audit_path) if audit_path else None,
    )
