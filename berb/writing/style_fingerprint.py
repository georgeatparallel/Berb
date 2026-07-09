"""Writing style fingerprinting engine for academic paper generation.

This module extracts writing style patterns from top-cited authors in a domain
and uses them to generate papers with similar stylistic characteristics.

Features:
- Author identification by citation count and language
- Style fingerprint extraction (sentence length, hedging, voice, etc.)
- Composite style profile generation
- Few-shot example selection for LLM prompts

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VocabularyLevel(StrEnum):
    """Vocabulary complexity levels."""

    ACCESSIBLE = "accessible"
    MODERATE = "moderate"
    DENSE = "dense"
    EXPERT = "expert"


class FirstPersonUsage(StrEnum):
    """First person usage frequency."""

    NEVER = "never"
    RARE = "rare"
    MODERATE = "moderate"
    FREQUENT = "frequent"


class AuthorProfile(BaseModel):
    """Profile of a cited author.

    Attributes:
        name: Author full name
        affiliation: Primary affiliation/institution
        country: Country code (ISO 3166-1)
        h_index: Author h-index
        total_citations: Total citation count
        top_papers: List of top-cited paper IDs/DOIs
        native_language: Inferred native language
    """

    name: str
    affiliation: str | None = None
    country: str | None = None
    h_index: int | None = None
    total_citations: int = 0
    top_papers: list[str] = Field(default_factory=list)
    native_language: str | None = None

    def is_native_english_speaker(self) -> bool:
        """Check if author is likely a native English speaker.

        Returns:
            True if affiliation country is primarily English-speaking
        """
        english_countries = {"US", "GB", "AU", "CA", "NZ", "IE"}
        return self.country in english_countries if self.country else False


class StyleFingerprint(BaseModel):
    """Composite writing style fingerprint extracted from top authors.

    Attributes:
        source_authors: Authors the style was extracted from
        avg_sentence_length: Average sentence length in words
        sentence_length_std: Standard deviation of sentence length
        avg_paragraph_sentences: Average sentences per paragraph
        vocabulary_level: Vocabulary complexity assessment
        hedging_frequency: Frequency of hedging phrases (0-1)
        passive_voice_ratio: Ratio of passive to active voice
        first_person_usage: First person pronoun usage frequency
        section_ratios: Target section length ratios
        citation_density: Citations per 100 words
        transition_patterns: Common transition phrases
        characteristic_phrases: Domain-specific characteristic phrases
        sample_paragraphs: Exemplar paragraphs for few-shot learning
    """

    source_authors: list[AuthorProfile] = Field(
        default_factory=list,
        description="Authors the style was extracted from",
    )

    # Sentence structure
    avg_sentence_length: float = Field(
        default=25.0,
        description="Average sentence length in words",
        ge=10.0,
        le=50.0,
    )
    sentence_length_std: float = Field(
        default=8.0,
        description="Standard deviation of sentence length",
    )
    avg_paragraph_sentences: float = Field(
        default=4.5,
        description="Average sentences per paragraph",
    )

    # Vocabulary and style
    vocabulary_level: VocabularyLevel = VocabularyLevel.MODERATE
    hedging_frequency: float = Field(
        default=0.3,
        description="Frequency of hedging phrases (0-1)",
        ge=0.0,
        le=1.0,
    )
    passive_voice_ratio: float = Field(
        default=0.25,
        description="Ratio of passive to active voice",
        ge=0.0,
        le=1.0,
    )
    first_person_usage: FirstPersonUsage = FirstPersonUsage.RARE

    # Structure
    section_ratios: dict[str, float] = Field(
        default_factory=lambda: {
            "introduction": 0.15,
            "related_work": 0.20,
            "methods": 0.25,
            "results": 0.20,
            "discussion": 0.15,
            "conclusion": 0.05,
        },
    )
    citation_density: float = Field(
        default=2.5,
        description="Citations per 100 words",
    )

    # Patterns
    transition_patterns: list[str] = Field(default_factory=list)
    characteristic_phrases: list[str] = Field(default_factory=list)
    sample_paragraphs: list[str] = Field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Convert style fingerprint to LLM prompt context.

        Returns:
            Formatted string for injection into writing prompts
        """
        lines = [
            "\n## Writing Style Guidelines",
            f"Based on analysis of {len(self.source_authors)} top-cited authors in the domain:",
        ]

        for author in self.source_authors[:3]:
            lines.append(f"  - {author.name} ({author.affiliation or 'Unknown'})")

        lines.extend(
            [
                "\n**Sentence Structure:**",
                f"  - Average sentence length: {self.avg_sentence_length:.1f} words (±{self.sentence_length_std:.1f})",
                f"  - Average paragraph: {self.avg_paragraph_sentences:.1f} sentences",
                "\n**Style Characteristics:**",
                f"  - Vocabulary level: {self.vocabulary_level.value}",
                f"  - Hedging frequency: {self.hedging_frequency:.0%}",
                f"  - Passive voice ratio: {self.passive_voice_ratio:.0%}",
                f"  - First person usage: {self.first_person_usage.value}",
                "\n**Paper Structure:**",
            ]
        )

        for section, ratio in self.section_ratios.items():
            lines.append(f"  - {section.replace('_', ' ').title()}: {ratio:.0%}")

        lines.append(f"\n**Citation Density:** {self.citation_density:.1f} per 100 words")

        if self.transition_patterns:
            lines.append(f"\n**Common Transitions:** {', '.join(self.transition_patterns[:5])}")

        if self.sample_paragraphs:
            lines.append("\n**Example Paragraphs for Reference:**")
            for i, para in enumerate(self.sample_paragraphs[:3], 1):
                lines.append(f"  Example {i}: {para[:100]}...")

        return "\n".join(lines)

    def compute_style_conformance_score(self, text: str) -> float:
        """Compute how well a text conforms to this style fingerprint.

        Args:
            text: Text to evaluate

        Returns:
            Conformance score (0-1, higher = more similar)
        """
        scores = []

        # Sentence length conformance
        sentences = self._extract_sentences(text)
        if sentences:
            avg_len = statistics.mean(len(s.split()) for s in sentences)
            len_diff = abs(avg_len - self.avg_sentence_length)
            len_score = max(0, 1 - (len_diff / self.avg_sentence_length))
            scores.append(len_score)

        # Hedging conformance
        hedging_count = self._count_hedging(text)
        total_words = len(text.split())
        if total_words > 0:
            hedging_freq = hedging_count / total_words
            hedging_diff = abs(hedging_freq - self.hedging_frequency)
            hedging_score = max(0, 1 - (hedging_diff * 10))
            scores.append(hedging_score)

        # First person conformance
        first_person_count = len(re.findall(r"\b(we|our|us|I|my|me)\b", text.lower()))
        fp_ratio = first_person_count / total_words if total_words > 0 else 0
        expected_fp = {
            FirstPersonUsage.NEVER: 0.0,
            FirstPersonUsage.RARE: 0.005,
            FirstPersonUsage.MODERATE: 0.015,
            FirstPersonUsage.FREQUENT: 0.03,
        }[self.first_person_usage]
        fp_diff = abs(fp_ratio - expected_fp)
        fp_score = max(0, 1 - (fp_diff * 50))
        scores.append(fp_score)

        return statistics.mean(scores) if scores else 0.5

    def _extract_sentences(self, text: str) -> list[str]:
        """Extract sentences from text."""
        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if s.strip() and len(s.split()) > 3]

    def _count_hedging(self, text: str) -> int:
        """Count hedging phrases in text."""
        hedging_patterns = [
            r"\bmay\b",
            r"\bmight\b",
            r"\bcould\b",
            r"\bsuggests?\b",
            r"\bappears?\b",
            r"\bseems?\b",
            r"\bpossibly\b",
            r"\bpotentially\b",
            r"\blikely\b",
            r"\bperhaps\b",
            r"\bapproximately\b",
            r"\bit is possible\b",
            r"\bwe propose\b",
            r"\bwe suggest\b",
        ]
        count = 0
        for pattern in hedging_patterns:
            count += len(re.findall(pattern, text.lower()))
        return count


