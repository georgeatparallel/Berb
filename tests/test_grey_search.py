"""Unit tests for grey literature search."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from berb.literature.grey_search import (
    GreyLiteratureSearch,
    GreyLiteratureResult,
    BioRxivClient,
    MedRxivClient,
    ClinicalTrialsClient,
    ZenodoClient,
)


class TestGreyLiteratureResult:
    """Test GreyLiteratureResult dataclass."""

    def test_create_result(self):
        """Test creating a grey literature result."""
        result = GreyLiteratureResult(
            title="Test Paper",
            authors=["Author 1", "Author 2"],
            year=2024,
            source="bioRxiv",
            url="https://biorxiv.org/...",
            doi="10.1101/123456",
            abstract="Test abstract",
            source_type="preprint",
            domain="biology",
        )

        assert result.title == "Test Paper"
        assert len(result.authors) == 2
        assert result.source == "bioRxiv"


class TestBioRxivClient:
    """Test BioRxivClient class."""

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful bioRxiv search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "Test Paper",
                    "authors": "Author 1; Author 2",
                    "date": "2024-01-15",
                    "link": "https://biorxiv.org/...",
                    "doi": "10.1101/123456",
                    "abstract": "Test abstract",
                    "version": "1",
                    "category": "Genomics",
                }
            ]
        }

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = BioRxivClient()
            results = await client.search("CRISPR", limit=10)

        assert len(results) == 1
        assert results[0].title == "Test Paper"
        assert results[0].source == "bioRxiv"
        assert results[0].domain == "biology"

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """Test bioRxiv search with no results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"collection": []}

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = BioRxivClient()
            results = await client.search("nonexistent query", limit=10)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_with_date_range(self):
        """Test bioRxiv search with date range."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"collection": []}

        with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            client = BioRxivClient()
            await client.search(
                "test",
                limit=10,
                date_from="2023-01-01",
                date_to="2024-12-31",
            )

        # Verify date params were passed
        call_args = mock_get.call_args[1]["params"]
        assert "from" in call_args
        assert "to" in call_args


class TestMedRxivClient:
    """Test MedRxivClient class."""

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful medRxiv search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "collection": [
                {
                    "title": "Clinical Study",
                    "authors": "Author 1; Author 2",
                    "date": "2024-02-20",
                    "link": "https://medrxiv.org/...",
                    "doi": "10.1101/789012",
                    "abstract": "Medical abstract",
                    "category": "Epidemiology",
                }
            ]
        }

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = MedRxivClient()
            results = await client.search("COVID-19", limit=10)

        assert len(results) == 1
        assert results[0].source == "medRxiv"
        assert results[0].domain == "medicine"


class TestClinicalTrialsClient:
    """Test ClinicalTrialsClient class."""

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful clinical trials search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "briefTitle": "Test Trial",
                            "nctId": "NCT0123456",
                            "briefSummary": "Trial summary",
                        },
                        "statusModule": {
                            "overallStatus": "COMPLETED",
                            "startDate": "2023-01-01",
                        },
                        "designModule": {
                            "phases": ["Phase 3"],
                        },
                        "armsInterventionsModule": {
                            "interventions": ["Drug A", "Placebo"],
                        },
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = ClinicalTrialsClient()
            results = await client.search("diabetes", limit=10)

        assert len(results) == 1
        assert results[0].source == "ClinicalTrials.gov"
        assert results[0].source_type == "trial"
        assert results[0].metadata["nct_id"] == "NCT0123456"

    @pytest.mark.asyncio
    async def test_search_with_status_filter(self):
        """Test clinical trials search with status filter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"studies": []}

        with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            client = ClinicalTrialsClient()
            await client.search("cancer", status="RECRUITING")

        # Verify status filter was passed
        call_args = mock_get.call_args[1]["params"]
        assert "filter.overallStatus" in call_args


