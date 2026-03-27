# SearXNG + Firecrawl Integration Plan for Berb

**Ανάλυση Δυνατοτήτων & Σχέδιο Ολοκλήρωσης στο Berb**

**Ημερομηνία:** 2026-03-27  
**Πηγές:** 
- SearXNG (searxng-master/) - Privacy metasearch engine
- Firecrawl (firecrawl-main/) - Web scraping & crawling API

---

## 📊 Executive Summary

### **SearXNG**
- **Τι είναι:** Privacy-focused metasearch engine
- **Πηγές:** 100+ search engines (Google, Bing, DuckDuckGo, Wikipedia, arXiv, etc.)
- **Κύρια Χαρακτηριστικά:**
  - No tracking, no profiling
  - Self-hostable (Docker)
  - 70+ languages
  - Search syntax (!images, !wp, !map, etc.)
  - API support (JSON format)

### **Firecrawl**
- **Τι είναι:** Web scraping/crawling API για LLM-ready data
- **Πηγές:** Any website (JavaScript rendering, dynamic content)
- **Κύρια Χαρακτηριστικά:**
  - Scrape → Markdown/HTML/JSON/Screenshot
  - Crawl → Entire website (100s-1000s of pages)
  - Map → Discover all URLs on website
  - Search → Web search with full page content
  - Extract → Structured data (JSON schema)
  - Self-hostable (Docker)

### **Value Proposition για Berb**
| Feature | Current Berb | With SearXNG | With Firecrawl | Combined |
|---------|-------------|--------------|----------------|----------|
| **Web Search** | Tavily (paid) + DuckDuckGo | 100+ engines (free) | ✅ | ✅✅ |
| **Academic Search** | OpenAlex, S2, arXiv | ✅ (arXiv, Wikipedia) | ❌ | ✅✅ |
| **Full-Page Scraping** | ❌ | ❌ | ✅ (JS rendering) | ✅✅ |
| **Website Crawling** | ❌ | ❌ | ✅ (100s of pages) | ✅✅ |
| **Structured Extraction** | ❌ | ❌ | ✅ (JSON schema) | ✅✅ |
| **Privacy** | Mixed | ✅✅ (no tracking) | ✅ (self-hosted) | ✅✅ |
| **Cost** | $10-30/month (Tavily) | $0 (self-hosted) | $0 (self-hosted) | $0 |

**Συνιστώμενη Στρατηγική:**
- ✅ **Integrate SearXNG** as primary web search (replace Tavily paid tier)
- ✅ **Integrate Firecrawl** for full-page scraping & crawling
- ✅ **Self-host both** for zero cost + privacy
- ✅ **Keep Tavily** as fallback (free tier)

---

## 🎯 SearXNG Integration

### **1.1 Architecture**

```
berb/web/search.py (enhanced)
├── SearXNGClient (NEW)
│   ├── search() → WebSearchResponse
│   ├── search_multi() → list[WebSearchResponse]
│   └── Special syntax support (!images, !wp, !arxiv, etc.)
├── TavilyClient (existing)
└── DuckDuckGoClient (existing fallback)

docker-compose.yml (NEW)
├── searxng service
├── redis cache (for SearXNG)
└── caddy reverse proxy (optional)
```

### **1.2 Implementation**

