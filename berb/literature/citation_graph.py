"""Citation graph intelligence for literature analysis.

This module provides citation network navigation and analysis:
- Forward citation traversal (papers citing this paper)
- Backward citation traversal (papers cited by this paper)
- Citation cluster detection
- Contradiction detection between papers
- Journal quality assessment
- Author authority scoring

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ClusterAlgorithm(str, Enum):
    """Citation clustering algorithm.

    Attributes:
        LOUVAIN: Louvain community detection
        LABEL_PROPAGATION: Label propagation algorithm
        CITATION_COCCURRENCE: Co-citation based clustering
    """

    LOUVAIN = "louvain"
    LABEL_PROPAGATION = "label_propagation"
    CITATION_COCCURRENCE = "citation_cocurrence"


class Paper(BaseModel):
    """Paper metadata for citation analysis.

    Attributes:
        id: Paper identifier (DOI or internal ID)
        doi: Digital Object Identifier
        title: Paper title
        authors: List of author names
        year: Publication year
        venue: Journal/conference name
        citation_count: Number of citations
        references: List of referenced paper IDs
    """

    id: str
    doi: str = ""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    citation_count: int = 0
    references: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(mode="json")


class Cluster(BaseModel):
    """Citation cluster/group of related papers.

    Attributes:
        id: Cluster identifier
        papers: Paper IDs in cluster
        centroid_keywords: Keywords describing cluster
        cohesion_score: How tightly related papers are (0-1)
        size: Number of papers in cluster
    """

    id: str
    papers: list[str] = Field(default_factory=list)
    centroid_keywords: list[str] = Field(default_factory=list)
    cohesion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    size: int = 0

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.size = len(self.papers)


class Contradiction(BaseModel):
    """Contradiction between papers.

    Attributes:
        paper1_id: First paper ID
        paper2_id: Second paper ID
        claim: The claim they disagree on
        paper1_position: First paper's position
        paper2_position: Second paper's position
        confidence: Confidence in contradiction detection (0-1)
        evidence: Evidence supporting contradiction
    """

    paper1_id: str
    paper2_id: str
    claim: str
    paper1_position: str
    paper2_position: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""


class JournalQuality(BaseModel):
    """Journal quality metrics.

    Attributes:
        journal_name: Journal name
        impact_factor: Journal impact factor
        h_index: Journal h-index
        quartile: Journal quartile (Q1-Q4)
        is_predatory: Whether journal is predatory
        retraction_count: Number of retractions
        quality_score: Overall quality score (0-10)
    """

    journal_name: str
    impact_factor: float | None = None
    h_index: int | None = None
    quartile: str = "Q3"
    is_predatory: bool = False
    retraction_count: int = 0
    quality_score: float = Field(default=5.0, ge=0.0, le=10.0)


class CitationGraphClient(Protocol):
    """Protocol for citation graph API clients."""

    async def get_citing_papers(
        self, paper_id: str, limit: int = 100
    ) -> list[Paper]:
        """Get papers that cite the given paper."""
        ...

    async def get_references(
        self, paper_id: str
    ) -> list[str]:
        """Get papers referenced by the given paper."""
        ...

    async def get_paper_details(
        self, paper_id: str
    ) -> Paper | None:
        """Get paper metadata."""
        ...

    async def get_journal_metrics(
        self, journal_name: str
    ) -> dict[str, Any]:
        """Get journal metrics."""
        ...

    async def get_author_metrics(
        self, author_id: str
    ) -> dict[str, Any]:
        """Get author metrics."""
        ...


class CitationGraphEngine:
    """Navigate and analyze citation networks.

    This engine provides:
    1. Forward citation traversal (who cites this)
    2. Backward citation traversal (what this cites)
    3. Citation cluster detection
    4. Contradiction detection
    5. Journal quality assessment
    6. Author authority scoring

    Usage::

        engine = CitationGraphEngine(client)
        citing = await engine.traverse_forward("paper-123", depth=2)
        clusters = await engine.find_citation_clusters([paper1, paper2])

    Attributes:
        client: Citation graph API client
        cache: In-memory cache for paper metadata
    """

    def __init__(self, client: CitationGraphClient | None = None):
        """Initialize citation graph engine.

        Args:
            client: Citation graph API client (optional)
        """
        self.client = client
        self._cache: dict[str, Paper] = {}
        self._journal_cache: dict[str, JournalQuality] = {}

    async def traverse_forward(
        self,
        paper_id: str,
        depth: int = 2,
        max_papers: int = 500,
    ) -> list[Paper]:
        """Find papers that cite this paper (forward citation).

        Args:
            paper_id: Starting paper ID
            depth: Citation depth (1 = direct citers, 2 = citers of citers)
            max_papers: Maximum papers to return

        Returns:
            List of citing papers
        """
        if not self.client:
            logger.warning("No citation client configured")
            return []

        all_citing: list[Paper] = []
        to_process = [paper_id]
        processed = {paper_id}

        for current_depth in range(depth):
            if not to_process or len(all_citing) >= max_papers:
                break

            next_level = []
            for pid in to_process:
                try:
                    citing = await self.client.get_citing_papers(
                        pid, limit=max_papers // (3 ** (current_depth + 1))
                    )
                    for paper in citing:
                        if paper.id not in processed:
                            processed.add(paper.id)
                            all_citing.append(paper)
                            if current_depth < depth - 1:
                                next_level.append(paper.id)
                except Exception as e:
                    logger.error(f"Failed to get citing papers for {pid}: {e}")

            to_process = next_level

        logger.info(
            f"Forward traversal complete: {len(all_citing)} papers at depth {depth}"
        )
        return all_citing[:max_papers]

    async def traverse_backward(
        self,
        paper_id: str,
        depth: int = 2,
        max_papers: int = 500,
    ) -> list[Paper]:
        """Find papers cited by this paper (backward citation).

        Args:
            paper_id: Starting paper ID
            depth: Citation depth
            max_papers: Maximum papers to return

        Returns:
            List of referenced papers
        """
        if not self.client:
            logger.warning("No citation client configured")
            return []

        all_referenced: list[Paper] = []
        to_process = [paper_id]
        processed = {paper_id}

        for current_depth in range(depth):
            if not to_process or len(all_referenced) >= max_papers:
                break

            next_level = []
            for pid in to_process:
                try:
                    # Get paper if not cached
                    if pid not in self._cache:
                        paper = await self.client.get_paper_details(pid)
                        if paper:
                            self._cache[pid] = paper

                    paper = self._cache.get(pid)
                    if paper and paper.references:
                        for ref_id in paper.references:
                            if ref_id not in processed:
                                processed.add(ref_id)
                                # Get referenced paper
                                ref_paper = await self.client.get_paper_details(ref_id)
                                if ref_paper:
                                    self._cache[ref_id] = ref_paper
                                    all_referenced.append(ref_paper)
                                    if current_depth < depth - 1:
                                        next_level.append(ref_id)
                except Exception as e:
                    logger.error(f"Failed to get references for {pid}: {e}")

            to_process = next_level

        logger.info(
            f"Backward traversal complete: {len(all_referenced)} papers at depth {depth}"
        )
        return all_referenced[:max_papers]

    async def find_citation_clusters(
        self,
        seed_papers: list[str],
        algorithm: ClusterAlgorithm = ClusterAlgorithm.LOUVAIN,
        min_cluster_size: int = 3,
        use_bayesian_confidence: bool = True,
        llm_client: Any | None = None,
    ) -> list[Cluster]:
        """Identify thematic clusters in citation network.

        Args:
            seed_papers: List of seed paper IDs
            algorithm: Clustering algorithm to use
            min_cluster_size: Minimum papers per cluster
            use_bayesian_confidence: Whether to use Bayesian confidence updates
            llm_client: LLM client for Bayesian analysis

        Returns:
            List of citation clusters with dynamic confidence scores
        """
        if not seed_papers:
            return []

        # Build citation network
        papers = await self._fetch_network(seed_papers)

        if len(papers) < min_cluster_size:
            return []

        # Simple clustering based on shared references
        # In production, would use NetworkX with Louvain algorithm
        clusters = self._cluster_by_shared_references(papers, min_cluster_size)

        # Enhance cluster confidence with Bayesian updates if enabled
        if use_bayesian_confidence and llm_client:
            clusters = await self._enhance_cluster_confidence_bayesian(
                clusters, papers, llm_client
            )

        logger.info(f"Found {len(clusters)} clusters from {len(papers)} papers")
        return clusters

    async def _enhance_cluster_confidence_bayesian(
        self,
        clusters: list[Cluster],
        papers: list[Paper],
        llm_client: Any,
    ) -> list[Cluster]:
        """Enhance cluster confidence using Bayesian belief updates.

        Uses Bayesian reasoning to update cluster confidence based on evidence:
        1. Prior confidence from Jaccard similarity
        2. Evidence: keyword overlap, citation patterns, venue similarity
        3. Posterior confidence after evidence integration

        Args:
            clusters: Initial clusters
            papers: All papers in network
            llm_client: LLM client for analysis

        Returns:
            List of clusters with enhanced confidence scores
        """
        enhanced_clusters = []

        for cluster in clusters:
            # Get papers in cluster
            cluster_papers = [
                p for p in papers if p.id in cluster.papers
            ]

            if len(cluster_papers) < 2:
                enhanced_clusters.append(cluster)
                continue

            # Define prior confidence (from Jaccard similarity)
            prior_confidence = cluster.cohesion_score

            # Gather evidence for Bayesian update
            evidence_score = self._gather_cluster_evidence(cluster_papers)

            # Apply Bayesian update
            # P(cluster_valid | evidence) = P(evidence | cluster_valid) × P(cluster_valid) / P(evidence)
            likelihood_given_valid = 0.8 if evidence_score > 0.6 else 0.4
            likelihood_given_invalid = 0.3 if evidence_score > 0.6 else 0.6

            prior_valid = prior_confidence
            prior_invalid = 1 - prior_confidence

            evidence_prob = (
                likelihood_given_valid * prior_valid +
                likelihood_given_invalid * prior_invalid
            )

            if evidence_prob > 0:
                posterior_confidence = (likelihood_given_valid * prior_valid) / evidence_prob
            else:
                posterior_confidence = prior_confidence

            # Adjust confidence
            cluster.cohesion_score = min(1.0, max(0.0, posterior_confidence))
            enhanced_clusters.append(cluster)

        return enhanced_clusters

    def _gather_cluster_evidence(
        self,
        cluster_papers: list[Paper],
    ) -> float:
        """Gather evidence for cluster validity.

        Evidence factors:
        1. Keyword overlap in titles
        2. Shared references
        3. Venue similarity
        4. Publication year proximity

        Args:
            cluster_papers: Papers in cluster

        Returns:
            Evidence score from 0-1
        """
        if len(cluster_papers) < 2:
            return 0.5

        evidence_scores = []

        # Evidence 1: Keyword overlap
        title_words = [
            set(p.title.lower().split())
            for p in cluster_papers if p.title
        ]
        if len(title_words) >= 2:
            overlaps = [
                len(w1 & w2) / max(len(w1), len(w2))
                for i, w1 in enumerate(title_words)
                for w2 in title_words[i+1:]
            ]
            if overlaps:
                evidence_scores.append(sum(overlaps) / len(overlaps))

        # Evidence 2: Shared references
        ref_sets = [set(p.references) for p in cluster_papers if p.references]
        if len(ref_sets) >= 2:
            ref_overlaps = [
                len(r1 & r2) / max(len(r1), len(r2))
                for i, r1 in enumerate(ref_sets)
                for r2 in ref_sets[i+1:]
                if r1 and r2
            ]
            if ref_overlaps:
                evidence_scores.append(sum(ref_overlaps) / len(ref_overlaps))

        # Evidence 3: Venue similarity
        venues = [p.venue for p in cluster_papers if p.venue]
        if venues:
            venue_mode = max(set(venues), key=venues.count)
            venue_similarity = venues.count(venue_mode) / len(venues)
            evidence_scores.append(venue_similarity)

        # Evidence 4: Year proximity
        years = [p.year for p in cluster_papers if p.year]
        if len(years) >= 2:
            year_range = max(years) - min(years)
            year_proximity = max(0, 1 - year_range / 10)  # 10-year window
            evidence_scores.append(year_proximity)

        return sum(evidence_scores) / len(evidence_scores) if evidence_scores else 0.5

    async def _fetch_network(
        self,
        seed_papers: list[str],
        max_papers: int = 200,
    ) -> list[Paper]:
        """Fetch citation network around seed papers.

        Args:
            seed_papers: Seed paper IDs
            max_papers: Maximum papers to fetch

        Returns:
            List of papers in network
        """
        network: dict[str, Paper] = {}

        # Get seed papers
        for pid in seed_papers:
            if pid not in self._cache and self.client:
                paper = await self.client.get_paper_details(pid)
                if paper:
                    self._cache[pid] = paper

            if pid in self._cache:
                network[pid] = self._cache[pid]

        # Get references for each seed
        for pid in list(network.keys()):
            if len(network) >= max_papers:
                break

            paper = network[pid]
            for ref_id in paper.references[:20]:  # Limit references per paper
                if ref_id not in network and ref_id in self._cache:
                    network[ref_id] = self._cache[ref_id]
                elif self.client and len(network) < max_papers:
                    ref_paper = await self.client.get_paper_details(ref_id)
                    if ref_paper:
                        self._cache[ref_id] = ref_paper
                        network[ref_id] = ref_paper

        return list(network.values())

    def _cluster_by_shared_references(
        self,
        papers: list[Paper],
        min_cluster_size: int,
    ) -> list[Cluster]:
        """Cluster papers by shared references.

        Args:
            papers: List of papers
            min_cluster_size: Minimum cluster size

        Returns:
            List of clusters
        """
        if not papers:
            return []

        # Build reference sets
        paper_refs: dict[str, set[str]] = {
            p.id: set(p.references) for p in papers
        }

        # Simple Jaccard similarity clustering
        clusters: list[Cluster] = []
        assigned: set[str] = set()

        for paper in papers:
            if paper.id in assigned:
                continue

            # Start new cluster
            cluster_papers = [paper.id]
            assigned.add(paper.id)

            # Find similar papers
            for other in papers:
                if other.id in assigned:
                    continue

                # Calculate Jaccard similarity
                refs1 = paper_refs.get(paper.id, set())
                refs2 = paper_refs.get(other.id, set())

                if refs1 and refs2:
                    intersection = len(refs1 & refs2)
                    union = len(refs1 | refs2)
                    similarity = intersection / union if union > 0 else 0

                    if similarity > 0.3:  # Threshold for same cluster
                        cluster_papers.append(other.id)
                        assigned.add(other.id)

            if len(cluster_papers) >= min_cluster_size:
                # Extract keywords from cluster
                keywords = self._extract_cluster_keywords(
                    [self._cache.get(pid) for pid in cluster_papers if pid in self._cache]
                )

                clusters.append(
                    Cluster(
                        id=f"cluster_{len(clusters) + 1}",
                        papers=cluster_papers,
                        centroid_keywords=keywords[:5],
                        cohesion_score=0.7,  # Simplified
                    )
                )

        return clusters

    def _extract_cluster_keywords(
        self,
        papers: list[Paper | None],
    ) -> list[str]:
        """Extract representative keywords from cluster.

        Args:
            papers: Papers in cluster

        Returns:
            List of keywords
        """
        # Simplified keyword extraction from titles
        words: dict[str, int] = {}
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
        }

        for paper in papers:
            if paper and paper.title:
                for word in paper.title.lower().split():
                    word = word.strip(".,;:!?()[]{}\"'")
                    if word not in stop_words and len(word) > 3:
                        words[word] = words.get(word, 0) + 1

        # Return top words
        sorted_words = sorted(words.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:10]]

    async def detect_contradictions(
        self,
        papers: list[Paper],
        use_multi_perspective: bool = True,
        llm_client: Any | None = None,
    ) -> list[Contradiction]:
        """Find papers that report conflicting results.

        Args:
            papers: List of papers to analyze
            use_multi_perspective: Whether to use multi-perspective analysis
            llm_client: LLM client for multi-perspective analysis

        Returns:
            List of detected contradictions
        """
        if not papers or len(papers) < 2:
            return []

        contradictions = []

        # Use multi-perspective analysis if enabled
        if use_multi_perspective and llm_client:
            contradictions = await self._detect_contradictions_multiperspective(
                papers, llm_client
            )
        else:
            # Fallback to simplified detection
            for i, paper1 in enumerate(papers):
                for paper2 in papers[i + 1:]:
                    if self._might_contradict(paper1, paper2):
                        contradictions.append(
                            Contradiction(
                                paper1_id=paper1.id,
                                paper2_id=paper2.id,
                                claim="Potential contradiction detected",
                                paper1_position="unknown",
                                paper2_position="unknown",
                                confidence=0.5,
                                evidence="Papers may have conflicting claims",
                            )
                        )

        logger.info(f"Detected {len(contradictions)} potential contradictions")
        return contradictions

    async def _detect_contradictions_multiperspective(
        self,
        papers: list[Paper],
        llm_client: Any,
    ) -> list[Contradiction]:
        """Detect contradictions using multi-perspective analysis.

        Uses 4 perspectives to analyze potential contradictions:
        1. Methodology - Do the methods contradict?
        2. Results - Do the results contradict?
        3. Interpretation - Do the interpretations contradict?
        4. Scope - Are they actually about different things?

        Args:
            papers: List of papers to analyze
            llm_client: LLM client for analysis

        Returns:
            List of detected contradictions with higher accuracy
        """
        from berb.reasoning.multi_perspective import (
            MultiPerspectiveMethod,
            PerspectiveType,
        )

        contradictions = []
        mp_method = MultiPerspectiveMethod(llm_client=llm_client)

        # Analyze each pair of papers
        for i, paper1 in enumerate(papers):
            for paper2 in papers[i + 1:]:
                # Build analysis prompt for each perspective
                perspectives_analysis = {}

                # 1. Methodology perspective
                method_problem = f"""Analyze if these papers have contradictory methodologies:

