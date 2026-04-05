"""File System Query Engine for Literature.

Companion to FileSystemLiteratureProcessor for querying
organized literature using file system operations.

Based on "Coding Agents as Long-Context Processors" (arXiv:2603.20432):
"Use grep/search tools instead of LLM attention to find relevant content.
Then pass only relevant excerpts to LLM."

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.literature.fs_query import FileSystemQueryEngine
    
    engine = FileSystemQueryEngine(workspace)
    results = await engine.search("graph neural networks", top_k=10)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from berb.literature.fs_processor import LiteratureWorkspace, RelevantExcerpt

logger = logging.getLogger(__name__)


@dataclass
class QueryConfig:
    """Query configuration.
    
    Attributes:
        use_grep: Use grep for text search
        use_index: Use metadata index for filtering
        use_embeddings: Use semantic search (if available)
        min_relevance: Minimum relevance score
        max_results: Maximum results to return
    """
    use_grep: bool = True
    use_index: bool = True
    use_embeddings: bool = False
    min_relevance: float = 0.0
    max_results: int = 50


class FileSystemQueryEngine:
    """Query engine for file-system-organized literature.
    
    Features:
    - Grep-based text search
    - Metadata index filtering
    - Relevance scoring
    - Semantic search (optional, requires sentence-transformers)
    
    Usage:
        engine = FileSystemQueryEngine(workspace)
        results = await engine.search("query", top_k=10)
    """
    
    def __init__(
        self,
        workspace: LiteratureWorkspace,
        config: QueryConfig | None = None,
    ):
        """Initialize query engine.
        
        Args:
            workspace: Literature workspace
            config: Query configuration
        """
        self.workspace = workspace
        self.config = config or QueryConfig()
        self._index_cache: dict[str, Any] | None = None
        logger.info(f"Initialized FileSystemQueryEngine for {workspace.root}")
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[RelevantExcerpt]:
        """Search literature using file system operations.
        
        Args:
            query: Search query
            top_k: Maximum results to return
            
        Returns:
            List of relevant excerpts
        """
        results = []
        
        # Search using grep
        if self.config.use_grep:
            grep_results = await self._grep_search(query)
            results.extend(grep_results)
        
        # Search using index
        if self.config.use_index:
            index_results = await self._index_search(query)
            results.extend(index_results)
        
        # Deduplicate and rank
        ranked = self._rank_results(results, query)
        
        # Filter by relevance
        filtered = [
            r for r in ranked
            if r.relevance_score >= self.config.min_relevance
        ]
        
        # Limit results
        return filtered[:top_k]
    
    async def _grep_search(
        self,
        query: str,
    ) -> list[RelevantExcerpt]:
        """Search using grep.
        
        Args:
            query: Search query
            
        Returns:
            List of excerpts
        """
        import asyncio
        
        results = []
        
        # Search in summaries
        if self.workspace.summaries.exists():
            summaries_results = await self._grep_directory(
                query,
                self.workspace.summaries,
                "*.md",
            )
            results.extend(summaries_results)
        
        # Search in claims
        if self.workspace.claims.exists():
            claims_results = await self._grep_directory(
                query,
                self.workspace.claims,
                "*.json",
            )
            results.extend(claims_results)
        
        # Search in methods
        if self.workspace.methods.exists():
            methods_results = await self._grep_directory(
                query,
                self.workspace.methods,
                "*.md",
            )
            results.extend(methods_results)
        
        logger.debug(f"Grep search found {len(results)} results")
        return results
    
    async def _grep_directory(
        self,
        query: str,
        directory: Path,
        pattern: str = "*.md",
    ) -> list[RelevantExcerpt]:
        """Grep search in directory.
        
        Args:
            query: Search query
            directory: Directory to search
            pattern: File pattern
            
        Returns:
            List of excerpts
        """
        results = []
        
        # Use Python glob for cross-platform compatibility
        files = list(directory.rglob(pattern))
        
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
                
                # Case-insensitive search
                matches = re.finditer(
                    re.escape(query),
                    content,
                    re.IGNORECASE,
                )
                
                for match in matches:
                    # Get context around match
                    start = max(0, match.start() - 100)
                    end = min(len(content), match.end() + 100)
                    excerpt = content[start:end]
                    
                    # Extract paper ID from file path
                    paper_id = file_path.stem
                    
                    results.append(RelevantExcerpt(
                        paper_id=paper_id,
                        content=excerpt,
                        relevance_score=0.5,  # Will be ranked later
                        source_file=file_path,
                        metadata={"match_position": match.start()},
                    ))
                    
            except Exception as e:
                logger.warning(f"Failed to search {file_path}: {e}")
        
        return results
    
    async def _index_search(
        self,
        query: str,
    ) -> list[RelevantExcerpt]:
        """Search using metadata index.
        
        Args:
            query: Search query
            
        Returns:
            List of excerpts
        """
        results = []
        
        # Load index
        index = await self._load_index()
        
        if not index:
            return results
        
        # Search in titles and abstracts
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for paper in index.get("papers", []):
            title = paper.get("title", "").lower()
            # Check for word overlap
            title_words = set(title.split())
            overlap = len(query_words & title_words)
            
            if overlap > 0 or query_lower in title:
                relevance = overlap / max(len(query_words), 1)
                
                results.append(RelevantExcerpt(
                    paper_id=paper.get("id", ""),
                    content=f"{paper.get('title', '')}\n{paper.get('abstract', '')}",
                    relevance_score=relevance,
                    source_file=self.workspace.index_path,
                    metadata={"paper_metadata": paper},
                ))
        
        logger.debug(f"Index search found {len(results)} results")
        return results
    
    async def _load_index(self) -> dict[str, Any] | None:
        """Load metadata index.
        
        Returns:
            Index data or None
        """
        if self._index_cache:
            return self._index_cache
        
        if not self.workspace.index_path.exists():
            return None
        
        try:
            with open(self.workspace.index_path, encoding="utf-8") as f:
                self._index_cache = json.load(f)
            return self._index_cache
        except Exception as e:
            logger.warning(f"Failed to load index: {e}")
            return None
    
    def _rank_results(
        self,
        results: list[RelevantExcerpt],
        query: str,
    ) -> list[RelevantExcerpt]:
        """Rank and deduplicate results.
        
        Args:
            results: Search results
            query: Original query
            
        Returns:
            Ranked results
        """
        # Group by paper_id
        by_paper: dict[str, list[RelevantExcerpt]] = {}
        for result in results:
            if result.paper_id not in by_paper:
                by_paper[result.paper_id] = []
            by_paper[result.paper_id].append(result)
        
        # Rank papers
        ranked = []
        query_words = set(query.lower().split())
        
        for paper_id, excerpts in by_paper.items():
            # Calculate relevance
            max_relevance = max(e.relevance_score for e in excerpts)
            
            # Boost for multiple matches
            match_count = len(excerpts)
            boost = min(0.3, match_count * 0.05)
            
            # Boost for query word matches in content
            for excerpt in excerpts:
                content_words = set(excerpt.content.lower().split())
                overlap = len(query_words & content_words)
                word_boost = overlap / max(len(query_words), 1) * 0.2
                max_relevance = max(max_relevance, word_boost)
            
            final_relevance = min(1.0, max_relevance + boost)
            
            # Create combined excerpt
            combined_content = "\n...\n".join(e.content for e in excerpts[:3])
            
            ranked.append(RelevantExcerpt(
                paper_id=paper_id,
                content=combined_content,
                relevance_score=final_relevance,
                source_file=excerpts[0].source_file,
                metadata={"match_count": match_count},
            ))
        
        # Sort by relevance
        ranked.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return ranked
    
    async def get_paper_info(
        self,
        paper_id: str,
    ) -> dict[str, Any] | None:
        """Get paper information from index.
        
        Args:
            paper_id: Paper identifier
            
        Returns:
            Paper metadata or None
        """
        index = await self._load_index()
        
        if not index:
            return None
        
        for paper in index.get("papers", []):
            if paper.get("id") == paper_id:
                return paper
        
        return None
    
    async def get_related_papers(
        self,
        paper_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get papers related to a specific paper.
        
        Args:
            paper_id: Paper identifier
            limit: Maximum related papers to return
            
        Returns:
            List of related paper metadata
        """
        index = await self._load_index()
        
        if not index:
            return []
        
        # Find the paper
        target_paper = None
        for paper in index.get("papers", []):
            if paper.get("id") == paper_id:
                target_paper = paper
                break
        
        if not target_paper:
            return []
        
        # Get topics
        target_topics = set(target_paper.get("topics", []))
        target_year = target_paper.get("year")
        
        # Score other papers
        scored = []
        for paper in index.get("papers", []):
            if paper.get("id") == paper_id:
                continue
            
            score = 0.0
            
            # Topic overlap
            paper_topics = set(paper.get("topics", []))
            topic_overlap = len(target_topics & paper_topics)
            score += topic_overlap * 0.3
            
            # Year proximity
            paper_year = paper.get("year")
            if paper_year and target_year:
                year_diff = abs(paper_year - target_year)
                score += max(0, 0.2 - year_diff * 0.02)
            
            # Citation count
            citations = paper.get("citation_count", 0)
            score += min(0.3, citations / 100)
            
            scored.append((score, paper))
        
        # Sort and return top
        scored.sort(key=lambda x: x[0], reverse=True)
        return [paper for _, paper in scored[:limit]]
    
    async def browse_by_topic(
        self,
        topic: str,
    ) -> list[dict[str, Any]]:
        """Browse papers by topic cluster.
        
        Args:
            topic: Topic name or cluster ID
            
        Returns:
            List of paper metadata
        """
        # Check if topic directory exists
        topic_dir = self.workspace.by_topic / topic
        
        if not topic_dir.exists():
            # Try to find matching cluster
            for cluster_dir in self.workspace.by_topic.iterdir():
                if cluster_dir.is_dir() and topic.lower() in cluster_dir.name.lower():
                    topic_dir = cluster_dir
                    break
        
        if not topic_dir.exists():
            return []
        
        # Load papers from cluster
        papers = []
        for md_file in topic_dir.glob("*.md"):
            if md_file.name.endswith("_info.md"):
                continue
            
            content = md_file.read_text(encoding="utf-8")
            
            # Extract title
            title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else md_file.stem
            
            papers.append({
                "id": md_file.stem,
                "title": title,
                "source_file": str(md_file),
            })
        
        return papers
    
    async def browse_by_year(
        self,
        year: int | str,
    ) -> list[dict[str, Any]]:
        """Browse papers by year.
        
        Args:
            year: Year or "unknown"
            
        Returns:
            List of paper metadata
        """
        year_dir = self.workspace.by_year / str(year)
        
        if not year_dir.exists():
            return []
        
        papers = []
        for md_file in year_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            
            # Extract title
            title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else md_file.stem
            
            papers.append({
                "id": md_file.stem,
                "title": title,
                "source_file": str(md_file),
            })
        
        return papers
    
    async def get_statistics(self) -> dict[str, Any]:
        """Get workspace statistics.
        
        Returns:
            Statistics dictionary
        """
        index = await self._load_index()
        
        if not index:
            return {"total_papers": 0}
        
        stats = {
            "total_papers": index.get("total_papers", 0),
            "topic_clusters": len(list(self.workspace.by_topic.iterdir())) if self.workspace.by_topic.exists() else 0,
            "summaries": len(list(self.workspace.summaries.glob("*.md"))) if self.workspace.summaries.exists() else 0,
            "claims": len(list(self.workspace.claims.glob("*.json"))) if self.workspace.claims.exists() else 0,
            "methods": len(list(self.workspace.methods.glob("*.md"))) if self.workspace.methods.exists() else 0,
        }
        
        return stats


__all__ = [
    "FileSystemQueryEngine",
    "QueryConfig",
]