```python
# berb/web/searxng_client.py
"""SearXNG web search client for Berb."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .search import SearchResult, WebSearchResponse

logger = logging.getLogger(__name__)


@dataclass
class SearXNGConfig:
    """SearXNG configuration."""
    
    base_url: str = "http://localhost:8080"
    """SearXNG server URL"""
    
    engines: list[str] | None = None
    """Specific engines to use (default: all)"""
    
    categories: list[str] | None = None
    """Categories: general, science, images, videos, etc."""
    
    language: str = "en"
    """Search language"""
    
    safe_search: int = 0
    """0=off, 1=moderate, 2=strict"""
    
    timeout: int = 30
    """Request timeout in seconds"""


class SearXNGClient:
    """Client for SearXNG metasearch engine."""
    
    def __init__(self, config: SearXNGConfig | None = None):
        self.config = config or SearXNGConfig()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )
    
    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        engines: list[str] | None = None,
        categories: list[str] | None = None,
        language: str | None = None,
    ) -> WebSearchResponse:
        """
        Search using SearXNG.
        
        Args:
            query: Search query
            max_results: Maximum results
            engines: Specific engines (e.g., ["google", "bing", "arxiv"])
            categories: Categories (e.g., ["science", "general"])
            language: Language code (e.g., "en", "fr")
        
        Returns:
            WebSearchResponse with results
        
        Examples:
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
        params = {
            "q": query,
            "format": "json",
            "pageno": 1,
        }
        
        if engines or self.config.engines:
            params["engines"] = ",".join(engines or self.config.engines)
        
        if categories or self.config.categories:
            params["categories"] = ",".join(categories or self.config.categories)
        
        if language or self.config.language:
            params["language"] = language or self.config.language
        
        params["safe_search"] = self.config.safe_search
        
        response = await self._client.get("/search", params=params)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", [])[:max_results]:
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
        )
    
    async def search_multi(
        self,
        queries: list[str],
        *,
        max_results: int = 10,
        inter_query_delay: float = 0.5,
    ) -> list[WebSearchResponse]:
        """Search multiple queries with rate limiting."""
        import asyncio
        
        responses = []
        for i, query in enumerate(queries):
            if i > 0:
                await asyncio.sleep(inter_query_delay)
            resp = await self.search(query, max_results=max_results)
            responses.append(resp)
        
        return responses
    
    async def get_engines(self) -> list[dict[str, Any]]:
        """Get list of available engines."""
        response = await self._client.get("/engines")
        response.raise_for_status()
        return response.json()
    
    async def health_check(self) -> bool:
        """Check if SearXNG server is healthy."""
        try:
            response = await self._client.get("/")
            return response.status_code == 200
        except Exception:
            return False
```

### **1.3 Docker Compose Setup**

```yaml
# docker-compose.searxng.yml
version: '3.8'

services:
  searxng:
    image: searxng/searxng:latest
    container_name: berb-searxng
    ports:
      - "8080:8080"
    volumes:
      - ./searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://localhost:8080
      - SEARXNG_SECRET_KEY=CHANGEME
    depends_on:
      - redis
    networks:
      - berb-network
    restart: unless-stopped
  
  redis:
    image: redis:alpine
    container_name: berb-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    networks:
      - berb-network
    restart: unless-stopped

volumes:
  redis-data:

networks:
  berb-network:
    driver: bridge
```

### **1.4 SearXNG Configuration**

```yaml
# searxng/settings.yml
use_default_settings: true

general:
  debug: false
  instance_name: "Berb Search"
  donation_url: null
  contact_url: null
  enable_metrics: true

search:
  safe_search: 0
  autocomplete: "google"
  default_lang: "en"
  
  engines:
    - name: arxiv
      engine: arxiv
      shortcut: !arxiv
      categories: science
      timeout: 30
    
    - name: google scholar
      engine: google_scholar
      shortcut: !gs
      categories: science
    
    - name: wikipedia
      engine: wikipedia
      shortcut: !wp
      categories: general
    
    - name: duckduckgo
      engine: duckduckgo
      shortcut: !ddg
      categories: general
    
    - name: bing
      engine: bing
      shortcut: !bing
      categories: general
    
    - name: pubmed
      engine: pubmed
      shortcut: !pm
      categories: science
      timeout: 30
    
    - name: zenodo
      engine: json_engine
      shortcut: !zen
      categories: science
      search_url: https://zenodo.org/api/records/
      results_parameter: hits.hits
    
    - name: clinicaltrials
      engine: json_engine
      shortcut: !ct
      categories: science
      search_url: https://clinicaltrials.gov/api/query/
    
    - name: github
      engine: github
      shortcut: !gh
      categories: it
    
    - name: stackoverflow
      engine: stackoverflow
      shortcut: !so
      categories: it

server:
  secret_key: "CHANGEME"
  limiter: false
  image_proxy: true
  http_protocol_version: "1.0"

outgoing:
  request_timeout: 30.0
  max_request_timeout: 60.0
  useragent_suffix: "Berb/1.0"
```

### **1.5 Integration with Existing Search**

