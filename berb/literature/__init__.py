"""Literature search and analysis module for Berb.

Includes citation classification, evidence consensus mapping,
citation graph analysis, section-aware citation analysis,
structured reading notes, multimodal literature analysis,
recency filtering, and file-system-based literature processing
for handling 200-400 papers efficiently.

Re-exports are lazy (PEP 562): touching this package no longer pulls arxiv,
feedparser, httpx and the LLM client into every importer. Names resolve on
first attribute access.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from berb._lazy import lazy_exports

_EXPORTS = {
    # Models
    "Author": "models",
    "Paper": "models",
    # Search
    "search_papers": "search",
    # Verification
    "CitationResult": "verify",
    "VerificationReport": "verify",
    "VerifyStatus": "verify",
    "verify_citations": "verify",
    # Multimodal
    "MultimodalLiteratureAgent": "multimodal_search",
    "MultimodalPaper": "multimodal_search",
    "FigureAnalysis": "multimodal_search",
    "ExtractedChartData": "multimodal_search",
    "ExtractedTableData": "multimodal_search",
    "analyze_paper_multimodal": "multimodal_search",
    # Citation classification
    "CitationClassifier": "citation_classifier",
    "CitationIntent": "citation_classifier",
    "CitationClassification": "citation_classifier",
    "PaperCitationProfile": "citation_classifier",
    "CitationClassifierConfig": "citation_classifier",
    "classify_citations": "citation_classifier",
    # Evidence mapping
    "EvidenceConsensusMapper": "evidence_map",
    "EvidenceMap": "evidence_map",
    "EvidenceMapGenerator": "evidence_map",
    "ClaimEvidence": "evidence_map",
    "StudyProfile": "evidence_map",
    "StudyType": "evidence_map",
    "ConsensusLevel": "evidence_map",
    "EvidenceConsensusConfig": "evidence_map",
    "build_evidence_map": "evidence_map",
    # Citation graph
    "CitationGraphEngine": "citation_graph",
    "CitationGraphClient": "citation_graph",
    "CitationGraphConfig": "citation_graph",
    "CitationGraphPaper": ("citation_graph", "Paper"),
    "Cluster": "citation_graph",
    "Contradiction": "citation_graph",
    "JournalQuality": "citation_graph",
    "analyze_citation_network": "citation_graph",
    # Section analysis
    "SectionCitationAnalyzer": "section_analysis",
    "SectionCitation": "section_analysis",
    "PaperSection": "section_analysis",
    "CitationPurpose": "section_analysis",
    "SectionPaperCitationProfile": ("section_analysis", "PaperCitationProfile"),
    "CitationRecommendation": "section_analysis",
    "SectionCitationAnalysis": "section_analysis",
    "SectionAnalysisConfig": "section_analysis",
    "CitationPlacementOptimizer": "section_analysis",
    "analyze_section_citations": "section_analysis",
    # Structured notes
    "StructuredNotesGenerator": "structured_notes",
    "PaperReadingNote": "structured_notes",
    "ClaimWithEvidence": "structured_notes",
    "ReadingNotesCollection": "structured_notes",
    "ReadingNotesConfig": "structured_notes",
    "generate_reading_notes": "structured_notes",
    # Recency filter
    "RecencyFilter": "recency_filter",
    "RecencyFilterConfig": "recency_filter",
    "RecencyAwareRanker": "recency_filter",
    "filter_papers_by_recency": "recency_filter",
    "rank_papers_with_recency": "recency_filter",
    # FS-based processing
    "FileSystemLiteratureProcessor": "fs_processor",
    "LiteratureWorkspace": "fs_processor",
    "RelevantExcerpt": "fs_processor",
    "FileSystemQueryEngine": "fs_query",
    "QueryConfig": "fs_query",
}

__getattr__, __dir__ = lazy_exports(__name__, _EXPORTS, globals())

if TYPE_CHECKING:
    from .citation_classifier import (
        CitationClassification,
        CitationClassifier,
        CitationClassifierConfig,
        CitationIntent,
        PaperCitationProfile,
        classify_citations,
    )
    from .citation_graph import (
        CitationGraphClient,
        CitationGraphConfig,
        CitationGraphEngine,
        Cluster,
        Contradiction,
        JournalQuality,
        analyze_citation_network,
    )
    from .citation_graph import (
        Paper as CitationGraphPaper,
    )
    from .evidence_map import (
        ClaimEvidence,
        ConsensusLevel,
        EvidenceConsensusConfig,
        EvidenceConsensusMapper,
        EvidenceMap,
        EvidenceMapGenerator,
        StudyProfile,
        StudyType,
        build_evidence_map,
    )
    from .fs_processor import (
        FileSystemLiteratureProcessor,
        LiteratureWorkspace,
        RelevantExcerpt,
    )
    from .fs_query import (
        FileSystemQueryEngine,
        QueryConfig,
    )
    from .models import Author, Paper
    from .multimodal_search import (
        ExtractedChartData,
        ExtractedTableData,
        FigureAnalysis,
        MultimodalLiteratureAgent,
        MultimodalPaper,
        analyze_paper_multimodal,
    )
    from .recency_filter import (
        RecencyAwareRanker,
        RecencyFilter,
        RecencyFilterConfig,
        filter_papers_by_recency,
        rank_papers_with_recency,
    )
    from .search import search_papers
    from .section_analysis import (
        CitationPlacementOptimizer,
        CitationPurpose,
        CitationRecommendation,
        PaperSection,
        SectionAnalysisConfig,
        SectionCitation,
        SectionCitationAnalysis,
        SectionCitationAnalyzer,
        analyze_section_citations,
    )
    from .section_analysis import (
        PaperCitationProfile as SectionPaperCitationProfile,
    )
    from .structured_notes import (
        ClaimWithEvidence,
        PaperReadingNote,
        ReadingNotesCollection,
        ReadingNotesConfig,
        StructuredNotesGenerator,
        generate_reading_notes,
    )
    from .verify import (
        CitationResult,
        VerificationReport,
        VerifyStatus,
        verify_citations,
    )

__all__ = [
    # Models
    "Author",
    "Paper",
    # Search
    "search_papers",
    # Verification
    "CitationResult",
    "VerificationReport",
    "VerifyStatus",
    "verify_citations",
    # Multimodal
    "MultimodalLiteratureAgent",
    "MultimodalPaper",
    "FigureAnalysis",
    "ExtractedChartData",
    "ExtractedTableData",
    "analyze_paper_multimodal",
    # Citation classification
    "CitationClassifier",
    "CitationIntent",
    "CitationClassification",
    "PaperCitationProfile",
    "CitationClassifierConfig",
    "classify_citations",
    # Evidence mapping
    "EvidenceConsensusMapper",
    "EvidenceMap",
    "EvidenceMapGenerator",
    "ClaimEvidence",
    "StudyProfile",
    "StudyType",
    "ConsensusLevel",
    "EvidenceConsensusConfig",
    "build_evidence_map",
    # Citation graph
    "CitationGraphEngine",
    "CitationGraphClient",
    "CitationGraphConfig",
    "CitationGraphPaper",
    "Cluster",
    "Contradiction",
    "JournalQuality",
    "analyze_citation_network",
    # Section analysis
    "SectionCitationAnalyzer",
    "SectionCitation",
    "PaperSection",
    "CitationPurpose",
    "SectionPaperCitationProfile",
    "CitationRecommendation",
    "SectionCitationAnalysis",
    "SectionAnalysisConfig",
    "CitationPlacementOptimizer",
    "analyze_section_citations",
    # Structured notes
    "StructuredNotesGenerator",
    "PaperReadingNote",
    "ClaimWithEvidence",
    "ReadingNotesCollection",
    "ReadingNotesConfig",
    "generate_reading_notes",
    # Recency filter
    "RecencyFilter",
    "RecencyFilterConfig",
    "RecencyAwareRanker",
    "filter_papers_by_recency",
    "rank_papers_with_recency",
    # FS-based processing (NEW)
    "FileSystemLiteratureProcessor",
    "LiteratureWorkspace",
    "RelevantExcerpt",
    "FileSystemQueryEngine",
    "QueryConfig",
]
