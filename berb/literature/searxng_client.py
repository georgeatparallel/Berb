"""SearXNG Client - Metasearch integration for Berb.

This module provides integration with SearXNG for:
- Unified search across 200+ engines
- Academic search (Google Scholar, arXiv, Crossref, etc.)
- Built-in deduplication
- Result caching

Architecture: Facade + Repository patterns
Paradigm: Functional + Async

Example:
    >>> client = SearXNGClient("http://localhost:8888")
    >>> papers = await client.search("graph neural networks", categories=["science"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SearXNGResult:
    """Search result from SearXNG.

    Attributes:
        title: Result title
        url: Result URL
        content: Result content/snippet
        engine: Source engine name
        score: Relevance score
        published_date: Publication date (if available)
        authors: List of authors (for academic papers)
        doi: DOI (for academic papers)
    """

    title: str
    url: str
    content: str
    engine: str
    score: float
    published_date: str | None = None
    authors: list[str] = field(default_factory=list)
    doi: str | None = None


@dataclass
class SearXNGConfig:
    """SearXNG client configuration.

    Attributes:
        base_url: SearXNG server URL
        timeout_sec: Request timeout
        max_pages: Maximum pages to fetch
        cache_enabled: Enable result caching
        cache_ttl: Cache TTL in seconds
    """

    base_url: str
    timeout_sec: int = 30
    max_pages: int = 5
    cache_enabled: bool = True
    cache_ttl: int = 86400  # 24 hours


# ─────────────────────────────────────────────────────────────────────────────
# SearXNG Client
# ─────────────────────────────────────────────────────────────────────────────


class SearXNGClient:
    """Client for SearXNG metasearch engine.

    Provides:
    - Unified search across multiple engines
    - Academic search specialization
    - Result deduplication
    - Response caching

    Example:
        >>> client = SearXNGClient("http://localhost:8888")
        >>> results = await client.search("query", engines=["google scholar", "arxiv"])
    """

    def __init__(self, config: SearXNGConfig):
        """Initialize SearXNG client.

        Args:
            config: Client configuration
        """
        self.config = config
        self.base_url = config.base_url.rstrip("/")

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(config.timeout_sec),
        )

        # Simple in-memory cache
        self._cache: dict[str, list[SearXNGResult]] = {}
        self._cache_times: dict[str, float] = {}

        logger.info(f"SearXNGClient initialized: {config.base_url}")

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> SearXNGClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        categories: list[str] | None = None,
        engines: list[str] | None = None,
        language: str = "en",
        pageno: int = 1,
        time_range: str = "all",
        safesearch: int = 0,
    ) -> list[SearXNGResult]:
        """Search across multiple engines.

        Args:
            query: Search query
            categories: Categories to search (e.g., ["science"])
            engines: Specific engines to use
            language: Language code
            pageno: Page number
            time_range: Time range (day/week/month/year/all)
            safesearch: Safe search level (0/1/2)

        Returns:
            List of SearXNGResult objects

        Example:
            >>> results = await client.search(
            ...     "graph neural networks",
            ...     categories=["science"],
            ...     engines=["google scholar", "arxiv", "crossref"],
            ... )
        """
        # Check cache
        cache_key = self._get_cache_key(query, categories, engines, pageno)
        if self.config.cache_enabled:
            cached = self._cache_get(cache_key)
            if cached:
                logger.debug(f"Cache hit for query: {query[:50]}")
                return cached

        # Build request params
        params = {
            "q": query,
            "language": language,
            "pageno": pageno,
            "time_range": time_range,
            "safesearch": safesearch,
            "format": "json",
        }

        if categories:
            params["categories"] = ",".join(categories)

        if engines:
            params["engines"] = ",".join(engines)

        try:
            response = await self._client.get(
                "/search",
                params=params,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()

            data = response.json()
            results = self._parse_results(data)

            # Cache results
            if self.config.cache_enabled:
                self._cache_set(cache_key, results)

            logger.info(
                f"Search returned {len(results)} results (engines: {data.get('engines', [])})"
            )

            return results

        except httpx.HTTPError as e:
            logger.error(f"Search failed: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Academic Search
    # ─────────────────────────────────────────────────────────────────────────

    async def search_academic(
        self,
        query: str,
        year_min: int | None = None,
        limit: int = 20,
    ) -> list[SearXNGResult]:
        """Search academic sources specifically.

        Args:
            query: Search query
            year_min: Minimum publication year
            limit: Maximum results to return

        Returns:
            List of academic SearXNGResult objects
        """
        # Academic engines
        academic_engines = [
            "google scholar",
            "arxiv",
            "crossref",
            "pubmed",
            "base",
            "core",
        ]

        # Determine time range from year_min
        time_range = "all"
        if year_min:
            from datetime import datetime

            years_back = datetime.now().year - year_min
            if years_back <= 1:
                time_range = "year"
            elif years_back <= 5:
                time_range = "year"

        results = await self.search(
            query=query,
            categories=["science"],
            engines=academic_engines,
            time_range=time_range,
            pageno=1,
        )

        # Deduplicate by DOI
        deduplicated = self._deduplicate_by_doi(results)

        # Sort by score
        deduplicated.sort(key=lambda r: r.score, reverse=True)

        return deduplicated[:limit]

    # ─────────────────────────────────────────────────────────────────────────
    # Configuration
    # ─────────────────────────────────────────────────────────────────────────

    async def get_config(self) -> dict[str, Any]:
        """Get SearXNG server configuration.

        Returns:
            Config dict with engines, categories, etc.
        """
        try:
            response = await self._client.get("/config")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to get config: {e}")
            return {}

    async def health_check(self) -> bool:
        """Check SearXNG server health.

        Returns:
            True if healthy
        """
        try:
            response = await self._client.get("/healthz")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Parsing
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_results(self, data: dict[str, Any]) -> list[SearXNGResult]:
        """Parse SearXNG JSON response.

        Args:
            data: JSON response data

        Returns:
            List of SearXNGResult objects
        """
        results = []

        for item in data.get("results", []):
            # Extract authors from content if present
            authors = self._extract_authors(item.get("content", ""))

            # Extract DOI
            doi = self._extract_doi(item)

            result = SearXNGResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                engine=item.get("engine", ""),
                score=item.get("score", 0.0),
                published_date=item.get("publishedDate"),
                authors=authors,
                doi=doi,
            )
            results.append(result)

        return results

    @staticmethod
    def _extract_authors(content: str) -> list[str]:
        """Extract authors from content snippet."""
        import re

        # Look for author patterns (simplified)
        # E.g., "J Smith, A Johnson - Journal, 2023"
        match = re.match(r"^([^-]+)\s*-", content)
        if match:
            author_str = match.group(1).strip()
            # Split by comma and clean
            authors = [a.strip() for a in author_str.split(",")]
            return authors[:5]  # Limit to 5 authors

        return []

    @staticmethod
    def _extract_doi(item: dict[str, Any]) -> str | None:
        """Extract DOI from result item."""
        import re

        # Check explicit DOI field
        if "doi" in item:
            return item["doi"]

        # Check URL for DOI pattern
        url = item.get("url", "")
        doi_match = re.search(r"10\.\d+/[^\\s]+", url)
        if doi_match:
            return doi_match.group()

        # Check content for DOI
        content = item.get("content", "")
        doi_match = re.search(r"10\.\d+/[^\\s]+", content)
        if doi_match:
            return doi_match.group()

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Deduplication
    # ─────────────────────────────────────────────────────────────────────────

    def _deduplicate_by_doi(
        self,
        results: list[SearXNGResult],
    ) -> list[SearXNGResult]:
        """Deduplicate results by DOI.

        Args:
            results: List of results

        Returns:
            Deduplicated list (highest score kept for duplicates)
        """
        seen_dois: dict[str, SearXNGResult] = {}

        for result in results:
            if result.doi:
                if result.doi not in seen_dois:
                    seen_dois[result.doi] = result
                elif result.score > seen_dois[result.doi].score:
                    # Keep higher score
                    seen_dois[result.doi] = result
            else:
                # No DOI, use URL as key
                if result.url not in seen_dois:
                    seen_dois[result.url] = result

        return list(seen_dois.values())

    # ─────────────────────────────────────────────────────────────────────────
    # Caching
    # ─────────────────────────────────────────────────────────────────────────

    def _get_cache_key(
        self,
        query: str,
        categories: list[str] | None,
        engines: list[str] | None,
        pageno: int,
    ) -> str:
        """Generate cache key for query."""
        key_parts = [
            query,
            ",".join(categories or []),
            ",".join(engines or []),
            str(pageno),
        ]
        return "|".join(key_parts)

    def _cache_get(
        self,
        key: str,
    ) -> list[SearXNGResult] | None:
        """Get results from cache."""
        if key not in self._cache:
            return None

        # Check TTL
        import time

        elapsed = time.time() - self._cache_times[key]
        if elapsed > self.config.cache_ttl:
            del self._cache[key]
            del self._cache_times[key]
            return None

        return self._cache[key]

    def _cache_set(
        self,
        key: str,
        results: list[SearXNGResult],
    ) -> None:
        """Set results in cache."""
        import time

        self._cache[key] = results
        self._cache_times[key] = time.time()

    def clear_cache(self) -> int:
        """Clear cache.

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        self._cache_times.clear()
        logger.info(f"Cleared {count} cache entries")
        return count
