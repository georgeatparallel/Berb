"""Pipeline core — 23-stage research pipeline.

Includes improvement loop for iterative paper refinement
with Bayesian decision making and Iterative reasoning.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .hallucination_detector import (
    HallucinationDetector,
    HallucinationReport,
    CitationVerification,
    ClaimVerification,
    verify_paper_for_hallucinations,
)
from .improvement_loop import (
    AutonomousImprovementLoop,
    ImprovementLoopConfig,
    ImprovementResult,
    ScoreProgression,
    RoundResult,
    ClaimTracker,
    ClaimRecord,
    ClaimVerdict,
    FixType,
    ClassifiedWeakness,
    ComputeGuard,
    improve_paper,
)
from .bayesian_improvement_loop import (
    BayesianImprovementLoop,
    BayesianImprovementConfig,
    QualityBelief,
    IterativeFixPlanner,
)

__all__ = [
    # Hallucination detection
    "HallucinationDetector",
    "HallucinationReport",
    "CitationVerification",
    "ClaimVerification",
    "verify_paper_for_hallucinations",
    # Improvement loop
    "AutonomousImprovementLoop",
    "ImprovementLoopConfig",
    "ImprovementResult",
    "ScoreProgression",
    "RoundResult",
    "ClaimTracker",
    "ClaimRecord",
    "ClaimVerdict",
    "FixType",
    "ClassifiedWeakness",
    "ComputeGuard",
    "improve_paper",
    # Bayesian improvement
    "BayesianImprovementLoop",
    "BayesianImprovementConfig",
    "QualityBelief",
    "IterativeFixPlanner",
]
