"""Web search, crawling, and content extraction layer.

Provides unified access to:
- **Crawl4AI**: Web page → Markdown extraction
- **Tavily**: AI-native web search API
- **SearXNG**: Privacy-focused metasearch (100+ engines)
- **Firecrawl**: Advanced scraping/crawling/extraction
- **scholarly**: Google Scholar search
- **PDF extraction**: Full-text from PDF files

Public API
----------
- ``WebSearchAgent`` — orchestrates all web capabilities
- ``WebCrawler`` — Crawl4AI wrapper
- ``WebSearchClient`` — Tavily/SearXNG search wrapper
- ``SearXNGClient`` — SearXNG metasearch client
- ``FirecrawlClient`` — Firecrawl scraping/crawling client
- ``GoogleScholarClient`` — scholarly wrapper
- ``PDFExtractor`` — PDF text extraction
- ``check_url_ssrf`` — SSRF validation for URLs
"""

from berb.web._ssrf import check_url_ssrf
from berb.web.crawler import WebCrawler
from berb.web.search import WebSearchClient
from berb.web.searxng_client import SearXNGClient, SearXNGConfig
from berb.web.firecrawl_client import (
    FirecrawlClient,
    FirecrawlConfig,
    ScrapeFormat,
    ScrapeResult,
    CrawlResult,
    MapResult,
)
from berb.web.scholar import GoogleScholarClient
from berb.web.pdf_extractor import PDFExtractor
from berb.web.agent import WebSearchAgent

__all__ = [
    # Security
    "check_url_ssrf",
    
    # Crawling
    "WebCrawler",
    
    # Search
    "WebSearchClient",
    "SearXNGClient",
    "SearXNGConfig",
    "GoogleScholarClient",
    
    # Scraping/Crawling
    "FirecrawlClient",
    "FirecrawlConfig",
    "ScrapeFormat",
    "ScrapeResult",
    "CrawlResult",
    "MapResult",
    
    # PDF
    "PDFExtractor",
    
    # Agent
    "WebSearchAgent",
]