```python
# berb/web/search.py (enhanced)

class WebSearchClient:
    """Enhanced web search client with SearXNG support."""
    
    def __init__(
        self,
        *,
        api_key: str = "",
        max_results: int = 10,
        search_depth: str = "advanced",
        include_answer: bool = True,
        searxng_url: str | None = None,  # NEW
        use_searxng_primary: bool = True,  # NEW
    ) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self.max_results = max_results
        
        # SearXNG integration
        if searxng_url:
            self.searxng_client = SearXNGClient(
                SearXNGConfig(base_url=searxng_url)
            )
            self.use_searxng_primary = use_searxng_primary
        else:
            self.searxng_client = None
            self.use_searxng_primary = False
    
    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        engine: str | None = None,  # NEW: "searxng", "tavily", "duckduckgo"
    ) -> WebSearchResponse:
        """Search with engine selection."""
        limit = max_results or self.max_results
        
        # Explicit engine selection
        if engine == "searxng" and self.searxng_client:
            return await self.searxng_client.search(query, max_results=limit)
        elif engine == "tavily":
            return self._search_tavily(query, limit)
        elif engine == "duckduckgo":
            return self._search_duckduckgo(query, limit)
        
        # Automatic selection
        if self.use_searxng_primary and self.searxng_client:
            try:
                return await self.searxng_client.search(query, max_results=limit)
            except Exception as exc:
                logger.warning("SearXNG failed, falling back: %s", exc)
        
        # Fallback chain: Tavily → DuckDuckGo
        if self.api_key:
            try:
                return self._search_tavily(query, limit)
            except Exception as exc:
                logger.warning("Tavily failed, falling back to DDG: %s", exc)
        
        return self._search_duckduckgo(query, limit)
```

---

## 🎯 Firecrawl Integration

### **2.1 Architecture**

```
berb/web/scraper.py (NEW)
├── FirecrawlClient
│   ├── scrape() → ScrapeResult (markdown/HTML/JSON/screenshot)
│   ├── crawl() → CrawlResult (100s of pages)
│   ├── map() → list[str] (all URLs)
│   ├── search() → WebSearchResponse (search + scrape)
│   └── extract() → StructuredData (JSON schema)

berb/literature/full_text.py (NEW)
└── FullTextExtractor
    └── extract_from_url() → str (clean full text)
```

### **2.2 Implementation**

