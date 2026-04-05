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
from berb.modes.workflow import (
    WorkflowConfig,
    WorkflowManager,
    WorkflowType,
    WORKFLOW_STAGES,
    create_workflow_manager,
    get_workflow_stages,
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
    "WorkflowType",
    "WorkflowConfig",
    "WorkflowManager",
    "WORKFLOW_STAGES",
    "create_workflow_manager",
    "get_workflow_stages",
]
