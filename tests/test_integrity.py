"""Tests for the research integrity subsystem (berb/integrity/).

Covers evidence models, evidence registry, claim manifest, config, and
the best-effort draft claim extraction helpers.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from berb.config import IntegrityConfig, RCConfig
from berb.integrity import (
    ClaimManifest,
    ClaimRecord,
    ClaimType,
    ClaimVerdict,
    EvidenceRecord,
    EvidenceSource,
    EvidenceType,
    VerifiedEvidenceRegistry,
    make_anchor,
)
from berb.integrity.evidence import make_evidence_id
from berb.pipeline.stage_impls._paper_writing import (
    _build_draft_claim_manifest,
    _build_line_section_map,
    _classify_numeric_claim,
    _extract_dataset_claims,
    _extract_numeric_claims,
    _parse_draft_sections,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_run_dir():
    """Create a temporary run directory with minimal experiment data."""
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        exp_data = {
            "best_run": {
                "metrics": {
                    "primary_metric": 0.95,
                    "primary_metric_std": 0.02,
                    "DQN/0/accuracy": 0.94,
                    "DQN/1/accuracy": 0.96,
                    "PPO/0/accuracy": 0.91,
                    "PPO/1/accuracy": 0.93,
                }
            },
            "condition_summaries": {
                "DQN": {"metrics": {"accuracy": 0.95}},
                "PPO": {"metrics": {"accuracy": 0.92}},
            },
            "metrics_summary": {
                "accuracy": {"min": 0.91, "max": 0.96, "mean": 0.935},
            },
        }
        s14 = run_dir / "stage-14"
        s14.mkdir()
        (s14 / "experiment_summary.json").write_text(json.dumps(exp_data), encoding="utf-8")
        yield run_dir


@pytest.fixture
def sample_draft() -> str:
    return """# Title

## Introduction
This paper addresses the problem of image classification.

## Results
Our method achieves 95.3 accuracy on the CIFAR-10 benchmark.
This outperforms prior baselines by 3.2 points.
We used 10 random seeds for each experimental condition.

