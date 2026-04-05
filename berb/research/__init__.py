"""Research exploration module for Berb.

Parallelized agentic tree search for exploring multiple research directions.
Open-ended discovery for template-free exploration.
Research gap analysis with multi-perspective reasoning.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .tree_search import (
    ParallelizedTreeSearch,
    SearchConfig,
    SearchPath,
    BranchNode,
    BranchStatus,
    DecisionPoint,
    explore_research_space,
)
from .idea_scorer import (
    IdeaQualityScorer,
    ScoringConfig,
    ResearchIdea,
    ScoredIdea,
    NoveltyLevel,
    score_and_rank_ideas,
)
from .open_ended_discovery import (
    OpenEndedDiscoveryAgent,
    DiscoveryNode,
    DiscoveryResult,
    NodeStatus,
    ExperimentManagerAgent,
    NoveltyVerifier,
    run_open_ended_discovery,
)
from .gap_analysis import (
    ResearchGapAnalyzer,
    GapAnalysisResult,
    ResearchGap,
    GapType,
    GapAnalysisConfig,
    GapToHypothesisConverter,
    analyze_research_gaps,
)

__all__ = [
    # Tree search
    "ParallelizedTreeSearch",
    "SearchConfig",
    "SearchPath",
    "BranchNode",
    "BranchStatus",
    "DecisionPoint",
    "explore_research_space",
    # Idea scoring
    "IdeaQualityScorer",
    "ScoringConfig",
    "ResearchIdea",
    "ScoredIdea",
    "NoveltyLevel",
    "score_and_rank_ideas",
    # Open-ended discovery
    "OpenEndedDiscoveryAgent",
    "DiscoveryNode",
    "DiscoveryResult",
    "NodeStatus",
    "ExperimentManagerAgent",
    "NoveltyVerifier",
    "run_open_ended_discovery",
    # Gap analysis
    "ResearchGapAnalyzer",
    "GapAnalysisResult",
    "ResearchGap",
    "GapType",
    "GapAnalysisConfig",
    "GapToHypothesisConverter",
    "analyze_research_gaps",
]
