"""Source-claim alignment verification.

This module checks if sources actually support the claims made:
- Aligned: Source supports claim
- Partially aligned: Source partially supports
- Misaligned: Source contradicts or doesn't support
- Cannot determine: Insufficient information

Inspired by Jenni AI's source-grounded verification.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AlignmentResult(str, Enum):
    """Source-claim alignment result.

    Attributes:
        ALIGNED: Source supports claim
        PARTIALLY_ALIGNED: Source partially supports
        MISALIGNED: Source contradicts or doesn't support
        CANNOT_DETERMINE: Insufficient information
    """

    ALIGNED = "aligned"
    PARTIALLY_ALIGNED = "partially_aligned"
    MISALIGNED = "misaligned"
    CANNOT_DETERMINE = "cannot_determine"


class AlignmentCheck(BaseModel):
    """Single alignment check result.

    Attributes:
        claim: Claim text
        source_id: Source identifier
        source_text: Source text snippet
        alignment: Alignment result
        confidence: Confidence in alignment (0-1)
        reasoning: Reasoning for alignment decision
        page_number: Page number in source (if applicable)
    """

    claim: str
    source_id: str
    source_text: str = ""
    alignment: AlignmentResult = AlignmentResult.CANNOT_DETERMINE
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: str = ""
    page_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(mode="json")


class AlignmentReport(BaseModel):
    """Complete alignment report for a paper.

    Attributes:
        total_claims: Total claims checked
        aligned: Number of aligned claims
        partially_aligned: Number of partially aligned
        misaligned: Number of misaligned claims
        cannot_determine: Number of undetermined
        alignment_rate: Percentage of aligned claims
        checks: Individual alignment checks
        generated_at: When report was generated
    """

    total_claims: int = 0
    aligned: int = 0
    partially_aligned: int = 0
    misaligned: int = 0
    cannot_determine: int = 0
    alignment_rate: float = 0.0
    checks: list[AlignmentCheck] = Field(default_factory=list)
    generated_at: str = ""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Calculate derived fields
        self.total_claims = len(self.checks)
        self.aligned = sum(1 for c in self.checks if c.alignment == AlignmentResult.ALIGNED)
        self.partially_aligned = sum(
            1 for c in self.checks if c.alignment == AlignmentResult.PARTIALLY_ALIGNED
        )
        self.misaligned = sum(
            1 for c in self.checks if c.alignment == AlignmentResult.MISALIGNED
        )
        self.cannot_determine = sum(
            1 for c in self.checks if c.alignment == AlignmentResult.CANNOT_DETERMINE
        )

        if self.total_claims > 0:
            self.alignment_rate = (self.aligned + self.partially_aligned * 0.5) / self.total_claims


class SourceClient(Protocol):
    """Protocol for source/document clients."""

    async def get_document_text(self, source_id: str) -> str | None:
        """Get document text by ID."""
        ...

    async def get_document_section(
        self,
        source_id: str,
        section: str,
    ) -> str | None:
        """Get specific section from document."""
        ...


class SourceClaimAligner:
    """Check if sources actually support the claims made.

    This aligner:
    1. Extracts claims with their citations
    2. Retrieves cited source text
    3. Checks if source supports claim
    4. Flags misaligned citations
    5. Generates alignment report

    Usage::

        aligner = SourceClaimAligner(source_client)
        result = await aligner.check_alignment(claim, source)
        report = await aligner.verify_all_citations(paper_text, references)

    Attributes:
        source_client: Client for accessing source documents
    """

    # Alignment keywords
    SUPPORT_KEYWORDS = [
        "consistent with", "confirms", "supports", "validates",
        "demonstrates", "shows", "indicates", "suggests",
        "in agreement with", "corroborates",
    ]

    CONTRAST_KEYWORDS = [
        "however", "in contrast", "contradicts", "challenges",
        "disagrees with", "unlike", "differs from", "questions",
        "casts doubt on", "refutes",
    ]

    def __init__(self, source_client: SourceClient | None = None):
        """Initialize source-claim aligner.

        Args:
            source_client: Client for accessing source documents
        """
        self.source_client = source_client

    async def check_alignment(
        self,
        claim: str,
        source_text: str,
        source_id: str = "",
    ) -> AlignmentCheck:
        """Check if source supports claim.

        Args:
            claim: Claim to check
            source_text: Source document text
            source_id: Source identifier

        Returns:
            AlignmentCheck result
        """
        # Extract relevant source section
        relevant_section = self._find_relevant_section(claim, source_text)

        # Check alignment
        alignment, confidence, reasoning = self._analyze_alignment(
            claim, relevant_section
        )

        return AlignmentCheck(
            claim=claim,
            source_id=source_id,
            source_text=relevant_section[:500],  # Truncate
            alignment=alignment,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _find_relevant_section(
        self,
        claim: str,
        source_text: str,
        context_size: int = 500,
    ) -> str:
        """Find relevant section in source for claim.

        Args:
            claim: Claim text
            source_text: Full source text
            context_size: Context size to return

        Returns:
            Relevant section text
        """
        claim_lower = claim.lower()
        source_lower = source_text.lower()

        # Extract key terms from claim
        claim_terms = [
            word for word in claim_lower.split()
            if len(word) > 4 and word not in {"that", "this", "which", "there", "their"}
        ]

        # Find best matching section
        best_start = 0
        best_overlap = 0

        for i in range(0, len(source_lower) - 100, 100):
            section = source_lower[i:i + context_size]
            overlap = sum(1 for term in claim_terms if term in section)

            if overlap > best_overlap:
                best_overlap = overlap
                best_start = i

        if best_overlap > 0:
            return source_text[best_start:best_start + context_size]

        # Return first section if no match
        return source_text[:context_size]

    def _analyze_alignment(
        self,
        claim: str,
        source_section: str,
    ) -> tuple[AlignmentResult, float, str]:
        """Analyze alignment between claim and source.

        Args:
            claim: Claim text
            source_section: Relevant source section

        Returns:
            Tuple of (alignment, confidence, reasoning)
        """
        claim_lower = claim.lower()
        source_lower = source_section.lower()

        # Check for support keywords
        support_count = sum(
            1 for kw in self.SUPPORT_KEYWORDS if kw in source_lower
        )

        # Check for contrast keywords
        contrast_count = sum(
            1 for kw in self.CONTRAST_KEYWORDS if kw in source_lower
        )

        # Check for keyword overlap
        claim_words = set(claim_lower.split())
        source_words = set(source_lower.split())
        overlap = len(claim_words & source_words) / max(len(claim_words), 1)

        # Determine alignment
        if contrast_count > support_count:
            return (
                AlignmentResult.MISALIGNED,
                0.7 + (contrast_count * 0.1),
                f"Source contains contrasting language ({contrast_count} indicators)",
            )
        elif support_count > 0 and overlap > 0.3:
            return (
                AlignmentResult.ALIGNED,
                min(0.9, 0.5 + support_count * 0.1 + overlap * 0.2),
                f"Source supports claim ({support_count} indicators, {overlap:.0%} overlap)",
            )
        elif overlap > 0.5:
            return (
                AlignmentResult.PARTIALLY_ALIGNED,
                0.5 + overlap * 0.2,
                f"Source partially relevant ({overlap:.0%} overlap, no clear support)",
            )
        elif overlap > 0.2:
            return (
                AlignmentResult.CANNOT_DETERMINE,
                0.4,
                f"Insufficient overlap ({overlap:.0%}) to determine alignment",
            )
        else:
            return (
                AlignmentResult.MISALIGNED,
                0.6,
                f"Source does not appear to support claim ({overlap:.0%} overlap)",
            )

    async def verify_all_citations(
        self,
        paper_text: str,
        references: list[dict[str, Any]],
    ) -> AlignmentReport:
        """Verify all citations are aligned with their sources.

        Args:
            paper_text: Full paper text
            references: List of references

        Returns:
            AlignmentReport
        """
        # Extract claims with citations
        claims_with_citations = self._extract_claims_with_citations(paper_text)

        checks = []

        for claim_text, citation_ids in claims_with_citations:
            for citation_id in citation_ids:
                # Find reference
                ref = self._find_reference(citation_id, references)
                if not ref:
                    continue

                # Get source text
                source_text = await self._get_source_text(ref)
                if not source_text:
                    continue

                # Check alignment
                check = await self.check_alignment(
                    claim_text, source_text, citation_id
                )
                checks.append(check)

        return AlignmentReport(checks=checks)

    def _extract_claims_with_citations(
        self,
        text: str,
    ) -> list[tuple[str, list[str]]]:
        """Extract claims with their citations.

        Args:
            text: Paper text

        Returns:
            List of (claim, citation_ids) tuples
        """
        import re

        claims = []

        # Split into sentences
        sentences = text.replace("\n", " ").split(".")

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 30 or len(sentence) > 500:
                continue

            # Check for claim indicators
            indicators = [
                "we found", "we show", "we demonstrate", "our results",
                "this paper", "our approach", "experiments show",
            ]

            if any(ind in sentence.lower() for ind in indicators):
                # Extract citations
                citations = []

                # Numeric [1], [2, 3]
                numeric = re.findall(r"\[(\d+(?:,\s*\d+)*)\]", sentence)
                for match in numeric:
                    citations.extend(match.split(","))

                # Author-year (Smith, 2024)
                author_year = re.findall(r"\(([A-Z][a-z]+),?\s*(\d{4})\)", sentence)
                for author, year in author_year:
                    citations.append(f"{author}_{year}")

                if citations:
                    claims.append((sentence, citations))

        return claims

    def _find_reference(
        self,
        citation_id: str,
        references: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Find reference by citation ID.

        Args:
            citation_id: Citation ID
            references: List of references

        Returns:
            Reference dict or None
        """
        for ref in references:
            if ref.get("id") == citation_id or ref.get("doi") == citation_id:
                return ref

            # Check author-year match
            if "_" in citation_id:
                author, year = citation_id.split("_", 1)
                ref_authors = ref.get("authors", [])
                ref_year = str(ref.get("year", ""))
                if ref_year == year and any(author in a for a in ref_authors):
                    return ref

        return None

    async def _get_source_text(
        self,
        reference: dict[str, Any],
    ) -> str | None:
        """Get source text for reference.

        Args:
            reference: Reference dict

        Returns:
            Source text or None
        """
        # Check if text is embedded
        if "text" in reference:
            return reference["text"]

        if "abstract" in reference:
            return reference["abstract"]

        # Try to fetch from client
        if self.source_client:
            source_id = reference.get("id", reference.get("doi", ""))
            if source_id:
                return await self.source_client.get_document_text(source_id)

        return None


