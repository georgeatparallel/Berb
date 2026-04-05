"""Tests for Hidden Consistent Evaluation (Upgrade 2) and Council Mode (Upgrade 3)."""

import pytest
from unittest.mock import AsyncMock, patch

from berb.validation.hidden_eval import (
    HiddenConsistentEvaluation,
    PaperDocument,
    EvaluationResult,
    CriteriaVisibility,
)
from berb.review.council_mode import (
    CouncilMode,
    CouncilReport,
    CouncilSynthesis,
    CouncilConfig,
)


class TestPaperDocument:
    """Test PaperDocument dataclass."""
    
    def test_paper_creation(self):
        """Test paper document creation."""
        paper = PaperDocument(
            id="test-paper-1",
            title="Test Paper",
            abstract="This is a test abstract.",
            content="This is the full paper content.",
        )
        
        assert paper.id == "test-paper-1"
        assert paper.title == "Test Paper"
        assert "test abstract" in paper.abstract
    
    def test_paper_to_markdown(self):
        """Test paper to markdown conversion."""
        paper = PaperDocument(
            id="test-paper-2",
            title="Test Paper",
            abstract="Test abstract",
            content="Test content",
        )
        
        markdown = paper.to_markdown()
        
        assert "# Test Paper" in markdown
        assert "## Abstract" in markdown
        assert "Test abstract" in markdown


class TestEvaluationResult:
    """Test EvaluationResult dataclass."""
    
    def test_result_creation(self):
        """Test evaluation result creation."""
        result = EvaluationResult(
            paper_id="test-paper-1",
            overall_score=8.5,
            dimension_scores={"novelty": 9.0, "clarity": 8.0},
            criteria_used="search",
        )
        
        assert result.paper_id == "test-paper-1"
        assert result.overall_score == 8.5
        assert result.criteria_used == "search"
    
    def test_result_to_dict(self):
        """Test result to dictionary conversion."""
        result = EvaluationResult(
            paper_id="test-paper-2",
            overall_score=7.0,
            dimension_scores={"impact": 7.0},
            criteria_used="selection",
        )
        
        d = result.to_dict()
        
        assert d["paper_id"] == "test-paper-2"
        assert d["overall_score"] == 7.0
        assert "timestamp" in d


class TestHiddenConsistentEvaluation:
    """Test HiddenConsistentEvaluation."""
    
    def test_initialization(self):
        """Test HCE initialization."""
        hce = HiddenConsistentEvaluation()
        
        assert hce.search_criteria is not None
        assert hce.selection_criteria is not None
        assert hce.test_criteria is not None
        
        # Verify three-way split
        assert hce.search_criteria.visibility == CriteriaVisibility.SEARCH
        assert hce.selection_criteria.visibility == CriteriaVisibility.SELECTION
        assert hce.test_criteria.visibility == CriteriaVisibility.TEST
    
    def test_criteria_info(self):
        """Test criteria information retrieval."""
        hce = HiddenConsistentEvaluation()
        info = hce.get_criteria_info()
        
        assert "search" in info
        assert "selection" in info
        assert "test" in info
        
        assert "dimensions" in info["search"]
        assert "dimensions" in info["selection"]
    
    def test_compute_weighted_score(self):
        """Test weighted score computation."""
        hce = HiddenConsistentEvaluation()
        
        scores = {"novelty": 8.0, "technical_soundness": 9.0}
        weights = {"novelty": 0.5, "technical_soundness": 0.5}
        
        overall = hce._compute_weighted_score(scores, weights)
        
        assert overall == 8.5
    
    def test_compute_weighted_score_empty(self):
        """Test weighted score with empty scores."""
        hce = HiddenConsistentEvaluation()
        
        overall = hce._compute_weighted_score({}, {"novelty": 0.5})
        
        assert overall == 0.0
    
    def test_parse_scores_valid_json(self):
        """Test score parsing from valid JSON."""
        hce = HiddenConsistentEvaluation()
        
        response = '{"novelty": 8, "clarity": 7}'
        scores = hce._parse_scores(response)
        
        assert scores["novelty"] == 8.0
        assert scores["clarity"] == 7.0
    
    def test_parse_scores_invalid_json(self):
        """Test score parsing from invalid JSON."""
        hce = HiddenConsistentEvaluation()
        
        response = "Invalid response"
        scores = hce._parse_scores(response)
        
        assert scores == {}


class TestCouncilConfig:
    """Test CouncilConfig dataclass."""
    
    def test_default_config(self):
        """Test default council configuration."""
        config = CouncilConfig()
        
        assert config.models == []
        assert config.judge_model == "claude-sonnet"
        assert config.parallel is True
    
    def test_custom_config(self):
        """Test custom council configuration."""
        config = CouncilConfig(
            models=["claude-opus", "gpt-4o"],
            judge_model="claude-sonnet",
            task="Test task",
        )
        
        assert len(config.models) == 2
        assert config.judge_model == "claude-sonnet"
        assert config.task == "Test task"


