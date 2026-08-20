"""Tests for P2 Specification pattern implementation."""

from __future__ import annotations

import pytest

from berb.literature.models import Author, Paper
from berb.literature.specification import (
    AndSpecification,
    AuthorSpecification,
    CitationSpecification,
    NotSpecification,
    OrSpecification,
    PaperFilter,
    VenueSpecification,
    YearSpecification,
    author_match,
    min_citations,
    venue_match,
    year_range,
)


@pytest.fixture
def sample_papers() -> list[Paper]:
    """Create sample papers for testing."""
    return [
        Paper(
            paper_id="1",
            title="Recent ML Advances",
            authors=[Author(name="Smith, J."), Author(name="Johnson, A.")],
            year=2023,
            abstract="Abstract 1",
            venue="NeurIPS 2023",
            citation_count=100,
            doi="10.1234/1",
            arxiv_id="arxiv:2301.001",
            url="https://example.com/1",
            source="openalex",
        ),
        Paper(
            paper_id="2",
            title="Old Paper",
            authors=[Author(name="Brown, B.")],
            year=2015,
            abstract="Abstract 2",
            venue="ICML 2015",
            citation_count=500,
            doi="10.1234/2",
            arxiv_id="arxiv:1501.001",
            url="https://example.com/2",
            source="openalex",
        ),
        Paper(
            paper_id="3",
            title="Low Citation Paper",
            authors=[Author(name="Smith, J.")],
            year=2022,
            abstract="Abstract 3",
            venue="Workshop 2022",
            citation_count=5,
            doi="10.1234/3",
            arxiv_id="arxiv:2201.001",
            url="https://example.com/3",
            source="openalex",
        ),
        Paper(
            paper_id="4",
            title="Nature Paper",
            authors=[Author(name="Johnson, A."), Author(name="Williams, C.")],
            year=2024,
            abstract="Abstract 4",
            venue="Nature",
            citation_count=50,
            doi="10.1234/4",
            arxiv_id="arxiv:2401.001",
            url="https://example.com/4",
            source="openalex",
        ),
    ]


class TestYearSpecification:
    """Test YearSpecification."""

    def test_year_in_range(self, sample_papers: list[Paper]):
        """Test paper within year range."""
        spec = YearSpecification(min_year=2020, max_year=2026)
        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[3]) is True

    def test_year_out_of_range(self, sample_papers: list[Paper]):
        """Test paper outside year range."""
        spec = YearSpecification(min_year=2020, max_year=2026)
        assert spec.is_satisfied_by(sample_papers[1]) is False

    def test_year_default_range(self, sample_papers: list[Paper]):
        """Test default year range accepts all."""
        spec = YearSpecification()
        for paper in sample_papers:
            assert spec.is_satisfied_by(paper) is True

    def test_year_convenience_function(self, sample_papers: list[Paper]):
        """Test year_range convenience function."""
        spec = year_range(2020, 2026)
        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[1]) is False


class TestCitationSpecification:
    """Test CitationSpecification."""

    def test_above_min_citations(self, sample_papers: list[Paper]):
        """Test paper above minimum citations."""
        spec = CitationSpecification(min_citations=50)
        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[1]) is True
        assert spec.is_satisfied_by(sample_papers[3]) is True

    def test_below_min_citations(self, sample_papers: list[Paper]):
        """Test paper below minimum citations."""
        spec = CitationSpecification(min_citations=50)
        assert spec.is_satisfied_by(sample_papers[2]) is False

    def test_zero_citations(self, sample_papers: list[Paper]):
        """Test zero minimum accepts all."""
        spec = CitationSpecification(min_citations=0)
        for paper in sample_papers:
            assert spec.is_satisfied_by(paper) is True

    def test_min_citations_convenience(self, sample_papers: list[Paper]):
        """Test min_citations convenience function."""
        spec = min_citations(100)
        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[2]) is False


class TestVenueSpecification:
    """Test VenueSpecification."""

    def test_venue_substring_match(self, sample_papers: list[Paper]):
        """Test venue substring matching."""
        spec = VenueSpecification(venues=["neurips"])
        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[1]) is False

    def test_venue_exact_match(self, sample_papers: list[Paper]):
        """Test venue exact matching."""
        spec = VenueSpecification(venues=["Nature"], exact_match=True)
        assert spec.is_satisfied_by(sample_papers[3]) is True
        assert spec.is_satisfied_by(sample_papers[0]) is False

    def test_venue_multiple_options(self, sample_papers: list[Paper]):
        """Test multiple venue options."""
        spec = VenueSpecification(venues=["neurips", "icml"])
        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[1]) is True
        assert spec.is_satisfied_by(sample_papers[2]) is False

    def test_venue_convenience(self, sample_papers: list[Paper]):
        """Test venue_match convenience function."""
        spec = venue_match("Nature", "Science", exact=True)
        assert spec.is_satisfied_by(sample_papers[3]) is True


class TestAuthorSpecification:
    """Test AuthorSpecification."""

    def test_author_any_match(self, sample_papers: list[Paper]):
        """Test matching any author."""
        spec = AuthorSpecification(authors=["Smith"])
        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[2]) is True
        assert spec.is_satisfied_by(sample_papers[1]) is False

    def test_author_all_match(self, sample_papers: list[Paper]):
        """Test matching all authors."""
        spec = AuthorSpecification(authors=["Smith", "Johnson"], match_all=True)
        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[3]) is False

    def test_author_convenience(self, sample_papers: list[Paper]):
        """Test author_match convenience function."""
        spec = author_match("Johnson", "Williams")
        assert spec.is_satisfied_by(sample_papers[3]) is True


