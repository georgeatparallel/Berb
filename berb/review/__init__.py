"""Automated peer review for Berb papers.

Implements 5-reviewer ensemble + Area Chair meta-review
and cross-model review for unbiased evaluation.
Enhanced with Jury reasoning for multi-dimensional evaluation.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .ensemble import (
    AutomatedReviewerEnsemble,
    Decision,
    MetaReview,
    Review,
    ReviewDimension,
    ReviewerPersona,
    review_paper,
)
from .cross_model_reviewer import (
    CrossModelReviewer,
    CrossModelReviewConfig,
    CrossModelReviewConfigPreset,
    ReviewVerdict,
    WeaknessSeverity,
    Weakness,
    ReviewResult,
    ImprovementDelta,
    get_review_config_for_generation,
)
from .jury_reviewer import (
    JuryCrossModelReviewer,
    JuryReviewConfig,
    MultiJuryReviewer,
    MultiJuryReviewConfig,
)

__all__ = [
    # Ensemble review
    "AutomatedReviewerEnsemble",
    "Decision",
    "MetaReview",
    "Review",
    "ReviewDimension",
    "ReviewerPersona",
    "review_paper",
    # Cross-model review
    "CrossModelReviewer",
    "CrossModelReviewConfig",
    "CrossModelReviewConfigPreset",
    "ReviewVerdict",
    "WeaknessSeverity",
    "Weakness",
    "ReviewResult",
    "ImprovementDelta",
    "get_review_config_for_generation",
    # Jury review
    "JuryCrossModelReviewer",
    "JuryReviewConfig",
    "MultiJuryReviewer",
    "MultiJuryReviewConfig",
]
