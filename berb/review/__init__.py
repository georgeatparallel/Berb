"""Automated peer review for Berb papers.

Implements 5-reviewer ensemble + Area Chair meta-review,
cross-model review for unbiased evaluation, and council mode
for multi-model parallel analysis.
Enhanced with Jury reasoning for multi-dimensional evaluation.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .council_mode import (
    CouncilMode,
    CouncilReport,
    CouncilSynthesis,
    CouncilConfig,
    run_council,
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
from .ensemble import (
    AutomatedReviewerEnsemble,
    Decision,
    MetaReview,
    Review,
    ReviewDimension,
    ReviewerPersona,
    review_paper,
)
from .jury_reviewer import (
    JuryCrossModelReviewer,
    JuryReviewConfig,
    MultiJuryReviewer,
    MultiJuryReviewConfig,
)

__all__ = [
    # Council mode (NEW)
    "CouncilMode",
    "CouncilReport",
    "CouncilSynthesis",
    "CouncilConfig",
    "run_council",
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
    # Ensemble review
    "AutomatedReviewerEnsemble",
    "Decision",
    "MetaReview",
    "Review",
    "ReviewDimension",
    "ReviewerPersona",
    "review_paper",
    # Jury review
    "JuryCrossModelReviewer",
    "JuryReviewConfig",
    "MultiJuryReviewer",
    "MultiJuryReviewConfig",
]
