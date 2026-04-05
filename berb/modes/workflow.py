"""Workflow types and configuration for Berb research pipeline.

This module defines the different research workflows that users can select,
each with its own set of enabled stages and behavior. The workflow type
determines WHAT the user wants, while the operation mode determines HOW
the pipeline executes (autonomous vs collaborative).

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WorkflowType(str, Enum):
    """Types of research workflows available in Berb.
    
    Each workflow type represents a different research goal and determines
    which stages of the 23-stage pipeline are executed.
    
    Attributes:
        FULL_RESEARCH: End-to-end research (topic → paper). All 23 stages.
        LITERATURE_ONLY: Literature search + synthesis only. No experiments.
        PAPER_FROM_RESULTS: User has results, Berb writes the paper.
        EXPERIMENT_ONLY: Design and run experiments only. No paper.
        REVIEW_ONLY: Review an existing manuscript.
        REBUTTAL: Generate rebuttal letter from reviewer comments.
        LITERATURE_REVIEW: Write a standalone literature review paper.
        MATH_PAPER: Paper with significant mathematical content.
        COMPUTATIONAL_PAPER: Paper with significant computational experiments.
    """

    FULL_RESEARCH = "full-research"
    """End-to-end: topic → literature → hypothesis → experiments → paper.
    Runs all 23 stages. The default Berb experience."""

    LITERATURE_ONLY = "literature-only"
    """Literature search + synthesis only. No experiments, no paper.
    Outputs: structured bibliography, synthesis report, gap analysis, reading notes.
    Stages: 1-8 (Scoping + Literature + Synthesis + Hypothesis)"""

    PAPER_FROM_RESULTS = "paper-from-results"
    """User already has experiment results. Berb writes the paper.
    User uploads: data files, figures, experiment descriptions.
    Stages: 14-23 (Analysis + Writing + Finalization)"""

    EXPERIMENT_ONLY = "experiment-only"
    """Design and run experiments only. No paper writing.
    User provides: hypothesis + background context.
    Stages: 9-15 (Design + Execution + Analysis + Decision)"""

    REVIEW_ONLY = "review-only"
    """Review an existing paper/manuscript. Score + feedback + improvement suggestions.
    User uploads: manuscript PDF.
    Stages: 18 only (Peer Review) + M1 cross-model review"""

    REBUTTAL = "rebuttal"
    """Generate rebuttal letter from reviewer comments.
    User uploads: manuscript + reviewer comments.
    Uses: K4 Rebuttal Generator"""

    LITERATURE_REVIEW_PAPER = "literature-review"
    """Write a standalone literature review / survey paper.
    No experiments. Deep literature search + synthesis + paper writing.
    Stages: 1-8 + 16-23 (skip experiment stages)"""

    MATH_PAPER = "math-paper"
    """Paper with significant mathematical content.
    Includes: theorem/proof generation, equation typesetting, formal verification.
    All 23 stages + O2 mathematical content engine."""

    COMPUTATIONAL_PAPER = "computational-paper"
    """Paper with significant computational experiments.
    Emphasis on code quality, reproducibility, benchmark comparisons.
    All 23 stages + O3 pseudocode appendix + O4 code quality."""


class WorkflowConfig(BaseModel):
    """Configuration for a research workflow.
    
    This configuration determines which stages of the pipeline are executed
    based on the selected workflow type, plus additional user preferences.
    
    Attributes:
        workflow: The type of workflow to execute
        enabled_stages: Optional override for which stages to run
        uploaded_pdfs: PDF files to include in literature (O1)
        uploaded_data: Experiment data files (for paper-from-results)
        uploaded_manuscript: Manuscript for review workflows
        uploaded_reviews: Reviewer comments for rebuttal
        include_math: Enable mathematical content engine (O2)
        include_experiments: Enable experiment stages
        include_code_appendix: Generate pseudocode appendix (O3)
        include_supplementary: Generate supplementary materials (O5)
        operation_mode: Autonomous or collaborative mode
    """

    workflow: WorkflowType = WorkflowType.FULL_RESEARCH
    enabled_stages: list[int] | None = Field(
        default=None,
        description="Auto-determined from workflow, or manual override",
    )

    # User-provided inputs
    uploaded_pdfs: list[Path] = Field(
        default_factory=list,
        description="PDFs to include in literature (O1)",
    )
    uploaded_data: list[Path] = Field(
        default_factory=list,
        description="Experiment data (for paper-from-results)",
    )
    uploaded_manuscript: Path | None = Field(
        default=None,
        description="For review-only / rebuttal workflows",
    )
    uploaded_reviews: Path | None = Field(
        default=None,
        description="For rebuttal workflow",
    )

    # Component toggles (user chooses what they want)
    include_math: bool = False
    """Enable mathematical content engine (O2)"""
    
    include_experiments: bool = True
    """Enable experiment stages"""
    
    include_code_appendix: bool = False
    """Generate pseudocode appendix (O3)"""
    
    include_supplementary: bool = True
    """Generate supplementary materials (O5)"""

    # Operation mode (orthogonal to workflow)
    operation_mode: Literal["autonomous", "collaborative"] = "autonomous"
    """Whether to run autonomously or with human-in-the-loop"""

    @property
    def default_stages(self) -> list[int]:
        """Get the default stages for this workflow type."""
        return WORKFLOW_STAGES.get(self.workflow, list(range(1, 24)))

    @property
    def active_stages(self) -> list[int]:
        """Get the stages that will actually be executed."""
        if self.enabled_stages is not None:
            return self.enabled_stages
        return self.default_stages

    def model_post_init(self, __context: dict) -> None:
        """Validate workflow configuration after initialization."""
        # Validate that enabled_stages are within valid range
        if self.enabled_stages:
            for stage in self.enabled_stages:
                if not (1 <= stage <= 23):
                    raise ValueError(f"Stage number must be between 1 and 23, got {stage}")

        # Validate workflow-specific constraints
        if self.workflow == WorkflowType.LITERATURE_ONLY and not self.include_experiments:
            # Literature-only doesn't run experiments, which is the default
            pass

        if self.workflow == WorkflowType.PAPER_FROM_RESULTS and not self.uploaded_data:
            logger.warning(
                "paper-from-results workflow selected but no uploaded_data provided"
            )

        if self.workflow == WorkflowType.REVIEW_ONLY and not self.uploaded_manuscript:
            logger.warning(
                "review-only workflow selected but no uploaded_manuscript provided"
            )

        if self.workflow == WorkflowType.REBUTTAL:
            if not self.uploaded_manuscript:
                logger.warning(
                    "rebuttal workflow selected but no uploaded_manuscript provided"
                )
            if not self.uploaded_reviews:
                logger.warning(
                    "rebuttal workflow selected but no uploaded_reviews provided"
                )


# Stage mapping per workflow type
WORKFLOW_STAGES: dict[WorkflowType, list[int]] = {
    WorkflowType.FULL_RESEARCH: list(range(1, 24)),
    """All 23 stages: topic → literature → hypothesis → experiments → paper""",
    
    WorkflowType.LITERATURE_ONLY: [1, 2, 3, 4, 5, 6, 7, 8],
    """Scoping + Literature + Synthesis + Hypothesis only""",
    
    WorkflowType.PAPER_FROM_RESULTS: [14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
    """Analysis + Writing + Finalization only""",
    
    WorkflowType.EXPERIMENT_ONLY: [9, 10, 11, 12, 13, 14, 15],
    """Design + Execution + Analysis + Decision only""",
    
    WorkflowType.REVIEW_ONLY: [18],
    """Peer Review only""",
    
    WorkflowType.REBUTTAL: [],
    """Custom pipeline, not stage-based (uses K4 Rebuttal Generator)""",
    
    WorkflowType.LITERATURE_REVIEW_PAPER: [1, 2, 3, 4, 5, 6, 7, 8, 16, 17, 18, 19, 20, 21, 22, 23],
    """Scoping + Literature + Synthesis + Paper Writing (skip experiments)""",
    
    WorkflowType.MATH_PAPER: list(range(1, 24)),
    """All 23 stages + mathematical content engine (O2)""",
    
    WorkflowType.COMPUTATIONAL_PAPER: list(range(1, 24)),
    """All 23 stages + pseudocode appendix (O3) + code quality (O4)""",
}


class WorkflowManager:
    """Manager for workflow selection and configuration.
    
    This class handles:
    - Workflow type selection and validation
    - Stage mapping and filtering
    - Workflow-specific configuration
    - User input validation
    
    Attributes:
        current_workflow: The currently selected workflow
        config: Workflow configuration
    """

    def __init__(
        self,
        workflow: WorkflowType = WorkflowType.FULL_RESEARCH,
        config: WorkflowConfig | None = None,
    ):
        """Initialize workflow manager.
        
        Args:
            workflow: The workflow type to use
            config: Optional workflow configuration
        """
        self.current_workflow = workflow
        self.config = config or WorkflowConfig(workflow=workflow)

    def get_enabled_stages(self) -> list[int]:
        """Get the list of stages that will be executed.
        
        Returns:
            List of stage numbers to execute
        """
        return self.config.active_stages

    def is_stage_enabled(self, stage_number: int) -> bool:
        """Check if a specific stage is enabled for this workflow.
        
        Args:
            stage_number: The stage number to check
            
        Returns:
            True if the stage is enabled
        """
        return stage_number in self.config.active_stages

    def get_stage_names(self) -> dict[int, str]:
        """Get the names of all enabled stages.
        
        Returns:
            Dictionary mapping stage numbers to names
        """
        stage_names = {
            1: "TOPIC_INIT",
            2: "PROBLEM_DECOMPOSE",
            3: "SEARCH_STRATEGY",
            4: "LITERATURE_COLLECT",
            5: "LITERATURE_SCREEN",
            6: "KNOWLEDGE_EXTRACT",
            7: "SYNTHESIS",
            8: "HYPOTHESIS_GEN",
            9: "EXPERIMENT_DESIGN",
            10: "CODE_GENERATION",
            11: "RESOURCE_PLANNING",
            12: "EXPERIMENT_RUN",
            13: "ITERATIVE_REFINE",
            14: "RESULT_ANALYSIS",
            15: "RESEARCH_DECISION",
            16: "PAPER_OUTLINE",
            17: "PAPER_DRAFT",
            18: "PEER_REVIEW",
            19: "PAPER_REVISION",
            20: "QUALITY_GATE",
            21: "KNOWLEDGE_ARCHIVE",
            22: "EXPORT_PUBLISH",
            23: "CITATION_VERIFY",
        }
        return {
            num: name
            for num, name in stage_names.items()
            if self.is_stage_enabled(num)
        }

    def to_dict(self) -> dict:
        """Convert workflow configuration to dictionary.
        
        Returns:
            Dictionary representation of workflow configuration
        """
        return {
            "workflow": self.current_workflow.value,
            "enabled_stages": self.config.active_stages,
            "uploaded_pdfs": [str(p) for p in self.config.uploaded_pdfs],
            "uploaded_data": [str(p) for p in self.config.uploaded_data],
            "uploaded_manuscript": (
                str(self.config.uploaded_manuscript)
                if self.config.uploaded_manuscript
                else None
            ),
            "uploaded_reviews": (
                str(self.config.uploaded_reviews)
                if self.config.uploaded_reviews
                else None
            ),
            "include_math": self.config.include_math,
            "include_experiments": self.config.include_experiments,
            "include_code_appendix": self.config.include_code_appendix,
            "include_supplementary": self.config.include_supplementary,
            "operation_mode": self.config.operation_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowManager:
        """Create workflow manager from dictionary.
        
        Args:
            data: Dictionary with workflow configuration
            
        Returns:
            Configured WorkflowManager instance
        """
        workflow = WorkflowType(data.get("workflow", "full-research"))
        config = WorkflowConfig(
            workflow=workflow,
            enabled_stages=data.get("enabled_stages"),
            uploaded_pdfs=[Path(p) for p in data.get("uploaded_pdfs", [])],
            uploaded_data=[Path(p) for p in data.get("uploaded_data", [])],
            uploaded_manuscript=(
                Path(data["uploaded_manuscript"])
                if data.get("uploaded_manuscript")
                else None
            ),
            uploaded_reviews=(
                Path(data["uploaded_reviews"])
                if data.get("uploaded_reviews")
                else None
            ),
            include_math=data.get("include_math", False),
            include_experiments=data.get("include_experiments", True),
            include_code_appendix=data.get("include_code_appendix", False),
            include_supplementary=data.get("include_supplementary", True),
            operation_mode=data.get("operation_mode", "autonomous"),
        )
        return cls(workflow=workflow, config=config)


# Convenience functions for CLI
def get_workflow_stages(workflow: WorkflowType) -> list[int]:
    """Get the stages for a workflow type.
    
    Args:
        workflow: The workflow type
        
    Returns:
        List of stage numbers
    """
    return WORKFLOW_STAGES.get(workflow, list(range(1, 24)))


def create_workflow_manager(
    workflow: str = "full-research",
    stages: list[int] | None = None,
    uploaded_pdfs: list[str] | None = None,
    uploaded_data: list[str] | None = None,
    uploaded_manuscript: str | None = None,
    uploaded_reviews: str | None = None,
    include_math: bool = False,
    include_experiments: bool = True,
    include_code_appendix: bool = False,
    include_supplementary: bool = True,
    operation_mode: str = "autonomous",
) -> WorkflowManager:
    """Create a workflow manager from CLI arguments.
    
    Args:
        workflow: Workflow type string
        stages: Optional list of stage numbers to enable
        uploaded_pdfs: List of PDF paths
        uploaded_data: List of data file paths
        uploaded_manuscript: Manuscript path
        uploaded_reviews: Reviews path
        include_math: Enable math engine
        include_experiments: Enable experiments
        include_code_appendix: Include code appendix
        include_supplementary: Include supplementary materials
        operation_mode: Autonomous or collaborative
        
    Returns:
        Configured WorkflowManager instance
    """
    wf_type = WorkflowType(workflow.lower().replace(" ", "-"))

    config = WorkflowConfig(
        workflow=wf_type,
        enabled_stages=stages,
        uploaded_pdfs=[Path(p) for p in uploaded_pdfs or []],
        uploaded_data=[Path(p) for p in uploaded_data or []],
        uploaded_manuscript=(
            Path(uploaded_manuscript) if uploaded_manuscript else None
        ),
        uploaded_reviews=(
            Path(uploaded_reviews) if uploaded_reviews else None
        ),
        include_math=include_math,
        include_experiments=include_experiments,
        include_code_appendix=include_code_appendix,
        include_supplementary=include_supplementary,
        operation_mode=operation_mode,
    )

    return WorkflowManager(workflow=wf_type, config=config)
