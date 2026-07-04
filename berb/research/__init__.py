"""Research exploration module for Berb.

Parallelized agentic tree search for exploring multiple research directions.
Open-ended discovery for template-free exploration.
Research gap analysis with multi-perspective reasoning.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .gap_analysis import (
    GapAnalysisConfig,
    GapAnalysisResult,
    GapToHypothesisConverter,
    GapType,
    ResearchGap,
    ResearchGapAnalyzer,
    analyze_research_gaps,
)
from .idea_scorer import (
    IdeaQualityScorer,
    NoveltyLevel,
    ResearchIdea,
    ScoredIdea,
    ScoringConfig,
    score_and_rank_ideas,
)
from .open_ended_discovery import (
    DiscoveryNode,
    DiscoveryResult,
    ExperimentManagerAgent,
    NodeStatus,
    NoveltyVerifier,
    OpenEndedDiscoveryAgent,
    run_open_ended_discovery,
)
from .tree_search import (
    BranchNode,
    BranchStatus,
    DecisionPoint,
    ParallelizedTreeSearch,
    SearchConfig,
    SearchPath,
    explore_research_space,
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
