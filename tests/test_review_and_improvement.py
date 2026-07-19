"""Unit tests for Berb review and integrity subsystems.

Ports of ClaimTracker tests onto the live integrity.ClaimManifest.
Cross-model review and improvement loop tests removed (modules deleted in F1).

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import pytest

from berb.integrity import ClaimManifest, ClaimRecord, ClaimType, ClaimVerdict
from berb.integrity.claims import ClaimRecord as ClaimRecordClass


class TestClaimVerdict:
    """Test ClaimVerdict enum (live copy in berb.integrity)."""

    def test_verdict_values(self):
        """Test verdict values."""
        assert ClaimVerdict.SUPPORTED.value == "supported"
        assert ClaimVerdict.UNSUPPORTED.value == "unsupported"
        assert ClaimVerdict.CANNOT_DETERMINE.value == "cannot_determine"
        assert ClaimVerdict.NOT_CHECKED.value == "not_checked"


class TestClaimType:
    """Test ClaimType enum."""

    def test_type_values(self):
        """Test type values."""
        assert ClaimType.EMPIRICAL.value == "empirical"
        assert ClaimType.COMPARATIVE.value == "comparative"
        assert ClaimType.CAUSAL.value == "causal"
        assert ClaimType.NOVELTY.value == "novelty"
        assert ClaimType.CITATION.value == "citation"
        assert ClaimType.LIMITATION.value == "limitation"
        assert ClaimType.BACKGROUND.value == "background"


class TestClaimRecord:
    """Test ClaimRecord dataclass."""

    def test_create_claim_record(self):
        """Test creating a claim record."""
        record = ClaimRecord(
            claim_id="test-1",
            text="Method X improves accuracy by 15%",
            claim_type=ClaimType.EMPIRICAL,
        )
        assert record.claim_id == "test-1"
        assert record.text == "Method X improves accuracy by 15%"
        assert record.claim_type == ClaimType.EMPIRICAL
        assert record.verdict == ClaimVerdict.NOT_CHECKED

    def test_claim_record_serialization(self):
        """Test ClaimRecord to_dict / from_dict round-trip."""
        record = ClaimRecord(
            claim_id="test-2",
            text="This is a test claim",
            claim_type=ClaimType.COMPARATIVE,
            section="Results",
            confidence="high",
            verdict=ClaimVerdict.SUPPORTED,
            evidence_ids=["ev-1", "ev-2"],
        )
        d = record.to_dict()
        restored = ClaimRecord.from_dict(d)
        assert restored.claim_id == record.claim_id
        assert restored.text == record.text
        assert restored.claim_type == record.claim_type
        assert restored.verdict == record.verdict
        assert restored.evidence_ids == record.evidence_ids

    def test_claim_record_unknown_type_fallback(self):
        """Test that unknown type falls back gracefully."""
        record = ClaimRecord.from_dict({
            "claim_id": "test-3",
            "text": "Fallback test",
            "claim_type": "nonexistent",
        })
        assert record.claim_type == ClaimType.UNKNOWN


class TestClaimManifest:
    """Test ClaimManifest — the live equivalent of the old ClaimTracker."""

    def test_create_manifest(self):
        """Test creating a claim manifest."""
        manifest = ClaimManifest(paper_stage="draft")
        assert manifest.paper_stage == "draft"
        assert manifest.total_claims == 0
        assert manifest.supported_claims == 0

    def test_add_claim(self):
        """Test adding a claim to the manifest."""
        manifest = ClaimManifest(paper_stage="draft")
        claim = ClaimRecord(
            claim_id="c-1",
            text="Test claim",
            claim_type=ClaimType.EMPIRICAL,
        )
        manifest.add_claim(claim)
        assert manifest.total_claims == 1
        assert manifest.claims[0].text == "Test claim"

    def test_add_claim_auto_id(self):
        """Test adding claim without ID assigns one."""
        manifest = ClaimManifest(paper_stage="draft")
        claim = ClaimRecord(
            claim_id="",
            text="Auto-ID claim",
            claim_type=ClaimType.CAUSAL,
        )
        manifest.add_claim(claim)
        assert len(claim.claim_id) == 16  # UUID hex[:16]
        assert manifest.total_claims == 1

    def test_supported_count(self):
        """Test counting supported claims."""
        manifest = ClaimManifest(paper_stage="draft")
        manifest.add_claim(ClaimRecord(
            claim_id="c-1", text="Supported",
            claim_type=ClaimType.EMPIRICAL,
            verdict=ClaimVerdict.SUPPORTED,
        ))
        manifest.add_claim(ClaimRecord(
            claim_id="c-2", text="Unsupported",
            claim_type=ClaimType.EMPIRICAL,
            verdict=ClaimVerdict.UNSUPPORTED,
        ))
        manifest.add_claim(ClaimRecord(
            claim_id="c-3", text="Not checked",
            claim_type=ClaimType.EMPIRICAL,
        ))
        assert manifest.supported_claims == 1
        assert manifest.unsupported_claims == 1

    def test_manifest_round_trip(self):
        """Test ClaimManifest JSON round-trip."""
        manifest = ClaimManifest(paper_stage="draft")
        manifest.add_claim(ClaimRecord(
            claim_id="c-1", text="Claim 1",
            claim_type=ClaimType.EMPIRICAL,
            verdict=ClaimVerdict.SUPPORTED,
        ))
        manifest.add_claim(ClaimRecord(
            claim_id="c-2", text="Claim 2",
            claim_type=ClaimType.COMPARATIVE,
            verdict=ClaimVerdict.UNSUPPORTED,
        ))
        json_str = manifest.to_json()
        restored = ClaimManifest.from_dict(
            __import__("json").loads(json_str)
        )
        assert restored.paper_stage == "draft"
        assert restored.total_claims == 2
        assert restored.supported_claims == 1

    def test_manifest_load_save(self, tmp_path):
        """Test ClaimManifest.save() and .load()."""
        manifest = ClaimManifest(paper_stage="draft")
        manifest.add_claim(ClaimRecord(
            claim_id="c-1", text="File test",
            claim_type=ClaimType.NOVELTY,
        ))
        path = tmp_path / "test_manifest.json"
        manifest.save(str(path))
        assert path.exists()

        loaded = ClaimManifest.load(str(path))
        assert loaded.paper_stage == "draft"
        assert loaded.total_claims == 1