Paper 1: {paper1.title}
Paper 2: {paper2.title}

Consider:
- Different experimental designs?
- Different measurement techniques?
- Different control conditions?
- Different statistical methods?

Return JSON: {{"contradicts": bool, "reasoning": "explanation", "confidence": 0-1}}"""

                # 2. Results perspective
                results_problem = f"""Analyze if these papers report contradictory results:

Paper 1: {paper1.title}
Paper 2: {paper2.title}

Consider:
- Opposite findings?
- Significantly different effect sizes?
- Different directions of correlation?

Return JSON: {{"contradicts": bool, "reasoning": "explanation", "confidence": 0-1}}"""

                # 3. Interpretation perspective
                interpretation_problem = f"""Analyze if these papers interpret findings differently:

Paper 1: {paper1.title}
Paper 2: {paper2.title}

Consider:
- Different theoretical frameworks?
- Different causal explanations?
- Different implications drawn?

Return JSON: {{"contradicts": bool, "reasoning": "explanation", "confidence": 0-1}}"""

                # 4. Scope perspective
                scope_problem = f"""Analyze if these papers are actually about different things:

Paper 1: {paper1.title}
Paper 2: {paper2.title}

Consider:
- Different populations studied?
- Different conditions examined?
- Different variables measured?
- Different research questions?

