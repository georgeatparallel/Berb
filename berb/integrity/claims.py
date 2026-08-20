"""Claim manifest models for the Berb integrity subsystem.

A claim manifest records every claim extracted from a paper draft, along
with optional links to supporting evidence in the registry.  It persists
as ``claim_manifest.json`` and is consumed by integrity gates.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ClaimType(StrEnum):
    """Taxonomy of research claims found in a paper."""

    EMPIRICAL = "empirical"
    """Reports a numeric result (accuracy, loss, runtime, etc.)."""

    COMPARATIVE = "comparative"
    """Claims superiority / equivalence / difference vs a baseline."""

    CAUSAL = "causal"
    """X causes / improves / reduces Y."""

    NOVELTY = "novelty"
    """Claims first, state-of-the-art, or novel contribution."""

    METHODOLOGICAL = "methodological"
    """Describes a method, algorithm, or implementation detail."""

    CITATION = "citation"
    """Attributes a claim or concept to a cited source."""

    DATASET = "dataset"
    """Claims about dataset provenance, size, or characteristics."""

    LIMITATION = "limitation"
    """Acknowledges a limitation or negative result."""

    BACKGROUND = "background"
    """Background or introductory statement that needs no verification."""

    UNKNOWN = "unknown"
    """Could not be classified."""


class ClaimVerdict(StrEnum):
    """Support verdict for a single claim."""

    SUPPORTED = "supported"
    """Evidence exists matching this claim."""

    UNSUPPORTED = "unsupported"
    """No matching evidence found."""

    CANNOT_DETERMINE = "cannot_determine"
    """Classifier could not determine support (ambiguous)."""

    NOT_CHECKED = "not_checked"
    """Verdict not yet computed (best-effort manifest)."""

    INCONCLUSIVE = "inconclusive"
    """Underpowered test or split instability — absence of evidence is NOT
    evidence of absence.  Never assign REFUTED from an underpowered test."""

    UNSPLITTABLE = "unsplittable"
    """Effect size cannot be checked against a held-out test split because
    the dataset was too small to partition.  Disclosed in limitations."""


@dataclass
class ClaimRecord:
    """A single claim extracted from the paper."""

    claim_id: str
    """Unique identifier (UUID4)."""

    text: str
    """The claim text (sentence or clause)."""

    claim_type: ClaimType
    """Classification of the claim."""

    section: str = ""
    """Section name where the claim appears."""

    line_number: int = 0
    """Approximate line number in the source document."""

    evidence_ids: list[str] = field(default_factory=list)
    """IDs of evidence records that support this claim (best-effort)."""

    confidence: str = "medium"
    """Classifier confidence: ``high``, ``medium``, or ``low``."""

    verdict: ClaimVerdict = ClaimVerdict.NOT_CHECKED
    """Support verdict."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Arbitrary metadata (extracted values, matched evidence keys, etc.)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "claim_type": self.claim_type.value,
            "section": self.section,
            "line_number": self.line_number,
            "evidence_ids": self.evidence_ids,
            "confidence": self.confidence,
            "verdict": self.verdict.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClaimRecord:
        """Deserialise from a dict."""
        try:
            claim_type = ClaimType(data.get("claim_type", "unknown"))
        except ValueError:
            claim_type = ClaimType.UNKNOWN
        try:
            verdict = ClaimVerdict(data.get("verdict", "not_checked"))
        except ValueError:
            verdict = ClaimVerdict.NOT_CHECKED
        return cls(
            claim_id=data["claim_id"],
            text=data["text"],
            claim_type=claim_type,
            section=data.get("section", ""),
            line_number=int(data.get("line_number", 0)),
            evidence_ids=list(data.get("evidence_ids", [])),
            confidence=str(data.get("confidence", "medium")),
            verdict=verdict,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ClaimManifest:
    """Manifest of all claims extracted from a paper version."""

    paper_stage: str
    """Pipeline stage: ``draft``, ``revised``, or ``final``."""

    claims: list[ClaimRecord] = field(default_factory=list)
    """All claims found in this version."""

    generated_at: str = ""
    """ISO-8601 timestamp of manifest generation."""

    def add_claim(self, claim: ClaimRecord) -> None:
        """Add a claim, assigning a unique ID if missing."""
        if not claim.claim_id:
            claim.claim_id = uuid.uuid4().hex[:16]
        self.claims.append(claim)

    @property
    def total_claims(self) -> int:
        return len(self.claims)

    @property
    def supported_claims(self) -> int:
        return sum(1 for c in self.claims if c.verdict == ClaimVerdict.SUPPORTED)

    @property
    def unsupported_claims(self) -> int:
        return sum(1 for c in self.claims if c.verdict == ClaimVerdict.UNSUPPORTED)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {
            "paper_stage": self.paper_stage,
            "generated_at": self.generated_at,
            "total_claims": self.total_claims,
            "supported_claims": self.supported_claims,
            "unsupported_claims": self.unsupported_claims,
            "claims": [c.to_dict() for c in self.claims],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialise to pretty-printed JSON."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClaimManifest:
        """Restore from a dict produced by ``to_dict``."""
        manifest = cls(
            paper_stage=str(data.get("paper_stage", "draft")),
            generated_at=str(data.get("generated_at", "")),
        )
        for item in data.get("claims", ()):
            try:
                manifest.claims.append(ClaimRecord.from_dict(item))
            except (KeyError, ValueError, TypeError):
                logger.warning(
                    "Skipping unparseable claim in manifest: %s", str(item)[:120]
                )
        return manifest

    @classmethod
    def load(cls, path: str | Path) -> ClaimManifest:
        """Load from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def save(self, path: str | Path) -> Path:
        """Save to a JSON file."""
        p = Path(path)
        p.write_text(self.to_json(), encoding="utf-8")
        return p
