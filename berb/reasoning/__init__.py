"""Reasoning methods for Berb autonomous research pipeline.

This module provides advanced reasoning methods for enhanced decision-making
throughout the 23-stage research pipeline.

Available Methods:
- Multi-Perspective: 4 perspectives (constructive, destructive, systemic, minimalist)
- Pre-Mortem Analysis: Failure identification and hardening
- Bayesian Reasoning: Probability-based belief updates
- Debate: Pro/Con arguments with judge evaluation
- Dialectical: Thesis/Antithesis/Aufhebung synthesis
- Research: Iterative search and synthesis
- Socratic: Question-driven understanding
- Scientific: Hypothesis generation and testing
- Jury: Orchestrated multi-agent evaluation

Usage:
    from berb.reasoning import (
        MultiPerspectiveMethod,
        PreMortemMethod,
        BayesianMethod,
    )
    
    # Multi-perspective analysis
    method = MultiPerspectiveMethod(router)
    result = await method.execute(context)
    
    # Pre-mortem failure analysis
    pm = PreMortemMethod()
    result = await pm.execute(context)
    
    # Bayesian reasoning
    bayesian = BayesianMethod(router)
    result = await bayesian.execute(context)

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from berb.reasoning.base import (
    ReasoningMethod,
    ReasoningResult,
    ReasoningContext,
    MethodType,
    create_context,
)
from berb.reasoning.multi_perspective import (
    MultiPerspectiveMethod,
    PerspectiveType,
    PerspectiveCandidate,
    PerspectiveScore,
)
from berb.reasoning.pre_mortem import (
    PreMortemMethod,
    FailureNarrative,
    RootCause,
    EarlySignal,
)
from berb.reasoning.bayesian import (
    BayesianMethod,
    Hypothesis,
    Evidence,
    BayesianResult,
)

__all__ = [
    # Base classes
    "ReasoningMethod",
    "ReasoningResult",
    "ReasoningContext",
    "MethodType",
    "create_context",
    
    # Multi-Perspective
    "MultiPerspectiveMethod",
    "PerspectiveType",
    "PerspectiveCandidate",
    "PerspectiveScore",
    
    # Pre-Mortem
    "PreMortemMethod",
    "FailureNarrative",
    "RootCause",
    "EarlySignal",
    
    # Bayesian
    "BayesianMethod",
    "Hypothesis",
    "Evidence",
    "BayesianResult",
]
