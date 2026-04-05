"""Citation recency filter for prioritizing recent work.

This module provides recency-aware citation filtering:
- Configurable recency window (default: 5 years)
- Field-aware windows (ML: 3 years, Physics: 10 years)
- Boosts recent highly-cited papers
- Filters outdated methods

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RecencyFilterConfig(BaseModel):
    """Configuration for recency filter.

    Attributes:
        enabled: Whether filter is enabled
        default_window_years: Default recency window
        field_overrides: Field-specific window overrides
        boost_recent_citations: Whether to boost recent papers
        min_citation_boost: Minimum citations for boost
    """

    enabled: bool = True
    default_window_years: int = 5
    field_overrides: dict[str, int] = Field(default_factory=dict)
    boost_recent_citations: bool = True
    min_citation_boost: int = 10


class RecencyFilter:
    """Filter and prioritize citations by recency.

    This filter:
    1. Calculates paper age
    2. Applies field-specific windows
    3. Boosts recent highly-cited papers
    4. Filters outdated methods

    Usage::

        filter = RecencyFilter(field="machine-learning")
        scored = await filter.score_papers(papers)
        filtered = filter.filter_by_recency(papers)

    Attributes:
        field: Research field
        config: Filter configuration
    """

    # Field-specific recency windows
    FIELD_WINDOWS = {
        "machine-learning": 3,
        "deep-learning": 3,
        "ai": 3,
        "computer-vision": 4,
        "nlp": 4,
        "biomedical": 5,
        "clinical": 5,
        "physics": 10,
        "mathematics": 15,
        "social-sciences": 7,
        "humanities": 20,
    }

    def __init__(
        self,
        field: str = "general",
        config: RecencyFilterConfig | None = None,
    ):
        """Initialize recency filter.

        Args:
            field: Research field
            config: Filter configuration
        """
        self.field = field.lower()
        self.config = config or RecencyFilterConfig()

        # Determine recency window
        self.window_years = self._get_window_for_field(field)

    def _get_window_for_field(self, field: str) -> int:
        """Get recency window for a field.

        Args:
            field: Research field

        Returns:
            Window in years
        """
        # Check field overrides
        if self.config.field_overrides:
            for field_pattern, window in self.config.field_overrides.items():
                if field_pattern in field.lower():
                    return window

        # Check default field windows
        for field_pattern, window in self.FIELD_WINDOWS.items():
            if field_pattern in field.lower():
                return window

        # Use default
        return self.config.default_window_years

    async def score_papers(
        self,
        papers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Score papers by recency and citations.

        Args:
            papers: List of papers

        Returns:
            Papers with recency scores
        """
        current_year = datetime.now(timezone.utc).year
        scored_papers = []

        for paper in papers:
            # Calculate age
            year = paper.get("year")
            if not year:
                age = 999  # Very old if year unknown
            else:
                age = current_year - year

            # Calculate recency score
            recency_score = self._calculate_recency_score(age)

            # Calculate citation boost
            citation_boost = 0.0
            if self.config.boost_recent_citations and age <= self.window_years:
                citations = paper.get("citation_count", 0)
                if citations >= self.config.min_citation_boost:
                    citation_boost = min(0.5, citations / 100.0)

            # Combined score
            combined_score = recency_score + citation_boost

            # Add scores to paper
            scored_paper = paper.copy()
            scored_paper["recency_score"] = recency_score
            scored_paper["citation_boost"] = citation_boost
            scored_paper["combined_score"] = combined_score
            scored_paper["age_years"] = age

            scored_papers.append(scored_paper)

        # Sort by combined score
        scored_papers.sort(key=lambda p: p["combined_score"], reverse=True)

        return scored_papers

    def _calculate_recency_score(self, age: int) -> float:
        """Calculate recency score for a paper age.

        Args:
            age: Paper age in years

        Returns:
            Recency score (0-1)
        """
        if age <= 0:
            return 1.0
        elif age <= self.window_years:
            # Linear decay within window
            return 1.0 - (age / self.window_years) * 0.3
        elif age <= self.window_years * 2:
            # Steeper decay outside window
            return 0.7 - ((age - self.window_years) / self.window_years) * 0.4
        else:
            # Very low score for old papers
            return max(0.1, 0.3 - (age / 100.0))

    def filter_by_recency(
        self,
        papers: list[dict[str, Any]],
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Filter papers by recency.

        Args:
            papers: List of papers
            min_score: Minimum recency score

        Returns:
            Filtered papers
        """
        current_year = datetime.now(timezone.utc).year
        filtered = []

        for paper in papers:
            year = paper.get("year")
            if not year:
                continue

            age = current_year - year
            score = self._calculate_recency_score(age)

            if score >= min_score:
                filtered_paper = paper.copy()
                filtered_paper["recency_score"] = score
                filtered_paper["age_years"] = age
                filtered.append(filtered_paper)

        # Sort by recency score
        filtered.sort(key=lambda p: p["recency_score"], reverse=True)

        return filtered

    def is_outdated(
        self,
        paper: dict[str, Any],
    ) -> bool:
        """Check if paper is outdated.

        Args:
            paper: Paper metadata

        Returns:
            True if outdated
        """
        year = paper.get("year")
        if not year:
            return True

        current_year = datetime.now(timezone.utc).year
        age = current_year - year

        return age > self.window_years * 2

    def get_fresh_papers(
        self,
        papers: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Get freshest papers.

        Args:
            papers: List of papers
            top_k: Number of papers to return

        Returns:
            Freshest papers
        """
        scored = self.score_papers(papers)
        return scored[:top_k]


class RecencyAwareRanker:
    """Rank papers with recency awareness.

    This ranker:
    1. Combines relevance with recency
    2. Boosts recent highly-cited work
    3. Demotes outdated methods

    Attributes:
        recency_weight: Weight for recency in ranking
    """

    def __init__(
        self,
        field: str = "general",
        recency_weight: float = 0.3,
    ):
        """Initialize ranker.

        Args:
            field: Research field
            recency_weight: Weight for recency (0-1)
        """
        self.field = field
        self.recency_weight = recency_weight
        self.filter = RecencyFilter(field=field)

    async def rank(
        self,
        papers: list[dict[str, Any]],
        relevance_scores: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Rank papers combining relevance and recency.

        Args:
            papers: List of papers
            relevance_scores: Optional relevance scores

        Returns:
            Ranked papers
        """
        # Get recency scores
        scored_papers = await self.filter.score_papers(papers)

        # Combine with relevance
        for paper in scored_papers:
            paper_id = paper.get("id", paper.get("doi", ""))
            relevance = relevance_scores.get(paper_id, 0.5) if relevance_scores else 0.5

            # Combined ranking score
            recency = paper.get("recency_score", 0.5)
            combined = (
                (1 - self.recency_weight) * relevance +
                self.recency_weight * recency
            )

            paper["ranking_score"] = combined

        # Sort by ranking score
        scored_papers.sort(key=lambda p: p["ranking_score"], reverse=True)

        return scored_papers


# Convenience functions
async def filter_papers_by_recency(
    papers: list[dict[str, Any]],
    field: str = "general",
    min_score: float = 0.3,
) -> list[dict[str, Any]]:
    """Convenience function for recency filtering.

    Args:
        papers: Papers to filter
        field: Research field
        min_score: Minimum recency score

    Returns:
        Filtered papers
    """
    filter = RecencyFilter(field=field)
    return filter.filter_by_recency(papers, min_score)


async def rank_papers_with_recency(
    papers: list[dict[str, Any]],
    field: str = "general",
    recency_weight: float = 0.3,
) -> list[dict[str, Any]]:
    """Convenience function for recency-aware ranking.

    Args:
        papers: Papers to rank
        field: Research field
        recency_weight: Weight for recency

    Returns:
        Ranked papers
    """
    ranker = RecencyAwareRanker(field=field, recency_weight=recency_weight)
    return await ranker.rank(papers)
