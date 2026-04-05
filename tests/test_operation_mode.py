"""Unit tests for Berb operation modes.

Tests for autonomous and collaborative operation modes,
including feedback collection, audit trail, and mode management.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from berb.modes.operation_mode import (
    OperationMode,
    OperationModeManager,
    CollaborativeConfig,
    FeedbackAction,
    HumanFeedback,
    StageSummary,
    AuditTrail,
    create_mode_manager,
)


class TestOperationMode:
    """Test OperationMode enum."""

    def test_operation_mode_values(self):
        """Test operation mode enum values."""
        assert OperationMode.AUTONOMOUS.value == "autonomous"
        assert OperationMode.COLLABORATIVE.value == "collaborative"

    def test_operation_mode_from_string(self):
        """Test creating operation mode from string."""
        assert OperationMode("autonomous") == OperationMode.AUTONOMOUS
        assert OperationMode("collaborative") == OperationMode.COLLABORATIVE


class TestCollaborativeConfig:
    """Test CollaborativeConfig."""

    def test_default_config(self):
        """Test default collaborative configuration."""
        config = CollaborativeConfig()
        assert config.pause_after_stages == [2, 6, 8, 9, 15, 18]
        assert config.approval_timeout_minutes == 60
        assert config.feedback_format == "cli"
        assert config.allow_stage_skip is False
        assert config.allow_hypothesis_edit is True
        assert config.allow_experiment_override is True

    def test_custom_config(self):
        """Test custom collaborative configuration."""
        config = CollaborativeConfig(
            pause_after_stages=[1, 5, 10],
            approval_timeout_minutes=30,
            feedback_format="json",
            allow_stage_skip=True,
        )
        assert config.pause_after_stages == [1, 5, 10]
        assert config.approval_timeout_minutes == 30
        assert config.feedback_format == "json"
        assert config.allow_stage_skip is True

    def test_should_pause(self):
        """Test should_pause method."""
        config = CollaborativeConfig(pause_after_stages=[2, 8, 15])
        assert config.should_pause(2) is True
        assert config.should_pause(8) is True
        assert config.should_pause(5) is False
        assert config.should_pause(20) is False


class TestFeedbackAction:
    """Test FeedbackAction enum."""

    def test_feedback_action_values(self):
        """Test feedback action enum values."""
        assert FeedbackAction.APPROVE.value == "approve"
        assert FeedbackAction.EDIT.value == "edit"
        assert FeedbackAction.REJECT.value == "reject"
        assert FeedbackAction.SKIP.value == "skip"
        assert FeedbackAction.ADD_HYPOTHESIS.value == "add_hypothesis"
        assert FeedbackAction.OVERRIDE.value == "override"


class TestHumanFeedback:
    """Test HumanFeedback model."""

    def test_create_feedback(self):
        """Test creating human feedback."""
        feedback = HumanFeedback(
            stage_number=8,
            action=FeedbackAction.APPROVE,
        )
        assert feedback.stage_number == 8
        assert feedback.action == FeedbackAction.APPROVE
        assert feedback.feedback_text is None
        assert feedback.timestamp is not None

    def test_create_feedback_with_text(self):
        """Test creating feedback with feedback text."""
        feedback = HumanFeedback(
            stage_number=9,
            action=FeedbackAction.EDIT,
            feedback_text="Please add more baselines",
        )
        assert feedback.feedback_text == "Please add more baselines"

    def test_to_audit_entry(self):
        """Test converting feedback to audit entry."""
        feedback = HumanFeedback(
            stage_number=5,
            action=FeedbackAction.REJECT,
            feedback_text="Low quality papers",
            confidence_scores={"relevance": 0.3},
        )
        entry = feedback.to_audit_entry()
        assert entry["type"] == "human_feedback"
        assert entry["stage_number"] == 5
        assert entry["action"] == "reject"
        assert entry["feedback_text"] == "Low quality papers"
        assert "timestamp" in entry


class TestStageSummary:
    """Test StageSummary model."""

    def test_create_summary(self):
        """Test creating stage summary."""
        summary = StageSummary(
            stage_number=8,
            stage_name="HYPOTHESIS_GEN",
            status="completed",
            output_summary="Generated 5 hypotheses",
            key_decisions=["Selected multi-perspective reasoning"],
            confidence_scores={"novelty": 0.85, "feasibility": 0.75},
        )
        assert summary.stage_number == 8
        assert summary.status == "completed"
        assert len(summary.key_decisions) == 1

    def test_format_for_cli(self):
        """Test CLI formatting."""
        summary = StageSummary(
            stage_number=2,
            stage_name="PROBLEM_DECOMPOSE",
            status="completed",
            output_summary="Decomposed into 4 sub-problems",
            confidence_scores={"completeness": 0.9},
        )
        cli_output = summary.format_for_cli()
        assert "Stage 2: PROBLEM_DECOMPOSE" in cli_output
        assert "Status: COMPLETED" in cli_output
        assert "Decomposed into 4 sub-problems" in cli_output

    def test_format_for_json(self):
        """Test JSON formatting."""
        summary = StageSummary(
            stage_number=1,
            stage_name="TOPIC_INIT",
            status="completed",
            output_summary="Topic initialized",
        )
        json_output = summary.format_for_json()
        data = json.loads(json_output)
        assert data["stage_number"] == 1
        assert data["stage_name"] == "TOPIC_INIT"


class TestAuditTrail:
    """Test AuditTrail."""

    def test_create_audit_trail(self, tmp_path):
        """Test creating audit trail."""
        filepath = tmp_path / "audit_trail.json"
        trail = AuditTrail(filepath)
        assert trail.filepath == filepath
        assert len(trail.entries) == 0

    def test_record_feedback(self, tmp_path):
        """Test recording feedback."""
        filepath = tmp_path / "audit_trail.json"
        trail = AuditTrail(filepath)
        
        feedback = HumanFeedback(
            stage_number=8,
            action=FeedbackAction.APPROVE,
        )
        trail.record_feedback(feedback)
        
        assert len(trail.entries) == 1
        assert trail.entries[0]["type"] == "human_feedback"
        assert trail.entries[0]["stage_number"] == 8
        
        # Verify file was written
        assert filepath.exists()

    def test_record_stage_completion(self, tmp_path):
        """Test recording stage completion."""
        filepath = tmp_path / "audit_trail.json"
        trail = AuditTrail(filepath)
        
        trail.record_stage_completion(
            stage_number=5,
            stage_name="LITERATURE_SCREEN",
            output_path="output/stage_5.json",
        )
        
        assert len(trail.entries) == 1
        assert trail.entries[0]["type"] == "stage_completion"
        assert trail.entries[0]["stage_number"] == 5

    def test_record_approval(self, tmp_path):
        """Test recording approval."""
        filepath = tmp_path / "audit_trail.json"
        trail = AuditTrail(filepath)
        
        trail.record_approval(stage_number=8, approved_by="human")
        
        assert len(trail.entries) == 1
        assert trail.entries[0]["type"] == "stage_approval"

    def test_record_rejection(self, tmp_path):
        """Test recording rejection."""
        filepath = tmp_path / "audit_trail.json"
        trail = AuditTrail(filepath)
        
        trail.record_rejection(
            stage_number=9,
            reason="Experiment design flawed",
            requested_action="regenerate",
        )
        
        assert len(trail.entries) == 1
        assert trail.entries[0]["type"] == "stage_rejection"
        assert "flawed" in trail.entries[0]["reason"]

    def test_get_stage_history(self, tmp_path):
        """Test getting stage history."""
        filepath = tmp_path / "audit_trail.json"
        trail = AuditTrail(filepath)
        
        trail.record_approval(stage_number=5)
        trail.record_approval(stage_number=8)
        trail.record_rejection(stage_number=5, reason="test", requested_action="fix")
        
        history = trail.get_stage_history(5)
        assert len(history) == 2

    def test_get_full_report(self, tmp_path):
        """Test getting full report."""
        filepath = tmp_path / "audit_trail.json"
        trail = AuditTrail(filepath)
        
        trail.record_approval(stage_number=5)
        trail.record_rejection(stage_number=8, reason="test", requested_action="fix")
        
        report = trail.get_full_report()
        assert "total_entries" in report
        assert report["total_entries"] == 2
        assert "summary" in report
        assert report["summary"]["approvals"] == 1
        assert report["summary"]["rejections"] == 1

    def test_load_existing_trail(self, tmp_path):
        """Test loading existing audit trail."""
        filepath = tmp_path / "audit_trail.json"
        
        # Create initial trail
        trail1 = AuditTrail(filepath)
        trail1.record_approval(stage_number=1)
        
        # Load again
        trail2 = AuditTrail(filepath)
        assert len(trail2.entries) == 1


class TestOperationModeManager:
    """Test OperationModeManager."""

    def test_create_autonomous_manager(self):
        """Test creating autonomous mode manager."""
        manager = OperationModeManager(mode=OperationMode.AUTONOMOUS)
        assert manager.mode == OperationMode.AUTONOMOUS
        assert manager.is_collaborative() is False
        assert manager.should_pause_after_stage(8) is False

    def test_create_collaborative_manager(self):
        """Test creating collaborative mode manager."""
        config = CollaborativeConfig(pause_after_stages=[2, 8])
        manager = OperationModeManager(
            mode=OperationMode.COLLABORATIVE,
            collaborative_config=config,
        )
        assert manager.is_collaborative() is True
        assert manager.should_pause_after_stage(2) is True
        assert manager.should_pause_after_stage(8) is True
        assert manager.should_pause_after_stage(5) is False

    def test_inject_feedback_hypothesis(self):
        """Test injecting hypothesis feedback."""
        manager = OperationModeManager(mode=OperationMode.COLLABORATIVE)
        
        feedback = HumanFeedback(
            stage_number=8,
            action=FeedbackAction.ADD_HYPOTHESIS,
            feedback_text="Additional hypothesis here",
        )
        context = {"hypotheses": ["Original hypothesis"]}
        
        updated = manager.inject_feedback_into_context(feedback, context)
        
        assert "human_feedback" in updated
        assert len(updated["hypotheses"]) == 2
        assert "Additional hypothesis here" in updated["hypotheses"]

    def test_inject_feedback_override(self):
        """Test injecting experiment override feedback."""
        manager = OperationModeManager(mode=OperationMode.COLLABORATIVE)
        
        feedback = HumanFeedback(
            stage_number=9,
            action=FeedbackAction.OVERRIDE,
            metadata={"overrides": {"max_iterations": 20}},
        )
        context = {}
        
        updated = manager.inject_feedback_into_context(feedback, context)
        
        assert "experiment_overrides" in updated
        assert updated["experiment_overrides"]["max_iterations"] == 20

    def test_get_audit_report(self):
        """Test getting audit report."""
        manager = OperationModeManager(mode=OperationMode.COLLABORATIVE)
        
        manager.audit_trail.record_approval(stage_number=5)
        manager.audit_trail.record_rejection(
            stage_number=8, reason="test", requested_action="fix"
        )
        
        report = manager.get_audit_report()
        assert report["total_entries"] == 2
        assert report["summary"]["approvals"] == 1


class TestCreateModeManager:
    """Test create_mode_manager convenience function."""

    def test_create_autonomous(self):
        """Test creating autonomous manager."""
        manager = create_mode_manager(mode="autonomous")
        assert manager.mode == OperationMode.AUTONOMOUS
        assert not manager.is_collaborative()

    def test_create_collaborative_with_pause(self):
        """Test creating collaborative manager with custom pause stages."""
        manager = create_mode_manager(
            mode="collaborative",
            pause_after=[1, 5, 10],
            timeout_minutes=30,
        )
        assert manager.is_collaborative()
        assert manager.collaborative_config.pause_after_stages == [1, 5, 10]
        assert manager.collaborative_config.approval_timeout_minutes == 30


@pytest.mark.asyncio
class TestAsyncApproval:
    """Test async approval workflows."""

    async def test_cli_approval_timeout(self):
        """Test CLI approval timeout."""
        config = CollaborativeConfig(
            approval_timeout_minutes=1,
            feedback_format="cli",
        )
        manager = OperationModeManager(
            mode=OperationMode.COLLABORATIVE,
            collaborative_config=config,
        )
        
        summary = StageSummary(
            stage_number=8,
            stage_name="HYPOTHESIS_GEN",
            status="completed",
            output_summary="Test",
        )
        
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            with pytest.raises(TimeoutError):
                await manager.present_for_approval(summary)

    async def test_json_feedback_parsing(self):
        """Test JSON feedback parsing."""
        config = CollaborativeConfig(feedback_format="json")
        manager = OperationModeManager(
            mode=OperationMode.COLLABORATIVE,
            collaborative_config=config,
        )
        
        summary = StageSummary(
            stage_number=5,
            stage_name="LITERATURE_SCREEN",
            status="completed",
            output_summary="Test",
        )
        
        # Mock JSON input
        json_feedback = '{"action": "approve", "feedback_text": "Good work"}'
        
        with patch("asyncio.wait_for", return_value=json_feedback):
            with patch("builtins.input", return_value=json_feedback):
                feedback = await manager._collect_json_feedback(summary)
                assert feedback.action == FeedbackAction.APPROVE
