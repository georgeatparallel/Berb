"""Writing pattern memory for persistent style learning.

This module maintains a global "writing memory" that learns patterns
from mined papers across runs. Patterns include transition phrases,
section templates, argument structures, and domain-specific vocabulary.

Uses Iterative reasoning for pattern extraction and refinement.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from berb.llm.client import LLMProvider
from berb.reasoning.research import ResearchMethod

logger = logging.getLogger(__name__)


class PatternType(StrEnum):
    """Type of writing pattern.

    Attributes:
        TRANSITION: Transition phrases between sections/paragraphs
        SECTION_TEMPLATE: Section structure templates
        ARGUMENT_STRUCTURE: Argument flow patterns
        HEDGING: Hedging phrases for different confidence levels
        VOCABULARY: Domain-specific vocabulary
        CITATION: Citation introduction patterns
        EMPHASIS: Emphasis and highlighting patterns
        CONNECTION: Logical connection patterns
    """

    TRANSITION = "transition"
    SECTION_TEMPLATE = "section_template"
    ARGUMENT_STRUCTURE = "argument_structure"
    HEDGING = "hedging"
    VOCABULARY = "vocabulary"
    CITATION = "citation"
    EMPHASIS = "emphasis"
    CONNECTION = "connection"


class WritingPattern(BaseModel):
    """A single writing pattern.

    Attributes:
        id: Unique pattern identifier
        type: Pattern type
        domain: Research domain
        pattern_text: The pattern text
        examples: Example usage contexts
        frequency: How often this pattern appears
        effectiveness_score: Estimated effectiveness (0-10)
        source_papers: Papers where pattern was found
        created_at: When pattern was first recorded
        updated_at: Last update timestamp
        tags: Pattern tags for retrieval
    """

    id: str
    type: PatternType
    domain: str = ""
    pattern_text: str
    examples: list[str] = Field(default_factory=list)
    frequency: int = 1
    effectiveness_score: float = Field(default=5.0, ge=0.0, le=10.0)
    source_papers: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "domain": self.domain,
            "pattern_text": self.pattern_text,
            "examples": self.examples,
            "frequency": self.frequency,
            "effectiveness_score": self.effectiveness_score,
            "source_papers": self.source_papers,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
        }


class WritingPatternsMemory(BaseModel):
    """Persistent memory of writing patterns.

    Attributes:
        patterns: All stored patterns
        domain: Primary research domain
        total_patterns: Total pattern count
        last_updated: Last update timestamp
        version: Memory format version
    """

    patterns: dict[str, WritingPattern] = Field(default_factory=dict)
    domain: str = ""
    total_patterns: int = 0
    last_updated: str = ""
    version: str = "1.0"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.total_patterns = len(self.patterns)
        if not self.last_updated:
            self.last_updated = datetime.now(UTC).isoformat()

    def add_pattern(self, pattern: WritingPattern) -> None:
        """Add or update a pattern.

        Args:
            pattern: Writing pattern to add
        """
        if pattern.id in self.patterns:
            # Update existing
            existing = self.patterns[pattern.id]
            existing.frequency += 1
            existing.updated_at = datetime.now(UTC).isoformat()
            if pattern.source_papers:
                existing.source_papers.extend(pattern.source_papers)
                existing.source_papers = list(set(existing.source_papers))
        else:
            # Add new
            pattern.created_at = datetime.now(UTC).isoformat()
            pattern.updated_at = pattern.created_at
            self.patterns[pattern.id] = pattern

        self.total_patterns = len(self.patterns)
        self.last_updated = datetime.now(UTC).isoformat()

    def get_patterns_by_type(
        self,
        pattern_type: PatternType,
        domain: str | None = None,
    ) -> list[WritingPattern]:
        """Get patterns by type.

        Args:
            pattern_type: Pattern type
            domain: Optional domain filter

        Returns:
            List of matching patterns
        """
        patterns = [
            p for p in self.patterns.values()
            if p.type == pattern_type
        ]

        if domain:
            patterns = [p for p in patterns if p.domain == domain]

        return sorted(patterns, key=lambda p: p.frequency, reverse=True)

    def get_patterns_for_section(
        self,
        section: str,
        domain: str | None = None,
    ) -> list[WritingPattern]:
        """Get patterns relevant for a section.

        Args:
            section: Section name (introduction, methods, etc.)
            domain: Optional domain filter

        Returns:
            List of relevant patterns
        """
        # Map section to pattern types
        section_patterns = {
            "introduction": [PatternType.TRANSITION, PatternType.ARGUMENT_STRUCTURE],
            "methods": [PatternType.SECTION_TEMPLATE, PatternType.VOCABULARY],
            "results": [PatternType.EMPHASIS, PatternType.CITATION],
            "discussion": [PatternType.CONNECTION, PatternType.HEDGING],
            "conclusion": [PatternType.TRANSITION, PatternType.EMPHASIS],
        }

        pattern_types = section_patterns.get(section, [PatternType.TRANSITION])

        patterns = []
        for ptype in pattern_types:
            patterns.extend(self.get_patterns_by_type(ptype, domain))

        return patterns[:20]  # Top 20

    def merge(self, other: WritingPatternsMemory) -> None:
        """Merge another memory into this one.

        Args:
            other: Another writing patterns memory
        """
        for _pattern_id, pattern in other.patterns.items():
            self.add_pattern(pattern)

    def to_json(self) -> str:
        """Serialize to JSON.

        Returns:
            JSON string
        """
        data = {
            "patterns": {k: v.to_dict() for k, v in self.patterns.items()},
            "domain": self.domain,
            "total_patterns": self.total_patterns,
            "last_updated": self.last_updated,
            "version": self.version,
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> WritingPatternsMemory:
        """Deserialize from JSON.

        Args:
            json_str: JSON string

        Returns:
            WritingPatternsMemory instance
        """
        data = json.loads(json_str)

        patterns = {}
        for pid, pdata in data.get("patterns", {}).items():
            patterns[pid] = WritingPattern(**pdata)

        return cls(
            patterns=patterns,
            domain=data.get("domain", ""),
            total_patterns=data.get("total_patterns", 0),
            last_updated=data.get("last_updated", ""),
            version=data.get("version", "1.0"),
        )


class WritingPatternMemoryConfig(BaseModel):
    """Configuration for pattern memory.

    Attributes:
        persistence_path: Path to persist memory
        auto_save: Whether to auto-save after updates
        max_patterns: Maximum patterns to store
        llm_provider: LLM provider for pattern extraction
    """

    persistence_path: str | None = None
    auto_save: bool = True
    max_patterns: int = 1000
    llm_provider: LLMProvider | None = None


class WritingPatternMiner:
    """Mines writing patterns from papers.

    This miner uses iterative reasoning to extract:
    - Transition phrases
    - Section templates
    - Argument structures
    - Domain-specific vocabulary

    Usage::

        miner = WritingPatternMiner(llm_provider)
        patterns = await miner.mine_from_papers(papers, domain)
    """

    # Pattern extraction prompts
    TRANSITION_PROMPT = """Extract transition phrases from this academic text.
