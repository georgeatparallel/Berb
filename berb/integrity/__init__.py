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

from .anchors import (
    MAX_ANCHOR_VALUE_CHARS,
    Anchor,
    AnchorKind,
    MarkerRef,
    make_anchor,
    parse_markers,
    strip_markers,
    verify_anchors,
)
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
from .findings import (
    CheckId,
    Finding,
    Severity,
    gates,
)
from .registry import (
    VerifiedEvidenceRegistry,
)
from .revision_guard import (
    conserved_tokens,
)
from .uncited import (
    SentenceRef,
    detect_uncited,
    is_uncited_assertion,
    split_sentences,
)

__all__ = [
    "MAX_ANCHOR_VALUE_CHARS",
    "Anchor",
    "AnchorKind",
    "CheckId",
    "ClaimManifest",
    "ClaimRecord",
    "ClaimType",
    "ClaimVerdict",
    "EvidenceRecord",
    "EvidenceSource",
    "EvidenceType",
    "Finding",
    "MarkerRef",
    "SentenceRef",
    "Severity",
    "VerifiedEvidenceRegistry",
    "conserved_tokens",
    "detect_uncited",
    "gates",
    "is_uncited_assertion",
    "make_anchor",
    "parse_markers",
    "split_sentences",
    "strip_markers",
    "verify_anchors",
]