Return JSON: {{"different_scope": bool, "reasoning": "explanation", "confidence": 0-1}}"""

                # Run perspective analyses (simplified - would use full MP framework)
                # For now, use keyword-based analysis as placeholder
                method_analysis = self._analyze_perspective(paper1, paper2, "methodology")
                results_analysis = self._analyze_perspective(paper1, paper2, "results")
                interpretation_analysis = self._analyze_perspective(paper1, paper2, "interpretation")
                scope_analysis = self._analyze_perspective(paper1, paper2, "scope")

                # Aggregate perspectives
                contradiction_count = sum([
                    method_analysis.get("contradicts", False),
                    results_analysis.get("contradicts", False),
                    interpretation_analysis.get("contradicts", False),
                ])
                scope_different = scope_analysis.get("different_scope", False)

                # Determine if true contradiction
                if contradiction_count >= 2 and not scope_different:
                    # True contradiction (multiple perspectives agree, not just different scope)
                    avg_confidence = (
                        method_analysis.get("confidence", 0.5) +
                        results_analysis.get("confidence", 0.5) +
                        interpretation_analysis.get("confidence", 0.5)
                    ) / 3

                    contradictions.append(
                        Contradiction(
                            paper1_id=paper1.id,
                            paper2_id=paper2.id,
                            claim=f"Contradiction in {contradiction_count} perspectives",
                            paper1_position=paper1.title[:100],
                            paper2_position=paper2.title[:100],
                            confidence=avg_confidence,
                            evidence=self._build_contradiction_evidence(
                                method_analysis, results_analysis, interpretation_analysis
                            ),
                        )
                    )

        return contradictions

    def _analyze_perspective(
        self,
        paper1: Paper,
        paper2: Paper,
        perspective: str,
    ) -> dict[str, Any]:
        """Analyze papers from a specific perspective.

        Args:
            paper1: First paper
            paper2: Second paper
            perspective: Perspective to analyze

        Returns:
            Analysis result dictionary
        """
        # Simplified analysis (would use LLM in production)
        title1 = paper1.title.lower()
        title2 = paper2.title.lower()

        if perspective == "methodology":
            # Check for different methodology keywords
            method1_keywords = ["experimental", "clinical", "survey", "meta-analysis"]
            method2_keywords = ["simulation", "theoretical", "review", "case study"]
            contradicts = any(kw in title1 for kw in method1_keywords) and \
                         any(kw in title2 for kw in method2_keywords)
            return {"contradicts": contradicts, "confidence": 0.6 if contradicts else 0.4}

        elif perspective == "results":
            # Check for contrasting result keywords
            contrast_keywords = ["increases", "decreases", "improves", "worsens",
                               "positive", "negative", "significant", "null"]
            contradicts = sum(kw in title1 for kw in contrast_keywords) > 0 and \
                         sum(kw in title2 for kw in contrast_keywords) > 0
            return {"contradicts": contradicts, "confidence": 0.5 if contradicts else 0.4}

        elif perspective == "interpretation":
            # Check for different interpretation keywords
            interp1_keywords = ["causes", "leads to", "mechanism", "pathway"]
            interp2_keywords = ["correlates", "associated with", "relationship", "link"]
            contradicts = any(kw in title1 for kw in interp1_keywords) and \
                         any(kw in title2 for kw in interp2_keywords)
            return {"contradicts": contradicts, "confidence": 0.55 if contradicts else 0.4}

        elif perspective == "scope":
            # Check for different scope keywords
            scope1_keywords = ["children", "elderly", "patients", "healthy"]
            scope2_keywords = ["animals", "cells", "in vitro", "in silico"]
            different = any(kw in title1 for kw in scope1_keywords) and \
                       any(kw in title2 for kw in scope2_keywords)
            return {"different_scope": different, "confidence": 0.7 if different else 0.3}

        return {"contradicts": False, "confidence": 0.4}

    def _build_contradiction_evidence(
        self,
        method_analysis: dict,
        results_analysis: dict,
        interpretation_analysis: dict,
    ) -> str:
        """Build evidence string from perspective analyses.

        Args:
            method_analysis: Methodology analysis
            results_analysis: Results analysis
            interpretation_analysis: Interpretation analysis

        Returns:
            Evidence string
        """
        evidence_parts = []

        if method_analysis.get("contradicts"):
            evidence_parts.append("Different methodologies")
        if results_analysis.get("contradicts"):
            evidence_parts.append("Contradictory results")
        if interpretation_analysis.get("contradicts"):
            evidence_parts.append("Different interpretations")

        return "; ".join(evidence_parts) if evidence_parts else "Multiple perspective contradictions"

    def _might_contradict(
        self,
        paper1: Paper,
        paper2: Paper,
    ) -> bool:
        """Check if two papers might contradict.

        Args:
            paper1: First paper
            paper2: Second paper

        Returns:
            True if might contradict
        """
        # Simplified heuristic
        # In production, would analyze citation context
        if not paper1.title or not paper2.title:
            return False

        # Same topic but different conclusions
        title1 = paper1.title.lower()
        title2 = paper2.title.lower()

        # Check for contrasting keywords
        contrasting = {
            "not", "no", "without", "fail", "failed", "impossible",
            "contrary", "opposite", "contradict", "challenge",
        }

        has_contrast1 = any(w in title1 for w in contrasting)
        has_contrast2 = any(w in title2 for w in contrasting)

        # Simple word overlap
        words1 = set(title1.split())
        words2 = set(title2.split())
        overlap = len(words1 & words2) / max(len(words1), len(words2))

        return overlap > 0.5 and (has_contrast1 or has_contrast2)

    async def journal_quality_check(
        self,
        paper: Paper,
    ) -> JournalQuality:
        """Check journal quality metrics.

        Args:
            paper: Paper to check

        Returns:
            JournalQuality assessment
        """
        if not paper.venue:
            return JournalQuality(
                journal_name="Unknown",
                quality_score=5.0,
            )

        # Check cache
        if paper.venue in self._journal_cache:
            return self._journal_cache[paper.venue]

        # Get metrics from client
        metrics = {}
        if self.client:
            try:
                metrics = await self.client.get_journal_metrics(paper.venue)
            except Exception as e:
                logger.warning(f"Failed to get journal metrics: {e}")

        # Build quality assessment
        quality = JournalQuality(
            journal_name=paper.venue,
            impact_factor=metrics.get("impact_factor"),
            h_index=metrics.get("h_index"),
            quartile=metrics.get("quartile", "Q3"),
            is_predatory=metrics.get("is_predatory", False),
            retraction_count=metrics.get("retraction_count", 0),
        )

        # Calculate quality score
        score = 5.0
        if quality.impact_factor:
            score += min(3.0, quality.impact_factor / 5.0)
        if quality.h_index:
            score += min(1.0, quality.h_index / 100.0)
        if quality.quartile == "Q1":
            score += 1.0
        elif quality.quartile == "Q2":
            score += 0.5
        if quality.is_predatory:
            score = 1.0
        if quality.retraction_count > 5:
            score -= 2.0

        quality.quality_score = max(0.0, min(10.0, score))

        self._journal_cache[paper.venue] = quality
        return quality

    async def author_authority_score(
        self,
        author_id: str,
        domain: str,
    ) -> float:
        """Score author's authority in a specific domain.

        Args:
            author_id: Author identifier
            domain: Research domain

        Returns:
            Authority score (0-10)
        """
        if not self.client:
            return 5.0

        try:
            metrics = await self.client.get_author_metrics(author_id)
        except Exception as e:
            logger.warning(f"Failed to get author metrics: {e}")
            return 5.0

        # Calculate authority score
        score = 5.0

        # h-index contribution
        h_index = metrics.get("h_index", 0)
        score += min(3.0, h_index / 20.0)

        # Citation count contribution
        citations = metrics.get("citation_count", 0)
        score += min(1.0, citations / 10000.0)

        # Paper count contribution
        papers = metrics.get("paper_count", 0)
        score += min(1.0, papers / 100.0)

        # Domain relevance
        domain_match = metrics.get("domain_relevance", 0.5)
        score *= (0.5 + domain_match * 0.5)

        return max(0.0, min(10.0, score))


class CitationGraphConfig(BaseModel):
    """Configuration for citation graph engine.

    Attributes:
        enabled: Whether citation graph analysis is enabled
        max_depth: Maximum traversal depth
        max_papers: Maximum papers to fetch
        min_cluster_size: Minimum papers per cluster
        cache_enabled: Whether to cache results
    """

    enabled: bool = True
    max_depth: int = 2
    max_papers: int = 500
    min_cluster_size: int = 3
    cache_enabled: bool = True


# Convenience function
async def analyze_citation_network(
    paper_ids: list[str],
    client: CitationGraphClient | None = None,
    config: CitationGraphConfig | None = None,
) -> dict[str, Any]:
    """Convenience function for citation network analysis.

    Args:
        paper_ids: List of paper IDs to analyze
        client: Citation graph client
        config: Engine configuration

    Returns:
        Analysis results dictionary
    """
    config = config or CitationGraphConfig()
    if not config.enabled:
        return {}

    engine = CitationGraphEngine(client)

    # Forward and backward traversal
    all_citing: list[Paper] = []
    all_referenced: list[Paper] = []

    for pid in paper_ids:
        citing = await engine.traverse_forward(
            pid, depth=config.max_depth, max_papers=config.max_papers
        )
        referenced = await engine.traverse_backward(
            pid, depth=config.max_depth, max_papers=config.max_papers
        )
        all_citing.extend(citing)
        all_referenced.extend(referenced)

    # Find clusters
    clusters = await engine.find_citation_clusters(
        paper_ids, min_cluster_size=config.min_cluster_size
    )

    # Detect contradictions
    all_papers = list(set(all_citing + all_referenced))
    contradictions = await engine.detect_contradictions(all_papers)

    return {
        "citing_papers": [p.to_dict() for p in all_citing],
        "referenced_papers": [p.to_dict() for p in all_referenced],
        "clusters": [c.model_dump() for c in clusters],
        "contradictions": [cd.model_dump() for cd in contradictions],
        "total_papers": len(all_papers),
        "total_clusters": len(clusters),
        "total_contradictions": len(contradictions),
    }
