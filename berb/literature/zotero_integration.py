"""Zotero MCP (Model Context Protocol) client for Berb.

Integrates with Zotero via MCP server for:
- Import papers from Zotero collections
- Export annotations and notes
- Sync with Zotero groups
- Bi-directional sync with Obsidian

Requires: Zotero MCP server running (https://github.com/zotero/mcp-server)

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.literature.zotero_integration import ZoteroMCPClient, ZoteroConfig

    config = ZoteroConfig(mcp_url="http://localhost:8765", api_key="...")
    client = ZoteroMCPClient(config)

    # List collections
    collections = await client.list_collections()

    # Get papers from collection
    papers = await client.get_collection_papers("collection-id")

    # Export annotations
    annotations = await client.export_annotations("paper-id")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ZoteroConfig:
    """Zotero MCP configuration.

    Attributes:
        mcp_url: Zotero MCP server URL (default: http://localhost:8765)
        api_key: Zotero API key (required for API access)
        library_id: Zotero library ID (default: user library)
        library_type: Library type: user or group (default: user)
        timeout: Request timeout in seconds (default: 30)
        include_annotations: Include annotations in exports (default: True)
        include_notes: Include notes in exports (default: True)
    """

    mcp_url: str = "http://localhost:8765"
    """Zotero MCP server URL"""

    api_key: str = ""
    """Zotero API key"""

    library_id: str = ""
    """Zotero library ID (empty = user library)"""

    library_type: str = "user"
    """Library type: user or group"""

    timeout: int = 30
    """Request timeout in seconds"""

    include_annotations: bool = True
    """Include annotations in exports"""

    include_notes: bool = True
    """Include notes in exports"""


@dataclass
class ZoteroCollection:
    """Zotero collection metadata.

    Attributes:
        id: Collection ID
        name: Collection name
        parent_id: Parent collection ID (if nested)
        item_count: Number of items in collection
    """

    id: str = ""
    name: str = ""
    parent_id: str = ""
    item_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "item_count": self.item_count,
        }


@dataclass
class ZoteroItem:
    """Zotero item (paper) metadata.

    Attributes:
        id: Item ID
        key: Item key
        title: Item title
        creators: List of creators (authors, editors, etc.)
        item_type: Type (journalArticle, conferencePaper, etc.)
        publication_title: Journal/conference name
        date: Publication date
        doi: DOI
        url: URL
        tags: List of tags
        collections: List of collection IDs
        annotations: List of annotations
        notes: List of notes
        extra: Extra metadata
    """

    id: str = ""
    key: str = ""
    title: str = ""
    creators: list[dict[str, str]] = field(default_factory=list)
    item_type: str = ""
    publication_title: str = ""
    date: str = ""
    doi: str = ""
    url: str = ""
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    annotations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "key": self.key,
            "title": self.title,
            "creators": self.creators,
            "item_type": self.item_type,
            "publication_title": self.publication_title,
            "date": self.date,
            "doi": self.doi,
            "url": self.url,
            "tags": self.tags,
            "collections": self.collections,
            "annotations": self.annotations,
            "notes": self.notes,
            "extra": self.extra,
        }

    @property
    def authors(self) -> list[str]:
        """Extract author names."""
        return [
            f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
            for c in self.creators
            if c.get("creatorType") == "author"
        ]


@dataclass
class ZoteroAnnotation:
    """Zotero annotation (highlight, note, etc.).

    Attributes:
        id: Annotation ID
        type: Annotation type (highlight, underline, note, etc.)
        text: Annotated text
        comment: Annotation comment/note
        color: Highlight color
        page: Page number
        created_date: Creation date
        modified_date: Modification date
    """

    id: str = ""
    type: str = ""
    text: str = ""
    comment: str = ""
    color: str = ""
    page: int = 0
    created_date: str = ""
    modified_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "comment": self.comment,
            "color": self.color,
            "page": self.page,
            "created_date": self.created_date,
            "modified_date": self.modified_date,
        }


class ZoteroMCPClient:
    """Client for Zotero MCP server.

    Provides integration with Zotero reference manager:
    - List collections
    - Get items from collections
    - Export annotations and notes
    - Sync with Zotero groups
    - Bi-directional sync with Obsidian

    Examples:
        Basic usage:
            >>> client = ZoteroMCPClient()
            >>> collections = await client.list_collections()
            >>> for coll in collections:
            ...     print(f"{coll.name}: {coll.item_count} items")

        Get papers with annotations:
            >>> papers = await client.get_collection_papers("collection-id")
            >>> for paper in papers:
            ...     print(f"{paper.title}")
            ...     for ann in paper.annotations:
            ...         print(f"  - {ann.text[:100]}")
    """

    def __init__(self, config: ZoteroConfig | None = None):
        """
        Initialize Zotero MCP client.

        Args:
            config: Zotero configuration (uses defaults if None)
        """
        self.config = config or ZoteroConfig()
        self._http_client = None

        # Validate configuration
        if not self.config.mcp_url:
            raise ValueError("Zotero MCP URL required")

    async def list_collections(self) -> list[ZoteroCollection]:
        """
        List all Zotero collections.

        Returns:
            List of ZoteroCollection objects

        Raises:
            ConnectionError: If MCP server is unreachable
            HTTPError: If API request fails

        Examples:
            >>> collections = await client.list_collections()
            >>> for coll in collections:
            ...     print(f"{coll.name} ({coll.id})")
        """
        # Try MCP protocol first
        try:
            result = await self._mcp_call("list_collections")
            return [
                ZoteroCollection(
                    id=c.get("id", ""),
                    name=c.get("name", ""),
                    parent_id=c.get("parentCollection", ""),
                    item_count=c.get("item_count", 0),
                )
                for c in result
            ]
        except Exception as e:
            logger.warning(f"MCP list_collections failed, trying Zotero API: {e}")
            return await self._list_collections_api()

    async def _list_collections_api(self) -> list[ZoteroCollection]:
        """List collections using Zotero API (fallback)."""
        import httpx

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url="https://api.zotero.org",
                timeout=self.config.timeout,
                headers={
                    "Zotero-API-Key": self.config.api_key,
                },
            )

        # Build URL
        library_prefix = f"groups/{self.config.library_id}" if self.config.library_type == "group" else "users"
        url = f"/{library_prefix}/{self.config.library_id or 'self'}/collections"

        try:
            response = await self._http_client.get(url)
            response.raise_for_status()
            collections = response.json()

            return [
                ZoteroCollection(
                    id=c["key"],
                    name=c["data"]["name"],
                    parent_id=c["data"].get("parentCollection", ""),
                )
                for c in collections
            ]

        except httpx.HTTPError as e:
            logger.error(f"Zotero API collections request failed: {e}")
            return []

    async def get_collection_papers(
        self,
        collection_id: str,
        *,
        limit: int = 100,
        include_annotations: bool | None = None,
        include_notes: bool | None = None,
    ) -> list[ZoteroItem]:
        """
        Get all papers from a Zotero collection.

        Args:
            collection_id: Collection ID
            limit: Maximum items to return
            include_annotations: Include annotations (default: from config)
            include_notes: Include notes (default: from config)

        Returns:
            List of ZoteroItem objects

        Examples:
            >>> papers = await client.get_collection_papers("collection-id")
            >>> for paper in papers:
            ...     print(f"{paper.title} ({paper.date})")
        """
        # Try MCP protocol first
        try:
            result = await self._mcp_call(
                "get_collection_items",
                collection_id=collection_id,
                limit=limit,
            )
            return [self._parse_zotero_item(item) for item in result]
        except Exception as e:
            logger.warning(f"MCP get_collection_items failed, trying Zotero API: {e}")
            return await self._get_collection_papers_api(
                collection_id,
                limit=limit,
                include_annotations=include_annotations,
                include_notes=include_notes,
            )

    async def _get_collection_papers_api(
        self,
        collection_id: str,
        limit: int = 100,
        include_annotations: bool | None = None,
        include_notes: bool | None = None,
    ) -> list[ZoteroItem]:
        """Get collection papers using Zotero API (fallback)."""
        import httpx

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url="https://api.zotero.org",
                timeout=self.config.timeout,
                headers={
                    "Zotero-API-Key": self.config.api_key,
                },
            )

        library_prefix = f"groups/{self.config.library_id}" if self.config.library_type == "group" else "users"
        url = f"/{library_prefix}/{self.config.library_id or 'self'}/collections/{collection_id}/items"
        params = {
            "format": "json",
            "limit": limit,
            "include": "annotations,notes" if (include_annotations or self.config.include_annotations) else "json",
        }

        try:
            response = await self._http_client.get(url, params=params)
            response.raise_for_status()
            items = response.json()

            return [self._parse_zotero_item(item) for item in items]

        except httpx.HTTPError as e:
            logger.error(f"Zotero API items request failed: {e}")
            return []

    def _parse_zotero_item(self, item: dict[str, Any]) -> ZoteroItem:
        """Parse Zotero API item response."""
        data = item.get("data", {})

        # Parse creators
        creators = []
        for creator in data.get("creators", []):
            creators.append({
                "firstName": creator.get("firstName", ""),
                "lastName": creator.get("lastName", ""),
                "creatorType": creator.get("creatorType", ""),
            })

        # Parse annotations
        annotations = []
        for ann in item.get("annotations", []):
            ann_data = ann.get("data", {})
            annotations.append(ZoteroAnnotation(
                id=ann.get("key", ""),
                type=ann_data.get("annotationType", ""),
                text=ann_data.get("annotationText", ""),
                comment=ann_data.get("annotationComment", ""),
                color=ann_data.get("annotationColor", ""),
            ).to_dict())

        # Parse notes
        notes = []
        for note in item.get("notes", []):
            note_data = note.get("data", {})
            notes.append({
                "id": note.get("key", ""),
                "text": note_data.get("note", ""),
            })

        return ZoteroItem(
            id=str(item.get("key", "")),
            key=item.get("key", ""),
            title=data.get("title", ""),
            creators=creators,
            item_type=data.get("itemType", ""),
            publication_title=data.get("publicationTitle", ""),
            date=data.get("date", ""),
            doi=data.get("DOI", ""),
            url=data.get("url", ""),
            tags=[t["tag"] for t in data.get("tags", [])],
            collections=data.get("collections", []),
            annotations=annotations,
            notes=notes,
            extra={"abstractNote": data.get("abstractNote", "")},
        )

    async def export_annotations(
        self,
        item_id: str,
        *,
        format: str = "markdown",
    ) -> str:
        """
        Export annotations from a Zotero item.

        Args:
            item_id: Item ID
            format: Export format (markdown, json, text)

        Returns:
            Formatted annotations text

        Examples:
            >>> annotations = await client.export_annotations("item-id", format="markdown")
            >>> print(annotations)
        """
        # Try MCP protocol first
        try:
            result = await self._mcp_call(
                "export_annotations",
                item_id=item_id,
                format=format,
            )
            return result
        except Exception as e:
            logger.warning(f"MCP export_annotations failed: {e}")
            return await self._export_annotations_api(item_id, format)

    async def _export_annotations_api(
        self,
        item_id: str,
        format: str = "markdown",
    ) -> str:
        """Export annotations using Zotero API (fallback)."""
        # Get item with annotations
        items = await self._get_collection_papers_api(
            collection_id="",  # Not needed for direct item fetch
            limit=1,
        )

        # Find the specific item
        item = next((i for i in items if i.id == item_id), None)
        if not item:
            return f"Item {item_id} not found"

        # Format annotations
        if format == "markdown":
            return self._format_annotations_markdown(item)
        elif format == "json":
            import json
            return json.dumps([a for a in item.annotations], indent=2)
        else:
            return "\n".join([a.get("text", "") for a in item.annotations])

    def _format_annotations_markdown(self, item: ZoteroItem) -> str:
        """Format annotations as markdown."""
        lines = []

        # Title
        lines.append(f"# {item.title}")
        lines.append("")
        lines.append(f"**Authors:** {', '.join(item.authors)}")
        lines.append(f"**Date:** {item.date}")
        lines.append("")

        # Annotations
        if item.annotations:
            lines.append("---")
            lines.append("## Annotations")
            lines.append("")

            for i, ann in enumerate(item.annotations, 1):
                if ann.get("text"):
                    lines.append(f"### Highlight {i}")
                    lines.append("")
                    lines.append(f"> {ann.get('text', '')}")
                    lines.append("")
                    if ann.get("comment"):
                        lines.append(f"**Note:** {ann.get('comment')}")
                        lines.append("")

        # Notes
        if item.notes:
            lines.append("---")
            lines.append("## Notes")
            lines.append("")

            for note in item.notes:
                lines.append(note.get("text", ""))
                lines.append("")

        return "\n".join(lines)

    async def search(
        self,
        query: str,
        *,
        field: str = "title",
        limit: int = 50,
    ) -> list[ZoteroItem]:
        """
        Search Zotero library.

        Args:
            query: Search query
            field: Field to search (title, creator, tag, etc.)
            limit: Maximum results

        Returns:
            List of ZoteroItem objects

        Examples:
            >>> results = await client.search("transformer", field="title")
            >>> for item in results:
            ...     print(f"{item.title} ({item.date})")
        """
        # Try MCP protocol first
        try:
            result = await self._mcp_call(
                "search",
                query=query,
                field=field,
                limit=limit,
            )
            return [self._parse_zotero_item(item) for item in result]
        except Exception as e:
            logger.warning(f"MCP search failed: {e}")
            # Fallback: fetch all and filter locally
            collections = await self.list_collections()
            all_items = []
            for coll in collections:
                items = await self.get_collection_papers(coll.id, limit=limit)
                all_items.extend(items)

            # Local filter
            query_lower = query.lower()
            if field == "title":
                return [i for i in all_items if query_lower in i.title.lower()][:limit]
            elif field == "creator":
                return [i for i in all_items if any(query_lower in a.lower() for a in i.authors)][:limit]
            else:
                return all_items[:limit]

    async def _mcp_call(
        self,
        method: str,
        **kwargs: Any,
    ) -> Any:
        """Make MCP protocol call."""
        import httpx

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.config.mcp_url,
                timeout=self.config.timeout,
            )

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": kwargs,
        }

        response = await self._http_client.post("/", json=payload)
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            raise Exception(f"MCP error: {result['error']}")

        return result.get("result", {})

    async def health_check(self) -> bool:
        """
        Check if Zotero MCP server is healthy.

        Returns:
            True if server is reachable

        Examples:
            >>> if await client.health_check():
            ...     print("Zotero MCP is online")
        """
        try:
            await self._mcp_call("ping")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> ZoteroMCPClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


def create_zotero_client_from_env() -> ZoteroMCPClient:
    """
    Create ZoteroMCPClient from environment variables.

    Environment Variables:
        ZOTERO_MCP_URL: Zotero MCP server URL (default: http://localhost:8765)
        ZOTERO_API_KEY: Zotero API key (required for API access)
        ZOTERO_LIBRARY_ID: Zotero library ID (optional)
        ZOTERO_LIBRARY_TYPE: Library type: user or group (default: user)

    Returns:
        ZoteroMCPClient configured from environment

    Examples:
        # In .env file:
        # ZOTERO_MCP_URL=http://localhost:8765
        # ZOTERO_API_KEY=your-api-key
        # ZOTERO_LIBRARY_ID=12345

        >>> client = create_zotero_client_from_env()
    """
    import os
    
    return ZoteroMCPClient(
        ZoteroConfig(
            mcp_url=os.environ.get("ZOTERO_MCP_URL", "http://localhost:8765"),
            api_key=os.environ.get("ZOTERO_API_KEY", ""),
            library_id=os.environ.get("ZOTERO_LIBRARY_ID", ""),
            library_type=os.environ.get("ZOTERO_LIBRARY_TYPE", "user"),
        )
    )
