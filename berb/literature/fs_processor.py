"""File-System-Based Literature Processing.

Based on "Coding Agents as Long-Context Processors" (arXiv:2603.20432):
"Externalize long-context processing from latent attention into explicit,
executable interactions. Let agents organize literature in file systems
and manipulate it using tools."

Result: +17.3% over SOTA on long-context benchmarks.

File Structure:
workspace/
├── by_topic/           # Clustered by theme
├── by_year/            # Chronological
├── by_relevance/       # Ranked by relevance score
├── summaries/          # One-paragraph per paper
├── claims/             # Extracted claims with citations
├── contradictions/     # Identified contradictions
├── methods/            # Method descriptions
└── index.json          # Searchable metadata index

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.literature.fs_processor import FileSystemLiteratureProcessor
    
    processor = FileSystemLiteratureProcessor()
    workspace = await processor.organize_literature(papers, workspace_path)
    
    # Query using file system tools
    relevant = await processor.query_literature(
        "graph neural networks",
        workspace,
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from berb.literature.models import Paper

logger = logging.getLogger(__name__)


@dataclass
class LiteratureWorkspace:
    """Literature workspace structure.
    
    Attributes:
        root: Root directory
        by_topic: Topic-clustered papers
        by_year: Chronologically organized papers
        by_relevance: Relevance-ranked papers
        summaries: Paper summaries
        claims: Extracted claims
        contradictions: Identified contradictions
        methods: Method descriptions
        index_path: Metadata index file
    """
    root: Path
    by_topic: Path
    by_year: Path
    by_relevance: Path
    summaries: Path
    claims: Path
    contradictions: Path
    methods: Path
    index_path: Path
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "root": str(self.root),
            "by_topic": str(self.by_topic),
            "by_year": str(self.by_year),
            "by_relevance": str(self.by_relevance),
            "summaries": str(self.summaries),
            "claims": str(self.claims),
            "contradictions": str(self.contradictions),
            "methods": str(self.methods),
            "index_path": str(self.index_path),
        }


@dataclass
class RelevantExcerpt:
    """Relevant excerpt from literature query.
    
    Attributes:
        paper_id: Source paper identifier
        content: Excerpt content
        relevance_score: Relevance score (0-1)
        source_file: Source file path
        metadata: Additional metadata
    """
    paper_id: str
    content: str
    relevance_score: float
    source_file: Path
    metadata: dict[str, Any] = field(default_factory=dict)


class FileSystemLiteratureProcessor:
    """Process large literature collections via file system operations.
    
    Based on "Coding Agents as Long-Context Processors" finding that
    agents outperform raw LLM attention for long-context tasks by +17.3%
    when they organize text in file systems and manipulate it using tools.
    
    Key Features:
    - Handles 200-400 papers without context window pressure
    - Better retrieval accuracy than attention-only approaches
    - Query via grep/search tools instead of LLM attention
    - Automatic clustering and organization
    - Incremental updates
    
    Usage:
        processor = FileSystemLiteratureProcessor()
        workspace = await processor.organize_literature(papers, Path("/workspace"))
        results = await processor.query_literature("query", workspace)
    """
    
    def __init__(self, model: str = "gpt-4o"):
        """Initialize FS literature processor.
        
        Args:
            model: LLM model for summarization/extraction
        """
        self.model = model
        logger.info(f"Initialized FileSystemLiteratureProcessor with {model}")
    
    async def organize_literature(
        self,
        papers: list[Paper],
        workspace_root: Path,
        cluster_topics: bool = True,
        extract_summaries: bool = True,
        extract_claims: bool = True,
    ) -> LiteratureWorkspace:
        """Create structured file system organization.
        
        Args:
            papers: List of papers to organize
            workspace_root: Root directory for workspace
            cluster_topics: Whether to cluster by topic
            extract_summaries: Whether to extract summaries
            extract_claims: Whether to extract claims
            
        Returns:
            Literature workspace structure
        """
        logger.info(f"Organizing {len(papers)} papers in {workspace_root}")
        
        # Create directory structure
        workspace = self._create_workspace(workspace_root)
        
        # Write index
        await self._write_index(papers, workspace.index_path)
        
        # Organize by topic
        if cluster_topics:
            await self._organize_by_topic(papers, workspace.by_topic)
        
        # Organize by year
        await self._organize_by_year(papers, workspace.by_year)
        
        # Organize by relevance
        await self._organize_by_relevance(papers, workspace.by_relevance)
        
        # Extract summaries
        if extract_summaries:
            await self._extract_summaries(papers, workspace.summaries)
        
        # Extract claims
        if extract_claims:
            await self._extract_claims(papers, workspace.claims)
        
        # Identify contradictions
        await self._identify_contradictions(papers, workspace.contradictions)
        
        # Extract methods
        await self._extract_methods(papers, workspace.methods)
        
        logger.info(
            f"Organized {len(papers)} papers in {workspace.root} "
            f"({workspace.by_topic}, {workspace.summaries}, etc.)"
        )
        
        return workspace
    
    def _create_workspace(self, root: Path) -> LiteratureWorkspace:
        """Create workspace directory structure.
        
        Args:
            root: Root directory
            
        Returns:
            Literature workspace
        """
        root.mkdir(parents=True, exist_ok=True)
        
        subdirs = {
            "by_topic": root / "by_topic",
            "by_year": root / "by_year",
            "by_relevance": root / "by_relevance",
            "summaries": root / "summaries",
            "claims": root / "claims",
            "contradictions": root / "contradictions",
            "methods": root / "methods",
            "index_path": root / "index.json",
        }
        
        for key, path in subdirs.items():
            if key != "index_path":
                path.mkdir(exist_ok=True)
        
        return LiteratureWorkspace(
            root=root,
            by_topic=subdirs["by_topic"],
            by_year=subdirs["by_year"],
            by_relevance=subdirs["by_relevance"],
            summaries=subdirs["summaries"],
            claims=subdirs["claims"],
            contradictions=subdirs["contradictions"],
            methods=subdirs["methods"],
            index_path=subdirs["index_path"],
        )
    
    async def _write_index(
        self,
        papers: list[Paper],
        index_path: Path,
    ) -> None:
        """Write searchable metadata index.
        
        Args:
            papers: List of papers
            index_path: Index file path
        """
        index = {
            "total_papers": len(papers),
            "created_at": str(Path.cwd()),
            "papers": [
                {
                    "id": p.paper_id if hasattr(p, 'paper_id') else p.get('id', ''),
                    "title": p.title if hasattr(p, 'title') else p.get('title', ''),
                    "authors": (
                        [str(a) for a in p.authors]
                        if hasattr(p, 'authors')
                        else p.get('authors', [])
                    ),
                    "year": p.year if hasattr(p, 'year') else p.get('year'),
                    "venue": p.venue if hasattr(p, 'venue') else p.get('venue', ''),
                    "citation_count": (
                        p.citation_count
                        if hasattr(p, 'citation_count')
                        else p.get('citation_count', 0)
                    ),
                    "doi": p.doi if hasattr(p, 'doi') else p.get('doi'),
                    "arxiv_id": p.arxiv_id if hasattr(p, 'arxiv_id') else p.get('arxiv_id'),
                    "relevance_score": getattr(p, 'relevance_score', 0.0),
                    "topics": getattr(p, 'topics', []),
                }
                for p in papers
            ],
        }
        
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Written index with {len(papers)} papers to {index_path}")
    
    async def _organize_by_topic(
        self,
        papers: list[Paper],
        topic_dir: Path,
    ) -> None:
        """Cluster papers by topic.
        
        Uses sentence transformers for embedding and KMeans for clustering.
        
        Args:
            papers: List of papers
            topic_dir: Topic directory
        """
        try:
            from sklearn.cluster import KMeans
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning("sklearn or sentence-transformers not installed, skipping topic clustering")
            # Fallback: organize by keywords
            await self._organize_by_keywords(papers, topic_dir)
            return
        
        # Get texts for embedding
        texts = []
        for paper in papers:
            title = paper.title if hasattr(paper, 'title') else paper.get('title', '')
            abstract = getattr(paper, 'abstract', paper.get('abstract', ''))
            texts.append(f"{title} {abstract}")
        
        # Embed
        logger.info(f"Embedding {len(texts)} papers for topic clustering...")
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(texts, show_progress_bar=True)
        
        # Cluster
        n_clusters = min(10, max(2, len(papers) // 5))
        logger.info(f"Clustering into {n_clusters} topics...")
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)
        
        # Write clusters
        for i, label in enumerate(labels):
            cluster_dir = topic_dir / f"cluster_{label}"
            cluster_dir.mkdir(exist_ok=True)
            
            paper = papers[i]
            paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
            paper_file = cluster_dir / f"{paper_id}.md"
            paper_file.write_text(self._paper_to_markdown(paper))
        
        # Write cluster info
        for label in range(n_clusters):
            cluster_papers = [papers[i] for i in range(len(papers)) if labels[i] == label]
            info_file = topic_dir / f"cluster_{label}_info.md"
            info_file.write_text(
                f"# Cluster {label}\n\n"
                f"**Papers:** {len(cluster_papers)}\n\n"
                f"Papers in this cluster:\n" +
                "\n".join([f"- {p.title if hasattr(p, 'title') else p.get('title', 'Unknown')}" for p in cluster_papers])
            )
        
        logger.info(f"Organized {len(papers)} papers into {n_clusters} topic clusters")
    
    async def _organize_by_keywords(
        self,
        papers: list[Paper],
        topic_dir: Path,
    ) -> None:
        """Fallback: organize by keywords if sklearn not available.
        
        Args:
            papers: List of papers
            topic_dir: Topic directory
        """
        # Simple keyword-based organization
        keywords = ["machine learning", "deep learning", "nlp", "vision", "other"]
        
        for keyword in keywords:
            (topic_dir / keyword).mkdir(exist_ok=True)
        
        for i, paper in enumerate(papers):
            title = (paper.title if hasattr(paper, 'title') else paper.get('title', '')).lower()
            
            assigned = False
            for keyword in keywords[:-1]:
                if keyword in title:
                    keyword_dir = topic_dir / keyword
                    paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
                    paper_file = keyword_dir / f"{paper_id}.md"
                    paper_file.write_text(self._paper_to_markdown(paper))
                    assigned = True
                    break
            
            if not assigned:
                other_dir = topic_dir / "other"
                paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
                paper_file = other_dir / f"{paper_id}.md"
                paper_file.write_text(self._paper_to_markdown(paper))
    
    async def _organize_by_year(
        self,
        papers: list[Paper],
        year_dir: Path,
    ) -> None:
        """Organize papers chronologically.
        
        Args:
            papers: List of papers
            year_dir: Year directory
        """
        by_year: dict[int, list[Paper]] = {}
        
        for paper in papers:
            year = paper.year if hasattr(paper, 'year') else paper.get('year')
            if year is None:
                year = 0  # Unknown year
            if year not in by_year:
                by_year[year] = []
            by_year[year].append(paper)
        
        for year, year_papers in sorted(by_year.items()):
            year_path = year_dir / (str(year) if year > 0 else "unknown")
            year_path.mkdir(exist_ok=True)
            
            for i, paper in enumerate(year_papers):
                paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
                paper_file = year_path / f"{paper_id}.md"
                paper_file.write_text(self._paper_to_markdown(paper))
        
        logger.debug(f"Organized papers by year in {year_dir}")
    
    async def _organize_by_relevance(
        self,
        papers: list[Paper],
        relevance_dir: Path,
    ) -> None:
        """Organize papers by relevance score.
        
        Args:
            papers: List of papers
            relevance_dir: Relevance directory
        """
        # Sort by relevance
        def get_relevance(p: Paper) -> float:
            return getattr(p, 'relevance_score', 0.0)
        
        sorted_papers = sorted(papers, key=get_relevance, reverse=True)
        
        # Create tiers
        tiers = {
            "high": relevance_dir / "high_relevance",
            "medium": relevance_dir / "medium_relevance",
            "low": relevance_dir / "low_relevance",
        }
        
        for path in tiers.values():
            path.mkdir(exist_ok=True)
        
        n = len(sorted_papers)
        for i, paper in enumerate(sorted_papers):
            if i < n * 0.2:
                tier = "high"
            elif i < n * 0.6:
                tier = "medium"
            else:
                tier = "low"
            
            paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
            paper_file = tiers[tier] / f"{paper_id}.md"
            paper_file.write_text(self._paper_to_markdown(paper))
        
        logger.debug(f"Organized {len(papers)} papers by relevance in {relevance_dir}")
    
    async def _extract_summaries(
        self,
        papers: list[Paper],
        summaries_dir: Path,
    ) -> None:
        """Extract one-paragraph summaries.
        
        Args:
            papers: List of papers
            summaries_dir: Summaries directory
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        for i, paper in enumerate(papers):
            title = paper.title if hasattr(paper, 'title') else paper.get('title', 'Unknown')
            abstract = getattr(paper, 'abstract', paper.get('abstract', 'No abstract'))
            
            prompt = f"""
Summarize this paper in one paragraph (3-4 sentences):

Title: {title}
Abstract: {abstract}

Provide a concise summary focusing on:
1. Main contribution
2. Key findings
3. Relevance to research
"""
            
            try:
                response = await client.chat(
                    messages=[{"role": "user", "content": prompt}],
                )
                
                paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
                summary_file = summaries_dir / f"{paper_id}.md"
                summary_file.write_text(f"# {title}\n\n{response.content}")
                
            except Exception as e:
                logger.warning(f"Failed to summarize paper {title}: {e}")
                # Fallback: use abstract as summary
                paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
                summary_file = summaries_dir / f"{paper_id}.md"
                summary_file.write_text(f"# {title}\n\n**Summary:** (Extraction failed)\n\n{abstract}")
        
        logger.info(f"Extracted summaries to {summaries_dir}")
    
    async def _extract_claims(
        self,
        papers: list[Paper],
        claims_dir: Path,
    ) -> None:
        """Extract claims with citations.
        
        Args:
            papers: List of papers
            claims_dir: Claims directory
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        for i, paper in enumerate(papers):
            title = paper.title if hasattr(paper, 'title') else paper.get('title', 'Unknown')
            abstract = getattr(paper, 'abstract', paper.get('abstract', 'No abstract'))
            
            prompt = f"""
