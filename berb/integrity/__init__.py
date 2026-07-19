"""Research integrity subsystem for Berb.

Provides evidence registry, claim manifest, provenance tracking, and
integrity gate policies to prevent AI-generated research fabrication.

Sub-packages
------------
eval
    Hidden Consistent Evaluation (HCE) and finding reproduction tools.
    Import via ``berb.integrity.eval.hidden_eval`` or ``berb.integrity.eval.finding_reproduction``.
"""

from __future__ import annotations

from .claims import (
    ClaimManifest,
    ClaimRecord,
    ClaimType,
    ClaimVerdict,
)
from .evidence import (
    EvidenceRecord,
    EvidenceSource,
    EvidenceType,
)
from .registry import (
    VerifiedEvidenceRegistry,
)

__all__ = [
    "ClaimManifest",
    "ClaimRecord",
    "ClaimType",
    "ClaimVerdict",
    "EvidenceRecord",
    "EvidenceSource",
    "EvidenceType",
    "VerifiedEvidenceRegistry",
]
