"""Structured paper reading notes for traceable knowledge extraction.

This module generates structured reading notes for each paper,
capturing research questions, methodology, key findings, limitations,
and claims with citation context.

Uses Multi-Perspective reasoning for comprehensive note generation.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from berb.reasoning.multi_perspective import MultiPerspectiveMethod, PerspectiveType
from berb.reasoning.base import ReasoningContext
from berb.llm.client import LLMProvider
from berb.literature.citation_classifier import CitationClassification, CitationIntent

logger = logging.getLogger(__name__)


class ClaimWithEvidence(BaseModel):
    """A claim extracted from a paper with its evidence.

    Attributes:
        claim_text: The claim statement
        evidence_type: Type of evidence (experimental/theoretical/etc.)
        confidence: Claim confidence (0-1)
        page_number: Page where claim appears (if available)
        supporting_data: Data supporting the claim
    """

    claim_text: str
    evidence_type: Literal["experimental", "theoretical", "empirical", "survey"] = "experimental"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    page_number: int | None = None
    supporting_data: str = ""


class PaperReadingNote(BaseModel):
    """Structured reading note for a paper.

    Attributes:
        paper_id: Paper identifier
        doi: Paper DOI
        title: Paper title
        authors: Author list
        year: Publication year
        venue: Publication venue
        research_question: Main research question
        methodology: Methodology description
        key_findings: List of key findings
        limitations: List of limitations
        claims: Extracted claims with evidence
        relevance_to_topic: Relevance assessment
        quality_assessment: Quality score (0-10)
        citation_profile: Citation classification profile
        used_in_stages: Pipeline stages where this paper was referenced
        contribution_type: How this paper contributes to current research
        notes_metadata: Additional metadata
        created_at: When note was created
        updated_at: Last update timestamp
    """

    paper_id: str
    doi: str = ""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    research_question: str = ""
    methodology: str = ""
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    claims: list[ClaimWithEvidence] = Field(default_factory=list)
    relevance_to_topic: str = ""
    quality_assessment: float = Field(default=5.0, ge=0.0, le=10.0)
    citation_profile: dict[str, int] = Field(default_factory=dict)
    used_in_stages: list[int] = Field(default_factory=list)
    contribution_type: Literal[
        "background",
        "methodology",
        "comparison",
        "supporting",
        "contrasting",
    ] = "background"
    notes_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(mode="json")

    def to_markdown(self) -> str:
        """Convert to Markdown format.

        Returns:
            Markdown string
        """
        lines = [
            f"# {self.title}",
            "",
            f"**Authors:** {', '.join(self.authors)}",
            f"**Year:** {self.year}",
            f"**Venue:** {self.venue}",
            f"**DOI:** {self.doi}",
            "",
            "## Research Question",
            "",
            self.research_question,
            "",
            "## Methodology",
            "",
            self.methodology,
            "",
            "## Key Findings",
            "",
        ]

        for i, finding in enumerate(self.key_findings, 1):
            lines.append(f"{i}. {finding}")

        lines.extend([
            "",
            "## Limitations",
            "",
        ])

        for i, limit in enumerate(self.limitations, 1):
            lines.append(f"{i}. {limit}")

        lines.extend([
            "",
            "## Extracted Claims",
            "",
        ])

        for claim in self.claims[:5]:
            lines.append(f"- {claim.claim_text} (confidence: {claim.confidence:.2f})")

        lines.extend([
            "",
            "## Relevance",
            "",
            self.relevance_to_topic,
            "",
            f"**Quality:** {self.quality_assessment:.1f}/10",
            f"**Contribution Type:** {self.contribution_type}",
            "",
            f"*Generated: {self.created_at}*",
        ])

        return "\n".join(lines)


class ReadingNotesCollection(BaseModel):
    """Collection of reading notes.

    Attributes:
        notes: Dictionary of notes by paper ID
        domain: Research domain
        total_notes: Total number of notes
        created_at: When collection was created
        updated_at: Last update timestamp
    """

    notes: dict[str, PaperReadingNote] = Field(default_factory=dict)
    domain: str = ""
    total_notes: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.total_notes = len(self.notes)
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def add_note(self, note: PaperReadingNote) -> None:
        """Add a note to collection.

        Args:
            note: Paper reading note
        """
        self.notes[note.paper_id] = note
        self.total_notes = len(self.notes)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_notes_by_contribution(
        self,
        contribution_type: str,
    ) -> list[PaperReadingNote]:
        """Get notes by contribution type.

        Args:
            contribution_type: Type to filter by

        Returns:
            List of matching notes
        """
        return [
            n for n in self.notes.values()
            if n.contribution_type == contribution_type
        ]

    def get_high_quality_notes(
        self,
        min_quality: float = 7.0,
    ) -> list[PaperReadingNote]:
        """Get notes with quality above threshold.

        Args:
            min_quality: Minimum quality score

        Returns:
            List of high-quality notes
        """
        return [
            n for n in self.notes.values()
            if n.quality_assessment >= min_quality
        ]

    def export_to_json(self, path: Path | str) -> None:
        """Export collection to JSON file.

        Args:
            path: Output file path
        """
        data = {
            "notes": {k: v.to_dict() for k, v in self.notes.items()},
            "domain": self.domain,
            "total_notes": self.total_notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def export_notes_to_directory(
        self,
        output_dir: Path | str,
        format: Literal["markdown", "json"] = "markdown",
    ) -> None:
        """Export individual notes to files.

        Args:
            output_dir: Output directory
            format: Export format
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for note in self.notes.values():
            if format == "markdown":
                filename = f"{note.paper_id}.md"
                content = note.to_markdown()
            else:
                filename = f"{note.paper_id}.json"
                content = json.dumps(note.to_dict(), indent=2)

            with open(output_dir / filename, "w", encoding="utf-8") as f:
                f.write(content)


