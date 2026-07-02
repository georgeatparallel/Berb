"""Tests for berb.web.scholar — GoogleScholarClient."""

from __future__ import annotations

import time
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
        assert d["source"] == "google_scholar"

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
        assert lit.source == "google_scholar"
        assert len(lit.authors) == 2
        assert lit.authors[0].name == "Author One"


# ---------------------------------------------------------------------------
# GoogleScholarClient
# ---------------------------------------------------------------------------


class TestGoogleScholarClient:
    @patch("berb.web.scholar.HAS_SCHOLARLY", True)
    def test_available_always_true(self):
        """scholarly is now an installed dependency, always available."""
        client = GoogleScholarClient()
        assert client.available

    def test_parse_pub_full(self):
        """Test _parse_pub with a complete publication dict."""
        pub = {
            "bib": {
                "title": "Deep Learning",
                "author": ["LeCun", "Bengio", "Hinton"],
                "pub_year": "2015",
                "abstract": "Deep learning review.",
                "venue": "Nature",
            },
            "num_citations": 30000,
            "pub_url": "https://nature.com/dl",
            "cites_id": ["abc123"],
        }
        paper = GoogleScholarClient._parse_pub(pub)
        assert paper.title == "Deep Learning"
        assert paper.year == 2015
        assert paper.citation_count == 30000
        assert "LeCun" in paper.authors
        assert paper.venue == "Nature"

    def test_parse_pub_string_authors(self):
        pub = {
            "bib": {
                "title": "Paper",
                "author": "Smith and Jones",
                "pub_year": "2023",
            },
            "num_citations": 10,
            "pub_url": "https://example.com",
        }
        paper = GoogleScholarClient._parse_pub(pub)
        assert paper.title == "Paper"
        assert "Smith" in paper.authors
        assert "Jones" in paper.authors

    def test_parse_pub_missing_fields(self):
        pub = {"bib": {}, "num_citations": 0}
        paper = GoogleScholarClient._parse_pub(pub)
        assert paper.title == ""
        assert paper.year == 0
        assert paper.authors == []

    @patch("berb.web.scholar.HAS_SCHOLARLY", True)
    def test_rate_limiting(self):
        client = GoogleScholarClient(inter_request_delay=0.01)
        t0 = time.monotonic()
        client._rate_limit()
        client._rate_limit()
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.01

    @patch("berb.web.scholar.HAS_SCHOLARLY", True)
    @patch("berb.web.scholar.scholarly")
    def test_search_with_mocked_scholarly(self, mock_scholarly):
        """Test search using mocked scholarly library."""
        mock_pub = {
            "bib": {
                "title": "Test Paper",
                "author": ["Author A"],
                "pub_year": "2024",
            },
            "num_citations": 5,
            "pub_url": "https://example.com",
        }
        mock_scholarly.search_pubs.return_value = iter([mock_pub])

        client = GoogleScholarClient(inter_request_delay=0.0)
        results = client.search("test query", limit=5)
        assert len(results) == 1
        assert results[0].title == "Test Paper"

    @patch("berb.web.scholar.time.sleep", return_value=None)
    @patch("berb.web.scholar.HAS_SCHOLARLY", True)
    @patch("berb.web.scholar.scholarly")
    def test_search_error_graceful(self, mock_scholarly, _mock_sleep):
        """Search should return empty list on error, not raise.

        The injected error message ("Rate limited") is classified by
        GoogleScholarClient._with_retry as a block-type failure (matches the
        "rate limit" keyword), which quadruples the exponential backoff base
        (up to a 64s cap) across 3 retries — several real seconds of
        time.sleep() per run. That's genuine retry/backoff logic being
        exercised correctly, not a bug, so we mock time.sleep itself to keep
        this test fast and deterministic rather than weakening the retry
        classification or reducing max_retries.
        """
        mock_scholarly.search_pubs.side_effect = Exception("Rate limited")

        client = GoogleScholarClient(inter_request_delay=0.0)
        results = client.search("test query")
        assert results == []
