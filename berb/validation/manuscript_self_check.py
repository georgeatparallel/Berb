"""Manuscript self-check for validating generated papers.

This module performs self-audit of generated papers before delivery,
checking for:
- Citation-claim alignment
- Contrasting evidence acknowledgment
- Citation completeness
- Reference formatting

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IssueSeverity(str, Enum):
    """Severity of manuscript issues.

    Attributes:
        CRITICAL: Must fix before submission
        MAJOR: Should fix before submission
        MINOR: Recommended to fix
        COSMETIC: Optional improvement
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    COSMETIC = "cosmetic"


class MisalignmentWarning(BaseModel):
    """Citation-claim misalignment warning.

    Attributes:
        claim: The claim made in the paper
        citation_id: Citation that doesn't support the claim
        expected_support: Expected support type
        actual_support: Actual support type provided
        severity: Issue severity
        suggestion: Suggested fix
    """

    claim: str
    citation_id: str
    expected_support: str  # supporting, contrasting
    actual_support: str
    severity: IssueSeverity
    suggestion: str


class OmissionWarning(BaseModel):
    """Missing contrasting evidence warning.

    Attributes:
        claim: The claim made
        missing_evidence: Contrasting evidence that should be acknowledged
        severity: Issue severity
        suggestion: Suggested fix
    """

    claim: str
    missing_evidence: str
    severity: IssueSeverity
    suggestion: str


class UncitedClaim(BaseModel):
    """Empirical claim without citation.

    Attributes:
        claim: The uncited claim
        context: Surrounding context
        appears_empirical: Whether claim appears empirical
        severity: Issue severity
    """

    claim: str
    context: str
    appears_empirical: bool
    severity: IssueSeverity


class FormatError(BaseModel):
    """Citation formatting error.

    Attributes:
        citation: The malformed citation
        expected_format: Expected format
        actual_format: Actual format
        location: Location in paper
        severity: Issue severity
    """

    citation: str
    expected_format: str
    actual_format: str
    location: str  # Section/paragraph
    severity: IssueSeverity


class ManuscriptIntegrityReport(BaseModel):
    """Complete manuscript self-check report.

    Attributes:
        total_claims: Total claims found
        uncited_claims: Number of uncited empirical claims
        misaligned_citations: Number of misaligned citations
        missing_contrasts: Number of missing contrasting evidence
        format_errors: Number of formatting errors
        overall_score: Overall integrity score (0-10)
        passed: Whether manuscript passes self-check
        issues: All issues found
    """

    total_claims: int = 0
    uncited_claims: int = 0
    misaligned_citations: int = 0
    missing_contrasts: int = 0
    format_errors: int = 0
    overall_score: float = Field(default=10.0, ge=0.0, le=10.0)
    passed: bool = True
    misalignment_warnings: list[MisalignmentWarning] = Field(default_factory=list)
    omission_warnings: list[OmissionWarning] = Field(default_factory=list)
    uncited_claims_list: list[UncitedClaim] = Field(default_factory=list)
    format_errors_list: list[FormatError] = Field(default_factory=list)


