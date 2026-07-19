"""Research integrity subsystem for Berb.

Provides evidence registry, claim manifest, provenance tracking, and
integrity gate policies to prevent AI-generated research fabrication.
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
