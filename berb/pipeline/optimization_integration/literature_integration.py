"""Literature FS Integration (Upgrade 4).

Integrates FileSystemLiteratureProcessor with pipeline stages 4-6:
- Stage 4: LITERATURE_COLLECT
- Stage 5: LITERATURE_SCREEN
- Stage 6: KNOWLEDGE_EXTRACT

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from berb.literature.fs_processor import (
    FileSystemLiteratureProcessor,
    LiteratureWorkspace,
)
from berb.literature.fs_query import FileSystemQueryEngine

logger = logging.getLogger(__name__)


class LiteratureFSIntegration:
    """Integrates FS-based literature processing with pipeline.
    
    Usage in pipeline:
        integration = LiteratureFSIntegration(workspace_root)
        workspace = await integration.organize_literature(papers)
        results = await integration.query_literature(query, workspace)
    """
    
    def __init__(
        self,
        workspace_root: Path,
        model: str = "gpt-4o",
    ):
        """Initialize literature FS integration.
        
        Args:
            workspace_root: Root directory for literature workspace
            model: LLM model for summarization/extraction
        """
        self.workspace_root = workspace_root
        self.model = model
        self.processor = FileSystemLiteratureProcessor(model=model)
        self._current_workspace: LiteratureWorkspace | None = None
        
        logger.info(f"Initialized LiteratureFSIntegration at {workspace_root}")
    
    async def organize_literature(
        self,
        papers: list[Any],
        project_id: str,
    ) -> LiteratureWorkspace:
        """Stage 4-6: Organize collected literature.
        
        Args:
            papers: List of papers from literature collection
            project_id: Project identifier
            
        Returns:
            Literature workspace
        """
        workspace_path = self.workspace_root / project_id / "literature"
        
        logger.info(f"Organizing {len(papers)} papers in {workspace_path}")
        
        self._current_workspace = await self.processor.organize_literature(
            papers=papers,
            workspace_root=workspace_path,
            cluster_topics=True,
            extract_summaries=True,
            extract_claims=True,
        )
        
        logger.info(
            f"Literature organized: {len(papers)} papers, "
            f"{self._current_workspace.by_topic} topics"
        )
        
        return self._current_workspace
    
    async def query_literature(
        self,
        query: str,
        top_k: int = 20,
    ) -> list[Any]:
        """Query organized literature.
        
        Args:
            query: Search query
            top_k: Maximum results
            
        Returns:
            List of relevant excerpts
        """
        if not self._current_workspace:
            raise ValueError("No workspace loaded. Call organize_literature first.")
        
        engine = FileSystemQueryEngine(self._current_workspace)
        results = await engine.search(query, top_k)
        
        logger.info(f"Query '{query}' returned {len(results)} results")
        
        return results
    
    async def get_summary(self, paper_id: str) -> str | None:
        """Get summary for specific paper.
        
        Args:
            paper_id: Paper identifier
            
        Returns:
            Summary text or None
        """
        if not self._current_workspace:
            return None
        
        return await self.processor.get_summary(
            self._current_workspace,
            paper_id,
        )
    
    async def get_claims(self, paper_id: str) -> list[dict] | None:
        """Get claims for specific paper.
        
        Args:
            paper_id: Paper identifier
            
        Returns:
            List of claims or None
        """
        if not self._current_workspace:
            return None
        
        return await self.processor.get_claims(
            self._current_workspace,
            paper_id,
        )
    
    async def get_statistics(self) -> dict[str, Any]:
        """Get literature workspace statistics.
        
        Returns:
            Statistics dictionary
        """
        if not self._current_workspace:
            return {"total_papers": 0}
        
        return await FileSystemQueryEngine(
            self._current_workspace
        ).get_statistics()


async def organize_literature_stage(
    papers: list[Any],
    workspace_root: Path,
    project_id: str,
    model: str = "gpt-4o",
) -> LiteratureWorkspace:
    """Stage 4-6 integration: Organize literature.
    
    Args:
        papers: Papers from literature collection
        workspace_root: Workspace root directory
        project_id: Project identifier
        model: LLM model
        
    Returns:
        Literature workspace
    """
    integration = LiteratureFSIntegration(workspace_root, model)
    return await integration.organize_literature(papers, project_id)