class ManuscriptSelfChecker:
    """Self-audit of generated paper before delivery.

    This checker validates:
    - Citation-claim alignment (claims match citation support)
    - Contrasting evidence acknowledgment
    - Citation completeness (empirical claims have citations)
    - Reference formatting consistency

    Usage::

        checker = ManuscriptSelfChecker()
        report = await checker.full_check(paper_text, references)
        if not report.passed:
            # Fix issues before submission

    Attributes:
        citation_style: Expected citation style (apa/numeric/etc.)
        check_empirical_claims: Whether to check empirical claims
        min_confidence_threshold: Minimum confidence for citation support
    """

    # Patterns indicating empirical claims
    EMPIRICAL_CLAIM_PATTERNS = [
        r"\b(study|experiment|analysis|results|data)\s+(shows?|demonstrates?|reveals?|indicates?)\b",
        r"\bwe\s+(found|observed|measured|discovered|show)\b",
        r"\bit\s+is\s+(well\s+)?(established|known|documented)\s+that\b",
        r"\bprevious\s+(work|research|studies)\s+(have|has)\s+(shown|demonstrated)\b",
        r"\b(according\s+to|based\s+on)\s+(previous|prior|earlier)\s+(work|research)\b",
    ]

    # Hedging patterns that may indicate uncertainty
    HEDGING_PATTERNS = [
        r"\bmay\b", r"\bmight\b", r"\bcould\b", r"\bsuggests?\b",
        r"\bappears?\b", r"\bseems?\b", r"\bpossibly\b", r"\bpotentially\b",
    ]

    def __init__(
        self,
        citation_style: str = "numeric",
        check_empirical_claims: bool = True,
        min_confidence_threshold: float = 0.7,
    ):
        """Initialize manuscript self-checker.

        Args:
            citation_style: Expected citation style
            check_empirical_claims: Whether to check empirical claims
            min_confidence_threshold: Minimum confidence for citation support
        """
        self.citation_style = citation_style
        self.check_empirical_claims = check_empirical_claims
        self.min_confidence_threshold = min_confidence_threshold

    async def check_citation_claim_alignment(
        self,
        paper_text: str,
        references: list[dict[str, Any]],
        citation_classifications: list[Any] | None = None,
    ) -> list[MisalignmentWarning]:
        """Verify paper doesn't misrepresent citation support.

        Args:
            paper_text: Full paper text
            references: Reference metadata
            citation_classifications: Optional pre-computed classifications

        Returns:
            List of misalignment warnings
        """
        warnings = []

        # Extract claims with citations
        claims_with_citations = self._extract_claims_with_citations(paper_text)

        for claim, citation_ids in claims_with_citations:
            # Check if claim language matches citation support
            for citation_id in citation_ids:
                # Find classification for this citation
                classification = None
                if citation_classifications:
                    classification = next(
                        (c for c in citation_classifications if c.cited_paper_id == citation_id),
                        None,
                    )

                # Check for misalignment
                if classification:
                    claim_lower = claim.lower()

                    # If claim is assertive but citation is contrasting
                    if classification.intent.value == "contrasting":
                        if not any(h in claim_lower for h in ["however", "but", "although"]):
                            warnings.append(
                                MisalignmentWarning(
                                    claim=claim[:200],
                                    citation_id=citation_id,
                                    expected_support="supporting",
                                    actual_support="contrasting",
                                    severity=IssueSeverity.MAJOR,
                                    suggestion="Rephrase claim to acknowledge contrasting evidence or use different citation",
                                )
                            )

                    # If claim says "proves" but citation only "suggests"
                    if classification.confidence < 0.7:
                        if any(word in claim_lower for word in ["proves", "demonstrates", "establishes"]):
                            warnings.append(
                                MisalignmentWarning(
                                    claim=claim[:200],
                                    citation_id=citation_id,
                                    expected_support="strong",
                                    actual_support=f"weak (confidence: {classification.confidence:.2f})",
                                    severity=IssueSeverity.MINOR,
                                    suggestion="Use more hedged language (e.g., 'suggests', 'indicates')",
                                )
                            )

        return warnings

    async def check_contrasting_evidence_acknowledged(
        self,
        paper_text: str,
        evidence_map: dict[str, Any] | None = None,
    ) -> list[OmissionWarning]:
        """Verify paper acknowledges known contradictions.

        Args:
            paper_text: Full paper text
            evidence_map: Optional evidence map with contrasting info

        Returns:
            List of omission warnings
        """
        warnings = []

        # Extract strong claims
        strong_claims = self._extract_strong_claims(paper_text)

        for claim in strong_claims:
            # Check if contrasting evidence exists
            if evidence_map:
                claim_key = claim[:100].lower()
                if claim_key in evidence_map:
                    evidence = evidence_map[claim_key]
                    if evidence.get("contrasting_count", 0) > 0:
                        # Check if paper acknowledges this
                        claim_context = self._get_claim_context(paper_text, claim)
                        if not self._has_contrast_language(claim_context):
                            warnings.append(
                                OmissionWarning(
                                    claim=claim[:200],
                                    missing_evidence=f"{evidence['contrasting_count']} contrasting studies",
                                    severity=IssueSeverity.MAJOR,
                                    suggestion="Add sentence acknowledging contrasting evidence",
                                )
                            )

        return warnings

    async def check_citation_completeness(
        self,
        paper_text: str,
    ) -> list[UncitedClaim]:
        """Find empirical claims lacking citations.

        Args:
            paper_text: Full paper text

        Returns:
            List of uncited claims
        """
        uncited = []

        if not self.check_empirical_claims:
            return uncited

        # Find sentences with empirical claim patterns
        sentences = self._extract_sentences(paper_text)

        for sentence in sentences:
            if self._is_empirical_claim(sentence):
                # Check if sentence has citation
                if not self._has_citation(sentence):
                    # Check if it's common knowledge (exception)
                    if not self._is_common_knowledge(sentence):
                        uncited.append(
                            UncitedClaim(
                                claim=sentence[:200],
                                context=sentence,
                                appears_empirical=True,
                                severity=IssueSeverity.MINOR,
                            )
                        )

        return uncited

    async def check_reference_formatting(
        self,
        references: list[dict[str, Any]],
        paper_text: str,
    ) -> list[FormatError]:
        """Verify citation format consistency.

        Args:
            references: Reference metadata
            paper_text: Full paper text

        Returns:
            List of format errors
        """
        errors = []

        # Extract all citations from paper
        citations_in_text = self._extract_citations_from_text(paper_text)

        for citation_text, location in citations_in_text:
            # Check format based on style
            if self.citation_style == "numeric":
                if not re.match(r"\[\d+\]", citation_text):
                    errors.append(
                        FormatError(
                            citation=citation_text,
                            expected_format="[N] (numeric)",
                            actual_format=citation_text,
                            location=location,
                            severity=IssueSeverity.COSMETIC,
                        )
                    )
            elif self.citation_style == "apa":
                if not re.match(r"\([A-Z][a-z]+,\s*\d{4}\)", citation_text):
                    errors.append(
                        FormatError(
                            citation=citation_text,
                            expected_format="(Author, Year)",
                            actual_format=citation_text,
                            location=location,
                            severity=IssueSeverity.COSMETIC,
                        )
                    )
            elif self.citation_style == "author-year":
                if not re.match(r"[A-Z][a-z]+\s+\(\d{4}\)", citation_text):
                    errors.append(
                        FormatError(
                            citation=citation_text,
                            expected_format="Author (Year)",
                            actual_format=citation_text,
                            location=location,
                            severity=IssueSeverity.COSMETIC,
                        )
                    )

        return errors

    async def full_check(
        self,
        paper_text: str,
        references: list[dict[str, Any]],
        citation_classifications: list[Any] | None = None,
        evidence_map: dict[str, Any] | None = None,
    ) -> ManuscriptIntegrityReport:
        """Run all manuscript self-checks.

        Args:
            paper_text: Full paper text
            references: Reference metadata
            citation_classifications: Optional citation classifications
            evidence_map: Optional evidence map

        Returns:
            ManuscriptIntegrityReport
        """
        # Run all checks
        misalignments = await self.check_citation_claim_alignment(
            paper_text, references, citation_classifications
        )
        omissions = await self.check_contrasting_evidence_acknowledged(
            paper_text, evidence_map
        )
        uncited = await self.check_citation_completeness(paper_text)
        format_errors = await self.check_reference_formatting(
            references, paper_text
        )

        # Count claims
        total_claims = len(self._extract_claims_with_citations(paper_text))

        # Calculate overall score
        score = 10.0
        score -= len(misalignments) * 1.5
        score -= len(omissions) * 1.0
        score -= len(uncited) * 0.5
        score -= len(format_errors) * 0.2
        score = max(0.0, score)

        # Determine pass/fail
        passed = (
            len(misalignments) == 0 and
            len(omissions) == 0 and
            score >= 7.0
        )

        return ManuscriptIntegrityReport(
            total_claims=total_claims,
            uncited_claims=len(uncited),
            misaligned_citations=len(misalignments),
            missing_contrasts=len(omissions),
            format_errors=len(format_errors),
            overall_score=score,
            passed=passed,
            misalignment_warnings=misalignments,
            omission_warnings=omissions,
            uncited_claims_list=uncited,
            format_errors_list=format_errors,
        )

    # Helper methods

    def _extract_claims_with_citations(
        self, text: str
    ) -> list[tuple[str, list[str]]]:
        """Extract claims with their citations.

        Returns list of (claim_text, [citation_ids])
        """
        # Simplified extraction - would need NLP for production
        claims = []
        sentences = self._extract_sentences(text)

        for sentence in sentences:
            citations = self._extract_citation_ids(sentence)
            if citations and self._is_claim_sentence(sentence):
                claims.append((sentence, citations))

        return claims

    def _extract_strong_claims(self, text: str) -> list[str]:
        """Extract strong/assertive claims."""
        strong_claims = []
        sentences = self._extract_sentences(text)

        strong_patterns = [
            r"\b(proves?|demonstrates?|establishes?|confirms?)\b",
            r"\bclearly\s+(shows?|indicates?)\b",
            r"\bit\s+is\s+(well\s+)?(established|known|clear)\s+that\b",
        ]

        for sentence in sentences:
            for pattern in strong_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    strong_claims.append(sentence)
                    break

        return strong_claims

    def _extract_sentences(self, text: str) -> list[str]:
        """Extract sentences from text."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if len(s.split()) > 5]

    def _extract_citation_ids(self, text: str) -> list[str]:
        """Extract citation identifiers from text."""
        citations = []

        # Numeric style: [1], [2, 3]
        numeric = re.findall(r"\[(\d+(?:,\s*\d+)*)\]", text)
        for match in numeric:
            citations.extend(match.split(","))

        # Author-year style: (Smith, 2024)
        author_year = re.findall(r"\(([A-Z][a-z]+),?\s*(\d{4})\)", text)
        for author, year in author_year:
            citations.append(f"{author}_{year}")

        return citations

    def _extract_citations_from_text(
        self, text: str
    ) -> list[tuple[str, str]]:
        """Extract citations with location info."""
        citations = []

        # Find all citation patterns
        patterns = [
            (r"\[\d+\]", "numeric"),
            (r"\([A-Z][a-z]+,\s*\d{4}\)", "apa"),
            (r"[A-Z][a-z]+\s+\(\d{4}\)", "author-year"),
        ]

        for pattern, style in patterns:
            for match in re.finditer(pattern, text):
                # Get location (section/paragraph)
                location = self._get_location(text, match.start())
                citations.append((match.group(), location))

        return citations

    def _is_empirical_claim(self, sentence: str) -> bool:
        """Check if sentence is an empirical claim."""
        sentence_lower = sentence.lower()
        for pattern in self.EMPIRICAL_CLAIM_PATTERNS:
            if re.search(pattern, sentence_lower):
                return True
        return False

    def _is_claim_sentence(self, sentence: str) -> bool:
        """Check if sentence makes a claim."""
        # Simplified heuristic
        return len(sentence) > 30 and not sentence.startswith(("#", "##", "###"))

    def _has_citation(self, text: str) -> bool:
        """Check if text contains a citation."""
        patterns = [
            r"\[\d+\]",
            r"\([A-Z][a-z]+,\s*\d{4}\)",
            r"[A-Z][a-z]+\s+\(\d{4}\)",
            r"\b[A-Z][a-z]+\s+et\s+al\.\s*\(\d{4}\)",
        ]
        return any(re.search(p, text) for p in patterns)

    def _has_contrast_language(self, text: str) -> bool:
        """Check if text acknowledges contrasting evidence."""
        contrast_words = [
            "however", "but", "although", "nevertheless",
            "in contrast", "on the other hand", "conversely",
            "despite", "while some studies", "contrasting evidence",
        ]
        text_lower = text.lower()
        return any(word in text_lower for word in contrast_words)

    def _is_common_knowledge(self, sentence: str) -> bool:
        """Check if sentence expresses common knowledge."""
        common_patterns = [
            r"\bmachine\s+learning\s+is\b",
            r"\bdeep\s+learning\s+has\b",
            r"\bartificial\s+intelligence\b",
            r"\bthe\s+internet\s+is\b",
        ]
        sentence_lower = sentence.lower()
        return any(re.search(p, sentence_lower) for p in common_patterns)

    def _get_claim_context(self, text: str, claim: str) -> str:
        """Get surrounding context for a claim."""
        idx = text.find(claim)
        if idx == -1:
            return claim

        start = max(0, idx - 200)
        end = min(len(text), idx + len(claim) + 200)
        return text[start:end]

    def _get_location(self, text: str, position: int) -> str:
        """Get section/paragraph location for a position."""
        # Simplified - would need actual section parsing
        return f"position {position}"