@dataclass
class StyleExtractionResult:
    """Result of style extraction from papers.

    Attributes:
        fingerprint: Computed style fingerprint
        papers_analyzed: Number of papers analyzed
        authors_identified: Number of authors identified
        extraction_errors: Any errors encountered
    """

    fingerprint: StyleFingerprint
    papers_analyzed: int = 0
    authors_identified: int = 0
    extraction_errors: list[str] = field(default_factory=list)


class StyleFingerprintEngine:
    """Engine for extracting and applying writing style fingerprints.

    This engine:
    1. Identifies top-cited native-language speakers in a domain
    2. Extracts writing style patterns from their papers
    3. Builds composite style profiles
    4. Injects style constraints into writing prompts

    Attributes:
        http_client: HTTP client for fetching paper content
        target_language: Target language for style extraction
        num_target_authors: Number of authors to analyze
        papers_per_author: Papers to analyze per author
    """

    # Native English speaking countries
    ENGLISH_COUNTRIES = {"US", "GB", "AU", "CA", "NZ", "IE"}

    # Hedging phrases for detection
    HEDGING_PHRASES = [
        "may",
        "might",
        "could",
        "suggests",
        "suggest",
        "appears",
        "seems",
        "possibly",
        "potentially",
        "likely",
        "perhaps",
        "approximately",
        "it is possible",
        "we propose",
        "we suggest",
        "our results indicate",
        "this suggests",
        "may be",
    ]

    # Transition phrase patterns
    TRANSITION_PATTERNS = [
        "however",
        "furthermore",
        "moreover",
        "additionally",
        "in contrast",
        "similarly",
        "consequently",
        "therefore",
        "thus",
        "hence",
        "notably",
        "importantly",
    ]

    def __init__(
        self,
        target_language: str = "auto",
        num_target_authors: int = 3,
        papers_per_author: int = 5,
        http_client: httpx.AsyncClient | None = None,
    ):
        """Initialize style fingerprint engine.

        Args:
            target_language: Target language ("auto" for auto-detect)
            num_target_authors: Number of authors to analyze
            papers_per_author: Papers to analyze per author
            http_client: Optional HTTP client for fetching content
        """
        self.target_language = target_language
        self.num_target_authors = num_target_authors
        self.papers_per_author = papers_per_author
        self.http_client = http_client or httpx.AsyncClient()

        # Style analysis cache
        self._author_cache: dict[str, AuthorProfile] = {}
        self._paper_cache: dict[str, str] = {}

    async def identify_top_authors(
        self,
        domain: str,
        semantic_scholar_client: Any | None = None,
        openalex_client: Any | None = None,
    ) -> list[AuthorProfile]:
        """Identify top-cited authors in the domain.

        Args:
            domain: Research domain (e.g., "quantum computing")
            semantic_scholar_client: Optional Semantic Scholar client
            openalex_client: Optional OpenAlex client

        Returns:
            List of top author profiles
        """
        logger.info(f"Identifying top authors in domain: {domain}")

        authors: list[AuthorProfile] = []

        # Try Semantic Scholar first
        if semantic_scholar_client:
            try:
                authors = await self._search_authors_semantic_scholar(
                    domain, semantic_scholar_client
                )
            except Exception as e:
                logger.warning(f"Semantic Scholar search failed: {e}")

        # Fallback to OpenAlex
        if not authors and openalex_client:
            try:
                authors = await self._search_authors_openalex(domain, openalex_client)
            except Exception as e:
                logger.warning(f"OpenAlex search failed: {e}")

        # Filter for native speakers if target language is English
        if self._is_english_target():
            native_authors = [a for a in authors if a.is_native_english_speaker()]
            if len(native_authors) >= self.num_target_authors:
                authors = native_authors
                logger.info(f"Filtered to {len(authors)} native English speakers")

        # Fallback: use top authors regardless of language
        if len(authors) < self.num_target_authors:
            logger.warning(f"Only found {len(authors)} authors, using regardless of language")

        return authors[: self.num_target_authors]

    async def _search_authors_semantic_scholar(
        self, domain: str, client: Any
    ) -> list[AuthorProfile]:
        """Search authors via Semantic Scholar.

        Args:
            domain: Research domain
            client: Semantic Scholar client instance

        Returns:
            List of author profiles
        """
        # Search for papers in domain
        papers = await client.search_papers(
            query=domain,
            limit=self.num_target_authors * self.papers_per_author,
        )

        # Extract authors from papers
        author_papers: dict[str, list[dict]] = {}
        for paper in papers:
            for author in paper.get("authors", []):
                name = author.get("name", "Unknown")
                if name not in author_papers:
                    author_papers[name] = []
                author_papers[name].append(paper)

        # Build author profiles sorted by citation count
        profiles = []
        for name, paper_list in author_papers.items():
            total_citations = sum(p.get("citationCount", 0) for p in paper_list)
            profiles.append(
                AuthorProfile(
                    name=name,
                    total_citations=total_citations,
                    top_papers=[p.get("paperId", "") for p in paper_list[:5]],
                )
            )

        # Sort by citations
        profiles.sort(key=lambda a: a.total_citations, reverse=True)
        return profiles

    async def _search_authors_openalex(self, domain: str, client: Any) -> list[AuthorProfile]:
        """Search authors via OpenAlex.

        Args:
            domain: Research domain
            client: OpenAlex client instance

        Returns:
            List of author profiles
        """
        # Search for works in domain
        works = await client.search_works(
            query=domain,
            limit=self.num_target_authors * self.papers_per_author,
        )

        # Extract authors
        author_works: dict[str, list[dict]] = {}
        for work in works:
            for author in work.get("authorships", []):
                name = author.get("author", {}).get("display_name", "Unknown")
                if name not in author_works:
                    author_works[name] = []
                author_works[name].append(work)

        # Build profiles
        profiles = []
        for name, work_list in author_works.items():
            total_cites = sum(w.get("cited_by_count", 0) for w in work_list)
            profiles.append(
                AuthorProfile(
                    name=name,
                    total_citations=total_cites,
                    top_papers=[w.get("id", "") for w in work_list[:5]],
                )
            )

        profiles.sort(key=lambda a: a.total_citations, reverse=True)
        return profiles

    async def extract_style_from_authors(
        self,
        authors: list[AuthorProfile],
        paper_texts: dict[str, str] | None = None,
    ) -> StyleFingerprint:
        """Extract style fingerprint from authors' papers.

        Args:
            authors: List of author profiles
            paper_texts: Optional pre-fetched paper texts

        Returns:
            Composite style fingerprint
        """
        logger.info(f"Extracting style from {len(authors)} authors")

        all_sentences: list[list[str]] = []
        all_paragraphs: list[list[str]] = []
        all_hedging_counts: list[int] = []
        all_passive_counts: list[int] = []
        all_first_person_counts: list[int] = []
        total_words = 0

        sample_paragraphs: list[str] = []

        for author in authors:
            # Get paper texts
            texts = await self._get_author_papers(author, paper_texts)

            for text in texts:
                # Extract sentences
                sentences = self._extract_sentences(text)
                if sentences:
                    all_sentences.append(sentences)

                # Extract paragraphs
                paragraphs = self._extract_paragraphs(text)
                if paragraphs:
                    all_paragraphs.append(paragraphs)
                    # Collect sample paragraphs
                    sample_paragraphs.extend(paragraphs[:2])

                # Count style markers
                words = text.split()
                total_words += len(words)
                all_hedging_counts.append(self._count_hedging(text))
                all_passive_counts.append(self._count_passive_voice(text))
                all_first_person_counts.append(self._count_first_person(text))

        # Compute aggregate statistics
        if not all_sentences:
            return StyleFingerprint(source_authors=authors)

        # Sentence length statistics, in WORDS (matching the field's documented
        # unit and compute_style_conformance_score's own len(s.split()) usage).
        # This previously used len(s) — character count, not word count —
        # which both violated the field's semantics and could overshoot the
        # StyleFingerprint.avg_sentence_length Pydantic bound (le=50.0),
        # raising a ValidationError that silently killed the whole feature.
        all_sentence_lengths = [len(s.split()) for sentences in all_sentences for s in sentences]
        avg_sentence_length = (
            statistics.mean(all_sentence_lengths) if all_sentence_lengths else 25.0
        )
        avg_sentence_length = max(10.0, min(50.0, avg_sentence_length))
        sentence_length_std = (
            statistics.stdev(all_sentence_lengths) if len(all_sentence_lengths) > 1 else 8.0
        )

        # Paragraph statistics
        paragraph_lengths = [len(p) for paragraphs in all_paragraphs for p in paragraphs]
        avg_paragraph_sentences = statistics.mean(paragraph_lengths) if paragraph_lengths else 4.5

        # Hedging frequency
        total_hedging = sum(all_hedging_counts)
        hedging_frequency = total_hedging / total_words if total_words > 0 else 0.3

        # Passive voice ratio
        total_passive = sum(all_passive_counts)
        passive_voice_ratio = total_passive / total_words if total_words > 0 else 0.25

        # First person usage
        total_first_person = sum(all_first_person_counts)
        fp_ratio = total_first_person / total_words if total_words > 0 else 0.005
        first_person_usage = self._classify_first_person(fp_ratio)

        # Vocabulary level (simplified - based on avg word length)
        vocabulary_level = self._estimate_vocabulary_level(all_sentence_lengths)

        # Build fingerprint
        fingerprint = StyleFingerprint(
            source_authors=authors,
            avg_sentence_length=avg_sentence_length,
            sentence_length_std=sentence_length_std,
            avg_paragraph_sentences=avg_paragraph_sentences,
            vocabulary_level=vocabulary_level,
            hedging_frequency=min(hedging_frequency * 100, 1.0),  # Normalize
            passive_voice_ratio=min(passive_voice_ratio * 10, 1.0),
            first_person_usage=first_person_usage,
            sample_paragraphs=sample_paragraphs[:5],  # Top 5 samples
        )

        logger.info(
            f"Extracted style: avg_sentence={avg_sentence_length:.1f}, "
            f"hedging={hedging_frequency:.3f}, passive={passive_voice_ratio:.3f}"
        )

        return fingerprint

    async def _get_author_papers(
        self,
        author: AuthorProfile,
        paper_texts: dict[str, str] | None = None,
    ) -> list[str]:
        """Get paper texts for an author.

        Args:
            author: Author profile
            paper_texts: Optional pre-fetched texts

        Returns:
            List of paper texts
        """
        texts = []

        if paper_texts:
            # Use pre-fetched texts
            for paper_id in author.top_papers[: self.papers_per_author]:
                if paper_id in paper_texts:
                    texts.append(paper_texts[paper_id])
        else:
            # Fetch papers
            for paper_id in author.top_papers[: self.papers_per_author]:
                try:
                    text = await self._fetch_paper_text(paper_id)
                    if text:
                        texts.append(text)
                        self._paper_cache[paper_id] = text
                except Exception as e:
                    logger.warning(f"Failed to fetch paper {paper_id}: {e}")

        return texts

    async def _fetch_paper_text(self, paper_id: str) -> str | None:
        """Fetch full text of a paper.

        Args:
            paper_id: Paper identifier (DOI, arXiv ID, etc.)

        Returns:
            Paper text or None
        """
        # Try arXiv first
        if paper_id.startswith("arXiv:") or len(paper_id) == 8:
            arxiv_id = paper_id.replace("arXiv:", "")
            url = f"https://arxiv.org/abs/{arxiv_id}"
            try:
                # self.http_client is a long-lived instance member, not a
                # per-call context manager: `async with self.http_client`
                # would call __aexit__ and close the connection pool after
                # the FIRST fetch, breaking every subsequent call in the
                # same engine's lifetime (e.g. the loop in _get_author_papers
                # over multiple papers/authors).
                response = await self.http_client.get(url, timeout=30)
                if response.status_code == 200:
                    # Extract abstract at minimum
                    # Full text would require PDF parsing
                    return self._extract_arxiv_abstract(response.text)
            except Exception:
                pass

        # For other papers, would need PDF parsing or API access
        return None

    def _extract_arxiv_abstract(self, html: str) -> str:
        """Extract abstract from arXiv HTML.

        Args:
            html: arXiv page HTML

        Returns:
            Abstract text
        """
        match = re.search(
            r'<blockquote class="abstract[^>]*>(.*?)</blockquote>',
            html,
            re.DOTALL,
        )
        if match:
            abstract = match.group(1)
            # Remove HTML tags
            abstract = re.sub(r"<[^>]+>", "", abstract)
            return abstract.strip()
        return ""

    def _extract_sentences(self, text: str) -> list[str]:
        """Extract sentences from text.

        Args:
            text: Input text

        Returns:
            List of sentences
        """
        # Split on sentence boundaries
        sentences = re.split(r"(?<=[.!?])\s+", text)
        # Filter short fragments
        return [s.strip() for s in sentences if len(s.split()) > 5]

    def _extract_paragraphs(self, text: str) -> list[str]:
        """Extract paragraphs from text.

        Args:
            text: Input text

        Returns:
            List of paragraphs
        """
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if len(p.split()) > 20]

    def _count_hedging(self, text: str) -> int:
        """Count hedging phrases in text.

        Args:
            text: Input text

        Returns:
            Count of hedging phrases
        """
        text_lower = text.lower()
        count = 0
        for phrase in self.HEDGING_PHRASES:
            count += text_lower.count(phrase)
        return count

    def _count_passive_voice(self, text: str) -> int:
        """Estimate passive voice usage.

        Args:
            text: Input text

        Returns:
            Count of passive voice constructions
        """
        # Simple heuristic: "be" + past participle patterns
        passive_patterns = [
            r"\b(is|are|was|were|be|been|being)\s+\w+ed\b",
            r"\b(is|are|was|were)\s+(shown|demonstrated|observed|found|reported)\b",
        ]
        count = 0
        for pattern in passive_patterns:
            count += len(re.findall(pattern, text.lower()))
        return count

    def _count_first_person(self, text: str) -> int:
        """Count first person pronouns.

        Args:
            text: Input text

        Returns:
            Count of first person pronouns
        """
        patterns = [r"\bwe\b", r"\bour\b", r"\bus\b", r"\bI\b", r"\bmy\b", r"\bme\b"]
        count = 0
        for pattern in patterns:
            count += len(re.findall(pattern, text.lower()))
        return count

    def _classify_first_person(self, ratio: float) -> FirstPersonUsage:
        """Classify first person usage frequency.

        Args:
            ratio: First person pronouns per word

        Returns:
            FirstPersonUsage classification
        """
        if ratio < 0.002:
            return FirstPersonUsage.NEVER
        elif ratio < 0.01:
            return FirstPersonUsage.RARE
        elif ratio < 0.02:
            return FirstPersonUsage.MODERATE
        else:
            return FirstPersonUsage.FREQUENT

    def _estimate_vocabulary_level(self, sentence_lengths: list[int]) -> VocabularyLevel:
        """Estimate vocabulary complexity level.

        Args:
            sentence_lengths: List of sentence lengths

        Returns:
            VocabularyLevel estimate
        """
        if not sentence_lengths:
            return VocabularyLevel.MODERATE

        avg_len = statistics.mean(sentence_lengths)

        if avg_len < 20:
            return VocabularyLevel.ACCESSIBLE
        elif avg_len < 28:
            return VocabularyLevel.MODERATE
        elif avg_len < 35:
            return VocabularyLevel.DENSE
        else:
            return VocabularyLevel.EXPERT

    def _is_english_target(self) -> bool:
        """Check if target language is English.

        Returns:
            True if targeting English
        """
        if self.target_language == "auto":
            return True  # Default to English
        return self.target_language.lower() in {"en", "english"}


