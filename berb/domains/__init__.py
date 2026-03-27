"""Universal cross-domain research code generation framework.

This package provides domain detection, prompt adaptation, and experiment
schema generalization so the pipeline can generate code for any
computational research domain — not just ML/AI.

Includes specialized modules for:
- General domain detection and adaptation
- Physics domain (including chaos detection)
"""

from berb.domains.detector import DomainProfile, detect_domain

# Chaos detection tools (physics domain)
from berb.domains import chaos

__all__ = [
    "DomainProfile",
    "detect_domain",
    "chaos",
]
