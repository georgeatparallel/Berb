"""Academic paper search backed by the Semantic Scholar API.

Replaces the previous ``scholarly`` (Google Scholar scraping) implementation.
Semantic Scholar provides a stable, ToS-compliant REST API that returns the
same information (title, authors, year, abstract, citation count, venue).

The public interface (``GoogleScholarClient``, ``ScholarPaper``) is preserved
so existing call-sites require no changes.

API docs: https://api.semanticscholar.org/api-docs/graph
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_S2_BASE = "https://api.semanticscholar.org/graph/v1"
_S2_FIELDS = "title,authors,year,abstract,citationCount,externalIds,venue,url"
_DEFAULT_TIMEOUT = 15  # seconds


@dataclass
class ScholarPaper:
    """A paper result from Semantic Scholar (formerly Google Scholar)."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int = 0
    abstract: str = ""
    citation_count: int = 0
    url: str = ""
    scholar_id: str = ""
    venue: str = ""
    source: str = "semantic_scholar"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.abstract,
            "citation_count": self.citation_count,
            "url": self.url,
            "scholar_id": self.scholar_id,
            "venue": self.venue,
            "source": self.source,
        }

    def to_literature_paper(self) -> Any:
        """Convert to berb.literature.models.Paper."""
        from berb.literature.models import Author, Paper
        authors_tuple = tuple(Author(name=a) for a in self.authors)
        return Paper(
            paper_id=self.scholar_id or f"s2-{hashlib.sha256(self.title.encode()).hexdigest()[:8]}",
            title=self.title,
            authors=authors_tuple,
            year=self.year,
            abstract=self.abstract,
            venue=self.venue,
            citation_count=self.citation_count,
            url=self.url,
            source="semantic_scholar",
        )


class GoogleScholarClient:
    """Academic paper search client backed by the Semantic Scholar API.

    Keeps the same interface as the former ``scholarly``-based client so
    existing call-sites do not require changes.

    Parameters
    ----------
    inter_request_delay:
        Seconds between requests (Semantic Scholar public tier: 1 req/s
        unauthenticated; pass an ``api_key`` for 10 req/s).
    api_key:
        Optional Semantic Scholar API key for higher rate limits.
    """

    def __init__(
        self,
        *,
        inter_request_delay: float = 1.1,
        use_proxy: bool = False,  # kept for API compat; ignored
        api_key: str | None = None,
    ) -> None:
        self.delay = inter_request_delay
        self._api_key = api_key
        self._last_request_time: float = 0.0
        if use_proxy:
            logger.debug("use_proxy is ignored — Semantic Scholar API needs no proxy")

    @property
    def available(self) -> bool:
        """Always True — uses stdlib urllib, no optional dependency."""
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, *, limit: int = 10) -> list[ScholarPaper]:
        """Search Semantic Scholar for papers matching *query*."""
        params = urllib.parse.urlencode({
            "query": query,
            "limit": min(limit, 100),
            "fields": _S2_FIELDS,
        })
        url = f"{_S2_BASE}/paper/search?{params}"
        data = self._get(url)
        papers: list[ScholarPaper] = []
        for item in (data.get("data") or [])[:limit]:
            papers.append(self._parse_item(item))
        logger.info("Semantic Scholar: found %d papers for %r", len(papers), query)
        return papers

    def get_citations(self, scholar_id: str, *, limit: int = 20) -> list[ScholarPaper]:
        """Return papers that cite *scholar_id* (citation graph traversal)."""
        params = urllib.parse.urlencode({
            "limit": min(limit, 100),
            "fields": _S2_FIELDS,
        })
        url = f"{_S2_BASE}/paper/{urllib.parse.quote(scholar_id)}/citations?{params}"
        data = self._get(url)
        papers: list[ScholarPaper] = []
        for item in (data.get("data") or [])[:limit]:
            citing = item.get("citingPaper") or item
            papers.append(self._parse_item(citing))
        logger.info("Semantic Scholar: found %d citations for %s", len(papers), scholar_id)
        return papers

    def search_author(self, name: str) -> list[dict[str, Any]]:
        """Search for an author on Semantic Scholar."""
        params = urllib.parse.urlencode({
            "query": name,
            "limit": 5,
            "fields": "name,affiliations,citationCount,paperCount,hIndex",
        })
        url = f"{_S2_BASE}/author/search?{params}"
        data = self._get(url)
        results = []
        for item in (data.get("data") or [])[:5]:
            affiliations = item.get("affiliations") or []
            results.append({
                "name": item.get("name", ""),
                "affiliation": affiliations[0] if affiliations else "",
                "scholar_id": str(item.get("authorId", "")),
                "citedby": item.get("citationCount", 0),
                "interests": [],
            })
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get(self, url: str) -> dict[str, Any]:
        """Perform a rate-limited GET and return parsed JSON."""
        self._rate_limit()
        req = urllib.request.Request(url)
        if self._api_key:
            req.add_header("x-api-key", self._api_key)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Semantic Scholar request failed (%s): %s", url, exc)
            return {}

    def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.monotonic()

    @staticmethod
    def _parse_item(item: dict[str, Any]) -> ScholarPaper:
        """Parse a Semantic Scholar paper object into ScholarPaper."""
        authors = [a.get("name", "") for a in (item.get("authors") or [])]
        ext_ids = item.get("externalIds") or {}
        scholar_id = str(item.get("paperId") or "")
        url = (
            item.get("url")
            or (f"https://doi.org/{ext_ids['DOI']}" if "DOI" in ext_ids else "")
        )
        return ScholarPaper(
            title=item.get("title") or "",
            authors=authors,
            year=int(item.get("year") or 0),
            abstract=item.get("abstract") or "",
            citation_count=int(item.get("citationCount") or 0),
            url=url,
            scholar_id=scholar_id,
            venue=item.get("venue") or "",
            source="semantic_scholar",
        )
