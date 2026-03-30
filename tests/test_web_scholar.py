"""Tests for berb.web.scholar — GoogleScholarClient (Semantic Scholar backend)."""

from __future__ import annotations

import json
import time
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from berb.web.scholar import GoogleScholarClient, ScholarPaper


# ---------------------------------------------------------------------------
# ScholarPaper dataclass
# ---------------------------------------------------------------------------


class TestScholarPaper:
    def test_to_dict(self):
        p = ScholarPaper(
            title="Attention Is All You Need",
            authors=["Vaswani", "Shazeer"],
            year=2017,
            citation_count=50000,
        )
        d = p.to_dict()
        assert d["title"] == "Attention Is All You Need"
        assert d["year"] == 2017
        assert d["source"] == "semantic_scholar"

    def test_to_literature_paper(self):
        p = ScholarPaper(
            title="Test Paper",
            authors=["Author One", "Author Two"],
            year=2024,
            abstract="An abstract.",
            citation_count=100,
            url="https://example.com",
        )
        lit = p.to_literature_paper()
        assert lit.title == "Test Paper"
        assert lit.source == "semantic_scholar"
        assert len(lit.authors) == 2
        assert lit.authors[0].name == "Author One"


# ---------------------------------------------------------------------------
# GoogleScholarClient
# ---------------------------------------------------------------------------


class TestGoogleScholarClient:
    def test_available_always_true(self):
        """Client is always available — uses stdlib urllib."""
        client = GoogleScholarClient()
        assert client.available

    def test_parse_item_full(self):
        """Test _parse_item with a complete Semantic Scholar response dict."""
        item = {
            "paperId": "abc123",
            "title": "Deep Learning",
            "authors": [{"name": "LeCun"}, {"name": "Bengio"}, {"name": "Hinton"}],
            "year": 2015,
            "abstract": "Deep learning review.",
            "citationCount": 30000,
            "venue": "Nature",
            "url": "https://nature.com/dl",
            "externalIds": {},
        }
        paper = GoogleScholarClient._parse_item(item)
        assert paper.title == "Deep Learning"
        assert paper.year == 2015
        assert paper.citation_count == 30000
        assert "LeCun" in paper.authors
        assert paper.venue == "Nature"
        assert paper.scholar_id == "abc123"

    def test_parse_item_missing_fields(self):
        item = {}
        paper = GoogleScholarClient._parse_item(item)
        assert paper.title == ""
        assert paper.year == 0
        assert paper.authors == []

    def test_rate_limiting(self):
        client = GoogleScholarClient(inter_request_delay=0.01)
        t0 = time.monotonic()
        client._rate_limit()
        client._rate_limit()
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.01

    def test_search_with_mocked_api(self):
        """Test search using a mocked HTTP response."""
        response_data = {
            "data": [
                {
                    "paperId": "p1",
                    "title": "Test Paper",
                    "authors": [{"name": "Author A"}],
                    "year": 2024,
                    "abstract": "",
                    "citationCount": 5,
                    "venue": "",
                    "url": "https://example.com",
                    "externalIds": {},
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = GoogleScholarClient(inter_request_delay=0.0)
            results = client.search("test query", limit=5)

        assert len(results) == 1
        assert results[0].title == "Test Paper"

    def test_search_error_graceful(self):
        """Search should return empty list on error, not raise."""
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            client = GoogleScholarClient(inter_request_delay=0.0)
            results = client.search("test query")
        assert results == []
