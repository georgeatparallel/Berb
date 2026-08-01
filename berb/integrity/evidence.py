"""Evidence record models for the Berb integrity subsystem.

Defines the machine-readable evidence schema that grounds all claims
in a research paper to verifiable provenance.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EvidenceType(StrEnum):
    """Categorisation of a piece of registered evidence."""

    METRIC = "metric"
    """Numeric result from experiment artifacts (accuracy, loss, etc.)."""

    STATISTICAL_TEST = "statistical_test"
    """p-value, confidence interval, test name, effect size."""

    DATASET_ACCESS = "dataset_access"
    """Dataset / database acquisition and access metadata."""

    METHOD_IMPLEMENTATION = "method_implementation"
    """Methods, baselines, ablations actually implemented and run."""

    RUN_CONFIG = "run_config"
    """Seeds, trial count, hyperparameters, hardware, training config."""

    FIGURE = "figure"
    """Generated figure / table with data and script provenance."""

    SOURCE_SNIPPET = "source_snippet"
    """Literature excerpt supporting a claim."""

    ANALYSIS_FINDING = "analysis_finding"
    """Derived finding from Stage 14 analysis."""

    LIMITATION = "limitation"
    """Explicitly registered limitation or negative result."""


@dataclass
class EvidenceSource:
    """Provenance of where an evidence record came from."""

    stage: int
    """Pipeline stage number that produced this evidence."""

    artifact_path: str
    """Relative path to the artifact that contains the raw evidence."""

    source_description: str = ""
    """Human-readable description of the source."""


@dataclass
class EvidenceRecord:
    """A single piece of verified evidence in the integrity registry.

    Each record represents one fact grounded in real pipeline execution
    (experiment, literature, analysis, etc.) that a paper claim can
    reference.
    """

    evidence_id: str
    """Unique identifier (UUID4)."""

    evidence_type: EvidenceType
    """Category of evidence."""

    value: Any
    """The actual evidence value (numeric, string, dict, list, etc.)."""

    source: EvidenceSource
    """Provenance metadata."""

    label: str = ""
    """Optional short label for display / CLI output."""

    created_at: str = ""
    """ISO-8601 timestamp; auto-set if empty."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Arbitrary key-value metadata (condition name, metric key, etc.)."""

    content_hash: str = ""
    """SHA-256 of canonical JSON content for deduplication."""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        if not self.evidence_id:
            self.evidence_id = uuid.uuid4().hex[:16]
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """SHA-256 hash of type + normalised value."""
        canonical = json.dumps(
            {
                "type": self.evidence_type.value,
                "value": self._normalise_value(self.value),
                "stage": self.source.stage,
                "artifact_path": self.source.artifact_path,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _normalise_value(value: Any) -> Any:
        """Round floats for stable hashing."""
        if isinstance(value, float):
            return round(value, 10)
        if isinstance(value, dict):
            return {k: EvidenceRecord._normalise_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [EvidenceRecord._normalise_value(v) for v in value]
        return value

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "value": self.value,
            "source": {
                "stage": self.source.stage,
                "artifact_path": self.source.artifact_path,
                "source_description": self.source.source_description,
            },
            "label": self.label,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRecord:
        """Deserialise from a dict (produced by ``to_dict``)."""
        src = data.get("source", {})
        return cls(
            evidence_id=data.get("evidence_id", ""),
            evidence_type=EvidenceType(data["evidence_type"]),
            value=data["value"],
            source=EvidenceSource(
                stage=int(src.get("stage", 0)),
                artifact_path=src.get("artifact_path", ""),
                source_description=src.get("source_description", ""),
            ),
            label=data.get("label", ""),
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
            content_hash=data.get("content_hash", ""),
        )


def make_evidence_id() -> str:
    """Generate a short unique evidence ID."""
    return uuid.uuid4().hex[:16]
