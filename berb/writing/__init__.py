"""Writing module for Berb.

Paper writing assistance with style mimicry, anti-AI editing,
parallel section writing, and humanitarian impact assessment.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .impact_assessment import (
    ContributionAssessment,
    HumanitarianImpactAssessment,
    assess_contribution_type,
)
from .parallel_writer import (
    PaperSections,
    ParallelSectionWriter,
    SectionPlan,
    write_paper_parallel,
)

__all__ = [
    # Humanitarian Impact
    "HumanitarianImpactAssessment",
    "ContributionAssessment",
    "assess_contribution_type",
    # Parallel Writing
    "ParallelSectionWriter",
    "SectionPlan",
    "PaperSections",
    "write_paper_parallel",
]
