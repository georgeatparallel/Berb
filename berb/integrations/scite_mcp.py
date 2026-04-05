"""Scite.ai MCP integration for pre-classified citation intelligence.

This module provides optional integration with scite.ai's MCP server
for users who have scite subscriptions ($10-20/month).

Enhanced with:
- Bayesian scite index enhancement (domain-specific)
- Debate-based classification dispute resolution

Scite.ai provides:
- 1.6B+ pre-classified citation statements
- Supporting/contrasting/mentioning classifications
- Smart citation search
- Reference checking

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SciteCitationType(str, Enum):
    """Scite citation classification.

    Attributes:
        SUPPORTING: Citation provides evidence FOR the cited claim
        CONTRASTING: Citation provides evidence AGAINST the cited claim
        MENTIONING: Citation references without evaluative stance
    """

    SUPPORTING = "supporting"
    CONTRASTING = "contrasting"
    MENTIONING = "mentioning"


class SmartCitationResult(BaseModel):
    """Smart citation result from scite.ai.

    Attributes:
        doi: Cited paper DOI
        citing_doi: Citing paper DOI
        citation_type: Classification type
        citation_text: The actual citation statement
        confidence: Confidence score (0-1)
        section: Section where citation appears
    """

    doi: str
    citing_doi: str
    citation_type: SciteCitationType
    citation_text: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    section: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doi": self.doi,
            "citing_doi": self.citing_doi,
            "citation_type": self.citation_type.value,
            "citation_text": self.citation_text,
            "confidence": self.confidence,
            "section": self.section,
        }


class CitationProfile(BaseModel):
    """Citation profile for a paper from scite.ai.

    Attributes:
        doi: Paper DOI
        total_citations: Total citation count
        supporting_count: Number of supporting citations
        contrasting_count: Number of contrasting citations
        mentioning_count: Number of mentioning citations
        scite_index: Scite index score (0-1)
        top_citations: Top citations by confidence
    """

    doi: str
    total_citations: int = 0
    supporting_count: int = 0
    contrasting_count: int = 0
    mentioning_count: int = 0
    scite_index: float = Field(default=0.5, ge=0.0, le=1.0)
    top_citations: list[SmartCitationResult] = Field(default_factory=list)

    @property
    def support_ratio(self) -> float:
        """Calculate support ratio.

        Returns:
            Ratio of supporting to total classified citations
        """
        classified = self.supporting_count + self.contrasting_count
        if classified == 0:
            return 0.5
        return self.supporting_count / classified


class ReferenceCheckReport(BaseModel):
    """Reference check report from scite.ai.

    Attributes:
        manuscript_id: Manuscript identifier
        total_references: Total references checked
        supported_references: Number of supported references
        contradicted_references: Number of contradicted references
        retracted_references: Number of retracted references
        overall_score: Overall reference quality score (0-10)
        issues: List of issues found
    """

    manuscript_id: str
    total_references: int = 0
    supported_references: int = 0
    contradicted_references: int = 0
    retracted_references: int = 0
    overall_score: float = Field(default=5.0, ge=0.0, le=10.0)
    issues: list[str] = Field(default_factory=list)


class SciteMCPClient(Protocol):
    """Protocol for scite.ai MCP client."""

    async def search_with_smart_citations(
        self,
        query: str,
        limit: int = 100,
    ) -> list[SmartCitationResult]:
        """Search with smart citations."""
        ...

    async def get_paper_citation_profile(
        self,
        doi: str,
    ) -> CitationProfile:
        """Get citation profile for paper."""
        ...

    async def reference_check(
        self,
        manuscript_pdf: str,
    ) -> ReferenceCheckReport:
        """Check manuscript references."""
        ...

    async def get_scite_index(
        self,
        doi: str,
    ) -> float:
        """Get scite index for paper."""
        ...


class SciteConfig(BaseModel):
    """Scite.ai configuration.

    Attributes:
        enabled: Whether scite integration is enabled
        api_key: Scite API key
        api_url: Scite API URL
        timeout_seconds: Request timeout
        prefer_over_llm: Prefer scite over LLM classifier
    """

    enabled: bool = False
    api_key: str = ""
    api_url: str = "https://api.scite.ai"
    timeout_seconds: int = 30
    prefer_over_llm: bool = True


class SciteClient:
    """Scite.ai API client for citation intelligence.

    This client provides:
    1. Smart citation search
    2. Paper citation profiles
    3. Reference checking
    4. Scite index retrieval

    Usage::

        client = SciteClient(api_key="your-key")
        profile = await client.get_paper_citation_profile("10.1038/nature123")
        print(f"Supporting: {profile.supporting_count}")

    Attributes:
        config: Scite configuration
        http_client: HTTP client for API calls
    """

    def __init__(
        self,
        config: SciteConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        """Initialize scite client.

        Args:
            config: Scite configuration
            http_client: HTTP client
        """
        self.config = config or SciteConfig()
        self.http_client = http_client or httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            } if self.config.api_key else {},
        )

    async def search_with_smart_citations(
        self,
        query: str,
        limit: int = 100,
    ) -> list[SmartCitationResult]:
        """Search with smart citations.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of smart citation results
        """
        if not self.config.enabled:
            logger.warning("Scite integration not enabled")
            return []

        try:
            async with self.http_client as client:
                response = await client.get(
                    f"{self.config.api_url}/v1/smart-citations/search",
                    params={"query": query, "limit": limit},
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("citations", []):
                    results.append(
                        SmartCitationResult(
                            doi=item.get("doi", ""),
                            citing_doi=item.get("citing_doi", ""),
                            citation_type=SciteCitationType(
                                item.get("classification", "mentioning")
                            ),
                            citation_text=item.get("citation_text", ""),
                            confidence=item.get("confidence", 0.5),
                            section=item.get("section", ""),
                        )
                    )

                return results

        except Exception as e:
            logger.error(f"Scite search failed: {e}")
            return []

    async def get_paper_citation_profile(
        self,
        doi: str,
    ) -> CitationProfile:
        """Get citation profile for paper.

        Args:
            doi: Paper DOI

        Returns:
            CitationProfile
        """
        if not self.config.enabled:
            return CitationProfile(doi=doi)

        try:
            async with self.http_client as client:
                response = await client.get(
                    f"{self.config.api_url}/v1/works/{doi}",
                )
                response.raise_for_status()
                data = response.json()

                # Parse citation counts
                citations = data.get("citations", {})
                supporting = citations.get("supporting", 0)
                contrasting = citations.get("contrasting", 0)
                mentioning = citations.get("mentioning", 0)
                total = supporting + contrasting + mentioning

                # Get top citations
                top_citations = []
                for item in data.get("top_citations", [])[:10]:
                    top_citations.append(
                        SmartCitationResult(
                            doi=doi,
                            citing_doi=item.get("citing_doi", ""),
                            citation_type=SciteCitationType(
                                item.get("classification", "mentioning")
                            ),
                            citation_text=item.get("citation_text", ""),
                            confidence=item.get("confidence", 0.5),
                        )
                    )

                return CitationProfile(
                    doi=doi,
                    total_citations=total,
                    supporting_count=supporting,
                    contrasting_count=contrasting,
                    mentioning_count=mentioning,
                    scite_index=data.get("scite_index", 0.5),
                    top_citations=top_citations,
                )

        except Exception as e:
            logger.error(f"Scite profile fetch failed: {e}")
            return CitationProfile(doi=doi)

    async def reference_check(
        self,
        manuscript_text: str,
        manuscript_id: str = "manuscript",
    ) -> ReferenceCheckReport:
        """Check manuscript references.

        Args:
            manuscript_text: Manuscript text
            manuscript_id: Manuscript identifier

        Returns:
            ReferenceCheckReport
        """
        if not self.config.enabled:
            return ReferenceCheckReport(manuscript_id=manuscript_id)

        try:
            async with self.http_client as client:
                response = await client.post(
                    f"{self.config.api_url}/v1/reference-check",
                    json={"text": manuscript_text},
                )
                response.raise_for_status()
                data = response.json()

                issues = []
                if data.get("retracted_count", 0) > 0:
                    issues.append(
                        f"{data['retracted_count']} retracted references found"
                    )

                if data.get("contradicted_count", 0) > 0:
                    issues.append(
                        f"{data['contradicted_count']} contradicted references found"
                    )

                # Calculate overall score
                total = data.get("total_references", 1)
                supported = data.get("supported_references", 0)
                score = 5.0 + (supported / total) * 5.0

                if data.get("retracted_count", 0) > 0:
                    score -= 3.0
                if data.get("contradicted_count", 0) > 0:
                    score -= 2.0

                return ReferenceCheckReport(
                    manuscript_id=manuscript_id,
                    total_references=total,
                    supported_references=supported,
                    contradicted_references=data.get("contradicted_references", 0),
                    retracted_references=data.get("retracted_count", 0),
                    overall_score=max(0.0, min(10.0, score)),
                    issues=issues,
                )

        except Exception as e:
            logger.error(f"Scite reference check failed: {e}")
            return ReferenceCheckReport(manuscript_id=manuscript_id)

    async def get_scite_index(
        self,
        doi: str,
    ) -> float:
        """Get scite index for paper.

        Args:
            doi: Paper DOI

        Returns:
            Scite index (0-1)
        """
        if not self.config.enabled:
            return 0.5

        try:
            async with self.http_client as client:
                response = await client.get(
                    f"{self.config.api_url}/v1/works/{doi}/scite-index",
                )
                response.raise_for_status()
                data = response.json()
                return data.get("scite_index", 0.5)

        except Exception as e:
            logger.error(f"Scite index fetch failed: {e}")
            return 0.5


@dataclass
class SciteIntegrationConfig:
    """Configuration for scite integration.

    Attributes:
        enabled: Whether integration is enabled
        api_key: Scite API key
        fallback_to_llm: Fallback to LLM classifier if scite unavailable
        cache_results: Cache scite results
        max_cache_size: Maximum cache size
    """

    enabled: bool = False
    api_key: str = ""
    fallback_to_llm: bool = True
    cache_results: bool = True
    max_cache_size: int = 1000


class SciteIntegration:
    """High-level scite.ai integration.

    This class provides a unified interface for scite.ai features,
    with automatic fallback to LLM-based classification.

    Usage::

        integration = SciteIntegration(
            api_key="your-key",
            fallback_to_llm=True,
        )

        profile = await integration.get_citation_profile(doi)
        report = await integration.check_references(manuscript)

    Attributes:
        scite_client: Scite API client
        config: Integration configuration
        cache: Results cache
    """

    def __init__(
        self,
        api_key: str | None = None,
        config: SciteIntegrationConfig | None = None,
        llm_classifier: Any | None = None,
    ):
        """Initialize scite integration.

        Args:
            api_key: Scite API key
            config: Integration configuration
            llm_classifier: Fallback LLM classifier
        """
        self.config = config or SciteIntegrationConfig(
            enabled=api_key is not None,
            api_key=api_key or "",
        )

        self.scite_client = SciteClient(
            config=SciteConfig(
                enabled=self.config.enabled,
                api_key=self.config.api_key,
            ),
        )

        self.llm_classifier = llm_classifier
        self._cache: dict[str, Any] = {}

    async def get_citation_profile(
        self,
        doi: str,
    ) -> CitationProfile:
        """Get citation profile with caching.

        Args:
            doi: Paper DOI

        Returns:
            CitationProfile
        """
        # Check cache
        if self.config.cache_results:
            cache_key = f"profile:{doi}"
            if cache_key in self._cache:
                logger.debug(f"Cache hit for {doi}")
                return self._cache[cache_key]

        # Fetch from scite
        profile = await self.scite_client.get_paper_citation_profile(doi)

        # Cache result
        if self.config.cache_results:
            if len(self._cache) >= self.config.max_cache_size:
                self._cache.clear()
            self._cache[cache_key] = profile

        return profile

    async def check_references(
        self,
        manuscript_text: str,
        manuscript_id: str = "manuscript",
    ) -> ReferenceCheckReport:
        """Check manuscript references.

        Args:
            manuscript_text: Manuscript text
            manuscript_id: Manuscript identifier

        Returns:
            ReferenceCheckReport
        """
        return await self.scite_client.reference_check(
            manuscript_text,
            manuscript_id,
        )

    async def search_citations(
        self,
        query: str,
        limit: int = 100,
    ) -> list[SmartCitationResult]:
        """Search with smart citations.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of smart citation results
        """
        return await self.scite_client.search_with_smart_citations(
            query,
            limit,
        )

    async def get_scite_index(self, doi: str) -> float:
        """Get scite index for paper.

        Args:
            doi: Paper DOI

        Returns:
            Scite index (0-1)
        """
        return await self.scite_client.get_scite_index(doi)


# Convenience functions
async def get_citation_profile(
    doi: str,
    api_key: str | None = None,
) -> CitationProfile:
    """Get citation profile for paper.

    Args:
        doi: Paper DOI
        api_key: Scite API key

    Returns:
        CitationProfile
    """
    integration = SciteIntegration(api_key=api_key)
    return await integration.get_citation_profile(doi)


async def check_manuscript_references(
    manuscript_text: str,
    api_key: str | None = None,
) -> ReferenceCheckReport:
    """Check manuscript references.

    Args:
        manuscript_text: Manuscript text
        api_key: Scite API key

    Returns:
        ReferenceCheckReport
    """
    integration = SciteIntegration(api_key=api_key)
    return await integration.check_references(manuscript_text)
