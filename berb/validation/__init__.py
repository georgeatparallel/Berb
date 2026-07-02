"""Validation modules for Berb.

Finding reproduction for system validation, reference integrity checking,
claim tracking, claim confidence analysis, source-claim alignment,
claim verification pipeline, manuscript self-check, and hidden consistent
evaluation (HCE) for preventing evaluation gaming.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .claim_confidence import (
    ClaimConfidenceAnalyzer,
    ClaimConfidenceConfig,
    ClaimConfidenceLevel,
    ClaimConfidenceResult,
    ExtractedClaim,
    UnsupportedClaim,
    analyze_claim_confidence,
    flag_paper_claims,
)
from .claim_tracker import (
    ChallengeEvent,
    ClaimExtractionConfig,
    ClaimIntegrityChecker,
    ClaimIntegrityReport,
    ClaimRecord,
    ClaimTracker,
    ClaimVerdict,
    track_paper_claims,
)
from .claim_verification import (
    ClaimVerification,
    ClaimVerificationPipeline,
    VerificationConfig,
    VerificationReport,
    check_claim_support,
    verify_paper_claims,
)
from .finding_reproduction import (
    FindingReproducer,
    KnownFinding,
    KnownFindingDatabase,
    ReproductionResult,
    ReproductionStatus,
    ReproductionWorkflow,
    reproduce_finding,
)
from .hidden_eval import (
    CriteriaVisibility,
    EvalCriteria,
    EvaluationResult,
    HiddenConsistentEvaluation,
    PaperDocument,
)
from .manuscript_self_check import (
    FormatError,
    IssueSeverity,
    ManuscriptIntegrityReport,
    ManuscriptSelfChecker,
    MisalignmentWarning,
    OmissionWarning,
    UncitedClaim,
)
from .reference_integrity import (
    EditorialNotice,
    IntegrityReport,
    JournalQuality,
    ReferenceIntegrityChecker,
    ReferenceIntegrityIssue,
    RetractionStatus,
    StalenessReport,
)
from .source_alignment import (
    AlignmentCheck,
    AlignmentConfig,
    AlignmentReport,
    AlignmentResult,
    SourceClaimAligner,
    check_citation_alignment,
    verify_paper_citations,
)

__all__ = [
    # Claim confidence
    "ClaimConfidenceAnalyzer",
    "ClaimConfidenceLevel",
    "ClaimConfidenceResult",
    "ClaimConfidenceConfig",
    "ExtractedClaim",
    "UnsupportedClaim",
    "analyze_claim_confidence",
    "flag_paper_claims",
    # Claim tracking
    "ClaimTracker",
    "ClaimIntegrityChecker",
    "ClaimRecord",
    "ClaimVerdict",
    "ClaimIntegrityReport",
    "ChallengeEvent",
    "ClaimExtractionConfig",
    "track_paper_claims",
    # Claim verification
    "ClaimVerificationPipeline",
    "ClaimVerification",
    "VerificationReport",
    "VerificationConfig",
    "verify_paper_claims",
    "check_claim_support",
    # Finding reproduction
    "FindingReproducer",
    "KnownFinding",
    "KnownFindingDatabase",
    "ReproductionWorkflow",
    "ReproductionResult",
    "ReproductionStatus",
    "reproduce_finding",
    # Hidden consistent evaluation (NEW)
    "HiddenConsistentEvaluation",
    "PaperDocument",
    "EvaluationResult",
    "EvalCriteria",
    "CriteriaVisibility",
    # Manuscript self-check
    "ManuscriptSelfChecker",
    "ManuscriptIntegrityReport",
    "MisalignmentWarning",
    "OmissionWarning",
    "UncitedClaim",
    "FormatError",
    "IssueSeverity",
    # Reference integrity
    "ReferenceIntegrityChecker",
    "RetractionStatus",
    "JournalQuality",
    "StalenessReport",
    "ReferenceIntegrityIssue",
    "IntegrityReport",
    "EditorialNotice",
    # Source alignment
    "SourceClaimAligner",
    "AlignmentResult",
    "AlignmentCheck",
    "AlignmentReport",
    "AlignmentConfig",
    "check_citation_alignment",
    "verify_paper_citations",
]