## Conclusion
We demonstrated the effectiveness of our proposed approach.
"""


# ---------------------------------------------------------------------------
# EvidenceRecord
# ---------------------------------------------------------------------------


class TestEvidenceRecord:
    def test_create_minimal(self) -> None:
        rec = EvidenceRecord(
            evidence_id="test01",
            evidence_type=EvidenceType.METRIC,
            value=0.95,
            source=EvidenceSource(stage=14, artifact_path="experiment_summary.json"),
        )
        assert rec.evidence_id == "test01"
        assert rec.evidence_type == EvidenceType.METRIC
        assert rec.value == 0.95
        assert rec.source.stage == 14
        assert rec.created_at != ""
        assert rec.content_hash != ""

    def test_auto_generate_id(self) -> None:
        rec = EvidenceRecord(
            evidence_id="",
            evidence_type=EvidenceType.METRIC,
            value=42.0,
            source=EvidenceSource(stage=12, artifact_path="runs/"),
        )
        assert len(rec.evidence_id) == 16

    def test_round_trip_dict(self) -> None:
        original = EvidenceRecord(
            evidence_id="rt01",
            evidence_type=EvidenceType.RUN_CONFIG,
            value={"learning_rate": 0.001, "batch_size": 64},
            source=EvidenceSource(
                stage=9,
                artifact_path="exp_plan.yaml",
                source_description="training config",
            ),
            label="hyperparams",
            metadata={"condition": "DQN"},
        )
        data = original.to_dict()
        restored = EvidenceRecord.from_dict(data)
        assert restored.evidence_id == original.evidence_id
        assert restored.evidence_type == original.evidence_type
        assert restored.value == original.value
        assert restored.source.stage == original.source.stage
        assert restored.label == original.label
        assert restored.metadata == original.metadata

    def test_deduplicate_hash(self) -> None:
        rec1 = EvidenceRecord(
            evidence_id="a",
            evidence_type=EvidenceType.METRIC,
            value=0.95,
            source=EvidenceSource(stage=14, artifact_path="x.json"),
        )
        rec2 = EvidenceRecord(
            evidence_id="b",
            evidence_type=EvidenceType.METRIC,
            value=0.95,
            source=EvidenceSource(stage=14, artifact_path="x.json"),
        )
        # Same content → same hash (even though ids differ)
        assert rec1.content_hash == rec2.content_hash

    def test_different_content_different_hash(self) -> None:
        rec1 = EvidenceRecord(
            evidence_id="a",
            evidence_type=EvidenceType.METRIC,
            value=0.95,
            source=EvidenceSource(stage=14, artifact_path="x.json"),
        )
        rec2 = EvidenceRecord(
            evidence_id="b",
            evidence_type=EvidenceType.METRIC,
            value=0.96,
            source=EvidenceSource(stage=14, artifact_path="x.json"),
        )
        assert rec1.content_hash != rec2.content_hash


# ---------------------------------------------------------------------------
# VerifiedEvidenceRegistry
# ---------------------------------------------------------------------------


class TestVerifiedEvidenceRegistry:
    def test_empty_registry(self) -> None:
        reg = VerifiedEvidenceRegistry()
        assert len(reg.records) == 0
        assert reg.get("nonexistent") is None

    def test_add_and_lookup(self) -> None:
        reg = VerifiedEvidenceRegistry()
        rec = EvidenceRecord(
            evidence_id="e001",
            evidence_type=EvidenceType.METRIC,
            value=0.95,
            source=EvidenceSource(stage=14, artifact_path="x.json"),
        )
        eid = reg.add_record(rec)
        assert eid == "e001"
        assert reg.get("e001") is not None
        assert reg.lookup("e001") is not None

    def test_add_deduplicate(self) -> None:
        reg = VerifiedEvidenceRegistry()
        rec1 = EvidenceRecord(
            evidence_id="a",
            evidence_type=EvidenceType.METRIC,
            value=0.95,
            source=EvidenceSource(stage=14, artifact_path="x.json"),
        )
        rec2 = EvidenceRecord(
            evidence_id="b",
            evidence_type=EvidenceType.METRIC,
            value=0.95,
            source=EvidenceSource(stage=14, artifact_path="x.json"),
        )
        eid1 = reg.add_record(rec1)
        eid2 = reg.add_record(rec2)
        # Same content → deduplicated (eid2 should return first id)
        assert eid2 == eid1

    def test_find_by_type(self) -> None:
        reg = VerifiedEvidenceRegistry()
        reg.add_record(
            EvidenceRecord(
                evidence_id="m1",
                evidence_type=EvidenceType.METRIC,
                value=0.9,
                source=EvidenceSource(stage=14, artifact_path="x.json"),
            )
        )
        reg.add_record(
            EvidenceRecord(
                evidence_id="m2",
                evidence_type=EvidenceType.METHOD_IMPLEMENTATION,
                value="DQN",
                source=EvidenceSource(stage=14, artifact_path="x.json"),
            )
        )
        metrics = reg.find(evidence_type=EvidenceType.METRIC)
        assert len(metrics) == 1
        methods = reg.find(evidence_type=EvidenceType.METHOD_IMPLEMENTATION)
        assert len(methods) == 1

    def test_find_by_stage(self) -> None:
        reg = VerifiedEvidenceRegistry()
        reg.add_record(
            EvidenceRecord(
                evidence_id="s9",
                evidence_type=EvidenceType.RUN_CONFIG,
                value={"lr": 0.001},
                source=EvidenceSource(stage=9, artifact_path="x.yaml"),
            )
        )
        reg.add_record(
            EvidenceRecord(
                evidence_id="s14",
                evidence_type=EvidenceType.METRIC,
                value=0.95,
                source=EvidenceSource(stage=14, artifact_path="x.json"),
            )
        )
        stage14 = reg.find(stage=14)
        assert len(stage14) == 1

    def test_save_load_round_trip(self, tmp_run_dir) -> None:
        reg = VerifiedEvidenceRegistry.from_run_dir(tmp_run_dir)
        assert len(reg.records) > 0

        path = tmp_run_dir / "evidence_registry.json"
        reg.save(path)
        assert path.is_file()

        loaded = VerifiedEvidenceRegistry.load(path)
        assert len(loaded.records) == len(reg.records)

        # Check a specific record
        original_ids = set(reg.records.keys())
        loaded_ids = set(loaded.records.keys())
        assert original_ids == loaded_ids

    def test_merge(self) -> None:
        reg1 = VerifiedEvidenceRegistry()
        reg1.add_record(
            EvidenceRecord(
                evidence_id="a",
                evidence_type=EvidenceType.METRIC,
                value=0.9,
                source=EvidenceSource(stage=14, artifact_path="x.json"),
            )
        )
        reg2 = VerifiedEvidenceRegistry()
        reg2.add_record(
            EvidenceRecord(
                evidence_id="b",
                evidence_type=EvidenceType.METHOD_IMPLEMENTATION,
                value="PPO",
                source=EvidenceSource(stage=14, artifact_path="x.json"),
            )
        )
        count = reg1.merge(reg2)
        assert count == 1
        assert len(reg1.records) == 2

    def test_from_run_dir(self, tmp_run_dir) -> None:
        reg = VerifiedEvidenceRegistry.from_run_dir(tmp_run_dir)
        assert len(reg.records) > 0

        metrics = reg.find(evidence_type=EvidenceType.METRIC)
        assert len(metrics) > 0

        methods = reg.find(evidence_type=EvidenceType.METHOD_IMPLEMENTATION)
        assert len(methods) >= 2  # DQN, PPO

    def test_from_run_dir_empty_dir(self, tmp_path) -> None:
        reg = VerifiedEvidenceRegistry.from_run_dir(tmp_path)
        assert len(reg.records) == 0  # no experiment data

    def test_find_by_value(self) -> None:
        reg = VerifiedEvidenceRegistry()
        reg.add_record(
            EvidenceRecord(
                evidence_id="v1",
                evidence_type=EvidenceType.METRIC,
                value=0.95,
                source=EvidenceSource(stage=14, artifact_path="x.json"),
            )
        )
        matches = reg.find_by_value(0.95)
        assert len(matches) == 1
        matches = reg.find_by_value(0.99)
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# IntegrityConfig
# ---------------------------------------------------------------------------


class TestIntegrityConfig:
    def test_default_mode_is_draft(self) -> None:
        cfg = IntegrityConfig()
        assert cfg.mode == "draft"

    def test_has_auto_strict_domains(self) -> None:
        cfg = IntegrityConfig()
        assert "biomedical" in cfg.auto_strict_domains
        assert "clinical" in cfg.auto_strict_domains
        assert "legal" in cfg.auto_strict_domains

    def test_rc_config_has_integrity(self) -> None:
        assert "integrity" in RCConfig.__dataclass_fields__

    def test_config_custom_values(self) -> None:
        cfg = IntegrityConfig(
            mode="submission",
            fail_on_unsupported_claims=True,
            fail_on_unverified_statistics=True,
        )
        assert cfg.mode == "submission"
        assert cfg.fail_on_unsupported_claims is True
        assert cfg.fail_on_unverified_statistics is True

    def test_strict_mode_config(self) -> None:
        cfg = IntegrityConfig(mode="strict")
        assert cfg.mode == "strict"


# ---------------------------------------------------------------------------
# ClaimManifest
# ---------------------------------------------------------------------------


class TestClaimManifest:
    def test_empty_manifest(self) -> None:
        manifest = ClaimManifest(paper_stage="draft")
        assert manifest.total_claims == 0
        assert manifest.supported_claims == 0
        assert manifest.unsupported_claims == 0

    def test_add_claim(self) -> None:
        manifest = ClaimManifest(paper_stage="draft")
        claim = ClaimRecord(
            claim_id="c001",
            text="Test claim.",
            claim_type=ClaimType.EMPIRICAL,
        )
        manifest.add_claim(claim)
        assert manifest.total_claims == 1
        assert manifest.claims[0].claim_id == "c001"

    def test_auto_assign_id(self) -> None:
        manifest = ClaimManifest(paper_stage="draft")
        claim = ClaimRecord(
            claim_id="",
            text="Auto ID.",
            claim_type=ClaimType.COMPARATIVE,
        )
        manifest.add_claim(claim)
        assert len(manifest.claims[0].claim_id) == 16

    def test_save_load_round_trip(self) -> None:
        manifest = ClaimManifest(paper_stage="draft")
        manifest.add_claim(
            ClaimRecord(
                claim_id="c1",
                text="Claim 1",
                claim_type=ClaimType.EMPIRICAL,
            )
        )
        manifest.add_claim(
            ClaimRecord(
                claim_id="c2",
                text="Claim 2",
                claim_type=ClaimType.COMPARATIVE,
            )
        )

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "claim_manifest.json"
            manifest.save(path)
            loaded = ClaimManifest.load(path)

        assert loaded.total_claims == 2
        assert loaded.claims[0].text == "Claim 1"
        assert loaded.claims[0].claim_type == ClaimType.EMPIRICAL

    def test_to_json_output(self) -> None:
        manifest = ClaimManifest(paper_stage="draft")
        manifest.add_claim(
            ClaimRecord(
                claim_id="c1",
                text="Claim 1",
                claim_type=ClaimType.EMPIRICAL,
            )
        )
        json_str = manifest.to_json()
        data = json.loads(json_str)
        assert data["paper_stage"] == "draft"
        assert data["total_claims"] == 1
        assert data["claims"][0]["claim_id"] == "c1"

    def test_verdict_counts(self) -> None:
        manifest = ClaimManifest(paper_stage="draft")
        manifest.add_claim(
            ClaimRecord(
                claim_id="c1",
                text="Supported",
                claim_type=ClaimType.EMPIRICAL,
                verdict=ClaimVerdict.SUPPORTED,
            )
        )
        manifest.add_claim(
            ClaimRecord(
                claim_id="c2",
                text="Unsupported",
                claim_type=ClaimType.EMPIRICAL,
                verdict=ClaimVerdict.UNSUPPORTED,
            )
        )
        assert manifest.supported_claims == 1
        assert manifest.unsupported_claims == 1


class TestClaimRecord:
    def test_minimal(self) -> None:
        claim = ClaimRecord(
            claim_id="c001",
            text="Test claim.",
            claim_type=ClaimType.EMPIRICAL,
        )
        assert claim.claim_id == "c001"
        assert claim.claim_type == ClaimType.EMPIRICAL
        assert claim.verdict == ClaimVerdict.NOT_CHECKED

    def test_round_trip(self) -> None:
        original = ClaimRecord(
            claim_id="c001",
            text="Our method achieves 95% accuracy.",
            claim_type=ClaimType.EMPIRICAL,
            section="Results",
            line_number=42,
            evidence_ids=["ev001", "ev002"],
            confidence="high",
            verdict=ClaimVerdict.SUPPORTED,
            metadata={"extracted_numbers": ["95"]},
        )
        data = original.to_dict()
        restored = ClaimRecord.from_dict(data)
        assert restored.claim_id == original.claim_id
        assert restored.text == original.text
        assert restored.claim_type == original.claim_type
        assert restored.section == original.section
        assert restored.verdict == original.verdict
        assert restored.metadata == original.metadata


# ---------------------------------------------------------------------------
# Draft claim extraction helpers
# ---------------------------------------------------------------------------


class TestDraftClaimExtraction:
    def test_parse_draft_sections(self, sample_draft) -> None:
        sections = _parse_draft_sections(sample_draft)
        assert "Introduction" in sections
        assert "Results" in sections
        assert "Conclusion" in sections

    def test_extract_numeric_claims(self, sample_draft) -> None:
        sections = _parse_draft_sections(sample_draft)
        manifest = ClaimManifest(paper_stage="draft")
        _extract_numeric_claims(sample_draft, sections, manifest, set())
        assert manifest.total_claims >= 2  # 95.3 and 3.2 and 10

        # Check classification
        types = {c.claim_type for c in manifest.claims}
        assert ClaimType.EMPIRICAL in types
        assert ClaimType.COMPARATIVE in types  # "outperforms"

    def test_numeric_claim_unsupported_without_evidence(self, sample_draft) -> None:
        sections = _parse_draft_sections(sample_draft)
        manifest = ClaimManifest(paper_stage="draft")
        _extract_numeric_claims(sample_draft, sections, manifest, set())
        for c in manifest.claims:
            if c.claim_type in (ClaimType.EMPIRICAL, ClaimType.COMPARATIVE):
                assert c.verdict == ClaimVerdict.UNSUPPORTED

    def test_numeric_claim_supported_with_evidence(self, sample_draft) -> None:
        sections = _parse_draft_sections(sample_draft)
        manifest = ClaimManifest(paper_stage="draft")
        # Provide 95.3 as a known value
        _extract_numeric_claims(sample_draft, sections, manifest, {95.3})
        # The 95.3 claim should be supported
        for c in manifest.claims:
            if "95.3" in c.text:
                assert c.verdict == ClaimVerdict.SUPPORTED

    def test_classify_numeric_claim(self) -> None:
        assert _classify_numeric_claim("Outperforms baselines", "Results") == ClaimType.COMPARATIVE
        assert _classify_numeric_claim("Accuracy 95%", "Results") == ClaimType.EMPIRICAL
        assert _classify_numeric_claim("Using ImageNet dataset", "Method") == ClaimType.DATASET
        assert _classify_numeric_claim("We run 10 experiments", "Setup") == ClaimType.EMPIRICAL

    def test_extract_dataset_claims(self) -> None:
        text = "We use the ImageNet dataset for evaluation.\nWe evaluate on CIFAR-100.\n"
        sections = {"Method": (0, 1)}
        manifest = ClaimManifest(paper_stage="draft")
        _extract_dataset_claims(text, sections, manifest)
        # At least one dataset claim (heuristic based on "we use X dataset")
        assert manifest.total_claims >= 1

    def test_build_line_section_map(self) -> None:
        sections = {"Intro": (0, 4), "Method": (5, 9)}
        section_map = _build_line_section_map(sections, 10)
        assert section_map[0] == "Intro"
        assert section_map[5] == "Method"
        assert section_map[9] == "Method"

    def test_build_draft_claim_manifest_writes_file(self, tmp_run_dir, sample_draft) -> None:
        # Regression test (audit §4.2): _build_draft_claim_manifest referenced
        # the module-level name ClaimManifest without importing it, raising
        # NameError on every call. The caller in generate_paper_draft() swallows
        # that exception (`except Exception: logger.debug(...)`), so the bug
        # never crashed the pipeline — it just silently produced no manifest.
        stage_dir = tmp_run_dir / "stage-17"
        stage_dir.mkdir()

        _build_draft_claim_manifest(sample_draft, tmp_run_dir, stage_dir)

        manifest_path = stage_dir / "claim_manifest.json"
        assert manifest_path.exists()
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert saved["paper_stage"] == "draft"
        assert len(saved["claims"]) >= 1


# ---------------------------------------------------------------------------
# Integration: end-to-end manifest building with evidence
# ---------------------------------------------------------------------------


class TestIntegrityIntegration:
    def test_build_manifest_from_run_dir(self, tmp_run_dir, sample_draft) -> None:
        """Verify that manifest building loads evidence and links claims."""
        # Pre-build evidence registry
        reg = VerifiedEvidenceRegistry.from_run_dir(tmp_run_dir)
        reg.save(tmp_run_dir / "evidence_registry.json")

        # Now simulate what Stage 17 would do
        sections = _parse_draft_sections(sample_draft)
        manifest = ClaimManifest(paper_stage="draft")

        evidence_reg = VerifiedEvidenceRegistry.load(tmp_run_dir / "evidence_registry.json")
        metric_values = {
            r.value for r in evidence_reg.records.values() if isinstance(r.value, (int, float))
        }

        _extract_numeric_claims(sample_draft, sections, manifest, metric_values)

        # Claims should exist
        assert manifest.total_claims > 0

        # The "95.3 accuracy on CIFAR-10 benchmark" may be classified as
        # DATASET (due to "benchmark" keyword) or EMPIRICAL.  In either
        # case, 95.3 is not in the 0.91-0.96 experiment data, so if it's
        # classified as EMPIRICAL it should be UNSUPPORTED.
        for c in manifest.claims:
            if "95.3" in c.text:
                if c.claim_type in (ClaimType.EMPIRICAL, ClaimType.COMPARATIVE):
                    assert c.verdict == ClaimVerdict.UNSUPPORTED
                break

    def test_evidence_registry_and_claim_manifest_coexist(self, tmp_run_dir, sample_draft) -> None:
        """Both artifacts can be produced from the same run directory."""
        # Build evidence registry
        reg = VerifiedEvidenceRegistry.from_run_dir(tmp_run_dir)
        reg.save(tmp_run_dir / "evidence_registry.json")

        # Build claim manifest
        sections = _parse_draft_sections(sample_draft)
        manifest = ClaimManifest(paper_stage="draft")
        _extract_numeric_claims(sample_draft, sections, manifest, set())
        manifest.save(tmp_run_dir / "claim_manifest.json")

        # Both files exist
        assert (tmp_run_dir / "evidence_registry.json").is_file()
        assert (tmp_run_dir / "claim_manifest.json").is_file()

        # They are valid JSON
        er = json.loads((tmp_run_dir / "evidence_registry.json").read_text(encoding="utf-8"))
        cm = json.loads((tmp_run_dir / "claim_manifest.json").read_text(encoding="utf-8"))
        assert er["record_count"] > 0
        assert cm["total_claims"] > 0


# ---------------------------------------------------------------------------
# Edge cases and error handling
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_evidence_registry_load_missing_file(self, tmp_path) -> None:
        reg = VerifiedEvidenceRegistry.load(tmp_path / "nonexistent.json")
        assert len(reg.records) == 0

    def test_evidence_registry_load_corrupt_file_raises(self, tmp_path) -> None:
        """A3-1 (hardening_plan_2026-08-13.md): a present-but-corrupt
        evidence_registry.json must raise, not silently look like "no
        evidence exists" to downstream integrity gates."""
        import json

        bad = tmp_path / "bad.json"
        bad.write_text("{invalid json}", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            VerifiedEvidenceRegistry.load(bad)

    def test_claim_manifest_empty_save_load(self) -> None:
        manifest = ClaimManifest(paper_stage="draft")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manifest.json"
            manifest.save(path)
            loaded = ClaimManifest.load(path)
        assert loaded.total_claims == 0

    def test_build_line_section_map_preamble(self) -> None:
        sections = {"Abstract": (3, 5)}
        section_map = _build_line_section_map(sections, 10)
        assert section_map[0] == "(preamble)"

    def test_make_evidence_id(self) -> None:
        eid = make_evidence_id()
        assert len(eid) == 16
        assert isinstance(eid, str)

    def test_evidence_type_values(self) -> None:
        """All enum values are valid strings."""
        for et in EvidenceType:
            assert isinstance(et.value, str)
            assert len(et.value) > 0


class TestClaimManifestAnchorSchema:
    """tasks/ars_integration_plan.md W1: ClaimRecord.anchors and
    ClaimManifest.schema_version are additive fields — a v1 manifest on
    disk (neither key present) must load unchanged."""

    def test_v1_manifest_with_no_anchors_key_loads_fine(self) -> None:
        v1_data = {
            "paper_stage": "draft",
            "generated_at": "2026-01-01T00:00:00Z",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Accuracy improved by 10%.",
                    "claim_type": "empirical",
                    # no "anchors" key at all — a real pre-W1 file
                }
            ],
        }
        manifest = ClaimManifest.from_dict(v1_data)
        assert manifest.schema_version == 1
        assert manifest.total_claims == 1
        assert manifest.claims[0].anchors == ()

    def test_fresh_manifest_writes_current_schema_version(self) -> None:
        manifest = ClaimManifest(paper_stage="draft")
        assert manifest.to_dict()["schema_version"] == 2

    def test_claim_record_anchors_round_trip(self) -> None:
        anchor = make_anchor("he2016deep", "quote", "deep residual learning")
        assert anchor is not None
        record = ClaimRecord(
            claim_id="c1",
            text="Accuracy improved.",
            claim_type=ClaimType.EMPIRICAL,
            anchors=(anchor,),
        )
        restored = ClaimRecord.from_dict(record.to_dict())
        assert restored.anchors == (anchor,)

    def test_malformed_anchor_entry_is_skipped_not_fatal(self) -> None:
        data = {
            "claim_id": "c1",
            "text": "x",
            "claim_type": "empirical",
            "anchors": [
                {"cite_key": "ok2020x", "kind": "quote", "value": "v", "anchor_id": "abc123"},
                {"cite_key": "../evil", "kind": "quote", "value": "v", "anchor_id": "def456"},
                "not even a dict",
                {"kind": "bogus"},
            ],
        }
        record = ClaimRecord.from_dict(data)
        assert len(record.anchors) == 1
        assert record.anchors[0].cite_key == "ok2020x"

    def test_manifest_save_load_round_trip_preserves_anchors(self, tmp_path) -> None:
        anchor = make_anchor("he2016deep", "quote", "deep residual learning")
        assert anchor is not None
        manifest = ClaimManifest(paper_stage="draft")
        manifest.add_claim(
            ClaimRecord(
                claim_id="",
                text="Accuracy improved.",
                claim_type=ClaimType.EMPIRICAL,
                anchors=(anchor,),
            )
        )
        path = tmp_path / "manifest.json"
        manifest.save(path)
        loaded = ClaimManifest.load(path)
        assert loaded.schema_version == 2
        assert loaded.claims[0].anchors == (anchor,)
