"""Full-text extraction from web pages for literature review.

Integrates with Firecrawl and SearXNG to extract full-text content
from academic papers, blog posts, documentation, and other web sources.

Supports:
- Academic papers (arXiv, PubMed, ACL, etc.)
- Technical blogs
- Documentation sites
- News articles
- General web pages

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.literature.full_text import FullTextExtractor, ExtractorConfig

    config = ExtractorConfig(max_chars=50000)
    extractor = FullTextExtractor(config)

    # Extract from single URL
    result = await extractor.extract("https://arxiv.org/abs/1234.5678")
    print(result.content)

    # Batch extract
    results = await extractor.extract_batch([
        "https://arxiv.org/abs/1234.5678",
        "https://arxiv.org/abs/2345.6789",
    ])
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class ExtractorConfig:
    """Full-text extractor configuration.

    Attributes:
        max_chars: Maximum characters to extract per page (default: 50000)
        min_chars: Minimum characters for valid extraction (default: 100)
        timeout: Request timeout in seconds (default: 30)
        firecrawl_enabled: Enable Firecrawl integration (default: True)
        searxng_enabled: Enable SearXNG integration (default: False)
        firecrawl_url: Firecrawl server URL
        searxng_url: SearXNG server URL
    """

    max_chars: int = 50000
    """Maximum characters to extract per page"""

    min_chars: int = 100
    """Minimum characters for valid extraction"""

    timeout: int = 30
    """Request timeout in seconds"""

    firecrawl_enabled: bool = True
    """Enable Firecrawl integration"""

    searxng_enabled: bool = False
    """Enable SearXNG integration"""

    firecrawl_url: str = "http://localhost:3000"
    """Firecrawl server URL"""

    searxng_url: str = "http://localhost:8080"
    """SearXNG server URL"""


@dataclass
class FullTextResult:
    """Result from full-text extraction.

    Attributes:
        url: Source URL
        title: Page title
        content: Extracted text content
        markdown: Extracted markdown (if available)
        authors: Detected authors
        publication_date: Detected publication date
        source_type: Type of source (paper, blog, docs, etc.)
        word_count: Number of words extracted
        char_count: Number of characters extracted
        success: Whether extraction was successful
        error: Error message if failed
        elapsed_seconds: Time taken to extract
        metadata: Additional metadata
    """

    url: str = ""
    title: str = ""
    content: str = ""
    markdown: str = ""
    authors: list[str] = field(default_factory=list)
    publication_date: str = ""
    source_type: str = ""  # paper, blog, docs, news, general
    word_count: int = 0
    char_count: int = 0
    success: bool = True
    error: str = ""
    elapsed_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "markdown": self.markdown,
            "authors": self.authors,
            "publication_date": self.publication_date,
            "source_type": self.source_type,
            "word_count": self.word_count,
            "char_count": self.char_count,
            "success": self.success,
            "error": self.error,
        }


class FullTextExtractor:
    """Extract full-text content from web pages.

    Uses Firecrawl for high-quality extraction with fallback
    to basic HTTP scraping when Firecrawl is unavailable.

    Examples:
        Basic extraction:
            >>> extractor = FullTextExtractor()
            >>> result = await extractor.extract("https://arxiv.org/abs/1234.5678")
            >>> print(f"Title: {result.title}")
            >>> print(f"Content: {result.content[:500]}")

        Batch extraction:
            >>> urls = ["https://arxiv.org/abs/1234.5678", ...]
            >>> results = await extractor.extract_batch(urls)
            >>> for r in results:
            ...     if r.success:
            ...         print(f"{r.url}: {r.word_count} words")
    """

    # Academic source patterns
    ACADEMIC_PATTERNS = {
        "arxiv": r"arxiv\.org/(abs|pdf)/",
        "pubmed": r"pubmed\.ncbi\.nlm\.nih\.gov/",
        "acl": r"aclanthology\.org/",
        "neurips": r"papers\.nips\.cc/",
        "icml": r"proceedings\.mlr\.press/",
        "iclr": r"openreview\.net/",
        "nature": r"nature\.com/",
        "science": r"science\.org/",
        "doi": r"doi\.org/",
    }

    def __init__(self, config: ExtractorConfig | None = None):
        """
        Initialize full-text extractor.

        Args:
            config: Extractor configuration (uses defaults if None)
        """
        self.config = config or ExtractorConfig()
        self._firecrawl_client = None
        self._http_client = None

    async def extract(
        self,
        url: str,
        *,
        use_firecrawl: bool | None = None,
        extract_metadata: bool = True,
    ) -> FullTextResult:
        """
        Extract full-text from a single URL.

        Args:
            url: URL to extract from
            use_firecrawl: Explicitly use Firecrawl (default: auto-detect)
            extract_metadata: Extract authors, date, etc.

        Returns:
            FullTextResult with extracted content

        Examples:
            # Basic extraction
            >>> result = await extractor.extract("https://arxiv.org/abs/1234.5678")

            # Force Firecrawl
            >>> result = await extractor.extract(
            ...     "https://example.com",
            ...     use_firecrawl=True,
            ... )
        """
        import time

        start_time = time.time()

        # Detect source type
        source_type = self._detect_source_type(url)

        # Determine extraction method
        use_fc = use_firecrawl
        if use_fc is None:
            use_fc = self.config.firecrawl_enabled

        try:
            if use_fc:
                result = await self._extract_firecrawl(url)
            else:
                result = await self._extract_basic(url)

            # Post-process
            if result.success:
                result.url = url
                result.source_type = source_type
                result.word_count = len(result.content.split())
                result.char_count = len(result.content)

                # Enforce limits
                if result.char_count > self.config.max_chars:
                    result.content = result.content[: self.config.max_chars]

                # Validate minimum
                if result.char_count < self.config.min_chars:
                    result.success = False
                    result.error = f"Content too short: {result.char_count} chars"

                # Extract metadata if requested
                if extract_metadata and result.success:
                    await self._extract_metadata(result)

            result.elapsed_seconds = time.time() - start_time
            return result

        except Exception as e:
            logger.error("Full-text extraction failed for %r: %s", url, e)
            return FullTextResult(
                url=url,
                success=False,
                error=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    async def extract_batch(
        self,
        urls: list[str],
        *,
        max_concurrent: int = 5,
        inter_url_delay: float = 0.5,
        **kwargs: Any,
    ) -> list[FullTextResult]:
        """
        Extract full-text from multiple URLs.

        Args:
            urls: List of URLs to extract from
            max_concurrent: Maximum concurrent extractions
            inter_url_delay: Delay between URLs in seconds
            **kwargs: Additional args passed to extract()

        Returns:
            List of FullTextResult objects

        Examples:
            # Batch extraction
            >>> urls = ["https://arxiv.org/abs/...", ...]
            >>> results = await extractor.extract_batch(urls, max_concurrent=3)
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def _extract_with_semaphore(url: str) -> FullTextResult:
            async with semaphore:
                result = await self.extract(url, **kwargs)
                await asyncio.sleep(inter_url_delay)
                return result

        tasks = [_extract_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(
                    FullTextResult(
                        url=urls[i],
                        success=False,
                        error=str(result),
                    )
                )
            else:
                processed.append(result)

        return processed

    async def _extract_firecrawl(self, url: str) -> FullTextResult:
        """Extract using Firecrawl (high-quality)."""
        if self._firecrawl_client is None:
            from .firecrawl_client import FirecrawlClient, FirecrawlConfig

            self._firecrawl_client = FirecrawlClient(
                FirecrawlConfig(
                    base_url=self.config.firecrawl_url,
                    timeout=self.config.timeout,
                )
            )

        scrape_result = await self._firecrawl_client.scrape(
            url,
            format="markdown",
            only_main_content=True,
            include_html=False,
        )

        if not scrape_result.success:
            return FullTextResult(
                url=url,
                success=False,
                error=scrape_result.error,
            )

        # Extract title from metadata
        title = ""
        if scrape_result.metadata:
            title = scrape_result.metadata.get("title", "")

        return FullTextResult(
            url=url,
            title=title,
            content=scrape_result.markdown,
            markdown=scrape_result.markdown,
            metadata=scrape_result.metadata,
            success=True,
        )

    async def _extract_basic(self, url: str) -> FullTextResult:
        """Extract using basic HTTP (fallback)."""
        import httpx

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                },
            )

        try:
            response = await self._http_client.get(url)
            response.raise_for_status()
            html = response.text

            # Simple HTML to text conversion
            content = self._html_to_text(html)
            title = self._extract_title(html)

            return FullTextResult(
                url=url,
                title=title,
                content=content,
                success=True,
            )

        except httpx.HTTPError as e:
            return FullTextResult(
                url=url,
                success=False,
                error=str(e),
            )

    async def _extract_metadata(self, result: FullTextResult) -> None:
        """Extract metadata from content."""
        # Extract authors (common patterns)
        author_patterns = [
            r"Authors?:?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            r"by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+et\s+al",
        ]

        for pattern in author_patterns:
            match = re.search(pattern, result.content[:2000])
            if match:
                authors_str = match.group(1)
                # Split by common separators
                authors = re.split(r",|and|&", authors_str)
                result.authors = [a.strip() for a in authors if a.strip()]
                break

        # Extract publication date
        date_patterns = [
            r"(\d{4}-\d{2}-\d{2})",  # ISO format
            r"(\w+\s+\d{1,2},?\s+\d{4})",  # Month Day, Year
            r"(\d{1,2}\s+\w+\s+\d{4})",  # Day Month Year
        ]

        for pattern in date_patterns:
            match = re.search(pattern, result.content[:2000])
            if match:
                result.publication_date = match.group(1)
                break

    def _detect_source_type(self, url: str) -> str:
        """Detect the type of source from URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()

        # Academic papers
        for source, pattern in self.ACADEMIC_PATTERNS.items():
            if re.search(pattern, url, re.IGNORECASE):
                return "paper"

        # Technical blogs
        blog_indicators = ["blog", "medium", "substack", "dev.to"]
        if any(ind in domain for ind in blog_indicators):
            return "blog"

        # Documentation
        docs_indicators = ["docs", "documentation", "api", "reference"]
        if any(ind in path for ind in docs_indicators):
            return "docs"

        # News
        news_indicators = ["news", "article", "story"]
        if any(ind in domain or ind in path for ind in news_indicators):
            return "news"

        return "general"

    def _extract_title(self, html: str) -> str:
        """Extract title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text (basic)."""
        # Remove scripts and styles
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        return text

    async def close(self) -> None:
        """Close HTTP clients."""
        if self._firecrawl_client:
            await self._firecrawl_client.close()
        if self._http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> FullTextExtractor:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


def create_extractor_from_env() -> FullTextExtractor:
    """
    Create FullTextExtractor from environment variables.

    Environment Variables:
        FIRECRAWL_BASE_URL: Firecrawl server URL
        SEARXNG_BASE_URL: SearXNG server URL
        EXTRACTOR_MAX_CHARS: Maximum characters per extraction
        EXTRACTOR_TIMEOUT: Request timeout in seconds

    Returns:
        FullTextExtractor configured from environment
    """
    import os

    return FullTextExtractor(
        ExtractorConfig(
            firecrawl_url=os.environ.get("FIRECRAWL_BASE_URL", "http://localhost:3000"),
            searxng_url=os.environ.get("SEARXNG_BASE_URL", "http://localhost:8080"),
            max_chars=int(os.environ.get("EXTRACTOR_MAX_CHARS", "50000")),
            timeout=int(os.environ.get("EXTRACTOR_TIMEOUT", "30")),
        )
    )
