"""Tests for Hidden Consistent Evaluation (Upgrade 2)."""

from berb.integrity.eval.hidden_eval import (
    CriteriaVisibility,
    EvaluationResult,
    HiddenConsistentEvaluation,
    PaperDocument,
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




class TestHCEIntegration:
    """Integration tests for HCE."""

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
