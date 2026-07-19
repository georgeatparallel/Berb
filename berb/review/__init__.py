"""Automated peer review for Berb papers.

Implements 5-reviewer ensemble + Area Chair meta-review
for robust paper quality assessment.

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

__all__ = [
    # Ensemble review
    "AutomatedReviewerEnsemble",
    "Decision",
    "MetaReview",
    "Review",
    "ReviewDimension",
    "ReviewerPersona",
    "review_paper",
]
