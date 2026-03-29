"""Citation graph construction and traversal.

Uses Semantic Scholar as the primary source (reliable API, 200M+ papers)
with Google Scholar as a supplementary fallback.

Public API
----------
- ``CitationGraph`` — build and traverse citation networks
- ``get_citation_graph(paper_ids, depth, client)`` — convenience factory
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CitationNode:
    """A single node in the citation graph."""

    paper_id: str
    title: str
    year: int = 0
    citation_count: int = 0
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    url: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "year": self.year,
            "citation_count": self.citation_count,
            "authors": self.authors,
            "venue": self.venue,
            "url": self.url,
            "source": self.source,
        }


@dataclass
class CitationEdge:
    """Directed citation edge: *citing* → *cited*."""

    citing_id: str
    cited_id: str


@dataclass
class CitationGraphResult:
    """Full citation graph for a seed set of papers."""

    seed_ids: list[str]
    nodes: dict[str, CitationNode] = field(default_factory=dict)
    edges: list[CitationEdge] = field(default_factory=list)

    # Influence metrics
    pagerank: dict[str, float] = field(default_factory=dict)

    def most_influential(self, top_n: int = 10) -> list[CitationNode]:
        """Return top-N nodes by PageRank score (or citation_count if no PR)."""
        if self.pagerank:
            ranked = sorted(self.nodes.values(), key=lambda n: self.pagerank.get(n.paper_id, 0), reverse=True)
        else:
            ranked = sorted(self.nodes.values(), key=lambda n: n.citation_count, reverse=True)
        return ranked[:top_n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_ids": self.seed_ids,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [{"citing": e.citing_id, "cited": e.cited_id} for e in self.edges],
            "pagerank": self.pagerank,
        }


# ---------------------------------------------------------------------------
# Citation graph builder
# ---------------------------------------------------------------------------

class CitationGraph:
    """Build citation graphs using Semantic Scholar as primary source.

    Parameters
    ----------
    s2_client:
        Semantic Scholar client (``berb.literature.semantic_scholar``).
        If None, a fresh instance is created.
    scholar_client:
        Optional ``GoogleScholarClient`` used as fallback when S2 returns
        no citations for a paper.
    max_citations_per_paper:
        Cap on outbound citations fetched per paper (keeps graph tractable).
    compute_pagerank:
        Whether to run PageRank on the resulting graph.
    """

    def __init__(
        self,
        *,
        s2_client: Any | None = None,
        scholar_client: Any | None = None,
        max_citations_per_paper: int = 50,
        compute_pagerank: bool = True,
    ) -> None:
        self._s2 = s2_client
        self._scholar = scholar_client
        self._max_cites = max_citations_per_paper
        self._compute_pagerank = compute_pagerank

    def build(
        self,
        seed_paper_ids: list[str],
        *,
        depth: int = 1,
    ) -> CitationGraphResult:
        """Build a citation graph starting from *seed_paper_ids*.

        Parameters
        ----------
        seed_paper_ids:
            Semantic Scholar paper IDs, arXiv IDs, or DOIs.
        depth:
            How many hops to traverse (1 = direct citations only).

        Returns
        -------
        CitationGraphResult
        """
        result = CitationGraphResult(seed_ids=list(seed_paper_ids))
        frontier: set[str] = set(seed_paper_ids)

        for hop in range(depth):
            next_frontier: set[str] = set()
            logger.info("Citation graph hop %d/%d — %d papers in frontier", hop + 1, depth, len(frontier))

            for paper_id in frontier:
                if paper_id in result.nodes:
                    continue
                citations = self._fetch_citations(paper_id)
                if not citations:
                    continue

                for node in citations:
                    if node.paper_id not in result.nodes:
                        result.nodes[node.paper_id] = node
                    result.edges.append(CitationEdge(citing_id=paper_id, cited_id=node.paper_id))
                    if hop < depth - 1:
                        next_frontier.add(node.paper_id)

            frontier = next_frontier - set(result.nodes.keys())

        logger.info(
            "Citation graph built: %d nodes, %d edges",
            len(result.nodes), len(result.edges),
        )

        if self._compute_pagerank and result.edges:
            result.pagerank = self._pagerank(result)

        return result

    # ------------------------------------------------------------------
    # Citation fetching — S2 primary, Scholar fallback
    # ------------------------------------------------------------------

    def _fetch_citations(self, paper_id: str) -> list[CitationNode]:
        """Fetch papers that cite *paper_id* from S2 (with Scholar fallback)."""
        nodes = self._fetch_from_s2(paper_id)
        if nodes:
            return nodes

        if self._scholar and self._scholar.available:
            logger.debug("S2 returned no citations for %s — trying Scholar", paper_id)
            nodes = self._fetch_from_scholar(paper_id)

        return nodes

    def _fetch_from_s2(self, paper_id: str) -> list[CitationNode]:
        """Fetch citations via Semantic Scholar API."""
        try:
            s2 = self._get_s2()
            raw = s2.get_citations(paper_id, limit=self._max_cites)
            nodes: list[CitationNode] = []
            for item in raw:
                pid = item.get("paperId") or item.get("paper_id", "")
                if not pid:
                    continue
                bib_data = item.get("citingPaper") or item
                nodes.append(CitationNode(
                    paper_id=pid,
                    title=bib_data.get("title", ""),
                    year=int(bib_data.get("year") or 0),
                    citation_count=int(bib_data.get("citationCount") or 0),
                    authors=[
                        a.get("name", "") for a in (bib_data.get("authors") or [])
                        if isinstance(a, dict)
                    ],
                    venue=bib_data.get("venue", ""),
                    url=bib_data.get("url", "") or f"https://www.semanticscholar.org/paper/{pid}",
                    source="semantic_scholar",
                ))
            return nodes
        except Exception as exc:  # noqa: BLE001
            logger.warning("S2 citation fetch failed for %s: %s", paper_id, exc)
            return []

    def _fetch_from_scholar(self, scholar_id: str) -> list[CitationNode]:
        """Fetch citations via Google Scholar (fallback)."""
        try:
            papers = self._scholar.get_citations(scholar_id, limit=self._max_cites)
            return [
                CitationNode(
                    paper_id=p.scholar_id or f"gs-{i}",
                    title=p.title,
                    year=p.year,
                    citation_count=p.citation_count,
                    authors=p.authors,
                    venue=p.venue,
                    url=p.url,
                    source="google_scholar",
                )
                for i, p in enumerate(papers)
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scholar citation fetch failed for %s: %s", scholar_id, exc)
            return []

    # ------------------------------------------------------------------
    # PageRank (pure Python, no external deps)
    # ------------------------------------------------------------------

    @staticmethod
    def _pagerank(
        result: CitationGraphResult,
        *,
        damping: float = 0.85,
        iterations: int = 50,
        tol: float = 1e-6,
    ) -> dict[str, float]:
        """Compute PageRank scores for the citation graph nodes.

        Citation direction: A cites B → link A→B (B gets authority from A).
        """
        nodes = list(result.nodes.keys())
        n = len(nodes)
        if n == 0:
            return {}

        idx = {nid: i for i, nid in enumerate(nodes)}

        # Build adjacency: out_links[i] = list of j that i cites
        out_links: list[list[int]] = [[] for _ in range(n)]
        for edge in result.edges:
            if edge.citing_id in idx and edge.cited_id in idx:
                out_links[idx[edge.citing_id]].append(idx[edge.cited_id])

        scores = [1.0 / n] * n
        for _ in range(iterations):
            new_scores = [(1.0 - damping) / n] * n
            for i, links in enumerate(out_links):
                if not links:
                    # Dangling node: distribute to all
                    share = scores[i] / n
                    for j in range(n):
                        new_scores[j] += damping * share
                else:
                    share = scores[i] / len(links)
                    for j in links:
                        new_scores[j] += damping * share

            delta = sum(abs(new_scores[i] - scores[i]) for i in range(n))
            scores = new_scores
            if delta < tol:
                break

        return {nodes[i]: scores[i] for i in range(n)}

    # ------------------------------------------------------------------
    # Lazy S2 client init
    # ------------------------------------------------------------------

    def _get_s2(self) -> Any:
        if self._s2 is None:
            from berb.literature.semantic_scholar import SemanticScholarClient
            self._s2 = SemanticScholarClient()
        return self._s2


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def get_citation_graph(
    paper_ids: list[str],
    *,
    depth: int = 1,
    max_citations_per_paper: int = 50,
    use_scholar_fallback: bool = False,
    scholar_proxy_api_key: str = "",
    compute_pagerank: bool = True,
) -> CitationGraphResult:
    """Build a citation graph for the given paper IDs.

    Args:
        paper_ids: Seed paper IDs (Semantic Scholar IDs, arXiv IDs, or DOIs).
        depth: Citation hop depth (1 = direct citations only).
        max_citations_per_paper: Cap on citations fetched per paper.
        use_scholar_fallback: Enable Google Scholar as S2 fallback.
        scholar_proxy_api_key: ScraperAPI key for Scholar (optional).
        compute_pagerank: Compute PageRank on the resulting graph.

    Returns:
        CitationGraphResult with nodes, edges, and optional PageRank scores.
    """
    scholar_client = None
    if use_scholar_fallback:
        try:
            from berb.web.scholar import GoogleScholarClient
            scholar_client = GoogleScholarClient(proxy_api_key=scholar_proxy_api_key)
        except ImportError:
            logger.warning("scholarly not installed; Scholar fallback disabled")

    graph = CitationGraph(
        scholar_client=scholar_client,
        max_citations_per_paper=max_citations_per_paper,
        compute_pagerank=compute_pagerank,
    )
    return graph.build(paper_ids, depth=depth)
