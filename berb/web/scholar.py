"""Google Scholar search powered by the ``scholarly`` library.

scholarly is installed as a dependency and provides direct access to
Google Scholar search, citation graph traversal, and author lookup.

Hardening additions (2026-03-29):
- Proxy rotation pool (free-proxy-list, ScraperAPI, Bright Data)
- Exponential backoff on CAPTCHA / 429 / network errors
- Health-check auto-disable: 3 consecutive failures → disabled + warning

Usage::

    client = GoogleScholarClient()
    papers = client.search("attention is all you need", limit=5)
    citing = client.get_citations(papers[0].scholar_id, limit=10)

    # With ScraperAPI proxy
    client = GoogleScholarClient(proxy_api_key="YOUR_SCRAPERAPI_KEY")
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from scholarly import scholarly, ProxyGenerator
    HAS_SCHOLARLY = True
except ImportError:
    scholarly = None  # type: ignore[assignment]
    ProxyGenerator = None  # type: ignore[assignment,misc]
    HAS_SCHOLARLY = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_CONSECUTIVE_FAILURES = 3
_BACKOFF_BASE = 2.0          # seconds — doubles each retry
_BACKOFF_MAX = 64.0          # cap at ~1 minute
_BACKOFF_JITTER = 0.5        # ± 50% random jitter


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScholarPaper:
    """A paper result from Google Scholar."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int = 0
    abstract: str = ""
    citation_count: int = 0
    url: str = ""
    scholar_id: str = ""
    venue: str = ""
    source: str = "google_scholar"

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
            paper_id=self.scholar_id or f"gs-{hashlib.sha256(self.title.encode()).hexdigest()[:8]}",
            title=self.title,
            authors=authors_tuple,
            year=self.year,
            abstract=self.abstract,
            venue=self.venue,
            citation_count=self.citation_count,
            url=self.url,
            source="google_scholar",
        )


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class GoogleScholarClient:
    """Google Scholar search client using the ``scholarly`` library.

    Hardened with proxy rotation, exponential backoff, and automatic
    health-check disabling after repeated failures.

    Parameters
    ----------
    inter_request_delay:
        Base seconds between requests (jitter applied on top).
    use_proxy:
        Use free rotating proxies via ``scholarly``'s built-in FreeProxies.
    proxy_api_key:
        ScraperAPI key.  If set, a ScraperAPI proxy URL is used, which is
        far more reliable than free proxies.
    bright_data_url:
        Bright Data (Luminati) proxy URL (e.g. ``"http://user:pass@zproxy.lum-superproxy.io:22225"``).
    max_retries:
        Number of retry attempts per request before giving up.
    """

    def __init__(
        self,
        *,
        inter_request_delay: float = 2.0,
        use_proxy: bool = False,
        proxy_api_key: str = "",
        bright_data_url: str = "",
        max_retries: int = 3,
    ) -> None:
        if not HAS_SCHOLARLY:
            raise ImportError(
                "scholarly is required for Google Scholar search. "
                "Install: pip install 'berb[web]'"
            )
        self.delay = inter_request_delay
        self.max_retries = max_retries
        self._last_request_time: float = 0.0
        self._consecutive_failures: int = 0
        self._disabled: bool = False

        self._setup_proxy(
            use_proxy=use_proxy,
            proxy_api_key=proxy_api_key,
            bright_data_url=bright_data_url,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """False when auto-disabled after repeated failures."""
        return not self._disabled

    def search(self, query: str, *, limit: int = 10) -> list[ScholarPaper]:
        """Search Google Scholar for papers matching *query*."""
        if self._disabled:
            logger.warning("GoogleScholarClient is disabled (too many failures). Returning [].")
            return []

        def _op() -> list[ScholarPaper]:
            self._rate_limit()
            results: list[ScholarPaper] = []
            search_gen = scholarly.search_pubs(query)
            for i, pub in enumerate(search_gen):
                if i >= limit:
                    break
                results.append(self._parse_pub(pub))
                if i < limit - 1:
                    self._rate_limit()
            return results

        results = self._with_retry(_op, context=f"search({query!r})")
        if results is None:
            return []
        logger.info("Google Scholar: found %d papers for %r", len(results), query)
        return results

    def get_citations(self, scholar_id: str, *, limit: int = 20) -> list[ScholarPaper]:
        """Fetch papers that cite the given paper (citation graph traversal)."""
        if self._disabled:
            logger.warning("GoogleScholarClient is disabled. Returning [].")
            return []

        def _op() -> list[ScholarPaper]:
            self._rate_limit()
            results: list[ScholarPaper] = []
            pub = scholarly.search_single_pub(scholar_id)
            if pub:
                for i, cit in enumerate(scholarly.citedby(pub)):
                    if i >= limit:
                        break
                    results.append(self._parse_pub(cit))
                    if i < limit - 1:
                        self._rate_limit()
            return results

        results = self._with_retry(_op, context=f"get_citations({scholar_id!r})")
        if results is None:
            return []
        logger.info("Google Scholar: found %d citations for %s", len(results), scholar_id)
        return results

    def search_author(self, name: str) -> list[dict[str, Any]]:
        """Search for an author on Google Scholar."""
        if self._disabled:
            return []

        def _op() -> list[dict[str, Any]]:
            self._rate_limit()
            results = []
            for author in scholarly.search_author(name):
                results.append({
                    "name": author.get("name", ""),
                    "affiliation": author.get("affiliation", ""),
                    "scholar_id": author.get("scholar_id", ""),
                    "citedby": author.get("citedby", 0),
                    "interests": author.get("interests", []),
                })
                if len(results) >= 5:
                    break
            return results

        result = self._with_retry(_op, context=f"search_author({name!r})")
        return result if result is not None else []

    def reset(self) -> None:
        """Re-enable the client after it was auto-disabled."""
        self._disabled = False
        self._consecutive_failures = 0
        logger.info("GoogleScholarClient re-enabled.")

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def _with_retry(self, op: Any, *, context: str = "") -> Any | None:
        """Execute *op()* with exponential backoff.  Returns None on permanent failure."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = op()
                self._consecutive_failures = 0  # reset on success
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self._consecutive_failures += 1
                msg = str(exc).lower()
                is_block = any(k in msg for k in ("captcha", "429", "too many", "blocked", "rate limit"))

                if attempt < self.max_retries:
                    wait = self._backoff(attempt, long=is_block)
                    logger.warning(
                        "Scholar %s failed (attempt %d/%d, %s): %s — retrying in %.1fs",
                        context, attempt + 1, self.max_retries, "BLOCK" if is_block else "error", exc, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Scholar %s failed permanently after %d attempts: %s",
                        context, self.max_retries + 1, exc,
                    )

        self._check_health()
        return None

    def _backoff(self, attempt: int, *, long: bool = False) -> float:
        """Return wait time with exponential backoff and jitter."""
        base = _BACKOFF_BASE * (4 if long else 1)  # longer wait on blocks
        raw = min(base * (2 ** attempt), _BACKOFF_MAX)
        jitter = raw * _BACKOFF_JITTER * (2 * random.random() - 1)
        return max(1.0, raw + jitter)

    def _check_health(self) -> None:
        """Auto-disable after too many consecutive failures."""
        if self._consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            self._disabled = True
            logger.warning(
                "GoogleScholarClient auto-disabled after %d consecutive failures. "
                "Call .reset() to re-enable, or use SearXNG/Semantic Scholar instead.",
                self._consecutive_failures,
            )

    # ------------------------------------------------------------------
    # Proxy setup
    # ------------------------------------------------------------------

    def _setup_proxy(
        self,
        *,
        use_proxy: bool,
        proxy_api_key: str,
        bright_data_url: str,
    ) -> None:
        """Configure scholarly proxy (priority: ScraperAPI > Bright Data > FreeProxies)."""
        if not ProxyGenerator:
            return

        if proxy_api_key:
            try:
                pg = ProxyGenerator()
                pg.ScraperAPI(proxy_api_key)
                scholarly.use_proxy(pg)
                logger.info("Google Scholar: ScraperAPI proxy enabled")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("ScraperAPI proxy setup failed: %s", exc)

        if bright_data_url:
            try:
                pg = ProxyGenerator()
                pg.SingleProxy(http=bright_data_url, https=bright_data_url)
                scholarly.use_proxy(pg)
                logger.info("Google Scholar: Bright Data proxy enabled")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Bright Data proxy setup failed: %s", exc)

        if use_proxy:
            try:
                pg = ProxyGenerator()
                pg.FreeProxies()
                scholarly.use_proxy(pg)
                logger.info("Google Scholar: free proxy pool enabled (unreliable)")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Free proxy setup failed: %s", exc)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.monotonic()

    @staticmethod
    def _parse_pub(pub: Any) -> ScholarPaper:
        """Parse a scholarly publication object into ScholarPaper."""
        bib = pub.get("bib", {}) if isinstance(pub, dict) else getattr(pub, "bib", {})
        info = pub if isinstance(pub, dict) else pub.__dict__ if hasattr(pub, "__dict__") else {}

        authors = bib.get("author", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(" and ")]

        year = 0
        year_raw = bib.get("pub_year", bib.get("year", 0))
        try:
            year = int(year_raw)
        except (ValueError, TypeError):
            pass

        cites_id = info.get("cites_id", [])
        scholar_id = info.get("author_pub_id", "") or (
            cites_id[0] if isinstance(cites_id, list) and cites_id else ""
        )

        return ScholarPaper(
            title=bib.get("title", ""),
            authors=authors,
            year=year,
            abstract=bib.get("abstract", ""),
            citation_count=info.get("num_citations", 0),
            url=info.get("pub_url", info.get("eprint_url", "")),
            scholar_id=scholar_id,
            venue=bib.get("venue", bib.get("journal", "")),
        )