class ReadingNotesConfig(BaseModel):
    """Configuration for reading notes generation.

    Attributes:
        use_multi_perspective: Whether to use multi-perspective reasoning
        llm_provider: LLM provider
        extract_claims: Whether to extract claims
        extract_limitations: Whether to extract limitations
        quality_threshold: Minimum quality for inclusion
        persistence_path: Path to persist notes
    """

    use_multi_perspective: bool = True
    llm_provider: LLMProvider | None = None
    extract_claims: bool = True
    extract_limitations: bool = True
    quality_threshold: float = 5.0
    persistence_path: str | None = None


class StructuredNotesGenerator:
    """Generates structured reading notes from papers.

    This generator uses multi-perspective reasoning to extract:
    - Research questions
    - Methodology details
    - Key findings
    - Limitations
    - Claims with evidence

    Usage::

        generator = StructuredNotesGenerator(
            config=ReadingNotesConfig(
                use_multi_perspective=True,
                llm_provider=llm_provider,
            ),
        )

        notes = await generator.generate_notes(paper_metadata, paper_text)
    """

    # Perspective definitions for note generation
    NOTE_PERSPECTIVES = {
        "methodologist": {
            "role": "Methodologist",
            "focus": "Extract methodology details, experimental design, data collection",
            "questions": [
                "What methodology was used?",
                "What was the experimental design?",
                "What data was collected and how?",
                "What were the controls and variables?",
            ],
        },
        "critic": {
            "role": "Critical Reviewer",
            "focus": "Identify limitations, weaknesses, and potential biases",
            "questions": [
                "What are the main limitations?",
                "What assumptions were made?",
                "What potential biases exist?",
                "What could invalidate the findings?",
            ],
        },
        "synthesizer": {
            "role": "Knowledge Synthesizer",
            "focus": "Extract key findings and claims with evidence",
            "questions": [
                "What are the main findings?",
                "What claims are made?",
                "What evidence supports each claim?",
                "How strong is the evidence?",
            ],
        },
        "connector": {
            "role": "Domain Connector",
            "focus": "Assess relevance and connections to broader field",
            "questions": [
                "How does this relate to prior work?",
                "What gap does this fill?",
                "What future work does this enable?",
                "Who should cite this paper?",
            ],
        },
    }

    def __init__(self, config: ReadingNotesConfig | None = None):
        """Initialize notes generator.

        Args:
            config: Configuration
        """
        self.config = config or ReadingNotesConfig()

        # Initialize multi-perspective method
        self.multi_perspective_method = None
        if self.config.llm_provider and self.config.use_multi_perspective:
            self.multi_perspective_method = MultiPerspectiveMethod(
                llm_client=self.config.llm_provider,
            )

        # Notes collection
        self.collection = ReadingNotesCollection()

        # Load existing notes if path specified
        if self.config.persistence_path:
            self._load_notes()

    async def generate_notes(
        self,
        paper_metadata: dict[str, Any],
        paper_text: str = "",
        topic: str = "",
    ) -> PaperReadingNote:
        """Generate structured reading notes for a paper.

        Args:
            paper_metadata: Paper metadata (title, authors, venue, etc.)
            paper_text: Full paper text (optional)
            topic: Current research topic for relevance assessment

        Returns:
            PaperReadingNote
        """
        paper_id = paper_metadata.get("id", paper_metadata.get("doi", "unknown"))

        logger.info(f"Generating reading notes for {paper_id}")

        # Extract information using multi-perspective reasoning
        if self.multi_perspective_method and paper_text:
            extraction = await self._multi_perspective_extraction(
                paper_text, topic
            )
        else:
            # Fallback to heuristic extraction
            extraction = await self._heuristic_extraction(
                paper_metadata, paper_text, topic
            )

        # Build note
        note = PaperReadingNote(
            paper_id=paper_id,
            doi=paper_metadata.get("doi", ""),
            title=paper_metadata.get("title", ""),
            authors=paper_metadata.get("authors", []),
            year=paper_metadata.get("year"),
            venue=paper_metadata.get("venue", ""),
            research_question=extraction.get("research_question", ""),
            methodology=extraction.get("methodology", ""),
            key_findings=extraction.get("key_findings", []),
            limitations=extraction.get("limitations", []),
            claims=extraction.get("claims", []),
            relevance_to_topic=extraction.get("relevance", ""),
            quality_assessment=extraction.get("quality", 5.0),
            contribution_type=self._infer_contribution_type(extraction),
            notes_metadata=extraction.get("metadata", {}),
        )

        # Add to collection
        self.collection.add_note(note)

        # Auto-save if configured
        if self.config.persistence_path:
            self._save_notes()

        logger.info(f"Reading notes generated for {paper_id}")
        return note

    async def generate_notes_batch(
        self,
        papers: list[dict[str, Any]],
        topic: str = "",
    ) -> ReadingNotesCollection:
        """Generate notes for multiple papers.

        Args:
            papers: List of paper metadata with optional text
            topic: Research topic for relevance

        Returns:
            ReadingNotesCollection
        """
        logger.info(f"Generating notes for {len(papers)} papers")

        for i, paper in enumerate(papers):
            paper_text = paper.get("text", paper.get("abstract", ""))
            await self.generate_notes(paper, paper_text, topic)

            # Progress logging
            if (i + 1) % 10 == 0:
                logger.info(f"Processed {i + 1}/{len(papers)} papers")

        logger.info(f"Batch complete: {self.collection.total_notes} notes")
        return self.collection

    async def _multi_perspective_extraction(
        self,
        paper_text: str,
        topic: str,
    ) -> dict[str, Any]:
        """Extract note content using multi-perspective reasoning.

        Args:
            paper_text: Full paper text
            topic: Research topic

        Returns:
            Extraction results dictionary
        """
        extraction = {
            "research_question": "",
            "methodology": "",
            "key_findings": [],
            "limitations": [],
            "claims": [],
            "relevance": "",
            "quality": 5.0,
            "metadata": {},
        }

        # Run each perspective
        for perspective_name, perspective_def in self.NOTE_PERSPECTIVES.items():
            problem = self._build_perspective_problem(
                paper_text, topic, perspective_def
            )

            try:
                result = await self._run_perspective(problem, perspective_name)

                # Extract relevant content based on perspective
                if perspective_name == "methodologist":
                    extraction["methodology"] = self._extract_section(
                        result.content, "methodology"
                    )
                elif perspective_name == "critic":
                    extraction["limitations"] = self._extract_list(
                        result.content, "limitations"
                    )
                elif perspective_name == "synthesizer":
                    extraction["key_findings"] = self._extract_list(
                        result.content, "findings"
                    )
                    extraction["claims"] = self._extract_claims(result.content)
                elif perspective_name == "connector":
                    extraction["relevance"] = self._extract_section(
                        result.content, "relevance"
                    )

            except Exception as e:
                logger.warning(f"Perspective {perspective_name} failed: {e}")

        return extraction

    def _build_perspective_problem(
        self,
        paper_text: str,
        topic: str,
        perspective_def: dict[str, Any],
    ) -> str:
        """Build problem statement for a perspective.

        Args:
            paper_text: Paper text
            topic: Research topic
            perspective_def: Perspective definition

        Returns:
            Problem statement
        """
        return f"""Paper Analysis Task

**Role:** {perspective_def['role']}
**Focus:** {perspective_def['focus']}

**Paper Text:**
{paper_text[:8000]}  # Truncate for context limits

**Research Topic:** {topic}

**Your Questions:**
{chr(10).join(f"- {q}" for q in perspective_def['questions'])}

Please provide detailed answers to each question based on the paper content.
Organize your response with clear sections for each question."""

    async def _run_perspective(
        self,
        problem: str,
        perspective_name: str,
    ) -> Any:
        """Run single perspective analysis.

        Args:
            problem: Problem statement
            perspective_name: Perspective name

        Returns:
            Perspective result
        """
        if not self.multi_perspective_method:
            return type('Result', (), {"content": ""})()

        context = ReasoningContext(
            stage_id="NOTE_GENERATION",
            stage_name=f"Note Generation - {perspective_name}",
            input_data={"problem": problem},
        )

        return await self.multi_perspective_method.execute(context)

    def _extract_section(
        self,
        content: str,
        section_name: str,
    ) -> str:
        """Extract section from perspective result.

        Args:
            content: Result content
            section_name: Section to extract

        Returns:
            Extracted section text
        """
        # Simple extraction - find section header and get content
        import re

        pattern = rf"##?\s*{section_name}[:\s]*(.*?)(?=##?|$)"
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_list(
        self,
        content: str,
        list_type: str,
    ) -> list[str]:
        """Extract list from perspective result.

        Args:
            content: Result content
            list_type: Type of list to extract

        Returns:
            Extracted list items
        """
        import re

        # Look for numbered or bulleted lists
        items = []

        # Numbered lists
        numbered = re.findall(r"\d+[\.\)]\s*(.+)$", content, re.MULTILINE)
        items.extend([item.strip() for item in numbered if len(item) > 10])

        # Bulleted lists
        bulleted = re.findall(r"[•\-\*]\s*(.+)$", content, re.MULTILINE)
        items.extend([item.strip() for item in bulleted if len(item) > 10])

        return items[:10]  # Top 10 items

    def _extract_claims(
        self,
        content: str,
    ) -> list[ClaimWithEvidence]:
        """Extract claims with evidence from content.

        Args:
            content: Result content

        Returns:
            List of claims
        """
        claims = []

        # Look for claim patterns
        claim_indicators = [
            "we found", "we show", "we demonstrate", "our results",
            "this paper", "our approach", "experiments show",
        ]

        sentences = content.split(".")
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 500:
                continue

            # Check if sentence contains claim indicators
            for indicator in claim_indicators:
                if indicator in sentence.lower():
                    claims.append(
                        ClaimWithEvidence(
                            claim_text=sentence.rstrip("."),
                            evidence_type="experimental",
                            confidence=0.8,
                        )
                    )
                    break

        return claims[:10]  # Top 10 claims

    async def _heuristic_extraction(
        self,
        paper_metadata: dict[str, Any],
        paper_text: str,
        topic: str,
    ) -> dict[str, Any]:
        """Extract note content using heuristics (no LLM).

        Args:
            paper_metadata: Paper metadata
            paper_text: Paper text
            topic: Research topic

        Returns:
            Extraction results
        """
        # Extract from metadata
        abstract = paper_metadata.get("abstract", "")

        return {
            "research_question": self._extract_research_question(abstract),
            "methodology": paper_metadata.get("methodology", ""),
            "key_findings": paper_metadata.get("findings", []),
            "limitations": paper_metadata.get("limitations", []),
            "claims": [],
            "relevance": self._assess_relevance(abstract, topic),
            "quality": self._estimate_quality(paper_metadata),
            "metadata": {},
        }

    def _extract_research_question(self, abstract: str) -> str:
        """Extract research question from abstract.

        Args:
            abstract: Paper abstract

        Returns:
            Research question
        """
        # Look for question patterns
        import re

        patterns = [
            r"(?:we|this paper) (?:investigate|examine|study|explore|analyze) (.+?)[.\n]",
            r"(?:the|our) (?:goal|objective|aim|purpose) (?:is|was) to (.+?)[.\n]",
            r"how to (.+?)[.\n]",
            r"whether (.+?)[.\n]",
        ]

        for pattern in patterns:
            match = re.search(pattern, abstract, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return ""

    def _assess_relevance(
        self,
        abstract: str,
        topic: str,
    ) -> str:
        """Assess paper relevance to topic.

        Args:
            abstract: Paper abstract
            topic: Research topic

        Returns:
            Relevance assessment
        """
        if not topic:
            return "General relevance"

        # Count keyword overlap
        topic_words = set(topic.lower().split())
        abstract_words = set(abstract.lower().split())

        overlap = len(topic_words & abstract_words)

        if overlap > 5:
            return "Highly relevant - direct topic match"
        elif overlap > 2:
            return "Moderately relevant - related concepts"
        else:
            return " tangentially relevant - background material"

    def _estimate_quality(
        self,
        paper_metadata: dict[str, Any],
    ) -> float:
        """Estimate paper quality from metadata.

        Args:
            paper_metadata: Paper metadata

        Returns:
            Quality score (0-10)
        """
        score = 5.0  # Base score

        # Venue prestige
        venue = paper_metadata.get("venue", "").lower()
        prestigious_venues = [
            "nature", "science", "pnas", "neurips", "icml", "acl", "cvpr",
        ]
        for v in prestigious_venues:
            if v in venue:
                score += 2.0
                break

        # Citation count
        citations = paper_metadata.get("citations", 0)
        if citations > 100:
            score += 2.0
        elif citations > 50:
            score += 1.5
        elif citations > 10:
            score += 1.0

        # Recency
        year = paper_metadata.get("year")
        if year and year >= 2023:
            score += 0.5

        return min(10.0, score)

    def _infer_contribution_type(
        self,
        extraction: dict[str, Any],
    ) -> Literal["background", "methodology", "comparison", "supporting", "contrasting"]:
        """Infer contribution type from extraction.

        Args:
            extraction: Extraction results

        Returns:
            Contribution type
        """
        # Check for contrasting language
        limitations = " ".join(extraction.get("limitations", []))
        if any(w in limitations.lower() for w in ["contrast", "disagree", "challenge"]):
            return "contrasting"

        # Check for methodology focus
        methodology = extraction.get("methodology", "")
        if len(methodology) > 100:
            return "methodology"

        # Check for supporting findings
        findings = extraction.get("key_findings", [])
        if findings:
            return "supporting"

        return "background"

    def _save_notes(self) -> None:
        """Save notes to disk."""
        if not self.config.persistence_path:
            return

        try:
            path = Path(self.config.persistence_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.collection.export_to_json(path)
            logger.debug(f"Saved reading notes to {path}")
        except Exception as e:
            logger.error(f"Failed to save reading notes: {e}")

    def _load_notes(self) -> None:
        """Load notes from disk."""
        if not self.config.persistence_path:
            return

        path = Path(self.config.persistence_path)
        if not path.exists():
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            notes_dict = data.get("notes", {})
            for paper_id, note_data in notes_dict.items():
                note = PaperReadingNote(**note_data)
                self.collection.add_note(note)

            logger.info(f"Loaded {self.collection.total_notes} reading notes")
        except Exception as e:
            logger.error(f"Failed to load reading notes: {e}")


# Convenience function
async def generate_reading_notes(
    papers: list[dict[str, Any]],
    topic: str = "",
    llm_provider: LLMProvider | None = None,
    persistence_path: str | None = None,
) -> ReadingNotesCollection:
    """Convenience function to generate reading notes.

    Args:
        papers: List of paper metadata
        topic: Research topic
        llm_provider: LLM provider
        persistence_path: Optional persistence path

    Returns:
        ReadingNotesCollection
    """
    config = ReadingNotesConfig(
        use_multi_perspective=llm_provider is not None,
        llm_provider=llm_provider,
        persistence_path=persistence_path,
    )

    generator = StructuredNotesGenerator(config)
    return await generator.generate_notes_batch(papers, topic)
