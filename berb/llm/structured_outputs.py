"""Structured output definitions for pipeline stages.

This module defines Pydantic models for structured LLM outputs,
eliminating JSON parse failures and ensuring consistent output format.

Architecture: Pydantic v2 models with validation
Paradigm: Declarative schema definition

Usage:
    from berb.llm.structured_outputs import DecompositionOutput
    
    # Use with LLM tool/function calling
    response = client.chat(
        messages,
        response_format=DecompositionOutput,
    )
"""

# Author: Georgios-Chrysovalantis Chatzivantsidis

from __future__ import annotations

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Phase A: Scoping
# ─────────────────────────────────────────────────────────────────────────────


class DecompositionOutput(BaseModel):
    """Structured output for Stage 2: Problem Decomposition.
    
    Expected fields:
    - sub_problems: List of sub-problems (max 5)
    - assumptions: Key assumptions with labels
    - failure_modes: Potential failure modes
    """
    sub_problems: list[str] = Field(
        ...,
        description="List of 3-5 sub-problems to solve",
        min_length=1,
        max_length=5,
    )
    assumptions: list[dict[str, str]] = Field(
        ...,
        description="Key assumptions with text and label (VERIFIED/HYPOTHESIS/UNKNOWN)",
    )
    failure_modes: list[str] = Field(
        ...,
        description="Potential failure modes to watch for",
        min_length=1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase C: Synthesis
# ─────────────────────────────────────────────────────────────────────────────


class HypothesisOutput(BaseModel):
    """Structured output for Stage 8: Hypothesis Generation.
    
    Expected fields:
    - hypotheses: List of testable hypotheses
    - rationale: Reasoning behind hypotheses
    """
    hypotheses: list[dict[str, str]] = Field(
        ...,
        description="List of 3-5 testable hypotheses with statement and rationale",
        min_length=1,
        max_length=5,
    )
    rationale: str = Field(
        ...,
        description="Overall reasoning behind the hypotheses",
        min_length=50,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase D: Design
# ─────────────────────────────────────────────────────────────────────────────


class ExperimentDesignOutput(BaseModel):
    """Structured output for Stage 9: Experiment Design.
    
    Expected fields:
    - method: Experimental method description
    - variables: Independent/dependent variables
    - controls: Control conditions
    - metrics: Success metrics
    """
    method: str = Field(
        ...,
        description="Detailed experimental method",
        min_length=100,
    )
    variables: dict[str, list[str]] = Field(
        ...,
        description="Independent and dependent variables",
    )
    controls: list[str] = Field(
        ...,
        description="Control conditions",
        min_length=1,
    )
    metrics: list[str] = Field(
        ...,
        description="Success metrics to measure",
        min_length=2,
    )


class CodeGenerationOutput(BaseModel):
    """Structured output for Stage 10: Code Generation.
    
    Expected fields:
    - files: List of files to create
    - implementation: Main implementation code
    - dependencies: Required dependencies
    """
    files: list[dict[str, str]] = Field(
        ...,
        description="List of files with path and content",
        min_length=1,
    )
    dependencies: list[str] = Field(
        ...,
        description="Required Python packages",
    )
    instructions: str = Field(
        ...,
        description="Instructions for running the code",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase F: Analysis
# ─────────────────────────────────────────────────────────────────────────────


class ResearchDecisionOutput(BaseModel):
    """Structured output for Stage 15: Research Decision.
    
    Expected fields:
    - decision: PROCEED, REFINE, or PIVOT
    - rationale: Reasoning for decision
    - next_steps: Recommended next steps
    """
    decision: str = Field(
        ...,
        description="Decision: PROCEED, REFINE, or PIVOT",
        pattern="^(PROCEED|REFINE|PIVOT)$",
    )
    rationale: str = Field(
        ...,
        description="Detailed reasoning for the decision",
        min_length=50,
    )
    next_steps: list[str] = Field(
        ...,
        description="Recommended next steps",
        min_length=1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase G: Writing
# ─────────────────────────────────────────────────────────────────────────────


class PeerReviewOutput(BaseModel):
    """Structured output for Stage 18: Peer Review.
    
    Expected fields:
    - scores: Scores for each dimension (0-10)
    - strengths: Paper strengths
    - weaknesses: Paper weaknesses
    - recommendations: Recommendations for improvement
    """
    scores: dict[str, float] = Field(
        ...,
        description="Scores for novelty, rigor, clarity, impact, experiments (0-10)",
    )
    strengths: list[str] = Field(
        ...,
        description="Paper strengths",
        min_length=1,
    )
    weaknesses: list[str] = Field(
        ...,
        description="Paper weaknesses",
        min_length=1,
    )
    recommendations: list[str] = Field(
        ...,
        description="Recommendations for improvement",
        min_length=1,
    )
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "scores": {
                    "novelty": 7.5,
                    "rigor": 8.0,
                    "clarity": 6.5,
                    "impact": 7.0,
                    "experiments": 8.5,
                },
                "strengths": ["Strong methodology", "Clear results"],
                "weaknesses": ["Limited discussion", "Missing baseline"],
                "recommendations": ["Expand discussion", "Add baseline comparison"],
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# Phase H: Finalization
# ─────────────────────────────────────────────────────────────────────────────


class CitationVerificationOutput(BaseModel):
    """Structured output for Stage 23: Citation Verification.
    
    Expected fields:
    - verified_citations: List of verified citations
    - unverified_citations: List of unverified citations
    - removed_citations: Citations to remove
    """
    verified_citations: list[dict[str, str]] = Field(
        ...,
        description="Citations verified as real and relevant",
    )
    unverified_citations: list[dict[str, str]] = Field(
        ...,
        description="Citations that could not be verified",
    )
    removed_citations: list[str] = Field(
        ...,
        description="Citation keys to remove from paper",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────────────────────


def get_output_model(stage_name: str) -> type[BaseModel] | None:
    """Get structured output model for a pipeline stage.
    
    Args:
        stage_name: Name of the pipeline stage (e.g., "HYPOTHESIS_GEN")
        
    Returns:
        Pydantic model class or None if no structured output defined
        
    Example:
        >>> model = get_output_model("HYPOTHESIS_GEN")
        >>> model  # HypothesisOutput
    """
    stage_to_model = {
        "PROBLEM_DECOMPOSE": DecompositionOutput,
        "HYPOTHESIS_GEN": HypothesisOutput,
        "EXPERIMENT_DESIGN": ExperimentDesignOutput,
        "CODE_GENERATION": CodeGenerationOutput,
        "RESEARCH_DECISION": ResearchDecisionOutput,
        "PEER_REVIEW": PeerReviewOutput,
        "CITATION_VERIFY": CitationVerificationOutput,
    }
    
    return stage_to_model.get(stage_name.upper())


def validate_output(model: type[BaseModel], data: dict) -> BaseModel:
    """Validate output data against model schema.
    
    Args:
        model: Pydantic model class
        data: Data dictionary to validate
        
    Returns:
        Validated model instance
        
    Raises:
        ValidationError: If data doesn't match schema
    """
    return model.model_validate(data)
