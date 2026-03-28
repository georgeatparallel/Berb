"""Tests for SearXNG web search client."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from berb.web.searxng_client import (
    SearXNGClient,
    SearXNGConfig,
    create_searxng_client_from_env,
    _parse_csv_env,
)


class TestSearXNGConfig:
    """Test SearXNGConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = SearXNGConfig()
        
        assert config.base_url == "http://localhost:8080"
        assert config.engines is None
        assert config.categories is None
        assert config.language == "en"
        assert config.safe_search == 0
        assert config.timeout == 30
        assert config.max_results == 20
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = SearXNGConfig(
            base_url="http://searxng:8080",
            engines=["arxiv", "pubmed"],
            categories=["science"],
            language="fr",
            safe_search=2,
            timeout=60,
            max_results=50,
        )
        
        assert config.base_url == "http://searxng:8080"
        assert config.engines == ["arxiv", "pubmed"]
        assert config.categories == ["science"]
        assert config.language == "fr"
        assert config.safe_search == 2
        assert config.timeout == 60
        assert config.max_results == 50


class TestSearXNGClient:
    """Test SearXNGClient class."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        with patch("berb.web.searxng_client.httpx.AsyncClient") as mock:
            yield mock
    
    def test_init_default(self, mock_http_client):
        """Test initialization with default config."""
        client = SearXNGClient()
        
        assert client.config.base_url == "http://localhost:8080"
        assert client.config.language == "en"
        mock_http_client.assert_called_once()
    
    def test_init_custom_config(self, mock_http_client):
        """Test initialization with custom config."""
        config = SearXNGConfig(base_url="http://custom:8080")
        client = SearXNGClient(config)
        
        assert client.config.base_url == "http://custom:8080"
    
    @pytest.mark.asyncio
    async def test_search_basic(self, mock_http_client):
        """Test basic search functionality."""
        # Mock response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "content": "Test content",
                    "score": 0.9,
                    "engine": "google",
                }
            ],
            "search_time": 0.5,
            "answer": "",
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_http_client.return_value = mock_client_instance
        
        client = SearXNGClient()
        result = await client.search("test query")
        
        assert result.query == "test query"
        assert len(result.results) == 1
        assert result.results[0].title == "Test Result"
        assert result.results[0].url == "https://example.com"
        assert result.source == "searxng"
    
    @pytest.mark.asyncio
    async def test_search_with_engines(self, mock_http_client):
        """Test search with specific engines."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [],
            "search_time": 0.3,
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_http_client.return_value = mock_client_instance
        
        client = SearXNGClient()
        await client.search(
            "CRISPR",
            engines=["arxiv", "pubmed"],
            categories=["science"],
        )
        
        # Verify engines and categories were passed
        call_args = mock_client_instance.get.call_args
        params = call_args[1]["params"]
        assert "arxiv" in params["engines"]
        assert "pubmed" in params["engines"]
        assert "science" in params["categories"]
    
    @pytest.mark.asyncio
    async def test_search_multi(self, mock_http_client):
        """Test multiple queries."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [{"title": "Result", "url": "https://example.com", "content": ""}],
            "search_time": 0.3,
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_http_client.return_value = mock_client_instance
        
        client = SearXNGClient()
        results = await client.search_multi(
            ["query1", "query2", "query3"],
            inter_query_delay=0.1,
        )
        
        assert len(results) == 3
        assert mock_client_instance.get.call_count == 3
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_http_client):
        """Test health check when server is up."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_http_client.return_value = mock_client_instance
        
        client = SearXNGClient()
        result = await client.health_check()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_http_client):
        """Test health check when server is down."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_http_client.return_value = mock_client_instance
        
        client = SearXNGClient()
        result = await client.health_check()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_engines(self, mock_http_client):
        """Test getting available engines."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"name": "arxiv", "categories": ["science"], "language": "all"},
            {"name": "google", "categories": ["general"], "language": "all"},
        ]
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_http_client.return_value = mock_client_instance
        
        client = SearXNGClient()
        engines = await client.get_engines()
        
        assert len(engines) == 2
        assert engines[0]["name"] == "arxiv"
    
    @pytest.mark.asyncio
    async def test_get_categories(self, mock_http_client):
        """Test getting available categories."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"name": "arxiv", "categories": ["science", "it"]},
            {"name": "google", "categories": ["general", "news"]},
        ]
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_http_client.return_value = mock_client_instance
        
        client = SearXNGClient()
        categories = await client.get_categories()
        
        assert "science" in categories
        assert "general" in categories
        assert "it" in categories
        assert "news" in categories
    
    @pytest.mark.asyncio
    async def test_context_manager(self, mock_http_client):
        """Test async context manager."""
        mock_client_instance = AsyncMock()
        mock_http_client.return_value = mock_client_instance
        
        async with SearXNGClient() as client:
            assert client is not None
        
        mock_client_instance.aclose.assert_called_once()


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_parse_csv_env_empty(self, monkeypatch):
        """Test parsing empty environment variable."""
        monkeypatch.setenv("TEST_VAR", "")
        result = _parse_csv_env("TEST_VAR")
        assert result is None
    
    def test_parse_csv_env_single(self, monkeypatch):
        """Test parsing single value."""
        monkeypatch.setenv("TEST_VAR", "value1")
        result = _parse_csv_env("TEST_VAR")
        assert result == ["value1"]
    
    def test_parse_csv_env_multiple(self, monkeypatch):
        """Test parsing multiple values."""
        monkeypatch.setenv("TEST_VAR", "value1, value2, value3")
        result = _parse_csv_env("TEST_VAR")
        assert result == ["value1", "value2", "value3"]
    
    def test_parse_csv_env_with_whitespace(self, monkeypatch):
        """Test parsing with extra whitespace."""
        monkeypatch.setenv("TEST_VAR", "  value1  ,  value2  ,  ")
        result = _parse_csv_env("TEST_VAR")
        assert result == ["value1", "value2"]
    
    def test_create_searxng_client_from_env(self, monkeypatch, mock_http_client):
        """Test creating client from environment variables."""
        monkeypatch.setenv("SEARXNG_BASE_URL", "http://env-searxng:8080")
        monkeypatch.setenv("SEARXNG_ENGINES", "arxiv,pubmed")
        monkeypatch.setenv("SEARXNG_CATEGORIES", "science")
        monkeypatch.setenv("SEARXNG_LANGUAGE", "fr")
        monkeypatch.setenv("SEARXNG_SAFE_SEARCH", "2")
        monkeypatch.setenv("SEARXNG_TIMEOUT", "60")
        
        client = create_searxng_client_from_env()
        
        assert client.config.base_url == "http://env-searxng:8080"
        assert client.config.engines == ["arxiv", "pubmed"]
        assert client.config.categories == ["science"]
        assert client.config.language == "fr"
        assert client.config.safe_search == 2
        assert client.config.timeout == 60