Extract all claims from this paper. For each claim, include:
1. The claim statement
2. Evidence supporting it
3. Confidence level (high/medium/low)

Paper:
Title: {title}
Abstract: {abstract}

Format as JSON list:
[
    {{"claim": "...", "evidence": "...", "confidence": "high"}}
]
"""
            
            try:
                response = await client.chat(
                    messages=[{"role": "user", "content": prompt}],
                )
                
                # Parse JSON
                import json
                start = response.content.find("[")
                end = response.content.rfind("]") + 1
                if start >= 0 and end > start:
                    claims_json = response.content[start:end]
                    claims_data = json.loads(claims_json)
                else:
                    claims_data = {"raw": response.content}
                
                paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
                claims_file = claims_dir / f"{paper_id}.json"
                claims_file.write_text(json.dumps(claims_data, indent=2))
                
            except Exception as e:
                logger.warning(f"Failed to extract claims from paper {title}: {e}")
        
        logger.info(f"Extracted claims to {claims_dir}")
    
    async def _identify_contradictions(
        self,
        papers: list[Paper],
        contradictions_dir: Path,
    ) -> None:
        """Identify contradictions between papers.
        
        Args:
            papers: List of papers
            contradictions_dir: Contradictions directory
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        # Group by topic (simplified)
        topic_groups: dict[str, list[Paper]] = {}
        for paper in papers:
            topics = getattr(paper, 'topics', ['general'])
            if isinstance(topics, str):
                topics = [topics]
            for topic in topics:
                if topic not in topic_groups:
                    topic_groups[topic] = []
                topic_groups[topic].append(paper)
        
        # Find contradictions per topic
        for topic, topic_papers in topic_groups.items():
            if len(topic_papers) < 2:
                continue
            
            papers_text = "\n".join([
                f"- {p.title if hasattr(p, 'title') else p.get('title', 'Unknown')}: "
                f"{getattr(p, 'abstract', p.get('abstract', ''))[:200]}..."
                for p in topic_papers
            ])
            
            prompt = f"""
Identify contradictions between these papers on topic: {topic}

Papers:
{papers_text}

List any contradictory findings, claims, or interpretations.
"""
            
            try:
                response = await client.chat(
                    messages=[{"role": "user", "content": prompt}],
                )
                
                contradiction_file = contradictions_dir / f"{topic.replace('/', '_')}.md"
                contradiction_file.write_text(f"# Contradictions: {topic}\n\n{response.content}")
                
            except Exception as e:
                logger.warning(f"Failed to identify contradictions for topic {topic}: {e}")
        
        logger.info(f"Identified contradictions to {contradictions_dir}")
    
    async def _extract_methods(
        self,
        papers: list[Paper],
        methods_dir: Path,
    ) -> None:
        """Extract method descriptions.
        
        Args:
            papers: List of papers
            methods_dir: Methods directory
        """
        from berb.llm.client import get_llm_client
        
        client = get_llm_client(model=self.model)
        
        for i, paper in enumerate(papers):
            title = paper.title if hasattr(paper, 'title') else paper.get('title', 'Unknown')
            abstract = getattr(paper, 'abstract', paper.get('abstract', 'No abstract'))
            
            prompt = f"""
Extract the methodology from this paper:

Title: {title}
Abstract: {abstract}

Describe:
1. Research design
2. Data collection
3. Analysis methods
4. Key parameters

Format as structured markdown.
"""
            
            try:
                response = await client.chat(
                    messages=[{"role": "user", "content": prompt}],
                )
                
                paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', f'paper_{i}')
                method_file = methods_dir / f"{paper_id}.md"
                method_file.write_text(f"# {title}\n\n{response.content}")
                
            except Exception as e:
                logger.warning(f"Failed to extract methods from paper {title}: {e}")
        
        logger.info(f"Extracted methods to {methods_dir}")
    
    def _paper_to_markdown(self, paper: Paper) -> str:
        """Convert paper to markdown format.
        
        Args:
            paper: Paper object
            
        Returns:
            Markdown string
        """
        paper_id = paper.paper_id if hasattr(paper, 'paper_id') else paper.get('id', 'unknown')
        title = paper.title if hasattr(paper, 'title') else paper.get('title', 'Unknown')
        authors = (
            ', '.join(str(a) for a in paper.authors)
            if hasattr(paper, 'authors')
            else paper.get('authors', [])
        )
        year = paper.year if hasattr(paper, 'year') else paper.get('year', 'Unknown')
        venue = paper.venue if hasattr(paper, 'venue') else paper.get('venue', 'Unknown')
        citations = paper.citation_count if hasattr(paper, 'citation_count') else paper.get('citation_count', 0)
        doi = paper.doi if hasattr(paper, 'doi') else paper.get('doi', 'N/A')
        arxiv = paper.arxiv_id if hasattr(paper, 'arxiv_id') else paper.get('arxiv_id', 'N/A')
        abstract = getattr(paper, 'abstract', paper.get('abstract', 'No abstract available'))
        
        return f"""# {title}

**ID:** {paper_id}
**Authors:** {authors}
**Year:** {year}
**Venue:** {venue}
**Citations:** {citations}
**DOI:** {doi}
**arXiv:** {arxiv}

## Abstract
{abstract}
"""
    
    async def query_literature(
        self,
        query: str,
        workspace: LiteratureWorkspace,
        top_k: int = 10,
    ) -> list[RelevantExcerpt]:
        """Query literature using file system search.
        
        Uses grep/search tools instead of LLM attention to find
        relevant content. Then passes only relevant excerpts to LLM.
        
        Args:
            query: Search query
            workspace: Literature workspace
            top_k: Maximum results to return
            
        Returns:
            List of relevant excerpts
        """
        from berb.literature.fs_query import FileSystemQueryEngine
        
        engine = FileSystemQueryEngine(workspace)
        results = await engine.search(query, top_k)
        
        return results
    
    async def get_summary(self, workspace: LiteratureWorkspace, paper_id: str) -> str | None:
        """Get summary for a specific paper.
        
        Args:
            workspace: Literature workspace
            paper_id: Paper identifier
            
        Returns:
            Summary content or None
        """
        summary_file = workspace.summaries / f"{paper_id}.md"
        if summary_file.exists():
            return summary_file.read_text(encoding="utf-8")
        return None
    
    async def get_claims(self, workspace: LiteratureWorkspace, paper_id: str) -> list[dict] | None:
        """Get claims for a specific paper.
        
        Args:
            workspace: Literature workspace
            paper_id: Paper identifier
            
        Returns:
            List of claims or None
        """
        claims_file = workspace.claims / f"{paper_id}.json"
        if claims_file.exists():
            with open(claims_file, encoding="utf-8") as f:
                return json.load(f)
        return None


__all__ = [
    "FileSystemLiteratureProcessor",
    "LiteratureWorkspace",
    "RelevantExcerpt",
]
