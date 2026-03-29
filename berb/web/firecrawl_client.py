"""Firecrawl web scraping and crawling client for Berb.

Firecrawl provides:
- Scrape: Single URL → markdown/HTML/JSON/screenshot
- Crawl: Entire website (100s of pages)
- Map: Discover all URLs on website
- Search: Web search + full page content
- Extract: Structured data (JSON schema)
- JavaScript rendering (dynamic content)

Self-hosted via Docker for unlimited crawling.

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.web.firecrawl_client import FirecrawlClient, FirecrawlConfig

    config = FirecrawlConfig(api_key="...", base_url="http://localhost:3000")
    client = FirecrawlClient(config)

    # Scrape single page
    result = await client.scrape("https://arxiv.org/abs/1234.5678")

    # Crawl entire site
    crawl_result = await client.crawl("https://example.com", max_pages=100)

    # Extract structured data
    data = await client.extract(
        "https://example.com/papers",
        schema={"title": "string", "authors": "array"}
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ScrapeFormat(str, Enum):
    """Output format for scraping."""

    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    SCREENSHOT = "screenshot"
    LINKS = "links"


@dataclass
class FirecrawlConfig:
    """Firecrawl configuration.

    Attributes:
        api_key: Firecrawl API key (required for cloud, optional for self-hosted)
        base_url: Firecrawl server URL (default: http://localhost:3000)
        timeout: Request timeout in seconds (default: 60)
        max_retries: Maximum retry attempts (default: 3)
        retry_delay: Delay between retries in seconds (default: 1.0)
    """

    api_key: str = ""
    """Firecrawl API key"""

    base_url: str = "http://localhost:3000"
    """Firecrawl server URL"""

    timeout: int = 60
    """Request timeout in seconds"""

    max_retries: int = 3
    """Maximum retry attempts"""

    retry_delay: float = 1.0
    """Delay between retries in seconds"""


@dataclass
class ScrapeResult:
    """Result from scraping a single URL.

    Attributes:
        url: Scraped URL
        markdown: Page content as markdown
        html: Raw HTML (if requested)
        screenshot: Screenshot base64 (if requested)
        links: List of links on page (if requested)
        metadata: Page metadata (title, description, etc.)
        success: Whether scraping was successful
        error: Error message if failed
        elapsed_seconds: Time taken to scrape
    """

    url: str = ""
    markdown: str = ""
    html: str = ""
    screenshot: str = ""
    links: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str = ""
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "markdown": self.markdown,
            "html": self.html,
            "screenshot": self.screenshot,
            "links": self.links,
            "metadata": self.metadata,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class CrawlResult:
    """Result from crawling a website.

    Attributes:
        base_url: Base URL that was crawled
        pages: List of ScrapeResult for each page
        total_pages: Total number of pages crawled
        total_tokens: Total tokens extracted
        elapsed_seconds: Time taken to crawl
        success: Whether crawl was successful
        error: Error message if failed
    """

    base_url: str = ""
    pages: list[ScrapeResult] = field(default_factory=list)
    total_pages: int = 0
    total_tokens: int = 0
    elapsed_seconds: float = 0.0
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "base_url": self.base_url,
            "pages": [p.to_dict() for p in self.pages],
            "total_pages": self.total_pages,
            "total_tokens": self.total_tokens,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class MapResult:
    """Result from mapping a website's URLs.

    Attributes:
        base_url: Base URL that was mapped
        urls: List of discovered URLs
        total_urls: Total number of URLs found
        elapsed_seconds: Time taken to map
    """

    base_url: str = ""
    urls: list[str] = field(default_factory=list)
    total_urls: int = 0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "base_url": self.base_url,
            "urls": self.urls,
            "total_urls": self.total_urls,
            "elapsed_seconds": self.elapsed_seconds,
        }


class FirecrawlClient:
    """Client for Firecrawl web scraping and crawling.

    Provides comprehensive web scraping capabilities:
    - Single page scraping (markdown/HTML/screenshot)
    - Full website crawling (100s of pages)
    - URL discovery (sitemap, link following)
    - Structured data extraction (JSON schema)
    - JavaScript rendering support

    Examples:
        Basic scraping:
            >>> client = FirecrawlClient()
            >>> result = await client.scrape("https://arxiv.org/abs/1234.5678")
            >>> print(result.markdown[:500])

        Website crawling:
            >>> result = await client.crawl(
            ...     "https://example.com",
            ...     max_pages=100,
            ...     max_depth=3,
            ... )
            >>> print(f"Crawled {result.total_pages} pages")

        Structured extraction:
            >>> schema = {
            ...     "type": "object",
            ...     "properties": {
            ...         "title": {"type": "string"},
            ...         "authors": {"type": "array", "items": {"type": "string"}},
            ...     }
            ... }
            >>> result = await client.extract("https://arxiv.org/list/cs.AI/recent", schema)
    """

    def __init__(self, config: FirecrawlConfig | None = None):
        """
        Initialize Firecrawl client.

        Args:
            config: Firecrawl configuration (uses defaults if None)
        """
        self.config = config or FirecrawlConfig()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            follow_redirects=True,
        )

    async def scrape(
        self,
        url: str,
        *,
        format: ScrapeFormat = ScrapeFormat.MARKDOWN,
        only_main_content: bool = True,
        include_html: bool = False,
        include_links: bool = False,
        include_screenshot: bool = False,
        wait_for: int = 0,  # Wait for JS rendering (ms)
        headers: dict[str, str] | None = None,
    ) -> ScrapeResult:
        """
        Scrape a single URL.

        Args:
            url: URL to scrape
            format: Output format (markdown/html/json/screenshot/links)
            only_main_content: Extract only main content (exclude nav/footers)
            include_html: Include raw HTML in response
            include_links: Include list of links on page
            include_screenshot: Include screenshot (base64)
            wait_for: Wait for JavaScript rendering (milliseconds)
            headers: Custom headers for request

        Returns:
            ScrapeResult with scraped content

        Raises:
            httpx.HTTPError: If scraping fails
            httpx.TimeoutException: If request times out

        Examples:
            # Basic scraping
            >>> result = await client.scrape("https://arxiv.org/abs/1234.5678")
            >>> print(result.markdown)

            # With screenshot
            >>> result = await client.scrape(
            ...     "https://example.com",
            ...     include_screenshot=True,
            ... )

            # Wait for dynamic content
            >>> result = await client.scrape(
            ...     "https://example.com",
            ...     wait_for=2000,  # Wait 2 seconds for JS
            ... )
        """
        import time

        start_time = time.time()

        payload = {
            "url": url,
            "formats": [format.value],
            "onlyMainContent": only_main_content,
        }

        if include_html and format != ScrapeFormat.HTML:
            payload["formats"].append("html")
        if include_links:
            payload["formats"].append("links")
        if include_screenshot:
            payload["formats"].append("screenshot")
        if wait_for > 0:
            payload["waitFor"] = wait_for
        if headers:
            payload["headers"] = headers

        # Add API key if configured
        if self.config.api_key:
            payload["apiKey"] = self.config.api_key

        try:
            response = await self._client.post("/scrape", json=payload)
            response.raise_for_status()
            data = response.json()

            if not data.get("success", False):
                return ScrapeResult(
                    url=url,
                    success=False,
                    error=data.get("error", "Unknown error"),
                    elapsed_seconds=time.time() - start_time,
                )

            scrape_data = data.get("data", {})

            result = ScrapeResult(
                url=url,
                markdown=scrape_data.get("markdown", ""),
                html=scrape_data.get("html", ""),
                screenshot=scrape_data.get("screenshot", ""),
                links=scrape_data.get("links", []),
                metadata=scrape_data.get("metadata", {}),
                success=True,
                elapsed_seconds=time.time() - start_time,
            )

            return result

        except httpx.HTTPError as e:
            logger.error("Firecrawl scrape failed for URL %r: %s", url, e)
            return ScrapeResult(
                url=url,
                success=False,
                error=str(e),
                elapsed_seconds=time.time() - start_time,
            )
        except Exception as e:
            logger.error("Unexpected error during Firecrawl scrape: %s", e)
            return ScrapeResult(
                url=url,
                success=False,
                error=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    async def crawl(
        self,
        url: str,
        *,
        max_pages: int = 100,
        max_depth: int = 3,
        exclude_paths: list[str] | None = None,
        include_paths: list[str] | None = None,
        allow_external: bool = False,
        ignore_sitemap: bool = False,
        limit: int | None = None,
        scrape_options: dict[str, Any] | None = None,
    ) -> CrawlResult:
        """
        Crawl an entire website.

        Args:
            url: Base URL to start crawling from
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum link depth to follow
            exclude_paths: URL patterns to exclude (regex)
            include_paths: URL patterns to include (regex)
            allow_external: Allow crawling external links
            ignore_sitemap: Don't use sitemap.xml
            limit: Alias for max_pages
            scrape_options: Options for individual page scraping

        Returns:
            CrawlResult with all crawled pages

        Raises:
            httpx.HTTPError: If crawling fails
            httpx.TimeoutException: If request times out

        Examples:
            # Basic crawl
            >>> result = await client.crawl(
            ...     "https://example.com",
            ...     max_pages=100,
            ...     max_depth=2,
            ... )

            # Focused crawl (specific paths only)
            >>> result = await client.crawl(
            ...     "https://example.com",
            ...     include_paths=["/papers/", "/research/"],
            ...     exclude_paths=["/blog/", "/news/"],
            ... )
        """
        import time

        start_time = time.time()

        payload = {
            "url": url,
            "limit": limit or max_pages,
            "maxDepth": max_depth,
            "scrapeOptions": scrape_options or {},
        }

        if exclude_paths:
            payload["excludePaths"] = exclude_paths
        if include_paths:
            payload["includePaths"] = include_paths
        payload["allowExternalLinks"] = allow_external
        payload["ignoreSitemap"] = ignore_sitemap

        # Add API key if configured
        if self.config.api_key:
            payload["apiKey"] = self.config.api_key

        try:
            # Start crawl job
            response = await self._client.post("/crawl", json=payload)
            response.raise_for_status()
            job_data = response.json()

            job_id = job_data.get("jobId")
            if not job_id:
                return CrawlResult(
                    base_url=url,
                    success=False,
                    error="No job ID returned",
                    elapsed_seconds=time.time() - start_time,
                )

            # Poll for completion
            result = await self._poll_crawl_job(job_id, start_time)
            result.base_url = url
            return result

        except httpx.HTTPError as e:
            logger.error("Firecrawl crawl failed for URL %r: %s", url, e)
            return CrawlResult(
                base_url=url,
                success=False,
                error=str(e),
                elapsed_seconds=time.time() - start_time,
            )
        except Exception as e:
            logger.error("Unexpected error during Firecrawl crawl: %s", e)
            return CrawlResult(
                base_url=url,
                success=False,
                error=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    async def _poll_crawl_job(
        self,
        job_id: str,
        start_time: float,
        poll_interval: float = 2.0,
    ) -> CrawlResult:
        """Poll crawl job until completion."""
        import asyncio

        while True:
            await asyncio.sleep(poll_interval)

            try:
                response = await self._client.get(f"/crawl/status/{job_id}")
                response.raise_for_status()
                status_data = response.json()

                status = status_data.get("status")

                if status == "completed":
                    # Collect all results
                    pages = []
                    total_tokens = 0
                    for page_data in status_data.get("data", []):
                        page_result = ScrapeResult(
                            url=page_data.get("url", ""),
                            markdown=page_data.get("markdown", ""),
                            html=page_data.get("html", ""),
                            metadata=page_data.get("metadata", {}),
                            success=True,
                        )
                        pages.append(page_result)
                        # Estimate tokens
                        total_tokens += len(page_result.markdown) // 4

                    return CrawlResult(
                        pages=pages,
                        total_pages=len(pages),
                        total_tokens=total_tokens,
                        success=True,
                        elapsed_seconds=time.time() - start_time,
                    )

                elif status == "failed":
                    return CrawlResult(
                        success=False,
                        error=status_data.get("error", "Crawl failed"),
                        elapsed_seconds=time.time() - start_time,
                    )

                # Still processing
                logger.debug("Crawl job %s status: %s", job_id, status)

            except Exception as e:
                logger.warning("Error polling crawl job: %s", e)
                # Continue polling

    async def map(
        self,
        url: str,
        *,
        sitemap_only: bool = False,
        include_subdomains: bool = False,
    ) -> MapResult:
        """
        Discover all URLs on a website.

        Args:
            url: Base URL to map
            sitemap_only: Only use sitemap.xml
            include_subdomains: Include subdomain URLs

        Returns:
            MapResult with discovered URLs

        Examples:
            # Map all URLs
            >>> result = await client.map("https://example.com")
            >>> print(f"Found {result.total_urls} URLs")

            # Sitemap only
            >>> result = await client.map(
            ...     "https://example.com",
            ...     sitemap_only=True,
            ... )
        """
        import time

        start_time = time.time()

        payload = {
            "url": url,
            "sitemapOnly": sitemap_only,
            "includeSubdomains": include_subdomains,
        }

        if self.config.api_key:
            payload["apiKey"] = self.config.api_key

        try:
            response = await self._client.post("/map", json=payload)
            response.raise_for_status()
            data = response.json()

            urls = data.get("urls", [])

            return MapResult(
                base_url=url,
                urls=urls,
                total_urls=len(urls),
                elapsed_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error("Firecrawl map failed for URL %r: %s", url, e)
            return MapResult(
                base_url=url,
                urls=[],
                total_urls=0,
                elapsed_seconds=time.time() - start_time,
            )

    async def extract(
        self,
        url: str,
        schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Extract structured data from a webpage using LLM.

        Args:
            url: URL to extract from
            schema: JSON schema for expected output
            system_prompt: System prompt for extraction
            prompt: User prompt for extraction

        Returns:
            Extracted data matching schema

        Examples:
            # Extract paper metadata
            >>> schema = {
            ...     "type": "object",
            ...     "properties": {
            ...         "title": {"type": "string"},
            ...         "authors": {"type": "array", "items": {"type": "string"}},
            ...         "abstract": {"type": "string"},
            ...     },
            ...     "required": ["title", "authors"]
            ... }
            >>> result = await client.extract(
            ...     "https://arxiv.org/abs/1234.5678",
            ...     schema,
            ... )
        """
        payload = {
            "url": url,
            "schema": schema,
        }

        if system_prompt:
            payload["systemPrompt"] = system_prompt
        if prompt:
            payload["prompt"] = prompt

        if self.config.api_key:
            payload["apiKey"] = self.config.api_key

        try:
            response = await self._client.post("/extract", json=payload)
            response.raise_for_status()
            data = response.json()

            if not data.get("success", False):
                logger.error("Firecrawl extract failed: %s", data.get("error"))
                return {}

            return data.get("data", {})

        except Exception as e:
            logger.error("Firecrawl extract failed for URL %r: %s", url, e)
            return {}

    async def health_check(self) -> bool:
        """
        Check if Firecrawl server is healthy.

        Returns:
            True if server is reachable and responding

        Examples:
            >>> if await client.health_check():
            ...     print("Firecrawl is online")
        """
        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> FirecrawlClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


def create_firecrawl_client_from_env() -> FirecrawlClient:
    """
    Create Firecrawl client from environment variables.

    Environment Variables:
        FIRECRAWL_API_KEY: Firecrawl API key (optional for self-hosted)
        FIRECRAWL_BASE_URL: Firecrawl server URL (default: http://localhost:3000)
        FIRECRAWL_TIMEOUT: Request timeout in seconds (default: 60)

    Returns:
        FirecrawlClient configured from environment

    Examples:
        # In .env file:
        # FIRECRAWL_API_KEY=your-api-key
        # FIRECRAWL_BASE_URL=http://firecrawl:3000
        # FIRECRAWL_TIMEOUT=120

        >>> client = create_firecrawl_client_from_env()
    """
    import os

    return FirecrawlClient(
        FirecrawlConfig(
            api_key=os.environ.get("FIRECRAWL_API_KEY", ""),
            base_url=os.environ.get("FIRECRAWL_BASE_URL", "http://localhost:3000"),
            timeout=int(os.environ.get("FIRECRAWL_TIMEOUT", "60")),
        )
    )
