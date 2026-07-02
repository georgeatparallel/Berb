"""Literature search and analysis module for Berb.

Includes citation classification, evidence consensus mapping,
citation graph analysis, section-aware citation analysis,
structured reading notes, multimodal literature analysis,
recency filtering, and file-system-based literature processing
for handling 200-400 papers efficiently.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

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
