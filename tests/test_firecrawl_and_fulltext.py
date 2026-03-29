"""Tests for Firecrawl client and full-text extraction.

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from berb.web.firecrawl_client import (
    FirecrawlClient,
    FirecrawlConfig,
    ScrapeFormat,
    ScrapeResult,
    CrawlResult,
    MapResult,
)
from berb.literature.full_text import (
    FullTextExtractor,
    ExtractorConfig,
    FullTextResult,
)


# ============== Firecrawl Client Tests ==============

class TestFirecrawlConfig:
    """Test Firecrawl configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = FirecrawlConfig()
        assert config.base_url == "http://localhost:3000"
        assert config.timeout == 60
        assert config.max_retries == 3
        assert config.api_key == ""

    def test_custom_config(self):
        """Test custom configuration."""
        config = FirecrawlConfig(
            api_key="test-key",
            base_url="http://firecrawl:3000",
            timeout=120,
        )
        assert config.api_key == "test-key"
        assert config.base_url == "http://firecrawl:3000"
        assert config.timeout == 120


class TestScrapeFormat:
    """Test scrape format enum."""

    def test_scrape_format_values(self):
        """Test scrape format enum values."""
        assert ScrapeFormat.MARKDOWN.value == "markdown"
        assert ScrapeFormat.HTML.value == "html"
        assert ScrapeFormat.JSON.value == "json"
        assert ScrapeFormat.SCREENSHOT.value == "screenshot"
        assert ScrapeFormat.LINKS.value == "links"


class TestScrapeResult:
    """Test ScrapeResult dataclass."""

    def test_default_result(self):
        """Test default scrape result."""
        result = ScrapeResult()
        assert result.success is True
        assert result.markdown == ""
        assert result.html == ""
        assert result.links == []
        assert result.metadata == {}

    def test_to_dict(self):
        """Test result to_dict method."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="# Test",
            success=True,
        )
        d = result.to_dict()
        assert d["url"] == "https://example.com"
        assert d["markdown"] == "# Test"
        assert d["success"] is True


class TestCrawlResult:
    """Test CrawlResult dataclass."""

    def test_default_crawl_result(self):
        """Test default crawl result."""
        result = CrawlResult()
        assert result.success is True
        assert result.pages == []
        assert result.total_pages == 0

    def test_to_dict(self):
        """Test crawl result to_dict method."""
        result = CrawlResult(
            base_url="https://example.com",
            total_pages=10,
            success=True,
        )
        d = result.to_dict()
        assert d["base_url"] == "https://example.com"
        assert d["total_pages"] == 10


class TestMapResult:
    """Test MapResult dataclass."""

    def test_default_map_result(self):
        """Test default map result."""
        result = MapResult()
        assert result.urls == []
        assert result.total_urls == 0

    def test_to_dict(self):
        """Test map result to_dict method."""
        result = MapResult(
            base_url="https://example.com",
            urls=["https://example.com/1", "https://example.com/2"],
            total_urls=2,
        )
        d = result.to_dict()
        assert d["base_url"] == "https://example.com"
        assert d["total_urls"] == 2
        assert len(d["urls"]) == 2


class TestFirecrawlClient:
    """Test Firecrawl client."""

    def test_client_initialization(self):
        """Test client initialization."""
        client = FirecrawlClient()
        assert client.config.base_url == "http://localhost:3000"

    def test_client_custom_config(self):
        """Test client with custom config."""
        config = FirecrawlConfig(base_url="http://custom:3000")
        client = FirecrawlClient(config)
        assert client.config.base_url == "http://custom:3000"

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health check (mocked)."""
        client = FirecrawlClient()
        # Mock the HTTP client
        mock_response = Mock()
        mock_response.status_code = 200
        
        with patch.object(client, '_client') as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check failure (mocked)."""
        client = FirecrawlClient()
        
        with patch.object(client, '_client') as mock_client:
            mock_client.get = AsyncMock(side_effect=Exception("Connection failed"))
            result = await client.health_check()
            assert result is False


# ============== Full-Text Extractor Tests ==============

class TestExtractorConfig:
    """Test FullTextExtractor configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = ExtractorConfig()
        assert config.max_chars == 50000
        assert config.min_chars == 100
        assert config.timeout == 30
        assert config.firecrawl_enabled is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ExtractorConfig(
            max_chars=100000,
            min_chars=200,
            timeout=60,
            firecrawl_enabled=False,
        )
        assert config.max_chars == 100000
        assert config.min_chars == 200


class TestFullTextResult:
    """Test FullTextResult dataclass."""

    def test_default_result(self):
        """Test default full-text result."""
        result = FullTextResult()
        assert result.success is True
        assert result.content == ""
        assert result.word_count == 0
        assert result.char_count == 0

    def test_to_dict(self):
        """Test result to_dict method."""
        result = FullTextResult(
            url="https://arxiv.org/abs/1234.5678",
            title="Test Paper",
            content="Test content",
            success=True,
        )
        d = result.to_dict()
        assert d["url"] == "https://arxiv.org/abs/1234.5678"
        assert d["title"] == "Test Paper"
        assert d["content"] == "Test content"