```python
# berb/web/scraper.py
"""Firecrawl web scraping client for Berb."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from firecrawl import FirecrawlApp  # pip install firecrawl-py

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    """Result from scraping a single URL."""
    
    url: str
    markdown: str
    html: str | None = None
    screenshot: str | None = None  # base64
    links: list[str] | None = None
    metadata: dict[str, Any] | None = None
    success: bool = True
    error: str | None = None


@dataclass
class CrawlResult:
    """Result from crawling a website."""
    
    total_pages: int
    pages: list[ScrapeResult]
    success: bool = True
    error: str | None = None


class FirecrawlClient:
    """Client for Firecrawl web scraping API."""
    
    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout: int = 120,
    ):
        """
        Initialize Firecrawl client.
        
        Args:
            api_key: Firecrawl API key (from firecrawl.dev or self-hosted)
            api_url: Self-hosted API URL (default: cloud API)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.api_url = api_url
        self.timeout = timeout
        
        self._client = FirecrawlApp(
            api_key=api_key,
            api_url=api_url,
        )
    
    async def scrape(
        self,
        url: str,
        *,
        formats: list[str] | None = None,
        only_main_content: bool = True,
        wait_for: int | None = None,
        timeout: int | None = None,
    ) -> ScrapeResult:
        """
        Scrape a single URL.
        
        Args:
            url: URL to scrape
            formats: Output formats ["markdown", "html", "screenshot", "links"]
            only_main_content: Filter out nav/footer/etc.
            wait_for: Wait milliseconds for JS to load
            timeout: Request timeout
        
        Returns:
            ScrapeResult with content in requested formats
        
        Examples:
            # Basic scrape
            result = await client.scrape("https://example.com")
            print(result.markdown)
            
            # With screenshot
            result = await client.scrape(
                "https://example.com",
                formats=["markdown", "screenshot"],
            )
            
            # Wait for JS
            result = await client.scrape(
                "https://example.com",
                wait_for=3000,  # 3 seconds
            )
        """
        formats = formats or ["markdown"]
        
        try:
            result = self._client.scrape_url(
                url=url,
                params={
                    "formats": formats,
                    "onlyMainContent": only_main_content,
                    "waitFor": wait_for,
                    "timeout": timeout or self.timeout,
                },
            )
            
            return ScrapeResult(
                url=url,
                markdown=result.get("markdown", ""),
                html=result.get("html"),
                screenshot=result.get("screenshot"),
                links=result.get("links"),
                metadata=result.get("metadata"),
                success=True,
            )
            
        except Exception as e:
            logger.error("Firecrawl scrape failed for %s: %s", url, e)
            return ScrapeResult(
                url=url,
                markdown="",
                success=False,
                error=str(e),
            )
    
    async def crawl(
        self,
        url: str,
        *,
        limit: int = 100,
        max_depth: int = 2,
        allow_backward_links: bool = False,
        exclude_paths: list[str] | None = None,
        formats: list[str] | None = None,
        poll_interval: int = 30,
    ) -> CrawlResult:
        """
        Crawl an entire website.
        
        Args:
            url: Starting URL
            limit: Maximum pages to crawl
            max_depth: Maximum crawl depth
            allow_backward_links: Allow crawling parent pages
            exclude_paths: URL patterns to exclude
            formats: Output formats
            poll_interval: Status check interval
        
        Returns:
            CrawlResult with all pages
        
        Examples:
            # Basic crawl
            result = await client.crawl(
                "https://docs.firecrawl.dev",
                limit=50,
            )
            print(f"Crawled {result.total_pages} pages")
            
            # Deep crawl with exclusions
            result = await client.crawl(
                "https://example.com",
                limit=100,
                max_depth=3,
                exclude_paths=["/blog/*", "/api/*"],
            )
        """
        formats = formats or ["markdown"]
        
        try:
            crawl_result = self._client.crawl_url(
                url=url,
                params={
                    "limit": limit,
                    "maxDepth": max_depth,
                    "allowBackwardLinks": allow_backward_links,
                    "excludePaths": exclude_paths or [],
                    "scrapeOptions": {
                        "formats": formats,
                        "onlyMainContent": True,
                    },
                },
                poll_interval=poll_interval,
            )
            
            pages = []
            for page in crawl_result.get("data", []):
                pages.append(ScrapeResult(
                    url=page.get("metadata", {}).get("sourceURL", url),
                    markdown=page.get("markdown", ""),
                    html=page.get("html"),
                    metadata=page.get("metadata"),
                ))
            
            return CrawlResult(
                total_pages=len(pages),
                pages=pages,
                success=True,
            )
            
        except Exception as e:
            logger.error("Firecrawl crawl failed for %s: %s", url, e)
            return CrawlResult(
                total_pages=0,
                pages=[],
                success=False,
                error=str(e),
            )
    
    async def map(self, url: str) -> list[str]:
        """
        Discover all URLs on a website.
        
        Args:
            url: Website URL
        
        Returns:
            List of URLs
        
        Examples:
            urls = await client.map("https://example.com")
            print(f"Found {len(urls)} URLs")
        """
        try:
            result = self._client.map_url(url=url)
            return result.get("urls", [])
        except Exception as e:
            logger.error("Firecrawl map failed for %s: %s", url, e)
            return []
    
    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        scrape_results: bool = True,
    ) -> list[ScrapeResult]:
        """
        Search the web and scrape results.
        
        Args:
            query: Search query
            max_results: Maximum results
            scrape_results: Scrape full page content
        
        Returns:
            List of ScrapeResult
        
        Examples:
            # Search only
            results = await client.search("CRISPR gene editing")
            
            # Search + scrape full content
            results = await client.search(
                "CRISPR gene editing",
                scrape_results=True,
            )
        """
        try:
            search_result = self._client.search(
                query=query,
                params={
                    "limit": max_results,
                },
            )
            
            if not scrape_results:
                return [
                    ScrapeResult(
                        url=item.get("url", ""),
                        markdown=item.get("content", ""),
                        metadata=item.get("metadata"),
                    )
                    for item in search_result.get("data", [])
                ]
            
            # Scrape each result
            pages = []
            for item in search_result.get("data", [])[:max_results]:
                url = item.get("url", "")
                page = await self.scrape(url)
                pages.append(page)
            
            return pages
            
        except Exception as e:
            logger.error("Firecrawl search failed for %s: %s", query, e)
            return []
    
    async def extract(
        self,
        url: str,
        schema: dict[str, Any],
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Extract structured data using AI.
        
        Args:
            url: URL to extract from
            schema: JSON schema for extraction
            prompt: Optional prompt for extraction
        
        Returns:
            Extracted data matching schema
        
        Examples:
            from pydantic import BaseModel
            
            class CompanyInfo(BaseModel):
                company_mission: str
                is_open_source: bool
                is_in_yc: bool
            
            result = await client.extract(
                "https://firecrawl.dev",
                schema=CompanyInfo.model_json_schema(),
            )
            print(result)
        """
        try:
            result = self._client.extract(
                url=url,
                params={
                    "schema": schema,
                    "prompt": prompt,
                },
            )
            return result.get("data", {})
        except Exception as e:
            logger.error("Firecrawl extract failed for %s: %s", url, e)
            return {}
```