@dataclass
class AlignmentConfig:
    """Configuration for alignment checking.

    Attributes:
        enabled: Whether alignment checking is enabled
        min_confidence: Minimum confidence for alignment
        flag_misaligned: Whether to flag misaligned citations
        auto_fix: Whether to automatically fix misaligned citations
    """

    enabled: bool = True
    min_confidence: float = 0.5
    flag_misaligned: bool = True
    auto_fix: bool = False


# Import dataclass
from dataclasses import dataclass


# Convenience functions
async def check_citation_alignment(
    claim: str,
    source_text: str,
    source_id: str = "",
    client: SourceClient | None = None,
) -> AlignmentCheck:
    """Check single citation alignment.

    Args:
        claim: Claim text
        source_text: Source text
        source_id: Source ID
        client: Source client

    Returns:
        AlignmentCheck
    """
    aligner = SourceClaimAligner(client)
    return await aligner.check_alignment(claim, source_text, source_id)


async def verify_paper_citations(
    paper_text: str,
    references: list[dict[str, Any]],
    client: SourceClient | None = None,
) -> AlignmentReport:
    """Verify all citations in paper.

    Args:
        paper_text: Paper text
        references: References
        client: Source client

    Returns:
        AlignmentReport
    """
    aligner = SourceClaimAligner(client)
    return await aligner.verify_all_citations(paper_text, references)
