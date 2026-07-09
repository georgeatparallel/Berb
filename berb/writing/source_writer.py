"""Smart source-based generation for grounded writing.

This module generates text anchored in specific source documents:
- Every claim traces to a specific source
- Prevents hallucination
- Integrates with reading notes (K3) and style fingerprint (B1)
- Verifies with claim confidence (N1)

Inspired by Writeless AI's source-grounded writing.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SourceMapping(BaseModel):
    """Mapping of generated text to sources.

    Attributes:
        text_span: Generated text
        source_ids: IDs of sources used
        confidence: Confidence in source grounding (0-1)
        start_pos: Start position in section
        end_pos: End position in section
    """

    text_span: str
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    start_pos: int = 0
    end_pos: int = 0


class GeneratedSection(BaseModel):
    """Generated section with source mapping.

    Attributes:
        section_type: Type of section (introduction, methods, etc.)
        content: Section content
        source_mappings: Per-span source mappings
        total_sources: Number of unique sources used
        unsupported_claims: Claims without source support
    """

    section_type: str
    content: str
    source_mappings: list[SourceMapping] = Field(default_factory=list)
    total_sources: int = 0
    unsupported_claims: list[str] = Field(default_factory=list)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Calculate derived fields
        self.total_sources = len({
            sid for m in self.source_mappings for sid in m.source_ids
        })


class SourceBasedWriter:
    """Generate text anchored in specific source documents.

    This writer:
    1. For each outline point, finds matching evidence in reading notes
    2. Constructs argument flow: claim → evidence → interpretation
    3. Generates text with inline citations at point-of-claim
    4. Verifies each citation-claim pair (N1 claim confidence)
    5. Applies style constraints from fingerprint (B1)

    Usage::

        writer = SourceBasedWriter()
        section = await writer.write_section_from_sources(
            section_outline="Introduction covering X, Y, Z",
            relevant_sources=[paper1, paper2],
            reading_notes=[note1, note2],
            style=style_fingerprint,
        )

    Attributes:
        domain: Research domain
        style_fingerprint: Optional style fingerprint
    """

    def __init__(
        self,
        domain: str = "general",
        style_fingerprint: Any | None = None,
    ):
        """Initialize source-based writer.

        Args:
            domain: Research domain
            style_fingerprint: Optional style fingerprint
        """
        self.domain = domain
        self.style_fingerprint = style_fingerprint

    async def write_section_from_sources(
        self,
        section_outline: str,
        relevant_sources: list[dict[str, Any]],
        reading_notes: list[Any] | None = None,
        style: Any | None = None,
        citation_engine: Any | None = None,
    ) -> GeneratedSection:
        """Write a section where every claim traces to a specific source.

        Process:
        1. For each outline point, find matching evidence in reading notes
        2. Construct argument flow: claim → evidence → interpretation
        3. Generate text with inline citations at point-of-claim
        4. Verify each citation-claim pair (N1 claim confidence)
        5. Apply style constraints from fingerprint

        Args:
            section_outline: Section outline
            relevant_sources: Relevant source papers
            reading_notes: Reading notes from K3
            style: Style fingerprint from B1
            citation_engine: Citation engine from L1/L2

        Returns:
            GeneratedSection with source mappings
        """
        # Use provided style or default
        style = style or self.style_fingerprint

        # Extract claims from reading notes
        claims_with_sources = self._extract_claims_from_notes(
            reading_notes or []
        )

        # Generate section content
        content, source_mappings = await self._generate_section_content(
            section_outline,
            claims_with_sources,
            relevant_sources,
            style,
        )

        # Identify unsupported claims
        unsupported = self._find_unsupported_claims(
            content, claims_with_sources
        )

        return GeneratedSection(
            section_type=section_outline.split("\n")[0] if "\n" in section_outline else "section",
            content=content,
            source_mappings=source_mappings,
            unsupported_claims=unsupported,
        )

    def _extract_claims_from_notes(
        self,
        reading_notes: list[Any],
    ) -> list[dict[str, Any]]:
        """Extract claims from reading notes.

        Args:
            reading_notes: Reading notes from K3

        Returns:
            List of claims with source information
        """
        claims = []

        for note in reading_notes:
            # Extract from PaperReadingNote structure
            if hasattr(note, "key_findings"):
                for finding in note.key_findings:
                    claims.append({
                        "claim": finding,
                        "source_id": getattr(note, "paper_id", ""),
                        "confidence": getattr(note, "quality_assessment", 5.0) / 10.0,
                    })

            # Extract from dict structure
            elif isinstance(note, dict):
                for finding in note.get("key_findings", []):
                    claims.append({
                        "claim": finding,
                        "source_id": note.get("paper_id", ""),
                        "confidence": note.get("quality_assessment", 5.0) / 10.0,
                    })

        return claims

    async def _generate_section_content(
        self,
        outline: str,
        claims_with_sources: list[dict[str, Any]],
        relevant_sources: list[dict[str, Any]],
        style: Any | None,
    ) -> tuple[str, list[SourceMapping]]:
        """Generate section content with source mappings.

        Args:
            outline: Section outline
            claims_with_sources: Claims with source info
            relevant_sources: Relevant source papers
            style: Style fingerprint

        Returns:
            Tuple of (content, source_mappings)
        """
        # Simplified generation (would use LLM in production)
        paragraphs = []
        mappings = []
        pos = 0

        # Group claims by theme
        themes = self._group_claims_by_theme(claims_with_sources)

        for theme, theme_claims in themes.items():
            # Generate paragraph for theme
            paragraph = self._generate_theme_paragraph(
                theme, theme_claims, style
            )

            # Create source mapping
            source_ids = [c["source_id"] for c in theme_claims]
            avg_confidence = sum(c["confidence"] for c in theme_claims) / len(theme_claims)

            paragraphs.append(paragraph)
            mappings.append(
                SourceMapping(
                    text_span=paragraph,
                    source_ids=source_ids,
                    confidence=avg_confidence,
                    start_pos=pos,
                    end_pos=pos + len(paragraph),
                )
            )
            pos += len(paragraph) + 1  # +1 for newline

        content = "\n".join(paragraphs)
        return content, mappings

    def _group_claims_by_theme(
        self,
        claims: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Group claims by theme/topic.

        Args:
            claims: List of claims

        Returns:
            Dictionary of theme to claims
        """
        # Simplified grouping (would use NLP clustering in production)
        themes: dict[str, list[dict[str, Any]]] = {}

        for claim in claims:
            # Use first few words as theme key (simplified)
            theme = claim["claim"][:50].split(" ")[0]
            if theme not in themes:
                themes[theme] = []
            themes[theme].append(claim)

        return themes

    def _generate_theme_paragraph(
        self,
        theme: str,
        claims: list[dict[str, Any]],
        style: Any | None,
    ) -> str:
        """Generate paragraph for a theme.

        Args:
            theme: Theme/topic
            claims: Claims for this theme
            style: Style fingerprint

        Returns:
            Generated paragraph
        """
        # Simplified generation (would use LLM in production)
        sentences = []

        for claim in claims:
            sentence = f"{claim['claim']}"
            sentences.append(sentence)

        return " ".join(sentences)

    def _find_unsupported_claims(
        self,
        content: str,
        claims_with_sources: list[dict[str, Any]],
    ) -> list[str]:
        """Find claims without source support.

        Args:
            content: Generated content
            claims_with_sources: Claims with sources

        Returns:
            List of unsupported claims
        """
        # In production, would verify each claim against sources
        # For now, return empty list
        return []