Focus on phrases that connect sections, paragraphs, or ideas.

Examples: "Furthermore,", "In contrast,", "Building on this work,"

Text:
{text}

Extract transitions as a JSON list."""

    HEDGING_PROMPT = """Extract hedging phrases from this academic text.
These are phrases that express uncertainty or caution.

Examples: "may suggest", "appears to", "potentially", "our results indicate"

Text:
{text}

Extract hedging phrases as a JSON list."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        config: WritingPatternMemoryConfig | None = None,
    ):
        """Initialize pattern miner.

        Args:
            llm_provider: LLM provider
            config: Configuration
        """
        self.llm_provider = llm_provider
        self.config = config or WritingPatternMemoryConfig()

        # Initialize iterative method
        self.iterative_method = None
        if self.llm_provider:
            self.iterative_method = ResearchMethod(self.llm_provider)

        # Pattern memory
        self.memory = WritingPatternsMemory()

        # Load existing memory if path specified
        if self.config.persistence_path:
            self._load_memory()

    async def mine_from_papers(
        self,
        papers: list[dict[str, Any]],
        domain: str,
    ) -> WritingPatternsMemory:
        """Mine patterns from multiple papers.

        Args:
            papers: List of paper texts/metadata
            domain: Research domain

        Returns:
            WritingPatternsMemory with extracted patterns
        """
        logger.info(f"Mining patterns from {len(papers)} papers in {domain}")

        for i, paper in enumerate(papers):
            paper_id = paper.get("id", f"paper_{i}")
            text = paper.get("text", paper.get("abstract", ""))

            if not text:
                continue

            # Extract patterns from this paper
            patterns = await self._extract_patterns(text, paper_id, domain)

            # Add to memory
            for pattern in patterns:
                self.memory.add_pattern(pattern)

            # Auto-save if configured
            if self.config.auto_save and i % 10 == 0:
                self._save_memory()

        # Save final memory
        if self.config.auto_save:
            self._save_memory()

        logger.info(f"Mining complete: {self.memory.total_patterns} patterns")
        return self.memory

    async def _extract_patterns(
        self,
        text: str,
        paper_id: str,
        domain: str,
    ) -> list[WritingPattern]:
        """Extract patterns from a single paper.

        Args:
            text: Paper text
            paper_id: Paper identifier
            domain: Research domain

        Returns:
            List of extracted patterns
        """
        patterns = []
        datetime.now(UTC).isoformat()

        # Extract transitions
        transitions = await self._extract_transitions(text)
        for t in transitions[:5]:  # Top 5 transitions
            patterns.append(
                WritingPattern(
                    id=f"transition_{paper_id}_{len(patterns)}",
                    type=PatternType.TRANSITION,
                    domain=domain,
                    pattern_text=t,
                    source_papers=[paper_id],
                    tags=["transition", domain],
                )
            )

        # Extract hedging
        hedging = await self._extract_hedging(text)
        for h in hedging[:5]:
            patterns.append(
                WritingPattern(
                    id=f"hedging_{paper_id}_{len(patterns)}",
                    type=PatternType.HEDGING,
                    domain=domain,
                    pattern_text=h,
                    source_papers=[paper_id],
                    tags=["hedging", domain],
                )
            )

        # Extract section templates (if LLM available)
        if self.iterative_method:
            section_templates = await self._extract_section_templates(text)
            for st in section_templates[:3]:
                patterns.append(
                    WritingPattern(
                        id=f"section_{paper_id}_{len(patterns)}",
                        type=PatternType.SECTION_TEMPLATE,
                        domain=domain,
                        pattern_text=st["template"],
                        examples=[st.get("example", "")],
                        source_papers=[paper_id],
                        tags=["section", st.get("section", "unknown")],
                    )
                )

        return patterns

    async def _extract_transitions(self, text: str) -> list[str]:
        """Extract transition phrases from text.

        Args:
            text: Paper text

        Returns:
            List of transition phrases
        """
        # Use LLM if available
        if self.iterative_method:
            try:
                from berb.reasoning.base import ReasoningContext

                context = ReasoningContext(
                    stage_id="PATTERN_EXTRACTION",
                    stage_name="Extract Transitions",
                    input_data={
                        "task": "extract_transitions",
                        "text": text[:5000],  # Truncate
                    },
                )

                result = await self.iterative_method.execute(context)
                # Parse result (simplified)
                if isinstance(result.output, dict):
                    return result.output.get("transitions", [])
            except Exception as e:
                logger.warning(f"LLM transition extraction failed: {e}")

        # Fallback: keyword-based extraction
        import re

        transition_patterns = [
            r"(Furthermore[^,.]*[,\.])",
            r"(In contrast[^,.]*[,\.])",
            r"(Building on[^,.]*[,\.])",
            r"(However[^,.]*[,\.])",
            r"(Moreover[^,.]*[,\.])",
            r"(Additionally[^,.]*[,\.])",
            r"(Consequently[^,.]*[,\.])",
            r"(Therefore[^,.]*[,\.])",
        ]

        transitions = []
        for pattern in transition_patterns:
            matches = re.findall(pattern, text)
            transitions.extend(matches)

        return list(set(transitions))[:10]

    async def _extract_hedging(self, text: str) -> list[str]:
        """Extract hedging phrases from text.

        Args:
            text: Paper text

        Returns:
            List of hedging phrases
        """
        import re

        hedging_patterns = [
            r"(may (?:suggest|indicate|show))",
            r"(appears? to (?:be|suggest))",
            r"(potentially (?:useful|important))",
            r"(our results (?:suggest|indicate))",
            r"(it is (?:possible|likely) that)",
            r"(we (?:propose|suggest))",
        ]

        hedging = []
        for pattern in hedging_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            hedging.extend(matches)

        return list(set(hedging))[:10]

    async def _extract_section_templates(
        self,
        text: str,
    ) -> list[dict[str, Any]]:
        """Extract section templates from text.

        Args:
            text: Paper text

        Returns:
            List of section templates with metadata
        """
        # Split by sections
        sections = self._split_by_sections(text)

        templates = []
        for section_name, section_text in sections:
            # Extract first few sentences as template
            sentences = section_text.split(".")[:3]
            if sentences:
                template = ". ".join(sentences) + "."
                templates.append({
                    "section": section_name,
                    "template": template,
                    "example": section_text[:200],
                })

        return templates

    def _split_by_sections(
        self,
        text: str,
    ) -> list[tuple[str, str]]:
        """Split text by sections.

        Args:
            text: Full paper text

        Returns:
            List of (section_name, section_text) tuples
        """
        sections = []

        # Look for section headings
        heading_pattern = r"^##\s+(.+)$"
        matches = list(re.finditer(heading_pattern, text, re.MULTILINE))

        if matches:
            for i, match in enumerate(matches):
                section_name = match.group(1).strip().lower()
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                section_text = text[start:end].strip()
                sections.append((section_name, section_text))
        else:
            # No sections found, treat as introduction
            sections.append(("introduction", text))

        return sections

    def _save_memory(self) -> None:
        """Save memory to disk."""
        if not self.config.persistence_path:
            return

        try:
            path = Path(self.config.persistence_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.memory.to_json())
            logger.debug(f"Saved writing pattern memory to {path}")
        except Exception as e:
            logger.error(f"Failed to save writing pattern memory: {e}")

    def _load_memory(self) -> None:
        """Load memory from disk."""
        if not self.config.persistence_path:
            return

        path = Path(self.config.persistence_path)
        if not path.exists():
            return

        try:
            with open(path, encoding="utf-8") as f:
                json_str = f.read()
            self.memory = WritingPatternsMemory.from_json(json_str)
            logger.info(f"Loaded writing pattern memory from {path}")
        except Exception as e:
            logger.error(f"Failed to load writing pattern memory: {e}")