### **2.3 Full-Text Extraction**

```python
# berb/literature/full_text.py
"""Full-text extraction from web pages."""

from __future__ import annotations

import logging
from pathlib import Path

from berb.web.scraper import FirecrawlClient, ScrapeResult

logger = logging.getLogger(__name__)


class FullTextExtractor:
    """Extract clean full text from web pages."""
    
    def __init__(self, firecrawl_client: FirecrawlClient | None = None):
        self.firecrawl = firecrawl_client or FirecrawlClient()
    
    async def extract_from_url(
        self,
        url: str,
        *,
        only_main_content: bool = True,
        include_links: bool = False,
    ) -> str:
        """
        Extract full text from a URL.
        
        Args:
            url: URL to extract from
            only_main_content: Filter out nav/footer/etc.
            include_links: Include extracted links
        
        Returns:
            Clean markdown text
        """
        result = await self.firecrawl.scrape(
            url,
            formats=["markdown", "links"] if include_links else ["markdown"],
            only_main_content=only_main_content,
        )
        
        if not result.success:
            logger.warning("Extraction failed for %s: %s", url, result.error)
            return ""
        
        return result.markdown
    
    async def extract_from_urls(
        self,
        urls: list[str],
        *,
        max_concurrent: int = 5,
    ) -> dict[str, str]:
        """
        Extract full text from multiple URLs.
        
        Args:
            urls: List of URLs
            max_concurrent: Maximum concurrent requests
        
        Returns:
            Dict mapping URL → text
        """
        import asyncio
        
        async def extract_one(url: str) -> tuple[str, str]:
            text = await self.extract_from_url(url)
            return (url, text)
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def with_semaphore(url: str) -> tuple[str, str]:
            async with semaphore:
                return await extract_one(url)
        
        tasks = [with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        extracted = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("Extraction failed: %s", result)
            else:
                url, text = result
                if text:
                    extracted[url] = text
        
        return extracted
    
    async def extract_from_pdf(
        self,
        url: str,
    ) -> str | None:
        """
        Extract text from PDF URL.
        
        Note: Requires Firecrawl with PDF parsing enabled.
        """
        result = await self.firecrawl.scrape(
            url,
            formats=["markdown"],
        )
        
        if result.success and result.markdown:
            return result.markdown
        
        return None
```

### **2.4 Self-Hosting Firecrawl**

```yaml
# docker-compose.firecrawl.yml
version: '3.8'

services:
  firecrawl-api:
    image: firecrawl/firecrawl:latest
    container_name: berb-firecrawl-api
    ports:
      - "3002:3002"
    environment:
      - PORT=3002
      - HOST=0.0.0.0
      - REDIS_URL=redis://redis:6379
      - PLAYWRIGHT_MICROSERVICE_URL=http://playwright:3000/scrape
      - USE_DB_AUTHENTICATION=false
      - BULL_AUTH_KEY=CHANGEME
    depends_on:
      - redis
      - playwright
    networks:
      - berb-network
    restart: unless-stopped
  
  firecrawl-worker:
    image: firecrawl/firecrawl:latest
    container_name: berb-firecrawl-worker
    environment:
      - REDIS_URL=redis://redis:6379
      - PLAYWRIGHT_MICROSERVICE_URL=http://playwright:3000/scrape
      - USE_DB_AUTHENTICATION=false
    depends_on:
      - redis
      - playwright
    networks:
      - berb-network
    restart: unless-stopped
    command: ["npm", "run", "worker"]
  
  playwright:
    image: firecrawl/playwright:latest
    container_name: berb-playwright
    ports:
      - "3000:3000"
    environment:
      - PORT=3000
    networks:
      - berb-network
    restart: unless-stopped
  
  redis:
    image: redis:alpine
    container_name: berb-redis-firecrawl
    ports:
      - "6379:6379"
    volumes:
      - redis-firecrawl-data:/data
    networks:
      - berb-network
    restart: unless-stopped

volumes:
  redis-firecrawl-data:

networks:
  berb-network:
    driver: bridge
```

---

## 📊 Integration Roadmap

