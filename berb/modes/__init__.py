"""Operation modes for Berb research pipeline.

This module provides autonomous and collaborative operation modes,
enabling human-in-the-loop research at configurable decision points.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from berb.modes.operation_mode import (
    CollaborativeConfig,
    FeedbackAction,
    HumanFeedback,
    OperationMode,
    OperationModeManager,
    StageSummary,
    AuditTrail,
    create_mode_manager,
)

__all__ = [
    "OperationMode",
    "CollaborativeConfig",
    "FeedbackAction",
    "HumanFeedback",
    "StageSummary",
    "AuditTrail",
    "OperationModeManager",
    "create_mode_manager",
]
