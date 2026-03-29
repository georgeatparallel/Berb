"""Claim verification pipeline for scientific integrity.

This module provides end-to-end claim verification (Jenni AI style):
1. Extract all empirical claims from paper
2. For each claim, find cited sources
3. Check if sources support claim
4. Flag unsupported/overstated claims
5. Generate verification report

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from berb.validation.claim_confidence import (
    ClaimConfidenceAnalyzer,
    ClaimConfidenceLevel,
    ClaimConfidenceResult,
)
from berb.validation.source_alignment import (
    SourceClaimAligner,
    AlignmentResult,
    AlignmentCheck,
)

logger = logging.getLogger(__name__)


class ClaimVerification(BaseModel):
    """Verification result for a single claim.

    Attributes:
        claim_text: Claim text
        confidence_level: Confidence classification
        alignment_result: Source alignment result
        supporting_sources: Sources that support claim
        contradicting_sources: Sources that contradict
        page_numbers: Page numbers where claim appears
        requires_revision: Whether claim needs revision
        revision_suggestion: Suggested revision
    """

    claim_text: str
    confidence_level: ClaimConfidenceLevel
    alignment_result: AlignmentResult = AlignmentResult.CANNOT_DETERMINE
    supporting_sources: list[str] = Field(default_factory=list)
    contradicting_sources: list[str] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)
    requires_revision: bool = False
    revision_suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "claim_text": self.claim_text,
            "confidence_level": self.confidence_level.value,
            "alignment_result": self.alignment_result.value,
            "supporting_sources": self.supporting_sources,
            "contradicting_sources": self.contradicting_sources,
            "page_numbers": self.page_numbers,
            "requires_revision": self.requires_revision,
            "revision_suggestion": self.revision_suggestion,
        }


class VerificationReport(BaseModel):
    """Complete claim verification report.

    Attributes:
        manuscript_id: Manuscript identifier
        total_claims: Total claims verified
        well_supported: Number of well-supported claims
        weakly_supported: Number of weakly supported
        unsupported: Number of unsupported claims
        overstated: Number of overstated claims
        contradicted: Number of contradicted claims
        misaligned: Number of misaligned citations
        overall_score: Overall verification score (0-10)
        claims: Individual claim verifications
        recommendations: Recommendations for improvement
        generated_at: When report was generated
    """

    manuscript_id: str
    total_claims: int = 0
    well_supported: int = 0
    weakly_supported: int = 0
    unsupported: int = 0
    overstated: int = 0
    contradicted: int = 0
    misaligned: int = 0
    overall_score: float = Field(default=5.0, ge=0.0, le=10.0)
    claims: list[ClaimVerification] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Calculate derived fields
        self.total_claims = len(self.claims)
        self.well_supported = sum(
            1 for c in self.claims
            if c.confidence_level == ClaimConfidenceLevel.WELL_SUPPORTED
        )
        self.weakly_supported = sum(
            1 for c in self.claims
            if c.confidence_level == ClaimConfidenceLevel.WEAKLY_SUPPORTED
        )
        self.unsupported = sum(
            1 for c in self.claims
            if c.confidence_level == ClaimConfidenceLevel.UNSUPPORTED
        )
        self.overstated = sum(
            1 for c in self.claims
            if c.confidence_level == ClaimConfidenceLevel.OVERSTATED
        )
        self.contradicted = sum(
            1 for c in self.claims
            if c.confidence_level == ClaimConfidenceLevel.CONTRADICTED
        )
        self.misaligned = sum(
            1 for c in self.claims
            if c.alignment_result == AlignmentResult.MISALIGNED
        )

        # Calculate overall score
        if self.total_claims > 0:
            self.overall_score = (
                (self.well_supported * 10 +
                 self.weakly_supported * 6 +
                 self.overstated * 3 +
                 self.unsupported * 2 +
                 self.contradicted * 1) / self.total_claims
            )
            # Penalize misaligned citations
            self.overall_score -= self.misaligned * 0.5
            self.overall_score = max(0.0, min(10.0, self.overall_score))


class ClaimVerificationPipeline:
    """End-to-end claim verification pipeline.

    This pipeline:
    1. Extracts all empirical claims from paper
    2. For each claim, finds cited sources
    3. Checks if sources support claim
    4. Flags unsupported/overstated claims
    5. Generates verification report

    Usage::

        pipeline = ClaimVerificationPipeline(source_client)
        report = await pipeline.verify_paper(paper_text, references)

    Attributes:
        confidence_analyzer: Claim confidence analyzer
        alignment_checker: Source-claim aligner
    """

    def __init__(self, source_client: Any | None = None):
        """Initialize verification pipeline.

        Args:
            source_client: Client for accessing source documents
        """
        self.confidence_analyzer = ClaimConfidenceAnalyzer(source_client)
        self.alignment_checker = SourceClaimAligner(source_client)

    async def verify_paper(
        self,
        paper_text: str,
        references: list[dict[str, Any]],
        manuscript_id: str = "manuscript",
    ) -> VerificationReport:
        """Verify all claims in paper against sources.

        Args:
            paper_text: Full paper text
            references: List of references
            manuscript_id: Manuscript identifier

        Returns:
            VerificationReport
        """
        logger.info(f"Starting claim verification for {manuscript_id}")

        # Step 1: Extract all empirical claims
        claims = await self.confidence_analyzer.extract_claims(paper_text)
        logger.info(f"Extracted {len(claims)} claims")

        # Step 2: Verify each claim
        verifications = []
        for claim in claims:
            # Find relevant references
            relevant_refs = self._find_relevant_references(claim, references)

            # Analyze confidence
            confidence_result = await self.confidence_analyzer.analyze_confidence(
                claim.text, relevant_refs
            )

            # Check alignment for each citation
            alignment_checks = []
            for ref in relevant_refs:
                source_text = ref.get("text", ref.get("abstract", ""))
                if source_text:
                    check = await self.alignment_checker.check_alignment(
                        claim.text, source_text, ref.get("id", "")
                    )
                    alignment_checks.append(check)

            # Build verification
            verification = self._build_verification(
                claim, confidence_result, alignment_checks
            )
            verifications.append(verification)

        # Step 3: Generate report
        report = VerificationReport(
            manuscript_id=manuscript_id,
            claims=verifications,
            recommendations=self._generate_recommendations(verifications),
        )

        logger.info(
            f"Verification complete: {report.overall_score:.1f}/10, "
            f"{report.well_supported}/{report.total_claims} well-supported"
        )

        return report

    def _find_relevant_references(
        self,
        claim: Any,  # ExtractedClaim
        references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Find references relevant to claim.

        Args:
            claim: Claim object
            references: List of references

        Returns:
            List of relevant references
        """
        if not references:
            return []

        # If claim has citations, use those
        if hasattr(claim, "citations") and claim.citations:
            return [
                ref for ref in references
                if ref.get("id") in claim.citations or ref.get("doi") in claim.citations
            ]

        # Otherwise, return all references (limited)
        return references[:5]

    def _build_verification(
        self,
        claim: Any,  # ExtractedClaim
        confidence_result: ClaimConfidenceResult,
        alignment_checks: list[AlignmentCheck],
    ) -> ClaimVerification:
        """Build verification from analysis results.

        Args:
            claim: Claim object
            confidence_result: Confidence analysis result
            alignment_checks: Alignment check results

        Returns:
            ClaimVerification
        """
        # Collect supporting/contradicting sources
        supporting = confidence_result.supporting_sources
        contradicting = confidence_result.contradicting_sources

        # Check for misaligned citations
        misaligned = [
            check for check in alignment_checks
            if check.alignment == AlignmentResult.MISALIGNED
        ]

        # Determine if revision required
        requires_revision = (
            confidence_result.confidence_level
            in [
                ClaimConfidenceLevel.UNSUPPORTED,
                ClaimConfidenceLevel.OVERSTATED,
                ClaimConfidenceLevel.CONTRADICTED,
            ]
            or len(misaligned) > 0
        )

        # Generate revision suggestion
        revision_suggestion = ""
        if requires_revision and confidence_result.recommendations:
            revision_suggestion = confidence_result.recommendations[0]

        # Get alignment result (use first if available)
        alignment_result = (
            alignment_checks[0].alignment if alignment_checks
            else AlignmentResult.CANNOT_DETERMINE
        )

        return ClaimVerification(
            claim_text=claim.text,
            confidence_level=confidence_result.confidence_level,
            alignment_result=alignment_result,
            supporting_sources=supporting,
            contradicting_sources=contradicting,
            page_numbers=claim.page_numbers if hasattr(claim, "page_numbers") else [],
            requires_revision=requires_revision,
            revision_suggestion=revision_suggestion,
        )

    def _generate_recommendations(
        self,
        verifications: list[ClaimVerification],
    ) -> list[str]:
        """Generate recommendations based on verifications.

        Args:
            verifications: Claim verifications

        Returns:
            List of recommendations
        """
        recommendations = []

        # Count issues
        unsupported = sum(
            1 for v in verifications
            if v.confidence_level == ClaimConfidenceLevel.UNSUPPORTED
        )
        overstated = sum(
            1 for v in verifications
            if v.confidence_level == ClaimConfidenceLevel.OVERSTATED
        )
        misaligned = sum(
            1 for v in verifications
            if v.alignment_result == AlignmentResult.MISALIGNED
        )

        if unsupported > 0:
            recommendations.append(
                f"Add citations for {unsupported} unsupported claims"
            )

        if overstated > 0:
            recommendations.append(
                f"Soften language for {overstated} overstated claims"
            )

        if misaligned > 0:
            recommendations.append(
                f"Fix {misaligned} misaligned citations"
            )

        if not recommendations:
            recommendations.append("All claims are well-supported")

        return recommendations

    async def verify_single_claim(
        self,
        claim_text: str,
        sources: list[dict[str, Any]],
    ) -> ClaimVerification:
        """Verify single claim.

        Args:
            claim_text: Claim text
            sources: Source documents

        Returns:
            ClaimVerification
        """
        # Analyze confidence
        confidence_result = await self.confidence_analyzer.analyze_confidence(
            claim_text, sources
        )

        # Check alignment
        alignment_checks = []
        for source in sources:
            source_text = source.get("text", source.get("abstract", ""))
            if source_text:
                check = await self.alignment_checker.check_alignment(
                    claim_text, source_text, source.get("id", "")
                )
                alignment_checks.append(check)

        # Build verification (simplified)
        from berb.validation.claim_confidence import ExtractedClaim

        claim = ExtractedClaim(text=claim_text)
        return self._build_verification(claim, confidence_result, alignment_checks)