class StyleMimicryConfig(BaseModel):
    """Configuration for style mimicry.

    Attributes:
        enabled: Whether style mimicry is enabled
        num_target_authors: Number of authors to analyze
        papers_per_author: Papers to analyze per author
        target_language: Target language for style extraction
        style_weight: Weight of style constraints (0-1)
        fallback_style: Fallback style if authors unavailable
    """

    enabled: bool = True
    num_target_authors: int = 3
    papers_per_author: int = 5
    target_language: str = "auto"
    style_weight: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Weight of style constraints in prompts",
    )
    fallback_style: str = "nature"  # Use Nature journal style as fallback


async def create_style_fingerprint(
    domain: str,
    config: StyleMimicryConfig | None = None,
    semantic_scholar_client: Any | None = None,
    openalex_client: Any | None = None,
) -> StyleFingerprint:
    """Convenience function to create style fingerprint.

    Args:
        domain: Research domain
        config: Style mimicry configuration
        semantic_scholar_client: Optional Semantic Scholar client
        openalex_client: Optional OpenAlex client

    Returns:
        Style fingerprint for the domain
    """
    config = config or StyleMimicryConfig()

    engine = StyleFingerprintEngine(
        target_language=config.target_language,
        num_target_authors=config.num_target_authors,
        papers_per_author=config.papers_per_author,
    )

    # Identify authors
    authors = await engine.identify_top_authors(
        domain,
        semantic_scholar_client=semantic_scholar_client,
        openalex_client=openalex_client,
    )

    # Extract style
    fingerprint = await engine.extract_style_from_authors(authors)

    return fingerprint