class WritingPatternRetriever:
    """Retrieves relevant writing patterns for generation.

    This retriever finds patterns from memory that are
    relevant to the current writing context.

    Usage::

        retriever = WritingPatternRetriever(memory)
        patterns = retriever.retrieve(section="introduction", domain="ml")
    """

    def __init__(self, memory: WritingPatternsMemory):
        """Initialize retriever.

        Args:
            memory: Writing patterns memory
        """
        self.memory = memory

    def retrieve(
        self,
        section: str | None = None,
        domain: str | None = None,
        pattern_type: PatternType | None = None,
        top_k: int = 10,
    ) -> list[WritingPattern]:
        """Retrieve relevant patterns.

        Args:
            section: Optional section filter
            domain: Optional domain filter
            pattern_type: Optional pattern type filter
            top_k: Number of patterns to return

        Returns:
            List of relevant patterns
        """
        if section:
            patterns = self.memory.get_patterns_for_section(section, domain)
        elif pattern_type:
            patterns = self.memory.get_patterns_by_type(pattern_type, domain)
        else:
            patterns = list(self.memory.patterns.values())

        # Filter by domain if specified
        if domain:
            patterns = [p for p in patterns if p.domain == domain]

        # Sort by frequency and effectiveness
        patterns = sorted(
            patterns,
            key=lambda p: (p.frequency * 0.7 + p.effectiveness_score * 0.3),
            reverse=True,
        )

        return patterns[:top_k]

    def get_patterns_as_prompt_context(
        self,
        section: str | None = None,
        domain: str | None = None,
    ) -> str:
        """Get patterns formatted as prompt context.

        Args:
            section: Optional section filter
            domain: Optional domain filter

        Returns:
            Formatted prompt context string
        """
        patterns = self.retrieve(section=section, domain=domain, top_k=20)

        if not patterns:
            return ""

        lines = ["## Writing Style Patterns", ""]

        # Group by type
        by_type: dict[str, list[WritingPattern]] = {}
        for p in patterns:
            type_name = p.type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(p)

        for type_name, type_patterns in by_type.items():
            lines.append(f"### {type_name.replace('_', ' ').title()}")
            for p in type_patterns[:5]:
                lines.append(f"- {p.pattern_text}")
            lines.append("")

        return "\n".join(lines)


# Convenience functions
async def mine_writing_patterns(
    papers: list[dict[str, Any]],
    domain: str,
    persistence_path: str | None = None,
    llm_provider: LLMProvider | None = None,
) -> WritingPatternsMemory:
    """Convenience function to mine writing patterns.

    Args:
        papers: List of paper texts/metadata
        domain: Research domain
        persistence_path: Optional path to save memory
        llm_provider: LLM provider

    Returns:
        WritingPatternsMemory
    """
    config = WritingPatternMemoryConfig(
        persistence_path=persistence_path,
        auto_save=True,
        llm_provider=llm_provider,
    )

    miner = WritingPatternMiner(llm_provider, config)
    return await miner.mine_from_papers(papers, domain)


def load_pattern_memory(
    persistence_path: str,
) -> WritingPatternsMemory:
    """Load pattern memory from disk.

    Args:
        persistence_path: Path to memory file

    Returns:
        WritingPatternsMemory
    """
    config = WritingPatternMemoryConfig(persistence_path=persistence_path)
    miner = WritingPatternMiner(config=config)
    return miner.memory