@dataclass
class VerificationConfig:
    """Configuration for claim verification.

    Attributes:
        enabled: Whether verification is enabled
        min_score: Minimum acceptable verification score
        flag_unsupported: Whether to flag unsupported claims
        auto_fix: Whether to automatically fix claims
        strict_mode: Use strict verification criteria
    """

    enabled: bool = True
    min_score: float = 7.0
    flag_unsupported: bool = True
    auto_fix: bool = False
    strict_mode: bool = False


# Import dataclass
from dataclasses import dataclass


# Convenience functions
async def verify_paper_claims(
    paper_text: str,
    references: list[dict[str, Any]],
    manuscript_id: str = "manuscript",
    source_client: Any | None = None,
) -> VerificationReport:
    """Verify all claims in paper.

    Args:
        paper_text: Paper text
        references: References
        manuscript_id: Manuscript ID
        source_client: Source client

    Returns:
        VerificationReport
    """
    pipeline = ClaimVerificationPipeline(source_client)
    return await pipeline.verify_paper(paper_text, references, manuscript_id)


async def check_claim_support(
    claim_text: str,
    sources: list[dict[str, Any]],
    source_client: Any | None = None,
) -> ClaimVerification:
    """Check single claim support.

    Args:
        claim_text: Claim text
        sources: Source documents
        source_client: Source client

    Returns:
        ClaimVerification
    """
    pipeline = ClaimVerificationPipeline(source_client)
    return await pipeline.verify_single_claim(claim_text, sources)