### **Phase 1: SearXNG Integration (Week 1)**

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| Create `SearXNGClient` class | P0 | 2h | ⏳ |
| Add Docker Compose for SearXNG | P0 | 1h | ⏳ |
| Configure SearXNG engines | P0 | 1h | ⏳ |
| Integrate with `WebSearchClient` | P0 | 2h | ⏳ |
| Update config schema | P1 | 1h | ⏳ |
| Write tests | P1 | 2h | ⏳ |
| Documentation | P2 | 1h | ⏳ |

**Total:** ~10 hours

### **Phase 2: Firecrawl Integration (Week 2)**

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| Create `FirecrawlClient` class | P0 | 3h | ⏳ |
| Add `FullTextExtractor` | P0 | 2h | ⏳ |
| Add Docker Compose for Firecrawl | P1 | 2h | ⏳ |
| Integrate with literature search | P0 | 2h | ⏳ |
| Write tests | P1 | 2h | ⏳ |
| Documentation | P2 | 1h | ⏳ |

**Total:** ~12 hours

### **Phase 3: Pipeline Integration (Week 3)**

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| Stage 4 (LITERATURE_COLLECT): Use Firecrawl for full-text | P0 | 2h | ⏳ |
| Stage 6 (KNOWLEDGE_EXTRACT): Extract from crawled pages | P0 | 2h | ⏳ |
| Stage 23 (CITATION_VERIFY): Verify via crawled content | P1 | 1h | ⏳ |
| Add CLI commands (`/scrape`, `/crawl`, `/map`) | P2 | 3h | ⏳ |
| Benchmark performance | P1 | 2h | ⏳ |

**Total:** ~10 hours

---

## 💰 Cost Analysis

### **Current Setup (Tavily)**
```
Tavily Pro: $25/month
- 10,000 searches/month
- Advanced search depth
- Overages: $0.005/search

Estimated annual cost: $300
```

### **With SearXNG + Firecrawl (Self-Hosted)**
```
SearXNG: $0 (open-source, self-hosted)
- Unlimited searches
- 100+ engines

Firecrawl: $0 (open-source, self-hosted)
- Unlimited scraping
- JavaScript rendering

Server costs (for self-hosting):
- Small VPS: $5-10/month
- Or run locally: $0

Estimated annual cost: $60-120 (VPS) or $0 (local)
```

### **Savings**
- **Year 1:** $180-240 saved (60-80% reduction)
- **Year 2+:** $240/year saved (100% after initial setup)

---

## 📈 Expected Impact

| Metric | Current | With SearXNG | With Firecrawl | Combined |
|--------|---------|--------------|----------------|----------|
| **Search Coverage** | 3 engines | 100+ engines | Full web | ✅✅ |
| **Full-Text Access** | Limited | ❌ | ✅ (any site) | ✅✅ |
| **JavaScript Sites** | ❌ | ❌ | ✅ (rendering) | ✅✅ |
| **Structured Data** | ❌ | ❌ | ✅ (JSON schema) | ✅✅ |
| **Cost** | $25/month | $0 | $0 | $0 |
| **Privacy** | Mixed | ✅✅ | ✅ | ✅✅ |
| **Rate Limits** | 10K/month | Unlimited | Unlimited | Unlimited |

---

## 🔗 New Files to Create

```
berb/web/
├── searxng_client.py         # NEW: SearXNG integration (~200 lines)
├── scraper.py                # NEW: Firecrawl client (~350 lines)
└── search.py                 # ENHANCED: Add SearXNG support

berb/literature/
└── full_text.py              # NEW: Full-text extraction (~150 lines)

docker/
├── docker-compose.searxng.yml # NEW: SearXNG setup
└── docker-compose.firecrawl.yml # NEW: Firecrawl setup

searxng/
└── settings.yml              # NEW: SearXNG configuration

tests/
├── test_searxng_client.py    # NEW: SearXNG tests (~100 lines)
└── test_firecrawl_client.py  # NEW: Firecrawl tests (~150 lines)

docs/
└── SEARXNG_FIRECRAWL_INTEGRATION.md # NEW: Documentation
```

**Total New Code:** ~950 lines

---

## 🎯 Next Steps

1. **Week 1:** Implement SearXNG integration
2. **Week 2:** Implement Firecrawl integration
3. **Week 3:** Pipeline integration + testing
4. **Week 4:** Documentation + benchmarking

---

**Berb — Research, Refined.** 🧪✨
