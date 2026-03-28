"""Output token limits for each pipeline stage.

This module defines maximum token limits for LLM outputs per stage,
preventing verbose responses and reducing output token costs by 15-25%.

Architecture: Configuration dataclass with stage-specific limits
Paradigm: Declarative configuration

Usage:
    from berb.llm.output_limits import get_stage_token_limit
    
    max_tokens = get_stage_token_limit(Stage.HYPOTHESIS_GEN)
    # Returns: 2000
"""

# Author: Georgios-Chrysovalantis Chatzivantsidis

from enum import IntEnum


class Stage(IntEnum):
    """Pipeline stage enumeration for token limit lookup."""
    # Phase A: Scoping
    TOPIC_INIT = 1
    PROBLEM_DECOMPOSE = 2
    
    # Phase B: Literature
    SEARCH_STRATEGY = 3
    LITERATURE_COLLECT = 4
    LITERATURE_SCREEN = 5
    KNOWLEDGE_EXTRACT = 6
    
    # Phase C: Synthesis
    SYNTHESIS = 7
    HYPOTHESIS_GEN = 8
    
    # Phase D: Design
    EXPERIMENT_DESIGN = 9
    CODE_GENERATION = 10
    RESOURCE_PLANNING = 11
    
    # Phase E: Execution
    EXPERIMENT_RUN = 12
    ITERATIVE_REFINE = 13
    
    # Phase F: Analysis
    RESULT_ANALYSIS = 14
    RESEARCH_DECISION = 15
    
    # Phase G: Writing
    PAPER_OUTLINE = 16
    PAPER_DRAFT = 17
    PEER_REVIEW = 18
    PAPER_REVISION = 19
    
    # Phase H: Finalization
    QUALITY_GATE = 20
    KNOWLEDGE_ARCHIVE = 21
    EXPORT_PUBLISH = 22
    CITATION_VERIFY = 23


# Token limits per stage
# Rationale:
# - Simple stages (screening, verification): 500-1000 tokens
# - Medium stages (analysis, planning): 1500-3000 tokens
# - Complex stages (drafting, code gen): 4000-8000 tokens
OUTPUT_TOKEN_LIMITS: dict[Stage, int] = {
    # Phase A: Scoping (brief summaries)
    Stage.TOPIC_INIT: 1000,           # Topic summary
    Stage.PROBLEM_DECOMPOSE: 2000,    # Task list, structured JSON
    
    # Phase B: Literature (moderate detail)
    Stage.SEARCH_STRATEGY: 1500,      # Search plan
    Stage.LITERATURE_COLLECT: 3000,   # Paper list with metadata
    Stage.LITERATURE_SCREEN: 2000,    # Screening decisions
    Stage.KNOWLEDGE_EXTRACT: 2500,    # Knowledge cards
    
    # Phase C: Synthesis (complex reasoning)
    Stage.SYNTHESIS: 3000,            # Synthesis report
    Stage.HYPOTHESIS_GEN: 2000,       # Hypotheses list (3-5 hypotheses)
    
    # Phase D: Design (detailed specifications)
    Stage.EXPERIMENT_DESIGN: 3000,    # Experiment plan
    Stage.CODE_GENERATION: 6000,      # Code output (can be large)
    Stage.RESOURCE_PLANNING: 1500,    # Resource estimates
    
    # Phase E: Execution (results reporting)
    Stage.EXPERIMENT_RUN: 2000,       # Results summary
    Stage.ITERATIVE_REFINE: 2000,     # Refinement notes
    
    # Phase F: Analysis (decision-making)
    Stage.RESULT_ANALYSIS: 2500,      # Analysis report
    Stage.RESEARCH_DECISION: 1000,    # PROCEED/REFINE/PIVOT decision
    
    # Phase G: Writing (large outputs)
    Stage.PAPER_OUTLINE: 2000,        # Outline structure
    Stage.PAPER_DRAFT: 8000,          # Full draft (5,000-6,500 words)
    Stage.PEER_REVIEW: 800,           # Score + brief reasoning (concise!)
    Stage.PAPER_REVISION: 6000,       # Revised draft
    
    # Phase H: Finalization (verification)
    Stage.QUALITY_GATE: 500,          # Pass/fail + notes (very concise)
    Stage.KNOWLEDGE_ARCHIVE: 1500,    # Archive summary
    Stage.EXPORT_PUBLISH: 1000,       # Export confirmation
    Stage.CITATION_VERIFY: 2000,      # Verification report
}

# Default limit for unknown stages
DEFAULT_TOKEN_LIMIT = 4000


def get_stage_token_limit(stage: Stage | int | str) -> int:
    """Get token limit for a specific stage.
    
    Args:
        stage: Stage enum, stage number, or stage name
        
    Returns:
        Maximum token limit for the stage
        
    Example:
        >>> get_stage_token_limit(Stage.HYPOTHESIS_GEN)
        2000
        >>> get_stage_token_limit(8)
        2000
        >>> get_stage_token_limit("HYPOTHESIS_GEN")
        2000
    """
    # Convert to Stage enum if needed
    if isinstance(stage, int):
        try:
            stage = Stage(stage)
        except ValueError:
            return DEFAULT_TOKEN_LIMIT
    elif isinstance(stage, str):
        try:
            stage = Stage[stage.upper()]
        except KeyError:
            return DEFAULT_TOKEN_LIMIT
    
    # Look up limit
    return OUTPUT_TOKEN_LIMITS.get(stage, DEFAULT_TOKEN_LIMIT)


def get_all_limits() -> dict[str, int]:
    """Get all token limits as dictionary.
    
    Returns:
        Dictionary mapping stage names to token limits
        
    Example:
        >>> limits = get_all_limits()
        >>> limits["HYPOTHESIS_GEN"]
        2000
    """
    return {stage.name: limit for stage, limit in OUTPUT_TOKEN_LIMITS.items()}


def validate_response_length(content: str, stage: Stage) -> tuple[bool, int, int]:
    """Validate that response doesn't exceed token limit.
    
    Args:
        content: Response content to validate
        stage: Pipeline stage
        
    Returns:
        Tuple of (is_valid, estimated_tokens, limit)
    """
    # Estimate tokens (4 chars ≈ 1 token for English text)
    estimated_tokens = len(content) // 4
    limit = get_stage_token_limit(stage)
    is_valid = estimated_tokens <= limit
    
    return is_valid, estimated_tokens, limit
