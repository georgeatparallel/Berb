"""Obsidian knowledge base export for Berb.

Exports research artifacts to Obsidian vault with:
- Knowledge cards → Knowledge/ folder
- Experiment reports → Results/Reports/ folder
- Paper drafts → Writing/ folder
- Final archives → Papers/ folder
- Bi-directional sync support
- Frontmatter metadata (YAML)
- Wiki-style links between notes

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.knowledge.obsidian_export import ObsidianExporter, ObsidianConfig

    config = ObsidianConfig(vault_path="~/Obsidian Vault")
    exporter = ObsidianExporter(config)

    # Export knowledge card
    await exporter.export_knowledge_card({
        "id": "kc-001",
        "title": "Transformer Architecture",
        "content": "...",
        "tags": ["ml", "transformers"],
    })

    # Export experiment report
    await exporter.export_experiment_report({
        "id": "exp-001",
        "title": "BERT Fine-tuning Results",
        "content": "...",
        "metrics": {"accuracy": 0.95},
    })
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ObsidianConfig:
    """Obsidian export configuration.

    Attributes:
        vault_path: Path to Obsidian vault (required)
        knowledge_folder: Folder for knowledge cards (default: Knowledge)
        results_folder: Folder for experiment reports (default: Results/Reports)
        writing_folder: Folder for paper drafts (default: Writing)
        papers_folder: Folder for final papers (default: Papers)
        auto_export: Enable automatic export (default: False)
        create_links: Create wiki-style links between notes (default: True)
        include_frontmatter: Include YAML frontmatter (default: True)
        tag_prefix: Prefix for all tags (default: berb/)
    """

    vault_path: str = ""
    """Path to Obsidian vault"""

    knowledge_folder: str = "Knowledge"
    """Folder for knowledge cards"""

    results_folder: str = "Results/Reports"
    """Folder for experiment reports"""

    writing_folder: str = "Writing"
    """Folder for paper drafts"""

    papers_folder: str = "Papers"
    """Folder for final papers"""

    auto_export: bool = False
    """Enable automatic export"""

    create_links: bool = True
    """Create wiki-style links between notes"""

    include_frontmatter: bool = True
    """Include YAML frontmatter"""

    tag_prefix: str = "berb/"
    """Prefix for all tags"""


@dataclass
class ExportResult:
    """Result from an export operation.

    Attributes:
        success: Whether export was successful
        file_path: Path to exported file
        file_url: Obsidian URL (obsidian://open?vault=...&file=...)
        created: Whether file was created (vs updated)
        word_count: Number of words in exported file
        links_created: Number of wiki links created
        error: Error message if failed
    """

    success: bool = True
    file_path: str = ""
    file_url: str = ""
    created: bool = True
    word_count: int = 0
    links_created: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "file_path": self.file_path,
            "file_url": self.file_url,
            "created": self.created,
            "word_count": self.word_count,
            "links_created": self.links_created,
            "error": self.error,
        }


class ObsidianExporter:
    """Export Berb research artifacts to Obsidian.

    Provides bi-directional sync between Berb and Obsidian:
    - Export knowledge cards, experiment reports, papers
    - Create wiki-style links between related notes
    - Include YAML frontmatter for metadata
    - Support for Obsidian plugins (Dataview, etc.)

    Examples:
        Basic export:
            >>> exporter = ObsidianExporter(vault_path="~/Obsidian Vault")
            >>> result = await exporter.export_knowledge_card({
            ...     "title": "Transformer Architecture",
            ...     "content": "...",
            ...     "tags": ["ml", "transformers"],
            ... })
            >>> print(f"Exported to: {result.file_path}")

        Export with links:
            >>> result = await exporter.export_paper_draft({
            ...     "title": "My Research Paper",
            ...     "content": "...",
            ...     "references": ["kc-001", "kc-002"],
            ... }, create_links=True)
    """

    def __init__(self, config: ObsidianConfig | None = None):
        """
        Initialize Obsidian exporter.

        Args:
            config: Obsidian configuration (vault path required)
        """
        if config is None:
            config = ObsidianConfig()

        if not config.vault_path:
            # Try to get from environment
            config.vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "")

        if not config.vault_path:
            raise ValueError(
                "Obsidian vault path required. "
                "Set vault_path config or OBSIDIAN_VAULT_PATH environment variable."
            )

        self.config = config
        self.vault = Path(os.path.expanduser(config.vault_path))

        # Validate vault exists
        if not self.vault.exists():
            logger.warning(f"Obsidian vault not found: {self.vault}. Creating...")
            self.vault.mkdir(parents=True, exist_ok=True)

        # Create folder structure
        self._create_folders()

        # Cache for wiki links
        self._link_cache: dict[str, str] = {}

    def _create_folders(self) -> None:
        """Create folder structure in vault."""
        folders = [
            self.config.knowledge_folder,
            self.config.results_folder,
            self.config.writing_folder,
            self.config.papers_folder,
        ]

        for folder in folders:
            folder_path = self.vault / folder
            folder_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created folder: {folder_path}")

    async def export_knowledge_card(
        self,
        card: dict[str, Any],
        *,
        folder: str | None = None,
    ) -> ExportResult:
        """
        Export a knowledge card to Obsidian.

        Args:
            card: Knowledge card data (id, title, content, tags, etc.)
            folder: Override folder (default: from config)

        Returns:
            ExportResult with file path and metadata

        Examples:
            >>> result = await exporter.export_knowledge_card({
            ...     "id": "kc-001",
            ...     "title": "Transformer Architecture",
            ...     "content": "The transformer is a deep learning architecture...",
            ...     "tags": ["ml", "transformers", "attention"],
            ...     "created": "2024-03-28",
            ... })
        """
        folder_path = self.vault / (folder or self.config.knowledge_folder)
        title = card.get("title", "Untitled")
        card_id = card.get("id", f"kc-{datetime.now().strftime('%Y%m%d%H%M%S')}")

        # Generate filename
        filename = self._slugify(title) + ".md"
        file_path = folder_path / filename

        # Build content
        content = self._build_knowledge_card_md(card)

        # Write file
        try:
            created = not file_path.exists()
            file_path.write_text(content, encoding="utf-8")

            # Generate Obsidian URL
            file_url = self._generate_obsidian_url(file_path)

            # Count words and links
            word_count = len(content.split())
            links_created = content.count("[[")

            return ExportResult(
                success=True,
                file_path=str(file_path),
                file_url=file_url,
                created=created,
                word_count=word_count,
                links_created=links_created,
            )

        except Exception as e:
            logger.error(f"Failed to export knowledge card {title!r}: {e}")
            return ExportResult(
                success=False,
                error=str(e),
            )

    async def export_experiment_report(
        self,
        report: dict[str, Any],
        *,
        folder: str | None = None,
    ) -> ExportResult:
        """
        Export an experiment report to Obsidian.

        Args:
            report: Experiment report data (id, title, content, metrics, etc.)
            folder: Override folder (default: from config)

        Returns:
            ExportResult with file path and metadata

        Examples:
            >>> result = await exporter.export_experiment_report({
            ...     "id": "exp-001",
            ...     "title": "BERT Fine-tuning Results",
            ...     "content": "# Results\\n\\nAccuracy: 0.95...",
            ...     "metrics": {"accuracy": 0.95, "f1": 0.93},
            ...     "hypothesis_id": "hyp-001",
            ... })
        """
        folder_path = self.vault / (folder or self.config.results_folder)
        title = report.get("title", "Untitled Experiment")
        report_id = report.get("id", f"exp-{datetime.now().strftime('%Y%m%d%H%M%S')}")

        # Generate filename
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}_{self._slugify(title)}.md"
        file_path = folder_path / filename

        # Build content
        content = self._build_experiment_report_md(report)

        # Write file
        try:
            created = not file_path.exists()
            file_path.write_text(content, encoding="utf-8")

            file_url = self._generate_obsidian_url(file_path)
            word_count = len(content.split())
            links_created = content.count("[[")

            return ExportResult(
                success=True,
                file_path=str(file_path),
                file_url=file_url,
                created=created,
                word_count=word_count,
                links_created=links_created,
            )

        except Exception as e:
            logger.error(f"Failed to export experiment report {title!r}: {e}")
            return ExportResult(
                success=False,
                error=str(e),
            )

    async def export_paper_draft(
        self,
        draft: dict[str, Any],
        *,
        folder: str | None = None,
        create_links: bool = True,
    ) -> ExportResult:
        """
        Export a paper draft to Obsidian.

        Args:
            draft: Paper draft data (title, content, sections, references, etc.)
            folder: Override folder (default: from config)
            create_links: Create wiki links to referenced knowledge cards

        Returns:
            ExportResult with file path and metadata

        Examples:
            >>> result = await exporter.export_paper_draft({
            ...     "title": "My Research Paper",
            ...     "content": "# Introduction\\n\\n...",
            ...     "sections": ["Introduction", "Methods", "Results"],
            ...     "references": ["kc-001", "kc-002"],
            ... })
        """
        folder_path = self.vault / (folder or self.config.writing_folder)
        title = draft.get("title", "Untitled Paper")

        # Generate filename
        filename = self._slugify(title) + ".md"
        file_path = folder_path / filename

        # Build content
        content = self._build_paper_draft_md(draft, create_links=create_links)

        # Write file
        try:
            created = not file_path.exists()
            file_path.write_text(content, encoding="utf-8")

            file_url = self._generate_obsidian_url(file_path)
            word_count = len(content.split())
            links_created = content.count("[[")

            return ExportResult(
                success=True,
                file_path=str(file_path),
                file_url=file_url,
                created=created,
                word_count=word_count,
                links_created=links_created,
            )

        except Exception as e:
            logger.error(f"Failed to export paper draft {title!r}: {e}")
            return ExportResult(
                success=False,
                error=str(e),
            )

    async def export_final_paper(
        self,
        paper: dict[str, Any],
        *,
        folder: str | None = None,
    ) -> ExportResult:
        """
        Export a final paper to Obsidian.

        Args:
            paper: Final paper data (title, content, metadata, pdf_path, etc.)
            folder: Override folder (default: from config)

        Returns:
            ExportResult with file path and metadata
        """
        folder_path = self.vault / (folder or self.config.papers_folder)
        title = paper.get("title", "Untitled Paper")

        # Generate filename with date
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}_{self._slugify(title)}.md"
        file_path = folder_path / filename

        # Build content
        content = self._build_final_paper_md(paper)

        # Write file
        try:
            created = not file_path.exists()
            file_path.write_text(content, encoding="utf-8")

            file_url = self._generate_obsidian_url(file_path)
            word_count = len(content.split())
            links_created = content.count("[[")

            return ExportResult(
                success=True,
                file_path=str(file_path),
                file_url=file_url,
                created=created,
                word_count=word_count,
                links_created=links_created,
            )

        except Exception as e:
            logger.error(f"Failed to export final paper {title!r}: {e}")
            return ExportResult(
                success=False,
                error=str(e),
            )

    def _build_knowledge_card_md(self, card: dict[str, Any]) -> str:
        """Build markdown content for knowledge card."""
        lines = []

        # Frontmatter
        if self.config.include_frontmatter:
            lines.append("---")
            lines.append(f"title: \"{card.get('title', 'Untitled')}\"")
            lines.append(f"id: {card.get('id', '')}")
            lines.append(f"type: knowledge-card")
            lines.append(f"created: {card.get('created', datetime.now().isoformat())}")

            # Tags
            tags = card.get("tags", [])
            if tags:
                prefixed_tags = [f"{self.config.tag_prefix}{t}" for t in tags]
                lines.append(f"tags: [{', '.join(prefixed_tags)}]")

            # Additional metadata
            if "source" in card:
                lines.append(f"source: {card['source']}")
            if "url" in card:
                lines.append(f"url: {card['url']}")

            lines.append("---")
            lines.append("")

        # Title
        lines.append(f"# {card.get('title', 'Untitled')}")
        lines.append("")

        # Content
        content = card.get("content", "")
        lines.append(content)
        lines.append("")

        # References
        if "references" in card:
            lines.append("---")
            lines.append("## References")
            lines.append("")
            for ref in card["references"]:
                if isinstance(ref, dict):
                    lines.append(f"- {ref.get('title', 'Untitled')}: {ref.get('url', '')}")
                else:
                    lines.append(f"- {ref}")
            lines.append("")

        return "\n".join(lines)

    def _build_experiment_report_md(self, report: dict[str, Any]) -> str:
        """Build markdown content for experiment report."""
        lines = []

        # Frontmatter
        if self.config.include_frontmatter:
            lines.append("---")
            lines.append(f"title: \"{report.get('title', 'Untitled')}\"")
            lines.append(f"id: {report.get('id', '')}")
            lines.append(f"type: experiment-report")
            lines.append(f"date: {report.get('date', datetime.now().isoformat())}")

            # Tags
            lines.append(f"tags: [{self.config.tag_prefix}experiment]")

            # Metrics summary
            metrics = report.get("metrics", {})
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    lines.append(f"{key}: {value:.4f}" if isinstance(value, float) else f"{key}: {value}")

            lines.append("---")
            lines.append("")

        # Title
        lines.append(f"# {report.get('title', 'Untitled Experiment')}")
        lines.append("")

        # Hypothesis link
        if "hypothesis_id" in report:
            hyp_id = report["hypothesis_id"]
            lines.append(f"**Hypothesis:** [[{hyp_id}]]")
            lines.append("")

        # Content
        content = report.get("content", "")
        lines.append(content)
        lines.append("")

        # Metrics table
        metrics = report.get("metrics", {})
        if metrics:
            lines.append("---")
            lines.append("## Metrics")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            for key, value in metrics.items():
                if isinstance(value, float):
                    lines.append(f"| {key} | {value:.4f} |")
                else:
                    lines.append(f"| {key} | {value} |")
            lines.append("")

        return "\n".join(lines)

    def _build_paper_draft_md(
        self,
        draft: dict[str, Any],
        create_links: bool = True,
    ) -> str:
        """Build markdown content for paper draft."""
        lines = []

        # Frontmatter
        if self.config.include_frontmatter:
            lines.append("---")
            lines.append(f"title: \"{draft.get('title', 'Untitled')}\"")
            lines.append(f"type: paper-draft")
            lines.append(f"date: {datetime.now().isoformat()}")
            lines.append(f"tags: [{self.config.tag_prefix}paper, {self.config.tag_prefix}draft]")

            # Authors
            authors = draft.get("authors", [])
            if authors:
                lines.append(f"authors: [{', '.join(authors)}]")

            lines.append("---")
            lines.append("")

        # Title
        lines.append(f"# {draft.get('title', 'Untitled Paper')}")
        lines.append("")

        # Content with optional link creation
        content = draft.get("content", "")
        if create_links:
            content = self._create_wiki_links(content, draft.get("references", []))
        lines.append(content)

        return "\n".join(lines)

    def _build_final_paper_md(self, paper: dict[str, Any]) -> str:
        """Build markdown content for final paper."""
        lines = []

        # Frontmatter
        if self.config.include_frontmatter:
            lines.append("---")
            lines.append(f"title: \"{paper.get('title', 'Untitled')}\"")
            lines.append(f"type: paper")
            lines.append(f"status: final")
            lines.append(f"date: {datetime.now().isoformat()}")

            # Venue
            if "venue" in paper:
                lines.append(f"venue: {paper['venue']}")

            # Authors
            authors = paper.get("authors", [])
            if authors:
                lines.append(f"authors: [{', '.join(authors)}]")

            lines.append("---")
            lines.append("")

        # Title
        lines.append(f"# {paper.get('title', 'Untitled Paper')}")
        lines.append("")

        # Content
        content = paper.get("content", "")
        lines.append(content)
        lines.append("")

        # PDF attachment
        if "pdf_path" in paper:
            lines.append("---")
            lines.append("## Attachments")
            lines.append("")
            lines.append(f"![PDF]({paper['pdf_path']})")
            lines.append("")

        return "\n".join(lines)

    def _create_wiki_links(self, content: str, references: list[str]) -> str:
        """Create wiki-style links in content."""
        if not references:
            return content

        # Simple implementation: wrap reference IDs in [[ ]]
        for ref_id in references:
            # Escape special regex characters
            ref_id_escaped = re.escape(ref_id)
            # Replace with wiki link
            content = re.sub(
                rf"\b{ref_id_escaped}\b",
                f"[[{ref_id}]]",
                content,
            )

        return content

    def _slugify(self, text: str) -> str:
        """Convert text to filename-safe slug."""
        # Convert to lowercase
        text = text.lower()
        # Replace spaces with underscores
        text = text.replace(" ", "_")
        # Remove special characters
        text = re.sub(r"[^a-z0-9_]", "", text)
        # Remove multiple underscores
        text = re.sub(r"_+", "_", text)
        # Truncate
        return text[:50]

    def _generate_obsidian_url(self, file_path: Path) -> str:
        """Generate Obsidian URL for a file."""
        vault_name = self.vault.name
        relative_path = file_path.relative_to(self.vault)

        # URL encode the path
        import urllib.parse
        encoded_path = urllib.parse.quote(str(relative_path))

        return f"obsidian://open?vault={vault_name}&file={encoded_path}"

    async def sync_all(
        self,
        knowledge_cards: list[dict[str, Any]] | None = None,
        experiment_reports: list[dict[str, Any]] | None = None,
        paper_drafts: list[dict[str, Any]] | None = None,
    ) -> list[ExportResult]:
        """
        Sync all artifacts to Obsidian.

        Args:
            knowledge_cards: List of knowledge cards to export
            experiment_reports: List of experiment reports to export
            paper_drafts: List of paper drafts to export

        Returns:
            List of ExportResult objects

        Examples:
            >>> results = await exporter.sync_all(
            ...     knowledge_cards=cards,
            ...     experiment_reports=reports,
            ... )
            >>> success_count = sum(1 for r in results if r.success)
            >>> print(f"Exported {success_count} items")
        """
        results = []

        if knowledge_cards:
            for card in knowledge_cards:
                result = await self.export_knowledge_card(card)
                results.append(result)

        if experiment_reports:
            for report in experiment_reports:
                result = await self.export_experiment_report(report)
                results.append(result)

        if paper_drafts:
            for draft in paper_drafts:
                result = await self.export_paper_draft(draft)
                results.append(result)

        return results


def create_exporter_from_env() -> ObsidianExporter:
    """
    Create ObsidianExporter from environment variables.

    Environment Variables:
        OBSIDIAN_VAULT_PATH: Path to Obsidian vault (required)
        OBSIDIAN_KNOWLEDGE_FOLDER: Knowledge cards folder (default: Knowledge)
        OBSIDIAN_RESULTS_FOLDER: Experiment reports folder (default: Results/Reports)
        OBSIDIAN_WRITING_FOLDER: Paper drafts folder (default: Writing)
        OBSIDIAN_PAPERS_FOLDER: Final papers folder (default: Papers)
        OBSIDIAN_AUTO_EXPORT: Enable auto-export (default: false)
        OBSIDIAN_CREATE_LINKS: Create wiki links (default: true)

    Returns:
        ObsidianExporter configured from environment

    Examples:
        # In .env file:
        # OBSIDIAN_VAULT_PATH=~/Obsidian Vault
        # OBSIDIAN_KNOWLEDGE_FOLDER=Knowledge
        # OBSIDIAN_AUTO_EXPORT=true

        >>> exporter = create_exporter_from_env()
    """
    return ObsidianExporter(
        ObsidianConfig(
            vault_path=os.environ.get("OBSIDIAN_VAULT_PATH", ""),
            knowledge_folder=os.environ.get("OBSIDIAN_KNOWLEDGE_FOLDER", "Knowledge"),
            results_folder=os.environ.get("OBSIDIAN_RESULTS_FOLDER", "Results/Reports"),
            writing_folder=os.environ.get("OBSIDIAN_WRITING_FOLDER", "Writing"),
            papers_folder=os.environ.get("OBSIDIAN_PAPERS_FOLDER", "Papers"),
            auto_export=os.environ.get("OBSIDIAN_AUTO_EXPORT", "").lower() == "true",
            create_links=os.environ.get("OBSIDIAN_CREATE_LINKS", "true").lower() != "false",
        )
    )
