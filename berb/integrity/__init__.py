"""Research integrity subsystem for Berb.

Provides evidence registry, claim manifest, provenance tracking, and
integrity gate policies to prevent AI-generated research fabrication.

Sub-packages
------------
eval
    Hidden Consistent Evaluation (HCE). Import via
    ``berb.integrity.eval.hidden_eval``.
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
from .causal_overclaim import (
    check_causal_overclaim,
    is_causal_overclaim,
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
    EPISTEMIC_DISCLAIMER,
    CheckId,
    Finding,
    Severity,
    gates,
)
from .hypothesis_lock import (
    check_hypothesis_lock,
)
from .registry import (
    VerifiedEvidenceRegistry,
)
from .revision_guard import (
    ClaimDriftCandidate,
    conserved_tokens,
    find_claim_drift_candidates,
    strength_advisory,
)
from .uncited import (
    SentenceRef,
    detect_uncited,
    is_uncited_assertion,
    split_sentences,
)

__all__ = [
    "EPISTEMIC_DISCLAIMER",
    "MAX_ANCHOR_VALUE_CHARS",
    "Anchor",
    "AnchorKind",
    "CheckId",
    "ClaimDriftCandidate",
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
    "check_causal_overclaim",
    "check_hypothesis_lock",
    "conserved_tokens",
    "detect_uncited",
    "find_claim_drift_candidates",
    "gates",
    "is_causal_overclaim",
    "is_uncited_assertion",
    "make_anchor",
    "parse_markers",
    "split_sentences",
    "strength_advisory",
    "strip_markers",
    "verify_anchors",
]
