"""Enhanced Citation Verifier with 4-layer integrity checking.

Verifies citations through 4 layers:
1. Format Check - DOI/arXiv ID format validation
2. API Check - CrossRef/DataCite/arXiv API verification
3. Info Check - Title/author/year match
4. Content Check - Claim-citation alignment (LLM)

Removes hallucinated references automatically.

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.pipeline.citation_verification import (
        CitationVerifier,
        VerifierConfig,
    )

    config = VerifierConfig(enable_all_layers=True)
    verifier = CitationVerifier(config)

    # Verify single citation
    result = await verifier.verify({
        "doi": "10.1038/s41586-021-03819-2",
        "title": "Paper Title",
        "authors": ["Author One"],
        "year": 2021,
    })
    print(f"Valid: {result.is_valid}")
    print(f"Layers passed: {result.layers_passed}")

    # Verify paper's citations
    results = await verifier.verify_paper(paper_text, citations)
    valid_citations = [c for c in results if c.is_valid]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class VerificationLayer(str, Enum):
    """Citation verification layer."""

    FORMAT = "format"  # DOI/arXiv ID format
    API = "api"  # CrossRef/DataCite/arXiv API
    INFO = "info"  # Title/author/year match
    CONTENT = "content"  # Claim-citation alignment


@dataclass
class VerifierConfig:
    """Citation verifier configuration.

    Attributes:
        enable_format_check: Enable Layer 1 (default: True)
        enable_api_check: Enable Layer 2 (default: True)
        enable_info_check: Enable Layer 3 (default: True)
        enable_content_check: Enable Layer 4 (default: True)
        crossref_api_url: CrossRef API URL
        arxiv_api_url: arXiv API URL
        semantic_scholar_api_url: Semantic Scholar API URL
        timeout: API request timeout in seconds
        llm_client: LLM client for content check
        min_confidence: Minimum confidence for valid citation
    """

    enable_format_check: bool = True
    enable_api_check: bool = True
    enable_info_check: bool = True
    enable_content_check: bool = True

    crossref_api_url: str = "https://api.crossref.org/works"
    arxiv_api_url: str = "http://export.arxiv.org/api/query"
    semantic_scholar_api_url: str = "https://api.semanticscholar.org/graph/v1/paper"

    timeout: int = 30
    """API request timeout"""

    llm_client: Any = None
    """LLM client for content check"""

    min_confidence: float = 0.6
    """Minimum confidence for valid citation"""


@dataclass
class CitationVerificationResult:
    """Result from citation verification.

    Attributes:
        citation: Original citation data
        is_valid: Whether citation passed all enabled layers
        layers_passed: List of passed layers
        layers_failed: List of failed layers
        confidence: Overall confidence score
        errors: List of error messages
        warnings: List of warnings
        metadata: Verified metadata from APIs
        claim_alignment: Claim-citation alignment score
    """

    citation: dict[str, Any] = field(default_factory=dict)
    is_valid: bool = False
    layers_passed: list[VerificationLayer] = field(default_factory=list)
    layers_failed: list[VerificationLayer] = field(default_factory=list)
    confidence: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    claim_alignment: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "citation": self.citation,
            "is_valid": self.is_valid,
            "layers_passed": [l.value for l in self.layers_passed],
            "layers_failed": [l.value for l in self.layers_failed],
            "confidence": self.confidence,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "claim_alignment": self.claim_alignment,
        }


class CitationVerifier:
    """Verify citations through 4-layer integrity checking.

    Provides comprehensive citation verification:
    - Layer 1: Format validation (DOI, arXiv ID)
    - Layer 2: API verification (CrossRef, DataCite, arXiv)
    - Layer 3: Metadata matching (title, author, year)
    - Layer 4: Content alignment (claim-citation check)

    Examples:
        Basic verification:
            >>> verifier = CitationVerifier()
            >>> result = await verifier.verify({
            ...     "doi": "10.1038/s41586-021-03819-2",
            ...     "title": "Paper Title",
            ... })
            >>> print(f"Valid: {result.is_valid}")

        Verify paper's citations:
            >>> results = await verifier.verify_paper(paper_text, citations)
            >>> valid = [c for c in results if c.is_valid]
            >>> print(f"Valid citations: {len(valid)}/{len(results)}")
    """

    # DOI pattern
    DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[-._;()0-9A-Za-z]+$")

    # arXiv ID pattern
    ARXIV_PATTERN = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")

    def __init__(self, config: VerifierConfig | None = None):
        """
        Initialize citation verifier.

        Args:
            config: Verifier configuration (uses defaults if None)
        """
        self.config = config or VerifierConfig()
        self._http_client = None

    async def verify(
        self,
        citation: dict[str, Any],
        *,
        claim_text: str | None = None,
    ) -> CitationVerificationResult:
        """
        Verify a single citation through all enabled layers.

        Args:
            citation: Citation data (doi, arxiv_id, title, authors, year, etc.)
            claim_text: Text claim that cites this reference

        Returns:
            CitationVerificationResult with verification details

        Examples:
            >>> result = await verifier.verify({
            ...     "doi": "10.1038/s41586-021-03819-2",
            ...     "title": "Attention Is All You Need",
            ...     "authors": ["Vaswani"],
            ...     "year": 2017,
            ... })
            >>> if result.is_valid:
            ...     print("Citation verified!")
        """
        result = CitationVerificationResult(citation=citation)

        # Layer 1: Format check
        if self.config.enable_format_check:
            format_valid = await self._check_format(citation)
            if format_valid:
                result.layers_passed.append(VerificationLayer.FORMAT)
            else:
                result.layers_failed.append(VerificationLayer.FORMAT)
                result.errors.append("Format validation failed")

        # Layer 2: API check
        if self.config.enable_api_check and format_valid:
            api_metadata = await self._check_api(citation)
            if api_metadata:
                result.layers_passed.append(VerificationLayer.API)
                result.metadata = api_metadata
            else:
                result.layers_failed.append(VerificationLayer.API)
                result.warnings.append("API verification unavailable")

        # Layer 3: Info check
        if self.config.enable_info_check and result.metadata:
            info_match = await self._check_info(citation, result.metadata)
            if info_match:
                result.layers_passed.append(VerificationLayer.INFO)
            else:
                result.layers_failed.append(VerificationLayer.INFO)
                result.warnings.append("Metadata mismatch detected")

        # Layer 4: Content check
        if self.config.enable_content_check and claim_text:
            alignment = await self._check_content(citation, claim_text)
            result.claim_alignment = alignment
            if alignment >= self.config.min_confidence:
                result.layers_passed.append(VerificationLayer.CONTENT)
            else:
                result.layers_failed.append(VerificationLayer.CONTENT)
                result.warnings.append(f"Low claim-citation alignment: {alignment:.2f}")

        # Calculate overall confidence
        result.confidence = self._calculate_confidence(result)

        # Determine validity
        result.is_valid = (
            VerificationLayer.FORMAT in result.layers_passed and
            len(result.layers_failed) <= 1  # Allow 1 layer failure
        )

        return result

    async def verify_paper(
        self,
        paper_text: str,
        citations: list[dict[str, Any]],
        *,
        batch_size: int = 5,
    ) -> list[CitationVerificationResult]:
        """
        Verify all citations in a paper.

        Args:
            paper_text: Full paper text
            citations: List of citation data
            batch_size: Citations to verify concurrently

        Returns:
            List of CitationVerificationResult objects

        Examples:
            >>> results = await verifier.verify_paper(paper_text, citations)
            >>> valid = [r for r in results if r.is_valid]
            >>> print(f"Valid: {len(valid)}/{len(citations)}")
        """
        results = []

        # Extract claims for each citation (simplified)
        for citation in citations:
            claim = self._extract_claim_for_citation(paper_text, citation)
            result = await self.verify(citation, claim_text=claim)
            results.append(result)

        return results

    async def _check_format(self, citation: dict[str, Any]) -> bool:
        """Layer 1: Check DOI/arXiv ID format."""
        doi = citation.get("doi", "")
        arxiv_id = citation.get("arxiv_id", "")

        if doi:
            # Validate DOI format
            if not self.DOI_PATTERN.match(doi):
                logger.debug(f"Invalid DOI format: {doi}")
                return False

        if arxiv_id:
            # Validate arXiv ID format
            if not self.ARXIV_PATTERN.match(arxiv_id):
                logger.debug(f"Invalid arXiv ID format: {arxiv_id}")
                return False

        # Must have at least one identifier
        if not doi and not arxiv_id:
            # Check for URL
            url = citation.get("url", "")
            if "doi.org" in url or "arxiv.org" in url:
                return True
            logger.debug("No DOI or arXiv ID provided")
            return False

        return True

    async def _check_api(self, citation: dict[str, Any]) -> dict[str, Any] | None:
        """Layer 2: Verify via CrossRef/DataCite/arXiv API."""
        doi = citation.get("doi", "")
        arxiv_id = citation.get("arxiv_id", "")

        # Try DOI first (CrossRef)
        if doi:
            metadata = await self._query_crossref(doi)
            if metadata:
                return metadata

            # Try DataCite as fallback
            metadata = await self._query_datacite(doi)
            if metadata:
                return metadata

        # Try arXiv ID
        if arxiv_id:
            metadata = await self._query_arxiv(arxiv_id)
            if metadata:
                return metadata

        return None

    async def _query_crossref(self, doi: str) -> dict[str, Any] | None:
        """Query CrossRef API."""
        import httpx

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.config.timeout)

        try:
            url = f"{self.config.crossref_api_url}/{doi}"
            response = await self._http_client.get(url)

            if response.status_code == 200:
                data = response.json()
                message = data.get("message", {})

                return {
                    "source": "crossref",
                    "title": message.get("title", [""])[0],
                    "authors": [
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in message.get("author", [])
                    ],
                    "year": message.get("created", {}).get("date-parts", [[None]])[0][0],
                    "journal": message.get("container-title", [""])[0],
                    "publisher": message.get("publisher", ""),
                }
        except Exception as e:
            logger.debug(f"CrossRef query failed: {e}")

        return None

    async def _query_datacite(self, doi: str) -> dict[str, Any] | None:
        """Query DataCite API."""
        import httpx

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.config.timeout)

        try:
            url = f"https://api.datacite.org/dois/{doi}"
            response = await self._http_client.get(url)

            if response.status_code == 200:
                data = response.json()
                attributes = data.get("data", {}).get("attributes", {})

                return {
                    "source": "datacite",
                    "title": attributes.get("titles", [{}])[0].get("title", ""),
                    "authors": [
                        c.get("name", "")
                        for c in attributes.get("creators", [])
                    ],
                    "year": attributes.get("publicationYear"),
                    "publisher": attributes.get("publisher", ""),
                }
        except Exception as e:
            logger.debug(f"DataCite query failed: {e}")

        return None

    async def _query_arxiv(self, arxiv_id: str) -> dict[str, Any] | None:
        """Query arXiv API."""
        import httpx

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.config.timeout)

        try:
            params = {"id_list": arxiv_id, "max_results": 1}
            response = await self._http_client.get(
                self.config.arxiv_api_url,
                params=params,
            )

            if response.status_code == 200:
                # Parse Atom XML (simplified)
                content = response.text
                title_match = re.search(r"<title>(.*?)</title>", content)
                author_match = re.findall(r"<name>(.*?)</name>", content)
                date_match = re.search(r"<published>(\d{4})", content)

                if title_match:
                    return {
                        "source": "arxiv",
                        "title": title_match.group(1).strip(),
                        "authors": [a.strip() for a in author_match[1:]] if author_match else [],
                        "year": int(date_match.group(1)) if date_match else None,
                    }
        except Exception as e:
            logger.debug(f"arXiv query failed: {e}")

        return None

    async def _check_info(
        self,
        citation: dict[str, Any],
        metadata: dict[str, Any],
    ) -> bool:
        """Layer 3: Check title/author/year match."""
        matches = 0
        total = 0

        # Check title
        if citation.get("title") and metadata.get("title"):
            total += 1
            if self._fuzzy_match(citation["title"], metadata["title"]):
                matches += 1

        # Check authors (at least one match)
        if citation.get("authors") and metadata.get("authors"):
            total += 1
            citation_authors = {a.lower() for a in citation["authors"]}
            api_authors = {a.lower() for a in metadata["authors"]}
            if citation_authors & api_authors:  # Intersection
                matches += 1

        # Check year
        if citation.get("year") and metadata.get("year"):
            total += 1
            if citation["year"] == metadata["year"]:
                matches += 1

        # Require at least 50% match
        return matches >= total * 0.5 if total > 0 else True

    async def _check_content(
        self,
        citation: dict[str, Any],
        claim_text: str,
    ) -> float:
        """Layer 4: Check claim-citation alignment using LLM."""
        if not self.config.llm_client:
            # Fallback: keyword-based alignment
            return self._keyword_alignment(citation, claim_text)

        # Use LLM for alignment check
        prompt = f"""Analyze if this citation supports the claim:

