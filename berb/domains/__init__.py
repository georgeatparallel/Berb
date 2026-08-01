"""Universal cross-domain research code generation framework.

This package provides domain detection, prompt adaptation, and experiment
schema generalization so the pipeline can generate code for any
computational research domain — not just ML/AI.

Includes specialized modules for:
- General domain detection and adaptation

The physics/ and chaos/ numerical-library subpackages are DEPRECATED (D-01,
2026-07-19): zero production callers, scheduled for removal. They are no longer
re-exported here so importing this package does not pull in deprecated code.
Import them directly (``from berb.domains import chaos``) if genuinely needed.
"""

from berb.domains.detector import DomainProfile, detect_domain

__all__ = [
    "DomainProfile",
    "detect_domain",
]
