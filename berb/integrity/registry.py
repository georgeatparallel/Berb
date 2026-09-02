"""Evidence registry — machine-readable store for all research provenance.

The ``VerifiedEvidenceRegistry`` mirrors the numeric ``VerifiedRegistry``
and adds support for non-numeric evidence (datasets, methods, figures,
source snippets, etc.).  It persists as ``evidence_registry.json`` in the
run directory.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from berb.integrity.evidence import (
    EvidenceRecord,
    EvidenceSource,
    EvidenceType,
    make_evidence_id,
)

logger = logging.getLogger(__name__)

# Default output file name
EVIDENCE_REGISTRY_FILE = "evidence_registry.json"


@dataclass
class VerifiedEvidenceRegistry:
    """Registry of all verified evidence produced during a pipeline run.

    Behaves as a dict-like store of ``EvidenceRecord`` objects, keyed by
    ``evidence_id``.  Provides load/save/merge helpers and a factory that
    builds the registry by scanning the run directory.
    """

    records: dict[str, EvidenceRecord] = field(default_factory=dict)
    """Evidence records keyed by evidence_id."""

    # ------------------------------------------------------------------
    # Lookup & query
    # ------------------------------------------------------------------

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        """Look up a record by ID."""
        return self.records.get(evidence_id)

    def lookup(self, evidence_id: str) -> EvidenceRecord | None:
        """Alias for ``get``."""
        return self.get(evidence_id)

    def find(
        self,
        *,
        evidence_type: EvidenceType | None = None,
        stage: int | None = None,
        label: str | None = None,
    ) -> list[EvidenceRecord]:
        """Return matching records by optional filters."""
        results: list[EvidenceRecord] = []
        for rec in self.records.values():
            if evidence_type is not None and rec.evidence_type != evidence_type:
                continue
            if stage is not None and rec.source.stage != stage:
                continue
            if label is not None and label not in (rec.label or ""):
                continue
            results.append(rec)
        return results

    def find_by_value(self, value: Any) -> list[EvidenceRecord]:
        """Return records whose normalised value matches *value*."""
        needle = EvidenceRecord._normalise_value(value)
        return [
            r for r in self.records.values() if EvidenceRecord._normalise_value(r.value) == needle
        ]

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_record(self, record: EvidenceRecord) -> str:
        """Add a record, deduplicating by content_hash.

        Returns the evidence_id (existing or newly created).
        """
        # Deduplicate by content_hash
        for existing in self.records.values():
            if existing.content_hash == record.content_hash:
                return existing.evidence_id
        eid = record.evidence_id or make_evidence_id()
        record.evidence_id = eid
        self.records[eid] = record
        return eid

    def merge(self, other: VerifiedEvidenceRegistry) -> int:
        """Merge records from *other*, returning count of newly added."""
        count = 0
        for rec in other.records.values():
            existing_id = self.add_record(rec)
            if existing_id == rec.evidence_id:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {
            "records": [rec.to_dict() for rec in self.records.values()],
            "record_count": len(self.records),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerifiedEvidenceRegistry:
        """Restore from a dict produced by ``to_dict``."""
        reg = cls()
        for item in data.get("records", ()):
            try:
                rec = EvidenceRecord.from_dict(item)
                reg.records[rec.evidence_id] = rec
            except (KeyError, ValueError, TypeError):
                logger.warning("Skipping unparseable evidence record: %s", str(item)[:120])
        return reg

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def save(self, path: Path) -> Path:
        """Write evidence registry as JSON to *path*."""
        path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        logger.info(
            "Saved evidence registry (%d records) to %s",
            len(self.records),
            path,
        )
        return path

    @classmethod
    def load(cls, path: Path) -> VerifiedEvidenceRegistry:
        """Load evidence registry from a JSON file at *path*.

        A missing file is a normal first-run state and returns an empty
        registry. A file that exists but fails to parse is a real
        corruption bug — surfacing it as an empty registry would silently
        tell every downstream integrity gate "no evidence exists" instead
        of "evidence_registry.json is broken," so this raises instead.
        """
        if not path.is_file():
            logger.debug("No evidence registry found at %s", path)
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ------------------------------------------------------------------
    # Factory: build from run directory
    # ------------------------------------------------------------------

    @classmethod
    def from_run_dir(
        cls,
        run_dir: Path,
        *,
        verbose: bool = False,
    ) -> VerifiedEvidenceRegistry:
        """Scan *run_dir* and build a registry from all available evidence.

        Currently mirrors numeric values from ``VerifiedRegistry``
        (experiment-derived values).  Future phases will add evidence from
        literature, analysis, figure generation, and dataset-access stages.
        """
        reg = cls()

        # 1. Numeric evidence from experiment artifacts
        _add_experiment_evidence(reg, run_dir)

        # 2. Literature evidence from knowledge cards (future)

        # 3. Analysis evidence (future)

        # 4. Figure / table evidence (future)

        if verbose:
            logger.info(
                "from_run_dir: %d evidence records (%s)",
                len(reg.records),
                (
                    ", ".join(sorted({r.evidence_type.value for r in reg.records.values()}))
                    if reg.records
                    else "none"
                ),
            )
        return reg


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------


def _add_experiment_evidence(
    reg: VerifiedEvidenceRegistry,
    run_dir: Path,
) -> None:
    """Mirror values from the numeric VerifiedRegistry as evidence records."""
    try:
        from berb.pipeline.verified_registry import (
            VerifiedRegistry as _NumericRegistry,  # noqa: N814
        )
    except ImportError:
        logger.debug("Cannot import VerifiedRegistry — skipping numeric evidence")
        return

    # Build numeric registry using best_only=True (cleanest ground truth)
    vr = _NumericRegistry.from_run_dir(run_dir, best_only=True)
    if not vr.values:
        logger.debug("No numeric verified values found in %s", run_dir)
        return

    # Register each value as a METRIC evidence record
    for value, source_desc in vr.values.items():
        rec = EvidenceRecord(
            evidence_id=make_evidence_id(),
            evidence_type=EvidenceType.METRIC,
            value=value,
            source=EvidenceSource(
                stage=14,  # RESULT_ANALYSIS
                artifact_path="experiment_summary.json",
                source_description=source_desc,
            ),
            label=source_desc.split(".")[-1] if "." in source_desc else source_desc,
            metadata={"provenance_key": source_desc},
        )
        reg.add_record(rec)

    # Register condition names as METHOD_IMPLEMENTATION evidence
    for cond_name in sorted(vr.condition_names):
        rec = EvidenceRecord(
            evidence_id=make_evidence_id(),
            evidence_type=EvidenceType.METHOD_IMPLEMENTATION,
            value=cond_name,
            source=EvidenceSource(
                stage=14,
                artifact_path="experiment_summary.json",
                source_description=f"condition:{cond_name}",
            ),
            label=cond_name,
            metadata={"condition_name": cond_name},
        )
        reg.add_record(rec)

    # Register training config as RUN_CONFIG evidence
    for cfg_key, cfg_val in (vr.training_config or {}).items():
        if cfg_val is not None:
            rec = EvidenceRecord(
                evidence_id=make_evidence_id(),
                evidence_type=EvidenceType.RUN_CONFIG,
                value={cfg_key: cfg_val},
                source=EvidenceSource(
                    stage=14,
                    artifact_path="experiment_summary.json",
                    source_description=f"training_config.{cfg_key}",
                ),
                label=cfg_key,
                metadata={"config_key": cfg_key, "config_value": str(cfg_val)},
            )
            reg.add_record(rec)

    # Register condition-level stats (mean, std) as METRIC
    for cond_name, cond_result in vr.conditions.items():
        if cond_result.mean is not None:
            rec = EvidenceRecord(
                evidence_id=make_evidence_id(),
                evidence_type=EvidenceType.METRIC,
                value=cond_result.mean,
                source=EvidenceSource(
                    stage=14,
                    artifact_path="experiment_summary.json",
                    source_description=f"{cond_name}.mean",
                ),
                label=f"{cond_name}_mean",
                metadata={"condition_name": cond_name, "stat": "mean"},
            )
            reg.add_record(rec)
        if cond_result.std is not None and cond_result.std > 0:
            rec = EvidenceRecord(
                evidence_id=make_evidence_id(),
                evidence_type=EvidenceType.METRIC,
                value=cond_result.std,
                source=EvidenceSource(
                    stage=14,
                    artifact_path="experiment_summary.json",
                    source_description=f"{cond_name}.std",
                ),
                label=f"{cond_name}_std",
                metadata={"condition_name": cond_name, "stat": "std"},
            )
            reg.add_record(rec)
