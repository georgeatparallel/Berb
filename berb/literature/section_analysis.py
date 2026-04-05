"""Section-aware citation analysis for intelligent citation placement.

This module tracks where papers are cited (Introduction/Methods/Results/Discussion)
and provides recommendations for citation placement based on existing patterns.

Uses Iterative reasoning for section classification and placement optimization.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from berb.reasoning.research import ResearchMethod
from berb.llm.client import LLMProvider

logger = logging.getLogger(__name__)


class PaperSection(str, Enum):
    """Standard paper sections.

    Attributes:
        ABSTRACT: Paper abstract
        INTRODUCTION: Introduction section
        RELATED_WORK: Related work / Literature review
        METHODS: Methods / Methodology
        RESULTS: Results / Experiments
        DISCUSSION: Discussion / Analysis
        CONCLUSION: Conclusion
        APPENDIX: Appendix / Supplementary
    """

    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    RELATED_WORK = "related_work"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    APPENDIX = "appendix"


class CitationPurpose(str, Enum):
    """Purpose of a citation in context.

    Attributes:
        BACKGROUND: Providing background context
        METHOD_REFERENCE: Referencing a method used
        COMPARISON: Comparing results
        SUPPORT: Supporting a claim
        CONTRAST: Contrasting with prior work
        EXTENSION: Extending prior work
        MOTIVATION: Motivating the current work
    """

    BACKGROUND = "background"
    METHOD_REFERENCE = "method_reference"
    COMPARISON = "comparison"
    SUPPORT = "support"
    CONTRAST = "contrast"
    EXTENSION = "extension"
    MOTIVATION = "motivation"


class SectionCitation(BaseModel):
    """A citation within a specific section.

    Attributes:
        paper_id: Cited paper identifier
        section: Section where citation appears
        purpose: Purpose of the citation
        context: Surrounding text context
        position: Position in section (early/middle/late)
        paragraph_number: Paragraph number in section
    """

    paper_id: str
    section: PaperSection
    purpose: CitationPurpose = CitationPurpose.BACKGROUND
    context: str = ""
    position: Literal["early", "middle", "late"] = "middle"
    paragraph_number: int = 0


class PaperCitationProfile(BaseModel):
    """Citation profile for a paper.

    Attributes:
        paper_id: Paper identifier
        title: Paper title
        section_distribution: Citations per section
        primary_purpose: Most common citation purpose
        total_citations: Total citation count
        citation_contexts: List of citation contexts
    """

    paper_id: str
    title: str = ""
    section_distribution: dict[str, int] = Field(default_factory=dict)
    primary_purpose: CitationPurpose = CitationPurpose.BACKGROUND
    total_citations: int = 0
    citation_contexts: list[SectionCitation] = Field(default_factory=list)

    def get_primary_section(self) -> PaperSection | None:
        """Get the section where this paper is most cited.

        Returns:
            Primary section or None
        """
        if not self.section_distribution:
            return None

        return PaperSection(
            max(self.section_distribution, key=self.section_distribution.get)
        )


class CitationRecommendation(BaseModel):
    """Recommendation for citation placement.

    Attributes:
        paper_id: Paper to cite
        recommended_section: Where to cite
        recommended_purpose: Why to cite
        confidence: Recommendation confidence (0-1)
        reasoning: Explanation for recommendation
        alternative_sections: Alternative placement options
    """

    paper_id: str
    recommended_section: PaperSection
    recommended_purpose: CitationPurpose
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    alternative_sections: list[PaperSection] = Field(default_factory=list)


class SectionCitationAnalysis(BaseModel):
    """Complete section citation analysis.

    Attributes:
        paper_text: Analyzed paper text
        citations: All extracted citations
        papers_profile: Profile per cited paper
        section_summary: Summary statistics per section
        recommendations: Placement recommendations
    """

    paper_text: str = ""
    citations: list[SectionCitation] = Field(default_factory=list)
    papers_profile: dict[str, PaperCitationProfile] = Field(default_factory=dict)
    section_summary: dict[str, dict[str, Any]] = Field(default_factory=dict)
    recommendations: list[CitationRecommendation] = Field(default_factory=list)


class SectionAnalysisConfig(BaseModel):
    """Configuration for section analysis.

    Attributes:
        use_llm: Whether to use LLM for section classification
        llm_provider: LLM provider
        detect_sections_auto: Auto-detect sections from text
        citation_pattern: Citation pattern to match
    """

    use_llm: bool = True
    llm_provider: LLMProvider | None = None
    detect_sections_auto: bool = True
    citation_pattern: str = r"\[\d+\]|\([A-Z][a-z]+,\s*\d{4}\)"


class SectionCitationAnalyzer:
    """Analyzer for section-aware citation analysis.

    This analyzer:
    1. Extracts citations from paper text
    2. Identifies section for each citation
    3. Classifies citation purpose
    4. Builds citation profiles per paper
    5. Recommends optimal citation placement

    Usage::

        analyzer = SectionCitationAnalyzer(
            config=SectionAnalysisConfig(
                use_llm=True,
                llm_provider=llm_provider,
            ),
        )

        analysis = await analyzer.analyze(paper_text)
        recommendations = analysis.recommendations
    """

    # Section keywords for detection
    SECTION_KEYWORDS = {
        PaperSection.ABSTRACT: ["abstract", "summary"],
        PaperSection.INTRODUCTION: ["introduction", "intro", "background"],
        PaperSection.RELATED_WORK: [
            "related work", "related works", "literature review",
            "prior work", "previous work", "background"
        ],
        PaperSection.METHODS: [
            "methods", "methodology", "approach", "technique",
            "model", "architecture", "algorithm", "implementation"
        ],
        PaperSection.RESULTS: [
            "results", "experiments", "evaluation", "findings",
            "outcomes", "performance"
        ],
        PaperSection.DISCUSSION: [
            "discussion", "analysis", "interpretation",
            "implications", "limitations"
        ],
        PaperSection.CONCLUSION: [
            "conclusion", "concluding", "summary", "future work"
        ],
        PaperSection.APPENDIX: ["appendix", "supplementary", "appendix"],
    }

    # Purpose keywords
    PURPOSE_KEYWORDS = {
        CitationPurpose.BACKGROUND: ["is known to", "has been shown", "widely used"],
        CitationPurpose.METHOD_REFERENCE: ["we use", "based on", "following", "adopt"],
        CitationPurpose.COMPARISON: ["compared to", "outperforms", "better than", "vs"],
        CitationPurpose.SUPPORT: ["consistent with", "confirms", "supports", "agrees with"],
        CitationPurpose.CONTRAST: ["however", "in contrast", "unlike", "differs from"],
        CitationPurpose.EXTENSION: ["extend", "build on", "improve upon", "generalize"],
        CitationPurpose.MOTIVATION: ["motivated by", "inspired by", "to address"],
    }

    def __init__(self, config: SectionAnalysisConfig | None = None):
        """Initialize section citation analyzer.

        Args:
            config: Configuration
        """
        self.config = config or SectionAnalysisConfig()

        # Initialize iterative method for section classification
        self.iterative_method = None
        if self.config.llm_provider and self.config.use_llm:
            self.iterative_method = ResearchMethod(self.config.llm_provider)

        # Citation cache
        self._citation_cache: dict[str, SectionCitation] = {}

    async def analyze(
        self,
        paper_text: str,
        cited_papers: dict[str, dict[str, Any]] | None = None,
    ) -> SectionCitationAnalysis:
        """Analyze citations in paper text.

        Args:
            paper_text: Full paper text
            cited_papers: Optional metadata for cited papers

        Returns:
            SectionCitationAnalysis
        """
        logger.info(f"Analyzing citations in paper ({len(paper_text)} chars)")

        # Extract citations with sections
        citations = await self._extract_section_citations(paper_text)

        # Build paper profiles
        profiles = self._build_paper_profiles(citations, cited_papers)

        # Generate section summary
        section_summary = self._generate_section_summary(citations)

        # Generate recommendations
        recommendations = await self._generate_recommendations(
            citations, profiles, paper_text
        )

        analysis = SectionCitationAnalysis(
            paper_text=paper_text,
            citations=citations,
            papers_profile=profiles,
            section_summary=section_summary,
            recommendations=recommendations,
        )

        logger.info(
            f"Analysis complete: {len(citations)} citations, "
            f"{len(profiles)} unique papers"
        )

        return analysis

    async def _extract_section_citations(
        self,
        paper_text: str,
    ) -> list[SectionCitation]:
        """Extract citations with section information.

        Args:
            paper_text: Full paper text

        Returns:
            List of SectionCitation objects
        """
        citations = []

        # Split paper into sections
        sections = self._split_into_sections(paper_text)

        # Extract citations from each section
        for section_name, section_text, start_pos in sections:
            section_citations = self._extract_citations_from_text(
                section_text, section_name, start_pos
            )
            citations.extend(section_citations)

        return citations

    def _split_into_sections(
        self,
        text: str,
    ) -> list[tuple[PaperSection, str, int]]:
        """Split paper text into sections.

        Args:
            text: Full paper text

        Returns:
            List of (section, text, start_position) tuples
        """
        sections = []

        if self.config.detect_sections_auto:
            # Detect sections from headings
            section_positions = self._detect_section_positions(text)

            if section_positions:
                for i, (section, start_pos) in enumerate(section_positions):
                    end_pos = (
                        section_positions[i + 1][1]
                        if i + 1 < len(section_positions)
                        else len(text)
                    )
                    section_text = text[start_pos:end_pos]
                    sections.append((section, section_text, start_pos))
                return sections

        # Fallback: treat entire text as one section
        sections.append((PaperSection.INTRODUCTION, text, 0))
        return sections

    def _detect_section_positions(
        self,
        text: str,
    ) -> list[tuple[PaperSection, int]]:
        """Detect section positions from headings.

        Args:
            text: Full paper text

        Returns:
            List of (section, position) tuples
        """
        positions = []

        # Look for section headings (markdown style or numbered)
        heading_patterns = [
            (r"^#\s+(.+)$", re.MULTILINE),  # # Heading
            (r"^##\s+(.+)$", re.MULTILINE),  # ## Heading
            (r"^\d+\.\s+(.+)$", re.MULTILINE),  # 1. Heading
            (r"^[A-Z][A-Z\s]+$", re.MULTILINE),  # ALL CAPS
        ]

        for pattern, flags in heading_patterns:
            for match in re.finditer(pattern, text, flags):
                heading = match.group(1).strip().lower()
                position = match.start()

                # Match heading to section
                section = self._match_heading_to_section(heading)
                if section:
                    positions.append((section, position))

        # Sort by position
        positions.sort(key=lambda x: x[1])

        return positions

    def _match_heading_to_section(
        self,
        heading: str,
    ) -> PaperSection | None:
        """Match heading text to PaperSection.

        Args:
            heading: Heading text

        Returns:
            PaperSection or None
        """
        heading_lower = heading.lower()

        for section, keywords in self.SECTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in heading_lower:
                    return section

        return None

    def _extract_citations_from_text(
        self,
        text: str,
        section_name: str,
        start_pos: int,
    ) -> list[SectionCitation]:
        """Extract citations from text section.

        Args:
            text: Section text
            section_name: Section name
            start_pos: Start position in full text

        Returns:
            List of SectionCitation
        """
        citations = []

        # Find citation patterns
        pattern = self.config.citation_pattern
        for match in re.finditer(pattern, text):
            citation_text = match.group()
            position = match.start()

            # Determine position in section (early/middle/late)
            section_len = len(text)
            if position < section_len * 0.33:
                pos_label = "early"
            elif position < section_len * 0.66:
                pos_label = "middle"
            else:
                pos_label = "late"

            # Get surrounding context
            context_start = max(0, position - 100)
            context_end = min(len(text), position + len(citation_text) + 100)
            context = text[context_start:context_end]

            # Extract paper ID from citation
            paper_id = self._extract_paper_id(citation_text)

            # Determine purpose
            purpose = self._determine_citation_purpose(context)

            # Determine paragraph number
            paragraph_num = text[:position].count("\n\n")

            citation = SectionCitation(
                paper_id=paper_id,
                section=PaperSection(section_name) if section_name in [s.value for s in PaperSection] else PaperSection.INTRODUCTION,
                purpose=purpose,
                context=context,
                position=pos_label,
                paragraph_number=paragraph_num,
            )

            citations.append(citation)
            self._citation_cache[f"{section_name}:{position}"] = citation

        return citations

    def _extract_paper_id(self, citation_text: str) -> str:
        """Extract paper ID from citation text.

        Args:
            citation_text: Citation text (e.g., "[12]" or "(Smith, 2024)")

        Returns:
            Paper ID
        """
        # Numeric citation
        numeric_match = re.search(r"\[(\d+)\]", citation_text)
        if numeric_match:
            return f"paper_{numeric_match.group(1)}"

        # Author-year citation
        author_year_match = re.search(r"\(([A-Z][a-z]+),?\s*(\d{4})\)", citation_text)
        if author_year_match:
            author = author_year_match.group(1)
            year = author_year_match.group(2)
            return f"{author}_{year}"

        return citation_text.strip("[]()")

    def _determine_citation_purpose(
        self,
        context: str,
    ) -> CitationPurpose:
        """Determine purpose of citation from context.

        Args:
            context: Surrounding text

        Returns:
            CitationPurpose
        """
        context_lower = context.lower()

        # Check for purpose keywords
        for purpose, keywords in self.PURPOSE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in context_lower:
                    return purpose

        # Default to background
        return CitationPurpose.BACKGROUND

    def _build_paper_profiles(
        self,
        citations: list[SectionCitation],
        cited_papers: dict[str, dict[str, Any]] | None,
    ) -> dict[str, PaperCitationProfile]:
        """Build citation profiles for each cited paper.

        Args:
            citations: List of citations
            cited_papers: Optional paper metadata

        Returns:
            Dictionary of paper profiles
        """
        profiles: dict[str, PaperCitationProfile] = {}

        for citation in citations:
            paper_id = citation.paper_id

            if paper_id not in profiles:
                # Get title from metadata if available
                title = ""
                if cited_papers and paper_id in cited_papers:
                    title = cited_papers[paper_id].get("title", "")

                profiles[paper_id] = PaperCitationProfile(
                    paper_id=paper_id,
                    title=title,
                )

            # Update section distribution
            section = citation.section.value
            profiles[paper_id].section_distribution[section] = (
                profiles[paper_id].section_distribution.get(section, 0) + 1
            )
            profiles[paper_id].total_citations += 1
            profiles[paper_id].citation_contexts.append(citation)

        # Determine primary purpose for each paper
        for profile in profiles.values():
            purpose_counts: dict[str, int] = {}
            for ctx in profile.citation_contexts:
                purpose = ctx.purpose.value
                purpose_counts[purpose] = purpose_counts.get(purpose, 0) + 1

            if purpose_counts:
                primary = max(purpose_counts, key=purpose_counts.get)
                profile.primary_purpose = CitationPurpose(primary)

        return profiles

    def _generate_section_summary(
        self,
        citations: list[SectionCitation],
    ) -> dict[str, dict[str, Any]]:
        """Generate summary statistics per section.

        Args:
            citations: List of citations

        Returns:
            Summary dictionary per section
        """
        summary: dict[str, dict[str, Any]] = {}

        for section in PaperSection:
            section_citations = [c for c in citations if c.section == section]

            if section_citations:
                # Count by purpose
                purpose_counts: dict[str, int] = {}
                for c in section_citations:
                    purpose = c.purpose.value
                    purpose_counts[purpose] = purpose_counts.get(purpose, 0) + 1

                # Count by position
                position_counts: dict[str, int] = {}
                for c in section_citations:
                    pos = c.position
                    position_counts[pos] = position_counts.get(pos, 0) + 1

                summary[section.value] = {
                    "total_citations": len(section_citations),
                    "by_purpose": purpose_counts,
                    "by_position": position_counts,
                    "unique_papers": len(set(c.paper_id for c in section_citations)),
                }

        return summary

    async def _generate_recommendations(
        self,
        citations: list[SectionCitation],
        profiles: dict[str, PaperCitationProfile],
        paper_text: str,
    ) -> list[CitationRecommendation]:
        """Generate citation placement recommendations.

        Args:
            citations: List of citations
            profiles: Paper profiles
            paper_text: Full paper text

        Returns:
            List of recommendations
        """
        recommendations = []

        # For each cited paper, recommend optimal placement
        for paper_id, profile in profiles.items():
            primary_section = profile.get_primary_section()
            primary_purpose = profile.primary_purpose

            if primary_section:
                # Calculate confidence based on distribution concentration
                total = profile.total_citations
                primary_count = profile.section_distribution.get(primary_section.value, 0)
                confidence = primary_count / total if total > 0 else 0.5

                # Find alternative sections
                alternatives = sorted(
                    profile.section_distribution.keys(),
                    key=lambda s: profile.section_distribution[s],
                    reverse=True,
                )[1:3]

                recommendation = CitationRecommendation(
                    paper_id=paper_id,
                    recommended_section=primary_section,
                    recommended_purpose=primary_purpose,
                    confidence=confidence,
                    reasoning=self._generate_reasoning(profile),
                    alternative_sections=[
                        PaperSection(s) for s in alternatives
                    ],
                )
                recommendations.append(recommendation)

        return recommendations

    def _generate_reasoning(
        self,
        profile: PaperCitationProfile,
    ) -> str:
        """Generate reasoning for recommendation.

        Args:
            profile: Paper profile

        Returns:
            Reasoning text
        """
        primary_section = profile.get_primary_section()
        primary_purpose = profile.primary_purpose

        reasoning_parts = [
            f"This paper is primarily cited in the {primary_section.value} section",
        ]

        if primary_purpose != CitationPurpose.BACKGROUND:
            reasoning_parts.append(
                f"typically for {primary_purpose.value.replace('_', ' ')}"
            )

        reasoning_parts.append(
            f"({profile.total_citations} total citations)"
        )

        return " ".join(reasoning_parts)

    def recommend_placement(
        self,
        paper_to_cite: str,
        target_section: str | None = None,
        current_text: str = "",
    ) -> CitationRecommendation | None:
        """Recommend citation placement for a specific paper.

        Args:
            paper_to_cite: Paper ID to cite
            target_section: Optional target section
            current_text: Current paper text

        Returns:
            CitationRecommendation or None
        """
        # Check cache
        if paper_to_cite in self._citation_cache:
            cached = self._citation_cache[paper_to_cite]
            return CitationRecommendation(
                paper_id=paper_to_cite,
                recommended_section=cached.section,
                recommended_purpose=cached.purpose,
                confidence=0.8,
                reasoning="Based on existing citation pattern",
            )

        # Default recommendation
        if target_section:
            return CitationRecommendation(
                paper_id=paper_to_cite,
                recommended_section=PaperSection(target_section),
                recommended_purpose=CitationPurpose.BACKGROUND,
                confidence=0.5,
                reasoning="Default recommendation based on target section",
            )

        return None


class CitationPlacementOptimizer:
    """Optimizer for citation placement in generated text.

    This optimizer uses iterative reasoning to suggest
    optimal citation placements during paper generation.

    Usage::

        optimizer = CitationPlacementOptimizer(llm_provider)
        suggestions = await optimizer.optimize(draft_text, references)
    """

    def __init__(self, llm_provider: LLMProvider | None = None):
        """Initialize optimizer.

        Args:
            llm_provider: LLM provider
        """
        self.llm_provider = llm_provider
        self.analyzer = SectionCitationAnalyzer(
            config=SectionAnalysisConfig(
                use_llm=llm_provider is not None,
                llm_provider=llm_provider,
            ),
        )

    async def optimize(
        self,
        draft_text: str,
        references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Optimize citation placement in draft.

        Args:
            draft_text: Draft paper text
            references: List of reference metadata

        Returns:
            List of placement suggestions
        """
        # Analyze current citations
        analysis = await self.analyzer.analyze(draft_text)

        suggestions = []

        # Find sections with low citation density
        for section, summary in analysis.section_summary.items():
            if summary["total_citations"] < 3:
                suggestions.append({
                    "section": section,
                    "issue": "low_citation_density",
                    "recommendation": f"Add more citations to {section} section",
                    "priority": "medium",
                })

        # Find papers that should be cited but aren't
        cited_ids = set(c.paper_id for c in analysis.citations)
        for ref in references:
            ref_id = ref.get("id", ref.get("doi", ""))
            if ref_id and ref_id not in cited_ids:
                # Recommend where to cite
                primary_section = self._infer_section_for_reference(ref)
                suggestions.append({
                    "paper_id": ref_id,
                    "issue": "missing_citation",
                    "recommendation": f"Cite in {primary_section} section",
                    "priority": "high",
                })

        return suggestions

    def _infer_section_for_reference(
        self,
        reference: dict[str, Any],
    ) -> str:
        """Infer best section for citing a reference.

        Args:
            reference: Reference metadata

        Returns:
            Recommended section name
        """
        # Check reference type
        ref_type = reference.get("type", "").lower()

        if "method" in ref_type or "algorithm" in ref_type:
            return "methods"
        elif "survey" in ref_type or "review" in ref_type:
            return "related_work"
        elif "dataset" in ref_type:
            return "methods"
        else:
            return "related_work"


# Convenience function
async def analyze_section_citations(
    paper_text: str,
    cited_papers: dict[str, dict[str, Any]] | None = None,
    llm_provider: LLMProvider | None = None,
) -> SectionCitationAnalysis:
    """Convenience function for section citation analysis.

    Args:
        paper_text: Full paper text
        cited_papers: Optional paper metadata
        llm_provider: LLM provider

    Returns:
        SectionCitationAnalysis
    """
    analyzer = SectionCitationAnalyzer(
        config=SectionAnalysisConfig(
            use_llm=llm_provider is not None,
            llm_provider=llm_provider,
        ),
    )
    return await analyzer.analyze(paper_text, cited_papers)