class TestCouncilReport:
    """Test CouncilReport dataclass."""
    
    def test_report_creation(self):
        """Test council report creation."""
        report = CouncilReport(
            model="claude-opus",
            content="Test content",
            key_points=["Point 1", "Point 2"],
            confidence=0.85,
            unique_insights=["Unique insight"],
        )
        
        assert report.model == "claude-opus"
        assert len(report.key_points) == 2
        assert report.confidence == 0.85


class TestCouncilSynthesis:
    """Test CouncilSynthesis dataclass."""
    
    def test_synthesis_creation(self):
        """Test council synthesis creation."""
        synthesis = CouncilSynthesis(
            agreements=["Agreement 1"],
            divergences=["Divergence 1"],
            unique_insights={"model1": ["insight1"]},
            consensus_score=0.75,
            recommendation="Test recommendation",
            cover_letter="Test cover letter",
        )
        
        assert len(synthesis.agreements) == 1
        assert len(synthesis.divergences) == 1
        assert synthesis.consensus_score == 0.75
    
    def test_synthesis_to_dict(self):
        """Test synthesis to dictionary conversion."""
        synthesis = CouncilSynthesis(
            agreements=["Agreement"],
            consensus_score=0.8,
            recommendation="Recommendation",
        )
        
        d = synthesis.to_dict()
        
        assert d["agreements"] == ["Agreement"]
        assert d["consensus_score"] == 0.8
        assert d["recommendation"] == "Recommendation"


class TestCouncilMode:
    """Test CouncilMode."""
    
    def test_initialization(self):
        """Test council mode initialization."""
        council = CouncilMode()
        
        assert council.config is not None
        assert council.config.judge_model == "claude-sonnet"
    
    def test_custom_initialization(self):
        """Test council mode with custom config."""
        config = CouncilConfig(
            models=["claude-opus", "gpt-4o"],
            judge_model="claude-sonnet",
        )
        council = CouncilMode(config)
        
        assert council.config.judge_model == "claude-sonnet"
        assert len(council.config.models) == 2
    
    def test_extract_key_points(self):
        """Test key point extraction."""
        council = CouncilMode()
        
        content = """
Key findings:
- Point 1
- Point 2
- Point 3
"""
        points = council._extract_key_points(content)
        
        assert len(points) > 0
        assert "Point 1" in points
    
    def test_extract_unique_insights(self):
        """Test unique insight extraction."""
        council = CouncilMode()
        
        content = """
Unique insight: This is often overlooked.
Importantly, this finding suggests...
"""
        insights = council._extract_unique_insights(content)
        
        assert len(insights) > 0
    
    def test_estimate_confidence_high(self):
        """Test confidence estimation with high confidence indicators."""
        council = CouncilMode()
        
        content = "I am confident this is clearly correct."
        confidence = council._estimate_confidence(content)
        
        assert confidence > 0.5
    
    def test_estimate_confidence_low(self):
        """Test confidence estimation with low confidence indicators."""
        council = CouncilMode()
        
        content = "This might possibly be uncertain."
        confidence = council._estimate_confidence(content)
        
        assert confidence < 0.7
    
    def test_parse_synthesis_valid_json(self):
        """Test synthesis parsing from valid JSON."""
        council = CouncilMode()
        
        response = '''
{
    "agreements": ["Agreement 1"],
    "divergences": [],
    "unique_insights": {},
    "consensus_score": 0.8,
    "recommendation": "Proceed",
    "cover_letter": "Cover letter text"
}
'''
        reports = [CouncilReport(model="model1", content="test")]
        synthesis = council._parse_synthesis(response, reports)
        
        assert len(synthesis.agreements) == 1
        assert synthesis.consensus_score == 0.8
    
    def test_parse_synthesis_invalid_json(self):
        """Test synthesis parsing from invalid JSON."""
        council = CouncilMode()
        
        response = "Invalid response"
        reports = [CouncilReport(model="model1", content="test")]
        synthesis = council._parse_synthesis(response, reports)
        
        assert synthesis.consensus_score == 0.5  # Default


class TestIntegration:
    """Integration tests for HCE and Council."""
    
    def test_hce_criteria_independence(self):
        """Test that HCE criteria are independent."""
        hce = HiddenConsistentEvaluation()
        
        # Verify different dimensions
        search_dims = set(hce.search_criteria.dimensions)
        selection_dims = set(hce.selection_criteria.dimensions)
        test_dims = set(hce.test_criteria.dimensions)
        
        # Should have some overlap but not identical
        assert search_dims != selection_dims
        assert selection_dims != test_dims
    
    def test_council_parallel_flag(self):
        """Test council parallel execution flag."""
        config_parallel = CouncilConfig(parallel=True)
        config_sequential = CouncilConfig(parallel=False)
        
        assert config_parallel.parallel is True
        assert config_sequential.parallel is False