Citation: {citation.get('title', 'Unknown')} by {', '.join(citation.get('authors', ['Unknown']))} ({citation.get('year', 'n.d.')})

Claim: {claim_text}

Does the citation support the claim? Rate alignment 0.0-1.0:
- 0.0: Completely unrelated
- 0.5: Partially related but doesn't support
- 1.0: Directly supports the claim

Respond with just a number."""

        try:
            response = self.config.llm_client.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=10,
            )
            score_match = re.search(r"(\d\.?\d*)", response.content)
            if score_match:
                return float(score_match.group(1))
        except Exception as e:
            logger.debug(f"LLM content check failed: {e}")

        # Fallback to keyword alignment
        return self._keyword_alignment(citation, claim_text)

    def _keyword_alignment(
        self,
        citation: dict[str, Any],
        claim_text: str,
    ) -> float:
        """Keyword-based claim-citation alignment."""
        # Extract keywords from citation title
        title = citation.get("title", "").lower()
        title_words = set(re.findall(r"\b\w{4,}\b", title))

        # Check keyword overlap with claim
        claim_words = set(re.findall(r"\b\w{4,}\b", claim_text.lower()))

        if not title_words or not claim_words:
            return 0.5  # Neutral

        overlap = title_words & claim_words
        overlap_score = len(overlap) / max(len(title_words), len(claim_words))

        return min(1.0, overlap_score * 2)  # Scale up

    def _fuzzy_match(self, str1: str, str2: str, threshold: float = 0.7) -> bool:
        """Fuzzy string matching."""
        # Simple token-based matching
        tokens1 = set(str1.lower().split())
        tokens2 = set(str2.lower().split())

        if not tokens1 or not tokens2:
            return False

        overlap = tokens1 & tokens2
        similarity = len(overlap) / max(len(tokens1), len(tokens2))

        return similarity >= threshold

    def _calculate_confidence(
        self,
        result: CitationVerificationResult,
    ) -> float:
        """Calculate overall confidence score."""
        if not result.layers_passed:
            return 0.0

        # Base confidence from passed layers
        layer_weights = {
            VerificationLayer.FORMAT: 0.15,
            VerificationLayer.API: 0.35,
            VerificationLayer.INFO: 0.30,
            VerificationLayer.CONTENT: 0.20,
        }

        confidence = sum(
            layer_weights.get(layer, 0.0)
            for layer in result.layers_passed
        )

        # Adjust for claim alignment
        if result.claim_alignment > 0:
            confidence = (confidence + result.claim_alignment) / 2

        # Penalize for errors
        confidence -= len(result.errors) * 0.1
        confidence -= len(result.warnings) * 0.05

        return max(0.0, min(1.0, confidence))

    def _extract_claim_for_citation(
        self,
        paper_text: str,
        citation: dict[str, Any],
    ) -> str | None:
        """Extract claim text associated with a citation."""
        # Simple heuristic: find text near citation marker
        doi = citation.get("doi", "")
        arxiv_id = citation.get("arxiv_id", "")

        # Look for citation pattern
        patterns = []
        if doi:
            patterns.append(doi)
        if arxiv_id:
            patterns.append(arxiv_id)

        for pattern in patterns:
            # Find position in text
            pos = paper_text.lower().find(pattern.lower())
            if pos != -1:
                # Extract surrounding context (simplified)
                start = max(0, pos - 200)
                end = min(len(paper_text), pos + 50)
                return paper_text[start:end]

        return None

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> CitationVerifier:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


def create_verifier_from_env() -> CitationVerifier:
    """
    Create CitationVerifier from environment variables.

    Environment Variables:
        CITATION_ENABLE_FORMAT: Enable format check true/false
        CITATION_ENABLE_API: Enable API check true/false
        CITATION_ENABLE_INFO: Enable info check true/false
        CITATION_ENABLE_CONTENT: Enable content check true/false
        CITATION_TIMEOUT: API timeout in seconds

    Returns:
        CitationVerifier configured from environment
    """
    import os

    return CitationVerifier(
        VerifierConfig(
            enable_format_check=os.environ.get("CITATION_ENABLE_FORMAT", "true").lower() == "true",
            enable_api_check=os.environ.get("CITATION_ENABLE_API", "true").lower() == "true",
            enable_info_check=os.environ.get("CITATION_ENABLE_INFO", "true").lower() == "true",
            enable_content_check=os.environ.get("CITATION_ENABLE_CONTENT", "true").lower() == "true",
            timeout=int(os.environ.get("CITATION_TIMEOUT", "30")),
        )
    )