class TestZenodoClient:
    """Test ZenodoClient class."""

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful Zenodo search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "hits": {
                "hits": [
                    {
                        "metadata": {
                            "title": "Research Dataset",
                            "creators": [{"name": "Author 1"}, {"name": "Author 2"}],
                            "publication_date": "2024-03-15",
                            "description": "Dataset description",
                            "resource_type": {"type": "dataset"},
                            "license": {"id": "CC-BY-4.0"},
                        },
                        "links": {"self_html": "https://zenodo.org/..."},
                        "doi": "10.5281/zenodo.123456",
                        "stats": {"citations": 5},
                    }
                ]
            }
        }

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            client = ZenodoClient()
            results = await client.search("machine learning", limit=10)

        assert len(results) == 1
        assert results[0].source == "Zenodo"
        assert len(results[0].authors) == 2
        assert results[0].source_type == "dataset"

    @pytest.mark.asyncio
    async def test_search_with_api_key(self):
        """Test Zenodo search with API key."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"hits": {"hits": []}}

        with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            client = ZenodoClient(api_key="test_key")
            await client.search("test")

        # Verify API key was passed in headers
        call_args = mock_get.call_args[1]
        assert "headers" in call_args
        assert "Authorization" in call_args["headers"]


class TestGreyLiteratureSearch:
    """Test GreyLiteratureSearch class."""

    @pytest.mark.asyncio
    async def test_search_all_domains(self):
        """Test search across all domains."""
        search = GreyLiteratureSearch()

        # Mock all clients
        search._biorxiv.search = AsyncMock(return_value=[])
        search._medrxiv.search = AsyncMock(return_value=[])
        search._clinical.search = AsyncMock(return_value=[])
        search._zenodo.search = AsyncMock(return_value=[])

        results = await search.search("test query", domain="all", limit=100)

        # All clients should be called
        assert search._biorxiv.search.called
        assert search._medrxiv.search.called
        assert search._clinical.search.called
        assert search._zenodo.search.called

    @pytest.mark.asyncio
    async def test_search_biology_domain(self):
        """Test search for biology domain."""
        with (
            patch("berb.literature.grey_search.BioRxivClient") as mock_biorxiv,
            patch("berb.literature.grey_search.ZenodoClient") as mock_zenodo,
        ):
            mock_biorxiv.return_value.search = AsyncMock(return_value=[])
            mock_zenodo.return_value.search = AsyncMock(return_value=[])

            search = GreyLiteratureSearch()
            results = await search.search("genetics", domain="biology")

            # Only biology sources should be called
            assert mock_biorxiv.return_value.search.called
            assert mock_zenodo.return_value.search.called

    @pytest.mark.asyncio
    async def test_search_medicine_domain(self):
        """Test search for medicine domain."""
        with (
            patch("berb.literature.grey_search.MedRxivClient") as mock_medrxiv,
            patch("berb.literature.grey_search.ClinicalTrialsClient") as mock_clinical,
            patch("berb.literature.grey_search.ZenodoClient") as mock_zenodo,
        ):
            mock_medrxiv.return_value.search = AsyncMock(return_value=[])
            mock_clinical.return_value.search = AsyncMock(return_value=[])
            mock_zenodo.return_value.search = AsyncMock(return_value=[])

            search = GreyLiteratureSearch()
            results = await search.search("clinical trial", domain="medicine")

            # Only medicine sources should be called
            assert mock_medrxiv.return_value.search.called
            assert mock_clinical.return_value.search.called
            assert mock_zenodo.return_value.search.called

    @pytest.mark.asyncio
    async def test_search_with_source_filter(self):
        """Test search with specific sources."""
        with (
            patch("berb.literature.grey_search.BioRxivClient") as mock_biorxiv,
            patch("berb.literature.grey_search.MedRxivClient") as mock_medrxiv,
        ):
            mock_biorxiv.return_value.search = AsyncMock(return_value=[])
            mock_medrxiv.return_value.search = AsyncMock(return_value=[])

            search = GreyLiteratureSearch()
            results = await search.search(
                "test",
                include_sources=["biorxiv", "medrxiv"],
            )

            assert mock_biorxiv.return_value.search.called
            assert mock_medrxiv.return_value.search.called

    @pytest.mark.asyncio
    async def test_search_handles_errors_gracefully(self):
        """Test that search continues even if one source fails."""
        with (
            patch("berb.literature.grey_search.BioRxivClient") as mock_biorxiv,
            patch("berb.literature.grey_search.ZenodoClient") as mock_zenodo,
        ):
            # bioRxiv fails
            mock_biorxiv.return_value.search = AsyncMock(side_effect=Exception("API error"))
            # Zenodo succeeds
            mock_zenodo.return_value.search = AsyncMock(
                return_value=[
                    GreyLiteratureResult(
                        title="Test",
                        authors=[],
                        year=2024,
                        source="Zenodo",
                        url="...",
                    )
                ]
            )

            search = GreyLiteratureSearch()
            results = await search.search("test", domain="all")

            # Should still get results from other sources
            assert len(results) > 0

    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """Test getting statistics."""
        search = GreyLiteratureSearch()
        stats = await search.get_statistics()

        assert "sources" in stats
        assert "domains" in stats
        assert "source_types" in stats
        assert len(stats["sources"]) == 4

    def test_get_sources_for_domain(self):
        """Test domain-specific source selection."""
        search = GreyLiteratureSearch()

        biology_sources = search._get_sources_for_domain("biology")
        assert "biorxiv" in biology_sources
        assert "clinicaltrials" not in biology_sources

        medicine_sources = search._get_sources_for_domain("medicine")
        assert "medrxiv" in medicine_sources
        assert "clinicaltrials" in medicine_sources