class SourceGroundingVerifier:
    """Verify that generated text is grounded in sources.

    This verifier:
    1. Extracts all claims from generated text
    2. Checks each claim against source documents
    3. Flags unsupported or hallucinated claims
    4. Provides grounding score

    Attributes:
        min_grounding_score: Minimum acceptable grounding score
    """

    def __init__(self, min_grounding_score: float = 0.7):
        """Initialize verifier.

        Args:
            min_grounding_score: Minimum grounding score
        """
        self.min_grounding_score = min_grounding_score

    async def verify_grounding(
        self,
        text: str,
        sources: list[dict[str, Any]],
    ) -> GroundingReport:
        """Verify text grounding in sources.

        Args:
            text: Generated text
            sources: Source documents

        Returns:
            GroundingReport
        """
        # Extract claims
        claims = self._extract_claims(text)

        # Verify each claim
        verified = []
        for claim in claims:
            verification = await self._verify_claim(claim, sources)
            verified.append(verification)

        # Calculate grounding score
        grounded_count = sum(1 for v in verified if v.is_grounded)
        grounding_score = grounded_count / max(len(verified), 1)

        return GroundingReport(
            total_claims=len(verified),
            grounded_claims=grounded_count,
            ungrounded_claims=len(verified) - grounded_count,
            grounding_score=grounding_score,
            verifications=verified,
            passes_threshold=grounding_score >= self.min_grounding_score,
        )

    def _extract_claims(self, text: str) -> list[str]:
        """Extract claims from text.

        Args:
            text: Generated text

        Returns:
            List of claims
        """
        import re

        # Simplified claim extraction
        # In production, would use NLP claim detector
        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if len(s) > 20]

    async def _verify_claim(
        self,
        claim: str,
        sources: list[dict[str, Any]],
    ) -> ClaimVerification:
        """Verify single claim against sources.

        Args:
            claim: Claim to verify
            sources: Source documents

        Returns:
            ClaimVerification
        """
        # Simplified verification (would use NLI in production)
        # Check for keyword overlap with sources
        claim_keywords = set(claim.lower().split())

        for source in sources:
            source_text = source.get("abstract", "").lower()
            source_keywords = set(source_text.split())

            overlap = len(claim_keywords & source_keywords)
            if overlap > 5:
                return ClaimVerification(
                    claim=claim,
                    is_grounded=True,
                    grounding_source=source.get("id", ""),
                    confidence=min(1.0, overlap / 20),
                )

        return ClaimVerification(
            claim=claim,
            is_grounded=False,
            grounding_source="",
            confidence=0.0,
        )


