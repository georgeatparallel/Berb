"""SearXNG web search client for Berb.

Privacy-focused metasearch engine integration with 100+ search engines.
Self-hosted via Docker for zero cost and unlimited searches.

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.web.searxng_client import SearXNGClient, SearXNGConfig

    config = SearXNGConfig(base_url="http://localhost:8080")
    client = SearXNGClient(config)
    
    # Search all engines
    results = await client.search("CRISPR gene editing")
    
    # Search only arXiv
    results = await client.search(
        "CRISPR",
        engines=["arxiv"],
        categories=["science"],
    )
    
    # Search with syntax
    results = await client.search("!arxiv CRISPR")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from .search import SearchResult, WebSearchResponse

logger = logging.getLogger(__name__)


@dataclass
class SearXNGConfig:
    """SearXNG configuration.
    
    Attributes:
        base_url: SearXNG server URL (default: http://localhost:8080)
        engines: Specific engines to use (default: all)
        categories: Categories like general, science, images (default: all)
        language: Search language (default: en)
        safe_search: 0=off, 1=moderate, 2=strict (default: 0)
        timeout: Request timeout in seconds (default: 30)
        max_results: Maximum results per query (default: 20)
    """
    
    base_url: str = "http://localhost:8080"
    """SearXNG server URL"""
    
    engines: list[str] | None = None
    """Specific engines to use (e.g., ["google", "arxiv", "wikipedia"])"""
    
    categories: list[str] | None = None
    """Categories: general, science, images, videos, news, etc."""
    
    language: str = "en"
    """Search language code (e.g., "en", "fr", "de")"""
    
    safe_search: int = 0
    """Safe search level: 0=off, 1=moderate, 2=strict"""
    
    timeout: int = 30
    """Request timeout in seconds"""
    
    max_results: int = 20
    """Maximum results per query"""


class SearXNGClient:
    """Client for SearXNG metasearch engine.
    
    Provides privacy-focused web search with 100+ engines.
    Supports search syntax, engine selection, and category filtering.
    
    Examples:
        Basic search:
            >>> client = SearXNGClient()
            >>> results = await client.search("quantum computing")
        
        Search specific engines:
            >>> results = await client.search(
            ...     "CRISPR",
            ...     engines=["arxiv", "pubmed"],
            ...     categories=["science"],
            ... )
        
        Search with syntax:
            >>> results = await client.search("!arxiv CRISPR")
            >>> results = await client.search(":fr !wp Paris")
    """
    
    def __init__(self, config: SearXNGConfig | None = None):
        """
        Initialize SearXNG client.
        
        Args:
            config: SearXNG configuration (uses defaults if None)
        """
        self.config = config or SearXNGConfig()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            follow_redirects=True,
        )
        self._engines_cache: list[dict[str, Any]] | None = None
    
    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        engines: list[str] | None = None,
        categories: list[str] | None = None,
        language: str | None = None,
        safe_search: int | None = None,
        pageno: int = 1,
    ) -> WebSearchResponse:
        """
        Search using SearXNG.
        
        Args:
            query: Search query string
            max_results: Maximum results to return (default: from config)
            engines: Specific engines (e.g., ["google", "bing", "arxiv"])
            categories: Categories (e.g., ["science", "general"])
            language: Language code (e.g., "en", "fr")
            safe_search: 0=off, 1=moderate, 2=strict
            pageno: Page number for pagination
        
        Returns:
            WebSearchResponse with search results
        
        Raises:
            httpx.HTTPError: If SearXNG server returns error
            httpx.TimeoutException: If request times out
        
        Examples:
            # Search all engines
            >>> results = await client.search("machine learning survey 2025")
            >>> print(f"Found {len(results.results)} results")
            
            # Search only academic sources
            >>> results = await client.search(
            ...     "transformer architecture",
            ...     engines=["arxiv", "google_scholar", "pubmed"],
            ...     categories=["science"],
            ... )
            
            # Search with language
            >>> results = await client.search(
            ...     "intelligence artificielle",
            ...     language="fr",
            ...     engines=["wikipedia", "qwant"],
            ... )
        """
        limit = max_results or self.config.max_results
        
        params = {
            "q": query,
            "format": "json",
            "pageno": pageno,
        }
        
        # Engine selection
        engine_list = engines or self.config.engines
        if engine_list:
            params["engines"] = ",".join(engine_list)
        
        # Category selection
        category_list = categories or self.config.categories
        if category_list:
            params["categories"] = ",".join(category_list)
        
        # Language
        lang = language or self.config.language
        if lang:
            params["language"] = lang
        
        # Safe search
        safe = safe_search if safe_search is not None else self.config.safe_search
        params["safe_search"] = safe
        
        try:
            response = await self._client.get("/search", params=params)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("results", [])[:limit]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", "")[:500],
                    content=item.get("content", ""),
                    score=item.get("score", 0.0),
                    source=item.get("engine", "searxng"),
                ))
            
            return WebSearchResponse(
                query=query,
                results=results,
                elapsed_seconds=data.get("search_time", 0.0),
                source="searxng",
                answer=data.get("answer", ""),  # AI-generated answer if available
            )
            
        except httpx.HTTPError as e:
            logger.error("SearXNG search failed for query %r: %s", query, e)
            raise
        except Exception as e:
            logger.error("Unexpected error during SearXNG search: %s", e)
            raise
    
    async def search_multi(
        self,
        queries: list[str],
        *,
        max_results: int | None = None,
        inter_query_delay: float = 0.5,
    ) -> list[WebSearchResponse]:
        """
        Search multiple queries with rate limiting.
        
        Args:
            queries: List of search queries
            max_results: Maximum results per query
            inter_query_delay: Delay between queries in seconds
        
        Returns:
            List of WebSearchResponse objects
        
        Examples:
            >>> responses = await client.search_multi([
            ...     "CRISPR ethics",
            ...     "CRISPR clinical trials",
            ...     "CRISPR off-target effects",
            ... ])
            >>> for resp in responses:
            ...     print(f"{resp.query}: {len(resp.results)} results")
        """
        import asyncio
        
        responses = []
        for i, query in enumerate(queries):
            if i > 0:
                await asyncio.sleep(inter_query_delay)
            resp = await self.search(query, max_results=max_results)
            responses.append(resp)
        
        return responses
    
    async def get_engines(self) -> list[dict[str, Any]]:
        """
        Get list of available engines.
        
        Returns:
            List of engine dictionaries with name, categories, language, etc.
        
        Examples:
            >>> engines = await client.get_engines()
            >>> arxiv_engines = [e for e in engines if "arxiv" in e["name"].lower()]
        """
        if self._engines_cache:
            return self._engines_cache
        
        try:
            response = await self._client.get("/engines")
            response.raise_for_status()
            data = response.json()
            self._engines_cache = data
            return data
        except Exception as e:
            logger.warning("Failed to fetch engines list: %s", e)
            return []
    
    async def get_categories(self) -> list[str]:
        """
        Get list of available categories.
        
        Returns:
            List of category names
        
        Examples:
            >>> categories = await client.get_categories()
            >>> print(categories)
            ['general', 'science', 'images', 'videos', 'news', 'it']
        """
        engines = await self.get_engines()
        categories = set()
        for engine in engines:
            for category in engine.get("categories", []):
                categories.add(category)
        return sorted(categories)
    
    async def health_check(self) -> bool:
        """
        Check if SearXNG server is healthy.
        
        Returns:
            True if server is reachable and responding
        
        Examples:
            >>> if await client.health_check():
            ...     print("SearXNG is online")
            ... else:
            ...     print("SearXNG is offline")
        """
        try:
            response = await self._client.get("/")
            return response.status_code == 200
        except Exception:
            return False
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def __aenter__(self) -> SearXNGClient:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


def create_searxng_client_from_env() -> SearXNGClient:
    """
    Create SearXNG client from environment variables.
    
    Environment Variables:
        SEARXNG_BASE_URL: SearXNG server URL (default: http://localhost:8080)
        SEARXNG_ENGINES: Comma-separated engine list (optional)
        SEARXNG_CATEGORIES: Comma-separated categories (optional)
        SEARXNG_LANGUAGE: Language code (default: en)
        SEARXNG_SAFE_SEARCH: Safe search level 0-2 (default: 0)
        SEARXNG_TIMEOUT: Timeout in seconds (default: 30)
    
    Returns:
        SearXNGClient configured from environment
    
    Examples:
        # In .env file:
        # SEARXNG_BASE_URL=http://searxng:8080
        # SEARXNG_ENGINES=arxiv,google_scholar,pubmed
        # SEARXNG_CATEGORIES=science
        # SEARXNG_LANGUAGE=en
        # SEARXNG_SAFE_SEARCH=0
        
        >>> client = create_searxng_client_from_env()
    """
    import os
    
    return SearXNGClient(
        SearXNGConfig(
            base_url=os.environ.get("SEARXNG_BASE_URL", "http://localhost:8080"),
            engines=_parse_csv_env("SEARXNG_ENGINES"),
            categories=_parse_csv_env("SEARXNG_CATEGORIES"),
            language=os.environ.get("SEARXNG_LANGUAGE", "en"),
            safe_search=int(os.environ.get("SEARXNG_SAFE_SEARCH", "0")),
            timeout=int(os.environ.get("SEARXNG_TIMEOUT", "30")),
        )
    )


def _parse_csv_env(env_var: str) -> list[str] | None:
    """Parse comma-separated environment variable."""
    import os
    
    value = os.environ.get(env_var, "")
    if not value:
        return None
    return [x.strip() for x in value.split(",") if x.strip()]
