"""Web search powered by Tavily AI Search API and SearXNG.

Tavily is the primary search engine (installed as a dependency).
SearXNG is the privacy-focused alternative (self-hosted, 100+ engines).
A DuckDuckGo HTML scrape fallback exists for when no API key is set.

Usage::

    # With Tavily
    client = WebSearchClient(api_key="tvly-...")
    results = client.search("knowledge distillation survey 2024")
    
    # With SearXNG (self-hosted)
    client = WebSearchClient(searxng_url="http://localhost:8080")
    results = client.search("CRISPR gene editing", engine="searxng")
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.request import Request, urlopen
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str = ""
    content: str = ""
    score: float = 0.0
    source: str = ""  # "tavily" | "duckduckgo" | "searxng"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "content": self.content,
            "score": self.score,
            "source": self.source,
        }


@dataclass
class WebSearchResponse:
    """Response from a web search query."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    answer: str = ""  # Tavily can provide a direct AI answer
    elapsed_seconds: float = 0.0
    source: str = ""  # "tavily" | "duckduckgo"

    @property
    def has_results(self) -> bool:
        return len(self.results) > 0


class WebSearchClient:
    """General-purpose web search client.

    Supports multiple search engines:
    - Tavily (installed): Primary engine, AI-powered
    - SearXNG (self-hosted): Privacy-focused, 100+ engines
    - DuckDuckGo (fallback): No API key needed

    Parameters
    ----------
    api_key:
        Tavily API key. Falls back to ``TAVILY_API_KEY`` env var.
    max_results:
        Default number of results per query.
    search_depth:
        Tavily search depth: "basic" or "advanced".
    include_answer:
        Whether to request Tavily's AI-generated answer.
    searxng_url:
        SearXNG server URL. If set, SearXNG becomes primary engine.
    use_searxng_primary:
        Use SearXNG as primary engine (default: True if searxng_url set).
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        max_results: int = 10,
        search_depth: str = "advanced",
        include_answer: bool = True,
        searxng_url: str | None = None,
        use_searxng_primary: bool | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self.max_results = max_results
        self.search_depth = search_depth
        self.include_answer = include_answer
        
        # SearXNG integration
        self.searxng_url = searxng_url or os.environ.get("SEARXNG_BASE_URL")
        if use_searxng_primary is None:
            self.use_searxng_primary = bool(self.searxng_url)
        else:
            self.use_searxng_primary = use_searxng_primary
        
        # Lazy import SearXNG client
        self._searxng_client = None

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        engine: str | None = None,  # NEW: "searxng", "tavily", "duckduckgo"
        **searxng_kwargs: Any,  # NEW: passed to SearXNG client
    ) -> WebSearchResponse:
        """Search the web for a query.
        
        Args:
            query: Search query string
            max_results: Maximum results to return
            include_domains: Domains to include (Tavily only)
            exclude_domains: Domains to exclude (Tavily only)
            engine: Explicit engine selection ("searxng", "tavily", "duckduckgo")
            **searxng_kwargs: Additional args for SearXNG (engines, categories, etc.)
        
        Returns:
            WebSearchResponse with search results
        
        Examples:
            # Auto-select engine (SearXNG primary if configured)
            >>> results = client.search("machine learning")
            
            # Force SearXNG
            >>> results = client.search("CRISPR", engine="searxng")
            
            # SearXNG with specific engines
            >>> results = client.search(
            ...     "quantum computing",
            ...     engine="searxng",
            ...     engines=["arxiv", "google_scholar"],
            ...     categories=["science"],
            ... )
        """
        limit = max_results or self.max_results
        t0 = time.monotonic()

        # Explicit engine selection
        if engine == "searxng":
            return self._search_searxng(query, limit, t0, **searxng_kwargs)
        elif engine == "tavily":
            return self._search_tavily(query, limit, include_domains, exclude_domains, t0)
        elif engine == "duckduckgo":
            return self._search_duckduckgo(query, limit, t0)

        # Automatic selection: SearXNG primary if configured
        if self.use_searxng_primary and self.searxng_url:
            try:
                return self._search_searxng(query, limit, t0, **searxng_kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("SearXNG search failed, falling back: %s", exc)

        # Tavily is the primary engine (if SearXNG not configured)
        if self.api_key:
            try:
                return self._search_tavily(query, limit, include_domains, exclude_domains, t0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tavily search failed, falling back to DuckDuckGo: %s", exc)

        return self._search_duckduckgo(query, limit, t0)

    # ------------------------------------------------------------------
    # SearXNG backend (privacy-focused, self-hosted)
    # ------------------------------------------------------------------

    def _search_searxng(
        self,
        query: str,
        limit: int,
        t0: float,
        engines: list[str] | None = None,
        categories: list[str] | None = None,
        language: str | None = None,
        **kwargs: Any,
    ) -> WebSearchResponse:
        """Search using SearXNG (self-hosted metasearch engine)."""
        # Lazy import to avoid circular dependency
        if self._searxng_client is None:
            from .searxng_client import SearXNGClient, SearXNGConfig
            
            self._searxng_client = SearXNGClient(
                SearXNGConfig(
                    base_url=self.searxng_url,
                    engines=engines,
                    categories=categories,
                    language=language or "en",
                )
            )
        
        import asyncio
        
        # Run async search in sync context
        async def _async_search():
            return await self._searxng_client.search(
                query,
                max_results=limit,
                engines=engines,
                categories=categories,
                language=language,
                **kwargs,
            )
        
        searxng_response = asyncio.run(_async_search())
        elapsed = time.monotonic() - t0
        
        # Convert SearXNG results to our format
        results = []
        for item in searxng_response.results:
            results.append(SearchResult(
                title=item.title,
                url=item.url,
                snippet=item.snippet,
                content=item.content,
                score=item.score,
                source=item.source or "searxng",
            ))
        
        return WebSearchResponse(
            query=query,
            results=results,
            answer=searxng_response.answer,
            elapsed_seconds=elapsed,
            source="searxng",
        )

    def search_multi(
        self,
        queries: list[str],
        *,
        max_results: int | None = None,
        inter_query_delay: float = 1.0,
    ) -> list[WebSearchResponse]:
        """Run multiple search queries with cross-query deduplication."""
        responses = []
        seen_urls: set[str] = set()

        for i, query in enumerate(queries):
            if i > 0:
                time.sleep(inter_query_delay)
            resp = self.search(query, max_results=max_results)
            unique_results = [r for r in resp.results if r.url not in seen_urls]
            seen_urls.update(r.url for r in unique_results)
            resp.results = unique_results
            responses.append(resp)

        return responses

    # ------------------------------------------------------------------
    # Tavily backend (primary — uses installed tavily-python SDK)
    # ------------------------------------------------------------------

    def _search_tavily(
        self,
        query: str,
        limit: int,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
        t0: float,
    ) -> WebSearchResponse:
        """Search using Tavily API (installed SDK)."""
        from tavily import TavilyClient

        client = TavilyClient(api_key=self.api_key)

        kwargs: dict[str, Any] = {
            "query": query,
            "max_results": limit,
            "search_depth": self.search_depth,
            "include_answer": self.include_answer,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains

        response = client.search(**kwargs)
        elapsed = time.monotonic() - t0

        results = []
        for item in response.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", "")[:500],
                content=item.get("content", ""),
                score=item.get("score", 0.0),
                source="tavily",
            ))

        return WebSearchResponse(
            query=query,
            results=results,
            answer=response.get("answer", ""),
            elapsed_seconds=elapsed,
            source="tavily",
        )

    # ------------------------------------------------------------------
    # DuckDuckGo fallback (no API key needed)
    # ------------------------------------------------------------------

    def _search_duckduckgo(
        self, query: str, limit: int, t0: float
    ) -> WebSearchResponse:
        """Fallback: scrape DuckDuckGo HTML search results."""
        encoded = quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })

        try:
            resp = urlopen(req, timeout=15)  # noqa: S310
            html = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            logger.warning("DuckDuckGo search failed: %s", exc)
            return WebSearchResponse(query=query, elapsed_seconds=elapsed, source="duckduckgo")

        results = self._parse_ddg_html(html, limit)
        elapsed = time.monotonic() - t0
        return WebSearchResponse(query=query, results=results, elapsed_seconds=elapsed, source="duckduckgo")

    @staticmethod
    def _parse_ddg_html(html: str, limit: int) -> list[SearchResult]:
        """Parse DuckDuckGo HTML results page."""
        results = []
        link_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title_html) in enumerate(links[:limit]):
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
            if "duckduckgo.com" in url:
                # Extract actual URL from DDG redirect: //duckduckgo.com/l/?uddg=https%3A...
                from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs, unquote as _unquote
                _parsed_ddg = _urlparse(url)
                _uddg = _parse_qs(_parsed_ddg.query).get("uddg")
                if _uddg:
                    url = _unquote(_uddg[0])
                else:
                    continue
            results.append(SearchResult(title=title, url=url, snippet=snippet, source="duckduckgo"))

        return results
