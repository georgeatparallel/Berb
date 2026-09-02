"""Specification pattern for literature filtering.

P2 2026-04-02: Composable filtering for paper search.

This module implements the Specification pattern for flexible,
composable paper filtering. Specifications can be combined using
AND, OR, and NOT operators.

Usage:
    from berb.literature.specification import (
        YearSpecification,
        CitationSpecification,
        AndSpecification,
        OrSpecification,
    )

    # Create individual specifications
    recent = YearSpecification(min_year=2020, max_year=2026)
    influential = CitationSpecification(min_citations=50)

    # Combine specifications
    filter = AndSpecification(recent, influential)

    # Filter papers
    filtered = [p for p in papers if filter.is_satisfied_by(p)]

# Author: Georgios-Chrysovalantis Chatzivantsidis
# Date: 2026-04-02
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from berb.literature.models import Paper


class Specification(Protocol):
    """Protocol for paper specifications.

    A specification defines criteria that papers can satisfy.
    """

    def is_satisfied_by(self, paper: Paper) -> bool:
        """Check if paper satisfies this specification.

        Args:
            paper: Paper to check

        Returns:
            True if paper satisfies specification
        """
        ...

    def and_(self, other: Specification) -> Specification:
        """Combine with another specification using AND."""
        ...

    def or_(self, other: Specification) -> Specification:
        """Combine with another specification using OR."""
        ...

    def not_(self) -> Specification:
        """Negate this specification."""
        ...


@dataclass
class YearSpecification:
    """Specification for paper year range.

    P2 2026-04-02: Filter papers by publication year.

    Attributes:
        min_year: Minimum publication year (inclusive)
        max_year: Maximum publication year (inclusive)
    """

    min_year: int = 0
    max_year: int = 9999

    def is_satisfied_by(self, paper: Paper) -> bool:
        """Check if paper year is within range."""
        return self.min_year <= paper.year <= self.max_year

    def and_(self, other: Specification) -> Specification:
        """Combine with AND."""
        return AndSpecification(self, other)

    def or_(self, other: Specification) -> Specification:
        """Combine with OR."""
        return OrSpecification(self, other)

    def not_(self) -> Specification:
        """Negate this specification."""
        return NotSpecification(self)


@dataclass
class CitationSpecification:
    """Specification for minimum citation count.

    P2 2026-04-02: Filter papers by citation impact.

    Attributes:
        min_citations: Minimum number of citations
    """

    min_citations: int = 0

    def is_satisfied_by(self, paper: Paper) -> bool:
        """Check if paper has enough citations."""
        return paper.citation_count >= self.min_citations

    def and_(self, other: Specification) -> Specification:
        """Combine with AND."""
        return AndSpecification(self, other)

    def or_(self, other: Specification) -> Specification:
        """Combine with OR."""
        return OrSpecification(self, other)

    def not_(self) -> Specification:
        """Negate this specification."""
        return NotSpecification(self)


@dataclass
class VenueSpecification:
    """Specification for paper venue/journal.

    P2 2026-04-02: Filter papers by venue name.

    Attributes:
        venues: List of venue names to match (case-insensitive)
        exact_match: Whether to match exactly or use substring
    """

    venues: list[str]
    exact_match: bool = False

    def is_satisfied_by(self, paper: Paper) -> bool:
        """Check if paper venue matches."""
        paper_venue = paper.venue.lower() if paper.venue else ""

        for venue in self.venues:
            venue_lower = venue.lower()
            if self.exact_match:
                if paper_venue == venue_lower:
                    return True
            else:
                if venue_lower in paper_venue:
                    return True

        return False

    def and_(self, other: Specification) -> Specification:
        """Combine with AND."""
        return AndSpecification(self, other)

    def or_(self, other: Specification) -> Specification:
        """Combine with OR."""
        return OrSpecification(self, other)

    def not_(self) -> Specification:
        """Negate this specification."""
        return NotSpecification(self)


@dataclass
class AuthorSpecification:
    """Specification for paper authors.

    P2 2026-04-02: Filter papers by author names.

    Attributes:
        authors: List of author names to search for
        match_all: Whether all authors must be present (default: any)
    """

    authors: list[str]
    match_all: bool = False

    def is_satisfied_by(self, paper: Paper) -> bool:
        """Check if paper has matching authors."""
        if not paper.authors:
            return False

        paper_author_names = [
            a.name.lower() if hasattr(a, "name") else str(a).lower() for a in paper.authors
        ]

        if self.match_all:
            # All specified authors must be present
            return all(
                any(name.startswith(author.lower()) for name in paper_author_names)
                for author in self.authors
            )
        else:
            # Any specified author is sufficient
            return any(
                any(name.startswith(author.lower()) for name in paper_author_names)
                for author in self.authors
            )

    def and_(self, other: Specification) -> Specification:
        """Combine with AND."""
        return AndSpecification(self, other)

    def or_(self, other: Specification) -> Specification:
        """Combine with OR."""
        return OrSpecification(self, other)

    def not_(self) -> Specification:
        """Negate this specification."""
        return NotSpecification(self)


class AndSpecification:
    """Combines two specifications with AND logic.

    P2 2026-04-02: Both specifications must be satisfied.

    Attributes:
        left: Left specification
        right: Right specification
    """

    def __init__(self, left: Specification, right: Specification):
        self.left = left
        self.right = right

    def is_satisfied_by(self, paper: Paper) -> bool:
        """Check if both specifications are satisfied."""
        return self.left.is_satisfied_by(paper) and self.right.is_satisfied_by(paper)

    def and_(self, other: Specification) -> Specification:
        """Combine with AND."""
        return AndSpecification(self, other)

    def or_(self, other: Specification) -> Specification:
        """Combine with OR."""
        return OrSpecification(self, other)

    def not_(self) -> Specification:
        """Negate this specification."""
        return NotSpecification(self)


class OrSpecification:
    """Combines two specifications with OR logic.

    P2 2026-04-02: Either specification must be satisfied.

    Attributes:
        left: Left specification
        right: Right specification
    """

    def __init__(self, left: Specification, right: Specification):
        self.left = left
        self.right = right

    def is_satisfied_by(self, paper: Paper) -> bool:
        """Check if either specification is satisfied."""
        return self.left.is_satisfied_by(paper) or self.right.is_satisfied_by(paper)

    def and_(self, other: Specification) -> Specification:
        """Combine with AND."""
        return AndSpecification(self, other)

    def or_(self, other: Specification) -> Specification:
        """Combine with OR."""
        return OrSpecification(self, other)

    def not_(self) -> Specification:
        """Negate this specification."""
        return NotSpecification(self)


class NotSpecification:
    """Negates a specification.

    P2 2026-04-02: Specification must NOT be satisfied.

    Attributes:
        inner: Specification to negate
    """

    def __init__(self, inner: Specification):
        self.inner = inner

    def is_satisfied_by(self, paper: Paper) -> bool:
        """Check if inner specification is NOT satisfied."""
        return not self.inner.is_satisfied_by(paper)

    def and_(self, other: Specification) -> Specification:
        """Combine with AND."""
        return AndSpecification(self, other)

    def or_(self, other: Specification) -> Specification:
        """Combine with OR."""
        return OrSpecification(self, other)

    def not_(self) -> Specification:
        """Double negation."""
        return self.inner


# Convenience functions for fluent API
def year_range(min_year: int, max_year: int) -> YearSpecification:
    """Create year range specification.

    P2 2026-04-02: Convenience function for year filtering.

    Args:
        min_year: Minimum year
        max_year: Maximum year

    Returns:
        YearSpecification
    """
    return YearSpecification(min_year=min_year, max_year=max_year)


def min_citations(count: int) -> CitationSpecification:
    """Create minimum citation specification.

    P2 2026-04-02: Convenience function for citation filtering.

    Args:
        count: Minimum citation count

    Returns:
        CitationSpecification
    """
    return CitationSpecification(min_citations=count)


def venue_match(*venues: str, exact: bool = False) -> VenueSpecification:
    """Create venue match specification.

    P2 2026-04-02: Convenience function for venue filtering.

    Args:
        *venues: Venue names to match
        exact: Whether to match exactly

    Returns:
        VenueSpecification
    """
    return VenueSpecification(venues=list(venues), exact_match=exact)


def author_match(*authors: str, match_all: bool = False) -> AuthorSpecification:
    """Create author match specification.

    P2 2026-04-02: Convenience function for author filtering.

    Args:
        *authors: Author names to match
        match_all: Whether all authors must be present

    Returns:
        AuthorSpecification
    """
    return AuthorSpecification(authors=list(authors), match_all=match_all)


# Fluent API extensions for built-in types
class PaperFilter:
    """Fluent API for building paper filters.

    P2 2026-04-02: Builder pattern for complex specifications.

    Usage:
        filter = (PaperFilter()
            .from_year(2020)
            .to_year(2026)
            .with_min_citations(50)
            .build())
    """

    def __init__(self):
        self._specifications: list[Specification] = []

    def from_year(self, year: int) -> PaperFilter:
        """Set minimum year."""
        self._specifications.append(YearSpecification(min_year=year))
        return self

    def to_year(self, year: int) -> PaperFilter:
        """Set maximum year."""
        self._specifications.append(YearSpecification(max_year=year))
        return self

    def with_min_citations(self, count: int) -> PaperFilter:
        """Set minimum citations."""
        self._specifications.append(CitationSpecification(min_citations=count))
        return self

    def in_venue(self, *venues: str, exact: bool = False) -> PaperFilter:
        """Set venue filter."""
        self._specifications.append(VenueSpecification(venues=list(venues), exact_match=exact))
        return self

    def by_author(self, *authors: str, match_all: bool = False) -> PaperFilter:
        """Set author filter."""
        self._specifications.append(AuthorSpecification(authors=list(authors), match_all=match_all))
        return self

    def build(self) -> Specification:
        """Build combined specification (AND of all)."""
        if not self._specifications:
            # Return a specification that always returns True
            return _TrueSpecification()

        result = self._specifications[0]
        for spec in self._specifications[1:]:
            result = AndSpecification(result, spec)
        return result

    def apply(self, papers: list[Paper]) -> list[Paper]:
        """Apply filter to list of papers.

        Args:
            papers: List of papers to filter

        Returns:
            Filtered list of papers
        """
        spec = self.build()
        return [p for p in papers if spec.is_satisfied_by(p)]


class _TrueSpecification:
    """Internal specification that always returns True."""

    def is_satisfied_by(self, paper: Paper) -> bool:
        return True

    def and_(self, other: Specification) -> Specification:
        return other

    def or_(self, other: Specification) -> Specification:
        return self

    def not_(self) -> Specification:
        return _FalseSpecification()


class _FalseSpecification:
    """Internal specification that always returns False."""

    def is_satisfied_by(self, paper: Paper) -> bool:
        return False

    def and_(self, other: Specification) -> Specification:
        return self

    def or_(self, other: Specification) -> Specification:
        return other

    def not_(self) -> Specification:
        return _TrueSpecification()