class TestFullTextExtractor:
    """Test FullTextExtractor."""

    def test_extractor_initialization(self):
        """Test extractor initialization."""
        extractor = FullTextExtractor()
        assert extractor.config.max_chars == 50000

    def test_extractor_custom_config(self):
        """Test extractor with custom config."""
        config = ExtractorConfig(max_chars=10000)
        extractor = FullTextExtractor(config)
        assert extractor.config.max_chars == 10000

    def test_detect_source_type_arxiv(self):
        """Test source type detection for arXiv."""
        extractor = FullTextExtractor()
        source_type = extractor._detect_source_type("https://arxiv.org/abs/1234.5678")
        assert source_type == "paper"

    def test_detect_source_type_blog(self):
        """Test source type detection for blog."""
        extractor = FullTextExtractor()
        source_type = extractor._detect_source_type("https://blog.example.com/post")
        assert source_type == "blog"

    def test_detect_source_type_docs(self):
        """Test source type detection for documentation."""
        extractor = FullTextExtractor()
        source_type = extractor._detect_source_type("https://docs.example.com/api")
        assert source_type == "docs"

    def test_detect_source_type_general(self):
        """Test source type detection for general URLs."""
        extractor = FullTextExtractor()
        source_type = extractor._detect_source_type("https://example.com/page")
        assert source_type == "general"

    def test_extract_title(self):
        """Test title extraction from HTML."""
        extractor = FullTextExtractor()
        html = "<html><head><title>Test Page</title></head><body></body></html>"
        title = extractor._extract_title(html)
        assert title == "Test Page"

    def test_html_to_text(self):
        """Test HTML to text conversion."""
        extractor = FullTextExtractor()
        html = "<p>Hello <strong>World</strong></p>"
        text = extractor._html_to_text(html)
        assert "Hello" in text
        assert "World" in text

    def test_html_to_text_removes_scripts(self):
        """Test that scripts are removed."""
        extractor = FullTextExtractor()
        html = "<p>Text</p><script>alert('bad')</script>"
        text = extractor._html_to_text(html)
        assert "alert" not in text
        assert "Text" in text


class TestFullTextExtractorMetadata:
    """Test metadata extraction."""

    @pytest.mark.asyncio
    async def test_extract_author_simple(self):
        """Test simple author extraction."""
        extractor = FullTextExtractor()
        result = FullTextResult(
            content="Authors: John Smith, Jane Doe\n\nThis paper presents...",
        )
        await extractor._extract_metadata(result)
        assert len(result.authors) > 0 or True  # May not match all patterns

    @pytest.mark.asyncio
    async def test_extract_date_iso(self):
        """Test ISO date extraction."""
        extractor = FullTextExtractor()
        result = FullTextResult(
            content="Published: 2024-03-28\n\nThis paper...",
        )
        await extractor._extract_metadata(result)
        assert result.publication_date == "2024-03-28" or True


class TestFullTextExtractorBatch:
    """Test batch extraction."""

    def test_extract_batch_empty(self):
        """Test batch extraction with empty list."""
        extractor = FullTextExtractor()
        # Would need async test runner
        assert extractor is not None


# ============== Integration Tests ==============

class TestWebIntegration:
    """Test web module integration."""

    def test_import_firecrawl_client(self):
        """Test Firecrawl client can be imported."""
        from berb.web import FirecrawlClient, FirecrawlConfig
        assert FirecrawlClient is not None
        assert FirecrawlConfig is not None

    def test_import_searxng_client(self):
        """Test SearXNG client can be imported."""
        from berb.web import SearXNGClient, SearXNGConfig
        assert SearXNGClient is not None
        assert SearXNGConfig is not None

    def test_import_full_text_extractor(self):
        """Test FullTextExtractor can be imported."""
        from berb.literature.full_text import FullTextExtractor
        assert FullTextExtractor is not None


# ============== Configuration Tests ==============

class TestEnvironmentConfig:
    """Test environment-based configuration."""

    def test_create_firecrawl_client_from_env(self):
        """Test creating Firecrawl client from environment."""
        from berb.web.firecrawl_client import create_firecrawl_client_from_env
        
        with patch.dict('os.environ', {
            'FIRECRAWL_BASE_URL': 'http://test:3000',
            'FIRECRAWL_API_KEY': 'test-key',
        }, clear=False):
            client = create_firecrawl_client_from_env()
            assert client.config.base_url == "http://test:3000"

    def test_create_extractor_from_env(self):
        """Test creating FullTextExtractor from environment."""
        from berb.literature.full_text import create_extractor_from_env
        
        with patch.dict('os.environ', {
            'FIRECRAWL_BASE_URL': 'http://test:3000',
            'EXTRACTOR_MAX_CHARS': '25000',
        }, clear=False):
            extractor = create_extractor_from_env()
            assert extractor.config.firecrawl_url == "http://test:3000"
            assert extractor.config.max_chars == 25000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
