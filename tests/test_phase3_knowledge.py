"""Tests for Phase 3: Knowledge Base (Obsidian, Zotero).

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import tempfile
from pathlib import Path

from berb.knowledge.obsidian_export import (
    ObsidianExporter,
    ObsidianConfig,
    ExportResult,
    create_exporter_from_env,
)
from berb.literature.zotero_integration import (
    ZoteroMCPClient,
    ZoteroConfig,
    ZoteroCollection,
    ZoteroItem,
    ZoteroAnnotation,
    create_zotero_client_from_env,
)


# ============== Obsidian Export Tests ==============

class TestObsidianConfig:
    """Test Obsidian configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = ObsidianConfig()
        assert config.vault_path == ""
        assert config.knowledge_folder == "Knowledge"
        assert config.results_folder == "Results/Reports"
        assert config.include_frontmatter is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ObsidianConfig(
            vault_path="/tmp/test-vault",
            knowledge_folder="Cards",
            auto_export=True,
        )
        assert config.vault_path == "/tmp/test-vault"
        assert config.knowledge_folder == "Cards"
        assert config.auto_export is True


class TestExportResult:
    """Test ExportResult dataclass."""

    def test_default_result(self):
        """Test default export result."""
        result = ExportResult()
        assert result.success is True
        assert result.created is True
        assert result.word_count == 0

    def test_to_dict(self):
        """Test result to_dict method."""
        result = ExportResult(
            success=True,
            file_path="/tmp/test.md",
            word_count=100,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["file_path"] == "/tmp/test.md"
        assert d["word_count"] == 100


class TestObsidianExporter:
    """Test ObsidianExporter."""

    @pytest.fixture
    def temp_vault(self):
        """Create temporary vault directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_exporter_initialization(self, temp_vault):
        """Test exporter initialization."""
        config = ObsidianConfig(vault_path=str(temp_vault))
        exporter = ObsidianExporter(config)
        assert exporter.vault == temp_vault

    def test_exporter_creates_folders(self, temp_vault):
        """Test folder creation."""
        config = ObsidianConfig(vault_path=str(temp_vault))
        exporter = ObsidianExporter(config)

        # Check folders exist
        assert (temp_vault / "Knowledge").exists()
        assert (temp_vault / "Results/Reports").exists()
        assert (temp_vault / "Writing").exists()
        assert (temp_vault / "Papers").exists()

    def test_exporter_missing_vault_path(self):
        """Test error on missing vault path."""
        with pytest.raises(ValueError, match="vault path required"):
            ObsidianExporter(ObsidianConfig())

    @pytest.mark.asyncio
    async def test_export_knowledge_card(self, temp_vault):
        """Test knowledge card export."""
        config = ObsidianConfig(vault_path=str(temp_vault))
        exporter = ObsidianExporter(config)

        card = {
            "id": "kc-001",
            "title": "Test Knowledge Card",
            "content": "This is test content.",
            "tags": ["test", "example"],
        }

        result = await exporter.export_knowledge_card(card)

        assert result.success is True
        assert result.word_count > 0
        assert Path(result.file_path).exists()

        # Check content
        content = Path(result.file_path).read_text()
        assert "Test Knowledge Card" in content
        assert "test content" in content.lower()

    @pytest.mark.asyncio
    async def test_export_experiment_report(self, temp_vault):
        """Test experiment report export."""
        config = ObsidianConfig(vault_path=str(temp_vault))
        exporter = ObsidianExporter(config)

        report = {
            "id": "exp-001",
            "title": "Test Experiment",
            "content": "# Results\n\nAccuracy: 0.95",
            "metrics": {"accuracy": 0.95, "f1": 0.93},
        }

        result = await exporter.export_experiment_report(report)

        assert result.success is True
        assert result.word_count > 0

    @pytest.mark.asyncio
    async def test_export_paper_draft(self, temp_vault):
        """Test paper draft export."""
        config = ObsidianConfig(vault_path=str(temp_vault))
        exporter = ObsidianExporter(config)

        draft = {
            "title": "Test Paper",
            "content": "# Introduction\n\nThis is a test paper.",
            "authors": ["John Doe", "Jane Smith"],
        }

        result = await exporter.export_paper_draft(draft)

        assert result.success is True
        assert result.word_count > 0

    @pytest.mark.asyncio
    async def test_export_with_links(self, temp_vault):
        """Test wiki link creation."""
        config = ObsidianConfig(vault_path=str(temp_vault))
        exporter = ObsidianExporter(config)

        draft = {
            "title": "Test Paper",
            "content": "See kc-001 for more info.",
            "references": ["kc-001"],
        }

        result = await exporter.export_paper_draft(draft, create_links=True)

        assert result.success is True
        content = Path(result.file_path).read_text()
        assert "[[kc-001]]" in content

    def test_slugify(self, temp_vault):
        """Test filename slugify."""
        config = ObsidianConfig(vault_path=str(temp_vault))
        exporter = ObsidianExporter(config)

        assert exporter._slugify("Test Title") == "test_title"
        assert exporter._slugify("Special!@#Chars") == "specialchars"
        assert len(exporter._slugify("A" * 100)) <= 50

    def test_generate_obsidian_url(self, temp_vault):
        """Test Obsidian URL generation."""
        config = ObsidianConfig(vault_path=str(temp_vault))
        exporter = ObsidianExporter(config)

        file_path = temp_vault / "Knowledge" / "test.md"
        url = exporter._generate_obsidian_url(file_path)

        assert url.startswith("obsidian://")
        assert "test.md" in url


class TestObsidianFrontmatter:
    """Test frontmatter generation."""

    @pytest.fixture
    def temp_vault(self):
        """Create temporary vault directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_frontmatter_included(self, temp_vault):
        """Test YAML frontmatter inclusion."""
        config = ObsidianConfig(
            vault_path=str(temp_vault),
            include_frontmatter=True,
        )
        exporter = ObsidianExporter(config)

        card = {
            "id": "kc-001",
            "title": "Test Card",
            "content": "Content",
            "tags": ["test"],
        }

        result = await exporter.export_knowledge_card(card)
        content = Path(result.file_path).read_text()

        assert content.startswith("---")
        assert "title: \"Test Card\"" in content
        assert "id: kc-001" in content
        assert "berb/test" in content

    @pytest.mark.asyncio
    async def test_frontmatter_disabled(self, temp_vault):
        """Test frontmatter disabled."""
        config = ObsidianConfig(
            vault_path=str(temp_vault),
            include_frontmatter=False,
        )
        exporter = ObsidianExporter(config)

        card = {
            "id": "kc-001",
            "title": "Test Card",
            "content": "Content",
        }

        result = await exporter.export_knowledge_card(card)
        content = Path(result.file_path).read_text()

        assert not content.startswith("---")


# ============== Zotero Integration Tests ==============

class TestZoteroConfig:
    """Test Zotero configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = ZoteroConfig()
        assert config.mcp_url == "http://localhost:8765"
        assert config.library_type == "user"
        assert config.include_annotations is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ZoteroConfig(
            mcp_url="http://custom:8765",
            api_key="test-key",
            library_id="12345",
            library_type="group",
        )
        assert config.mcp_url == "http://custom:8765"
        assert config.api_key == "test-key"
        assert config.library_type == "group"


class TestZoteroCollection:
    """Test ZoteroCollection dataclass."""

    def test_to_dict(self):
        """Test collection to_dict method."""
        coll = ZoteroCollection(
            id="coll-001",
            name="Test Collection",
            item_count=10,
        )
        d = coll.to_dict()
        assert d["id"] == "coll-001"
        assert d["name"] == "Test Collection"
        assert d["item_count"] == 10


class TestZoteroItem:
    """Test ZoteroItem dataclass."""

    def test_to_dict(self):
        """Test item to_dict method."""
        item = ZoteroItem(
            id="item-001",
            title="Test Paper",
            creators=[
                {"firstName": "John", "lastName": "Doe", "creatorType": "author"},
            ],
            date="2024-03-28",
        )
        d = item.to_dict()
        assert d["id"] == "item-001"
        assert d["title"] == "Test Paper"

    def test_authors_property(self):
        """Test authors extraction."""
        item = ZoteroItem(
            creators=[
                {"firstName": "John", "lastName": "Doe", "creatorType": "author"},
                {"firstName": "Jane", "lastName": "Smith", "creatorType": "author"},
                {"firstName": "Bob", "lastName": "Jones", "creatorType": "editor"},
            ]
        )
        authors = item.authors
        assert "John Doe" in authors
        assert "Jane Smith" in authors
        assert "Bob Jones" not in authors  # Editor, not author


class TestZoteroAnnotation:
    """Test ZoteroAnnotation dataclass."""

    def test_to_dict(self):
        """Test annotation to_dict method."""
        ann = ZoteroAnnotation(
            id="ann-001",
            type="highlight",
            text="Important finding",
            comment="Key result",
            color="yellow",
        )
        d = ann.to_dict()
        assert d["id"] == "ann-001"
        assert d["type"] == "highlight"
        assert d["text"] == "Important finding"


class TestZoteroMCPClient:
    """Test ZoteroMCPClient."""

    def test_client_initialization(self):
        """Test client initialization."""
        config = ZoteroConfig(mcp_url="http://localhost:8765")
        client = ZoteroMCPClient(config)
        assert client.config.mcp_url == "http://localhost:8765"

    def test_client_missing_url(self):
        """Test error on missing MCP URL."""
        with pytest.raises(ValueError, match="MCP URL required"):
            ZoteroMCPClient(ZoteroConfig(mcp_url=""))

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health check (mocked)."""
        client = ZoteroMCPClient()
        
        with patch.object(client, '_mcp_call', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {}
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check failure (mocked)."""
        client = ZoteroMCPClient()
        
        with patch.object(client, '_mcp_call', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("Connection failed")
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_list_collections_mcp(self):
        """Test list collections via MCP (mocked)."""
        client = ZoteroMCPClient()
        
        mock_collections = [
            {"id": "coll-001", "name": "Test Collection 1"},
            {"id": "coll-002", "name": "Test Collection 2"},
        ]
        
        with patch.object(client, '_mcp_call', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_collections
            collections = await client.list_collections()
            
            assert len(collections) == 2
            assert collections[0].name == "Test Collection 1"

    @pytest.mark.asyncio
    async def test_get_collection_papers(self):
        """Test get collection papers (mocked)."""
        client = ZoteroMCPClient()
        
        mock_items = [
            {
                "key": "item-001",
                "data": {
                    "title": "Test Paper 1",
                    "creators": [
                        {"firstName": "John", "lastName": "Doe", "creatorType": "author"}
                    ],
                }
            },
        ]
        
        with patch.object(client, '_mcp_call', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_items
            papers = await client.get_collection_papers("coll-001")
            
            assert len(papers) == 1
            assert papers[0].title == "Test Paper 1"
            assert "John Doe" in papers[0].authors


class TestZoteroAnnotationExport:
    """Test annotation export."""

    @pytest.mark.asyncio
    async def test_export_annotations_markdown(self):
        """Test markdown annotation export."""
        client = ZoteroMCPClient()
        
        # Mock item with annotations
        mock_item = ZoteroItem(
            id="item-001",
            title="Test Paper",
            creators=[
                {"firstName": "John", "lastName": "Doe", "creatorType": "author"},
            ],
            date="2024-03-28",
            annotations=[
                {
                    "text": "Important finding",
                    "comment": "Key result",
                }
            ],
        )
        
        # Mock the API call
        with patch.object(client, '_get_collection_papers_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = [mock_item]
            
            result = await client._export_annotations_api("item-001", format="markdown")
            
            assert "Test Paper" in result
            assert "Important finding" in result
            assert "Key result" in result


# ============== Environment Configuration Tests ==============

class TestEnvironmentConfig:
    """Test environment-based configuration."""

    def test_create_obsidian_exporter_from_env(self):
        """Test creating ObsidianExporter from environment."""
        with patch.dict('os.environ', {
            'OBSIDIAN_VAULT_PATH': '/tmp/test-vault',
            'OBSIDIAN_KNOWLEDGE_FOLDER': 'Cards',
        }, clear=False):
            exporter = create_exporter_from_env()
            assert exporter.config.vault_path == "/tmp/test-vault"
            assert exporter.config.knowledge_folder == "Cards"

    def test_create_zotero_client_from_env(self):
        """Test creating ZoteroMCPClient from environment."""
        with patch.dict('os.environ', {
            'ZOTERO_MCP_URL': 'http://custom:8765',
            'ZOTERO_API_KEY': 'test-key',
        }, clear=False):
            client = create_zotero_client_from_env()
            assert client.config.mcp_url == "http://custom:8765"
            assert client.config.api_key == "test-key"


# ============== Integration Tests ==============

class TestKnowledgeIntegration:
    """Test knowledge module integration."""

    def test_import_obsidian_exporter(self):
        """Test ObsidianExporter can be imported."""
        from berb.knowledge import ObsidianExporter, ObsidianConfig
        assert ObsidianExporter is not None
        assert ObsidianConfig is not None

    def test_import_zotero_client(self):
        """Test ZoteroMCPClient can be imported."""
        from berb.literature.zotero_integration import ZoteroMCPClient, ZoteroConfig
        assert ZoteroMCPClient is not None
        assert ZoteroConfig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