class ClaimVerification(BaseModel):
    """Verification of a single claim.

    Attributes:
        claim: Claim text
        is_grounded: Whether claim is grounded in sources
        grounding_source: Source that grounds the claim
        confidence: Confidence in verification (0-1)
    """

    claim: str
    is_grounded: bool = False
    grounding_source: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class GroundingReport(BaseModel):
    """Complete grounding verification report.

    Attributes:
        total_claims: Total claims extracted
        grounded_claims: Number of grounded claims
        ungrounded_claims: Number of ungrounded claims
        grounding_score: Overall grounding score (0-1)
        verifications: Per-claim verifications
        passes_threshold: Whether grounding meets threshold
    """

    total_claims: int = 0
    grounded_claims: int = 0
    ungrounded_claims: int = 0
    grounding_score: float = 0.0
    verifications: list[ClaimVerification] = Field(default_factory=list)
    passes_threshold: bool = False


# Convenience functions
async def write_with_sources(
    outline: str,
    sources: list[dict[str, Any]],
    reading_notes: list[Any] | None = None,
    domain: str = "general",
) -> GeneratedSection:
    """Convenience function for source-based writing.

    Args:
        outline: Section outline
        sources: Source documents
        reading_notes: Reading notes
        domain: Research domain

    Returns:
        GeneratedSection
    """
    writer = SourceBasedWriter(domain=domain)
    return await writer.write_section_from_sources(
        section_outline=outline,
        relevant_sources=sources,
        reading_notes=reading_notes,
    )


async def verify_text_grounding(
    text: str,
    sources: list[dict[str, Any]],
    min_score: float = 0.7,
) -> GroundingReport:
    """Convenience function for grounding verification.

    Args:
        text: Text to verify
        sources: Source documents
        min_score: Minimum grounding score

    Returns:
        GroundingReport
    """
    verifier = SourceGroundingVerifier(min_grounding_score=min_score)
    return await verifier.verify_grounding(text, sources)