class TestAndSpecification:
    """Test AndSpecification composition."""

    def test_and_both_satisfied(self, sample_papers: list[Paper]):
        """Test AND with both satisfied."""
        year_spec = YearSpecification(min_year=2020)
        citation_spec = CitationSpecification(min_citations=50)
        combined = AndSpecification(year_spec, citation_spec)

        assert combined.is_satisfied_by(sample_papers[0]) is True
        assert combined.is_satisfied_by(sample_papers[1]) is False  # Old
        assert combined.is_satisfied_by(sample_papers[2]) is False  # Low citations

    def test_and_chain(self, sample_papers: list[Paper]):
        """Test chaining AND specifications."""
        spec = (
            YearSpecification(min_year=2020)
            .and_(CitationSpecification(min_citations=50))
            .and_(VenueSpecification(venues=["neurips"]))
        )

        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[3]) is False  # Wrong venue


class TestOrSpecification:
    """Test OrSpecification composition."""

    def test_or_either_satisfied(self, sample_papers: list[Paper]):
        """Test OR with either satisfied."""
        year_spec = YearSpecification(min_year=2023)
        citation_spec = CitationSpecification(min_citations=100)
        combined = OrSpecification(year_spec, citation_spec)

        assert combined.is_satisfied_by(sample_papers[0]) is True  # Both
        assert combined.is_satisfied_by(sample_papers[1]) is True  # High citations
        assert combined.is_satisfied_by(sample_papers[3]) is True  # Recent
        assert combined.is_satisfied_by(sample_papers[2]) is False  # Neither


class TestNotSpecification:
    """Test NotSpecification negation."""

    def test_not_negates(self, sample_papers: list[Paper]):
        """Test NOT negates specification."""
        spec = NotSpecification(YearSpecification(min_year=2020))

        assert spec.is_satisfied_by(sample_papers[0]) is False  # Recent
        assert spec.is_satisfied_by(sample_papers[1]) is True  # Old

    def test_double_negation(self, sample_papers: list[Paper]):
        """Test double negation returns original."""
        spec = NotSpecification(NotSpecification(YearSpecification(min_year=2020)))

        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[1]) is False


class TestPaperFilter:
    """Test PaperFilter fluent API."""

    def test_filter_year_range(self, sample_papers: list[Paper]):
        """Test filtering by year range."""
        filtered = PaperFilter().from_year(2020).to_year(2026).apply(sample_papers)

        assert len(filtered) == 3
        assert filtered[0].paper_id == "1"
        assert filtered[1].paper_id == "3"
        assert filtered[2].paper_id == "4"

    def test_filter_combined(self, sample_papers: list[Paper]):
        """Test combined filtering."""
        filtered = (
            PaperFilter().from_year(2020).with_min_citations(50).apply(sample_papers)
        )

        assert len(filtered) == 2
        assert filtered[0].paper_id == "1"
        assert filtered[1].paper_id == "4"

    def test_filter_venue(self, sample_papers: list[Paper]):
        """Test venue filtering."""
        filtered = PaperFilter().in_venue("neurips", "nature").apply(sample_papers)

        assert len(filtered) == 2
        assert filtered[0].paper_id == "1"
        assert filtered[1].paper_id == "4"

    def test_filter_author(self, sample_papers: list[Paper]):
        """Test author filtering."""
        filtered = PaperFilter().by_author("Smith").apply(sample_papers)

        assert len(filtered) == 2
        assert filtered[0].paper_id == "1"
        assert filtered[1].paper_id == "3"

    def test_filter_empty(self, sample_papers: list[Paper]):
        """Test empty filter returns all."""
        filtered = PaperFilter().apply(sample_papers)

        assert len(filtered) == 4

    def test_filter_build_spec(self, sample_papers: list[Paper]):
        """Test building specification."""
        spec = PaperFilter().from_year(2020).with_min_citations(10).build()

        assert spec.is_satisfied_by(sample_papers[0]) is True
        assert spec.is_satisfied_by(sample_papers[2]) is False


class TestComplexSpecifications:
    """Test complex specification combinations."""

    def test_complex_query(self, sample_papers: list[Paper]):
        """Test complex query: (recent AND high citation) OR (nature paper)."""
        recent = YearSpecification(min_year=2020)
        influential = CitationSpecification(min_citations=100)
        nature = VenueSpecification(venues=["Nature"], exact_match=True)

        # (recent AND influential) OR nature
        spec = OrSpecification(
            AndSpecification(recent, influential),
            nature,
        )

        assert spec.is_satisfied_by(sample_papers[0]) is True  # Recent + influential
        assert spec.is_satisfied_by(sample_papers[1]) is False  # Old
        assert spec.is_satisfied_by(sample_papers[2]) is False  # Low citation
        assert spec.is_satisfied_by(sample_papers[3]) is True  # Nature paper

    def test_fluent_complex_query(self, sample_papers: list[Paper]):
        """Test complex query with fluent API."""
        # Recent papers with 50+ citations
        filtered = (
            PaperFilter()
            .from_year(2020)
            .to_year(2026)
            .with_min_citations(50)
            .apply(sample_papers)
        )

        assert len(filtered) == 2
        assert all(p.year >= 2020 for p in filtered)
        assert all(p.citation_count >= 50 for p in filtered)
