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
    # Option 1: Direct import (for one-off usage)
    from berb.reasoning import MultiPerspectiveMethod
    method = MultiPerspectiveMethod(router)
    result = await method.execute(context)

    # Option 2: Registry singleton (recommended for reuse)
    from berb.reasoning.registry import get_reasoner, create_reasoner, list_reasoners
    
    # Get singleton instance (same instance returned on subsequent calls)
    method = get_reasoner("multi_perspective", router)
    result = await method.execute(context)
    
    # Create new instance (always fresh)
    method = create_reasoner("debate", llm_client, num_arguments=5)
    result = await method.execute(context)
    
    # List available methods
    print(list_reasoners())  # ['multi_perspective', 'pre_mortem', ...]

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
from berb.reasoning.debate import (
    DebateMethod,
    Argument,
    DebateResult,
)
from berb.reasoning.dialectical import (
    DialecticalMethod,
    DialecticalPosition,
    DialecticalResult,
)
from berb.reasoning.research import (
    ResearchMethod,
    ResearchIteration,
    ResearchResult,
)
from berb.reasoning.socratic import (
    SocraticMethod,
    SocraticQuestion,
    SocraticResult,
)
from berb.reasoning.scientific import (
    ScientificMethod,
    Hypothesis as ScientificHypothesis,
    ExperimentDesign,
    ScientificResult,
)
from berb.reasoning.jury import (
    JuryMethod,
    Juror,
    JurorRole,
    JuryResult,
)
from berb.reasoning.registry import (
    ReasonerRegistry,
    get_reasoner,
    create_reasoner,
    list_reasoners,
)

__all__ = [
    # Base classes
    "ReasoningMethod",
    "ReasoningResult",
    "ReasoningContext",
    "MethodType",
    "create_context",

    # Registry (recommended usage)
    "ReasonerRegistry",
    "get_reasoner",
    "create_reasoner",
    "list_reasoners",

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

    # Debate
    "DebateMethod",
    "Argument",
    "DebateResult",

    # Dialectical
    "DialecticalMethod",
    "DialecticalPosition",
    "DialecticalResult",

    # Research
    "ResearchMethod",
    "ResearchIteration",
    "ResearchResult",

    # Socratic
    "SocraticMethod",
    "SocraticQuestion",
    "SocraticResult",

    # Scientific
    "ScientificMethod",
    "ScientificHypothesis",
    "ExperimentDesign",
    "ScientificResult",

    # Jury
    "JuryMethod",
    "Juror",
    "JurorRole",
    "JuryResult",
]
